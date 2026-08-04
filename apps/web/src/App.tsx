import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createRun,
  captureTrackingSnapshot,
  decideDisclosureFactCandidate,
  deleteRun as deleteResearchRun,
  evidenceTextUrl,
  executeRun,
  getDecision,
  getRun,
  isProvider,
  listDisclosureFactCandidates,
  listModelProviders,
  listRuns,
  listTracking,
  previewReviewedDisclosureFacts,
  reviewEvidence,
  setTrackingStage,
  trackCandidate,
  type DecisionArtifact,
  type DisclosureFactCandidate,
  type EvidenceMode,
  type ModelProviderStatus,
  type Provider,
  type ResearchRun,
  type RunMode,
  type Scorecard,
  type TrackingStage,
} from "./api";
import { StageDetailPanel } from "./StageDetailPanel";
import { AutonomousEvidencePanel } from "./AutonomousEvidencePanel";
import { ResearchReadiness } from "./ResearchReadiness";
import { SourceQueue } from "./SourceQueue";
import { LiveDesk } from "./LiveDesk";
import { MainlineDesk } from "./MainlineDesk";
import { ConnectionCenter } from "./ConnectionCenter";
import { subscribeSync } from "./sync";
import {
  BilingualText,
  LocalizedValue,
  humanizeUiValue,
  translateUiValue,
} from "./UiText";

const FINAL_STATUSES = new Set(["needs_review", "completed", "failed", "cancelled"]);
const MARKET_OPTIONS = [
  { value: "CN", label: "中国 A 股 · CN" },
  { value: "US", label: "美国 · US" },
  { value: "KR", label: "韩国 · KR" },
] as const;

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
    return (
      <div className="graph-empty">
        <BilingualText
          zh="请选择或创建一个研究任务以生成关系图。"
          en="Select or create a run to render its graph."
          align="center"
        />
      </div>
    );
  }

  return (
    <svg viewBox={`0 0 ${geometry.width} ${geometry.height}`} aria-label="研究关系图">
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
            <title>{`${edge.product} · ${translateUiValue(edge.confidence)} · ${edge.evidence_ids.length} 条来源`}</title>
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
            <text className="sub" x={point.x} y={point.y + 15}>{node.ticker ?? node.layer?.slice(0, 12) ?? "产业环节"}</text>
          </g>
        );
      })}
    </svg>
  );
}

