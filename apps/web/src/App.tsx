import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createRun,
  executeRun,
  getDecision,
  getRun,
  listRuns,
  reviewEvidence,
  type DecisionArtifact,
  type Provider,
  type ResearchRun,
  type RunMode,
} from "./api";

const FINAL_STATUSES = new Set(["needs_review", "completed", "failed", "cancelled"]);

function GraphView({ run }: { run: ResearchRun | null }) {
  const geometry = useMemo(() => {
    if (!run || run.nodes.length === 0) return null;
    const width = 720;
    const height = 360;
    const centerX = width / 2;
    const centerY = height / 2;
    const anchorId = String(run.manifest.anchor_node_id ?? "");
    const positions = new Map<string, { x: number; y: number }>();
    const ordered = [...run.nodes].sort((a, b) => {
      if (a.id === anchorId) return -1;
      if (b.id === anchorId) return 1;
      return a.label.localeCompare(b.label, "zh-CN");
    });
    ordered.forEach((node, index) => {
      if (node.id === anchorId || (anchorId === "" && index === 0)) {
        positions.set(node.id, { x: centerX, y: centerY });
        return;
      }
      const orbitIndex = anchorId ? index - 1 : index;
      const orbitCount = Math.max(1, ordered.length - 1);
      const angle = (orbitIndex / orbitCount) * Math.PI * 2 - Math.PI / 2;
      positions.set(node.id, {
        x: centerX + Math.cos(angle) * 250,
        y: centerY + Math.sin(angle) * 125,
      });
    });
    return { width, height, positions, anchorId };
  }, [run]);

  if (!run || !geometry) {
    return <div className="graph-empty">Select or create a run to render its graph.</div>;
  }

  return (
    <svg viewBox={`0 0 ${geometry.width} ${geometry.height}`} aria-label="Research graph">
      {run.edges.map((edge) => {
        const source = geometry.positions.get(edge.source);
        const target = geometry.positions.get(edge.target);
        if (!source || !target) return null;
        return (
          <g key={edge.id}>
            <line
              className={`live-edge ${edge.confidence}`}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
            />
            <title>{`${edge.product} · ${edge.confidence} · ${edge.evidence_ids.length} sources`}</title>
          </g>
        );
      })}
      {run.nodes.map((node) => {
        const point = geometry.positions.get(node.id);
        if (!point) return null;
        const isCore = node.id === geometry.anchorId || (!geometry.anchorId && node === run.nodes[0]);
        return (
          <g className={`live-node ${isCore ? "core" : ""}`} key={node.id}>
            <circle cx={point.x} cy={point.y} r={isCore ? 48 : 38} />
            <text x={point.x} y={point.y - 2}>{node.label.slice(0, 8)}</text>
            <text className="sub" x={point.x} y={point.y + 15}>{node.ticker ?? node.layer?.slice(0, 12) ?? "segment"}</text>
          </g>
        );
      })}
    </svg>
  );
}

