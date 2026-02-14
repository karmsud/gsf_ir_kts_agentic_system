# ToolX Release Notes — 2026 Q1

**Release window:** 2026-01-10 to 2026-02-07  
**Version:** 6.3.0

## Highlights
- New Dashboard banner for connectivity issues (HTTP 504)
- Improved SSO retry logic (reduced `ERR-AUTH-401` frequency)

## Breaking changes
- Attachment upload now blocks additional extensions: `.js .ps1 .exe`

## Known issues
- Some users may still see `ERR-AUTH-401` if browser blocks third-party cookies.

