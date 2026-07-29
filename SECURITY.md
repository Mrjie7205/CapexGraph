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
