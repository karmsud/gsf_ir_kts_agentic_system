# download_bge_model.ps1
# Downloads and prepares BAAI/bge-base-en-v1.5 ONNX INT8 model for KTS
#
# Prerequisites:
#   - Python 3.10+
#   - pip install optimum[onnxruntime] onnx onnxruntime transformers
#
# Usage:
#   .\scripts\download_bge_model.ps1
#   .\scripts\download_bge_model.ps1 -OutputDir ".\custom_path\bge"

param(
    [string]$OutputDir = ".\packaging\models\bge"
)

$ErrorActionPreference = "Stop"

$ModelId = "BAAI/bge-base-en-v1.5"
$OutputPath = Resolve-Path $OutputDir -ErrorAction SilentlyContinue
if (-not $OutputPath) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    $OutputPath = Resolve-Path $OutputDir
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "KTS BGE Model Downloader (Phase 5 WS-1)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Model: $ModelId"
Write-Host "Output: $OutputPath"
Write-Host ""

# Check Python dependencies
Write-Host "Checking dependencies..." -ForegroundColor Yellow
$deps = @("optimum", "onnx", "onnxruntime", "transformers", "tokenizers")
foreach ($dep in $deps) {
    $result = python -c "import $dep" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Missing dependency: $dep" -ForegroundColor Red
        Write-Host "Install with: pip install optimum[onnxruntime] onnx onnxruntime transformers tokenizers" -ForegroundColor Yellow
        exit 1
    }
}
Write-Host "All dependencies OK" -ForegroundColor Green
Write-Host ""

# Step 1: Export to ONNX using optimum-cli
Write-Host "Step 1: Exporting $ModelId to ONNX..." -ForegroundColor Yellow
$tempOnnx = Join-Path $env:TEMP "bge_onnx_temp"
if (Test-Path $tempOnnx) {
    Remove-Item -Recurse -Force $tempOnnx
}

$exportCmd = "optimum-cli export onnx --model $ModelId --task feature-extraction $tempOnnx"
Write-Host "Running: $exportCmd"
Invoke-Expression $exportCmd

if (-not (Test-Path "$tempOnnx\model.onnx")) {
    Write-Host "ONNX export failed - model.onnx not found" -ForegroundColor Red
    exit 1
}
Write-Host "ONNX export complete" -ForegroundColor Green
Write-Host ""

# Step 2: Quantize to INT8
Write-Host "Step 2: Quantizing to INT8..." -ForegroundColor Yellow
$quantScript = @"
import onnx
from onnxruntime.quantization import quantize_dynamic, QuantType
import sys
import os

input_path = sys.argv[1]
output_path = sys.argv[2]

print(f"Quantizing {input_path} -> {output_path}")

quantize_dynamic(
    model_input=input_path,
    model_output=output_path,
    weight_type=QuantType.QInt8,
    extra_options={'ActivationSymmetric': False}
)

# Verify output
model = onnx.load(output_path)
onnx.checker.check_model(model)
print(f"INT8 model verified: {os.path.getsize(output_path) / 1024 / 1024:.1f} MB")
"@

$quantScriptPath = Join-Path $env:TEMP "quantize_bge.py"
$quantScript | Set-Content -Path $quantScriptPath -Encoding UTF8

$inputOnnx = Join-Path $tempOnnx "model.onnx"
$outputOnnx = Join-Path $OutputPath "model.onnx"

python $quantScriptPath $inputOnnx $outputOnnx

if (-not (Test-Path $outputOnnx)) {
    Write-Host "INT8 quantization failed" -ForegroundColor Red
    exit 1
}
Write-Host "INT8 quantization complete" -ForegroundColor Green
Write-Host ""

# Step 3: Copy tokenizer files
Write-Host "Step 3: Copying tokenizer files..." -ForegroundColor Yellow
$tokenizerFiles = @("tokenizer.json", "tokenizer_config.json", "vocab.txt", "special_tokens_map.json")
foreach ($file in $tokenizerFiles) {
    $src = Join-Path $tempOnnx $file
    $dst = Join-Path $OutputPath $file
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        Write-Host "  Copied: $file"
    }
}
Write-Host ""

# Step 4: Cleanup
Write-Host "Step 4: Cleanup..." -ForegroundColor Yellow
Remove-Item -Recurse -Force $tempOnnx
Remove-Item -Force $quantScriptPath
Write-Host "Temp files removed" -ForegroundColor Green
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Green
Write-Host "BGE Model Ready" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Location: $OutputPath"
Write-Host ""
Get-ChildItem $OutputPath | ForEach-Object {
    $size = if ($_.Length -gt 1MB) { "{0:N1} MB" -f ($_.Length / 1MB) } else { "{0:N1} KB" -f ($_.Length / 1KB) }
    Write-Host ("  {0,-30} {1,10}" -f $_.Name, $size)
}
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Set KTS_BGE_MODEL_PATH=$OutputPath or update settings"
Write-Host "  2. Run: .\scripts\build_backend.ps1"
Write-Host "  3. Test with: python -m pytest tests/test_phase6_embedding.py"
