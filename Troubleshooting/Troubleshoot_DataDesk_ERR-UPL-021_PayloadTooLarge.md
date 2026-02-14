# Troubleshoot: DataDesk — ERR-UPL-021 (Payload too large (max 50MB))

**Last updated:** 2026-02-14  
**Applies to:** DataDesk (Web UI + API)

## Symptoms
- User sees `ERR-UPL-021` and cannot complete the workflow.
- UI may show a banner/dialog.

**Screenshot reference:** `Reference/images/ui_03.png`

## Quick triage (90 seconds)
1. Confirm whether issue is user-specific or site-wide.
2. Capture `TraceId` / `RunId` if present.
3. Note browser + network context (VPN/proxy) when applicable.

## Likely causes
- Misconfiguration (common)
- Policy/limits (payload size, rate limit)
- Access/identity (roles, MFA time skew)
- Service degradation (gateway 5xx)

## Resolution
1. Apply the fastest safe fix first.
2. Re-test the workflow end-to-end.
3. Capture evidence for escalation if unresolved.

### Resolution details for ERR-UPL-021
- If `ERR-UPL-021` relates to **limits**, reduce batch size or split workload.
- If `ERR-UPL-021` relates to **identity**, re-auth and validate time sync.
- If `ERR-UPL-021` relates to **network**, verify proxy/VPN and retry.

## Validation
- User can reproduce success path and error no longer appears.
- A fresh log event confirms completion.

## Escalation package
- code: `ERR-UPL-021`
- tool: `DataDesk`
- timestamp + environment
- TraceId/RunId
- screenshots/log snippet
