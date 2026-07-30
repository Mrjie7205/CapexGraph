import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  addLiveVerificationSource,
  actOnLiveEvent,
  analyzeLiveEvent,
  attachLiveContextToRun,
  captureLiveVerificationSource,
  createLiveLinkedRun,
  getLiveCoverage,
  getLiveEvent,
  getLiveSettings,
  getLiveStatus,
  getLiveVerificationTask,
  listLiveAudit,
  listLiveEvents,
  listRuns,
  liveStreamUrl,
  openLiveVerificationTask,
  patchLiveSettings,
  pollLiveStream,
  replayLiveDemo,
  reviewLiveVerificationEvidence,
  setLiveMonitor,
  type LiveAuditEntry,
  type LiveChannel,
  type LiveCheckpoint,
  type LiveEventRecord,
  type LiveHealth,
  type LiveLinkedRunResponse,
  type LiveSettings,
  type LiveStatus,
  type LiveVerificationTaskRecord,
  type Provider,
  type ResearchRun,
  type RunMode,
} from "./api";

type StreamState = "connecting" | "connected" | "reconnecting";
type AnalyzeProvider = "rules" | "codex_subscription" | "openai";

const HEALTH_LABELS: Record<LiveHealth | "standby", string> = {
  active: "ACTIVE",
  degraded: "DEGRADED",
  exhausted: "BUDGET HOLD",
  not_configured: "WAIT KEY",
  off: "OFF",
  replay: "REPLAY",
  standby: "STANDBY",
};

const TASK_LABELS: Record<string, string> = {
  pending: "等待官方来源",
  source_suggested: "来源待捕获",
  capture_pending: "正在捕获",
  captured: "等待人工审核",
  evidence_linked: "证据已链接",
  rejected: "已拒绝",
  failed: "捕获失败，可重试",
  cancelled: "已取消",
};

function formatTime(value?: string): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(parsed);
}

function seconds(value?: number): string {
  if (value === undefined || value === null) return "—";
  return value < 60 ? `${value.toFixed(1)}s` : `${(value / 60).toFixed(1)}m`;
}

function channelHealth(
  channel: LiveChannel,
  checkpoints: LiveCheckpoint[],
  configured: boolean,
  enabled: boolean,
): { health: LiveHealth | "standby"; freshness?: string; budget?: string } {
  if (!enabled) return { health: "off" };
  const relevant = checkpoints.filter((item) => item.channel === channel);
  if (relevant.length === 0) {
    return { health: configured ? "standby" : "not_configured" };
  }
  const order: Array<LiveHealth> = ["degraded", "exhausted", "active", "replay", "not_configured", "off"];
  const health = order.find((candidate) => relevant.some((item) => item.health === candidate)) ?? "standby";
  const freshest = relevant
    .map((item) => item.last_observed_at)
    .filter((item): item is string => Boolean(item))
    .sort()
    .at(-1);
  const budgeted = relevant.find((item) => item.call_budget);
  return {
    health,
    freshness: freshest,
    budget: budgeted ? `${budgeted.calls_used}/${budgeted.call_budget}` : undefined,
  };
}

