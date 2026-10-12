# Verify an exported valuation workbook actually opens in Excel and has no formula errors.
#   powershell -File tools/check_excel.ps1 -src "C:\path\to\valuation.xlsx"
# ASCII-only on purpose (PS 5.1 mangles BOM-less UTF-8 Chinese).
param([Parameter(Mandatory=$true)][string]$src)

$ErrorActionPreference = 'Stop'

$base = Split-Path -Parent $src
$name = [System.IO.Path]::GetFileNameWithoutExtension($src)
$ascii = Join-Path $base 'excel_check.xlsx'
Copy-Item $src $ascii -Force

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$excel.AskToUpdateLinks = $false
Start-Sleep -Milliseconds 900   # 实例刚起来时偶发 COM 未就绪

$failed = $false
try {
    # 与 verify_recalc.ps1 用同样的参数：UpdateLinks=0, ReadOnly=$false
    $wb = $null
    for ($i = 1; $i -le 3; $i++) {
        try {
            $wb = $excel.Workbooks.Open($ascii, 0, $false)
            break
        } catch {
            if ($i -eq 3) { throw }
            Write-Output ("Open retry {0}: {1}" -f $i, $_.Exception.Message)
            Start-Sleep -Milliseconds 1200
        }
    }
    $excel.CalculateFullRebuild()

    Write-Output ("Sheets = {0}" -f $wb.Worksheets.Count)
    foreach ($ws in $wb.Worksheets) {
        $used = $ws.UsedRange
        Write-Output ("  {0} : {1} rows x {2} cols" -f $ws.Name, $used.Rows.Count, $used.Columns.Count)
    }

    $errCount = 0
    foreach ($ws in $wb.Worksheets) {
        $errs = $null
        try { $errs = $ws.UsedRange.SpecialCells(-4123, 16) } catch {}
        if ($errs) { $errCount += $errs.Count; Write-Output ("  ERRORS in {0}: {1}" -f $ws.Name, $errs.Count) }
    }
    Write-Output ("TotalErrorCells = {0}" -f $errCount)
    if ($errCount -gt 0) { $failed = $true }

    # Save a recalculated copy so we can confirm cached values exist
    $out = Join-Path $base 'excel_check_recalc.xlsx'
    $wb.SaveAs($out, 51)
    $wb.Close($false)
    Write-Output ("RecalcCopy = {0}" -f $out)
} catch {
    Write-Output ("OPEN_FAILED: {0}" -f $_.Exception.Message)
    $failed = $true
} finally {
    $excel.Quit()
}

Remove-Item $ascii -Force -ErrorAction SilentlyContinue
if ($failed) { Write-Output 'EXCEL_CHECK_FAIL'; exit 1 }
Write-Output 'EXCEL_CHECK_OK'
exit 0
