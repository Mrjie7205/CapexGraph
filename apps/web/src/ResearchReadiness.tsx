import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  extractFinancialFacts,
  getCoverage,
  getRun,
  listFinancialFacts,
  reportUrl,
  type EvidenceCoverage,
  type FinancialFact,
  type ResearchRun,
} from "./api";
import { BilingualText, humanizeUiValue, translateUiValue } from "./UiText";

interface ResearchReadinessProps {
  run: ResearchRun | null;
  onRunUpdated: (run: ResearchRun) => void;
  onError: (message: string) => void;
}

function providerLabel(value: unknown): string {
  if (!value || typeof value !== "object") return "未记录";
  const item = value as Record<string, unknown>;
  return [item.name, item.version && `v${item.version}`, item.model]
    .filter(Boolean)
    .join(" · ");
}

function coverageGapLabel(value: string): string {
  if (value === "No evidence has been captured for this run.") return "该研究尚未捕获任何证据。";
  const captured = value.match(/^(\d+) captured source\(s\) still require human review\.$/);
  if (captured) return `${captured[1]} 条已捕获来源仍需人工审核。`;
  const hashes = value.match(/^(\d+) captured source hash\(es\) no longer match\.$/);
  if (hashes) return `${hashes[1]} 条已捕获来源的哈希已不匹配。`;
  const captureFailures = value.match(/^(\d+) source capture\(s\) failed\.$/);
  if (captureFailures) return `${captureFailures[1]} 条来源捕获失败。`;
  const discoveryFailures = value.match(/^(\d+) source discovery request\(s\) failed\.$/);
  if (discoveryFailures) return `${discoveryFailures[1]} 次来源发现请求失败。`;
  return value;
}

function valueLabel(fact: FinancialFact): string {
  if (fact.value === undefined || fact.value === null) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(fact.value);
}

