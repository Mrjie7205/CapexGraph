from __future__ import annotations

import atexit
import copy
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
from collections import deque
from pathlib import Path
from typing import Any

from capexgraph.providers.base import StructuredOutput
from capexgraph.providers.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderOutputValidationError,
    ProviderProtocolError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    ResearchProviderError,
)

_APP_SERVER_LOCK = threading.Lock()
_APP_SERVER: CodexAppServerClient | None = None


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _candidate_paths(explicit: str | None = None) -> list[Path]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    configured = os.getenv("CAPEXGRAPH_CODEX_CLI_PATH", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())

    codex_home = Path(os.getenv("CODEX_HOME", "") or Path.home() / ".codex")
    executable = "codex.exe" if os.name == "nt" else "codex"
    candidates.extend(
        [
            codex_home / ".sandbox-bin" / executable,
            codex_home / "plugins" / ".plugin-appserver" / executable,
            Path.home() / ".codex" / ".sandbox-bin" / executable,
            Path.home() / ".codex" / "plugins" / ".plugin-appserver" / executable,
        ]
    )
    if discovered := shutil.which("codex"):
        candidates.append(Path(discovered))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        identity = str(candidate.resolve(strict=False)).casefold()
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(candidate)
    return unique


def _run_codex(
    executable: Path,
    arguments: list[str],
    *,
    timeout: float,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(executable), *arguments],
        cwd=str(cwd) if cwd is not None else None,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        creationflags=_creation_flags(),
    )


def discover_codex_cli(explicit: str | None = None) -> tuple[Path | None, str | None]:
    for candidate in _candidate_paths(explicit):
        if not candidate.is_file():
            continue
        try:
            result = _run_codex(candidate, ["--version"], timeout=4)
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            version = (result.stdout or result.stderr).strip() or "unknown"
            return candidate.resolve(), version
    return None, None


