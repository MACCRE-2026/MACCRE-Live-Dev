<#
.SYNOPSIS
    MACCREv2 Setup Script
    Bootstraps the .venv and installs all dependencies.
    Supports online (default) and offline (-Offline) modes.

.NOTES
    VENDOR ARCHITECTURE:
    openpyxl is intentionally NOT installed via pip. It is vendored inside
    maccre_core/_vendor/ and injected into sys.path by maccre_core/__init__.py
    automatically at import time. Do not pip install openpyxl.

    OMNIBUILDER:
    The 'omni' CI/CD tool is a global Python script installed at C:\OmniBuilder\.
    setup.ps1 will install it there if a bundled copy is found in _OmniBuilder\.

.USAGE
    powershell -ExecutionPolicy Bypass -File setup.ps1
    powershell -ExecutionPolicy Bypass -File setup.ps1 -Offline
#>
param([switch]$Offline)

$root = $PSScriptRoot

Write-Host ""
Write-Host "============================================"
Write-Host "   MACCREv2 Environment Setup               "
Write-Host "============================================"
Write-Host ""

# -- 1. Verify Python 3.11+ ----------------------------------------------------
$pyVer = ""
try {
    $pyVer = (& python --version 2>&1).ToString()
} catch {
    Write-Host "[SETUP] ERROR: Python not found on PATH."
    Write-Host "        Download Python 3.11+ from https://www.python.org/downloads/"
    exit 1
}
Write-Host "[SETUP] Python: $pyVer"
if ($pyVer -notmatch "3\.(1[1-9]|[2-9]\d)") {
    Write-Host "[SETUP] ERROR: Python 3.11+ required. Found: $pyVer"
    exit 1
}

# -- 2. Create .venv -----------------------------------------------------------
$venv = Join-Path $root ".venv"
if (Test-Path $venv) {
    Write-Host "[SETUP] .venv already exists -- skipping creation"
} else {
    Write-Host "[SETUP] Creating .venv..."
    & python -m venv $venv
    if ($LASTEXITCODE -ne 0) { Write-Host "[SETUP] ERROR: venv creation failed"; exit 1 }
    Write-Host "[SETUP] .venv created"
}

# -- 3. Activate ---------------------------------------------------------------
$activate = Join-Path $venv "Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
    Write-Host "[SETUP] ERROR: Cannot find $activate"
    exit 1
}
. $activate
Write-Host "[SETUP] .venv activated"

# -- 4. Upgrade pip ------------------------------------------------------------
Write-Host "[SETUP] Upgrading pip..."
python -m pip install --upgrade pip --quiet

# -- 5. Install dependencies ---------------------------------------------------
# NOTE: openpyxl is vendored in maccre_core/_vendor/ -- do NOT install via pip.
#       It is auto-injected into sys.path by maccre_core/__init__.py.

$pkgDir = Join-Path $root "_packages"
$hasLocal = (Test-Path $pkgDir) -and ((Get-ChildItem -File $pkgDir -ErrorAction SilentlyContinue).Count -gt 0)

function Install-Req {
    param($reqFile, $label)
    if (-not (Test-Path $reqFile)) {
        Write-Host "[SETUP] WARNING: $label not found -- skipping"
        return
    }
    Write-Host "[SETUP] Installing $label..."
    if ($Offline -and $hasLocal) {
        pip install --no-index --find-links=$pkgDir -r $reqFile
    } else {
        pip install -r $reqFile
    }
}

Install-Req (Join-Path $root "requirements-sovereign.txt") "sovereign dependencies"
Install-Req (Join-Path $root "requirements-global.txt")   "global dependencies"

Write-Host "[SETUP] Installing optional dependencies (failures are non-fatal)..."
try {
    Install-Req (Join-Path $root "requirements-optional.txt") "optional dependencies"
} catch {
    Write-Host "[SETUP] WARNING: Some optional deps failed -- continuing"
}

# -- 6. Install OmniBuilder globally ------------------------------------------
# omni is a global CI/CD tool (not part of the venv). It lives at C:\OmniBuilder\
# and is on the system PATH so 'omni qa .' works from any project directory.
$omniSrc = Join-Path $root "_OmniBuilder"
$omniDst = "C:\OmniBuilder"
if (Test-Path $omniSrc) {
    Write-Host "[SETUP] Installing OmniBuilder to $omniDst..."
    if (-not (Test-Path $omniDst)) { New-Item -ItemType Directory -Path $omniDst -Force | Out-Null }
    Copy-Item -Path "$omniSrc\*" -Destination $omniDst -Force -Recurse

    # Add C:\OmniBuilder to user PATH if not already present
    $userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    if ($null -eq $userPath) { $userPath = "" }
    if ($userPath -notlike "*OmniBuilder*") {
        [System.Environment]::SetEnvironmentVariable("PATH", "$userPath;$omniDst", "User")
        $env:PATH = "$env:PATH;$omniDst"
        Write-Host "[SETUP] C:\OmniBuilder added to user PATH"
    } else {
        Write-Host "[SETUP] C:\OmniBuilder already in PATH"
    }
} else {
    Write-Host "[SETUP] WARNING: _OmniBuilder\ not found - omni CI/CD tool not installed."
    Write-Host "        You can still run MACCRE normally. omni is only needed for 'omni qa' / 'omni build'."
}

# -- 7. Generate initial workbook ----------------------------------------------
Write-Host ""
Write-Host "[SETUP] Generating initial MACCRE_Global.xlsx..."
try {
    python (Join-Path $root "maccre.py") workbook refresh --project GLOBAL
} catch {
    Write-Host "[SETUP] WARNING: Workbook generation failed."
    Write-Host "        Run manually: python maccre.py workbook refresh"
}

# -- Done ----------------------------------------------------------------------
Write-Host ""
Write-Host "============================================"
Write-Host "   MACCREv2 Setup Complete!"
Write-Host "============================================"
Write-Host ""
Write-Host "  VENDOR NOTE:"
Write-Host "  openpyxl is bundled in maccre_core/_vendor/ -- do not pip install it."
Write-Host "  It loads automatically via maccre_core/__init__.py sys.path injection."
Write-Host ""
Write-Host "  NEXT STEPS:"
Write-Host "  1. Copy mcp_config.template.json -> mcp_config.json"
Write-Host "     Fill in: MACCRE_ROOT, GEMINI_API_KEY, BRAVE_SEARCH_API_KEY"
Write-Host ""
Write-Host "  2. Create your first project:"
Write-Host "     python maccre.py new MyProject"
Write-Host ""
Write-Host "  3. Refresh the operator workbook:"
Write-Host "     python maccre.py workbook refresh --project MyProject"
Write-Host ""
Write-Host "  4. Open MACCRE_Global.xlsx, fill AGENTS + TOPOLOGY + SWARM_REQUEST"
Write-Host ""
Write-Host "  5. Fire:"
Write-Host "     python maccre.py workbook fire"
Write-Host ""
Write-Host "  Read MACCRE_Operator_Manual.md for the full reference."
Write-Host ""
