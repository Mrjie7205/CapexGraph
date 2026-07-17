import { FormEvent, useMemo, useState } from "react";
import { createRun, type ResearchRun, type RunMode } from "./api";

const DEMO_STEPS = [
  { label: "Define scope", agent: "Theme Analyst", state: "done" },
  { label: "Build player census", agent: "Universe Analyst", state: "done" },
  { label: "Map supply chain", agent: "Chain Mapper", state: "live" },
  { label: "Audit evidence", agent: "Evidence Auditor", state: "wait" },
  { label: "Issue verdict", agent: "Research Manager", state: "wait" },
];

const DEMO_EDGES = [
  { from: "石英坩埚", to: "单晶硅片", product: "High-purity consumable", confidence: "HIGH", sources: 3 },
  { from: "CMP材料", to: "晶圆制造", product: "Polishing slurry", confidence: "HIGH", sources: 4 },
  { from: "长晶设备", to: "硅片扩产", product: "Crystal growth system", confidence: "MED", sources: 2 },
];

const DEMO_CANDIDATES = [
  { symbol: "688019", name: "安集科技", verdict: "CANDIDATE", alpha: "+6.8%", stage: "启动" },
  { symbol: "688126", name: "沪硅产业", verdict: "WATCH", alpha: "+1.4%", stage: "震荡" },
  { symbol: "603688", name: "石英股份", verdict: "REVIEW", alpha: "—", stage: "待审" },
];

