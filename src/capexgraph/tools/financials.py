from __future__ import annotations

import csv
from pathlib import Path

from capexgraph.domain import FinancialMetric
from capexgraph.runtime.artifacts import atomic_write_json
from capexgraph.runtime.store import runs_dir
from capexgraph.tools.identity import canonical_ticker
from capexgraph.workflows import load_run, save_run

REQUIRED_COLUMNS = {"ticker", "metric", "period_end", "value", "unit"}


def load_financial_metrics(path: Path) -> list[FinancialMetric]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Financial CSV is missing columns: {sorted(missing)}")
        return [
            FinancialMetric(
                ticker=canonical_ticker(row["ticker"]),
                metric=row["metric"].strip(),
                period_end=row["period_end"],
                value=float(row["value"]),
                unit=row["unit"].strip(),
                source_evidence_id=row.get("source_evidence_id") or None,
            )
            for row in reader
        ]


def attach_financial_metrics(run_id: str, path: Path) -> list[FinancialMetric]:
    return attach_financial_metric_items(run_id, load_financial_metrics(path))


def attach_financial_metric_items(
    run_id: str,
    metrics: list[FinancialMetric],
) -> list[FinancialMetric]:
    run = load_run(run_id)
    if run is None:
        raise KeyError(f"Research run not found: {run_id}")
    evidence_ids = {item.id for item in run.evidence}
    missing = {
        metric.source_evidence_id
        for metric in metrics
        if metric.source_evidence_id and metric.source_evidence_id not in evidence_ids
    }
    if missing:
        raise ValueError(f"Financial metrics reference missing evidence: {sorted(missing)}")
    relative_path = "financials/metrics.json"
    atomic_write_json(
        runs_dir() / run.id / relative_path,
        {"items": [metric.model_dump(mode="json") for metric in metrics]},
    )
    run.manifest["financial_metrics"] = {
        "path": relative_path,
        "count": len(metrics),
        "tickers": sorted({metric.ticker for metric in metrics}),
    }
    save_run(run)
    return metrics
