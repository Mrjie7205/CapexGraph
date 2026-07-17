# Security policy

Please report vulnerabilities privately through GitHub Security Advisories rather than a public
issue. Include the affected version, reproduction steps, impact, and any proposed mitigation.

CapexGraph treats remote evidence as hostile input. The collector blocks localhost, credentials
in URLs, and private, loopback, link-local, and reserved IP ranges; follows bounded downloads;
and validates redirect destinations. These controls reduce risk but are not a substitute for
network isolation in a high-trust production environment.

Never commit API keys, licensed market data, private filings, personal data, or broker credentials.
CapexGraph intentionally has no brokerage execution path.
