from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import httpx

from capexgraph.config import load_project_env
from capexgraph.providers.errors import ProviderConfigurationError

DEFAULT_CODEX_BASE_URL = "http://127.0.0.1:8317/v1"
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def validate_codex_base_url(value: str, *, allow_remote: bool = False) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProviderConfigurationError(
            "CAPEXGRAPH_CODEX_BASE_URL must be an absolute HTTP(S) URL.",
            provider="codex_subscription",
        )
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderConfigurationError(
            "CAPEXGRAPH_CODEX_BASE_URL cannot contain credentials, query, or fragment.",
            provider="codex_subscription",
        )
    if parsed.hostname.lower() not in _LOOPBACK_HOSTS and not allow_remote:
        raise ProviderConfigurationError(
            "Codex subscription proxy must use loopback unless "
            "CAPEXGRAPH_ALLOW_REMOTE_CODEX_PROXY=1 is explicitly set.",
            provider="codex_subscription",
        )
    if parsed.path.rstrip("/") != "/v1":
        raise ProviderConfigurationError(
            "CAPEXGRAPH_CODEX_BASE_URL must end with /v1.",
            provider="codex_subscription",
        )
    return urlunsplit((parsed.scheme, parsed.netloc, "/v1", "", ""))


@dataclass(frozen=True)
class ModelSettings:
    openai_model: str | None = None
    openai_api_key: str | None = field(default=None, repr=False)
    openai_legacy_model: bool = False
    codex_transport: str = "cli"
    codex_cli_path: str | None = None
    codex_model: str | None = None
    codex_base_url: str = DEFAULT_CODEX_BASE_URL
    codex_proxy_key: str | None = field(default=None, repr=False)
    codex_timeout_seconds: float = 180.0
    allow_remote_codex_proxy: bool = False
    configuration_errors: tuple[str, ...] = ()

    @classmethod
    def from_environment(cls, *, load_env: bool = True) -> ModelSettings:
        if load_env:
            load_project_env()
        explicit_openai_model = os.getenv("CAPEXGRAPH_OPENAI_MODEL", "").strip()
        legacy_model = os.getenv("CAPEXGRAPH_MODEL", "").strip()
        errors: list[str] = []
        timeout_value = os.getenv("CAPEXGRAPH_CODEX_TIMEOUT_SECONDS", "180").strip()
        try:
            timeout = float(timeout_value)
            if not 1 <= timeout <= 600:
                raise ValueError
        except ValueError:
            timeout = 180.0
            errors.append("CAPEXGRAPH_CODEX_TIMEOUT_SECONDS must be between 1 and 600.")
        proxy_key = os.getenv("CAPEXGRAPH_CODEX_PROXY_KEY", "").strip() or None
        explicit_transport = os.getenv("CAPEXGRAPH_CODEX_TRANSPORT", "").strip().lower()
        codex_transport = explicit_transport or ("proxy" if proxy_key else "cli")
        if codex_transport not in {"cli", "proxy"}:
            errors.append("CAPEXGRAPH_CODEX_TRANSPORT must be cli or proxy.")
            codex_transport = "cli"
        return cls(
            openai_model=explicit_openai_model or legacy_model or None,
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip() or None,
            openai_legacy_model=not explicit_openai_model and bool(legacy_model),
            codex_transport=codex_transport,
            codex_cli_path=os.getenv("CAPEXGRAPH_CODEX_CLI_PATH", "").strip() or None,
            codex_model=os.getenv("CAPEXGRAPH_CODEX_MODEL", "").strip() or None,
            codex_base_url=(
                os.getenv("CAPEXGRAPH_CODEX_BASE_URL", "").strip()
                or DEFAULT_CODEX_BASE_URL
            ),
            codex_proxy_key=proxy_key,
            codex_timeout_seconds=timeout,
            allow_remote_codex_proxy=_enabled("CAPEXGRAPH_ALLOW_REMOTE_CODEX_PROXY"),
            configuration_errors=tuple(errors),
        )

    def provider_status(self, *, probe_codex: bool = False) -> list[dict[str, object]]:
        codex_status = self._codex_provider_status(probe_codex=probe_codex)

        openai_missing = [
            name
            for name, value in (
                ("CAPEXGRAPH_OPENAI_MODEL", self.openai_model),
                ("OPENAI_API_KEY", self.openai_api_key),
            )
            if not value
        ]
        return [
            {
                "name": "fixture",
                "configured": True,
                "model": "bundled golden fixtures",
                "setup_kind": "none",
                "billing_mode": "none",
                "endpoint_scope": "local",
                "reachability": "ready",
                "missing": [],
                "errors": [],
            },
            codex_status,
            {
                "name": "openai",
                "configured": not openai_missing,
                "model": self.openai_model,
                "setup_kind": "official_api",
                "billing_mode": "openai_api",
                "endpoint_scope": "api.openai.com",
                "reachability": "not_checked" if not openai_missing else "not_configured",
                "missing": openai_missing,
                "errors": [],
                "legacy_model_setting": self.openai_legacy_model,
            },
        ]

    def _codex_provider_status(self, *, probe_codex: bool) -> dict[str, object]:
        if self.codex_transport == "proxy":
            codex_missing = [
                name
                for name, value in (
                    ("CAPEXGRAPH_CODEX_MODEL", self.codex_model),
                    ("CAPEXGRAPH_CODEX_PROXY_KEY", self.codex_proxy_key),
                )
                if not value
            ]
            endpoint_scope = "invalid"
            endpoint_error = ""
            try:
                codex_base_url = validate_codex_base_url(
                    self.codex_base_url,
                    allow_remote=self.allow_remote_codex_proxy,
                )
                endpoint_scope = (
                    "loopback"
                    if urlsplit(codex_base_url).hostname.lower() in _LOOPBACK_HOSTS
                    else "remote_opt_in"
                )
            except ProviderConfigurationError as error:
                codex_base_url = ""
                endpoint_error = error.safe_message
            configured = (
                not codex_missing
                and not endpoint_error
                and not self.configuration_errors
            )
            reachability = "not_checked" if configured else "not_configured"
            if probe_codex and configured:
                reachability = _probe_codex_proxy(
                    codex_base_url,
                    self.codex_proxy_key or "",
                )
            return {
                "name": "codex_subscription",
                "configured": configured,
                "model": self.codex_model,
                "setup_kind": "local_proxy",
                "transport": "cli_proxy_api",
                "billing_mode": "chatgpt_subscription",
                "endpoint_scope": endpoint_scope,
                "reachability": reachability,
                "missing": codex_missing,
                "errors": [
                    item
                    for item in (*self.configuration_errors, endpoint_error)
                    if item
                ],
            }

        from capexgraph.providers.codex_cli import (
            discover_codex_cli,
            probe_codex_cli,
        )

        if probe_codex:
            cli = probe_codex_cli(self.codex_cli_path)
            installed = bool(cli["installed"])
            configured = bool(
                installed
                and cli["authenticated"]
                and cli["auth_mode"] == "chatgpt"
                and not self.configuration_errors
            )
            reachability = str(cli["reachability"])
            missing = (
                []
                if configured
                else ["Codex CLI"]
                if not installed
                else ["ChatGPT login"]
            )
            cli_version = cli["version"]
            auth_mode = cli["auth_mode"]
            cli_errors = list(cli["errors"])
        else:
            executable, cli_version = discover_codex_cli(self.codex_cli_path)
            installed = executable is not None
            configured = installed and not self.configuration_errors
            reachability = "not_checked" if installed else "not_installed"
            missing = [] if installed else ["Codex CLI"]
            auth_mode = None
            cli_errors = []
        return {
            "name": "codex_subscription",
            "configured": configured,
            "model": self.codex_model or "Codex CLI default",
            "setup_kind": "official_codex_cli",
            "transport": "codex_exec",
            "billing_mode": "chatgpt_subscription",
            "endpoint_scope": "local_process",
            "reachability": reachability,
            "missing": missing,
            "errors": [*self.configuration_errors, *cli_errors],
            "cli_version": cli_version,
            "auth_mode": auth_mode,
        }


def _probe_codex_proxy(base_url: str, proxy_key: str) -> str:
    try:
        response = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {proxy_key}"},
            timeout=2.0,
            trust_env=False,
        )
    except httpx.HTTPError:
        return "unreachable"
    if response.status_code in {401, 403}:
        return "authentication_failed"
    if response.is_success:
        return "reachable"
    return f"http_{response.status_code}"