export function LiveDesk() {
  const [status, setStatus] = useState<LiveStatus | null>(null);
  const [events, setEvents] = useState<LiveEventRecord[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [settings, setSettings] = useState<LiveSettings | null>(null);
  const [streamState, setStreamState] = useState<StreamState>("connecting");
  const [category, setCategory] = useState("all");
  const [channel, setChannel] = useState("all");
  const [query, setQuery] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [analysisProvider, setAnalysisProvider] = useState<AnalyzeProvider>("rules");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [bridgeOpen, setBridgeOpen] = useState(false);
  const [bridgeRuns, setBridgeRuns] = useState<ResearchRun[]>([]);
  const [bridgeRunId, setBridgeRunId] = useState("");
  const [bridgeMode, setBridgeMode] = useState<RunMode>("theme");
  const [bridgeMarket, setBridgeMarket] = useState("CN");
  const [taskRecord, setTaskRecord] = useState<LiveVerificationTaskRecord | null>(null);
  const [audit, setAudit] = useState<LiveAuditEntry[]>([]);
  const [linkedRun, setLinkedRun] = useState<LiveLinkedRunResponse | null>(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceTitle, setSourceTitle] = useState("");
  const [sourcePublisher, setSourcePublisher] = useState("");
  const [issuerDomain, setIssuerDomain] = useState("");

  async function refresh() {
    const [nextStatus, nextEvents, nextCoverage, nextSettings] = await Promise.all([
      getLiveStatus(),
      listLiveEvents(),
      getLiveCoverage(),
      getLiveSettings(),
    ]);
    setStatus({ ...nextStatus, coverage: nextCoverage });
    setEvents(nextEvents);
    setSettings(nextSettings);
    setSelectedKey((current) => current || nextEvents[0]?.signal.signal_key || "");
  }

  useEffect(() => {
    refresh().catch((reason) => {
      setError(reason instanceof Error ? reason.message : "Live Desk unavailable");
    });
    const timer = window.setInterval(() => {
      getLiveStatus().then(setStatus).catch(() => undefined);
    }, 15000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const source = new EventSource(liveStreamUrl());
    setStreamState("connecting");
    source.onopen = () => setStreamState("connected");
    source.onerror = () => setStreamState("reconnecting");
    source.addEventListener("live.signal", (rawEvent) => {
      const message = rawEvent as MessageEvent<string>;
      try {
        const incoming = JSON.parse(message.data) as LiveEventRecord;
        setEvents((current) => [
          incoming,
          ...current.filter((item) => item.signal.signal_key !== incoming.signal.signal_key),
        ]);
        setSelectedKey((current) => current || incoming.signal.signal_key);
        if (
          settings?.desktop_notifications &&
          typeof Notification !== "undefined" &&
          Notification.permission === "granted" &&
          incoming.alert?.state === "unread"
        ) {
          new Notification("CapexGraph · 市场事件", {
            body: incoming.signal.title,
            tag: incoming.signal.signal_key,
          });
        }
      } catch {
        setStreamState("reconnecting");
      }
    });
    return () => source.close();
  }, [settings?.desktop_notifications]);

  const visibleEvents = useMemo(
    () =>
      events.filter((item) => {
        if (category !== "all" && item.signal.category !== category) return false;
        if (channel !== "all" && !item.signal.channels.includes(channel as LiveChannel)) return false;
        if (query && !item.signal.title.toLocaleLowerCase().includes(query.toLocaleLowerCase())) return false;
        return true;
      }),
    [events, category, channel, query],
  );
  const selected =
    events.find((item) => item.signal.signal_key === selectedKey) ??
    visibleEvents[0] ??
    null;
  const mcp = channelHealth(
    "mcp",
    status?.checkpoints ?? [],
    status?.configuration.mcp.configured ?? false,
    status?.settings.mcp_enabled ?? true,
  );
  const websocket = channelHealth(
    "websocket",
    status?.checkpoints ?? [],
    status?.configuration.websocket.configured ?? false,
    status?.settings.websocket_enabled ?? true,
  );
  const activeTask = taskRecord?.task ?? selected?.verification_tasks?.[0];
  const linkedContexts = selected?.run_links ?? [];
  const bridgeStage = activeTask?.status === "evidence_linked"
    ? 4
    : activeTask?.status === "captured"
      ? 3
      : activeTask
        ? 2
        : 1;

  async function refreshBridge(signalReference?: string) {
    const reference = signalReference ?? selected?.signal.signal_key;
    if (!reference) return;
    const [eventRecord, nextRuns, nextAudit] = await Promise.all([
      getLiveEvent(reference),
      listRuns(),
      listLiveAudit(reference),
    ]);
    setEvents((current) => [
      eventRecord,
      ...current.filter((item) => item.signal.signal_key !== eventRecord.signal.signal_key),
    ]);
    setBridgeRuns(nextRuns);
    setAudit(nextAudit);
    const task = eventRecord.verification_tasks[0];
    if (task) {
      const detailed = await getLiveVerificationTask(task.id);
      setTaskRecord(detailed);
      setBridgeRunId((current) => current || detailed.task.run_id || nextRuns[0]?.id || "");
    } else {
      setTaskRecord(null);
      setBridgeRunId((current) => current || nextRuns[0]?.id || "");
    }
  }

  async function showResearchBridge() {
    if (!selected) return;
    setBridgeOpen(true);
    setSourceTitle((current) => current || `${selected.signal.title} · 官方披露`);
    setBusy("bridge-load");
    setError("");
    try {
      await refreshBridge(selected.signal.signal_key);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Research Bridge unavailable");
    } finally {
      setBusy("");
    }
  }

  async function doRefresh(action: () => Promise<unknown>, label: string) {
    setBusy(label);
    setError("");
    try {
      await action();
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${label} failed`);
    } finally {
      setBusy("");
    }
  }

  async function runAnalysis() {
    if (!selected) return;
    const provider = analysisProvider === "rules" ? undefined : analysisProvider as Provider;
    await doRefresh(
      () => analyzeLiveEvent(selected.signal.id, provider, provider !== undefined),
      "analyze",
    );
  }

  async function eventAction(action: "dismiss" | "mute" | "watch") {
    if (!selected) return;
    await doRefresh(() => actOnLiveEvent(selected.signal.id, action), action);
  }

  async function bridgeAction(
    action: () => Promise<unknown>,
    label: string,
  ) {
    if (!selected) return;
    setBusy(label);
    setError("");
    try {
      await action();
      await refresh();
      await refreshBridge(selected.signal.signal_key);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${label} failed`);
    } finally {
      setBusy("");
    }
  }

  async function openVerificationTask() {
    if (!selected || !bridgeRunId) return;
    if (!window.confirm(
      "确认创建官方来源核验任务？这会新增审计记录并把信号状态推进到“待官方补证”，不会把快讯直接当作 Evidence。",
    )) return;
    await bridgeAction(
      async () => {
        const record = await openLiveVerificationTask(selected.signal.id, bridgeRunId);
        setTaskRecord(record);
      },
      "bridge-open-task",
    );
  }

  async function submitOfficialSource(event: FormEvent) {
    event.preventDefault();
    if (!activeTask || !bridgeRunId || !sourceUrl.trim() || !sourceTitle.trim()) return;
    if (!window.confirm(
      "确认把这个网址作为监管机构或公司官方来源候选？系统会校验来源权限，但仍需后续捕获和人工审核。",
    )) return;
    await bridgeAction(
      async () => {
        const record = await addLiveVerificationSource(activeTask.id, {
          run_id: bridgeRunId,
          url: sourceUrl.trim(),
          title: sourceTitle.trim(),
          publisher: sourcePublisher.trim() || undefined,
          issuer_domains: issuerDomain.trim() ? [issuerDomain.trim()] : undefined,
        });
        setTaskRecord(record);
      },
      "bridge-source",
    );
  }

  async function captureOfficialSource() {
    if (!activeTask) return;
    const retry = activeTask.status === "failed";
    if (!window.confirm(
      `${retry ? "重试" : "开始"}受保护的官方网页捕获？捕获完成后仍保持“待审核”，不会自动变成可引用证据。`,
    )) return;
    await bridgeAction(
      async () => {
        const record = await captureLiveVerificationSource(activeTask.id, retry);
        setTaskRecord(record);
      },
      "bridge-capture",
    );
  }

  async function reviewOfficialEvidence(approved: boolean) {
    if (!activeTask) return;
    if (!window.confirm(
      approved
        ? "确认你已人工核对正文、主体和结论？批准后会把哈希匹配的官方材料链接为 Evidence，并生成新的信号版本。"
        : "确认拒绝这份捕获材料？它不会链接到信号，也不能支持研究结论。",
    )) return;
    await bridgeAction(
      async () => {
        const record = await reviewLiveVerificationEvidence(activeTask.id, approved);
        setTaskRecord(record);
      },
      approved ? "bridge-approve" : "bridge-reject",
    );
  }

  async function attachToExistingRun() {
    if (!selected || !bridgeRunId) return;
    if (!window.confirm(
      "确认把当前信号的不可变快照挂接到所选研究？原 run 的既有结果不会被改写，聚合消息仍标记为 secondary signal。",
    )) return;
    await bridgeAction(
      () => attachLiveContextToRun(bridgeRunId, selected.signal.id),
      "bridge-attach-run",
    );
  }

  async function createBridgeRun(asChild: boolean) {
    if (!selected) return;
    if (asChild && !bridgeRunId) return;
    if (!window.confirm(
      asChild
        ? "确认从所选研究创建一个新的派生复评？父 run 将保持完全不变。"
        : "确认以当前信号创建一个新的研究 run？这里只创建研究档案和不可变上下文，不会自动执行模型分析。",
    )) return;
    await bridgeAction(
      async () => {
        const response = await createLiveLinkedRun(selected.signal.id, {
          parent_run_id: asChild ? bridgeRunId : undefined,
          mode: asChild ? undefined : bridgeMode,
          subject: asChild ? undefined : selected.signal.title,
          market: asChild ? undefined : bridgeMarket.trim().toUpperCase(),
          note: asChild
            ? "Derived re-evaluation created from the Live Desk."
            : "Research run created from the Live Desk.",
        });
        setLinkedRun(response);
        setBridgeRunId(response.run.id);
      },
      asChild ? "bridge-child-run" : "bridge-new-run",
    );
  }

  async function saveSettings() {
    if (!settings) return;
    setBusy("settings");
    setError("");
    try {
      const updated = await patchLiveSettings(settings);
      setSettings(updated);
      setSettingsOpen(false);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Settings update failed");
    } finally {
      setBusy("");
    }
  }

  async function toggleNotifications(enabled: boolean) {
    if (
      enabled &&
      typeof Notification !== "undefined" &&
      Notification.permission === "default"
    ) {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setError("浏览器未授权桌面提醒；事件仍会留在 Live Desk。");
        return;
      }
    }
    setSettings((current) => current ? { ...current, desktop_notifications: enabled } : current);
  }

  return (
    <section className="live-desk" id="live">
      <header className="live-mast">
        <div>
          <span className="live-kicker">Live event gateway / 市场脉搏</span>
          <h2>先发现异动，<em>再证明影响。</em></h2>
          <p>双通道同级运行；聚合快讯只生成研究优先级，不是事实证据，更不是交易指令。</p>
        </div>
        <div className="live-operations">
          <div className={`channel-chip ${mcp.health}`}>
            <i />
            <span>Jin10 MCP<small>{HEALTH_LABELS[mcp.health]} · {mcp.budget ?? "head poll"}</small></span>
          </div>
          <div className={`channel-chip ${websocket.health}`}>
            <i />
            <span>WebSocket<small>{HEALTH_LABELS[websocket.health]} · {formatTime(websocket.freshness)}</small></span>
          </div>
          <div className={`channel-chip stream-${streamState}`}>
            <i />
            <span>Live Desk SSE<small>{streamState.toUpperCase()}</small></span>
          </div>
          <div className="live-buttons">
            <button
              disabled={Boolean(busy)}
              onClick={() => doRefresh(() => setLiveMonitor(!status?.running), "monitor")}
            >
              {status?.running ? "Stop monitor" : "Start monitor"}
            </button>
            <button onClick={() => setSettingsOpen(true)}>Settings</button>
          </div>
        </div>
      </header>

      <div className="live-tape" aria-label="Live coverage metrics">
        <article><span>Canonical signals</span><strong>{status?.coverage.total_signals ?? 0}</strong><small>{status?.unread_alerts ?? 0} unread alerts</small></article>
        <article><span>Cross-channel overlap</span><strong>{((status?.coverage.overlap_ratio ?? 0) * 100).toFixed(0)}%</strong><small>{status?.coverage.matched ?? 0} matched · {status?.coverage.divergent ?? 0} divergent</small></article>
        <article><span>Delivery P50 / P95</span><strong>{seconds(status?.coverage.delivery_delay_p50_seconds)}</strong><small>{seconds(status?.coverage.delivery_delay_p95_seconds)} tail delay</small></article>
        <article><span>Runtime</span><strong>{status?.running ? "ON" : "OFF"}</strong><small>{status?.running ? `since ${formatTime(status.started_at)}` : "manual inspection available"}</small></article>
      </div>

      {error && <div className="live-error">{error}</div>}

      <div className="live-console">
        <aside className="signal-feed">
          <div className="live-panel-head">
            <span>Signal ledger</span>
            <b>{visibleEvents.length.toString().padStart(2, "0")}</b>
          </div>
          <div className="feed-filters">
            <input placeholder="搜索事件…" value={query} onChange={(event) => setQuery(event.target.value)} />
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="all">全部类型</option><option value="flash">快讯</option><option value="calendar">日历</option><option value="quote">行情</option>
            </select>
            <select value={channel} onChange={(event) => setChannel(event.target.value)}>
              <option value="all">全部通道</option><option value="mcp">MCP</option><option value="websocket">WebSocket</option><option value="fixture">Fixture</option>
            </select>
          </div>
          <div className="feed-actions">
            <button disabled={Boolean(busy)} onClick={() => doRefresh(() => pollLiveStream("flash"), "poll-flash")}>Poll flash</button>
            <button disabled={Boolean(busy)} onClick={() => doRefresh(() => pollLiveStream("calendar"), "poll-calendar")}>Poll calendar</button>
          </div>
          <div className="signal-list">
            {visibleEvents.map((item) => (
              <button
                key={item.signal.signal_key}
                className={selected?.signal.signal_key === item.signal.signal_key ? "selected" : ""}
                onClick={() => setSelectedKey(item.signal.signal_key)}
              >
                <div className="signal-stamp">
                  <time>{formatTime(item.signal.last_observed_at)}</time>
                  <span className={item.signal.match_status}>{item.signal.match_status.replace("_", " ")}</span>
                </div>
                <strong>{item.signal.title}</strong>
                <div className="signal-tags">
                  <span>{item.signal.category}</span>
                  {item.signal.channels.map((source) => <i key={source}>{source}</i>)}
                  {item.assessment?.matched_themes.slice(0, 2).map((theme) => <em key={theme}>{theme}</em>)}
                  <em className={`verification-${item.signal.verification_state}`}>
                    {item.signal.verification_state.replaceAll("_", " ")}
                  </em>
                  <b>{item.assessment?.total_score.toFixed(0) ?? "—"}</b>
                </div>
              </button>
            ))}
            {visibleEvents.length === 0 && (
              <div className="live-empty">
                <strong>还没有实时事件</strong>
                <p>配置 MCP 后可正式轮询；也可以先加载冻结双通道样例验证完整路径。</p>
                <button disabled={Boolean(busy)} onClick={() => doRefresh(replayLiveDemo, "demo")}>Load no-key replay</button>
              </div>
            )}
          </div>
        </aside>

        <article className="signal-detail">
          <div className="live-panel-head">
            <span>Impact brief</span>
            <b>{selected?.signal.verification_state.replaceAll("_", " ") ?? "NO SIGNAL"}</b>
          </div>
          {selected ? (
            <>
              <div className="detail-lead">
                <div className="detail-score">
                  <strong>{selected.assessment?.total_score.toFixed(0) ?? "—"}</strong>
                  <span>rules score / 100</span>
                </div>
                <div>
                  <span className="detail-overline">{selected.signal.category} · V{selected.signal.version} · {selected.signal.match_status}</span>
                  <h3>{selected.signal.title}</h3>
                  <p>{selected.trust_notice}</p>
                </div>
              </div>

              <div className="score-ruler">
                {(["relevance", "urgency", "importance"] as const).map((metric) => (
                  <div key={metric}>
                    <span>{metric}</span>
                    <i><b style={{ width: `${selected.assessment?.[metric] ?? 0}%` }} /></i>
                    <strong>{selected.assessment?.[metric].toFixed(0) ?? "—"}</strong>
                  </div>
                ))}
                <div><span>novelty</span><i><b style={{ width: `${(selected.assessment?.novelty ?? 0) * 100}%` }} /></i><strong>{((selected.assessment?.novelty ?? 0) * 100).toFixed(0)}</strong></div>
              </div>

              <div className="lineage">
                <div className="detail-section-title"><span>Channel lineage</span><b>{selected.observations.length} observations</b></div>
                {selected.observations.map((observation) => (
                  <div className="lineage-row" key={observation.id}>
                    <span className={`channel-mark ${observation.channel}`}>{observation.channel}</span>
                    <div><strong>{observation.provider} / {observation.stream}</strong><small>published {formatTime(observation.published_at)} · observed {formatTime(observation.observed_at)}</small></div>
                    <i>{observation.retention_class}</i>
                  </div>
                ))}
              </div>

              <div className="impact-analysis">
                <div className="detail-section-title"><span>Conditional impact</span><b>{selected.analysis?.status ?? "NOT RUN"}</b></div>
                {selected.proposal ? (
                  <>
                    <p className="analysis-cost">analysis lineage · {selected.analysis?.model_provider ?? "rules"} · {selected.analysis?.model_call_count ?? 0} call(s) · {selected.analysis?.cost_status ?? "not_applicable"}</p>
                    <div className="impact-axis">
                      <div><small>Direction</small><strong>{selected.proposal.direction}</strong></div>
                      <div><small>Horizon</small><strong>{selected.proposal.horizon}</strong></div>
                      <div><small>Confidence</small><strong>{(selected.proposal.confidence * 100).toFixed(0)}%</strong></div>
                      <div><small>Next action</small><strong>{selected.proposal.recommended_action}</strong></div>
                    </div>
                    <ol className="transmission-path">
                      {selected.proposal.transmission_path.map((step, index) => <li key={`${step}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span>{step}</li>)}
                    </ol>
                    <div className="gap-note"><span>Evidence gaps</span>{selected.proposal.evidence_gaps.map((gap) => <p key={gap}>— {gap}</p>)}</div>
                    {selected.analysis?.failure && <div className="analysis-failure">{selected.analysis.failure}</div>}
                  </>
                ) : (
                  <p className="detail-placeholder">规则评分已完成。按需运行影响分析，低分事件不会自动产生模型费用。</p>
                )}
              </div>

              <div className="decision-bar">
                <select value={analysisProvider} onChange={(event) => setAnalysisProvider(event.target.value as AnalyzeProvider)}>
                  <option value="rules">Rules only · no key</option>
                  <option value="codex_subscription">Codex subscription</option>
                  <option value="openai">OpenAI API</option>
                </select>
                <button disabled={Boolean(busy)} onClick={runAnalysis}>Analyze impact</button>
                <button disabled={Boolean(busy)} onClick={() => eventAction("watch")}>Watch</button>
                <button disabled={Boolean(busy)} onClick={showResearchBridge}>Research bridge</button>
                <button disabled={Boolean(busy)} onClick={() => eventAction("dismiss")}>Dismiss</button>
                <button disabled={Boolean(busy)} onClick={() => eventAction("mute")}>Mute</button>
              </div>
            </>
          ) : (
            <div className="live-empty detail-empty"><strong>选择一条信号</strong><p>这里会呈现合流谱系、确定性评分、影响路径、证据缺口和人工动作。</p></div>
          )}
        </article>

        <aside className="coverage-rail">
          <div className="live-panel-head"><span>Coverage audit</span><b>LIVE</b></div>
          <div className="coverage-dial" style={{ "--coverage": `${(status?.coverage.overlap_ratio ?? 0) * 360}deg` } as React.CSSProperties}>
            <div><strong>{((status?.coverage.overlap_ratio ?? 0) * 100).toFixed(0)}%</strong><span>overlap</span></div>
          </div>
          <dl className="coverage-list">
            <div><dt>MCP only</dt><dd>{status?.coverage.mcp_only ?? 0}</dd></div>
            <div><dt>WS only</dt><dd>{status?.coverage.websocket_only ?? 0}</dd></div>
            <div><dt>Matched</dt><dd>{status?.coverage.matched ?? 0}</dd></div>
            <div><dt>Divergent</dt><dd>{status?.coverage.divergent ?? 0}</dd></div>
            <div><dt>P95 delay</dt><dd>{seconds(status?.coverage.delivery_delay_p95_seconds)}</dd></div>
          </dl>
          <div className="rail-note">
            <span>Interpretation</span>
            <p>通道覆盖率衡量发现能力，不证明消息正确。字段差异会保留为 divergent，不会被静默覆盖。</p>
          </div>
          <div className="rail-note safety">
            <span>Evidence firewall</span>
            <p>任何聚合信号都不能自动提升供应链关系置信度。官方材料捕获与人工审核仍是必经步骤。</p>
          </div>
          <div className={`rail-note soak ${status?.latest_soak?.passed ? "passed" : ""}`}>
            <span>Release gate</span>
            <p>
              {status?.latest_soak
                ? `${status.latest_soak.passed ? "PASS" : "FAIL"} · ${status.latest_soak.mode} · ${status.latest_soak.cycles} cycles`
                : "尚无本地 soak 报告；运行 capexgraph live soak。"}
            </p>
          </div>
        </aside>
      </div>

      {bridgeOpen && selected && (
        <div
          className="settings-scrim bridge-scrim"
          role="presentation"
          onMouseDown={() => setBridgeOpen(false)}
        >
          <aside
            className="research-bridge"
            role="dialog"
            aria-modal="true"
            aria-label="Research Bridge"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <span>Evidence firewall / M7</span>
                <h3>Research Bridge</h3>
                <p>{selected.signal.title}</p>
              </div>
              <button aria-label="Close Research Bridge" onClick={() => setBridgeOpen(false)}>×</button>
            </header>

            <p className="bridge-notice">
              这里把“值得核验的二手信号”推进为“可审计的研究输入”。每个写入动作都需要确认；
              只有监管机构或公司官方材料经捕获、哈希校验和人工批准后，才会成为 Evidence。
            </p>

            <div className="bridge-progress" aria-label={`Research Bridge stage ${bridgeStage}`}>
              {[
                ["01", "Signal", "二手线索"],
                ["02", "Official source", "官方候选"],
                ["03", "Human review", "人工审核"],
                ["04", "Linked run", "不可变复评"],
              ].map(([number, label, note], index) => (
                <div
                  className={bridgeStage > index ? "complete" : bridgeStage === index ? "active" : ""}
                  key={number}
                >
                  <b>{number}</b>
                  <span>{label}</span>
                  <small>{note}</small>
                </div>
              ))}
            </div>

            <section className="bridge-block">
              <div className="bridge-block-head">
                <div><span>Research file</span><h4>选择承接研究，或新建独立档案</h4></div>
                <b>{linkedContexts.length} linked snapshot(s)</b>
              </div>
              <div className="bridge-run-controls">
                <label>
                  已有研究
                  <select value={bridgeRunId} onChange={(event) => setBridgeRunId(event.target.value)}>
                    <option value="">请选择 run</option>
                    {bridgeRuns.map((run) => (
                      <option value={run.id} key={run.id}>
                        {run.mode.toUpperCase()} · {run.subject} · {run.id.slice(-8)}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  disabled={!bridgeRunId || Boolean(busy)}
                  onClick={attachToExistingRun}
                >
                  挂接不可变快照
                </button>
                <button
                  disabled={!bridgeRunId || Boolean(busy)}
                  onClick={() => createBridgeRun(true)}
                >
                  从所选 run 派生复评
                </button>
              </div>
              <div className="bridge-new-run">
                <label>
                  新建类型
                  <select value={bridgeMode} onChange={(event) => setBridgeMode(event.target.value as RunMode)}>
                    <option value="theme">Theme Scan</option>
                    <option value="anchor">Anchor Scan</option>
                  </select>
                </label>
                <label>
                  市场
                  <input value={bridgeMarket} onChange={(event) => setBridgeMarket(event.target.value)} />
                </label>
                <button disabled={Boolean(busy)} onClick={() => createBridgeRun(false)}>
                  新建链接研究
                </button>
              </div>
              {linkedRun && (
                <div className="bridge-result">
                  <span>Latest linked run</span>
                  <strong>{linkedRun.run.id}</strong>
                  <small>
                    context {linkedRun.link.context_hash.slice(0, 12)}… ·
                    {linkedRun.link.parent_run_id ? " parent preserved" : " new research file"}
                  </small>
                </div>
              )}
            </section>

            <section className="bridge-block verification-workflow">
              <div className="bridge-block-head">
                <div><span>Official-source task</span><h4>补证队列</h4></div>
                <b>{activeTask ? TASK_LABELS[activeTask.status] : "NOT OPEN"}</b>
              </div>

              {!activeTask ? (
                <div className="bridge-empty-action">
                  <p>先选择一个研究 run。创建任务只改变核验状态并留下审计记录，不会自动支持任何事实结论。</p>
                  <button
                    disabled={!bridgeRunId || Boolean(busy)}
                    onClick={openVerificationTask}
                  >
                    创建官方来源核验任务
                  </button>
                </div>
              ) : (
                <>
                  <div className={`task-card status-${activeTask.status}`}>
                    <div>
                      <span>{activeTask.id}</span>
                      <strong>{TASK_LABELS[activeTask.status] ?? activeTask.status}</strong>
                    </div>
                    <small>
                      run {activeTask.run_id?.slice(-10) ?? "not linked"} ·
                      attempt {activeTask.attempts} · updated {formatTime(activeTask.updated_at)}
                    </small>
                    {activeTask.error && <p>{activeTask.error}</p>}
                  </div>

                  {taskRecord?.source_suggestion && (
                    <div className="official-source-card">
                      <span>{taskRecord.source_suggestion.authority} · {taskRecord.source_suggestion.status}</span>
                      <strong>{taskRecord.source_suggestion.title}</strong>
                      <a href={taskRecord.source_suggestion.url} target="_blank" rel="noreferrer">
                        {taskRecord.source_suggestion.canonical_url}
                      </a>
                    </div>
                  )}

                  {["pending", "source_suggested", "failed"].includes(activeTask.status) && (
                    <form className="official-source-form" onSubmit={submitOfficialSource}>
                      <label className="wide">
                        官方网页 URL
                        <input
                          required
                          type="url"
                          value={sourceUrl}
                          onChange={(event) => setSourceUrl(event.target.value)}
                          placeholder="https://公司官网或监管机构/公告"
                        />
                      </label>
                      <label className="wide">
                        材料标题
                        <input
                          required
                          value={sourceTitle}
                          onChange={(event) => setSourceTitle(event.target.value)}
                        />
                      </label>
                      <label>
                        发布主体
                        <input
                          value={sourcePublisher}
                          onChange={(event) => setSourcePublisher(event.target.value)}
                          placeholder="公司 / 交易所 / 监管机构"
                        />
                      </label>
                      <label>
                        公司官网域名
                        <input
                          value={issuerDomain}
                          onChange={(event) => setIssuerDomain(event.target.value)}
                          placeholder="example.com；监管网站可留空"
                        />
                      </label>
                      <button disabled={Boolean(busy)} type="submit">登记官方来源候选</button>
                    </form>
                  )}

                  {["source_suggested", "failed"].includes(activeTask.status) && (
                    <div className="bridge-gate-action">
                      <p>捕获会保存规范化正文与 source hash；完成后仍需你人工核对。</p>
                      <button disabled={Boolean(busy)} onClick={captureOfficialSource}>
                        {activeTask.status === "failed" ? "重试受保护捕获" : "捕获并生成待审 Evidence"}
                      </button>
                    </div>
                  )}

                  {activeTask.status === "captured" && (
                    <div className="review-gate">
                      <div>
                        <span>Human review required</span>
                        <strong>{taskRecord?.evidence?.title ?? activeTask.evidence_id}</strong>
                        <p>请打开并核对捕获材料。批准会原子化完成 Evidence 链接；拒绝不会留下可引用关系。</p>
                      </div>
                      <div>
                        <button
                          className="reject"
                          disabled={Boolean(busy)}
                          onClick={() => reviewOfficialEvidence(false)}
                        >
                          拒绝材料
                        </button>
                        <button
                          disabled={Boolean(busy)}
                          onClick={() => reviewOfficialEvidence(true)}
                        >
                          已核对，批准并链接
                        </button>
                      </div>
                    </div>
                  )}

                  {activeTask.status === "evidence_linked" && (
                    <div className="evidence-seal">
                      <b>✓</b>
                      <div>
                        <span>Reviewed Evidence linked</span>
                        <strong>{taskRecord?.evidence?.title ?? activeTask.evidence_id}</strong>
                        <small>
                          link {taskRecord?.evidence_link?.link_hash.slice(0, 16)}… ·
                          source {taskRecord?.evidence_link?.source_hash.slice(0, 16)}…
                        </small>
                      </div>
                    </div>
                  )}
                </>
              )}
            </section>

            <section className="bridge-block audit-block">
              <div className="bridge-block-head">
                <div><span>Immutable audit</span><h4>事件时间线</h4></div>
                <b>{audit.length} entries</b>
              </div>
              <ol>
                {audit.slice().reverse().map((entry, index) => (
                  <li key={`${entry.event_type}-${entry.object_id}-${entry.id ?? index}`}>
                    <time>{formatTime(entry.occurred_at)}</time>
                    <div>
                      <span>{entry.event_type} · {entry.actor}</span>
                      <strong>{entry.summary}</strong>
                      <small>{entry.object_type} / {entry.object_id}</small>
                    </div>
                  </li>
                ))}
                {audit.length === 0 && <li className="audit-empty">暂无审计记录。</li>}
              </ol>
            </section>
          </aside>
        </div>
      )}

      {settingsOpen && settings && (
        <div className="settings-scrim" role="presentation" onMouseDown={() => setSettingsOpen(false)}>
          <aside className="live-settings" role="dialog" aria-modal="true" aria-label="Live Desk settings" onMouseDown={(event) => event.stopPropagation()}>
            <header><div><span>Gateway controls</span><h3>Live Desk 设置</h3></div><button onClick={() => setSettingsOpen(false)}>×</button></header>
            <p className="settings-notice">密钥只从后端环境变量读取；本面板不会接收、显示或返回任何 Bearer Token / Secret-Key。</p>
            <fieldset>
              <legend>Equal-priority channels</legend>
              <label><input type="checkbox" checked={settings.mcp_enabled} onChange={(event) => setSettings({ ...settings, mcp_enabled: event.target.checked })} /> MCP adaptive polling</label>
              <label><input type="checkbox" checked={settings.websocket_enabled} onChange={(event) => setSettings({ ...settings, websocket_enabled: event.target.checked })} /> WebSocket push</label>
              <label><input type="checkbox" checked={settings.flash_enabled} onChange={(event) => setSettings({ ...settings, flash_enabled: event.target.checked })} /> Flash stream</label>
              <label><input type="checkbox" checked={settings.calendar_enabled} onChange={(event) => setSettings({ ...settings, calendar_enabled: event.target.checked })} /> Calendar stream</label>
              <label><input type="checkbox" checked={settings.quote_enabled} onChange={(event) => setSettings({ ...settings, quote_enabled: event.target.checked })} /> Quote stream</label>
            </fieldset>
            <fieldset className="settings-grid">
              <legend>Cadence & gates</legend>
              <label>Urgent / sec<input type="number" min={15} value={settings.urgent_poll_seconds} onChange={(event) => setSettings({ ...settings, urgent_poll_seconds: Number(event.target.value) })} /></label>
              <label>Normal / sec<input type="number" min={15} value={settings.normal_poll_seconds} onChange={(event) => setSettings({ ...settings, normal_poll_seconds: Number(event.target.value) })} /></label>
              <label>Quiet / sec<input type="number" min={30} value={settings.quiet_poll_seconds} onChange={(event) => setSettings({ ...settings, quiet_poll_seconds: Number(event.target.value) })} /></label>
              <label>Alert score<input type="number" min={0} max={100} value={settings.alert_score_threshold} onChange={(event) => setSettings({ ...settings, alert_score_threshold: Number(event.target.value) })} /></label>
              <label>Model score<input type="number" min={0} max={100} value={settings.model_score_threshold} onChange={(event) => setSettings({ ...settings, model_score_threshold: Number(event.target.value) })} /></label>
              <label>Cooldown / sec<input type="number" min={0} value={settings.cooldown_seconds} onChange={(event) => setSettings({ ...settings, cooldown_seconds: Number(event.target.value) })} /></label>
            </fieldset>
            <fieldset>
              <legend>Research focus</legend>
              <label className="wide-label">Include keywords<textarea value={settings.include_keywords.join(", ")} onChange={(event) => setSettings({ ...settings, include_keywords: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} placeholder="存储, HBM, 资本开支" /></label>
              <label className="wide-label">Exclude keywords<textarea value={settings.exclude_keywords.join(", ")} onChange={(event) => setSettings({ ...settings, exclude_keywords: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} placeholder="体育, 娱乐" /></label>
              <label><input type="checkbox" checked={settings.desktop_notifications} onChange={(event) => toggleNotifications(event.target.checked)} /> Explicit browser notifications</label>
            </fieldset>
            <footer><button className="secondary" onClick={() => setSettingsOpen(false)}>Cancel</button><button disabled={busy === "settings"} onClick={saveSettings}>Save & apply</button></footer>
          </aside>
        </div>
      )}
    </section>
  );
}
