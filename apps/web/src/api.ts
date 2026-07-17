export type RunMode = "theme" | "anchor";

export interface PipelineStep {
  key: string;
  label: string;
  status: "pending" | "running" | "completed" | "blocked" | "failed";
  agent?: string;
  message: string;
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
}

export interface SupplyChainNode {
  id: string;
  label: string;
  ticker?: string;
}

export interface SupplyChainEdge {
  id: string;
  source: string;
  target: string;
  product: string;
  confidence: string;
  evidence_ids: string[];
}

export interface EvidenceItem {
  id: string;
  title: string;
}

export interface Candidate {
  node_id: string;
  verdict: string;
  confidence: string;
}

interface CreateRunOptions {
  provider?: "fixture" | "openai";
  execute?: boolean;
  asOfDate?: string;
}

export async function createRun(
  mode: RunMode,
  subject: string,
  options: CreateRunOptions = {},
): Promise<ResearchRun> {
  const response = await fetch(`/api/v1/runs/${mode}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      subject,
      market: "CN",
      provider: options.provider,
      execute: options.execute ?? false,
      as_of_date: options.asOfDate,
    }),
  });
  if (!response.ok) throw new Error(`API ${response.status}`);
  return response.json() as Promise<ResearchRun>;
}