export function ResearchReadiness({
  run,
  onRunUpdated,
  onError,
}: ResearchReadinessProps) {
  const [coverage, setCoverage] = useState<EvidenceCoverage | null>(null);
  const [facts, setFacts] = useState<FinancialFact[]>([]);
  const [identifier, setIdentifier] = useState("");
  const [busy, setBusy] = useState(false);
  const evidenceSignal = run?.evidence.map((item) => `${item.id}:${item.status}`).join("|") ?? "";

  async function refresh() {
    if (!run) {
      setCoverage(null);
      setFacts([]);
      return;
    }
    const [nextCoverage, nextFacts] = await Promise.all([
      getCoverage(run.id),
      listFinancialFacts(run.id),
    ]);
    setCoverage(nextCoverage);
    setFacts(nextFacts);
  }

  useEffect(() => {
    setIdentifier("");
    refresh().catch((reason) => {
      onError(reason instanceof Error ? reason.message : "研究就绪度数据暂不可用");
    });
  }, [run?.id, evidenceSignal]);

  async function extract(event: FormEvent) {
    event.preventDefault();
    if (!run || !identifier.trim()) return;
    setBusy(true);
    onError("");
    try {
      setFacts(await extractFinancialFacts(run.id, identifier.trim()));
      onRunUpdated(await getRun(run.id));
      setCoverage(await getCoverage(run.id));
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "财务事实提取失败");
    } finally {
      setBusy(false);
    }
  }

  const visibleFacts = useMemo(
    () =>
      [...facts]
        .sort((left, right) => {
          if (left.fact_type === "missing" && right.fact_type !== "missing") return 1;
          if (right.fact_type === "missing" && left.fact_type !== "missing") return -1;
          return String(right.period_end ?? "").localeCompare(String(left.period_end ?? ""));
        })
        .slice(0, 24),
    [facts],
  );
  const modelProvider = providerLabel(
    run?.manifest.model_provider_details ?? {
      name: run?.manifest.model_provider,
      model: run?.manifest.model,
      version: "selected",
    },
  );
  const executionContext =
    run?.manifest.model_execution_context &&
    typeof run.manifest.model_execution_context === "object"
      ? (run.manifest.model_execution_context as Record<string, unknown>)
      : {};
  const sourceFailures = [
    ...(Array.isArray(run?.manifest.source_discovery_errors)
      ? run.manifest.source_discovery_errors
      : []),
    ...(Array.isArray(run?.manifest.financial_fact_errors)
      ? run.manifest.financial_fact_errors
      : []),
  ] as Array<Record<string, unknown>>;
  const usableReviewed = (coverage?.reviewed ?? 0) + (coverage?.agent_reviewed ?? 0);

  return (
    <section className="readiness panel" id="readiness">
      <div className="panel-title">
        <BilingualText zh="研究就绪度" en="Research readiness" />
        <b>
          {coverage
            ? <><span>{translateUiValue(coverage.status)}</span><small>{humanizeUiValue(coverage.status)}</small></>
            : <><span>暂无研究</span><small>No run</small></>}
        </b>
      </div>
      {!run && <p className="empty-state">请创建或选择研究任务，以检查证据覆盖情况。</p>}
      {run && (
        <>
          <div className="readiness-grid">
            <article className={`coverage-orbit ${coverage?.strict_ready ? "ready" : ""}`}>
              <div className="coverage-ring">
                <strong>{usableReviewed}</strong>
                <span>可用审核<small>grounded</small></span>
              </div>
              <div>
                <BilingualText zh="证据模式" en="Evidence mode" compact />
                <h3>{coverage?.mode === "strict" ? "严格模式" : "部分模式"}<small>{coverage?.mode ?? "partial"}</small></h3>
                <p>
                  人工审核 {coverage?.reviewed ?? 0} · Agent 审核 {coverage?.agent_reviewed ?? 0}<br />
                  已捕获 {coverage?.captured ?? 0} · 待审核 {coverage?.pending_reviews ?? 0} · 失败 {coverage?.source_failures ?? 0}
                  <small>human · agent · captured · pending · failed</small>
                </p>
              </div>
            </article>
            <article className="provider-plate">
              <BilingualText zh="模型适配器" en="Model adapter" compact />
              <strong>{modelProvider}</strong>
              <p>
                研究日期 {run.as_of_date} · {String(run.manifest.evidence_policy ?? "证据策略待记录")}
              </p>
              <p>
                {translateUiValue(String(executionContext.transport ?? "传输方式待记录"))} ·{" "}
                {translateUiValue(String(executionContext.billing_mode ?? "计费方式待记录"))}
              </p>
              <a href={reportUrl(run.id)} target="_blank" rel="noreferrer">
                打开当前报告<small>Open current report ↗</small>
              </a>
            </article>
            <article className="coverage-gaps">
              <BilingualText zh="覆盖缺口" en="Coverage gaps" compact />
              {coverage?.gaps.length ? (
                <ul>{coverage.gaps.map((gap) => <li key={gap}>{coverageGapLabel(gap)}</li>)}</ul>
              ) : (
                <p>未检测到确定性的覆盖缺口。</p>
              )}
              {sourceFailures.map((failure, index) => (
                <p className="provider-failure" key={`${failure.at ?? index}`}>
                  来源服务：{String(failure.provider ?? "未知")} · {String(failure.error ?? "失败")}
                </p>
              ))}
            </article>
          </div>

          <div className="facts-head">
            <div>
              <BilingualText zh="官方申报事实" en="Official filing facts" compact />
              <h3>识别报告期、定位原文、不可变留存<small>Period-aware · source-located · immutable</small></h3>
            </div>
            <form onSubmit={extract}>
              <input
                aria-label="用于财务事实提取的 SEC 股票代码、公司名或 CIK"
                placeholder="准确的 SEC 股票代码 / 公司名 / CIK"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
              />
              <button disabled={busy || !identifier.trim()}>
                <BilingualText
                  zh={busy ? "正在提取…" : "提取 SEC 事实"}
                  en={busy ? "Extracting…" : "Extract SEC facts"}
                  compact
                  align="center"
                />
              </button>
            </form>
          </div>
          {visibleFacts.length > 0 ? (
            <div className="facts-table-wrap">
              <table className="facts-table">
                <thead>
                  <tr>
                    <th>指标<small>Metric</small></th>
                    <th>报表<small>Statement</small></th>
                    <th>报告期<small>Period</small></th>
                    <th>数值<small>Value</small></th>
                    <th>单位<small>Unit</small></th>
                    <th>类型<small>Type</small></th>
                    <th>来源定位<small>Source locator</small></th>
                  </tr>
                </thead>
                <tbody>
                  {visibleFacts.map((fact) => (
                    <tr key={fact.id}>
                      <td><strong>{fact.metric}</strong><small>{fact.ticker}</small></td>
                      <td>{translateUiValue(fact.statement)}<small>{humanizeUiValue(fact.statement)}</small></td>
                      <td>{fact.period_end ?? "未披露"}</td>
                      <td>{valueLabel(fact)}</td>
                      <td>{fact.unit}</td>
                      <td><span className={`fact-type ${fact.fact_type}`}>{translateUiValue(fact.fact_type)}<small>{humanizeUiValue(fact.fact_type)}</small></span></td>
                      <td title={fact.source_locator}>{fact.source_locator}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {facts.length > visibleFacts.length && (
                <p className="table-note">当前显示 24 / {facts.length} 条已持久化事实。</p>
              )}
            </div>
          ) : (
            <p className="empty-state">
              暂无申报事实。SEC 提取无需 API Key，但公司必须在 SEC 注册。
            </p>
          )}
        </>
      )}
    </section>
  );
}
