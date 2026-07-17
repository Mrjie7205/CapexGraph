from __future__ import annotations

import hashlib
import io
import ipaddress
import os
import re
import socket
from collections.abc import Callable
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, HttpUrl
from pypdf import PdfReader

from capexgraph.domain import Evidence, EvidenceKind, EvidenceStatus, ResearchRun
from capexgraph.runtime.artifacts import atomic_write_bytes, atomic_write_text
from capexgraph.runtime.store import runs_dir
from capexgraph.workflows import load_run, save_run

MAX_SOURCE_BYTES = 20 * 1024 * 1024
USER_AGENT = "CapexGraph/0.2 evidence-capture (+https://github.com/Mrjie7205/CapexGraph)"


class EvidenceSourceRequest(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: EvidenceKind
    url: HttpUrl
    published_at: date | None = None
    publisher: str | None = None


class EvidencePack(BaseModel):
    subject: str = Field(min_length=1)
    sources: list[EvidenceSourceRequest] = Field(min_length=1)


class CollectedDocument(BaseModel):
    evidence: Evidence
    text: str
    byte_count: int


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data.strip())


def _safe_evidence_id(value: str) -> str:
    safe = "".join(character for character in value if character.isalnum() or character in "-_")
    if not safe or safe != value:
        raise ValueError("Evidence IDs may contain only letters, numbers, hyphens, and underscores")
    return safe


def _is_forbidden_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _validate_public_url(
    url: str,
    *,
    allow_private: bool,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Evidence URL must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("Evidence URLs cannot contain credentials")
    if allow_private:
        return
    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Private or loopback evidence URLs are blocked")
    try:
        if _is_forbidden_ip(hostname):
            raise ValueError("Private or loopback evidence URLs are blocked")
        return
    except ValueError as error:
        if "blocked" in str(error):
            raise
    try:
        addresses = {entry[4][0] for entry in resolver(hostname, parsed.port or 443)}
    except OSError as error:
        raise ValueError(f"Evidence host could not be resolved: {hostname}") from error
    if not addresses or any(_is_forbidden_ip(address) for address in addresses):
        raise ValueError("Private or loopback evidence URLs are blocked")


def _extract_text(raw: bytes, content_type: str) -> str:
    if "pdf" in content_type.lower() or raw.startswith(b"%PDF"):
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        decoded = raw.decode("utf-8", errors="replace")
        parser = _TextExtractor()
        parser.feed(decoded)
        text = "\n".join(parser.parts)
    return re.sub(r"[ \t]+", " ", text).strip()


class EvidenceCollector:
    """Capture a public web/PDF source with SSRF guards, hashing, and local provenance."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        max_bytes: int = MAX_SOURCE_BYTES,
        allow_private: bool | None = None,
        resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
    ) -> None:
        self.client = client or httpx.Client(follow_redirects=True, timeout=30)
        self.max_bytes = max_bytes
        self.allow_private = (
            os.getenv("CAPEXGRAPH_ALLOW_PRIVATE_URLS") == "1"
            if allow_private is None
            else allow_private
        )
        self.resolver = resolver

    def collect(self, run_id: str, source: EvidenceSourceRequest) -> CollectedDocument:
        evidence_id = _safe_evidence_id(source.id)
        url = str(source.url)
        _validate_public_url(
            url,
            allow_private=self.allow_private,
            resolver=self.resolver,
        )
        raw_parts: list[bytes] = []
        size = 0
        with self.client.stream(
            "GET",
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,*/*"},
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            final_url = str(response.url)
            _validate_public_url(
                final_url,
                allow_private=self.allow_private,
                resolver=self.resolver,
            )
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > self.max_bytes:
                    raise ValueError(f"Evidence source exceeds {self.max_bytes} bytes")
                raw_parts.append(chunk)
            content_type = response.headers.get("content-type", "application/octet-stream")

        raw = b"".join(raw_parts)
        digest = hashlib.sha256(raw).hexdigest()
        text = _extract_text(raw, content_type)
        extension = ".pdf" if "pdf" in content_type.lower() or raw.startswith(b"%PDF") else ".html"
        relative_raw = Path("sources") / f"{evidence_id}{extension}"
        relative_text = Path("sources") / f"{evidence_id}.txt"
        run_dir = runs_dir() / run_id
        atomic_write_bytes(run_dir / relative_raw, raw)
        atomic_write_text(run_dir / relative_text, text)

        evidence = Evidence(
            id=evidence_id,
            title=source.title,
            kind=source.kind,
            source_url=final_url,
            published_at=source.published_at,
            excerpt=text[:600],
            source_hash=digest,
            publisher=source.publisher,
            content_type=content_type.split(";", 1)[0].strip(),
            local_path=relative_raw.as_posix(),
            status=EvidenceStatus.CAPTURED,
        )
        return CollectedDocument(evidence=evidence, text=text, byte_count=size)


def _replace_evidence(run: ResearchRun, evidence: Evidence) -> None:
    items = {item.id: item for item in run.evidence}
    items[evidence.id] = evidence
    run.evidence = list(items.values())


def collect_evidence_for_run(
    run_id: str,
    source: EvidenceSourceRequest,
    *,
    collector: EvidenceCollector | None = None,
) -> CollectedDocument:
    run = load_run(run_id)
    if run is None:
        raise KeyError(f"Research run not found: {run_id}")
    document = (collector or EvidenceCollector()).collect(run_id, source)
    _replace_evidence(run, document.evidence)
    providers = run.manifest.setdefault("data_providers", [])
    if "http-evidence" not in providers:
        providers.append("http-evidence")
    save_run(run)
    return document


def collect_evidence_pack(
    run_id: str,
    pack: EvidencePack,
    *,
    collector: EvidenceCollector | None = None,
) -> list[CollectedDocument]:
    run = load_run(run_id)
    if run is None:
        raise KeyError(f"Research run not found: {run_id}")
    if pack.subject.strip().lower() != run.subject.strip().lower():
        raise ValueError("Evidence pack subject does not match the research run")
    active_collector = collector or EvidenceCollector()
    return [
        collect_evidence_for_run(run_id, source, collector=active_collector)
        for source in pack.sources
    ]


def _evidence_file(run: ResearchRun, evidence: Evidence) -> Path:
    if not evidence.local_path:
        raise ValueError("Evidence has no captured local file")
    run_dir = (runs_dir() / run.id).resolve()
    path = (run_dir / evidence.local_path).resolve()
    if not path.is_relative_to(run_dir):
        raise ValueError("Evidence local path escapes the run directory")
    return path


def verify_evidence_hash(run: ResearchRun, evidence: Evidence) -> bool:
    if not evidence.source_hash:
        return False
    path = _evidence_file(run, evidence)
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == evidence.source_hash


def review_run_evidence(run_id: str, evidence_id: str, *, approved: bool) -> Evidence:
    run = load_run(run_id)
    if run is None:
        raise KeyError(f"Research run not found: {run_id}")
    evidence = next((item for item in run.evidence if item.id == evidence_id), None)
    if evidence is None:
        raise KeyError(f"Evidence not found: {evidence_id}")
    if approved and not verify_evidence_hash(run, evidence):
        raise ValueError("Evidence file hash does not match the captured source")
    evidence.status = EvidenceStatus.REVIEWED if approved else EvidenceStatus.REJECTED
    save_run(run)
    return evidence
