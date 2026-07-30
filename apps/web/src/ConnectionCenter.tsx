import { useEffect, useMemo, useState } from "react";
import {
  connectJin10Mcp,
  connectJin10WebSocket,
  disconnectJin10Mcp,
  disconnectJin10WebSocket,
  getCodexLoginState,
  getConnections,
  saveCodexModel,
  startCodexLogin,
  type ConnectionStatus,
} from "./api";

interface ConnectionCenterProps {
  open: boolean;
  onClose: () => void;
  onChanged: () => void;
}

function connectionTone(reachability: string): string {
  if (["ready", "active", "reachable"].includes(reachability)) return "ready";
  if (["not_configured", "not_installed", "login_required"].includes(reachability)) return "waiting";
  if (reachability === "live_probe_pending" || reachability === "not_checked") return "standby";
  return "error";
}

function connectionLabel(reachability: string): string {
  return {
    ready: "已连接",
    active: "运行中",
    reachable: "可用",
    not_configured: "等待凭据",
    not_installed: "未安装",
    login_required: "等待登录",
    live_probe_pending: "已保存 · 待启动验证",
    not_checked: "等待检测",
    wrong_auth_mode: "不是 ChatGPT 登录",
    unreachable: "连接失败",
  }[reachability] ?? reachability.replaceAll("_", " ");
}