function App() {
  const [mode, setMode] = useState<RunMode>("theme");
  const [subject, setSubject] = useState("A股半导体硅片");
  const [created, setCreated] = useState<ResearchRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const steps = useMemo(() => {
    if (!created) return DEMO_STEPS;
    return created.pipeline.map((step) => ({
      label: step.label,
      agent: step.agent ?? "System",
      state: step.status === "completed" ? "done" : step.status === "running" ? "live" : "wait",
    }));
  }, [created]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!subject.trim()) return;
    setBusy(true);
    setError("");
    try {
      setCreated(await createRun(mode, subject.trim()));
    } catch {
      setError("API尚未启动。先运行 capexgraph serve；当前界面继续展示演示数据。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="CapexGraph home">
          <span className="brand-mark"><i>C</i><i>G</i></span>
          <span>CapexGraph<small>evidence-led research</small></span>
        </a>
        <nav>
          <a className="active" href="#runs">Runs</a>
          <a href="#graph">Graph</a>
          <a href="#radar">Radar</a>
          <a href="#ledger">Evidence</a>
        </nav>
        <div className="system-state"><span /> Local workspace · Pre-alpha</div>
      </header>

      <section className="hero" id="top">
        <div className="eyebrow">Supply-chain intelligence / 供应链研究</div>
        <div className="hero-grid">
          <div>
            <h1>Trace the spend.<br /><em>Prove the edge.</em></h1>
            <p className="hero-copy">
              从资本开支和市场锚点出发，把每一个投资判断还原成可审计的产业链关系、证据和证伪条件。
            </p>
          </div>

          <form className="run-composer" onSubmit={submit}>
            <div className="composer-head">
              <span>New research run</span><b>01</b>
            </div>
            <div className="mode-switch" role="group" aria-label="Research mode">
              <button type="button" className={mode === "theme" ? "selected" : ""} onClick={() => setMode("theme")}>
                <span>Theme Scan</span><small>主题 → 瓶颈</small>
              </button>
              <button type="button" className={mode === "anchor" ? "selected" : ""} onClick={() => setMode("anchor")}>
                <span>Anchor Scan</span><small>个股 → 生态</small>
              </button>
            </div>
            <label htmlFor="subject">{mode === "theme" ? "Investment theme" : "Ticker or company"}</label>
            <div className="subject-row">
              <input id="subject" value={subject} onChange={(event) => setSubject(event.target.value)} />
              <button className="launch" disabled={busy}>{busy ? "Creating…" : "Launch ↗"}</button>
            </div>
            {created && <p className="run-success">Run created · {created.id}</p>}
            {error && <p className="run-error">{error}</p>}
          </form>
        </div>
      </section>

      <section className="stats" aria-label="Research statistics">
        <article><span>Active run</span><strong>01</strong><small>{created?.subject ?? "A股半导体硅片"}</small></article>
        <article><span>Grounded edges</span><strong>38</strong><small>84% medium confidence+</small></article>
        <article><span>Evidence items</span><strong>126</strong><small>11 awaiting review</small></article>
        <article><span>Tracked alpha</span><strong className="positive">+7.2%</strong><small>vs theme benchmark</small></article>
      </section>

      <section className="workbench" id="runs">
        <article className="pipeline panel">
          <div className="panel-title"><span>Current run / Workflow</span><b>{created ? "CREATED" : "RUNNING"}</b></div>
          <div className="run-title">
            <div><small>{created?.mode === "anchor" ? "ANCHOR SCAN" : "THEME SCAN"}</small><h2>{created?.subject ?? "A股半导体硅片"}</h2></div>
            <span className="run-id">{created?.id ?? "CG-20260717-001"}</span>
          </div>
          <ol className="steps">
            {steps.map((step, index) => (
              <li className={step.state} key={`${step.label}-${index}`}>
                <span className="step-no">{String(index + 1).padStart(2, "0")}</span>
                <div><strong>{step.label}</strong><small>{step.agent}</small></div>
                <i>{step.state === "done" ? "✓" : step.state === "live" ? "working" : "queued"}</i>
              </li>
            ))}
          </ol>
        </article>

        <article className="graph-card panel" id="graph">
          <div className="panel-title"><span>Graph / Live topology</span><b>38 EDGES</b></div>
          <div className="graph-canvas">
            <svg viewBox="0 0 640 300" aria-label="Demo supply-chain graph">
              <defs><filter id="soft"><feGaussianBlur stdDeviation="1.8" /></filter></defs>
              <path className="edge high" d="M120 82 C230 82 218 148 330 148" />
              <path className="edge high" d="M120 220 C230 220 228 155 330 155" />
              <path className="edge med" d="M335 150 C438 150 430 82 535 82" />
              <path className="edge med" d="M335 160 C438 160 432 226 535 226" />
              <g className="node"><circle cx="90" cy="82" r="42" /><text x="90" y="78">材料</text><text className="sub" x="90" y="96">Materials</text></g>
              <g className="node"><circle cx="90" cy="220" r="42" /><text x="90" y="216">设备</text><text className="sub" x="90" y="234">Equipment</text></g>
              <g className="node core"><circle cx="335" cy="152" r="57" /><text x="335" y="148">硅片制造</text><text className="sub" x="335" y="169">Wafer</text></g>
              <g className="node"><circle cx="550" cy="82" r="42" /><text x="550" y="78">晶圆厂</text><text className="sub" x="550" y="96">Fabs</text></g>
              <g className="node"><circle cx="550" cy="226" r="42" /><text x="550" y="222">封装</text><text className="sub" x="550" y="240">Packaging</text></g>
            </svg>
            <div className="graph-key"><span><i className="key-high" /> grounded</span><span><i className="key-med" /> review</span></div>
          </div>
        </article>
      </section>

      <section className="lower-grid">
        <article className="ledger panel" id="ledger">
          <div className="panel-title"><span>Evidence ledger</span><button>Review all →</button></div>
          {DEMO_EDGES.map((edge) => (
            <div className="evidence-row" key={`${edge.from}-${edge.to}`}>
              <div className="confidence">{edge.confidence}</div>
              <div><strong>{edge.from} <i>→</i> {edge.to}</strong><small>{edge.product}</small></div>
              <span>{edge.sources} sources</span>
            </div>
          ))}
        </article>

        <article className="radar panel" id="radar">
          <div className="panel-title"><span>Opportunity radar</span><button>Open tracker →</button></div>
          <div className="radar-head"><span>Symbol</span><span>Verdict</span><span>Stage</span><span>Alpha</span></div>
          {DEMO_CANDIDATES.map((candidate) => (
            <div className="candidate-row" key={candidate.symbol}>
              <div><strong>{candidate.symbol}</strong><small>{candidate.name}</small></div>
              <span className={`verdict ${candidate.verdict.toLowerCase()}`}>{candidate.verdict}</span>
              <span>{candidate.stage}</span>
              <b>{candidate.alpha}</b>
            </div>
          ))}
        </article>
      </section>

      <footer>
        <span>CapexGraph / v0.1.0</span>
        <p>Research infrastructure, not investment advice.</p>
        <span>Evidence over narrative.</span>
      </footer>
    </main>
  );
}

export default App;
