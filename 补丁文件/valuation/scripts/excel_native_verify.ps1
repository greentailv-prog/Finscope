param([Parameter(Mandatory=$true)][string]$Workbook, [string]$ReportPath = "")
$ErrorActionPreference = "Stop"
$path = (Resolve-Path $Workbook).Path
if (!$ReportPath) { $ReportPath = [IO.Path]::ChangeExtension($path, ".native_check.json") }
$excel=$null; $book=$null
$result=[ordered]@{file=$path; engine='Microsoft Excel COM'; status='EXCEL_FAIL'; errors=@(); formula_count=0; timestamp=(Get-Date).ToString('o')}
try {
  $excel=New-Object -ComObject Excel.Application
  $excel.Visible=$false; $excel.DisplayAlerts=$false
  $book=$excel.Workbooks.Open($path,0,$false)
  $excel.CalculateFullRebuild()
  foreach ($ws in $book.Worksheets) {
    $used=$ws.UsedRange
    foreach ($c in $used.Cells) {
      if ($c.HasFormula) { $result.formula_count++ }
      $v=[string]$c.Text
      if ($v -match '^#(REF!|DIV/0!|VALUE!|NAME\?|NUM!|N/A|NULL!)') {
        $result.errors += "$($ws.Name)!$($c.Address(0,0)): $v"
      }
    }
    if ($ws.Name -eq '三表联动预测') {
      for ($r=5;$r -le 14;$r++) {
        $year=$ws.Cells.Item($r,1).Value2
        if ($null -eq $year -or $year -eq '') {break}
        $check=[double]$ws.Cells.Item($r,27).Value2
        if ([Math]::Abs($check) -gt 0.01) { $result.errors += "三表联动预测!AA$r 不平衡 $check" }
        # 五表快速版没有 AC，FCFF 对照在“财务一致性校验”!D；
        # 兼容旧18表时才检查 AC。
        if ($ws.Cells.Item(4,29).Value2 -ne $null) {
          $fcffCheck=[double]$ws.Cells.Item($r,29).Value2
          if ([Math]::Abs($fcffCheck) -gt 0.01) { $result.errors += "三表联动预测!AC$r 与引擎FCFF不一致 $fcffCheck" }
        }
      }
    }
    if ($ws.Name -eq '财务一致性校验') {
      for ($r=5;$r -le 14;$r++) {
        $year=$ws.Cells.Item($r,1).Value2
        if ($null -eq $year -or $year -eq '') {break}
        $fcffDiff=[double]$ws.Cells.Item($r,4).Value2
        $bsDiff=[double]$ws.Cells.Item($r,5).Value2
        if ([Math]::Abs($fcffDiff) -gt 0.01) { $result.errors += "财务一致性校验!D$r FCFF不一致 $fcffDiff" }
        if ([Math]::Abs($bsDiff) -gt 0.01) { $result.errors += "财务一致性校验!E$r 三表不平衡 $bsDiff" }
      }
    }
  }
  $book.Save()
  if (($result.errors.Count -eq 0) -and ($result.formula_count -gt 0)) {$result.status='EXCEL_OK'}
} catch {
  $result.errors += "COM/Excel exception: $($_.Exception.Message)"
} finally {
  if ($book) {$book.Close($true) | Out-Null}
  if ($excel) {$excel.Quit() | Out-Null}
  $result | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $ReportPath
}
Write-Output $result.status
if ($result.status -ne 'EXCEL_OK') {exit 1}
exit 0
