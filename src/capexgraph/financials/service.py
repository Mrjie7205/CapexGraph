from __future__ import annotations

from datetime import UTC, datetime

from capexgraph.domain import FinancialFact
from capexgraph.financials.store import FinancialFactStore
from capexgraph.providers.filings import (
    FilingFactsProvider,
    OpenDartFinancialFactsProvider,
    SecCompanyFactsProvider,
)
from capexgraph.runtime.artifacts import atomic_write_json
from capexgraph.runtime.store import runs_dir
from capexgraph.tools.evidence import CollectedDocument, attach_collected_document
from capexgraph.workflows import load_run, save_run


class FinancialFactService:
    def __init__(self, store: FinancialFactStore | None = None) -> None:
        self.store = store or FinancialFactStore()

    def extract(
        self,
        run_id: str,
        *,
        identifier: str | None = None,
        provider: FilingFactsProvider | None = None,
    ) -> list[FinancialFact]:
        run = load_run(run_id)
        if run is None:
            raise KeyError(f"Research run not found: {run_id}")
        active_provider = provider or SecCompanyFactsProvider()
        try:
            result = active_provider.extract(run, identifier=identifier)
            evidence_path = runs_dir() / run.id / str(result.evidence.local_path)
            byte_count = evidence_path.stat().st_size
            attach_collected_document(
                run.id,
                CollectedDocument(
                    evidence=result.evidence,
                    text="",
                    byte_count=byte_count,
                ),
            )
            persisted = self.store.add_many(run.id, result.facts)
        except Exception as error:
            captured = getattr(error, "evidence", None)
            if captured is not None:
                evidence_path = runs_dir() / run.id / str(captured.local_path)
                attach_collected_document(
                    run.id,
                    CollectedDocument(
                        evidence=captured,
                        text="",
                        byte_count=evidence_path.stat().st_size,
                    ),
                )
            current = load_run(run_id)
            if current is not None:
                failures = current.manifest.setdefault("financial_fact_errors", [])
                failures.append(
                    {
                        "provider": active_provider.provider_name,
                        "version": active_provider.provider_version,
                        "at": datetime.now(UTC).isoformat(),
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
                save_run(current)
            raise

        current = load_run(run_id)
        if current is None:
            raise KeyError(f"Research run not found after extraction: {run_id}")
        relative_path = "financials/facts.json"
        atomic_write_json(
            runs_dir() / current.id / relative_path,
            {
                "schema_version": "1",
                "provider": {
                    "name": active_provider.provider_name,
                    "version": active_provider.provider_version,
                },
                "source_evidence_id": result.evidence.id,
                "items": [fact.model_dump(mode="json") for fact in persisted],
            },
        )
        latest: dict[str, FinancialFact] = {}
        for fact in persisted:
            if fact.value is None:
                continue
            existing = latest.get(fact.metric)
            fact_order = (
                fact.period_end or current.as_of_date,
                fact.filed_date or current.as_of_date,
            )
            existing_order = (
                (
                    existing.period_end or current.as_of_date,
                    existing.filed_date or current.as_of_date,
                )
                if existing
                else None
            )
            if existing_order is None or fact_order >= existing_order:
                latest[fact.metric] = fact
        atomic_write_json(
            runs_dir() / current.id / "financials/summary.json",
            {
                "latest": {
                    metric: fact.model_dump(mode="json") for metric, fact in sorted(latest.items())
                },
                "missing": [
                    fact.metric for fact in persisted if fact.fact_type.value == "missing"
                ],
            },
        )
        current.manifest["financial_facts"] = {
            "path": relative_path,
            "count": len(persisted),
            "source_evidence_id": result.evidence.id,
            "provider": active_provider.provider_name,
            "provider_version": active_provider.provider_version,
        }
        providers = current.manifest.setdefault("data_providers", [])
        if active_provider.provider_name not in providers:
            providers.append(active_provider.provider_name)
        records = current.manifest.setdefault("data_provider_records", [])
        identity = {
            "name": active_provider.provider_name,
            "version": active_provider.provider_version,
        }
        if identity not in records:
            records.append(identity)
        save_run(current)
        return persisted

    @staticmethod
    def provider(name: str) -> FilingFactsProvider:
        normalized = name.strip().lower().replace("_", "-")
        if normalized in {"sec", "sec-companyfacts"}:
            return SecCompanyFactsProvider()
        if normalized in {"opendart", "opendart-financial-statements"}:
            return OpenDartFinancialFactsProvider()
        raise ValueError("Unknown financial provider. Choose sec or opendart.")

    def list(self, run_id: str) -> list[FinancialFact]:
        if load_run(run_id) is None:
            raise KeyError(f"Research run not found: {run_id}")
        return self.store.list(run_id)