export function ConnectionCenter({
  open,
  onClose,
  onChanged,
}: ConnectionCenterProps) {
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [mcpToken, setMcpToken] = useState("");
  const [websocketKey, setWebsocketKey] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [busy, setBusy] = useState("");
  const [loginPending, setLoginPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function announceChange() {
    onChanged();
    window.dispatchEvent(new Event("capexgraph:connections-changed"));
  }

  async function refresh(probeMcp = false) {
    const next = await getConnections(probeMcp);
    setStatus(next);
    const defaultModel =
      next.codex_subscription.selected_model
      ?? next.codex_subscription.models.find((item) => item.is_default)?.id
      ?? next.codex_subscription.models[0]?.id
      ?? "";
    setSelectedModel(defaultModel);
    return next;
  }

  useEffect(() => {
    if (!open) return;
    setError("");
    setNotice("");
    refresh().catch((reason) => {
      setError(reason instanceof Error ? reason.message : "连接状态读取失败");
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open, onClose]);

  useEffect(() => {
    if (!loginPending || !open) return;
    const timer = window.setInterval(async () => {
      try {
        const state = await getCodexLoginState();
        if (state.connection?.authenticated || (state.completed && state.success)) {
          setLoginPending(false);
          setNotice("Codex 已通过 ChatGPT 订阅连接。");
          await refresh();
          announceChange();
        } else if (state.completed && !state.success) {
          setLoginPending(false);
          setError(state.error || "Codex 登录失败，请重新尝试。");
        }
      } catch {
        // Keep the browser flow alive; the next poll can recover.
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [loginPending, open, onChanged]);

  const connectedCount = useMemo(() => {
    if (!status) return 0;
    return [
      status.jin10_mcp.reachability === "ready",
      status.jin10_websocket.configured,
      status.codex_subscription.authenticated,
    ].filter(Boolean).length;
  }, [status]);

  async function connectMcp() {
    if (!mcpToken.trim()) return;
    setBusy("mcp");
    setError("");
    setNotice("");
    try {
      await connectJin10Mcp(mcpToken.trim());
      setMcpToken("");
      await refresh(true);
      announceChange();
      setNotice("金十 MCP 握手成功，正式轮询通道已就绪。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "MCP 连接失败");
    } finally {
      setBusy("");
    }
  }

  async function removeMcp() {
    if (!window.confirm("断开金十 MCP，并从本机配置中删除 Token？")) return;
    setBusy("mcp");
    setError("");
    try {
      await disconnectJin10Mcp();
      await refresh();
      announceChange();
      setNotice("金十 MCP 已断开。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "MCP 断开失败");
    } finally {
      setBusy("");
    }
  }

  async function connectWebSocket() {
    if (!websocketKey.trim()) return;
    setBusy("websocket");
    setError("");
    setNotice("");
    try {
      await connectJin10WebSocket(websocketKey.trim());
      setWebsocketKey("");
      await refresh();
      announceChange();
      setNotice("WebSocket Secret-Key 已保存；启动 Monitor 后完成真实流验证。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "WebSocket 配置失败");
    } finally {
      setBusy("");
    }
  }

  async function removeWebSocket() {
    if (!window.confirm("断开金十 WebSocket，并从本机配置中删除 Secret-Key？")) return;
    setBusy("websocket");
    setError("");
    try {
      await disconnectJin10WebSocket();
      await refresh();
      announceChange();
      setNotice("金十 WebSocket 已断开。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "WebSocket 断开失败");
    } finally {
      setBusy("");
    }
  }

  async function beginCodexLogin() {
    const loginTab = window.open("about:blank", "_blank");
    setBusy("codex");
    setError("");
    setNotice("");
    try {
      const login = await startCodexLogin();
      if (!login.auth_url) throw new Error("Codex 没有返回登录地址。");
      if (loginTab) {
        loginTab.opener = null;
        loginTab.location.replace(login.auth_url);
      } else {
        window.location.assign(login.auth_url);
      }
      setLoginPending(true);
      setNotice("已打开 OpenAI 官方登录页；完成登录后本面板会自动更新。");
    } catch (reason) {
      loginTab?.close();
      setError(reason instanceof Error ? reason.message : "Codex 登录无法启动");
    } finally {
      setBusy("");
    }
  }

  async function persistCodexModel() {
    if (!selectedModel) return;
    setBusy("codex-model");
    setError("");
    try {
      await saveCodexModel(selectedModel);
      await refresh();
      announceChange();
      setNotice(`Codex 研究模型已设为 ${selectedModel}。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "模型保存失败");
    } finally {
      setBusy("");
    }
  }

  if (!open) return null;

  const mcp = status?.jin10_mcp;
  const websocket = status?.jin10_websocket;
  const codex = status?.codex_subscription;

  return (
    <div className="connection-scrim" role="presentation" onMouseDown={onClose}>
      <aside
        className="connection-center"
        role="dialog"
        aria-modal="true"
        aria-labelledby="connection-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="connection-head">
          <div>
            <span>Local integration desk / 本机连接</span>
            <h2 id="connection-title">Connection Center</h2>
            <p>凭据只进入本机后端；浏览器不会读取、回显或同步它们。</p>
          </div>
          <div className="connection-score">
            <strong>{connectedCount}<small>/ 3</small></strong>
            <span>channels ready</span>
          </div>
          <button className="connection-close" onClick={onClose} aria-label="关闭连接中心">×</button>
        </header>

        {error && <div className="connection-message error">{error}</div>}
        {notice && <div className="connection-message success">{notice}</div>}

        {!status ? (
          <div className="connection-loading">
            <i />
            <strong>正在检查本机连接…</strong>
            <span>读取金十通道与 Codex ChatGPT 登录状态。</span>
          </div>
        ) : (
        <div className="connection-grid">
          <article className="connection-card">
            <div className="connection-card-head">
              <div className={`connection-orb ${connectionTone(mcp?.reachability ?? "not_checked")}`} />
              <div><span>Market signal · 01</span><h3>金十 MCP</h3></div>
              <b className={connectionTone(mcp?.reachability ?? "not_checked")}>
                {connectionLabel(mcp?.reachability ?? "not_checked")}
              </b>
            </div>
            <p>正式快讯和财经日历轮询。连接时会完成 MCP 握手、工具发现与资源发现。</p>
            {mcp?.configured ? (
              <div className="connection-facts">
                <span><small>Daily guard</small>{mcp.call_budget} / 1500</span>
                <span><small>Tools</small>{mcp.tools.length || "待检测"}</span>
                <span><small>Storage</small>本机 .env</span>
              </div>
            ) : (
              <label className="secret-field">
                Bearer Token
                <input
                  type="password"
                  autoComplete="new-password"
                  value={mcpToken}
                  onChange={(event) => setMcpToken(event.target.value)}
                  placeholder="粘贴金十 MCP Token"
                />
              </label>
            )}
            <footer>
              {mcp?.configured ? (
                <>
                  <button disabled={Boolean(busy)} onClick={() => refresh(true)}>重新检测</button>
                  <button className="quiet danger" disabled={Boolean(busy)} onClick={removeMcp}>断开</button>
                </>
              ) : (
                <button disabled={Boolean(busy) || !mcpToken.trim()} onClick={connectMcp}>
                  {busy === "mcp" ? "正在握手…" : "连接并验证"}
                </button>
              )}
            </footer>
          </article>

          <article className="connection-card">
            <div className="connection-card-head">
              <div className={`connection-orb ${connectionTone(websocket?.reachability ?? "not_checked")}`} />
              <div><span>Market signal · 02</span><h3>金十 WebSocket</h3></div>
              <b className={connectionTone(websocket?.reachability ?? "not_checked")}>
                {connectionLabel(websocket?.reachability ?? "not_checked")}
              </b>
            </div>
            <p>低延迟推送，与 MCP 同级运行。保存密钥后需在 Live Desk 启动 Monitor 完成实流验证。</p>
            {websocket?.configured ? (
              <div className="connection-facts">
                <span><small>Flash</small>1, 4</span>
                <span><small>Calendar</small>cj</span>
                <span><small>Next</small>启动 Monitor</span>
              </div>
            ) : (
              <label className="secret-field">
                Secret-Key
                <input
                  type="password"
                  autoComplete="new-password"
                  value={websocketKey}
                  onChange={(event) => setWebsocketKey(event.target.value)}
                  placeholder="粘贴开放平台 Secret-Key"
                />
              </label>
            )}
            <footer>
              {websocket?.configured ? (
                <button className="quiet danger" disabled={Boolean(busy)} onClick={removeWebSocket}>断开</button>
              ) : (
                <button disabled={Boolean(busy) || !websocketKey.trim()} onClick={connectWebSocket}>
                  {busy === "websocket" ? "正在保存…" : "保存连接"}
                </button>
              )}
            </footer>
          </article>

          <article className="connection-card codex-card">
            <div className="connection-card-head">
              <div className={`connection-orb ${connectionTone(codex?.reachability ?? "not_checked")}`} />
              <div><span>Reasoning · 03</span><h3>Codex Subscription</h3></div>
              <b className={connectionTone(codex?.reachability ?? "not_checked")}>
                {connectionLabel(codex?.reachability ?? "not_checked")}
              </b>
            </div>
            <p>通过 OpenAI 官方 Codex CLI 使用 ChatGPT 订阅；不需要 OpenAI Platform API Key。</p>
            {!codex?.installed ? (
              <div className="codex-install">
                <strong>没有检测到 Codex CLI</strong>
                <span>先安装官方 Codex，再返回此处登录。</span>
                <a href="https://learn.chatgpt.com/docs/cli" target="_blank" rel="noreferrer">打开官方安装说明 ↗</a>
              </div>
            ) : codex.authenticated ? (
              <>
                <div className="connection-facts">
                  <span><small>Account</small>{codex.account?.email ?? "ChatGPT"}</span>
                  <span><small>Plan</small>{codex.account?.plan_type ?? "已登录"}</span>
                  <span><small>CLI</small>{codex.version?.replace("codex-cli ", "v") ?? "ready"}</span>
                </div>
                <label className="model-field">
                  Research model
                  <select value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)}>
                    {codex.models.map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.display_name}{model.is_default ? " · default" : ""}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            ) : (
              <div className="codex-login-note">
                <strong>Codex CLI 已安装</strong>
                <span>点击后会打开 OpenAI 官方 ChatGPT 登录页。</span>
              </div>
            )}
            <footer>
              {codex?.authenticated ? (
                <>
                  <button disabled={Boolean(busy) || !selectedModel} onClick={persistCodexModel}>
                    {busy === "codex-model" ? "正在保存…" : "保存模型"}
                  </button>
                  <button className="quiet" disabled={Boolean(busy)} onClick={() => refresh()}>刷新账号</button>
                </>
              ) : codex?.installed ? (
                <button disabled={Boolean(busy) || loginPending} onClick={beginCodexLogin}>
                  {loginPending ? "等待登录完成…" : "使用 ChatGPT 登录"}
                </button>
              ) : null}
            </footer>
          </article>
        </div>
        )}

        <footer className="connection-foot">
          <p><b>Local-only boundary</b> Token 写入被 Git 忽略的项目 `.env`；Codex OAuth 由官方 CLI 和系统凭据存储管理。</p>
          <button onClick={onClose}>完成</button>
        </footer>
      </aside>
    </div>
  );
}
