# Security Policy

RAGFence is a security testing tool: reports and evidence are designed to fail
closed and to never leak secrets. If you find a vulnerability in RAGFence
itself, we want to hear about it before anyone else does.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅        |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security reports.**

Use GitHub's private vulnerability reporting:

1. Go to <https://github.com/eduardbar/RAGfence/security/advisories/new>
2. Describe the issue, its impact, and a minimal reproduction (a failing
   command or test case is ideal).
3. If possible, state which release you tested against.

You can also reach the maintainer privately through the contact listed on the
GitHub profile (<https://github.com/eduardbar>).

## What to include

- Affected version (`pip show ragfence`) and commit SHA if running from source.
- The command line or API calls that trigger the issue.
- Any report output involved — **redact real secrets first**; RAGFence reports
  are redacted by design, but your environment may add more.
- Your assessment of severity and impact.

## What to expect

- **Acknowledgement** within 7 days.
- **Triage and severity classification** (Critical / High / Medium / Low)
  within 14 days.
- **Fix or mitigation** for Critical/High findings targeted within 30 days,
  sooner when feasible.
- **Public disclosure** coordinated with you: credit given by default, embargo
  respected until a patched release ships.

## Scope

In scope:

- The `ragfence` CLI and library shipped on PyPI.
- The bundled reference environment (migrations, seed data, Docker setup).
- The GitHub Actions workflows in this repository.

Out of scope:

- Vulnerabilities in the *targets* being evaluated (that is the point of the
  tool — fix them, or better, report them upstream).
- Reports from automated scanners without a demonstrated impact.
- Social engineering of maintainers or hosting providers.

## Safe harbor

We consider good-faith security research conducted according to this policy
authorized and will not pursue legal action against it.
