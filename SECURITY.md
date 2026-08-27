# Security policy

## Supported versions

Security fixes are provided for the latest released minor version.

## Reporting a vulnerability

Please use the repository host's private security-advisory feature. Do not open a public issue with
exploit details, private configuration, or secret material. Include affected versions, impact,
reproduction steps, and a minimal remediation suggestion when available.

The maintainers will acknowledge a complete report within seven days and coordinate a fix and
disclosure timeline with the reporter.

## Deployment boundary

Development anonymous mode is loopback-only. Production must configure trusted proxy mode, inject
a strong shared secret outside the repository, and enumerate the direct-peer proxy networks allowed
to provide identity headers. ReliaForge does not provide tenant isolation, plugin sandboxing, or a
general-purpose remote execution boundary in this release. Install only plugins whose code you
trust.
