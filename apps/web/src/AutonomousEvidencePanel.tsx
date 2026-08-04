import type { EvidenceBootstrapState, ResearchRun } from "./api";

const PHASES = [
  { key: "planning_companies", label: "公司假设", note: "从研究边界提出可核验的上市公司种子" },
  { key: "discovering_official_sources", label: "官方来源", note: "按股票代码匹配监管或公司官方披露" },
  { key: "capturing_sources", label: "材料抓取", note: "下载正文并保存来源哈希" },
  { key: "reviewing_evidence", label: "独立审核", note: "逐份核对原文并验证精确引用" },
  { key: "completed", label: "交给图谱", note: "仅把通过审核的公司和证据送入研究" },
] as const;

function phaseIndex(state?: EvidenceBootstrapState): number {
  if (!state) return -1;
  return PHASES.findIndex((phase) => phase.key === state.phase);
}

function phaseState(
  index: number,
  activeIndex: number,
  status?: EvidenceBootstrapState["status"],
): "done" | "active" | "failed" | "waiting" {
  if (status === "failed" && index === activeIndex) return "failed";
  if (index < activeIndex || status === "completed") return "done";
  if (index === activeIndex && status === "running") return "active";
  return "waiting";
}

function companyLabel(company: Record<string, unknown>): string {
  const label = typeof company.label === "string" ? company.label : "已验证公司";
  const ticker = typeof company.ticker === "string" ? company.ticker : "";
  return ticker ? `${label} · ${ticker}` : label;
}

export function AutonomousEvidencePanel({
  run,
  upcoming = false,
}: {
  run: ResearchRun;
  upcoming?: boolean;
}) {
  const state = run.manifest.evidence_bootstrap;
  if (!state && !upcoming) return null;
  const activeIndex = phaseIndex(state);
  const status = state?.status ?? "idle";

  return (
    <article className={`autonomous-evidence panel ${status}`} aria-live="polite">
      <header className="autonomous-evidence-head">
        <div>
          <span className="eyebrow">Agent 自动取证</span>
          <h2>{state?.status === "completed" ? "官方材料已完成机器复核" : "自动补齐第一批公司证据"}</h2>
          <p>你无需挑公司或报告；系统会完成选择、抓取、逐份审核和引用核对。</p>
        </div>
        <b className={`bootstrap-status ${status}`}>
          {status === "running" ? "运行中" : status === "completed" ? "已完成" : status === "failed" ? "需重试" : "下一阶段启动"}
          <small>{state ? `第 ${state.attempt} 次` : "尚未开始"}</small>
        </b>
      </header>

      <ol className="bootstrap-phases">
        {PHASES.map((phase, index) => {
          const current = phaseState(index, activeIndex, state?.status);
          return (
            <li className={current} key={phase.key}>
              <i>{current === "done" ? "✓" : String(index + 1).padStart(2, "0")}</i>
              <div><strong>{phase.label}</strong><small>{phase.note}</small></div>
            </li>
          );
        })}
      </ol>

      {state && (
        <div className="bootstrap-metrics" aria-label="自动取证统计">
          <div><span>提出公司</span><strong>{state.proposed_companies}</strong></div>
          <div><span>发现来源</span><strong>{state.discovered_sources}</strong></div>
          <div><span>已抓取</span><strong>{state.captured_sources}</strong></div>
          <div><span>审核通过</span><strong>{state.accepted_sources}</strong></div>
          <div><span>拒绝 / 不足</span><strong>{state.rejected_sources}</strong></div>
        </div>
      )}

      {state?.accepted_companies.length ? (
        <div className="bootstrap-companies">
          <span>已验证公司</span>
          {state.accepted_companies.map((company, index) => (
            <b key={`${companyLabel(company)}-${index}`}>{companyLabel(company)}</b>
          ))}
        </div>
      ) : null}

      {state?.error && (
        <div className="bootstrap-error" role="alert">
          <strong>本轮没有形成可用证据</strong>
          <p>{state.error}</p>
          <small>重新运行失败检查点会再次尝试；图谱不会在零证据状态下偷偷继续。</small>
        </div>
      )}

      <footer>
        <span>审核身份会记录为“Agent 已审核”，不会冒充人工审核。</span>
        <strong>Agent 材料最高只支持中等置信度</strong>
      </footer>
    </article>
  );
}
