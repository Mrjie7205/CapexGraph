# Autonomous Evidence Bootstrap Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make a non-fixture Theme Scan automatically propose seed companies, discover and capture official disclosures, independently review their exact text, and feed accepted evidence into the graph stage without asking the user to choose companies or approve documents.

**Architecture:** Add a focused `AutonomousEvidenceBootstrapService` that runs immediately before the Theme `graph` handler when the run has no grounded company evidence. It uses three schema-bound model calls (company discovery plan, official-source selection, independent evidence review), but keeps ticker identity, official-source authority, downloads, hashes, exact-quote checks, confidence caps, persistence, and failure behavior deterministic. Agent-reviewed captures get a distinct `agent_reviewed` status and complete review provenance; they never impersonate legacy/human `reviewed` evidence and can support at most medium-confidence relationships.

**Tech Stack:** Python 3.11, Pydantic, FastAPI, existing model-provider adapters, existing official-source providers and SSRF-safe collector, React 18, TypeScript, Vite, pytest.

---

## Scope and fixed decisions

- The first vertical slice covers non-fixture **Theme Scan** runs. Anchor Scan and Catalyst Scan remain unchanged.
- Starting the pending `graph` stage is the single user authorization. No company selection, source selection, or evidence approval click is required.
- The bootstrap uses at most four company seeds and four captured official sources per attempt.
- Candidate company names and tickers are discovery hypotheses until an official provider returns matching ticker metadata.
- Only regulator or deterministically classified issuer sources are eligible for automatic approval.
- An independent Evidence Review Agent must return exact quotations that deterministic code can find in the captured text.
- `reviewed` keeps its existing human/legacy meaning. The new `agent_reviewed` state is explicit in API, artifacts, UI, and reports.
- Human-reviewed or curated sources may retain high confidence. Agent-reviewed sources are capped at medium confidence. Unsupported/model-only claims remain low confidence.
- If no source passes deterministic and Agent review, the graph checkpoint fails visibly and can be retried; it does not silently continue with an empty graph.
- Fixture runs bypass the bootstrap and retain the no-key deterministic acceptance path.
- No database migration is needed because Evidence and bootstrap state are stored inside the versioned run JSON payload; all new fields are optional for legacy runs.

## Task 1: Add honest Agent-review contracts and confidence semantics

**Files:**
- Modify: `src/capexgraph/domain/models.py`
- Modify: `src/capexgraph/domain/__init__.py`
- Modify: `src/capexgraph/tools/evidence.py`
- Modify: `src/capexgraph/research/context.py`
- Modify: `src/capexgraph/research/theme.py`
- Modify: `src/capexgraph/research/anchor.py`
- Test: `tests/test_live_tools.py`
- Test: `tests/test_theme_research.py`

- [x] **Step 1: Write failing tests for distinct Agent review provenance**

```python
def test_agent_review_is_hash_bound_and_distinct_from_human_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "Enterprise AI", "US")
    collector = EvidenceCollector(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={"content-type": "text/html"},
                    text="<html><body>Official AI product disclosure</body></html>",
                    request=request,
                )
            )
        ),
        resolver=lambda *_args: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    evidence = collect_evidence_for_run(
        run.id,
        EvidenceSourceRequest(
            id="official-ai-product",
            title="Official AI product",
            kind=EvidenceKind.COMPANY_DISCLOSURE,
            url="https://issuer.example/ai",
        ),
        collector=collector,
    ).evidence
    reviewed = review_run_evidence(
        run.id,
        evidence.id,
        approved=True,
        review=EvidenceReviewRecord(
            actor=EvidenceReviewActor.AGENT,
            reviewer="Evidence Review Agent",
            provider="test-model",
            model="test-model-v1",
            source_hash=evidence.source_hash,
            prompt_hash="a" * 64,
            rationale="The official filing directly supports the product claim.",
            supporting_quotes=["Official AI product disclosure"],
        ),
    )
    assert reviewed.status == EvidenceStatus.AGENT_REVIEWED
    assert reviewed.review.actor == EvidenceReviewActor.AGENT
    assert reviewed.review.source_hash == reviewed.source_hash
```

