# Security policy

Please report vulnerabilities privately through GitHub Security Advisories rather than a public
issue. Include the affected version, reproduction steps, impact, and any proposed mitigation.

CapexGraph treats remote evidence as hostile input. The collector blocks localhost, credentials
in URLs, and private, loopback, link-local, and reserved IP ranges; follows bounded downloads;
and validates redirect destinations. These controls reduce risk but are not a substitute for
network isolation in a high-trust production environment.

Never commit API keys, licensed market data, private filings, personal data, or broker credentials.
CapexGraph intentionally has no brokerage execution path.

The optional `codex_subscription` provider is local-first. Keep CLIProxyAPI bound to loopback and
protect it with a separate random local access key. CapexGraph must not receive, inspect, log, or
persist the proxy's ChatGPT OAuth access/refresh files. It records only credential-free provider,
model, transport, billing, endpoint-scope, and failure metadata. Non-loopback proxy URLs are
rejected unless the operator explicitly enables them; that opt-in should be paired with network
access controls and TLS. Never expose a personal subscription relay as a shared or public service.

The Codex subscription and official OpenAI API channels never fall back to each other. This prevents
a local proxy outage from creating an unexpected Platform API charge and prevents an API failure
from consuming personal subscription capacity.

The v0.5.1 live-signal contract keeps provider content retention explicit. `ephemeral` and
`metadata_only` observations persist allowed metadata and a content hash, not the raw body;
validation dead letters persist only a payload hash and safe schema errors. The bundled
dual-channel feed is synthetic.

Jin10 MCP Bearer and Open Platform WebSocket Secret-Key are independent backend environment
variables. They must never enter Live Desk settings, checkpoints, API/SSE responses, portable
artifacts, logs, or committed fixtures. Public status exposes only configured/missing booleans.
Provider errors are sanitized before persistence, common Authorization/API/Secret-Key patterns are
redacted, HTML-ish provider content is reduced to bounded plain text, and provider picture URLs are
deliberately omitted because licensed images must not be hotlinked or redistributed.

Live provider content is untrusted input. Deterministic rules run before optional model analysis;
injection-like strings are flagged and model prompts isolate provider text inside an explicit
untrusted-data boundary. A Jin10 signal cannot become Evidence, change an official event, or raise
relationship confidence. Browser notifications are disabled by default and require the operator's
explicit permission; the browser receives no provider credential.
