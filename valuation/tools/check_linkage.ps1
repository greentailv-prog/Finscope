# Proves the workbook is a "worksheet", not a report: change a driver in the
# assumption sheet, recalc, and confirm the DCF falls out of the downstream chain.
#
#   powershell -File tools/check_linkage.ps1 -src demo/valuation_model.xlsx
#
# ASCII-only on purpose (PS 5.1 reads BOM-less UTF-8 as ANSI and mangles Chinese).
# Sheets are addressed by INDEX because their names are Chinese:
#   1=summary 2=assumptions 3=dcf 4=relative 5=sotp 6=blend 7=sensitivity 8=sources
# Assumption sheet C8 = EBIT margin; DCF sheet C30 = per-share value.
# If the sheet layout changes, these coordinates must move with it.
param([Parameter(Mandatory=$true)][string]$src)

$ErrorActionPreference = 'Stop'

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$excel.AskToUpdateLinks = $false
Start-Sleep -Milliseconds 900

$failed = $false
try {
    $wb = $excel.Workbooks.Open($src, 0, $false)
    $ps  = $wb.Worksheets.Item(2)    # assumptions
    $dcf = $wb.Worksheets.Item(3)    # DCF

    $excel.CalculateFullRebuild()
    $m0 = $ps.Range("C8").Value2
    $p0 = $dcf.Range("C30").Value2

    # cut EBIT margin by 10pp -> DCF per-share must drop
    $ps.Range("C8").Value2 = $m0 - 0.10
    $excel.CalculateFullRebuild()
    $p1 = $dcf.Range("C30").Value2

    Write-Output ("EBIT margin {0:P2} -> {1:P2}" -f $m0, $ps.Range("C8").Value2)
    Write-Output ("DCF per-share {0:N2} -> {1:N2}" -f $p0, $p1)

    if (-not ($p1 -lt $p0)) {
        Write-Output "FAIL: cutting the margin did not lower DCF per-share -- assumptions are not wired through"
        $failed = $true
    }
    if ([math]::Abs($p0 - $p1) -lt 1) {
        Write-Output "FAIL: downstream value barely moved -- the link is broken"
        $failed = $true
    }

    $wb.Close($false)
} catch {
    Write-Output ("OPEN_FAILED: " + $_.Exception.Message)
    $failed = $true
} finally {
    $excel.Quit()
}

if ($failed) { Write-Output 'LINKAGE_CHECK_FAIL'; exit 1 }
Write-Output 'LINKAGE_CHECK_OK'
exit 0