- [x] **Step 2: Run the focused test and confirm it fails because the new enum/model/status do not exist**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_live_tools.py -q`

- [x] **Step 3: Add backward-compatible evidence review contracts**

Add `EvidenceStatus.AGENT_REVIEWED`, `EvidenceReviewActor`, and an optional `Evidence.review` record containing actor, reviewer, provider, model, transport, source hash, prompt hash, decision timestamp, rationale, exact supporting quotes, and warnings. Legacy `reviewed` evidence without a record remains valid as legacy human-reviewed evidence.

- [x] **Step 4: Make `review_run_evidence` set honest human or Agent status and reject stale review hashes**

The function must verify the local source hash for every approval, require Agent review provenance for `agent_reviewed`, and never let an Agent record produce the human `reviewed` state.

- [x] **Step 5: Write failing confidence-gate tests**

```python
def test_agent_reviewed_sources_cap_high_relationships_at_medium():
    confidence, grounded = apply_relationship_confidence_gate(
        requested_confidence="high",
        human_reviewed_sources=False,
        agent_reviewed_sources=True,
        curated=False,
        claim_label="relationship edge-company-demand",
    )
    assert confidence == "medium"
    assert grounded is True
```

- [x] **Step 6: Run the confidence test and confirm current code incorrectly treats Agent review as missing or high**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_theme_research.py -q`

- [x] **Step 7: Add deterministic human/Agent review checks and confidence cap**

Create helpers that verify unchanged human-reviewed and Agent-reviewed evidence separately. Theme and Anchor relationship gates must preserve high only for curated/human-reviewed sources, cap fully Agent-reviewed relationships at medium, and keep unsupported relationships low. Evidence coverage must count `agent_reviewed` separately and expose it as autonomous-ready without relabeling it human-reviewed.

- [x] **Step 8: Re-run both focused test files**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_live_tools.py tests/test_theme_research.py -q`

## Task 2: Build the autonomous evidence bootstrap service

**Files:**
- Create: `src/capexgraph/research/evidence_bootstrap.py`
- Modify: `src/capexgraph/research/__init__.py`
- Test: `tests/test_evidence_bootstrap.py`

- [x] **Step 1: Write a failing end-to-end service test with real persistence and guarded capture**

The test will use a schema-aware fake model, a fake official discovery provider returning ticker-bound `SourceSuggestion` records, and the real `SourceDiscoveryService` plus `EvidenceCollector` with `httpx.MockTransport`.

```python
def test_bootstrap_discovers_captures_agent_reviews_and_adds_verified_company(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_bootstrap_model: FakeBootstrapModel,
    fake_official_provider: FakeOfficialProvider,
    official_collector: EvidenceCollector,
):
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "Enterprise AI", "CN")
    result = AutonomousEvidenceBootstrapService(
        model=fake_bootstrap_model,
        source_service=SourceDiscoveryService(),
        provider_factory=lambda _name: fake_official_provider,
        collector=official_collector,
    ).run(run.id)

    assert result.status == "completed"
    assert result.accepted_sources == 1
    refreshed = load_run(run.id)
    assert refreshed.evidence[0].status == EvidenceStatus.AGENT_REVIEWED
    assert refreshed.evidence[0].review.supporting_quotes == [
        "Company A commercially deployed its enterprise AI platform."
    ]
    assert any(node.ticker == "000001.SZ" for node in refreshed.nodes)
```

- [x] **Step 2: Run the test and confirm it fails because the service and schemas do not exist**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_evidence_bootstrap.py -q`

- [x] **Step 3: Add typed Agent I/O and durable bootstrap state**

Define bounded schemas for:

- `CompanyDiscoveryPlan` with up to four discovery hypotheses;
- `OfficialSourceSelection` with up to four suggestion IDs;
- `EvidenceReviewBatch` with accept/reject/insufficient decisions and exact quotes;
- `EvidenceBootstrapState` with status, phase, attempt, timestamps, provider/model lineage, counts, accepted companies, reviews, warnings, and redacted errors.

