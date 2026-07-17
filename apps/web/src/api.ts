export type RunMode = "theme" | "anchor";
export type Provider = "fixture" | "openai";

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
  excerpt: string;
  status: "proposed" | "captured" | "reviewed" | "rejected";
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

export function getRun(runId: string): Promise<ResearchRun> {
  return request(`/api/v1/runs/${runId}`);
}

export function createRun(
  mode: RunMode,
  subject: string,
  provider: Provider,
  asOfDate?: string,
): Promise<ResearchRun> {
  return request(`/api/v1/runs/${mode}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      subject,
      market: "CN",
      provider,
      execute: false,
      as_of_date: asOfDate,
    }),
  });
}

export function executeRun(
  runId: string,
  provider: Provider,
  resume = false,
): Promise<ResearchRun> {
  return request(`/api/v1/runs/${runId}/${resume ? "resume" : "execute"}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, background: true, max_attempts: 2 }),
  });
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

export function getDecision(runId: string): Promise<DecisionArtifact> {
  return request(`/api/v1/runs/${runId}/artifacts/decision.json`);
}
