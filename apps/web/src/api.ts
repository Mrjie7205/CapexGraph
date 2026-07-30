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
  transport?: string;
  billing_mode: string;
  endpoint_scope: string;
  reachability: string;
  missing: string[];
  errors: string[];
  cli_version?: string;
  auth_mode?: string;
  legacy_model_setting?: boolean;
}

export interface Jin10McpConnection {
  configured: boolean;
  enabled: boolean;
  reachability: string;
  tools: string[];
  resources: string[];
  call_budget: number;
  error?: string;
}

export interface Jin10WebSocketConnection {
  configured: boolean;
  enabled: boolean;
  reachability: string;
  streams: Record<string, unknown[]>;
  error?: string;
}

export interface CodexModelOption {
  id: string;
  display_name: string;
  is_default: boolean;
}

export interface CodexConnection {
  installed: boolean;
  authenticated: boolean;
  auth_mode?: string;
  version?: string;
  reachability: string;
  errors: string[];
  account?: {
    type?: string;
    email?: string;
    plan_type?: string;
  };
  models: CodexModelOption[];
  selected_model?: string;
  transport: string;
}

export interface ConnectionStatus {
  local_only: boolean;
  storage: string;
  jin10_mcp: Jin10McpConnection;
  jin10_websocket: Jin10WebSocketConnection;
  codex_subscription: CodexConnection;
}

