import { useEffect, useMemo, useState } from "react";
import {
  decideMainlineProposal,
  importMainlineDemo,
  listMainlineAssessments,
  listMainlineJobs,
  listMainlineMetrics,
  listMainlinePolicies,
  listMainlineProposals,
  listOfficialSourceCapabilities,
  listThemeMemberships,
  listThemes,
  listThemeSources,
  runMainlineMonitor,
  syncMarketHistory,
  type MainlineAssessmentRecord,
  type MainlineMetric,
  type MainlinePolicy,
  type MonitorJob,
  type OfficialSourceCapability,
  type ThemeDefinition,
  type ThemeMembership,
  type ThemeResearchProposal,
  type ThemeSource,
} from "./api";
import { BilingualText, translateUiValue } from "./UiText";

type MarketProvider = "fixture-market" | "eodhd" | "tushare" | "yahoo";

interface MainlineDeskProps {
  onError: (message: string) => void;
}

function pct(value?: number): string {
  return value === undefined || value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function stateLabel(value?: string): string {
  const labels: Record<string, string> = {
    none: "无历史状态",
    insufficient: "数据不足",
    watch: "观察",
    emerging: "形成中",
    confirmed: "已确认",
    fragile: "转弱",
    exited: "退出",
  };
  return value ? labels[value] ?? translateUiValue(value) : "尚未评估";
}

function mainlineMessageZh(value: string): string {
  const metricPatterns: Array<[RegExp, string]> = [
    [/^20-session relative strength: (.+)$/i, "20日相对强度：$1"],
    [/^breadth above 20-session average: (.+)$/i, "站上20日均线的成分宽度：$1"],
    [/^positive participation: (.+)$/i, "上涨成分参与度：$1"],
    [/^point-in-time coverage: (.+)$/i, "点时数据覆盖率：$1"],
  ];
  for (const [pattern, replacement] of metricPatterns) {
    if (pattern.test(value)) return value.replace(pattern, replacement);
  }
  if (value === "Theme membership coverage is explicitly partial.") {
    return "主题成分历史覆盖被明确标记为不完整。";
  }
  const transition = value.match(
    /^Mainline state changed from (.+) to (.+); explicit confirmation is required\.$/i,
  );
  if (transition) {
    return `主线状态由${stateLabel(transition[1])}变为${stateLabel(transition[2])}；后续研究必须人工确认。`;
  }
  return value;
}

export function MainlineDesk({ onError }: MainlineDeskProps) {
  const [themes, setThemes] = useState<ThemeDefinition[]>([]);
  const [themeId, setThemeId] = useState("");
  const [market, setMarket] = useState("CN");
  const [asOf, setAsOf] = useState(new Date().toISOString().slice(0, 10));
  const [provider, setProvider] = useState<MarketProvider>("fixture-market");
  const [sources, setSources] = useState<ThemeSource[]>([]);
  const [memberships, setMemberships] = useState<ThemeMembership[]>([]);
  const [metrics, setMetrics] = useState<MainlineMetric[]>([]);
  const [assessments, setAssessments] = useState<MainlineAssessmentRecord[]>([]);
  const [jobs, setJobs] = useState<MonitorJob[]>([]);
  const [proposals, setProposals] = useState<ThemeResearchProposal[]>([]);
  const [policies, setPolicies] = useState<MainlinePolicy[]>([]);
  const [officialSources, setOfficialSources] = useState<OfficialSourceCapability[]>([]);
  const [busy, setBusy] = useState("");

  const theme = themes.find((item) => item.theme_id === themeId);

  async function refreshCatalog(selectTheme?: string) {
    const [themeItems, policyItems, officialItems] = await Promise.all([
      listThemes(),
      listMainlinePolicies(),
      listOfficialSourceCapabilities(),
    ]);
    setThemes(themeItems);
    setPolicies(policyItems);
    setOfficialSources(officialItems);
    const next = selectTheme || themeId || themeItems[0]?.theme_id || "";
    if (next) setThemeId(next);
  }

  async function refreshTheme() {
    if (!themeId || !asOf) return;
    const [sourceItems, memberItems, metricItems, assessmentItems, jobItems, proposalItems] =
      await Promise.all([
        listThemeSources(themeId),
        listThemeMemberships(themeId, asOf, market),
        listMainlineMetrics(themeId, market),
        listMainlineAssessments(themeId),
        listMainlineJobs(),
        listMainlineProposals(themeId),
      ]);
    setSources(sourceItems);
    setMemberships(memberItems);
    setMetrics(metricItems);
    setAssessments(assessmentItems);
    setJobs(jobItems.filter((item) => item.theme_id === themeId && item.market === market));
    setProposals(proposalItems);
  }

  useEffect(() => {
    refreshCatalog().catch((reason) => {
      onError(reason instanceof Error ? reason.message : "主线监控目录读取失败");
    });
  }, []);

  useEffect(() => {
    refreshTheme().catch((reason) => {
      onError(reason instanceof Error ? reason.message : "主题监控数据读取失败");
    });
  }, [themeId, market, asOf]);

  useEffect(() => {
    if (provider === "tushare" && market !== "CN") setProvider("eodhd");
  }, [market]);

  const memberRows = useMemo(() => {
    const grouped = new Map<string, ThemeMembership[]>();
    memberships.forEach((item) => {
      grouped.set(item.ticker, [...(grouped.get(item.ticker) ?? []), item]);
    });
    return [...grouped.entries()].map(([ticker, records]) => ({
      ticker,
      name: records[0].entity_name,
      role: records[0].role,
      recognition: Math.max(...records.map((item) => item.recognition_score)),
      exposure: Math.max(
        ...records.map((item) => item.exposure_score ?? -1),
      ),
      sourceCount: new Set(records.map((item) => item.source_id)).size,
    }));
  }, [memberships]);

  const latestMetric = metrics[0];
  const latestAssessment = assessments[0];
  const latestJob = jobs[0];
  const activePolicy = policies.find((item) => item.id === latestAssessment?.policy_id) ?? policies[0];

  async function loadDemo() {
    setBusy("demo");
    onError("");
    try {
      await importMainlineDemo();
      setAsOf("2026-08-03");
      setMarket("CN");
      setProvider("fixture-market");
      await refreshCatalog("memory-semiconductors");
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "示例数据加载失败");
    } finally {
      setBusy("");
    }
  }

  async function syncBars() {
    if (!theme || provider === "fixture-market") return;
    const benchmark = theme.benchmark_tickers[market];
    const tickers = [...new Set([...memberRows.map((item) => item.ticker), benchmark])].filter(
      Boolean,
    );
    if (!tickers.length) {
      onError("当前历史截面没有可同步的股票或基准。");
      return;
    }
    setBusy("sync");
    onError("");
    try {
      await syncMarketHistory(tickers, provider, 500);
      await refreshTheme();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "行情同步失败");
    } finally {
      setBusy("");
    }
  }

  async function runMonitor() {
    if (!themeId) return;
    setBusy("run");
    onError("");
    try {
      await runMainlineMonitor({
        theme_id: themeId,
        market,
        as_of_date: asOf,
        provider,
      });
      await refreshCatalog(themeId);
      await refreshTheme();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "主线评估失败");
    } finally {
      setBusy("");
    }
  }

  async function decide(proposalId: string, accepted: boolean) {
    setBusy(proposalId);
    onError("");
    try {
      await decideMainlineProposal(proposalId, accepted);
      await refreshTheme();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "研究提案处理失败");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="mainline-desk" id="mainline">
      <header className="mainline-mast">
        <div>
          <span className="mainline-kicker">DAILY REGIME / POINT-IN-TIME</span>
          <h2>主线雷达</h2>
          <p>先判断主题是否仍在主线，再把官方事件和瓶颈研究送入人工确认队列。</p>
        </div>
        <div className="mainline-state-card">
          <small>当前判断 · CURRENT STATE</small>
          <strong className={`state-${latestAssessment?.state ?? "empty"}`}>
            {stateLabel(latestAssessment?.state)}
          </strong>
          <span>
            {latestAssessment?.score === undefined
              ? "评分待生成"
              : `${latestAssessment.score.toFixed(1)} / 100`}
          </span>
          <i>
            {!activePolicy
              ? "政策信息待加载"
              : activePolicy.experimental
                ? "实验政策 · 尚未批准为投资规则"
                : "已批准政策"}
          </i>
        </div>
      </header>

      <div className="mainline-controls">
        <label>
          <BilingualText zh="主题" en="Theme" compact />
          <select value={themeId} onChange={(event) => setThemeId(event.target.value)}>
            {!themes.length && <option value="">尚未建立主题</option>}
            {themes.map((item) => <option key={item.id} value={item.theme_id}>{item.name}</option>)}
          </select>
        </label>
        <label>
          <BilingualText zh="市场" en="Market" compact />
          <select value={market} onChange={(event) => setMarket(event.target.value)}>
            {(theme?.markets ?? ["CN", "US", "KR"]).map((item) => (
              <option key={item} value={item}>{item === "CN" ? "中国 A 股" : item === "KR" ? "韩国" : "美国"} · {item}</option>
            ))}
          </select>
        </label>
        <label>
          <BilingualText zh="观察日期" en="As-of date" compact />
          <input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} />
        </label>
        <label>
          <BilingualText zh="行情口径" en="Market provider" compact />
          <select value={provider} onChange={(event) => setProvider(event.target.value as MarketProvider)}>
            <option value="fixture-market">冻结演示 · 无需 Key</option>
            <option value="eodhd">EODHD · 中美韩</option>
            {market === "CN" && <option value="tushare">Tushare · A 股校验</option>}
            <option value="yahoo">Yahoo · 明示降级路径</option>
          </select>
        </label>
        <button onClick={loadDemo} disabled={Boolean(busy)}>
          {busy === "demo" ? "加载中…" : "加载三市场演示"}<small>No-key demo</small>
        </button>
        <button onClick={syncBars} disabled={Boolean(busy) || provider === "fixture-market"}>
          {busy === "sync" ? "同步中…" : "同步本截面行情"}<small>Sync universe</small>
        </button>
        <button className="mainline-run" onClick={runMonitor} disabled={Boolean(busy) || !themeId}>
          {busy === "run" ? "计算中…" : "运行主线评估 ↗"}<small>Run deterministic assessment</small>
        </button>
      </div>

      <div className="mainline-grid">
        <article className="mainline-metrics">
          <div className="mainline-panel-title">
            <BilingualText zh="价格确认与参与度" en="Price confirmation & participation" />
            <span>{latestMetric?.as_of_date ?? "尚无结果"}</span>
          </div>
          <div className="metric-film">
            <div><small>20日主题收益</small><strong>{pct(latestMetric?.return_20d)}</strong></div>
            <div><small>相对基准</small><strong>{pct(latestMetric?.relative_strength_20d)}</strong></div>
            <div><small>站上均线宽度</small><strong>{pct(latestMetric?.breadth_above_20d)}</strong></div>
            <div><small>上涨参与度</small><strong>{pct(latestMetric?.positive_participation_20d)}</strong></div>
            <div><small>持续性</small><strong>{pct(latestMetric?.persistence_ratio)}</strong></div>
            <div><small>数据覆盖</small><strong>{pct(latestMetric?.coverage_ratio)}</strong></div>
          </div>
          <div className="mainline-explain">
            {(latestAssessment?.reasons ?? ["运行评估后，这里会解释状态由哪些指标驱动。"])
              .map((item) => <p key={item}>→ {mainlineMessageZh(item)}{mainlineMessageZh(item) !== item && <small>{item}</small>}</p>)}
            {latestAssessment?.blockers.map((item) => <p className="blocker" key={item}>! {mainlineMessageZh(item)}{mainlineMessageZh(item) !== item && <small>{item}</small>}</p>)}
            {latestMetric?.issues.map((item) => <p className="warning" key={item}>△ {mainlineMessageZh(item)}{mainlineMessageZh(item) !== item && <small>{item}</small>}</p>)}
          </div>
        </article>

        <article className="universe-panel">
          <div className="mainline-panel-title">
            <BilingualText zh="点时主题成分" en="Point-in-time universe" />
            <span>{memberRows.length} 个标的</span>
          </div>
          <div className="universe-head"><span>标的</span><span>市场认知</span><span>产业暴露</span><span>来源</span></div>
          {memberRows.map((item) => (
            <div className="universe-row" key={item.ticker}>
              <div><strong>{item.ticker}</strong><small>{item.name} · {item.role}</small></div>
              <span>{pct(item.recognition)}</span>
              <span className={item.exposure >= 0 ? "exposure-known" : "exposure-gap"}>
                {item.exposure >= 0 ? pct(item.exposure) : "待证据"}
              </span>
              <span>{item.sourceCount}</span>
            </div>
          ))}
          {!memberRows.length && <p className="empty-state">此日期与市场没有可用成分；系统不会用今天名单回填过去。</p>}
        </article>

        <aside className="mainline-rail">
          <div className="mainline-panel-title">
            <BilingualText zh="来源与任务状态" en="Sources & job state" />
          </div>
          <div className="source-stack">
            {sources.filter((item) => item.market === market || item.kind === "evidence_graph").map((item) => (
              <div key={item.id}>
                <i className={`coverage-${item.coverage}`} />
                <span>{item.name}<small>{item.kind} · {item.coverage}</small></span>
              </div>
            ))}
          </div>
          <div className="job-ticket">
            <small>最近盘后任务 · LATEST JOB</small>
            <strong>{latestJob ? translateUiValue(latestJob.status) : "尚未运行"}</strong>
            <p>{latestJob?.error || "重复运行同一日期会复用已完成结果，不会触发模型费用。"}</p>
          </div>
          <div className="official-matrix">
            <small>官方公告覆盖 · OFFICIAL SOURCES</small>
            {officialSources.filter((item) => item.markets.includes(market)).map((item) => (
              <div key={item.provider}>
                <span>{item.provider}</span>
                <b>{item.discovery}</b>
              </div>
            ))}
          </div>
        </aside>
      </div>

      <div className="proposal-strip">
        <div>
          <BilingualText zh="研究提案 / 人工成本门" en="Research proposals / Human cost gate" />
          <p>状态变化或已知成员的官方事件只会生成提案；接受提案也不会自动下单或偷偷调用模型。</p>
        </div>
        <div className="proposal-list">
          {proposals.length === 0 && <span className="proposal-empty">当前没有待处理提案</span>}
          {proposals.slice(0, 4).map((item) => (
            <article key={item.id}>
              <div>
                <strong>{item.action === "theme_scan" ? "运行主题扫描" : "重评既有候选"}</strong>
                <p>{mainlineMessageZh(item.reason)}{mainlineMessageZh(item.reason) !== item.reason && <small>{item.reason}</small>}</p>
              </div>
              <span>{translateUiValue(item.human_status)}</span>
              {item.human_status === "pending" && <div>
                <button disabled={busy === item.id} onClick={() => decide(item.id, true)}>接受</button>
                <button disabled={busy === item.id} onClick={() => decide(item.id, false)}>拒绝</button>
              </div>}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