Persist state after every phase under `run.manifest["evidence_bootstrap"]` and write `evidence-bootstrap.json` so restart/failure never loses where the autonomous attempt stopped.

- [x] **Step 4: Implement deterministic candidate and source validation**

- canonicalize the proposed ticker;
- require the candidate market to match the run;
- discover through `cninfo`, `sec`, or `kind` based on the run market;
- require returned official metadata to match the proposed ticker;
- use the official provider company name instead of trusting the model name;
- permit only regulator/issuer authority;
- deduplicate canonical URLs and source IDs;
- cap company and source counts before any download.

- [x] **Step 5: Implement selection, guarded capture, relevant-text construction, and independent review**

Use the existing source service and collector. Give the review call bounded exact text selected around company-specific evidence keywords, then verify every returned quote is a literal substring of that review text. A model `accept` with a missing/inexact quote becomes `insufficient`, not approved.

- [x] **Step 6: Bind accepted companies to accepted official sources**

Only companies with at least one accepted source become `SupplyChainNode` company records. Derive the node label and ticker from official provider metadata, retain the model-proposed industry layer as a hypothesis, and store supporting evidence IDs in node metadata.

- [x] **Step 7: Add failure/idempotency tests**

Cover:

- no valid official discovery results;
- capture failure persisted without leaking credentials;
- Agent acceptance with a fabricated quote;
- Agent rejection;
- ticker mismatch between model and provider;
- a second call returning the completed durable result without duplicate sources or nodes;
- source/model limits of four.

- [x] **Step 8: Run the complete bootstrap test file and confirm it passes**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_evidence_bootstrap.py -q`

## Task 3: Run bootstrap automatically before the Theme graph stage

**Files:**
- Modify: `src/capexgraph/research/theme.py`
- Modify: `src/capexgraph/research/context.py`
- Modify: `src/capexgraph/api/app.py`
- Test: `tests/test_theme_research.py`
- Test: `tests/test_api.py`

- [x] **Step 1: Write a failing graph-integration test**

```python
def test_live_theme_graph_bootstraps_evidence_before_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    autonomous_theme_executor: WorkflowExecutor,
):
    monkeypatch.setenv("CAPEXGRAPH_RUNS_DIR", str(tmp_path))
    run = create_run(RunMode.THEME, "Enterprise AI", "CN")
    executor = autonomous_theme_executor
    paused = executor.execute(run.id, until="census")
    completed = executor.execute(paused.id, until="graph")
    assert completed.manifest["evidence_bootstrap"]["status"] == "completed"
    assert completed.pipeline[2].status == StepStatus.COMPLETED
    assert completed.evidence[0].status == EvidenceStatus.AGENT_REVIEWED
```

- [x] **Step 2: Run the test and confirm the graph currently starts without bootstrap**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_theme_research.py -q`

- [x] **Step 3: Invoke bootstrap at the start of non-fixture Theme graph execution**

Skip when the provider policy is curated, when an earlier completed bootstrap is still hash-valid, or when the run already has unchanged human/Agent-reviewed company evidence. Otherwise run the service with the same locked provider/model. Reload and synchronize the run before graph generation so captured evidence and verified company nodes are in the prompt and persisted state.

- [x] **Step 4: Make zero accepted sources a durable graph failure**

Raise a safe retryable `EvidenceBootstrapError`. The normal workflow checkpoint must show a concise message while detailed phase/errors remain in the bootstrap artifact. Do not continue to an evidence-free graph.

- [x] **Step 5: Make research context prioritize reviewed exact quotes**

For Agent-reviewed evidence, include the review record's exact supporting quotes before generic extracted text so long annual reports do not lose the relevant passage to the existing 6000-character per-source limit.

- [x] **Step 6: Expose the bootstrap artifact and state through the existing run API**

Add `evidence-bootstrap.json` to the artifact allowlist. No endpoint may expose provider credentials, raw authentication, or unrestricted remote content.

