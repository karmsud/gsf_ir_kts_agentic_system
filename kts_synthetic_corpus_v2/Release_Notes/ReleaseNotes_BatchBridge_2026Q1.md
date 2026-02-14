# BatchBridge Release Notes — 2026 Q1

**Release window:** 2026-01-15 to 2026-02-05  
**Version:** 3.1.0

## Highlights
- Added built-in exponential backoff controls for rate limiting (HTTP 429 / ERR-RATE-429).
- Improved certificate chain validation during connector TLS handshake.

## Breaking changes
- Deprecated legacy Java keystore workaround for ERR-TLS-014.

## Known issues
- Some environments may still see ERR-TLS-014 if corporate root CA store is missing.
