# Troubleshoot: ToolX — ERR-AUTH-401 (Token expired after SSO redirect)

**Last updated:** 2026-02-14  
**Owner:** KTS Test Corpus Team  
**Applies to:** ToolX Web UI (Prod / UAT)

## Symptoms
- Users attempt to sign in via SSO and are redirected back to ToolX.
- A modal appears showing: `ERR-AUTH-401: Token expired after redirect.`  
- Retry sometimes repeats the issue.

**Screenshot reference:** `Reference/images/toolx_auth_401.png`

## Likely Causes
1. SSO session is stale (user kept a tab open overnight).
2. Browser blocks third‑party cookies needed for the redirect.
3. Clock skew on endpoint > 5 minutes (rare).

## Resolution (fast path)
1. **Hard refresh** ToolX tab (Ctrl+Shift+R).
2. **Sign out** of the identity provider in another tab, then sign back in.
3. In the browser, **allow third‑party cookies** for the identity domain (temporary test).
4. If still failing, run the ToolX built‑in connection test:
   - ToolX → **Settings** → **Help** → **Run Connection Test**
5. Validate: user can land on the Dashboard without an error dialog.

## Validation
- Confirm user can access Dashboard and open **Tickets** page.
- Confirm the **Last login** timestamp updates.

## Escalation data to capture
- Error code: `ERR-AUTH-401`
- `TraceId` value from dialog
- Timestamp + environment (Prod/UAT)
- Browser + version

