export type RunMode = "theme" | "anchor";
export type Provider = "fixture" | "codex_subscription" | "openai";
export type EvidenceMode = "partial" | "strict";

export function isProvider(value: unknown): value is Provider {
  return value === "fixture" || value === "codex_subscription" || value === "openai";
}

export interface ModelProviderStatus {
  name: Provider;
  configured: boolean;
  model?: string;
  setup_kind: string;
  billing_mode: string;
  endpoint_scope: string;
  reachability: string;
  missing: string[];
  errors: string[];
  legacy_model_setting?: boolean;
}

export interface PipelineStep {
  key: string;
  label: string;
  status: "pending" | "running" | "completed" | "blocked" | "failed";
  agent?: string;
  message: string;
  error?: string;
}

export interface SupplyChainNode {
  id: string;
  label: string;
  ticker?: string;
  layer?: string;
}

export interface SupplyChainEdge {
  id: string;
  source: string;
  target: string;
  relationship: string;
  product: string;
  basis: string;
  confidence: string;
  evidence_ids: string[];
}

export interface EvidenceItem {
  id: string;
  title: string;
  publisher?: string;
  source_url?: string;
  local_path?: string;
  excerpt: string;
  status: "proposed" | "captured" | "reviewed" | "rejected";
}

export interface EvidenceCoverage {
  mode: EvidenceMode;
  evidence_total: number;
  captured: number;
  reviewed: number;
  proposed: number;
  rejected: number;
  hash_mismatches: number;
  suggestions_total: number;
  pending_reviews: number;
  source_failures: number;
  discovery_failures: number;
  status: "empty" | "suggestions_only" | "partial" | "reviewed";
  strict_ready: boolean;
  gaps: string[];
}

export interface FinancialFact {
  id: string;
  company: string;
  ticker: string;
  statement: "income_statement" | "cash_flow" | "balance_sheet" | "supplemental";
  metric: string;
  concept: string;
  period_start?: string;
  period_end?: string;
  fiscal_year?: number;
  fiscal_period?: string;
  form?: string;
  filed_date?: string;
  accession?: string;
  value?: number;
  unit: string;
  fact_type: "reported" | "derived" | "restated" | "missing";
  source_evidence_id: string;
  source_locator: string;
  formula?: string;
  input_fact_ids: string[];
}

export type SourceSuggestionStatus =
  | "suggested"
  | "selected"
  | "capture_pending"
  | "captured"
  | "dismissed"
  | "capture_failed"
  | "duplicate";

export interface SourceSuggestion {
  id: string;
  run_id: string;
  title: string;
  url: string;
  canonical_url: string;
  kind: string;
  publisher?: string;
  authority: "regulator" | "issuer" | "other";
  reason: string;
  provider: string;
  provider_version: string;
  status: SourceSuggestionStatus;
  published_at?: string;
  evidence_id?: string;
  final_url?: string;
  duplicate_of?: string;
  error: string;
  metadata: Record<string, unknown>;
}

export interface Candidate {
  node_id: string;
  verdict: string;
  confidence: string;
  thesis: string;
  risks: string[];
  triggers: Array<{ metric: string; operator: string; value: number; note: string }>;
}

export interface ResearchRun {
  id: string;
  mode: RunMode;
  subject: string;
  market: string;
  as_of_date: string;
  status: string;
  pipeline: PipelineStep[];
  nodes: SupplyChainNode[];
  edges: SupplyChainEdge[];
  evidence: EvidenceItem[];
  candidates: Candidate[];
  manifest: Record<string, unknown>;
  updated_at: string;
}

export interface DecisionArtifact {
  research_status: string;
  summary: string;
  ranked_node_ids: string[];
  limitations: string[];
  next_actions: string[];
  disclaimer: string;
}

export type TrackingStage = "research" | "watch" | "validated" | "triggered" | "invalidated" | "archived";