- [x] **Step 7: Run focused Theme and API tests**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_theme_research.py tests/test_api.py -q`

## Task 4: Add a one-action autonomous evidence experience to the Cockpit

**Files:**
- Create: `apps/web/src/AutonomousEvidencePanel.tsx`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/UiText.tsx`
- Modify: `apps/web/src/styles.css`
- Test: `tests/test_web_autonomous_evidence.py`

- [x] **Step 1: Write a failing source-contract UI test**

```python
def test_graph_action_explains_autonomous_evidence_bootstrap():
    app = (WEB / "App.tsx").read_text(encoding="utf-8")
    panel = (WEB / "AutonomousEvidencePanel.tsx").read_text(encoding="utf-8")
    assert "Agent 自动补证并构建关系图" in app
    assert "agent_reviewed" in panel
    assert "无需选择公司或报告" in panel
    assert "人工已审核" not in panel
```

- [x] **Step 2: Run the UI contract test and confirm it fails for the missing panel**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_web_autonomous_evidence.py -q`

- [x] **Step 3: Extend typed API contracts**

Add `agent_reviewed` to Evidence status, typed optional Agent review provenance, and typed bootstrap state under the run manifest.

- [x] **Step 4: Add the autonomous evidence panel**

In the existing editorial paper/wine visual system, show:

- standby: the graph action will choose companies and reports automatically;
- running phases: proposing companies, discovering official sources, capturing, reviewing;
- completed: accepted companies/sources, rejected or insufficient items, provider/model lineage;
- failed: safe reason and instruction to retry the graph stage;
- confidence note: Agent-reviewed material is not human-reviewed and is capped at medium confidence.

The panel must remain compact, readable on mobile, accessible via `aria-live`, and must not display secrets or raw prompt text.

- [x] **Step 5: Change the pending graph action label**

When the next Theme step is `graph`, label the existing one-action control `Agent 自动补证并构建关系图`; clicking it uses the existing background stage execution and polling path. No additional approval control is introduced.

- [x] **Step 6: Update evidence ledger labels**

Display `agent_reviewed` as `Agent 已审核`, keep `reviewed` as `人工已审核`, and show reviewer/model plus warnings without implying that Agent review is human approval.

- [x] **Step 7: Run UI tests and production build**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_web_autonomous_evidence.py tests/test_web_run_controls.py tests/test_web_typography.py -q`

Run: `npm run build` from `apps/web`.

## Task 5: Document the changed trust contract and verify end to end

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/DECISIONS.md`
- Modify: `docs/THEME_SCAN.md`
- Modify: `docs/CURRENT_STATUS.md`
- Modify: `CHANGELOG.md`

- [x] **Step 1: Record the explicit product decision**

Document that the user authorized a fully autonomous Theme evidence bootstrap. Keep human and Agent review distinct, require exact hash-bound quotes and deterministic source/ticker validation, cap Agent-reviewed claims at medium confidence, and preserve manual human review as an optional stronger path rather than a required interaction.

- [x] **Step 2: Update Theme usage and handoff**

Explain that the graph action now performs company discovery, official-source selection, capture, Agent review, and graph mapping as one background operation. State the current Theme-only scope and honest failure/retry behavior.

- [x] **Step 3: Run formatting and focused regression checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest tests/test_evidence_bootstrap.py tests/test_theme_research.py tests/test_api.py tests/test_live_tools.py -q
Push-Location apps\web
npm run build
Pop-Location
```

- [x] **Step 4: Run the complete required gate**

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
Push-Location apps\web
npm run build
Pop-Location
```

- [x] **Step 5: Use a real browser against the local services**

Verify desktop and 390px mobile behavior for standby/running/completed/failed states, the graph-stage action label, Agent-review ledger labels, responsive layout, polling, and absence of new console errors. Use a temporary test run or deterministic injected case; do not advance or overwrite the user's retained research runs during UI acceptance.

- [x] **Step 6: Remove only QA artifacts created during implementation and preserve prior user changes**
