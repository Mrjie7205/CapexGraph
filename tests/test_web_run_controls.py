from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"


def test_cockpit_exposes_guarded_run_deletion() -> None:
    app = (WEB / "App.tsx").read_text(encoding="utf-8")
    api = (WEB / "api.ts").read_text(encoding="utf-8")

    assert "deleteResearchRun" in app
    assert "deleteArmed" in app
    assert "确认移入回收区" in app
    assert "expected_updated_at: updatedAt" in api
    assert 'method: "DELETE"' in api


def test_cockpit_has_a_readable_and_redacted_stage_detail_panel() -> None:
    app = (WEB / "App.tsx").read_text(encoding="utf-8")
    panel = (WEB / "StageDetailPanel.tsx").read_text(encoding="utf-8")

    assert "selectedStageKey" in app
    assert "查看详情" in app
    assert "<StageDetailPanel" in app
    assert 'aria-live="polite"' in panel
    assert "SENSITIVE_KEY" in panel
    assert "结构化阶段输出" in panel
    assert "阶段尚未生成结构化输出" in panel
    assert "JSON.stringify" not in panel


def test_switching_runs_selects_the_latest_finished_stage() -> None:
    app = (WEB / "App.tsx").read_text(encoding="utf-8")

    assert "const currentStage = selected.pipeline.find" not in app
    assert "[...selected.pipeline]" in app
    assert ".reverse()" in app


def test_theme_graph_explains_and_shows_autonomous_evidence_bootstrap() -> None:
    app = (WEB / "App.tsx").read_text(encoding="utf-8")
    api = (WEB / "api.ts").read_text(encoding="utf-8")
    panel_path = WEB / "AutonomousEvidencePanel.tsx"

    assert panel_path.is_file()
    panel = panel_path.read_text(encoding="utf-8")
    assert "<AutonomousEvidencePanel" in app
    assert "nextPendingStep" in app
    assert "自动选公司并审核官方材料" in app
    assert "agent_reviewed" in api
    assert "evidence_bootstrap" in api
    assert "hasGroundedCompanyEvidence" in app
    assert 'item.kind === "filing" || item.kind === "company_disclosure"' in app
    assert "kind: string" in api
    assert "Agent 自动取证" in panel
    assert "公司假设" in panel
    assert "官方来源" in panel
    assert "独立审核" in panel
    assert "最高只支持中等置信度" in panel


def test_cockpit_only_requests_decision_after_decision_stage_and_has_favicon() -> None:
    app = (WEB / "App.tsx").read_text(encoding="utf-8")
    index = (ROOT / "apps" / "web" / "index.html").read_text(encoding="utf-8")

    assert 'const decisionStep = selected?.pipeline.find((step) => step.key === "decision")' in app
    assert 'decisionStep?.status !== "completed"' in app
    assert 'rel="icon"' in index
    assert "data:image/svg+xml" in index


def test_mobile_run_actions_cannot_force_horizontal_overflow() -> None:
    styles = (WEB / "styles.css").read_text(encoding="utf-8")

    assert ".run-action { grid-template-columns: 1fr; }" in styles
    assert ".run-action .bilingual-secondary { white-space: normal; }" in styles


def test_readiness_separates_human_and_agent_review_counts() -> None:
    readiness = (WEB / "ResearchReadiness.tsx").read_text(encoding="utf-8")

    assert "coverage?.agent_reviewed" in readiness
    assert "人工审核" in readiness
    assert "Agent 审核" in readiness


def test_strict_evidence_copy_includes_autonomous_agent_review() -> None:
    app = (WEB / "App.tsx").read_text(encoding="utf-8")

    assert "严格模式 · 自动补证并执行置信度门槛" in app
    assert "严格模式 · 先完成人工审核" not in app
