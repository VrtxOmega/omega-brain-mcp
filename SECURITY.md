# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.1.x (latest) | Yes |
| < 2.1 | No |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately via [GitHub Security Advisories](https://github.com/VrtxOmega/omega-brain-mcp/security/advisories/new).

Include:
- A description of the vulnerability and its potential impact
- Steps to reproduce or proof-of-concept code
- The version(s) affected
- Any suggested mitigations

You will receive an acknowledgment within 72 hours. If the vulnerability is confirmed, a fix will be prioritized and a coordinated disclosure timeline will be agreed upon before any public announcement.

## Scope

The following are in scope for security reports:

- **S.E.A.L. ledger integrity** — vulnerabilities that allow hash chain manipulation without detection
- **Cortex gate bypass** — techniques that allow tool calls to bypass the Cortex similarity gate
- **NAFE scanner evasion** — input patterns that cause NAFE violations to go undetected
- **VERITAS pipeline manipulation** — inputs that cause the 10-gate pipeline to return incorrect verdicts
- **Handoff tampering** — vulnerabilities in the SHA-256 handoff seal/verify cycle
- **Arbitrary code execution** — vulnerabilities in the MCP server's tool dispatch or input parsing

The following are **out of scope**:

- Vulnerabilities requiring physical access to the host machine
- Attacks requiring the operator to run malicious code as the same user
- Theoretical attacks with no practical exploit path
- Issues in dependencies outside the `omega-brain-mcp` codebase (report those to the respective upstream projects)

## Security Architecture Notes

- All data is stored locally. No network egress occurs in stdio mode.
- The vault (`omega_vault.db`) is unencrypted SQLite. Protect it with OS-level file permissions.
- The S.E.A.L. ledger uses SHA-3-256 hash chaining. Chain integrity can be verified programmatically.
- The VERITAS gate engine (`veritas_build_gates.py`) is stateless and makes no network calls or file I/O.
- SSE mode exposes an HTTP endpoint. TLS termination and network access control are the operator's responsibility.

See the [Threat Model](README.md#threat-model) section of the README for explicit in-scope and out-of-scope threat boundaries.
