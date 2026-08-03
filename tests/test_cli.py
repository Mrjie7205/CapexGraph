from typer.testing import CliRunner

from capexgraph.cli import app

runner = CliRunner()


def test_model_provider_cli_lists_three_channels_without_secrets(monkeypatch) -> None:
    proxy_key = "local-proxy-secret"
    monkeypatch.setenv("CAPEXGRAPH_CODEX_PROXY_KEY", proxy_key)
    monkeypatch.setenv("CAPEXGRAPH_CODEX_MODEL", "codex-model")

    result = runner.invoke(app, ["model", "providers"])

    assert result.exit_code == 0
    assert "fixture" in result.output
    assert "codex_subscription" in result.output
    assert "openai" in result.output
    assert proxy_key not in result.output


def test_theme_help_exposes_all_model_channels() -> None:
    result = runner.invoke(app, ["theme", "--help"])

    assert result.exit_code == 0
    assert "codex_subscription" in result.output


def test_create_and_execute_returns_nonzero_when_provider_setup_fails(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        ["theme", "unsupported fixture subject", "--provider", "fixture", "--execute"],
    )

    assert result.exit_code == 1
    assert "failed" in result.output