function App() {
  const [mode, setMode] = useState<RunMode>("theme");
  const [provider, setProvider] = useState<Provider>("fixture");
  const [evidenceMode, setEvidenceMode] = useState<EvidenceMode>("partial");
  const [market, setMarket] = useState("CN");
  const [subject, setSubject] = useState("A股半导体硅片");
  const [runs, setRuns] = useState<ResearchRun[]>([]);
  const [modelProviders, setModelProviders] = useState<ModelProviderStatus[]>([]);
  const [selected, setSelected] = useState<ResearchRun | null>(null);
  const [decision, setDecision] = useState<DecisionArtifact | null>(null);
  const [factCandidates, setFactCandidates] = useState<DisclosureFactCandidate[]>([]);
  const [tracking, setTracking] = useState<Scorecard[]>([]);
  const [busy, setBusy] = useState(false);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState("");
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [selectedStageKey, setSelectedStageKey] = useState<string | null>(null);
  const [deleteArmed, setDeleteArmed] = useState(false);
  const [runNotice, setRunNotice] = useState("");
  const decisionStep = selected?.pipeline.find((step) => step.key === "decision");

  async function refreshModelProviders() {
    const providers = await listModelProviders(true);
    setModelProviders(providers);
  }

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
    refreshRuns().catch(() => setError("后端服务暂不可用，请先启动 CapexGraph 服务。"));
    listTracking().then(setTracking).catch(() => undefined);
    refreshModelProviders().catch(() => undefined);
  }, []);

  useEffect(
    () => subscribeSync(
      "connections",
      () => refreshModelProviders().catch(() => undefined),
      { remoteOnly: true },
    ),
    [],
  );

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
        setError(reason instanceof Error ? reason.message : "状态轮询失败");
      }
    }, 700);
    return () => window.clearInterval(timer);
  }, [polling, selected?.id]);

  useEffect(() => {
    setDecision(null);
    if (
      !selected
      || selected.status !== "needs_review"
      || decisionStep?.status !== "completed"
    ) return;
    getDecision(selected.id).then(setDecision).catch(() => undefined);
  }, [selected?.id, selected?.status, decisionStep?.status]);

  useEffect(() => {
    if (!selected) {
      setFactCandidates([]);
      return;
    }
    listDisclosureFactCandidates(selected.id).then(setFactCandidates).catch(() => setFactCandidates([]));
  }, [selected?.id]);

  useEffect(() => {
    setDeleteArmed(false);
    if (!selected) {
      setSelectedStageKey(null);
      return;
    }
    setSelectedStageKey(
      [...selected.pipeline]
        .reverse()
        .find((step) => ["completed", "failed", "blocked"].includes(step.status))?.key ?? null,
    );
  }, [selected?.id, selected?.updated_at]);

  async function startRun(run: ResearchRun, resume = false, until?: string) {
    const persistedProvider = run.manifest.model_provider;
    if (persistedProvider && !isProvider(persistedProvider)) {
      throw new Error(`研究记录中的模型通道暂不受支持：${String(persistedProvider)}`);
    }
    const runProvider = isProvider(persistedProvider) ? persistedProvider : provider;
    await executeRun(run.id, runProvider, resume, { evidenceMode, until });
    setSelected({ ...run, status: "running" });
    setPolling(true);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!subject.trim()) return;
    setBusy(true);
    setError("");
    try {
      const created = await createRun(
        mode,
        subject.trim(),
        provider,
        market.trim().toUpperCase(),
        evidenceMode,
      );
      setSelected(created);
      setRuns((items) => [created, ...items.filter((item) => item.id !== created.id)]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "研究任务创建失败");
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
      const created = await createRun(
        demoMode,
        demoSubject,
        "fixture",
        "CN",
        "partial",
        demoDate,
      );
      setSelected(created);
      setRuns((items) => [created, ...items]);
      await executeRun(created.id, "fixture", false, { evidenceMode: "partial" });
      setSelected({ ...created, status: "running" });
      setPolling(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "黄金样例运行失败");
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
      setError(reason instanceof Error ? reason.message : "研究执行失败");
    } finally {
      setBusy(false);
    }
  }

  async function runNextStage() {
    if (!selected) return;
    const nextStep = selected.pipeline.find((step) => ["pending", "failed"].includes(step.status));
    if (!nextStep) return;
    setBusy(true);
    setError("");
    try {
      await startRun(selected, selected.status === "failed", nextStep.key);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "阶段执行失败");
    } finally {
      setBusy(false);
    }
  }

  async function deleteSelectedRun() {
    if (!selected) return;
    setBusy(true);
    setError("");
    setRunNotice("");
    try {
      const result = await deleteResearchRun(selected.id, selected.updated_at);
      const latest = await listRuns();
      setRuns(latest);
      setSelected(latest[0] ?? null);
      setDeleteArmed(false);
      setRunNotice(`空任务已移入本地回收区：${result.archived_path}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务删除失败");
      setDeleteArmed(false);
    } finally {
      setBusy(false);
    }
  }

  async function review(evidenceId: string, approved: boolean) {
    if (!selected) return;
    try {
      const updated = await reviewEvidence(selected.id, evidenceId, approved);
      const current = await getRun(selected.id);
      setSelected({
        ...current,
        evidence: current.evidence.map((item) => (item.id === updated.id ? updated : item)),
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "证据审核失败");
    }
  }

  async function previewFacts(evidenceId: string) {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await previewReviewedDisclosureFacts(selected.id, evidenceId);
      setFactCandidates(await listDisclosureFactCandidates(selected.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "财务事实候选提取失败");
    } finally {
      setBusy(false);
    }
  }

  async function decideFactCandidate(candidateId: string, accepted: boolean) {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await decideDisclosureFactCandidate(selected.id, candidateId, accepted);
      setFactCandidates(await listDisclosureFactCandidates(selected.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "财务事实候选处理失败");
    } finally {
      setBusy(false);
    }
  }

  async function addToTracking(nodeId: string) {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await trackCandidate(selected.id, nodeId);
      setTracking(await listTracking());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "加入跟踪失败");
    } finally {
      setBusy(false);
    }
  }

  async function updateSnapshot(trackedId: string) {
    setBusy(true);
    setError("");
    try {
      await captureTrackingSnapshot(trackedId);
      setTracking(await listTracking());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "价格快照更新失败");
    } finally {
      setBusy(false);
    }
  }

  async function moveStage(trackedId: string, stage: TrackingStage) {
    try {
      await setTrackingStage(trackedId, stage);
      setTracking(await listTracking());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "跟踪阶段更新失败");
    }
  }

  const completedSteps = selected?.pipeline.filter((step) => step.status === "completed").length ?? 0;
  const hasPending = selected?.pipeline.some((step) => ["pending", "failed"].includes(step.status)) ?? false;
  const nextPendingStep = selected?.pipeline.find((step) => ["pending", "failed"].includes(step.status));
  const hasGroundedCompanyEvidence = selected?.evidence.some(
    (item) => (item.kind === "filing" || item.kind === "company_disclosure")
      && (item.status === "reviewed" || item.status === "agent_reviewed"),
  ) ?? false;
  const willBootstrapEvidence = Boolean(
    selected?.mode === "theme"
      && nextPendingStep?.key === "graph"
      && selected.manifest.model_provider !== "fixture"
      && !hasGroundedCompanyEvidence,
  );
  const hasAgentOutputs = Boolean(
    selected?.manifest.agent_outputs
      && Object.keys(selected.manifest.agent_outputs).length > 0,
  );
  const canDeleteSelected = Boolean(
    selected
      && selected.status === "created"
      && selected.pipeline.every((step) => step.status === "pending" && !step.attempts)
      && selected.nodes.length === 0
      && selected.edges.length === 0
      && selected.evidence.length === 0
      && selected.candidates.length === 0
      && !hasAgentOutputs,
  );
  const nodes = new Map(selected?.nodes.map((node) => [node.id, node]) ?? []);
  const trackedNodeIds = new Set(
    tracking.filter((card) => card.tracked.run_id === selected?.id).map((card) => card.tracked.node_id),
  );
  const selectedProviderStatus = modelProviders.find((item) => item.name === provider);
  const providerReadinessEnglish = selectedProviderStatus
    ? selectedProviderStatus.configured
      ? `${humanizeUiValue(selectedProviderStatus.reachability)} · ${humanizeUiValue(selectedProviderStatus.billing_mode)}`
      : `not configured · missing ${selectedProviderStatus.missing.join(", ") || "valid settings"}`
    : "status unavailable";
  const providerReadinessChinese = selectedProviderStatus
    ? selectedProviderStatus.configured
      ? `${translateUiValue(selectedProviderStatus.reachability)} · ${translateUiValue(selectedProviderStatus.billing_mode)}`
      : `尚未配置 · 缺少 ${selectedProviderStatus.missing.join("、") || "有效设置"}`
    : "状态暂不可用";

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="CapexGraph 首页">
          <span className="brand-mark"><i>C</i><i>G</i></span>
          <span>
            CapexGraph
            <BilingualText zh="可审计投资研究" en="Evidence-led research" compact />
          </span>
        </a>
        <nav aria-label="主导航">
          <a className="active" href="#live"><BilingualText zh="实时台" en="Live Desk" compact align="center" /></a>
          <a href="#mainline"><BilingualText zh="主线" en="Mainline" compact align="center" /></a>
          <a href="#runs"><BilingualText zh="研究" en="Runs" compact align="center" /></a>
          <a href="#sources"><BilingualText zh="来源" en="Sources" compact align="center" /></a>
          <a href="#graph"><BilingualText zh="关系图" en="Graph" compact align="center" /></a>
          <a href="#radar"><BilingualText zh="候选" en="Candidates" compact align="center" /></a>
        </nav>
        <div className="topbar-tools">
          <div className="system-state"><span /><BilingualText zh="本机工作区" en="Local workspace" compact /></div>
          <button className="connection-trigger" type="button" onClick={() => setConnectionsOpen(true)}>
            <i /><BilingualText zh="连接" en="Connections" compact />
          </button>
        </div>
      </header>

      <section className="hero" id="top">
        <div className="eyebrow"><BilingualText zh="供应链情报" en="Supply-chain intelligence" /></div>
        <div className="hero-grid">
          <div>
            <h1>
              追踪资本开支。<br /><em>验证研究优势。</em>
              <small>Trace the spend. Prove the edge.</small>
            </h1>
            <p className="hero-copy">从资本开支和市场锚点出发，把每一个研究判断还原成可审计的产业链关系、证据和证伪条件。</p>
          </div>
          <form className="run-composer" onSubmit={submit}>
            <div className="composer-head">
              <BilingualText zh="新建研究任务" en="New research run" />
              <BilingualText zh="在线" en="Live" compact align="right" />
            </div>
            <div className="mode-switch" role="group" aria-label="研究模式">
              <button type="button" className={mode === "theme" ? "selected" : ""} onClick={() => { setMode("theme"); setSubject("A股半导体硅片"); }}><span>主题扫描</span><small>Theme Scan · 主题 → 瓶颈</small></button>
              <button type="button" className={mode === "anchor" ? "selected" : ""} onClick={() => { setMode("anchor"); setSubject("兆易创新"); }}><span>锚点扫描</span><small>Anchor Scan · 个股 → 邻居</small></button>
            </div>
            <div className="composer-options">
              <label><BilingualText zh="模型通道" en="Model channel" compact /><select value={provider} onChange={(event) => { if (isProvider(event.target.value)) setProvider(event.target.value); }}><option value="fixture">冻结样例 · Fixture（无需模型）</option><option value="codex_subscription">Codex 订阅 · 本机调用</option><option value="openai">OpenAI API · 按量计费</option></select></label>
              <label><BilingualText zh="证据策略" en="Evidence policy" compact /><select value={evidenceMode} onChange={(event) => setEvidenceMode(event.target.value as EvidenceMode)}><option value="partial">部分模式 · 允许带缺口继续</option><option value="strict">严格模式 · 自动补证并执行置信度门槛</option></select></label>
              <label>
                <BilingualText zh="市场" en="Market" compact />
                <select value={market} onChange={(event) => setMarket(event.target.value)}>
                  {MARKET_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
            </div>
            <label htmlFor="subject"><BilingualText zh={mode === "theme" ? "投资主题" : "股票代码或公司"} en={mode === "theme" ? "Investment theme" : "Ticker or company"} compact /></label>
            <div className="subject-row">
              <input id="subject" value={subject} onChange={(event) => setSubject(event.target.value)} />
              <button className="launch" disabled={busy}>
                <BilingualText
                  zh={busy ? "正在创建…" : "创建工作区 ↗"}
                  en={busy ? "Creating…" : "Create workspace"}
                  compact
                  align="right"
                />
              </button>
            </div>
            <p className="composer-note">
              通道状态：
              <BilingualText zh={providerReadinessChinese} en={providerReadinessEnglish} compact />
              。冻结样例无需配置；Codex 可直接使用本机 ChatGPT 订阅；OpenAI API 使用独立 API Key 计费。
              <button type="button" className="inline-connect" onClick={() => setConnectionsOpen(true)}>管理连接 ↗</button>
            </p>
            <button className="demo-launch" type="button" disabled={busy} onClick={runGoldenDemo}>
              <BilingualText
                zh={`运行${mode === "theme" ? "主题" : "锚点"}黄金样例 · 无需 API Key`}
                en={`Run ${mode} golden case`}
                compact
                align="center"
              />
            </button>
            {error && <p className="run-error"><strong>操作未完成</strong><small>{error}</small></p>}
          </form>
        </div>
      </section>

      <section className="stats" aria-label="研究统计">
        <article><BilingualText zh="持久化研究" en="Persisted runs" /><strong>{runs.length || "—"}</strong><small>本机 SQLite 工作区</small></article>
        <article><BilingualText zh="工作流进度" en="Workflow progress" /><strong>{selected ? `${completedSteps}/${selected.pipeline.length}` : "—"}</strong><small>{selected ? `${translateUiValue(selected.status)} · ${humanizeUiValue(selected.status)}` : "尚未选择研究"}</small></article>
        <article><BilingualText zh="有据关系" en="Grounded edges" /><strong>{selected?.edges.length ?? "—"}</strong><small>{selected ? `${selected.evidence.length} 条证据材料` : "请选择研究"}</small></article>
        <article><BilingualText zh="研究候选" en="Research queue" /><strong>{selected?.candidates.length ?? "—"}</strong><small>仅为候选，不是买入建议</small></article>
      </section>

      <LiveDesk onOpenConnections={() => setConnectionsOpen(true)} />

      <MainlineDesk onError={setError} />

      <section className="workbench" id="runs">
        <article className="pipeline panel">
          <div className="panel-title">
            <BilingualText zh="研究任务 / 工作流" en="Runs / Workflow" />
            <b><LocalizedValue value={selected?.status} fallbackZh="暂无任务" fallbackEn="empty" /></b>
          </div>
          <div className="run-strip">
            {runs.length === 0 && <p className="empty-state">还没有持久化研究任务。<small>No persisted runs yet.</small></p>}
            {runs.slice(0, 5).map((run) => (
              <button key={run.id} className={selected?.id === run.id ? "active" : ""} onClick={() => { setSelected(run); setRunNotice(""); }}>
                <span>{translateUiValue(run.mode)}<small>{humanizeUiValue(run.mode)}</small></span>
                <strong>{run.subject}</strong>
                <small>{translateUiValue(run.status)} · {humanizeUiValue(run.status)}</small>
              </button>
            ))}
          </div>
          <div className="run-title">
            <div>
              <small>{selected ? `${translateUiValue(selected.mode)} · ${selected.mode.toUpperCase()}` : "暂无研究 · NO RUN"}</small>
              <h2>{selected?.subject ?? "请先创建研究任务"}</h2>
            </div>
            <div className="run-title-tools">
              <span className="run-id">{selected?.id ?? "—"}</span>
              {selected && (
                <button
                  className="delete-run-trigger"
                  type="button"
                  disabled={!canDeleteSelected || busy || polling}
                  title={canDeleteSelected ? "删除未运行、无研究产物的空任务" : "已有阶段、证据、关系或跟踪内容的任务受到保护"}
                  onClick={() => setDeleteArmed(true)}
                >
                  删除空任务
                </button>
              )}
            </div>
          </div>
          {runNotice && <p className="run-notice">{runNotice}</p>}
          {selected && !canDeleteSelected && (
            <p className="run-protection-note">该任务已经包含研究内容或状态记录，不能直接删除；这样可以保留检查点、证据和后续跟踪。</p>
          )}
          {selected && deleteArmed && canDeleteSelected && (
            <div className="delete-confirmation" role="alert">
              <div>
                <strong>确认删除“{selected.subject}”？</strong>
                <small>只会移除这个尚未运行的空任务，并将文件移入本机 runs/.trash 回收区。</small>
              </div>
              <button type="button" className="secondary" onClick={() => setDeleteArmed(false)}>取消</button>
              <button type="button" disabled={busy} onClick={deleteSelectedRun}>确认移入回收区</button>
            </div>
          )}
          {selected && hasPending && <div className="run-action">
            {selected.status === "failed" ? (
              <button disabled={busy || polling} onClick={continueRun}>
                <BilingualText zh="从失败检查点重试" en="Retry from failed checkpoint" compact align="center" />
              </button>
            ) : (
              <>
                <button disabled={busy || polling} onClick={runNextStage}>
                  <BilingualText
                    zh={willBootstrapEvidence ? "自动选公司并审核官方材料" : "运行下一阶段 · 检查点后暂停"}
                    en={willBootstrapEvidence ? "Auto-source evidence, then map graph" : "Run next stage"}
                    compact
                    align="center"
                  />
                </button>
                <button className="secondary" disabled={busy || polling} onClick={continueRun}>
                  <BilingualText zh="运行全部剩余阶段" en="Run all remaining stages" compact align="center" />
                </button>
              </>
            )}
            <small>{willBootstrapEvidence
              ? "这一次会自动提出种子公司、抓取监管/公司官方披露并独立审核；没有材料通过时图谱会停止。"
              : selected.status === "created"
                ? "先采集和审核材料，再执行研究；部分模式允许带缺口继续。"
                : "恢复执行时，已经完成的检查点会被保留。"}</small>
          </div>}
          <ol className="steps">
            {selected?.pipeline.map((step, index) => (
              <li className={step.status === "completed" ? "done" : step.status === "running" ? "live" : step.status === "failed" ? "failed" : "wait"} key={step.key}>
                <span className="step-no">{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <BilingualText as="strong" zh={translateUiValue(step.label)} en={step.label} />
                  <BilingualText
                    zh={translateUiValue(step.message || step.agent || "")}
                    en={step.message || step.agent}
                    compact
                  />
                  {step.error && <small className="step-error">{step.error}</small>}
                </div>
                <div className="step-tools">
                  <i><LocalizedValue value={step.status} /></i>
                  {["completed", "failed", "blocked"].includes(step.status) && (
                    <button
                      type="button"
                      aria-expanded={selectedStageKey === step.key}
                      onClick={() => setSelectedStageKey(selectedStageKey === step.key ? null : step.key)}
                    >
                      {selectedStageKey === step.key ? "收起详情" : "查看详情"}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </article>

        <article className="graph-card panel" id="graph">
          <div className="panel-title"><BilingualText zh="关系图 / 实时拓扑" en="Graph / Live topology" /><b>{selected?.edges.length ?? 0} 条关系<small>Edges</small></b></div>
          <div className="graph-canvas"><GraphView run={selected} /><div className="graph-key"><span><i className="key-high" /> 有证据<small>grounded</small></span><span><i className="key-med" /> 待审核<small>review</small></span></div></div>
          {decision && <div className="decision-note"><BilingualText zh="研究经理" en="Research manager" compact /><p>{decision.summary}</p><small>{decision.disclaimer}</small></div>}
        </article>
        {selected && (
          <AutonomousEvidencePanel run={selected} upcoming={willBootstrapEvidence} />
        )}
        {selected && <StageDetailPanel run={selected} stageKey={selectedStageKey} />}
      </section>

      <SourceQueue
        run={selected}
        onRunUpdated={setSelected}
        onError={setError}
      />

      <ResearchReadiness
        run={selected}
        onRunUpdated={setSelected}
        onError={setError}
      />

      <section className="lower-grid">
        <article className="ledger panel" id="ledger">
          <div className="panel-title"><BilingualText zh="证据台账" en="Evidence ledger" /><b>{selected?.evidence.length ?? 0} 条<small>Items</small></b></div>
          {selected?.evidence.map((item) => (
            <div className="source-row" key={item.id}>
              <span className={`source-status ${item.status}`}>{translateUiValue(item.status)}<small>{humanizeUiValue(item.status)}</small></span>
              <div>
                <strong>{item.title}</strong>
                <small>{item.publisher ?? item.id}</small>
                {item.review?.actor === "agent" && (
                  <small className="agent-review-note">
                    Evidence Review Agent · {item.review.supporting_quotes.length} 条原文引用 · {item.review.model ?? "模型未记录"}
                  </small>
                )}
              </div>
              <div className="review-actions">
                {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">查看来源<small>Source ↗</small></a>}
                {item.local_path?.startsWith("sources/") && <a href={evidenceTextUrl(selected.id, item.id)} target="_blank" rel="noreferrer">查看正文<small>Text ↗</small></a>}
                {item.status === "captured" && <>
                  <button onClick={() => review(item.id, true)}>批准<small>Approve</small></button>
                  <button onClick={() => review(item.id, false)}>拒绝<small>Reject</small></button>
                </>}
                {item.status === "reviewed" && item.local_path?.startsWith("sources/") && (
                  <button disabled={busy} onClick={() => previewFacts(item.id)}>
                    提取财务候选<small>Preview facts</small>
                  </button>
                )}
              </div>
            </div>
          ))}
          {selected && selected.evidence.length === 0 && <p className="empty-state">请先捕获官方来源；也可使用部分模式带缺口执行，仅生成低置信研究线索。</p>}
          {!selected && <p className="empty-state">请选择研究任务以查看证据台账。</p>}
          {selected && factCandidates.length > 0 && (
            <div className="fact-candidate-ledger">
              <div className="event-ledger-head">
                <BilingualText zh="财务事实候选 / 人工确认" en="Financial fact candidates / Human review" />
                <span>{factCandidates.filter((item) => item.status === "pending").length} 条待确认</span>
              </div>
              {factCandidates.map((item) => (
                <article className="fact-candidate-row" key={item.id}>
                  <div>
                    <strong>{item.metric}</strong>
                    <small>{item.ticker} · {item.period_end} · {item.source_locator}</small>
                  </div>
                  <span>{new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(item.value)} {item.unit}</span>
                  <p>{item.excerpt}</p>
                  <i>{translateUiValue(item.status)}</i>
                  {item.status === "pending" && <div>
                    <button disabled={busy} onClick={() => decideFactCandidate(item.id, true)}>确认</button>
                    <button disabled={busy} onClick={() => decideFactCandidate(item.id, false)}>拒绝</button>
                  </div>}
                </article>
              ))}
            </div>
          )}
        </article>

        <article className="radar panel" id="radar">
          <div className="panel-title"><BilingualText zh="研究候选队列" en="Research queue" /><b>{selected?.candidates.length ?? 0} 个候选<small>Candidates</small></b></div>
          <div className="radar-head"><span>代码<small>Symbol</small></span><span>结论<small>Verdict</small></span><span>置信度<small>Confidence</small></span><span>跟踪<small>Track</small></span></div>
          {selected?.candidates.map((candidate) => {
            const node = nodes.get(candidate.node_id);
            const isTracked = trackedNodeIds.has(candidate.node_id);
            return (
              <div className="candidate-row" key={candidate.node_id}>
                <div><strong>{node?.ticker ?? "—"}</strong><small>{node?.label ?? candidate.node_id}</small></div>
                <span className={`verdict ${candidate.verdict}`}>{translateUiValue(candidate.verdict)}<small>{humanizeUiValue(candidate.verdict)}</small></span>
                <span>{translateUiValue(candidate.confidence)}<small>{humanizeUiValue(candidate.confidence)}</small></span>
                <button className="track-button" aria-label={isTracked ? "已跟踪" : "加入跟踪"} disabled={busy || isTracked} onClick={() => addToTracking(candidate.node_id)}>{isTracked ? "✓" : "+"}</button>
              </div>
            );
          })}
          {selected && selected.candidates.length === 0 && <p className="empty-state">完成评分或比较阶段后，候选标的会显示在这里。</p>}
          {!selected && <p className="empty-state">研究候选将显示在这里。</p>}
          {decision && <div className="next-actions"><BilingualText zh="下一步行动" en="Next actions" />{decision.next_actions.map((item) => <p key={item}>→ {item}</p>)}</div>}
        </article>
      </section>

      <section className="tracking-board panel" id="tracking">
        <div className="panel-title"><BilingualText zh="前瞻跟踪 / 阶段看板" en="Forward tracking / Stage board" /><b>{tracking.length} 张跟踪卡<small>Live cards</small></b></div>
        {tracking.length === 0 && <p className="empty-state">将候选加入跟踪，以建立首次关注价与基准收益起点。</p>}
        <div className="tracking-grid">
          {tracking.map((card) => <article key={card.tracked.id}><div className="tracking-top"><span>{card.tracked.ticker}</span><select value={card.tracked.stage} onChange={(event) => moveStage(card.tracked.id, event.target.value as TrackingStage)}><option value="research">研究中 · Research</option><option value="watch">重点观察 · Watch</option><option value="validated">已验证 · Validated</option><option value="triggered">已触发 · Triggered</option><option value="invalidated">已失效 · Invalidated</option><option value="archived">已归档 · Archived</option></select></div><h3>{card.tracked.label}</h3><div className="return-strip"><div><small>标的收益<em>Return</em></small><strong>{card.latest ? `${card.latest.return_pct >= 0 ? "+" : ""}${card.latest.return_pct.toFixed(2)}%` : "—"}</strong></div><div><small>基准收益<em>Benchmark</em></small><strong>{card.latest ? `${card.latest.benchmark_return_pct >= 0 ? "+" : ""}${card.latest.benchmark_return_pct.toFixed(2)}%` : "—"}</strong></div><div><small>超额收益<em>Alpha</em></small><strong className={card.latest && card.latest.alpha_pct >= 0 ? "positive" : ""}>{card.latest ? `${card.latest.alpha_pct >= 0 ? "+" : ""}${card.latest.alpha_pct.toFixed(2)}%` : "—"}</strong></div></div><footer><span>{card.snapshot_count} 个快照 · {card.events.length} 个事件</span><button disabled={busy} onClick={() => updateSnapshot(card.tracked.id)}>刷新价格<small>Refresh prices</small></button></footer></article>)}
        </div>
      </section>

      <footer><span>CapexGraph / 本机</span><p>这是研究基础设施，不构成投资建议。<small>Research infrastructure, not investment advice.</small></p><span>证据优先于叙事。<small>Evidence over narrative.</small></span></footer>
      <ConnectionCenter
        open={connectionsOpen}
        onClose={() => setConnectionsOpen(false)}
        onChanged={() => refreshModelProviders().catch(() => undefined)}
      />
    </main>
  );
}

export default App;
