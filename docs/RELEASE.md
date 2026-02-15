# KTS Release Process

**Source of Truth**: `scripts/package_vsix.ps1`

## 1. Versioning Strategy

KTS uses Semantic Versioning (SemVer): `vMajor.Minor.Patch`.

- **Major**: Breaking backend changes or API rewrites.
- **Minor**: New features (Tier A3, Image extraction).
- **Patch**: Bug fixes, perf improvements.

The version is defined in:
1.  `extension/package.json` (`version` field)
2.  `cli/main.py` (`@click.version_option`)

## 2. Release Workflow

### Step 1: Update Version
Update versions in `package.json` and `cli/main.py`.

### Step 2: Build Artifacts (Clean Build)

**Tier A2 (Full)**
```powershell
.\scripts\build_backend_exe.ps1 -Tier A2 -Clean -SkipTests
.\scripts\package_vsix.ps1 -Tier A2 -Version "X.Y.Z"
```

**Tier A3 (Light)**
```powershell
.\scripts\build_backend_exe.ps1 -Tier A3 -Clean -SkipTests
.\scripts\package_vsix.ps1 -Tier A3 -Version "X.Y.Z"
```

### Step 3: Verify Artifacts
Check `extension/dist/`:
- `gsf-ir-kts-X.Y.Z.vsix` (~41MB)
- `gsf-ir-kts-X.Y.Z-a3.vsix` (~16MB)

Install locally to test activation: `code --install-extension extension/dist/gsf-ir-kts-X.Y.Z.vsix`

### Step 4: Publish
Distribute `.vsix` files to internal share or update mechanisms.

## 3. What NOT to Commit
- `dist/`, `build/`
- `.kts` folders (except for specific test fixtures if minimal)
- `__pycache__`
- `*.vsix`, `*.exe`
