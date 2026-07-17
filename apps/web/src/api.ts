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
}

export async function createRun(mode: RunMode, subject: string): Promise<ResearchRun> {
  const response = await fetch(`/api/v1/runs/${mode}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject, market: "CN" }),
  });
  if (!response.ok) throw new Error(`API ${response.status}`);
  return response.json() as Promise<ResearchRun>;
}
