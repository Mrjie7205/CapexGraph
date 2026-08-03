import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  addLiveVerificationSource,
  actOnLiveEvent,
  analyzeLiveEvent,
  attachLiveContextToRun,
  captureLiveVerificationSource,
  createLiveLinkedRun,
  getLiveEvent,
  getLiveSettings,
  getLiveStatus,
  getLiveVerificationTask,
  listLiveAudit,
  listLiveEventPage,
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
import { publishSync, subscribeSync } from "./sync";
import {
  BilingualText,
  humanizeUiValue,
  translateUiValue,
} from "./UiText";

type StreamState = "connecting" | "connected" | "reconnecting";
type AnalyzeProvider = "rules" | "codex_subscription" | "openai";
type SourceScope = "all" | "formal" | "fixture" | "mixed";

const LIVE_EVENT_PAGE_SIZE = 50;

const SOURCE_SCOPE_LABELS = {
  live: ["正式信号", "Live"],
  fixture: ["演示样例", "Fixture"],
  mixed: ["混合谱系", "Mixed"],
} as const;

const HEALTH_LABELS: Record<LiveHealth | "standby", string> = {
  active: "运行中",
  degraded: "服务降级",
  exhausted: "额度暂停",
  not_configured: "等待配置",
  off: "已关闭",
  replay: "样例回放",
  standby: "待命",
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

const SCORE_LABELS = {
  relevance: ["相关性", "Relevance"],
  urgency: ["紧迫性", "Urgency"],
  importance: ["重要性", "Importance"],
  novelty: ["新颖度", "Novelty"],
} as const;

const BRIDGE_MARKETS = [
  { value: "CN", label: "中国 A 股 · CN" },
  { value: "US", label: "美国 · US" },
  { value: "KR", label: "韩国 · KR" },
] as const;

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

function horizonLabel(value: string): string {
  return value
    .replace(/(\d+)-(\d+)\s*weeks?/i, "$1–$2 周")
    .replace(/(\d+)\s*weeks?/i, "$1 周")
    .replace(/(\d+)-(\d+)\s*days?/i, "$1–$2 天")
    .replace(/(\d+)\s*days?/i, "$1 天");
}

function researchPhraseLabel(value: string): string {
  return {
    "aggregator signal": "聚合信号",
    "official-source verification pending": "等待官方来源核验",
    "candidate impact requires human judgment": "候选影响仍需人工判断",
    "This aggregator signal is not Evidence.": "该聚合信号不是事实证据。",
    "Confirm the event against an official issuer, exchange, or regulator source.":
      "请使用公司、交易所或监管机构的官方材料核验该事件。",
  }[value] ?? value;
}

function channelHealth(
  channel: LiveChannel,
  checkpoints: LiveCheckpoint[],
  configured: boolean,
  enabled: boolean,
): { health: LiveHealth | "standby"; freshness?: string; budget?: string } {
  if (!enabled) return { health: "off" };
  if (!configured) return { health: "not_configured" };
  const relevant = checkpoints.filter((item) => item.channel === channel);
  if (relevant.length === 0) {
    return { health: "standby" };
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

export function LiveDesk({ onOpenConnections }: { onOpenConnections?: () => void }) {
  const [status, setStatus] = useState<LiveStatus | null>(null);
  const [events, setEvents] = useState<LiveEventRecord[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [settings, setSettings] = useState<LiveSettings | null>(null);
  const [streamState, setStreamState] = useState<StreamState>("connecting");
  const [category, setCategory] = useState("all");
  const [channel, setChannel] = useState("all");
  const [sourceScope, setSourceScope] = useState<SourceScope>("all");
  const [minScore, setMinScore] = useState("all");
  const [theme, setTheme] = useState("");
  const [entity, setEntity] = useState("");
  const [alertsOnly, setAlertsOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [eventTotal, setEventTotal] = useState(0);
  const [hasMoreEvents, setHasMoreEvents] = useState(false);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [lastEventSync, setLastEventSync] = useState("");
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
  const eventRequestId = useRef(0);
  const loadedEventCount = useRef(LIVE_EVENT_PAGE_SIZE);
  const fetchEventsRef = useRef<(offset?: number, append?: boolean) => Promise<void>>(
    async () => undefined,
  );

  const refreshStatus = useCallback(async () => {
    setStatus(await getLiveStatus());
  }, []);

  const refreshSettings = useCallback(async () => {
    setSettings(await getLiveSettings());
  }, []);

  const fetchEvents = useCallback(async (offset = 0, append = false) => {
    const requestId = ++eventRequestId.current;
    setEventsLoading(true);
    const requestedLimit = append
      ? LIVE_EVENT_PAGE_SIZE
      : Math.max(LIVE_EVENT_PAGE_SIZE, Math.min(200, loadedEventCount.current));
    const params: Record<string, string> = {
      offset: String(offset),
      limit: String(requestedLimit),
      source_scope: sourceScope,
    };
    if (category !== "all") params.category = category;
    if (channel !== "all") params.channel = channel;
    if (minScore !== "all") params.min_score = minScore;
    if (query.trim()) params.q = query.trim();
    if (theme.trim()) params.theme = theme.trim();
    if (entity.trim()) params.entity = entity.trim();
    if (alertsOnly) params.alerts_only = "true";
    try {
      const page = await listLiveEventPage(params);
      if (requestId !== eventRequestId.current) return;
      setEvents((current) => {
        if (!append) {
          loadedEventCount.current = Math.max(page.items.length, LIVE_EVENT_PAGE_SIZE);
          return page.items;
        }
        const merged = new Map(
          [...current, ...page.items].map((item) => [item.signal.signal_key, item]),
        );
        const next = [...merged.values()];
        loadedEventCount.current = Math.max(next.length, LIVE_EVENT_PAGE_SIZE);
        return next;
      });
      setEventTotal(page.total);
      setHasMoreEvents(page.has_more);
      setLastEventSync(new Date().toISOString());
      if (!append) {
        setSelectedKey((current) =>
          page.items.some((item) => item.signal.signal_key === current)
            ? current
            : page.items[0]?.signal.signal_key ?? ""
        );
      }
    } finally {
      if (requestId === eventRequestId.current) setEventsLoading(false);
    }
  }, [alertsOnly, category, channel, entity, minScore, query, sourceScope, theme]);

  useEffect(() => {
    fetchEventsRef.current = fetchEvents;
  }, [fetchEvents]);

  const refreshAll = useCallback(
    async () => {
      await Promise.all([refreshStatus(), refreshSettings(), fetchEvents(0, false)]);
    },
    [fetchEvents, refreshSettings, refreshStatus],
  );

  useEffect(() => {
    Promise.all([refreshStatus(), refreshSettings()]).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "实时台暂不可用");
    });
    const refreshFromSync = () => {
      Promise.all([refreshStatus(), fetchEventsRef.current(0, false)]).catch((reason) => {
        setError(reason instanceof Error ? reason.message : "实时台状态同步失败");
      });
    };
    const unsubscribe = subscribeSync(["connections", "live"], refreshFromSync);
    const statusTimer = window.setInterval(() => {
      refreshStatus().catch(() => undefined);
    }, 15000);
    const eventTimer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        fetchEventsRef.current(0, false).catch(() => undefined);
      }
    }, 30000);
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") refreshFromSync();
    };
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.clearInterval(statusTimer);
      window.clearInterval(eventTimer);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
      unsubscribe();
    };
  }, [refreshSettings, refreshStatus]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      fetchEvents(0, false).catch((reason) => {
        setError(reason instanceof Error ? reason.message : "事件列表刷新失败");
      });
    }, query.trim() || theme.trim() || entity.trim() ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [fetchEvents, query, theme, entity]);

  useEffect(() => {
    const source = new EventSource(liveStreamUrl());
    setStreamState("connecting");
    source.onopen = () => setStreamState("connected");
    source.onerror = () => setStreamState("reconnecting");
    source.addEventListener("live.ready", () => {
      setStreamState("connected");
      fetchEventsRef.current(0, false).catch(() => undefined);
    });
    source.addEventListener("live.signal", (rawEvent) => {
      const message = rawEvent as MessageEvent<string>;
      try {
        const incoming = JSON.parse(message.data) as LiveEventRecord;
        fetchEventsRef.current(0, false).catch(() => undefined);
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

  const selected =
    events.find((item) => item.signal.signal_key === selectedKey) ??
    events[0] ??
    null;
  const hasActiveFilters =
    category !== "all"
    || channel !== "all"
    || sourceScope !== "all"
    || minScore !== "all"
    || Boolean(query.trim())
    || Boolean(theme.trim())
    || Boolean(entity.trim())
    || alertsOnly;
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
      setError(reason instanceof Error ? reason.message : "研究桥暂不可用");
    } finally {
      setBusy("");
    }
  }

  async function doRefresh(action: () => Promise<unknown>, label: string) {
    setBusy(label);
    setError("");
    try {
      await action();
      await refreshAll();
      publishSync("live");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${label} 操作失败`);
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
      await refreshAll();
      await refreshBridge(selected.signal.signal_key);
      publishSync("live");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${label} 操作失败`);
    } finally {
      setBusy("");
    }
  }

  async function openVerificationTask() {
    if (!selected || !bridgeRunId) return;
    if (!window.confirm(
      "确认创建官方来源核验任务？这会新增审计记录并把信号状态推进到“待官方补证”，不会把快讯直接当作证据。",
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
        ? "确认你已人工核对正文、主体和结论？批准后会把哈希匹配的官方材料链接为证据，并生成新的信号版本。"
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
      "确认把当前信号的不可变快照挂接到所选研究？原研究任务的既有结果不会被改写，聚合消息仍标记为二手信号。",
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
        ? "确认从所选研究创建一个新的派生复评？父研究任务将保持完全不变。"
        : "确认以当前信号创建一个新的研究任务？这里只创建研究档案和不可变上下文，不会自动执行模型分析。",
    )) return;
    await bridgeAction(
      async () => {
        const response = await createLiveLinkedRun(selected.signal.id, {
          parent_run_id: asChild ? bridgeRunId : undefined,
          mode: asChild ? undefined : bridgeMode,
          subject: asChild ? undefined : selected.signal.title,
          market: asChild ? undefined : bridgeMarket.trim().toUpperCase(),
          note: asChild
            ? "由实时台创建的派生复评。"
            : "由实时台创建的研究任务。",
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
      await refreshAll();
      publishSync("live");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "实时台设置更新失败");
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
        setError("浏览器未授权桌面提醒；事件仍会留在实时台。");
        return;
      }
    }
    setSettings((current) => current ? { ...current, desktop_notifications: enabled } : current);
  }

  function resetEventFilters() {
    setCategory("all");
    setChannel("all");
    setSourceScope("all");
    setMinScore("all");
    setTheme("");
    setEntity("");
    setAlertsOnly(false);
    setQuery("");
  }

  return (
    <section className="live-desk" id="live">
      <header className="live-mast">
        <div>
          <BilingualText className="live-kicker" zh="实时事件网关 / 市场脉搏" en="Live event gateway" />
          <h2>先发现异动，<em>再证明影响。</em></h2>
          <p>双通道同级运行；聚合快讯只生成研究优先级，不是事实证据，更不是交易指令。</p>
        </div>
        <div className="live-operations">
          <div className={`channel-chip ${mcp.health}`}>
            <i />
            <span>金十 MCP<small>{HEALTH_LABELS[mcp.health]} · {mcp.budget ?? "等待首轮轮询"}<em>{humanizeUiValue(mcp.health)}</em></small></span>
          </div>
          <div className={`channel-chip ${websocket.health}`}>
            <i />
            <span>实时推送<small>{HEALTH_LABELS[websocket.health]} · {formatTime(websocket.freshness)}<em>WebSocket · {humanizeUiValue(websocket.health)}</em></small></span>
          </div>
          <div className={`channel-chip stream-${streamState}`}>
            <i />
            <span>页面事件流<small>{translateUiValue(streamState)}<em>Live Desk SSE · {streamState}</em></small></span>
          </div>
          <div className="live-buttons">
            <button
              disabled={Boolean(busy)}
              onClick={() => doRefresh(() => setLiveMonitor(!status?.running), "monitor")}
            >
              <BilingualText
                zh={status?.running ? "停止监控" : "启动监控"}
                en={status?.running ? "Stop monitor" : "Start monitor"}
                compact
                align="center"
              />
            </button>
            <button className="connection-button" onClick={onOpenConnections}><BilingualText zh="连接中心" en="Connections" compact align="center" /></button>
            <button onClick={() => setSettingsOpen(true)}><BilingualText zh="设置" en="Settings" compact align="center" /></button>
          </div>
        </div>
      </header>

      <div className="live-tape" aria-label="实时覆盖指标">
        <article><BilingualText zh="规范化信号" en="Canonical signals" /><strong>{status?.coverage.total_signals ?? 0}</strong><small>{status?.unread_alerts ?? 0} 条未读提醒</small></article>
        <article><BilingualText zh="跨通道重合率" en="Cross-channel overlap" /><strong>{((status?.coverage.overlap_ratio ?? 0) * 100).toFixed(0)}%</strong><small>{status?.coverage.matched ?? 0} 条匹配 · {status?.coverage.divergent ?? 0} 条有差异</small></article>
        <article><BilingualText zh="送达延迟 P50 / P95" en="Delivery P50 / P95" /><strong>{seconds(status?.coverage.delivery_delay_p50_seconds)}</strong><small>尾部延迟 {seconds(status?.coverage.delivery_delay_p95_seconds)}</small></article>
        <article><BilingualText zh="运行状态" en="Runtime" /><strong>{status?.running ? "开启" : "关闭"}</strong><small>{status?.running ? `启动于 ${formatTime(status.started_at)}` : "仍可人工查看已有事件"}</small></article>
      </div>

      {error && <div className="live-error"><strong>实时台操作未完成</strong><small>{error}</small></div>}

      <div className="live-console">
        <aside className="signal-feed">
          <div className="live-panel-head">
            <BilingualText zh="信号台账" en="Signal ledger" compact />
            <b>
              <span>{events.length} / {eventTotal}</span>
              <small>已加载 / total</small>
            </b>
          </div>
          <div className="feed-filters">
            <input aria-label="搜索事件" placeholder="搜索事件…" value={query} onChange={(event) => setQuery(event.target.value)} />
            <select aria-label="事件类型" value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="all">全部类型</option><option value="flash">快讯</option><option value="calendar">日历</option><option value="quote">行情</option><option value="news">资讯</option><option value="other">其他</option>
            </select>
            <select aria-label="采集通道" value={channel} onChange={(event) => setChannel(event.target.value)}>
              <option value="all">全部通道</option><option value="mcp">MCP 轮询</option><option value="websocket">实时推送 · WebSocket</option>
            </select>
          </div>
          <div className="feed-priority-filters">
            <select aria-label="数据来源" value={sourceScope} onChange={(event) => setSourceScope(event.target.value as SourceScope)}>
              <option value="all">正式 + 演示</option><option value="formal">仅正式信号</option><option value="fixture">仅演示样例</option><option value="mixed">混合谱系</option>
            </select>
            <select aria-label="最低规则评分" value={minScore} onChange={(event) => setMinScore(event.target.value)}>
              <option value="all">全部评分</option><option value="50">50 分以上</option><option value="65">65 分以上</option><option value="80">80 分以上</option>
            </select>
            <input aria-label="主题筛选" placeholder="主题…" value={theme} onChange={(event) => setTheme(event.target.value)} />
            <input aria-label="实体筛选" placeholder="公司 / 实体…" value={entity} onChange={(event) => setEntity(event.target.value)} />
            <label className="alert-filter">
              <input type="checkbox" checked={alertsOnly} onChange={(event) => setAlertsOnly(event.target.checked)} />
              <span>仅提醒<small>Alerts</small></span>
            </label>
            <button type="button" onClick={resetEventFilters} disabled={!hasActiveFilters}>重置<small>Reset</small></button>
          </div>
          <div className="feed-actions">
            <button disabled={Boolean(busy)} onClick={() => doRefresh(() => pollLiveStream("flash"), "poll-flash")}><BilingualText zh="轮询快讯" en="Poll flash" compact align="center" /></button>
            <button disabled={Boolean(busy)} onClick={() => doRefresh(() => pollLiveStream("calendar"), "poll-calendar")}><BilingualText zh="轮询日历" en="Poll calendar" compact align="center" /></button>
            <button disabled={eventsLoading} onClick={() => fetchEvents(0, false).catch((reason) => setError(reason instanceof Error ? reason.message : "事件列表刷新失败"))}>
              <BilingualText zh={eventsLoading ? "同步中" : "刷新列表"} en="Refresh feed" compact align="center" />
            </button>
          </div>
          <div className="signal-list">
            {events.map((item) => (
              <button
                key={item.signal.signal_key}
                className={selected?.signal.signal_key === item.signal.signal_key ? "selected" : ""}
                onClick={() => setSelectedKey(item.signal.signal_key)}
              >
                <div className="signal-stamp">
                  <time>{formatTime(item.signal.last_observed_at)}</time>
                  <span className="signal-states">
                    <em className={`source-scope ${item.source_scope}`}>
                      {SOURCE_SCOPE_LABELS[item.source_scope][0]}
                      <small>{SOURCE_SCOPE_LABELS[item.source_scope][1]}</small>
                    </em>
                    <i className={item.signal.match_status}>{translateUiValue(item.signal.match_status)}<small>{humanizeUiValue(item.signal.match_status)}</small></i>
                  </span>
                </div>
                <strong>{item.signal.title}</strong>
                <div className="signal-tags">
                  <span>{translateUiValue(item.signal.category)}<small>{item.signal.category}</small></span>
                  {item.signal.channels.map((source) => <i key={source}>{translateUiValue(source)}<small>{source}</small></i>)}
                  {item.assessment?.matched_themes.slice(0, 2).map((theme) => <em key={theme}>{theme}</em>)}
                  <em className={`verification-${item.signal.verification_state}`}>
                    {translateUiValue(item.signal.verification_state)}
                    <small>{humanizeUiValue(item.signal.verification_state)}</small>
                  </em>
                  <b>{item.assessment?.total_score.toFixed(0) ?? "—"}</b>
                </div>
              </button>
            ))}
            {eventsLoading && events.length === 0 && (
              <div className="live-empty loading">
                <strong>正在同步事件台账</strong>
                <p>从本机后端读取最新规范化信号与筛选结果。</p>
              </div>
            )}
            {!eventsLoading && events.length === 0 && (
              <div className="live-empty">
                <strong>{hasActiveFilters ? "没有符合条件的事件" : "还没有实时事件"}</strong>
                <p>{hasActiveFilters ? "放宽评分、主题、实体或来源条件后再查看。" : "配置 MCP 后可正式轮询；也可以先加载冻结双通道样例验证完整路径。"}</p>
                {hasActiveFilters
                  ? <button onClick={resetEventFilters}>清除全部筛选<small>Clear filters</small></button>
                  : <button disabled={Boolean(busy)} onClick={() => doRefresh(replayLiveDemo, "demo")}><BilingualText zh="加载免密钥回放" en="Load no-key replay" compact align="center" /></button>}
              </div>
            )}
            {events.length > 0 && (
              <div className="feed-pagination">
                <span>
                  已加载 {events.length} / {eventTotal}
                  <small>最近同步 {formatTime(lastEventSync)}</small>
                </span>
                {hasMoreEvents && (
                  <button
                    disabled={eventsLoading}
                    onClick={() => fetchEvents(events.length, true).catch((reason) => setError(reason instanceof Error ? reason.message : "加载更多失败"))}
                  >
                    {eventsLoading ? "加载中…" : "加载更多"}<small>Load more</small>
                  </button>
                )}
              </div>
            )}
          </div>
        </aside>

        <article className="signal-detail">
          <div className="live-panel-head">
            <BilingualText zh="影响简报" en="Impact brief" compact />
            <b>{selected
              ? <><span>{translateUiValue(selected.signal.verification_state)}</span><small>{humanizeUiValue(selected.signal.verification_state)}</small></>
              : <><span>暂无信号</span><small>No signal</small></>}</b>
          </div>
          {selected ? (
            <>
              <div className="detail-lead">
                <div className="detail-score">
                  <strong>{selected.assessment?.total_score.toFixed(0) ?? "—"}</strong>
                  <span>规则评分 / 100<small>rules score</small></span>
                </div>
                <div>
                  <span className="detail-overline">
                    {SOURCE_SCOPE_LABELS[selected.source_scope][0]} · {translateUiValue(selected.signal.category)} · V{selected.signal.version} · {translateUiValue(selected.signal.match_status)}
                    <small>{SOURCE_SCOPE_LABELS[selected.source_scope][1]} · {selected.signal.category} · {humanizeUiValue(selected.signal.match_status)}</small>
                  </span>
                  <h3>{selected.signal.title}</h3>
                  <p className="trust-notice">
                    聚合消息仍属于二手线索，并非事实证据。只有单独列出的已审核官方材料，才能支持研究结论。
                    <small>{selected.trust_notice}</small>
                  </p>
                </div>
              </div>

              <div className="score-ruler">
                {(["relevance", "urgency", "importance"] as const).map((metric) => (
                  <div key={metric}>
                    <span>{SCORE_LABELS[metric][0]}<small>{SCORE_LABELS[metric][1]}</small></span>
                    <i><b style={{ width: `${selected.assessment?.[metric] ?? 0}%` }} /></i>
                    <strong>{selected.assessment?.[metric].toFixed(0) ?? "—"}</strong>
                  </div>
                ))}
                <div><span>{SCORE_LABELS.novelty[0]}<small>{SCORE_LABELS.novelty[1]}</small></span><i><b style={{ width: `${(selected.assessment?.novelty ?? 0) * 100}%` }} /></i><strong>{((selected.assessment?.novelty ?? 0) * 100).toFixed(0)}</strong></div>
              </div>

              <div className="lineage">
                <div className="detail-section-title"><BilingualText zh="通道谱系" en="Channel lineage" compact /><b>{selected.observations.length} 条观测<small>Observations</small></b></div>
                {selected.observations.map((observation) => (
                  <div className="lineage-row" key={observation.id}>
                    <span className={`channel-mark ${observation.channel}`}>{translateUiValue(observation.channel)}<small>{observation.channel}</small></span>
                    <div><strong>{observation.provider} / {observation.stream}</strong><small>发布 {formatTime(observation.published_at)} · 观测 {formatTime(observation.observed_at)}</small></div>
                    <i>{translateUiValue(observation.retention_class)}<small>{humanizeUiValue(observation.retention_class)}</small></i>
                  </div>
                ))}
              </div>

              <div className="impact-analysis">
                <div className="detail-section-title">
                  <BilingualText zh="条件化影响" en="Conditional impact" compact />
                  <b>{selected.analysis
                    ? <><span>{translateUiValue(selected.analysis.status)}</span><small>{humanizeUiValue(selected.analysis.status)}</small></>
                    : <><span>尚未运行</span><small>Not run</small></>}</b>
                </div>
                {selected.proposal ? (
                  <>
                    <p className="analysis-cost">
                      分析谱系 · {selected.analysis?.model_provider ?? "规则引擎"} · 调用 {selected.analysis?.model_call_count ?? 0} 次 · {translateUiValue(selected.analysis?.cost_status ?? "not_applicable")}
                      <small>analysis lineage · {selected.analysis?.model_provider ?? "rules"} · {selected.analysis?.cost_status ?? "not_applicable"}</small>
                    </p>
                    <div className="impact-axis">
                      <div><small>方向<em>Direction</em></small><strong>{translateUiValue(selected.proposal.direction)}<small>{humanizeUiValue(selected.proposal.direction)}</small></strong></div>
                      <div><small>时间跨度<em>Horizon</em></small><strong>{horizonLabel(selected.proposal.horizon)}<small>{selected.proposal.horizon}</small></strong></div>
                      <div><small>置信度<em>Confidence</em></small><strong>{(selected.proposal.confidence * 100).toFixed(0)}%</strong></div>
                      <div><small>下一步<em>Next action</em></small><strong>{translateUiValue(selected.proposal.recommended_action)}<small>{humanizeUiValue(selected.proposal.recommended_action)}</small></strong></div>
                    </div>
                    <ol className="transmission-path">
                      {selected.proposal.transmission_path.map((step, index) => (
                        <li key={`${step}-${index}`}>
                          <span>{String(index + 1).padStart(2, "0")}</span>
                          <BilingualText
                            zh={researchPhraseLabel(step)}
                            en={researchPhraseLabel(step) === step ? undefined : step}
                            compact
                          />
                        </li>
                      ))}
                    </ol>
                    <div className="gap-note"><BilingualText zh="证据缺口" en="Evidence gaps" compact />{selected.proposal.evidence_gaps.map((gap) => <p key={gap}>— {researchPhraseLabel(gap)}{researchPhraseLabel(gap) !== gap && <small>{gap}</small>}</p>)}</div>
                    {selected.analysis?.failure && <div className="analysis-failure">{selected.analysis.failure}</div>}
                  </>
                ) : (
                  <p className="detail-placeholder">规则评分已完成。按需运行影响分析，低分事件不会自动产生模型费用。</p>
                )}
              </div>

              <div className="decision-bar">
                <select value={analysisProvider} onChange={(event) => setAnalysisProvider(event.target.value as AnalyzeProvider)}>
                  <option value="rules">仅规则分析 · 无需密钥</option>
                  <option value="codex_subscription">Codex 订阅 · 本机</option>
                  <option value="openai">OpenAI API · 按量计费</option>
                </select>
                <button disabled={Boolean(busy)} onClick={runAnalysis}>分析影响<small>Analyze impact</small></button>
                <button disabled={Boolean(busy)} onClick={() => eventAction("watch")}>加入观察<small>Watch</small></button>
                <button disabled={Boolean(busy)} onClick={showResearchBridge}>研究桥<small>Research bridge</small></button>
                <button disabled={Boolean(busy)} onClick={() => eventAction("dismiss")}>忽略<small>Dismiss</small></button>
                <button disabled={Boolean(busy)} onClick={() => eventAction("mute")}>静默<small>Mute</small></button>
              </div>
            </>
          ) : (
            <div className="live-empty detail-empty"><strong>选择一条信号</strong><p>这里会呈现合流谱系、确定性评分、影响路径、证据缺口和人工动作。</p></div>
          )}
        </article>

        <aside className="coverage-rail">
          <div className="live-panel-head"><BilingualText zh="覆盖审计" en="Coverage audit" compact /><b>实时<small>Live</small></b></div>
          <div className="coverage-dial" style={{ "--coverage": `${(status?.coverage.overlap_ratio ?? 0) * 360}deg` } as React.CSSProperties}>
            <div><strong>{((status?.coverage.overlap_ratio ?? 0) * 100).toFixed(0)}%</strong><span>重合率<small>overlap</small></span></div>
          </div>
          <dl className="coverage-list">
            <div><dt>仅 MCP<small>MCP only</small></dt><dd>{status?.coverage.mcp_only ?? 0}</dd></div>
            <div><dt>仅推送<small>WS only</small></dt><dd>{status?.coverage.websocket_only ?? 0}</dd></div>
            <div><dt>双通道匹配<small>Matched</small></dt><dd>{status?.coverage.matched ?? 0}</dd></div>
            <div><dt>通道有差异<small>Divergent</small></dt><dd>{status?.coverage.divergent ?? 0}</dd></div>
            <div><dt>P95 延迟<small>P95 delay</small></dt><dd>{seconds(status?.coverage.delivery_delay_p95_seconds)}</dd></div>
          </dl>
          <div className="rail-note">
            <BilingualText zh="指标解读" en="Interpretation" compact />
            <p>通道覆盖率衡量发现能力，不证明消息正确。字段差异会保留为“通道有差异”，不会被静默覆盖。</p>
          </div>
          <div className="rail-note safety">
            <BilingualText zh="证据防火墙" en="Evidence firewall" compact />
            <p>任何聚合信号都不能自动提升供应链关系置信度。官方材料捕获与人工审核仍是必经步骤。</p>
          </div>
          <div className={`rail-note soak ${status?.latest_soak?.passed ? "passed" : ""}`}>
            <BilingualText zh="发布门禁" en="Release gate" compact />
            <p>
              {status?.latest_soak
                ? `${status.latest_soak.passed ? "通过" : "未通过"} · ${translateUiValue(status.latest_soak.mode)} · ${status.latest_soak.cycles} 轮`
                : "尚无本机浸泡测试报告；请运行 capexgraph live soak。"}
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
            aria-label="研究桥"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <BilingualText zh="证据防火墙 / M7" en="Evidence firewall" compact />
                <h3>研究桥<small>Research Bridge</small></h3>
                <p>{selected.signal.title}</p>
              </div>
              <button aria-label="关闭研究桥" onClick={() => setBridgeOpen(false)}>×</button>
            </header>

            <p className="bridge-notice">
              这里把“值得核验的二手信号”推进为“可审计的研究输入”。每个写入动作都需要确认；
              只有监管机构或公司官方材料经捕获、哈希校验和人工批准后，才会成为证据。
            </p>

            <div className="bridge-progress" aria-label={`研究桥第 ${bridgeStage} 阶段`}>
              {[
                ["01", "二手线索", "Signal"],
                ["02", "官方候选", "Official source"],
                ["03", "人工审核", "Human review"],
                ["04", "不可变复评", "Linked run"],
              ].map(([number, label, english], index) => (
                <div
                  className={bridgeStage > index ? "complete" : bridgeStage === index ? "active" : ""}
                  key={number}
                >
                  <b>{number}</b>
                  <span>{label}</span>
                  <small>{english}</small>
                </div>
              ))}
            </div>

            <section className="bridge-block">
              <div className="bridge-block-head">
                <div><BilingualText zh="研究档案" en="Research file" compact /><h4>选择承接研究，或新建独立档案</h4></div>
                <b>{linkedContexts.length} 个已链接快照<small>Linked snapshots</small></b>
              </div>
              <div className="bridge-run-controls">
                <label>
                  已有研究<small>Existing run</small>
                  <select value={bridgeRunId} onChange={(event) => setBridgeRunId(event.target.value)}>
                    <option value="">请选择研究任务</option>
                    {bridgeRuns.map((run) => (
                      <option value={run.id} key={run.id}>
                        {translateUiValue(run.mode)} · {run.subject} · {run.id.slice(-8)}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  disabled={!bridgeRunId || Boolean(busy)}
                  onClick={attachToExistingRun}
                >
                  挂接不可变快照<small>Attach snapshot</small>
                </button>
                <button
                  disabled={!bridgeRunId || Boolean(busy)}
                  onClick={() => createBridgeRun(true)}
                >
                  从所选研究派生复评<small>Derived re-evaluation</small>
                </button>
              </div>
              <div className="bridge-new-run">
                <label>
                  新建类型<small>Run type</small>
                  <select value={bridgeMode} onChange={(event) => setBridgeMode(event.target.value as RunMode)}>
                    <option value="theme">主题扫描 · Theme Scan</option>
                    <option value="anchor">锚点扫描 · Anchor Scan</option>
                  </select>
                </label>
                <label>
                  市场<small>Market</small>
                  <select value={bridgeMarket} onChange={(event) => setBridgeMarket(event.target.value)}>
                    {BRIDGE_MARKETS.map((option) => (
                      <option value={option.value} key={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <button disabled={Boolean(busy)} onClick={() => createBridgeRun(false)}>
                  新建链接研究<small>Create linked run</small>
                </button>
              </div>
              {linkedRun && (
                <div className="bridge-result">
                  <span>最新链接研究<small>Latest linked run</small></span>
                  <strong>{linkedRun.run.id}</strong>
                  <small>
                    上下文 {linkedRun.link.context_hash.slice(0, 12)}… ·
                    {linkedRun.link.parent_run_id ? " 父研究已保留" : " 新研究档案"}
                  </small>
                </div>
              )}
            </section>

            <section className="bridge-block verification-workflow">
              <div className="bridge-block-head">
                <div><BilingualText zh="官方来源任务" en="Official-source task" compact /><h4>补证队列</h4></div>
                <b>{activeTask
                  ? <>{TASK_LABELS[activeTask.status]}<small>{humanizeUiValue(activeTask.status)}</small></>
                  : <>尚未创建<small>Not open</small></>}</b>
              </div>

              {!activeTask ? (
                <div className="bridge-empty-action">
                  <p>先选择一个研究任务。创建任务只改变核验状态并留下审计记录，不会自动支持任何事实结论。</p>
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
                      研究 {activeTask.run_id?.slice(-10) ?? "尚未链接"} ·
                      尝试 {activeTask.attempts} 次 · 更新于 {formatTime(activeTask.updated_at)}
                    </small>
                    {activeTask.error && <p>{activeTask.error}</p>}
                  </div>

                  {taskRecord?.source_suggestion && (
                    <div className="official-source-card">
                      <span>
                        {translateUiValue(taskRecord.source_suggestion.authority)} · {translateUiValue(taskRecord.source_suggestion.status)}
                        <small>{humanizeUiValue(taskRecord.source_suggestion.authority)} · {humanizeUiValue(taskRecord.source_suggestion.status)}</small>
                      </span>
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
                      <p>捕获会保存规范化正文与来源哈希；完成后仍需你人工核对。</p>
                      <button disabled={Boolean(busy)} onClick={captureOfficialSource}>
                        {activeTask.status === "failed" ? "重试受保护捕获" : "捕获并生成待审证据"}
                      </button>
                    </div>
                  )}

                  {activeTask.status === "captured" && (
                    <div className="review-gate">
                      <div>
                        <span>需要人工审核<small>Human review required</small></span>
                        <strong>{taskRecord?.evidence?.title ?? activeTask.evidence_id}</strong>
                        <p>请打开并核对捕获材料。批准会原子化完成证据链接；拒绝不会留下可引用关系。</p>
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
                        <span>已链接审核通过的证据<small>Reviewed Evidence linked</small></span>
                        <strong>{taskRecord?.evidence?.title ?? activeTask.evidence_id}</strong>
                        <small>
                          链接哈希 {taskRecord?.evidence_link?.link_hash.slice(0, 16)}… ·
                          来源哈希 {taskRecord?.evidence_link?.source_hash.slice(0, 16)}…
                        </small>
                      </div>
                    </div>
                  )}
                </>
              )}
            </section>

            <section className="bridge-block audit-block">
              <div className="bridge-block-head">
                <div><BilingualText zh="不可变审计" en="Immutable audit" compact /><h4>事件时间线</h4></div>
                <b>{audit.length} 条记录<small>Entries</small></b>
              </div>
              <ol>
                {audit.slice().reverse().map((entry, index) => (
                  <li key={`${entry.event_type}-${entry.object_id}-${entry.id ?? index}`}>
                    <time>{formatTime(entry.occurred_at)}</time>
                    <div>
                      <span>{translateUiValue(entry.event_type)} · {entry.actor}<small>{entry.event_type}</small></span>
                      <strong>{entry.summary}</strong>
                      <small>{translateUiValue(entry.object_type)} / {entry.object_id}</small>
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
          <aside className="live-settings" role="dialog" aria-modal="true" aria-label="实时台设置" onMouseDown={(event) => event.stopPropagation()}>
            <header><div><BilingualText zh="网关控制" en="Gateway controls" compact /><h3>实时台设置<small>Live Desk settings</small></h3></div><button aria-label="关闭实时台设置" onClick={() => setSettingsOpen(false)}>×</button></header>
            <p className="settings-notice">
              本面板只调整运行策略；访问令牌、推送密钥和 Codex 登录由
              <button type="button" onClick={() => { setSettingsOpen(false); onOpenConnections?.(); }}>连接中心</button>
              一次性提交给本机后端，前端不会回显或保存。
            </p>
            <fieldset>
              <legend>同等优先级通道<small>Equal-priority channels</small></legend>
              <label><input type="checkbox" checked={settings.mcp_enabled} onChange={(event) => setSettings({ ...settings, mcp_enabled: event.target.checked })} /> MCP 自适应轮询<small>MCP adaptive polling</small></label>
              <label><input type="checkbox" checked={settings.websocket_enabled} onChange={(event) => setSettings({ ...settings, websocket_enabled: event.target.checked })} /> WebSocket 实时推送<small>WebSocket push</small></label>
              <label><input type="checkbox" checked={settings.flash_enabled} onChange={(event) => setSettings({ ...settings, flash_enabled: event.target.checked })} /> 快讯流<small>Flash stream</small></label>
              <label><input type="checkbox" checked={settings.calendar_enabled} onChange={(event) => setSettings({ ...settings, calendar_enabled: event.target.checked })} /> 财经日历流<small>Calendar stream</small></label>
              <label><input type="checkbox" checked={settings.quote_enabled} onChange={(event) => setSettings({ ...settings, quote_enabled: event.target.checked })} /> 行情流<small>Quote stream</small></label>
            </fieldset>
            <fieldset className="settings-grid">
              <legend>轮询节奏与门槛<small>Cadence & gates</small></legend>
              <label>紧急间隔 / 秒<small>Urgent / sec</small><input type="number" min={15} value={settings.urgent_poll_seconds} onChange={(event) => setSettings({ ...settings, urgent_poll_seconds: Number(event.target.value) })} /></label>
              <label>常规间隔 / 秒<small>Normal / sec</small><input type="number" min={15} value={settings.normal_poll_seconds} onChange={(event) => setSettings({ ...settings, normal_poll_seconds: Number(event.target.value) })} /></label>
              <label>静默间隔 / 秒<small>Quiet / sec</small><input type="number" min={30} value={settings.quiet_poll_seconds} onChange={(event) => setSettings({ ...settings, quiet_poll_seconds: Number(event.target.value) })} /></label>
              <label>提醒分数线<small>Alert score</small><input type="number" min={0} max={100} value={settings.alert_score_threshold} onChange={(event) => setSettings({ ...settings, alert_score_threshold: Number(event.target.value) })} /></label>
              <label>模型分数线<small>Model score</small><input type="number" min={0} max={100} value={settings.model_score_threshold} onChange={(event) => setSettings({ ...settings, model_score_threshold: Number(event.target.value) })} /></label>
              <label>冷却时间 / 秒<small>Cooldown / sec</small><input type="number" min={0} value={settings.cooldown_seconds} onChange={(event) => setSettings({ ...settings, cooldown_seconds: Number(event.target.value) })} /></label>
            </fieldset>
            <fieldset>
              <legend>研究焦点<small>Research focus</small></legend>
              <label className="wide-label">纳入关键词<small>Include keywords</small><textarea value={settings.include_keywords.join(", ")} onChange={(event) => setSettings({ ...settings, include_keywords: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} placeholder="存储, HBM, 资本开支" /></label>
              <label className="wide-label">排除关键词<small>Exclude keywords</small><textarea value={settings.exclude_keywords.join(", ")} onChange={(event) => setSettings({ ...settings, exclude_keywords: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} placeholder="体育, 娱乐" /></label>
              <label><input type="checkbox" checked={settings.desktop_notifications} onChange={(event) => toggleNotifications(event.target.checked)} /> 浏览器桌面提醒<small>Explicit browser notifications</small></label>
            </fieldset>
            <footer><button className="secondary" onClick={() => setSettingsOpen(false)}>取消<small>Cancel</small></button><button disabled={busy === "settings"} onClick={saveSettings}>保存并应用<small>Save & apply</small></button></footer>
          </aside>
        </div>
      )}
    </section>
  );
}
