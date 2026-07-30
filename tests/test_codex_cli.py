from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pydantic import BaseModel

from capexgraph.providers import codex_cli


class NestedOutput(BaseModel):
    label: str


class StrictOutput(BaseModel):
    item: NestedOutput
    note: str | None = None


def test_strict_output_schema_closes_nested_objects_and_requires_all_fields() -> None:
    schema = codex_cli.strict_output_schema(StrictOutput)

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["item", "note"]
    assert schema["$defs"]["NestedOutput"]["additionalProperties"] is False
    assert schema["$defs"]["NestedOutput"]["required"] == ["label"]
    assert "default" not in schema["properties"]["note"]


def test_codex_exec_is_ephemeral_isolated_and_schema_validated(
    tmp_path,
    monkeypatch,
) -> None:
    executable = tmp_path / "codex.exe"
    executable.touch()
    monkeypatch.setattr(
        codex_cli,
        "discover_codex_cli",
        lambda _explicit=None: (executable, "codex-cli test"),
    )
    monkeypatch.setattr(
        codex_cli,
        "probe_codex_cli",
        lambda _explicit=None: {
            "installed": True,
            "authenticated": True,
            "auth_mode": "chatgpt",
            "version": "codex-cli test",
            "reachability": "ready",
            "errors": [],
        },
    )
    captured: dict[str, object] = {}

    def fake_run(
        _executable,
        arguments,
        *,
        timeout,
        cwd=None,
        input_text=None,
    ):
        captured.update(
            {
                "arguments": arguments,
                "timeout": timeout,
                "cwd": cwd,
                "input_text": input_text,
            }
        )
        schema_path = Path(arguments[arguments.index("--output-schema") + 1])
        output_path = Path(arguments[arguments.index("--output-last-message") + 1])
        captured["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
        output_path.write_text(
            StrictOutput(item=NestedOutput(label="ok"), note=None).model_dump_json(),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            [str(_executable), *arguments],
            0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(codex_cli, "_run_codex", fake_run)

    result = codex_cli.generate_codex_cli_output(
        StrictOutput,
        system_prompt="system",
        user_prompt="user",
        model="gpt-test",
        timeout_seconds=30,
    )

    assert result == StrictOutput(item=NestedOutput(label="ok"), note=None)
    arguments = captured["arguments"]
    assert isinstance(arguments, list)
    assert "--ephemeral" in arguments
    assert "--sandbox" in arguments
    assert "read-only" in arguments
    assert "--ignore-user-config" in arguments
    assert "--ignore-rules" in arguments
    assert "features.plugins=false" in arguments
    assert "features.remote_plugin=false" in arguments
    assert captured["schema"]["additionalProperties"] is False