export interface CodexLoginState {
  login_id?: string;
  completed?: boolean;
  success?: boolean;
  error?: string;
  auth_url?: string;
  connection?: CodexConnection;
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

export type LiveChannel = "mcp" | "websocket" | "fixture";
export type LiveHealth = "not_configured" | "active" | "degraded" | "off" | "exhausted" | "replay";
export type LiveAlertState = "unread" | "read" | "dismissed" | "muted";

export interface LiveCheckpoint {
  provider: string;
  channel: LiveChannel;
  stream: string;
  cursor: string;
  last_external_id?: string;
  last_published_at?: string;
  last_observed_at?: string;
  health: LiveHealth;
  calls_used: number;
  call_budget?: number;
  updated_at: string;
  error: string;
  metadata: Record<string, unknown>;
}

export interface LiveSignal {
  id: string;
  signal_key: string;
  version: number;
  category: "flash" | "calendar" | "quote" | "news" | "other";
  title: string;
  published_at: string;
  first_observed_at: string;
  last_observed_at: string;
  observation_ids: string[];
  channels: LiveChannel[];
  match_status: "single_channel" | "matched" | "divergent";
  verification_state: "signal_only" | "official_source_pending" | "evidence_linked";
  revision_reason: string;
  metadata: Record<string, unknown>;
}

export interface LiveObservation {
  id: string;
  provider: string;
  provider_version: string;
  channel: LiveChannel;
  stream: string;
  external_id: string;
  category: string;
  title: string;
  published_at: string;
  scheduled_at?: string;
  observed_at: string;
  retention_class: string;
  metadata: Record<string, unknown>;
}

export interface LiveAssessment {
  signal_version_id: string;
  ruleset_version: string;
  relevance: number;
  urgency: number;
  novelty: number;
  importance: number;
  total_score: number;
  matched_entities: string[];
  matched_themes: string[];
  matched_graph_nodes: string[];
  injection_flags: string[];
  should_alert: boolean;
  rationale: string[];
}

export interface LiveProposal {
  id: string;
  model_provider?: string;
  model?: string;
  themes: string[];
  entities: string[];
  direction: string;
  horizon: string;
  impact_score: number;
  confidence: number;
  transmission_path: string[];
  price_confirmation: string;
  evidence_gaps: string[];
  recommended_action: string;
  trigger_conditions: string[];
  invalidations: string[];
}

export interface LiveAnalysis {
  id: string;
  status: "rules_only" | "completed" | "failed" | "skipped";
  model_provider?: string;
  model?: string;
  model_call_count: number;
  retry_count: number;
  estimated_cost_usd?: number;
  cost_status: string;
  failure: string;
  created_at: string;
}

export interface LiveAlert {
  id?: number;
  signal_key: string;
  state: LiveAlertState;
  score: number;
  created_at: string;
  updated_at: string;
}

export type LiveVerificationTaskStatus =
  | "pending"
  | "source_suggested"
  | "capture_pending"
  | "captured"
  | "evidence_linked"
  | "rejected"
  | "failed"
  | "cancelled";

export interface LiveVerificationTask {
  id: string;
  signal_key: string;
  signal_version_id: string;
  query: string;
  status: LiveVerificationTaskStatus;
  run_id?: string;
  source_suggestion_id?: string;
  evidence_id?: string;
  evidence_link_id?: string;
  note: string;
  attempts: number;
  error: string;
  created_at: string;
  updated_at: string;
}

export interface LiveEvidenceLink {
  id: string;
  signal_key: string;
  signal_version_id: string;
  verification_task_id: string;
  run_id: string;
  evidence_id: string;
  source_hash: string;
  link_hash: string;
  linked_at: string;
  linked_by: string;
}

export interface LiveRunContextLink {
  id: string;
  signal_key: string;
  signal_version_id: string;
  run_id: string;
  parent_run_id?: string;
  context_hash: string;
  context: Record<string, unknown>;
  note: string;
  created_at: string;
  created_by: string;
}

export interface LiveAuditEntry {
  id?: number;
  signal_key: string;
  event_type: string;
  object_type: string;
  object_id: string;
  actor: string;
  summary: string;
  occurred_at: string;
  details: Record<string, unknown>;
}

export interface LiveSoakReport {
  id: string;
  mode: string;
  cycles: number;
  observations: number;
  created_versions: number;
  duplicates: number;
  injected_failures: number;
  observed_failures: number;
  checkpoint_isolation_ok: boolean;
  passed: boolean;
  started_at: string;
  completed_at: string;
  notes: string[];
}

export interface LiveVerificationTaskRecord {
  task: LiveVerificationTask;
  source_suggestion?: SourceSuggestion;
  evidence?: EvidenceItem;
  evidence_link?: LiveEvidenceLink;
  run?: ResearchRun;
}

export interface LiveLinkedRunResponse {
  run: ResearchRun;
  link: LiveRunContextLink;
}

export interface LiveEventRecord {
  signal: LiveSignal;
  observations: LiveObservation[];
  assessment?: LiveAssessment;
  proposal?: LiveProposal;
  analysis?: LiveAnalysis;
  alert?: LiveAlert;
  actions: Array<{ id: string; action: string; note: string; created_at: string }>;
  verification_tasks: LiveVerificationTask[];
  evidence_links: LiveEvidenceLink[];
  run_links: LiveRunContextLink[];
  trust_notice: string;
}

export interface LiveCoverage {
  total_signals: number;
  matched: number;
  divergent: number;
  mcp_only: number;
  websocket_only: number;
  fixture_only: number;
  overlap_ratio: number;
  delivery_delay_p50_seconds?: number;
  delivery_delay_p95_seconds?: number;
  freshest_by_channel: Record<string, string | undefined>;
}

export interface LiveSettings {
  mcp_enabled: boolean;
  websocket_enabled: boolean;
  flash_enabled: boolean;
  calendar_enabled: boolean;
  quote_enabled: boolean;
  normal_poll_seconds: number;
  urgent_poll_seconds: number;
  quiet_poll_seconds: number;
  alert_score_threshold: number;
  model_score_threshold: number;
  cooldown_seconds: number;
  include_keywords: string[];
  exclude_keywords: string[];
  entity_aliases: Record<string, string[]>;
  theme_keywords: Record<string, string[]>;
  desktop_notifications: boolean;
  model_provider?: Provider;
  updated_at: string;
}

export interface LiveStatus {
  running: boolean;
  started_at?: string;
  database: string;
  configuration: {
    provider: string;
    mcp: { enabled: boolean; configured: boolean; call_budget: number; hard_limit: number; missing: string[] };
    websocket: { enabled: boolean; configured: boolean; streams: Record<string, unknown[]>; missing: string[] };
    errors: string[];
  };
  settings: LiveSettings;
  checkpoints: LiveCheckpoint[];
  unread_alerts: number;
  coverage: LiveCoverage;
  latest_soak?: LiveSoakReport;
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

export function getConnections(probeMcp = false): Promise<ConnectionStatus> {
  return request(`/api/v1/connections?probe_mcp=${probeMcp ? "true" : "false"}`);
}

export function connectJin10Mcp(secret: string): Promise<Jin10McpConnection> {
  return request("/api/v1/connections/jin10-mcp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ secret }),
  });
}

export function disconnectJin10Mcp(): Promise<Jin10McpConnection> {
  return request("/api/v1/connections/jin10-mcp/disconnect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed: true }),
  });
}

export function connectJin10WebSocket(secret: string): Promise<Jin10WebSocketConnection> {
  return request("/api/v1/connections/jin10-websocket", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ secret }),
  });
}

export function disconnectJin10WebSocket(): Promise<Jin10WebSocketConnection> {
  return request("/api/v1/connections/jin10-websocket/disconnect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed: true }),
  });
}

export function startCodexLogin(): Promise<CodexLoginState> {
  return request("/api/v1/connections/codex/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed: true }),
  });
}

