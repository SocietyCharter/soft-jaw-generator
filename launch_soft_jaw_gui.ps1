param(
    [string]$PythonVersion = "3.10",
    [string]$EnvDir = ".conda-env"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"
$GuiScript = Join-Path $ProjectRoot "soft_jaw_gui_opengl.py"
$EnvPath = Join-Path $ProjectRoot $EnvDir
$ImportCheckPath = Join-Path $ProjectRoot ".codex_import_check.py"

if (-not (Test-Path $RequirementsPath)) {
    throw "requirements.txt not found at $RequirementsPath"
}

if (-not (Test-Path $GuiScript)) {
    throw "GUI script not found at $GuiScript"
}

function Find-CondaRoot {
    $condaCandidates = @(
        "C:\ProgramData\miniconda3",
        "C:\ProgramData\anaconda3",
        (Join-Path $env:USERPROFILE "miniconda3"),
        (Join-Path $env:USERPROFILE "anaconda3"),
        (Join-Path $env:LOCALAPPDATA "miniconda3"),
        (Join-Path $env:LOCALAPPDATA "anaconda3")
    )

    $condaCmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($condaCmd) {
        $candidate = Split-Path -Parent (Split-Path -Parent $condaCmd.Source)
        if (Test-Path (Join-Path $candidate "python.exe")) {
            return $candidate
        }
    }

    foreach ($candidate in $condaCandidates) {
        if ($candidate -and (Test-Path (Join-Path $candidate "python.exe")) -and (Test-Path (Join-Path $candidate "Scripts\conda-script.py"))) {
            return $candidate
        }
    }

    return $null
}

$condaRoot = Find-CondaRoot
if (-not $condaRoot) {
    Write-Host "Conda was not found on PATH or in common install locations." -ForegroundColor Red
    Write-Host "Install Miniconda or Anaconda, or edit this script with your Conda install path." -ForegroundColor Yellow
    exit 1
}

$condaPython = Join-Path $condaRoot "python.exe"
$condaScript = Join-Path $condaRoot "Scripts\conda-script.py"
$envPython = Join-Path $EnvPath "python.exe"

if (-not (Test-Path $condaPython) -or -not (Test-Path $condaScript)) {
    Write-Host "Conda install is incomplete: expected both python.exe and Scripts\\conda-script.py." -ForegroundColor Red
    exit 1
}

function Invoke-Conda {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Args
    )

    $oldNoPlugins = $env:CONDA_NO_PLUGINS
    $oldNoSite = $env:PYTHONNOUSERSITE
    $env:CONDA_NO_PLUGINS = "true"
    $env:PYTHONNOUSERSITE = "1"

    try {
        & $condaPython $condaScript --no-plugins @Args
        return $LASTEXITCODE
    }
    finally {
        if ($null -eq $oldNoPlugins) {
            Remove-Item Env:CONDA_NO_PLUGINS -ErrorAction SilentlyContinue
        } else {
            $env:CONDA_NO_PLUGINS = $oldNoPlugins
        }
        if ($null -eq $oldNoSite) {
            Remove-Item Env:PYTHONNOUSERSITE -ErrorAction SilentlyContinue
        } else {
            $env:PYTHONNOUSERSITE = $oldNoSite
        }
    }
}

$importCheck = @'
import importlib

modules = {
    "cadquery": "cadquery",
    "cadquery-ocp": "OCP",
    "PyQt5": "PyQt5",
    "pyqtgraph": "pyqtgraph",
    "PyOpenGL": "OpenGL",
    "numpy": "numpy",
    "numpy-stl": "stl",
}

missing = []
for package_name, module_name in modules.items():
    try:
        importlib.import_module(module_name)
    except Exception:
        missing.append(package_name)

if missing:
    raise SystemExit("MISSING:" + ",".join(missing))

print("OK")
'@
Set-Content -Path $ImportCheckPath -Value $importCheck -Encoding ASCII

Write-Host "Using project: $ProjectRoot" -ForegroundColor Cyan
Write-Host "Using conda root: $condaRoot" -ForegroundColor Cyan
Write-Host "Using project-local env: $EnvPath" -ForegroundColor Cyan

if (-not (Test-Path $envPython)) {
    Write-Host "Creating project-local conda env with Python $PythonVersion..." -ForegroundColor Yellow
    Invoke-Conda create --prefix $EnvPath -y "python=$PythonVersion"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $envPython)) {
        Write-Host "Conda could not create the local environment." -ForegroundColor Red
        Write-Host "If this machine is offline, connect once so Conda can fetch Python $PythonVersion, then rerun the script." -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "Checking required imports..." -ForegroundColor Cyan
& $envPython $ImportCheckPath
$needsInstall = $LASTEXITCODE -ne 0

if ($needsInstall) {
    Write-Host "Installing or repairing requirements in the local conda env..." -ForegroundColor Yellow
    & $envPython -m pip install -r $RequirementsPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Package install failed. Check network/proxy access and rerun the launcher." -ForegroundColor Red
        exit 1
    }

    Write-Host "Re-checking required imports..." -ForegroundColor Cyan
    & $envPython $ImportCheckPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Requirements check still failed after install." -ForegroundColor Red
        exit 1
    }
}

Write-Host "Launching soft jaw generator GUI..." -ForegroundColor Green
& $envPython $GuiScript
