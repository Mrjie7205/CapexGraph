CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    subject TEXT NOT NULL,
    market TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX idx_runs_updated_at ON runs(updated_at DESC);
CREATE INDEX idx_runs_status ON runs(status);

CREATE TABLE checkpoints (
    run_id TEXT NOT NULL,
    step_key TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    message TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    output_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id, step_key),
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE TABLE tracked_candidates (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    label TEXT NOT NULL,
    benchmark_ticker TEXT NOT NULL,
    call_date TEXT NOT NULL,
    call_price REAL,
    call_benchmark_price REAL,
    stage TEXT NOT NULL,
    thesis TEXT NOT NULL DEFAULT '',
    invalidation_json TEXT NOT NULL DEFAULT '[]',
    triggers_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(run_id, node_id)
);

CREATE TABLE tracking_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracked_id TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    price REAL NOT NULL,
    benchmark_price REAL NOT NULL,
    return_pct REAL NOT NULL,
    benchmark_return_pct REAL NOT NULL,
    alpha_pct REAL NOT NULL,
    source TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE(tracked_id, as_of_date),
    FOREIGN KEY(tracked_id) REFERENCES tracked_candidates(id) ON DELETE CASCADE
);

CREATE TABLE trigger_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracked_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    operator TEXT NOT NULL,
    threshold REAL NOT NULL,
    observed_value REAL NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    as_of_date TEXT NOT NULL,
    acknowledged_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(tracked_id, metric, operator, threshold, as_of_date),
    FOREIGN KEY(tracked_id) REFERENCES tracked_candidates(id) ON DELETE CASCADE
);

INSERT INTO runs (
    id, mode, subject, market, as_of_date, status,
    created_at, updated_at, payload
) VALUES (
    'legacy-theme-001',
    'theme',
    'Legacy v0.2 theme',
    'CN',
    '2025-01-02',
    'needs_review',
    '2025-01-02T00:00:00+00:00',
    '2025-01-02T01:00:00+00:00',
    '{"id":"legacy-theme-001","mode":"theme","subject":"Legacy v0.2 theme","market":"CN","as_of_date":"2025-01-02","status":"needs_review","created_at":"2025-01-02T00:00:00+00:00","updated_at":"2025-01-02T01:00:00+00:00","pipeline":[],"nodes":[],"edges":[],"evidence":[],"candidates":[],"manifest":{"release":"0.2.0"}}'
);

INSERT INTO checkpoints (
    run_id, step_key, status, attempt, started_at, completed_at,
    message, error, output_json
) VALUES (
    'legacy-theme-001',
    'intake',
    'completed',
    1,
    '2025-01-02T00:10:00+00:00',
    '2025-01-02T00:11:00+00:00',
    'legacy checkpoint',
    '',
    '{"output":{"legacy":true}}'
);

INSERT INTO tracked_candidates (
    id, run_id, node_id, ticker, label, benchmark_ticker, call_date,
    call_price, call_benchmark_price, stage, thesis, invalidation_json,
    triggers_json, created_at, updated_at
) VALUES (
    'legacy-tracked-001',
    'legacy-theme-001',
    'legacy-node',
    '600000.SH',
    'Legacy candidate',
    '000300.SH',
    '2025-01-02',
    10.0,
    100.0,
    'watch',
    'legacy thesis',
    '["legacy invalidation"]',
    '[{"metric":"alpha_pct","operator":">=","value":5.0,"note":"legacy trigger"}]',
    '2025-01-02T01:00:00+00:00',
    '2025-01-02T01:00:00+00:00'
);

INSERT INTO tracking_snapshots (
    id, tracked_id, as_of_date, price, benchmark_price, return_pct,
    benchmark_return_pct, alpha_pct, source, recorded_at
) VALUES (
    1,
    'legacy-tracked-001',
    '2025-02-02',
    11.0,
    105.0,
    10.0,
    5.0,
    5.0,
    'manual',
    '2025-02-02T01:00:00+00:00'
);

INSERT INTO trigger_events (
    id, tracked_id, metric, operator, threshold, observed_value, note,
    as_of_date, acknowledged_at, created_at
) VALUES (
    1,
    'legacy-tracked-001',
    'alpha_pct',
    '>=',
    5.0,
    5.0,
    'legacy event',
    '2025-02-02',
    NULL,
    '2025-02-02T01:00:00+00:00'
);
