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
import { BilingualText, humanizeUiValue, translateUiValue } from "./UiText";

interface SourceQueueProps {
  run: ResearchRun | null;
  onRunUpdated: (run: ResearchRun) => void;
  onError: (message: string) => void;
}

function sourceReasonLabel(value: string): string {
  const fixed: Record<string, string> = {
    "URL uses a recognized regulator domain.": "网址使用已识别的监管机构域名。",
    "URL matches an issuer domain supplied for this run.": "网址与该研究登记的公司官网域名匹配。",
    "User supplied this public URL; official ownership is not verified.":
      "该公开网址由用户提供，官方归属尚未验证。",
  };
  if (fixed[value]) return fixed[value];
  const edgar = value.match(/^Official EDGAR (.+) filing discovered for (.+)\.$/);
  if (edgar) return `已为 ${edgar[2]} 发现 EDGAR 官方 ${edgar[1]} 申报文件。`;
  return value;
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
      onError(reason instanceof Error ? reason.message : "官方来源队列暂不可用");
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
      onError(reason instanceof Error ? reason.message : "SEC 文件发现失败");
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
      onError(reason instanceof Error ? reason.message : "来源候选登记失败");
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
      onError(reason instanceof Error ? reason.message : "来源操作失败");
    } finally {
      setBusyId("");
    }
  }

  return (
    <section className="source-workspace panel" id="sources">
      <div className="panel-title">
        <BilingualText zh="官方来源 / 审核队列" en="Official sources / Review queue" />
        <b>{items.length} 条候选<small>Suggestions</small></b>
      </div>
      {!run && <p className="empty-state">请先选择研究任务，再发现官方来源。</p>}
      {run && (
        <>
          <div className="source-tools">
            <div>
              <BilingualText className="tool-label" zh="SEC / EDGAR 文件发现" en="SEC / EDGAR discovery" />
              <div className="source-tool-row">
                <input
                  aria-label="SEC 股票代码、公司名或 CIK"
                  placeholder="准确的股票代码、公司名或 CIK"
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                />
                <button disabled={queueBusy} onClick={discover}>
                  <BilingualText
                    zh={queueBusy ? "正在发现…" : "发现监管文件"}
                    en={queueBusy ? "Working…" : "Discover filings"}
                    compact
                    align="center"
                  />
                </button>
              </div>
              <small>候选来源在完成捕获与人工审核前，不能作为可信证据。</small>
            </div>
            <form onSubmit={addManual}>
              <BilingualText className="tool-label" zh="添加公司或监管机构网址" en="Add issuer or regulator URL" />
              <div className="manual-source-grid">
                <input
                  aria-label="官方来源标题"
                  placeholder="来源标题"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
                <input
                  aria-label="官方来源网址"
                  placeholder="https://…"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                />
                <input
                  aria-label="公司官网域名"
                  placeholder="公司官网域名（选填）"
                  value={issuerDomain}
                  onChange={(event) => setIssuerDomain(event.target.value)}
                />
                <button disabled={queueBusy || !title.trim() || !url.trim()}>
                  <BilingualText zh="加入队列" en="Add to queue" compact align="center" />
                </button>
              </div>
            </form>
          </div>
          <div className="suggestion-list">
            {items.length === 0 && (
              <p className="empty-state">
                暂无来源候选。你可以发现 SEC 文件，或添加已知的官方网站。
              </p>
            )}
            {items.map((item) => (
              <article className={`suggestion-card ${item.status}`} key={item.id}>
                <div className="suggestion-meta">
                  <span>{translateUiValue(item.authority)}<small>{humanizeUiValue(item.authority)}</small></span>
                  <span>{translateUiValue(item.kind)}<small>{humanizeUiValue(item.kind)}</small></span>
                  <span>{translateUiValue(item.status)}<small>{humanizeUiValue(item.status)}</small></span>
                </div>
                <div>
                  <strong>{item.title}</strong>
                  <p>
                    {sourceReasonLabel(item.reason)}
                    {sourceReasonLabel(item.reason) !== item.reason && <small>{item.reason}</small>}
                  </p>
                  <small>{item.provider}@{item.provider_version}</small>
                  {item.error && <small className="suggestion-error">{item.error}</small>}
                  {item.duplicate_of && <small>与 {item.duplicate_of} 重复 · Duplicate</small>}
                  {Number(item.metadata.duplicate_url_count ?? 0) > 0 && (
                    <small>
                      同一规范网址另被推荐 {Number(item.metadata.duplicate_url_count)} 次
                    </small>
                  )}
                </div>
                <div className="suggestion-actions">
                  <a href={item.url} target="_blank" rel="noreferrer">查看<small>Inspect ↗</small></a>
                  {item.status === "suggested" && (
                    <>
                      <button
                        disabled={busyId === item.id}
                        onClick={() => act(item, "capture")}
                      >
                        捕获<small>Capture</small>
                      </button>
                      <button
                        disabled={busyId === item.id}
                        onClick={() => act(item, "dismiss")}
                      >
                        忽略<small>Dismiss</small>
                      </button>
                    </>
                  )}
                  {item.status === "capture_failed" && (
                    <>
                      <button
                        disabled={busyId === item.id}
                        onClick={() => act(item, "retry")}
                      >
                        重试<small>Retry</small>
                      </button>
                      <button
                        disabled={busyId === item.id}
                        onClick={() => act(item, "dismiss")}
                      >
                        忽略<small>Dismiss</small>
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