def probe_codex_cli(explicit: str | None = None) -> dict[str, object]:
    executable, version = discover_codex_cli(explicit)
    if executable is None:
        return {
            "installed": False,
            "authenticated": False,
            "auth_mode": None,
            "version": None,
            "reachability": "not_installed",
            "errors": [],
        }
    try:
        result = _run_codex(executable, ["login", "status"], timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return {
            "installed": True,
            "authenticated": False,
            "auth_mode": None,
            "version": version,
            "reachability": "unreachable",
            "errors": ["Codex login status could not be checked."],
        }
    output = f"{result.stdout}\n{result.stderr}".strip()
    normalized = output.casefold()
    authenticated = result.returncode == 0
    if "chatgpt" in normalized:
        auth_mode = "chatgpt"
    elif "api key" in normalized or "apikey" in normalized:
        auth_mode = "api_key"
    elif authenticated:
        auth_mode = "unknown"
    else:
        auth_mode = None
    reachability = (
        "ready"
        if authenticated and auth_mode == "chatgpt"
        else "wrong_auth_mode"
        if authenticated
        else "login_required"
    )
    return {
        "installed": True,
        "authenticated": authenticated,
        "auth_mode": auth_mode,
        "version": version,
        "reachability": reachability,
        "errors": [],
    }


class CodexAppServerClient:
    """Minimal official Codex app-server client for account and model setup."""

    def __init__(self, executable: Path) -> None:
        self.executable = executable
        self._process: subprocess.Popen[str] | None = None
        self._write_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._next_id = 0
        self._stderr: deque[str] = deque(maxlen=20)
        self._login_state: dict[str, object] = {}

    @property
    def running(self) -> bool:
        return bool(self._process and self._process.poll() is None)

    def _reader(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for raw_line in process.stdout:
            try:
                message = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            message_id = message.get("id")
            if isinstance(message_id, int):
                with self._pending_lock:
                    waiter = self._pending.get(message_id)
                if waiter is not None:
                    waiter.put(message)
                continue
            if message.get("method") == "account/login/completed":
                params = message.get("params")
                if isinstance(params, dict):
                    self._login_state = {
                        "login_id": params.get("loginId"),
                        "completed": True,
                        "success": bool(params.get("success")),
                        "error": (
                            "Codex login failed."
                            if params.get("error")
                            else None
                        ),
                    }

    def _stderr_reader(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for raw_line in process.stderr:
            line = raw_line.strip()
            if line:
                self._stderr.append(line[:500])

    def _send(self, payload: dict[str, object]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise ProviderUnavailableError(
                "Codex app server is not running.",
                provider="codex_subscription",
            )
        with self._write_lock:
            process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
            process.stdin.flush()

    def _request(
        self,
        method: str,
        params: dict[str, object] | None = None,
        *,
        timeout: float = 10,
    ) -> dict[str, Any]:
        self.start()
        with self._pending_lock:
            self._next_id += 1
            request_id = self._next_id
            waiter: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = waiter
        payload: dict[str, object] = {"method": method, "id": request_id}
        if params is not None:
            payload["params"] = params
        try:
            self._send(payload)
            try:
                response = waiter.get(timeout=timeout)
            except queue.Empty as error:
                raise ProviderUnavailableError(
                    f"Codex app server timed out while handling {method}.",
                    provider="codex_subscription",
                ) from error
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        if response.get("error"):
            raise ProviderProtocolError(
                f"Codex app server rejected {method}.",
                provider="codex_subscription",
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise ProviderProtocolError(
                f"Codex app server returned an invalid {method} response.",
                provider="codex_subscription",
            )
        return result

    def start(self) -> None:
        if self.running:
            return
        with self._start_lock:
            if self.running:
                return
            self.close()
            try:
                self._process = subprocess.Popen(
                    [
                        str(self.executable),
                        "app-server",
                        "--listen",
                        "stdio://",
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=_creation_flags(),
                )
            except OSError as error:
                raise ProviderUnavailableError(
                    "Codex app server could not be started.",
                    provider="codex_subscription",
                ) from error
            threading.Thread(target=self._reader, daemon=True).start()
            threading.Thread(target=self._stderr_reader, daemon=True).start()

            with self._pending_lock:
                self._next_id += 1
                request_id = self._next_id
                waiter: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
                self._pending[request_id] = waiter
            try:
                self._send(
                    {
                        "method": "initialize",
                        "id": request_id,
                        "params": {
                            "clientInfo": {
                                "name": "capexgraph",
                                "title": "CapexGraph",
                                "version": "0.5.1",
                            }
                        },
                    }
                )
                try:
                    initialized = waiter.get(timeout=10)
                except queue.Empty as error:
                    raise ProviderUnavailableError(
                        "Codex app server initialization timed out.",
                        provider="codex_subscription",
                    ) from error
                if initialized.get("error"):
                    raise ProviderProtocolError(
                        "Codex app server initialization failed.",
                        provider="codex_subscription",
                    )
                self._send({"method": "initialized", "params": {}})
            except Exception:
                self.close()
                raise
            finally:
                with self._pending_lock:
                    self._pending.pop(request_id, None)

    def account(self, *, refresh: bool = False) -> dict[str, Any]:
        return self._request(
            "account/read",
            {"refreshToken": refresh},
            timeout=15,
        )

    def models(self) -> list[dict[str, Any]]:
        result = self._request(
            "model/list",
            {"limit": 100, "includeHidden": False},
            timeout=15,
        )
        data = result.get("data")
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def start_chatgpt_login(self) -> dict[str, object]:
        result = self._request(
            "account/login/start",
            {
                "type": "chatgpt",
                "useHostedLoginSuccessPage": True,
                "appBrand": "chatgpt",
            },
            timeout=20,
        )
        login_id = result.get("loginId")
        auth_url = result.get("authUrl")
        if not isinstance(login_id, str) or not isinstance(auth_url, str):
            raise ProviderProtocolError(
                "Codex did not return a browser login URL.",
                provider="codex_subscription",
            )
        self._login_state = {
            "login_id": login_id,
            "completed": False,
            "success": False,
            "error": None,
        }
        return {
            **self._login_state,
            "auth_url": auth_url,
        }

    def login_state(self) -> dict[str, object]:
        return dict(self._login_state)

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()


def get_codex_app_server(
    executable: Path | None = None,
) -> CodexAppServerClient:
    global _APP_SERVER
    if executable is None:
        executable, _ = discover_codex_cli()
    if executable is None:
        raise ProviderConfigurationError(
            "Install the official Codex CLI before connecting a ChatGPT subscription.",
            provider="codex_subscription",
        )
    with _APP_SERVER_LOCK:
        if _APP_SERVER is None or _APP_SERVER.executable != executable:
            if _APP_SERVER is not None:
                _APP_SERVER.close()
            _APP_SERVER = CodexAppServerClient(executable)
        return _APP_SERVER


def close_codex_app_server() -> None:
    global _APP_SERVER
    with _APP_SERVER_LOCK:
        if _APP_SERVER is not None:
            _APP_SERVER.close()
            _APP_SERVER = None


atexit.register(close_codex_app_server)


def codex_connection_status(*, include_models: bool = True) -> dict[str, object]:
    cli = probe_codex_cli()
    response: dict[str, object] = {
        **cli,
        "account": None,
        "models": [],
        "selected_model": os.getenv("CAPEXGRAPH_CODEX_MODEL", "").strip() or None,
        "transport": "official_codex_cli",
    }
    if not cli["installed"]:
        return response
    try:
        client = get_codex_app_server()
        account_result = client.account()
        account = account_result.get("account")
        if isinstance(account, dict):
            account_type = account.get("type")
            email = account.get("email")
            masked_email = None
            if isinstance(email, str) and "@" in email:
                local, domain = email.split("@", 1)
                masked_email = f"{local[:1]}***@{domain}"
            response["account"] = {
                "type": account_type,
                "email": masked_email,
                "plan_type": account.get("planType"),
            }
            response["authenticated"] = account_type == "chatgpt"
            response["auth_mode"] = account_type
            response["reachability"] = (
                "ready" if account_type == "chatgpt" else "wrong_auth_mode"
            )
        if include_models and response["authenticated"]:
            models = client.models()
            response["models"] = [
                {
                    "id": item.get("id") or item.get("model"),
                    "display_name": (
                        item.get("displayName")
                        or item.get("display_name")
                        or item.get("id")
                        or item.get("model")
                    ),
                    "is_default": bool(item.get("isDefault")),
                }
                for item in models
                if item.get("id") or item.get("model")
            ]
    except ResearchProviderError as error:
        response["reachability"] = "unreachable"
        response["errors"] = [error.safe_message]
    return response


def _default_codex_model(models: list[dict[str, object]]) -> str | None:
    for model in models:
        if model.get("is_default") and isinstance(model.get("id"), str):
            return str(model["id"])
    for model in models:
        if isinstance(model.get("id"), str):
            return str(model["id"])
    return None


def resolve_codex_model(configured: str | None = None) -> str:
    if configured and configured.strip():
        return configured.strip()
    status = codex_connection_status(include_models=True)
    models = status.get("models")
    if isinstance(models, list):
        resolved = _default_codex_model(
            [item for item in models if isinstance(item, dict)]
        )
        if resolved:
            return resolved
    return "codex-cli-default"


def _resolve_local_schema_ref(
    root: dict[str, Any],
    reference: str,
) -> dict[str, Any] | None:
    if not reference.startswith("#/"):
        return None
    current: object = root
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current if isinstance(current, dict) else None


def _make_strict_schema(
    schema: dict[str, Any],
    *,
    root: dict[str, Any],
) -> dict[str, Any]:
    for container_name in ("$defs", "definitions"):
        container = schema.get(container_name)
        if isinstance(container, dict):
            for name, definition in list(container.items()):
                if isinstance(definition, dict):
                    container[name] = _make_strict_schema(definition, root=root)

    if schema.get("type") == "object":
        schema.setdefault("additionalProperties", False)

    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties)
        schema["properties"] = {
            name: (
                _make_strict_schema(property_schema, root=root)
                if isinstance(property_schema, dict)
                else property_schema
            )
            for name, property_schema in properties.items()
        }

    items = schema.get("items")
    if isinstance(items, dict):
        schema["items"] = _make_strict_schema(items, root=root)

    for union_name in ("anyOf", "oneOf", "allOf"):
        variants = schema.get(union_name)
        if isinstance(variants, list):
            schema[union_name] = [
                (
                    _make_strict_schema(variant, root=root)
                    if isinstance(variant, dict)
                    else variant
                )
                for variant in variants
            ]

    if schema.get("default", object()) is None:
        schema.pop("default", None)

    reference = schema.get("$ref")
    if isinstance(reference, str) and len(schema) > 1:
        resolved = _resolve_local_schema_ref(root, reference)
        if resolved is not None:
            merged = {**copy.deepcopy(resolved), **schema}
            merged.pop("$ref", None)
            return _make_strict_schema(merged, root=root)
    return schema


def strict_output_schema(output_model: type[StructuredOutput]) -> dict[str, Any]:
    """Build the strict JSON Schema required by Codex structured output."""

    schema = copy.deepcopy(output_model.model_json_schema())
    return _make_strict_schema(schema, root=schema)


def generate_codex_cli_output(
    output_model: type[StructuredOutput],
    *,
    system_prompt: str,
    user_prompt: str,
    model: str | None,
    timeout_seconds: float,
) -> StructuredOutput:
    executable, _ = discover_codex_cli()
    if executable is None:
        raise ProviderConfigurationError(
            "Install the official Codex CLI before using the Codex subscription.",
            provider="codex_subscription",
        )
    status = probe_codex_cli(str(executable))
    if not status["authenticated"] or status["auth_mode"] != "chatgpt":
        raise ProviderAuthenticationError(
            "Connect Codex with ChatGPT before running subscription analysis.",
            provider="codex_subscription",
        )

    resolved_model = model.strip() if model and model.strip() else None
    prompt = (
        "You are the structured research reasoning component inside CapexGraph.\n"
        "Do not inspect local files, run commands, browse, or call tools. Use only the "
        "bounded context below. Return only JSON that matches the supplied schema.\n\n"
        f"SYSTEM INSTRUCTIONS\n{system_prompt}\n\n"
        f"USER INPUT\n{user_prompt}"
    )
    with tempfile.TemporaryDirectory(prefix="capexgraph-codex-") as directory:
        root = Path(directory)
        schema_path = root / "schema.json"
        output_path = root / "output.json"
        schema_path.write_text(
            json.dumps(strict_output_schema(output_model), ensure_ascii=False),
            encoding="utf-8",
        )
        arguments = [
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--color",
            "never",
            "-c",
            "features.plugins=false",
            "-c",
            "features.remote_plugin=false",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
        ]
        if resolved_model:
            arguments.extend(["--model", resolved_model])
        arguments.append("-")
        try:
            result = _run_codex(
                executable,
                arguments,
                timeout=timeout_seconds,
                cwd=root,
                input_text=prompt,
            )
        except subprocess.TimeoutExpired as error:
            raise ProviderUnavailableError(
                "Codex subscription analysis timed out.",
                provider="codex_subscription",
            ) from error
        except OSError as error:
            raise ProviderUnavailableError(
                "Codex CLI could not be started.",
                provider="codex_subscription",
            ) from error

        if result.returncode != 0:
            diagnostic = f"{result.stderr}\n{result.stdout}".casefold()
            if "rate limit" in diagnostic or "usage limit" in diagnostic:
                raise ProviderRateLimitError(
                    "Codex subscription usage limit was reached.",
                    provider="codex_subscription",
                )
            if "login" in diagnostic or "authentication" in diagnostic:
                raise ProviderAuthenticationError(
                    "Codex ChatGPT authentication failed.",
                    provider="codex_subscription",
                )
            raise ProviderUnavailableError(
                "Codex subscription analysis failed; inspect the local Codex diagnostics.",
                provider="codex_subscription",
            )
        if not output_path.is_file():
            raise ProviderProtocolError(
                "Codex returned no structured output.",
                provider="codex_subscription",
            )
        try:
            return output_model.model_validate_json(
                output_path.read_text(encoding="utf-8")
            )
        except Exception as error:
            raise ProviderOutputValidationError(
                "Codex output failed the requested research schema.",
                provider="codex_subscription",
            ) from error