export interface Scorecard {
  tracked: {
    id: string;
    run_id: string;
    node_id: string;
    ticker: string;
    label: string;
    benchmark_ticker: string;
    call_date: string;
    stage: TrackingStage;
  };
  latest?: {
    as_of_date: string;
    return_pct: number;
    benchmark_return_pct: number;
    alpha_pct: number;
  };
  events: Array<{ id: number; metric: string; observed_value: number; acknowledged_at?: string }>;
  snapshot_count: number;
  days_tracked: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: `API ${response.status}` }));
    throw new Error(payload.detail ?? `API ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function listRuns(): Promise<ResearchRun[]> {
  return request("/api/v1/runs?limit=30");
}

export async function listModelProviders(probeCodex = false): Promise<ModelProviderStatus[]> {
  const payload = await request<{ providers: ModelProviderStatus[] }>(
    `/api/v1/model/providers?probe_codex=${probeCodex ? "true" : "false"}`,
  );
  return payload.providers;
}

export function getRun(runId: string): Promise<ResearchRun> {
  return request(`/api/v1/runs/${runId}`);
}

export function createRun(
  mode: RunMode,
  subject: string,
  provider: Provider,
  market: string,
  evidenceMode: EvidenceMode,
  asOfDate?: string,
): Promise<ResearchRun> {
  return request(`/api/v1/runs/${mode}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      subject,
      market,
      provider,
      execute: false,
      evidence_mode: evidenceMode,
      as_of_date: asOfDate,
    }),
  });
}

export function executeRun(
  runId: string,
  provider: Provider,
  resume = false,
  options: { evidenceMode?: EvidenceMode; until?: string } = {},
): Promise<ResearchRun> {
  return request(`/api/v1/runs/${runId}/${resume ? "resume" : "execute"}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      provider,
      background: true,
      max_attempts: 2,
      evidence_mode: options.evidenceMode,
      until: options.until,
    }),
  });
}

export function getCoverage(runId: string): Promise<EvidenceCoverage> {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}/coverage`);
}

export function listFinancialFacts(runId: string): Promise<FinancialFact[]> {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}/financials`);
}

export function extractFinancialFacts(
  runId: string,
  identifier?: string,
): Promise<FinancialFact[]> {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}/financials/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identifier: identifier || undefined }),
  });
}

export function reportUrl(runId: string): string {
  return `/api/v1/runs/${encodeURIComponent(runId)}/report`;
}

export function reviewEvidence(
  runId: string,
  evidenceId: string,
  approved: boolean,
): Promise<EvidenceItem> {
  return request(`/api/v1/runs/${runId}/evidence/${evidenceId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved }),
  });
}

export function evidenceTextUrl(runId: string, evidenceId: string): string {
  return `/api/v1/runs/${encodeURIComponent(runId)}/evidence/${encodeURIComponent(evidenceId)}/text`;
}

export function listSourceSuggestions(runId: string): Promise<SourceSuggestion[]> {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}/sources`);
}

export function discoverSecSources(
  runId: string,
  identifier?: string,
): Promise<SourceSuggestion[]> {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}/sources/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider: "sec", identifier: identifier || undefined, limit: 10 }),
  });
}

export function suggestManualSource(
  runId: string,
  input: { url: string; title: string; publisher?: string; issuer_domains?: string[] },
): Promise<SourceSuggestion> {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}/sources/suggest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: "company_disclosure", ...input }),
  });
}

export function captureSourceSuggestion(
  runId: string,
  suggestionId: string,
  retry = false,
): Promise<SourceSuggestion> {
  const action = retry ? "retry" : "capture";
  return request(
    `/api/v1/runs/${encodeURIComponent(runId)}/sources/${encodeURIComponent(suggestionId)}/${action}`,
    { method: "POST" },
  );
}

export function dismissSourceSuggestion(
  runId: string,
  suggestionId: string,
): Promise<SourceSuggestion> {
  return request(
    `/api/v1/runs/${encodeURIComponent(runId)}/sources/${encodeURIComponent(suggestionId)}/dismiss`,
    { method: "POST" },
  );
}

export function getDecision(runId: string): Promise<DecisionArtifact> {
  return request(`/api/v1/runs/${runId}/artifacts/decision.json`);
}

export function listTracking(): Promise<Scorecard[]> {
  return request("/api/v1/tracking");
}

export function trackCandidate(runId: string, nodeId: string): Promise<unknown> {
  return request(`/api/v1/runs/${runId}/tracking`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: nodeId, capture_live: true }),
  });
}

export function captureTrackingSnapshot(trackedId: string): Promise<unknown> {
  return request(`/api/v1/tracking/${encodeURIComponent(trackedId)}/snapshots`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ capture_live: true }),
  });
}

export function setTrackingStage(trackedId: string, stage: TrackingStage): Promise<unknown> {
  return request(`/api/v1/tracking/${encodeURIComponent(trackedId)}/stage`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stage }),
  });
}
