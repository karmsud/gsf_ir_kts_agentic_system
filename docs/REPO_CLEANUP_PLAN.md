# SAFE REPO CLEANUP PLAN

## Only Removing Generated Artifacts & Build Dependencies from Git Tracking

Based on analysis of largest tracked files:
1. **node_modules/** (Root): Currently tracked (~15MB+). MUST REMOVE from git index (`git rm -r --cached`). This should be re-installed via `npm install` on any fresh checkout.
2. **scripts/logs/**: Currently tracked. (~2MB+). MUST REMOVE from git index. These are local execution logs.
3. **audit_artifacts/**: Potentially tracked. Remove.
4. **dist/** & **build/**: Potentially tracked (build artifacts). Remove.

## Retention (What We Keep)
- All source code (`backend/`, `cli/`, `extension/src/`).
- `package.json`, `package-lock.json`, `requirements.txt`.
- `packaging/` scripts and specs.
- Documentation (except irrelevant generated reports).

## Proposed Commands
1. `git rm -r --cached node_modules`
2. `git rm -r --cached scripts/logs`
3. `git rm -r --cached audit_artifacts` (if exists)
4. Update `.gitignore` to ensure these stay ignored.
5. Move rigorous test reports (`docs/EVAL_REPORT_*.md`) to `docs/archive/`.

