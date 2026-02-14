# Troubleshoot: ToolZ — ERR-PWD-007 (Password does not meet complexity)

**Last updated:** 2026-02-14  
**Owner:** KTS Test Corpus Team  
**Applies to:** ToolZ password reset flow

## Symptoms
- User attempts reset and sees: `ERR-PWD-007: Password does not meet complexity.`
- Requirements list is displayed.

**Screenshot reference:** `Reference/images/toolz_password_policy.png`

## Resolution
1. Ensure password is **14+ characters** and includes:
   - upper, lower, number, special
2. Ensure password is not in last 10 passwords.
3. If user uses a password manager, regenerate with policy options enabled.

## Validation
- User receives "Password updated" confirmation.
- User can sign in again.

