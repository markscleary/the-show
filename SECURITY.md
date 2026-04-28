# Security

If you find a security vulnerability in The Show, please report it privately rather than opening a public issue.

Email: security@shortandsweet.org

Include:
- A description of the vulnerability
- Steps to reproduce, ideally a minimal programme that demonstrates it
- The version of The Show affected
- Any thoughts on impact or severity

We'll acknowledge receipt within seven days and aim to ship a fix within thirty days for confirmed vulnerabilities. We'll credit reporters in the release notes unless they prefer not to be named.

Please give us reasonable time to ship a fix before disclosing publicly.

## Scope

In scope:
- The runtime itself (Python package `the-show`)
- The CLI tools
- The default adapters

Out of scope:
- Third-party services we integrate with (Telegram, email providers, etc.) — report to them
- Issues in projects that depend on The Show — report to them
- Issues that require operator-level access to the host machine to exploit
