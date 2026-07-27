import { FormEvent, useEffect, useState } from "react";
import {
  captureSourceSuggestion,
  dismissSourceSuggestion,
  discoverSecSources,
  getRun,
  listSourceSuggestions,
  suggestManualSource,
  type ResearchRun,
  type SourceSuggestion,
} from "./api";

interface SourceQueueProps {
  run: ResearchRun | null;
  onRunUpdated: (run: ResearchRun) => void;
  onError: (message: string) => void;
}

export function SourceQueue({ run, onRunUpdated, onError }: SourceQueueProps) {
  const [items, setItems] = useState<SourceSuggestion[]>([]);
  const [identifier, setIdentifier] = useState("");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [issuerDomain, setIssuerDomain] = useState("");
  const [busyId, setBusyId] = useState("");
  const [queueBusy, setQueueBusy] = useState(false);

  async function refresh() {
    if (!run) {
      setItems([]);
      return;
    }
    setItems(await listSourceSuggestions(run.id));
  }

  useEffect(() => {
    setIdentifier("");
    setUrl("");
    setTitle("");
    setIssuerDomain("");
    refresh().catch((reason) => {
      onError(reason instanceof Error ? reason.message : "Source queue unavailable");
    });
  }, [run?.id]);

  async function discover() {
    if (!run) return;
    setQueueBusy(true);
    onError("");
    try {
      await discoverSecSources(run.id, identifier.trim() || undefined);
      await refresh();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "SEC discovery failed");
    } finally {
      setQueueBusy(false);
    }
  }

  async function addManual(event: FormEvent) {
    event.preventDefault();
    if (!run || !url.trim() || !title.trim()) return;
    setQueueBusy(true);
    onError("");
    try {
      await suggestManualSource(run.id, {
        url: url.trim(),
        title: title.trim(),
        issuer_domains: issuerDomain.trim() ? [issuerDomain.trim()] : [],
      });
      setUrl("");
      setTitle("");
      await refresh();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Source suggestion failed");
    } finally {
      setQueueBusy(false);
    }
  }

  async function act(item: SourceSuggestion, action: "capture" | "retry" | "dismiss") {
    if (!run) return;
    setBusyId(item.id);
    onError("");
    try {
      if (action === "dismiss") {
        await dismissSourceSuggestion(run.id, item.id);
      } else {
        await captureSourceSuggestion(run.id, item.id, action === "retry");
        onRunUpdated(await getRun(run.id));
      }
      await refresh();
    } catch (reason) {
      await refresh().catch(() => undefined);
      onError(reason instanceof Error ? reason.message : "Source action failed");
    } finally {
      setBusyId("");
    }
  }

  return (
    <section className="source-workspace panel" id="sources">
      <div className="panel-title">
        <span>Official sources / Review queue</span>
        <b>{items.length} SUGGESTIONS</b>
      </div>
      {!run && <p className="empty-state">Select a run before discovering official sources.</p>}
      {run && (
        <>
          <div className="source-tools">
            <div>
              <span className="tool-label">SEC / EDGAR discovery</span>
              <div className="source-tool-row">
                <input
                  aria-label="SEC ticker company or CIK"
                  placeholder="Exact ticker, company, or CIK"
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                />
                <button disabled={queueBusy} onClick={discover}>
                  {queueBusy ? "Working…" : "Discover filings"}
                </button>
              </div>
              <small>Suggestions remain untrusted until you capture and review them.</small>
            </div>
            <form onSubmit={addManual}>
              <span className="tool-label">Add issuer or regulator URL</span>
              <div className="manual-source-grid">
                <input
                  aria-label="Official source title"
                  placeholder="Source title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
                <input
                  aria-label="Official source URL"
                  placeholder="https://…"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                />
                <input
                  aria-label="Issuer domain"
                  placeholder="Issuer domain (optional)"
                  value={issuerDomain}
                  onChange={(event) => setIssuerDomain(event.target.value)}
                />
                <button disabled={queueBusy || !title.trim() || !url.trim()}>
                  Add to queue
                </button>
              </div>
            </form>
          </div>
          <div className="suggestion-list">
            {items.length === 0 && (
              <p className="empty-state">
                No suggestions yet. Discover SEC filings or add a known official URL.
              </p>
            )}
            {items.map((item) => (
              <article className={`suggestion-card ${item.status}`} key={item.id}>
                <div className="suggestion-meta">
                  <span>{item.authority}</span>
                  <span>{item.kind}</span>
                  <span>{item.status}</span>
                </div>
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.reason}</p>
                  <small>{item.provider}@{item.provider_version}</small>
                  {item.error && <small className="suggestion-error">{item.error}</small>}
                  {item.duplicate_of && <small>Duplicate of {item.duplicate_of}</small>}
                  {Number(item.metadata.duplicate_url_count ?? 0) > 0 && (
                    <small>
                      Same canonical URL suggested{" "}
                      {Number(item.metadata.duplicate_url_count)} more time(s)
                    </small>
                  )}
                </div>
                <div className="suggestion-actions">
                  <a href={item.url} target="_blank" rel="noreferrer">Inspect ↗</a>
                  {item.status === "suggested" && (
                    <>
                      <button
                        disabled={busyId === item.id}
                        onClick={() => act(item, "capture")}
                      >
                        Capture
                      </button>
                      <button
                        disabled={busyId === item.id}
                        onClick={() => act(item, "dismiss")}
                      >
                        Dismiss
                      </button>
                    </>
                  )}
                  {item.status === "capture_failed" && (
                    <>
                      <button
                        disabled={busyId === item.id}
                        onClick={() => act(item, "retry")}
                      >
                        Retry
                      </button>
                      <button
                        disabled={busyId === item.id}
                        onClick={() => act(item, "dismiss")}
                      >
                        Dismiss
                      </button>
                    </>
                  )}
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
