from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from capexgraph.domain import (
    DisclosureFactCandidate,
    EvidenceStatus,
    ExtractionCandidateStatus,
    FinancialFact,
    FinancialFactType,
    FinancialStatement,
    SourceAuthority,
)
from capexgraph.financials.store import FinancialFactStore
from capexgraph.runtime.migrations import ensure_database
from capexgraph.runtime.store import state_db_path
from capexgraph.sources.store import SourceSuggestionStore
from capexgraph.tools.evidence import read_run_evidence_text, verify_evidence_hash
from capexgraph.workflows import load_run

PATTERNS = (
    re.compile(
        r"(?P<label>营业收入|归属于上市公司股东的净利润|净利润|资本开支|购建固定资产[^，。；\n]{0,12})"
        r"[^\d+\-(]{0,35}(?P<number>[+\-]?[\d,.]+)\s*(?P<unit>亿元|万元|元)"
    ),
    re.compile(
        r"(?P<label>매출액|영업이익|당기순이익|유형자산의\s*취득)"
        r"[^\d+\-(]{0,35}(?P<number>[+\-]?[\d,.]+)\s*(?P<unit>억원|백만원|원)"
    ),
    re.compile(
        r"(?P<label>revenue|net income|operating income|capital expenditures?)"
        r"[^\d+\-(]{0,35}(?P<number>[+\-]?[\d,.]+)\s*"
        r"(?P<unit>USD|US\$|\$)?\s*(?P<scale>billion|million)?",
        re.IGNORECASE,
    ),
)

METRICS = {
    "营业收入": ("revenue", FinancialStatement.INCOME),
    "归属于上市公司股东的净利润": ("net_income", FinancialStatement.INCOME),
    "净利润": ("net_income", FinancialStatement.INCOME),
    "资本开支": ("capital_expenditures", FinancialStatement.CASH_FLOW),
    "购建固定资产": ("capital_expenditures", FinancialStatement.CASH_FLOW),
    "매출액": ("revenue", FinancialStatement.INCOME),
    "영업이익": ("operating_income", FinancialStatement.INCOME),
    "당기순이익": ("net_income", FinancialStatement.INCOME),
    "유형자산의취득": ("capital_expenditures", FinancialStatement.CASH_FLOW),
    "revenue": ("revenue", FinancialStatement.INCOME),
    "net income": ("net_income", FinancialStatement.INCOME),
    "operating income": ("operating_income", FinancialStatement.INCOME),
    "capital expenditure": ("capital_expenditures", FinancialStatement.CASH_FLOW),
    "capital expenditures": ("capital_expenditures", FinancialStatement.CASH_FLOW),
}


def _report_period(title: str, metadata: dict) -> tuple[date, str] | None:
    value = str(metadata.get("report_period") or "")
    dates = re.findall(r"20\d{2}[-./]\d{2}[-./]\d{2}", value)
    if dates:
        parsed = dates[-1].replace(".", "-").replace("/", "-")
        return date.fromisoformat(parsed), "reported"
    cn = re.search(r"(20\d{2})年\s*(年度|半年度|第一季度|第三季度)", title)
    if cn:
        year = int(cn.group(1))
        mapping = {
            "年度": (12, 31, "FY"),
            "半年度": (6, 30, "H1"),
            "第一季度": (3, 31, "Q1"),
            "第三季度": (9, 30, "Q3"),
        }
        month, day, fiscal = mapping[cn.group(2)]
        return date(year, month, day), fiscal
    kr = re.search(r"(20\d{2})년\s*(사업보고서|반기보고서|분기보고서)", title)
    if kr:
        year = int(kr.group(1))
        mapping = {
            "사업보고서": (12, 31, "FY"),
            "반기보고서": (6, 30, "H1"),
            "분기보고서": (3, 31, "Q1"),
        }
        month, day, fiscal = mapping[kr.group(2)]
        return date(year, month, day), fiscal
    return None


def _normalized_value(match: re.Match[str], market: str) -> tuple[float, str]:
    number = float(match.group("number").replace(",", ""))
    unit = str(match.groupdict().get("unit") or "")
    scale = str(match.groupdict().get("scale") or "").casefold()
    if market == "CN":
        return number * {"亿元": 1e8, "万元": 1e4, "元": 1}[unit], "CNY"
    if market == "KR":
        return number * {"억원": 1e8, "백만원": 1e6, "원": 1}[unit], "KRW"
    return number * {"billion": 1e9, "million": 1e6, "": 1}[scale], "USD"


class DisclosureFactCandidateStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = (db_path or state_db_path()).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        ensure_database(self.db_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def save(self, candidate: DisclosureFactCandidate) -> DisclosureFactCandidate:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO disclosure_fact_candidates (
                    id, run_id, evidence_id, source_suggestion_id, metric,
                    period_end, value, status, created_at, decided_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    decided_at = excluded.decided_at,
                    payload = excluded.payload
                """,
                (
                    candidate.id,
                    candidate.run_id,
                    candidate.evidence_id,
                    candidate.source_suggestion_id,
                    candidate.metric,
                    candidate.period_end.isoformat(),
                    candidate.value,
                    candidate.status.value,
                    candidate.created_at.isoformat(),
                    candidate.decided_at.isoformat() if candidate.decided_at else None,
                    candidate.model_dump_json(),
                ),
            )
        return candidate

    def get(self, candidate_id: str) -> DisclosureFactCandidate | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM disclosure_fact_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        return DisclosureFactCandidate.model_validate_json(row["payload"]) if row else None

    def list(self, run_id: str) -> list[DisclosureFactCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM disclosure_fact_candidates
                WHERE run_id = ? ORDER BY created_at DESC, metric
                """,
                (run_id,),
            ).fetchall()
        return [DisclosureFactCandidate.model_validate_json(row["payload"]) for row in rows]


class ReviewedDisclosureFactService:
    provider_name = "reviewed-official-disclosure-regex"
    provider_version = "1"

    def __init__(
        self,
        store: DisclosureFactCandidateStore | None = None,
    ) -> None:
        self.store = store or DisclosureFactCandidateStore()
        self.source_store = SourceSuggestionStore(self.store.db_path)
        self.fact_store = FinancialFactStore(self.store.db_path)

    def preview(self, run_id: str, evidence_id: str) -> list[DisclosureFactCandidate]:
        run = load_run(run_id)
        if run is None:
            raise KeyError(f"Research run not found: {run_id}")
        evidence = next((item for item in run.evidence if item.id == evidence_id), None)
        if evidence is None:
            raise KeyError(f"Evidence not found: {evidence_id}")
        if evidence.status != EvidenceStatus.REVIEWED or not verify_evidence_hash(run, evidence):
            raise ValueError("Only hash-verified, human-reviewed evidence can produce candidates")
        suggestion = next(
            (item for item in self.source_store.list(run_id) if item.evidence_id == evidence_id),
            None,
        )
        if suggestion is None or suggestion.authority not in {
            SourceAuthority.REGULATOR,
            SourceAuthority.ISSUER,
        }:
            raise ValueError("Candidate extraction requires a linked official source suggestion")
        period = _report_period(suggestion.title, suggestion.metadata)
        if period is None:
            raise ValueError("Disclosure has no deterministically parseable reporting period")
        period_end, fiscal_period = period
        text = read_run_evidence_text(run_id, evidence_id)
        candidates: list[DisclosureFactCandidate] = []
        seen: set[tuple[str, float]] = set()
        market = str(suggestion.metadata.get("jurisdiction") or run.market).upper()
        for pattern in PATTERNS:
            for match in pattern.finditer(text):
                label = re.sub(r"\s+", "", match.group("label")).casefold()
                metric = next(
                    (value for key, value in METRICS.items() if label.startswith(key.casefold())),
                    None,
                )
                if metric is None:
                    continue
                value, unit = _normalized_value(match, market)
                if (metric[0], value) in seen:
                    continue
                seen.add((metric[0], value))
                digest = hashlib.sha256(
                    f"{run_id}:{evidence_id}:{metric[0]}:{period_end}:{value}".encode()
                ).hexdigest()[:24]
                excerpt = text[max(0, match.start() - 45) : match.end() + 45].strip()
                candidate = DisclosureFactCandidate(
                    id=f"disclosure-candidate-{digest}",
                    run_id=run_id,
                    evidence_id=evidence_id,
                    source_suggestion_id=suggestion.id,
                    company=str(suggestion.metadata.get("company_name") or run.subject),
                    ticker=str(suggestion.metadata.get("ticker") or run.subject).upper(),
                    market=market,
                    statement=metric[1],
                    metric=metric[0],
                    concept=match.group("label"),
                    period_end=period_end,
                    fiscal_year=period_end.year,
                    fiscal_period=fiscal_period,
                    value=value,
                    unit=unit,
                    source_locator=f"text:{match.start()}-{match.end()}",
                    excerpt=excerpt,
                    confidence=0.72,
                    validation_notes=[
                        "Value and unit were parsed deterministically from reviewed text.",
                        "Human acceptance is required before this becomes a FinancialFact.",
                    ],
                )
                candidates.append(self.store.save(candidate))
        return candidates

    def decide(
        self,
        run_id: str,
        candidate_id: str,
        *,
        accepted: bool,
    ) -> DisclosureFactCandidate:
        candidate = self.store.get(candidate_id)
        if candidate is None or candidate.run_id != run_id:
            raise KeyError(f"Disclosure fact candidate not found: {candidate_id}")
        if candidate.status != ExtractionCandidateStatus.PENDING:
            raise ValueError("Disclosure fact candidate has already been decided")
        candidate.decided_at = datetime.now(UTC)
        if not accepted:
            candidate.status = ExtractionCandidateStatus.REJECTED
            return self.store.save(candidate)
        suggestion = self.source_store.get(candidate.source_suggestion_id)
        if suggestion is None or suggestion.evidence_id != candidate.evidence_id:
            raise ValueError("Candidate source/evidence link is no longer valid")
        fact_digest = hashlib.sha256(f"accepted:{candidate.id}".encode()).hexdigest()[:24]
        fact = FinancialFact(
            id=f"fact-{fact_digest}",
            company=candidate.company,
            ticker=candidate.ticker,
            statement=candidate.statement,
            metric=candidate.metric,
            concept=candidate.concept,
            period_end=candidate.period_end,
            fiscal_year=candidate.fiscal_year,
            fiscal_period=candidate.fiscal_period,
            form="reviewed official disclosure",
            filed_date=suggestion.published_at,
            accession=str(suggestion.metadata.get("announcement_id") or "") or None,
            value=candidate.value,
            unit=candidate.unit,
            fact_type=FinancialFactType.REPORTED,
            source_evidence_id=candidate.evidence_id,
            source_locator=candidate.source_locator,
            provider=self.provider_name,
            provider_version=self.provider_version,
        )
        self.fact_store.add(run_id, fact)
        candidate.status = ExtractionCandidateStatus.ACCEPTED
        candidate.fact_id = fact.id
        return self.store.save(candidate)
