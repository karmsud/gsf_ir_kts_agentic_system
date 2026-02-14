# Troubleshoot: ToolX — HTTP 504 Gateway Timeout (Dashboard banner)

**Last updated:** 2026-02-14  
**Owner:** KTS Test Corpus Team  
**Applies to:** ToolX Web UI

## Symptoms
- Banner on Dashboard shows: `HTTP 504 Gateway Timeout`
- Widgets load partially; graphs blank.

**Screenshot reference:** `Reference/images/toolx_timeout_dashboard.png`

## Quick checks (2 minutes)
1. Verify VPN is connected (if required).
2. Open another internal site to confirm general connectivity.
3. If behind a proxy, retry with proxy disabled (if permitted).

## Resolution
1. ToolX → **Help** → **Run Connection Test**
2. If test fails at **API Gateway**, retry after clearing cache:
   - Chrome: Settings → Privacy → Clear browsing data → Cached images/files
3. If the issue is site‑wide, check your incident banner or status page.

## Validation
- Refresh Dashboard; confirm banner disappears.
- Open **Jobs** and confirm list loads.

## Notes
- If timeouts occur only on one widget, capture widget name and timeframe.