export function getCodexLoginState(): Promise<CodexLoginState> {
  return request("/api/v1/connections/codex/login");
}

export function saveCodexModel(model: string): Promise<CodexConnection> {
  return request("/api/v1/connections/codex/model", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
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

export function getLiveStatus(): Promise<LiveStatus> {
  return request("/api/v1/live/status");
}

export function listLiveEvents(params: Record<string, string> = {}): Promise<LiveEventRecord[]> {
  const query = new URLSearchParams(params).toString();
  return request(`/api/v1/live/events${query ? `?${query}` : ""}`);
}

export function getLiveEvent(signalReference: string): Promise<LiveEventRecord> {
  return request(`/api/v1/live/events/${encodeURIComponent(signalReference)}`);
}

export function getLiveCoverage(): Promise<LiveCoverage> {
  return request("/api/v1/live/coverage");
}

export function pollLiveStream(stream: "flash" | "calendar"): Promise<unknown> {
  return request("/api/v1/live/poll", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stream }),
  });
}

export function replayLiveDemo(): Promise<unknown> {
  return request("/api/v1/live/demo", { method: "POST" });
}

export function setLiveMonitor(running: boolean): Promise<LiveStatus> {
  return request(`/api/v1/live/monitor/${running ? "start" : "stop"}`, {
    method: "POST",
  });
}

export function getLiveSettings(): Promise<LiveSettings> {
  return request("/api/v1/live/settings");
}

export function patchLiveSettings(settings: Partial<LiveSettings>): Promise<LiveSettings> {
  return request("/api/v1/live/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

export function analyzeLiveEvent(
  signalId: string,
  provider?: Provider,
  forceModel = false,
): Promise<{ proposal: LiveProposal; analysis: LiveAnalysis }> {
  return request(`/api/v1/live/events/${encodeURIComponent(signalId)}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, force_model: forceModel }),
  });
}

export function openLiveVerificationTask(
  signalReference: string,
  runId?: string,
): Promise<LiveVerificationTaskRecord> {
  return request(`/api/v1/live/events/${encodeURIComponent(signalReference)}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      run_id: runId || undefined,
      confirmed: true,
      note: "Opened from the Live Desk Research Bridge.",
    }),
  });
}

export function getLiveVerificationTask(taskId: string): Promise<LiveVerificationTaskRecord> {
  return request(`/api/v1/live/verification-tasks/${encodeURIComponent(taskId)}`);
}

export function addLiveVerificationSource(
  taskId: string,
  input: {
    run_id?: string;
    url: string;
    title: string;
    publisher?: string;
    issuer_domains?: string[];
  },
): Promise<LiveVerificationTaskRecord> {
  return request(`/api/v1/live/verification-tasks/${encodeURIComponent(taskId)}/sources`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...input,
      kind: "company_disclosure",
      confirmed: true,
    }),
  });
}

export function captureLiveVerificationSource(
  taskId: string,
  retry = false,
): Promise<LiveVerificationTaskRecord> {
  return request(`/api/v1/live/verification-tasks/${encodeURIComponent(taskId)}/capture`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ retry, confirmed: true }),
  });
}

export function reviewLiveVerificationEvidence(
  taskId: string,
  approved: boolean,
): Promise<LiveVerificationTaskRecord> {
  return request(`/api/v1/live/verification-tasks/${encodeURIComponent(taskId)}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved, confirmed: true }),
  });
}

export function attachLiveContextToRun(
  runId: string,
  signalReference: string,
): Promise<LiveRunContextLink> {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}/live-context`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      signal_reference: signalReference,
      confirmed: true,
      note: "Immutable context attached from the Live Desk Research Bridge.",
    }),
  });
}

export function createLiveLinkedRun(
  signalReference: string,
  input: {
    parent_run_id?: string;
    mode?: RunMode;
    subject?: string;
    market?: string;
    provider?: Provider;
    note?: string;
  },
): Promise<LiveLinkedRunResponse> {
  const endpoint = input.parent_run_id ? "reevaluate" : "runs";
  return request(`/api/v1/live/events/${encodeURIComponent(signalReference)}/${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...input,
      confirmed: true,
    }),
  });
}

export function listLiveAudit(signalReference: string): Promise<LiveAuditEntry[]> {
  return request(`/api/v1/live/events/${encodeURIComponent(signalReference)}/audit`);
}

export function actOnLiveEvent(
  signalId: string,
  action: "read" | "dismiss" | "mute" | "watch" | "verify" | "ignore",
  note = "",
): Promise<unknown> {
  return request(`/api/v1/live/events/${encodeURIComponent(signalId)}/actions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, note }),
  });
}

export function liveStreamUrl(): string {
  return "/api/v1/live/stream";
}
