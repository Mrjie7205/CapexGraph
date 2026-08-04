import type { ReactNode } from "react";

import type { ResearchRun } from "./api";
import { humanizeUiValue, translateUiValue } from "./UiText";

export const SENSITIVE_KEY = /(?:api[_-]?key|authorization|bearer|credential|password|secret|token)/i;

const FIELD_LABELS: Record<string, string> = {
  scope: "研究范围",
  investment_question: "核心投资问题",
  included_layers: "纳入研究的产业层",
  excluded_topics: "明确排除的内容",
  capex_drivers: "资本开支驱动因素",
  research_questions: "后续研究问题",
  nodes: "识别出的产业节点",
  coverage_notes: "覆盖说明",
  unresolved_entities: "待核实实体",
  label: "名称",
  ticker: "代码",
  market: "市场",
  layer: "产业层",
  node_type: "节点类型",
  id: "记录 ID",
  source: "来源节点",
  target: "目标节点",
  relationship: "关系",
  product: "产品 / 服务",
  basis: "判断依据",
  confidence: "置信度",
  evidence_ids: "证据引用",
  summary: "阶段摘要",
  limitations: "局限与缺口",
  next_actions: "下一步",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key.replaceAll("_", " ");
}

function formatTimestamp(value?: string): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
    hour12: false,
  }).format(parsed);
}

function primitive(value: unknown): ReactNode {
  if (value === null || value === undefined || value === "") return <span className="stage-empty-value">—</span>;
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 4 }).format(value);
  return String(value);
}

function StructuredValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="stage-empty-value">暂无</span>;
    if (value.every((item) => !isRecord(item) && !Array.isArray(item))) {
      return <ul className="stage-detail-list">{value.map((item, index) => <li key={index}>{primitive(item)}</li>)}</ul>;
    }
    return (
      <div className="stage-detail-cards">
        {value.map((item, index) => (
          <article key={index}>
            <span className="stage-card-index">{String(index + 1).padStart(2, "0")}</span>
            <StructuredValue value={item} depth={depth + 1} />
          </article>
        ))}
      </div>
    );
  }

  if (isRecord(value)) {
    const entries = Object.entries(value).filter(([key]) => !SENSITIVE_KEY.test(key));
    if (entries.length === 0) return <span className="stage-empty-value">暂无可显示字段</span>;
    return (
      <dl className={`stage-detail-fields depth-${Math.min(depth, 2)}`}>
        {entries.map(([key, item]) => (
          <div key={key}>
            <dt>{fieldLabel(key)}</dt>
            <dd><StructuredValue value={item} depth={depth + 1} /></dd>
          </div>
        ))}
      </dl>
    );
  }

  return <>{primitive(value)}</>;
}

function readLineage(run: ResearchRun) {
  const details = isRecord(run.manifest.model_provider_details)
    ? run.manifest.model_provider_details
    : {};
  const usage = isRecord(run.manifest.model_usage) ? run.manifest.model_usage : {};
  return {
    provider: String(run.manifest.model_provider ?? details.name ?? "未记录"),
    model: String(run.manifest.model ?? details.model ?? "未记录"),
    transport: String(details.transport ?? details.api_surface ?? "未记录"),
    calls: typeof usage.calls === "number" ? String(usage.calls) : "—",
    evidenceMode: String(run.manifest.evidence_mode ?? "未记录"),
  };
}

export function StageDetailPanel({ run, stageKey }: { run: ResearchRun; stageKey: string | null }) {
  const stage = run.pipeline.find((item) => item.key === stageKey);
  if (!stage) return null;
  const position = run.pipeline.findIndex((item) => item.key === stage.key) + 1;
  const output = run.manifest.agent_outputs?.[stage.key];
  const lineage = readLineage(run);

  return (
    <article className="stage-detail panel" aria-live="polite">
      <header className="stage-detail-head">
        <div>
          <span>阶段 {String(position).padStart(2, "0")} / Stage detail</span>
          <h2>{translateUiValue(stage.label)}</h2>
          <small>{stage.label} · {stage.key}</small>
        </div>
        <b className={`stage-detail-status ${stage.status}`}>
          {translateUiValue(stage.status)}
          <small>{humanizeUiValue(stage.status)}</small>
        </b>
      </header>

      <div className="stage-detail-meta" aria-label="阶段运行信息">
        <div><span>执行 Agent</span><strong>{stage.agent || "—"}</strong></div>
        <div><span>尝试次数</span><strong>{stage.attempts || 0}</strong></div>
        <div><span>开始时间</span><strong>{formatTimestamp(stage.started_at)}</strong></div>
        <div><span>完成时间</span><strong>{formatTimestamp(stage.completed_at)}</strong></div>
      </div>

      <div className="stage-lineage">
        <span>运行谱系</span>
        <div><small>通道</small><strong>{translateUiValue(lineage.provider)}</strong></div>
        <div><small>模型</small><strong>{lineage.model}</strong></div>
        <div><small>传输</small><strong>{lineage.transport}</strong></div>
        <div><small>累计调用</small><strong>{lineage.calls}</strong></div>
        <div><small>证据策略</small><strong>{translateUiValue(lineage.evidenceMode)}</strong></div>
      </div>

      {(stage.message || stage.error) && (
        <div className={`stage-detail-message ${stage.error ? "error" : ""}`}>
          <span>{stage.error ? "阶段错误" : "阶段说明"}</span>
          <p>{stage.error || stage.message}</p>
        </div>
      )}

      <section className="stage-detail-output">
        <div className="stage-detail-section-title">
          <span>结构化阶段输出</span>
          <small>已按字段整理 · 非原始 JSON</small>
        </div>
        {output === undefined || output === null ? (
          <p className="stage-detail-empty">阶段尚未生成结构化输出。若阶段失败，请先查看上方错误；若仍在运行，请等待检查点完成。</p>
        ) : (
          <StructuredValue value={output} />
        )}
      </section>
    </article>
  );
}
