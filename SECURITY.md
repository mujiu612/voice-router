# Security Policy

## Supported scope

This repository primarily contains routing logic, provider wrappers, delivery planning scripts, and documentation for a voice workflow.

Security-sensitive areas include:

- provider credential handling
- subprocess execution
- remote audio fetching
- temporary file handling
- platform delivery behavior
- documentation examples that could encourage unsafe defaults

## Reporting a vulnerability

If you believe you found a security issue, please avoid opening a public issue with exploit details.

Instead:

1. Prepare a short report with:
   - affected file(s)
   - impact
   - reproduction steps
   - suggested mitigation, if known
2. Sanitize the report so it does not expose secrets or private data.
3. Send the report privately to the repository owner through a non-public channel.

If a private contact path is not yet listed in the repository profile, open a minimal public issue only to request a private reporting route, without disclosing exploit details.

## What helps a good report

Useful reports usually include:

- exact command or workflow used
- whether the issue requires credentials
- whether the issue affects local-only, provider-facing, or delivery-facing behavior
- whether exploitation depends on a malicious config, malicious input, or malicious remote server
- proposed severity and rationale

## Disclosure expectations

The goal is coordinated disclosure:

- reporters get acknowledgment
- maintainers investigate and patch
- public discussion happens after a fix or mitigation is available

## Hardening expectations for contributors

When contributing changes, avoid:

- putting secrets in command-line arguments when safer alternatives exist
- committing `.env` files or real credentials
- using fixed world-readable temp paths for sensitive intermediates
- allowing unrestricted remote fetches when allowlists or validation are practical
- embedding machine-specific paths or personal data in public docs