function App() {
  const [mode, setMode] = useState<RunMode>("theme");
  const [provider, setProvider] = useState<Provider>("fixture");
  const [subject, setSubject] = useState("A股半导体硅片");
  const [runs, setRuns] = useState<ResearchRun[]>([]);
  const [selected, setSelected] = useState<ResearchRun | null>(null);
  const [decision, setDecision] = useState<DecisionArtifact | null>(null);
  const [busy, setBusy] = useState(false);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState("");

  async function refreshRuns(selectId?: string) {
    const latest = await listRuns();
    setRuns(latest);
    if (selectId) {
      setSelected(latest.find((run) => run.id === selectId) ?? null);
    } else if (!selected && latest.length > 0) {
      setSelected(latest[0]);
    }
  }

  useEffect(() => {
    refreshRuns().catch(() => setError("API unavailable · run `capexgraph serve` first."));
  }, []);

  useEffect(() => {
    if (!selected || !polling) return;
    const timer = window.setInterval(async () => {
      try {
        const current = await getRun(selected.id);
        setSelected(current);
        if (FINAL_STATUSES.has(current.status)) {
          setPolling(false);
          await refreshRuns(current.id);
        }
      } catch (reason) {
        setPolling(false);
        setError(reason instanceof Error ? reason.message : "Polling failed");
      }
    }, 700);
    return () => window.clearInterval(timer);
  }, [polling, selected?.id]);

  useEffect(() => {
    setDecision(null);
    if (!selected || selected.status !== "needs_review") return;
    getDecision(selected.id).then(setDecision).catch(() => undefined);
  }, [selected?.id, selected?.status]);

  async function startRun(run: ResearchRun, resume = false) {
    await executeRun(run.id, provider, resume);
    setSelected({ ...run, status: "running" });
    setPolling(true);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!subject.trim()) return;
    setBusy(true);
    setError("");
    try {
      const created = await createRun(mode, subject.trim(), provider);
      setSelected(created);
      setRuns((items) => [created, ...items.filter((item) => item.id !== created.id)]);
      await startRun(created);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Run creation failed");
    } finally {
      setBusy(false);
    }
  }

  async function runGoldenDemo() {
    const demoMode = mode;
    const demoSubject = demoMode === "theme" ? "A股半导体硅片" : "兆易创新";
    const demoDate = demoMode === "theme" ? "2025-04-29" : "2026-04-23";
    setProvider("fixture");
    setSubject(demoSubject);
    setBusy(true);
    setError("");
    try {
      const created = await createRun(demoMode, demoSubject, "fixture", demoDate);
      setSelected(created);
      setRuns((items) => [created, ...items]);
      await executeRun(created.id, "fixture");
      setSelected({ ...created, status: "running" });
      setPolling(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Golden demo failed");
    } finally {
      setBusy(false);
    }
  }

  async function continueRun() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await startRun(selected, selected.status === "failed");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Execution failed");
    } finally {
      setBusy(false);
    }
  }

  async function review(evidenceId: string, approved: boolean) {
    if (!selected) return;
    try {
      const updated = await reviewEvidence(selected.id, evidenceId, approved);
      setSelected({
        ...selected,
        evidence: selected.evidence.map((item) => (item.id === updated.id ? updated : item)),
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Evidence review failed");
    }
  }

  const completedSteps = selected?.pipeline.filter((step) => step.status === "completed").length ?? 0;
  const hasPending = selected?.pipeline.some((step) => ["pending", "failed"].includes(step.status)) ?? false;
  const nodes = new Map(selected?.nodes.map((node) => [node.id, node]) ?? []);

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="CapexGraph home">
          <span className="brand-mark"><i>C</i><i>G</i></span>
          <span>CapexGraph<small>evidence-led research</small></span>
        </a>
        <nav><a className="active" href="#runs">Runs</a><a href="#graph">Graph</a><a href="#radar">Radar</a><a href="#ledger">Evidence</a></nav>
        <div className="system-state"><span /> Local research workspace</div>
      </header>

      <section className="hero" id="top">
        <div className="eyebrow">Supply-chain intelligence / 供应链研究</div>
        <div className="hero-grid">
          <div>
            <h1>Trace the spend.<br /><em>Prove the edge.</em></h1>
            <p className="hero-copy">从资本开支和市场锚点出发，把每一个研究判断还原成可审计的产业链关系、证据和证伪条件。</p>
          </div>
          <form className="run-composer" onSubmit={submit}>
            <div className="composer-head"><span>New research run</span><b>LIVE</b></div>
            <div className="mode-switch" role="group" aria-label="Research mode">
              <button type="button" className={mode === "theme" ? "selected" : ""} onClick={() => { setMode("theme"); setSubject("A股半导体硅片"); }}><span>Theme Scan</span><small>主题 → 瓶颈</small></button>
              <button type="button" className={mode === "anchor" ? "selected" : ""} onClick={() => { setMode("anchor"); setSubject("兆易创新"); }}><span>Anchor Scan</span><small>个股 → 邻居</small></button>
            </div>
            <div className="form-pair">
              <label>Provider<select value={provider} onChange={(event) => setProvider(event.target.value as Provider)}><option value="fixture">Fixture · no key</option><option value="openai">OpenAI</option></select></label>
              <label>Market<input value="CN" disabled /></label>
            </div>
            <label htmlFor="subject">{mode === "theme" ? "Investment theme" : "Ticker or company"}</label>
            <div className="subject-row"><input id="subject" value={subject} onChange={(event) => setSubject(event.target.value)} /><button className="launch" disabled={busy}>{busy ? "Starting…" : "Create & run ↗"}</button></div>
            <button className="demo-launch" type="button" disabled={busy} onClick={runGoldenDemo}>Run {mode} golden case · 无需 API Key</button>
            {error && <p className="run-error">{error}</p>}
          </form>
        </div>
      </section>

      <section className="stats" aria-label="Research statistics">
        <article><span>Persisted runs</span><strong>{runs.length || "—"}</strong><small>SQLite workspace</small></article>
        <article><span>Workflow progress</span><strong>{selected ? `${completedSteps}/${selected.pipeline.length}` : "—"}</strong><small>{selected?.status ?? "no run selected"}</small></article>
        <article><span>Grounded edges</span><strong>{selected?.edges.length ?? "—"}</strong><small>{selected ? `${selected.evidence.length} evidence items` : "select a run"}</small></article>
        <article><span>Research queue</span><strong>{selected?.candidates.length ?? "—"}</strong><small>candidates, not buy calls</small></article>
      </section>

      <section className="workbench" id="runs">
        <article className="pipeline panel">
          <div className="panel-title"><span>Runs / Workflow</span><b>{selected?.status ?? "EMPTY"}</b></div>
          <div className="run-strip">
            {runs.length === 0 && <p className="empty-state">No persisted runs yet.</p>}
            {runs.slice(0, 5).map((run) => <button key={run.id} className={selected?.id === run.id ? "active" : ""} onClick={() => setSelected(run)}><span>{run.mode}</span><strong>{run.subject}</strong><small>{run.status}</small></button>)}
          </div>
          <div className="run-title"><div><small>{selected?.mode?.toUpperCase() ?? "NO RUN"}</small><h2>{selected?.subject ?? "Create a research run"}</h2></div><span className="run-id">{selected?.id ?? "—"}</span></div>
          {selected && hasPending && <div className="run-action"><button disabled={busy || polling} onClick={continueRun}>{selected.status === "failed" ? "Resume failed run" : "Continue workflow"}</button></div>}
          <ol className="steps">
            {selected?.pipeline.map((step, index) => <li className={step.status === "completed" ? "done" : step.status === "running" ? "live" : step.status === "failed" ? "failed" : "wait"} key={step.key}><span className="step-no">{String(index + 1).padStart(2, "0")}</span><div><strong>{step.label}</strong><small>{step.message || step.agent}</small>{step.error && <small className="step-error">{step.error}</small>}</div><i>{step.status}</i></li>)}
          </ol>
        </article>

        <article className="graph-card panel" id="graph">
          <div className="panel-title"><span>Graph / Live topology</span><b>{selected?.edges.length ?? 0} EDGES</b></div>
          <div className="graph-canvas"><GraphView run={selected} /><div className="graph-key"><span><i className="key-high" /> grounded</span><span><i className="key-med" /> review</span></div></div>
          {decision && <div className="decision-note"><span>Research manager</span><p>{decision.summary}</p><small>{decision.disclaimer}</small></div>}
        </article>
      </section>

      <section className="lower-grid">
        <article className="ledger panel" id="ledger">
          <div className="panel-title"><span>Evidence ledger</span><b>{selected?.evidence.length ?? 0} ITEMS</b></div>
          {selected?.evidence.map((item) => <div className="source-row" key={item.id}><span className={`source-status ${item.status}`}>{item.status}</span><div><strong>{item.title}</strong><small>{item.publisher ?? item.id}</small></div>{item.status === "captured" ? <div className="review-actions"><button onClick={() => review(item.id, true)}>Approve</button><button onClick={() => review(item.id, false)}>Reject</button></div> : item.source_url ? <a href={item.source_url} target="_blank" rel="noreferrer">Source ↗</a> : <span />}</div>)}
          {selected && selected.evidence.length === 0 && <p className="empty-state">Execute through the graph stage to populate evidence.</p>}
          {!selected && <p className="empty-state">Select a run to inspect its source ledger.</p>}
        </article>

        <article className="radar panel" id="radar">
          <div className="panel-title"><span>Research queue</span><b>{selected?.candidates.length ?? 0} CANDIDATES</b></div>
          <div className="radar-head"><span>Symbol</span><span>Verdict</span><span>Confidence</span><span>Triggers</span></div>
          {selected?.candidates.map((candidate) => { const node = nodes.get(candidate.node_id); return <div className="candidate-row" key={candidate.node_id}><div><strong>{node?.ticker ?? "—"}</strong><small>{node?.label ?? candidate.node_id}</small></div><span className={`verdict ${candidate.verdict}`}>{candidate.verdict}</span><span>{candidate.confidence}</span><b>{candidate.triggers.length}</b></div>; })}
          {selected && selected.candidates.length === 0 && <p className="empty-state">No candidates until the scoring or compare step completes.</p>}
          {!selected && <p className="empty-state">Research candidates will appear here.</p>}
          {decision && <div className="next-actions"><span>Next actions</span>{decision.next_actions.map((item) => <p key={item}>→ {item}</p>)}</div>}
        </article>
      </section>

      <footer><span>CapexGraph / local</span><p>Research infrastructure, not investment advice.</p><span>Evidence over narrative.</span></footer>
    </main>
  );
}

export default App;
