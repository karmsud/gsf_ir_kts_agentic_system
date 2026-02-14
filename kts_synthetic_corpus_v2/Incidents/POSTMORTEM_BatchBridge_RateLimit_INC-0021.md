# Postmortem: BatchBridge Rate Limiting Spike (INC-0021)

**Date:** 2026-01-18  
**Severity:** P1  
**Primary signal:** HTTP 429 / ERR-RATE-429

## Summary
A surge in downstream API usage caused rate limiting. Retries without backoff amplified the issue.

## Corrective actions
- Default backoff enabled in 3.1.0 (see release notes)
- SOP published: SOP_Rate_Limit_Response_v1.docx

## Evidence
Screenshot: `Reference/images/ui_07.png`
