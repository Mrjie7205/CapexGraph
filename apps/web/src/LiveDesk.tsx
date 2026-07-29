import { useEffect, useMemo, useState } from "react";
import {
  actOnLiveEvent,
  analyzeLiveEvent,
  getLiveCoverage,
  getLiveSettings,
  getLiveStatus,
  listLiveEvents,
  liveStreamUrl,
  patchLiveSettings,
  pollLiveStream,
  replayLiveDemo,
  setLiveMonitor,
  type LiveChannel,
  type LiveCheckpoint,
  type LiveEventRecord,
  type LiveHealth,
  type LiveSettings,
  type LiveStatus,
  type Provider,
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

  async function eventAction(action: "dismiss" | "mute" | "watch" | "verify") {
    if (!selected) return;
    await doRefresh(() => actOnLiveEvent(selected.signal.id, action), action);
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
                <button disabled={Boolean(busy)} onClick={() => eventAction("verify")}>Verify</button>
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
        </aside>
      </div>

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
