# Security Policy

JARVIS is a personal, privacy-first local AI assistant maintained by a
single developer. All processing is designed to happen on-device; there
is no backend service, no user accounts, and no telemetry.

## Project Status

The project is in active pre-release development (Phase 1 at the time of
writing). There are no stable version numbers and no LTS branches — only
the latest `main` is supported. If a vulnerability is confirmed, the fix
lands on `main` and older commits are not backported.

## Scope

In-scope for security reports:

- Code execution, path traversal, or sandbox escape in the FastAPI backend
  (`alliance_*/src/jarvis/web_api.py` and related routers)
- Secrets or credentials accidentally committed to the repository
- Cross-site scripting or HTML injection in the web UI renderers
- Data exfiltration paths that break the "local-only" privacy guarantee
- Prompt-injection vectors that can reach the file system or execute tools

Out-of-scope:

- Issues that require physical access to the user's machine
- Self-XSS or issues requiring the victim to paste attacker-controlled
  content into their own REPL
- Missing security headers on `127.0.0.1` binding (the default and
  intended deployment mode)
- Denial of service against the user's own localhost
- Third-party model weights, tokenizers, or upstream LLM safety issues

## Reporting a Vulnerability

**Preferred:** Use GitHub's Private Vulnerability Reporting on this
repository:
<https://github.com/projecthub-codingstudio/JARVIS/security/advisories/new>

This keeps the report private until a fix is ready and lets us
collaborate on a patch in a private fork.

**Alternative:** If private reporting is unavailable, open a GitHub issue
titled "Security: please contact me" without any technical detail, and
the maintainer will reach out through a private channel.

## Response Expectations

This is a solo-maintained project. Realistic expectations:

- **Acknowledgement:** within 7 days
- **Triage and severity assessment:** within 14 days
- **Fix on `main`:** depends on severity and complexity; critical issues
  are prioritized over feature work
- **Public disclosure:** coordinated with the reporter, typically after
  a fix has shipped to `main`

Bug bounties are not offered.

## Prior Incidents

- **2026-04-11 — Firebase Web API key exposure.** An API key for a
  legacy, now-deleted `terminal-architect/` sub-project was committed
  inside a security audit report. The GCP project
  (`gen-lang-client-0554693878`) was shut down on 2026-04-11 and is
  scheduled for permanent deletion on 2026-05-11. The key was never
  used by the main JARVIS codebase. Detected by GitHub Secret Scanning.
