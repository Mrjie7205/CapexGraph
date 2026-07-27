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

interface ResearchReadinessProps {
  run: ResearchRun | null;
  onRunUpdated: (run: ResearchRun) => void;
  onError: (message: string) => void;
}

function providerLabel(value: unknown): string {
  if (!value || typeof value !== "object") return "not recorded";
  const item = value as Record<string, unknown>;
  return [item.name, item.version && `v${item.version}`, item.model]
    .filter(Boolean)
    .join(" · ");
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
      onError(reason instanceof Error ? reason.message : "Readiness data unavailable");
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
      onError(reason instanceof Error ? reason.message : "Financial extraction failed");
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
      version: "legacy",
    },
  );
  const sourceFailures = [
    ...(Array.isArray(run?.manifest.source_discovery_errors)
      ? run.manifest.source_discovery_errors
      : []),
    ...(Array.isArray(run?.manifest.financial_fact_errors)
      ? run.manifest.financial_fact_errors
      : []),
  ] as Array<Record<string, unknown>>;

  return (
    <section className="readiness panel" id="readiness">
      <div className="panel-title">
        <span>Research readiness / 研究就绪度</span>
        <b>{coverage?.status ?? "NO RUN"}</b>
      </div>
      {!run && <p className="empty-state">Create or select a run to inspect evidence coverage.</p>}
      {run && (
        <>
          <div className="readiness-grid">
            <article className={`coverage-orbit ${coverage?.strict_ready ? "ready" : ""}`}>
              <div className="coverage-ring">
                <strong>{coverage?.reviewed ?? 0}</strong>
                <span>reviewed</span>
              </div>
              <div>
                <small>Evidence mode</small>
                <h3>{coverage?.mode ?? "partial"}</h3>
                <p>
                  {coverage?.captured ?? 0} captured · {coverage?.pending_reviews ?? 0} pending ·{" "}
                  {coverage?.source_failures ?? 0} failed
                </p>
              </div>
            </article>
            <article className="provider-plate">
              <small>Model adapter</small>
              <strong>{modelProvider}</strong>
              <p>
                Research date {run.as_of_date} · {String(run.manifest.evidence_policy ?? "policy pending")}
              </p>
              <a href={reportUrl(run.id)} target="_blank" rel="noreferrer">
                Open current report ↗
              </a>
            </article>
            <article className="coverage-gaps">
              <small>Coverage gaps</small>
              {coverage?.gaps.length ? (
                <ul>{coverage.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
              ) : (
                <p>No deterministic coverage gaps detected.</p>
              )}
              {sourceFailures.map((failure, index) => (
                <p className="provider-failure" key={`${failure.at ?? index}`}>
                  {String(failure.provider ?? "provider")} · {String(failure.error ?? "failed")}
                </p>
              ))}
            </article>
          </div>

          <div className="facts-head">
            <div>
              <small>Official filing facts</small>
              <h3>Period-aware, source-located, immutable</h3>
            </div>
            <form onSubmit={extract}>
              <input
                aria-label="SEC ticker company or CIK for financial facts"
                placeholder="Exact SEC ticker / company / CIK"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
              />
              <button disabled={busy || !identifier.trim()}>
                {busy ? "Extracting…" : "Extract SEC facts"}
              </button>
            </form>
          </div>
          {visibleFacts.length > 0 ? (
            <div className="facts-table-wrap">
              <table className="facts-table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Statement</th>
                    <th>Period</th>
                    <th>Value</th>
                    <th>Unit</th>
                    <th>Type</th>
                    <th>Source locator</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleFacts.map((fact) => (
                    <tr key={fact.id}>
                      <td><strong>{fact.metric}</strong><small>{fact.ticker}</small></td>
                      <td>{fact.statement.replaceAll("_", " ")}</td>
                      <td>{fact.period_end ?? "not reported"}</td>
                      <td>{valueLabel(fact)}</td>
                      <td>{fact.unit}</td>
                      <td><span className={`fact-type ${fact.fact_type}`}>{fact.fact_type}</span></td>
                      <td title={fact.source_locator}>{fact.source_locator}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {facts.length > visibleFacts.length && (
                <p className="table-note">Showing 24 of {facts.length} persisted facts.</p>
              )}
            </div>
          ) : (
            <p className="empty-state">
              No filing facts yet. SEC extraction is no-key, but the issuer must be SEC-registered.
            </p>
          )}
        </>
      )}
    </section>
  );
}
