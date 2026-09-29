<#
.SYNOPSIS
  Open-check of generated .docx files in Microsoft Word (COM, hidden, read-only):
  opens each file, updates the TOC in memory, reports Word's own page count and
  optionally exports a PDF (-Pdf: next to the docx; -OutDir <dir>: into that directory,
  created if needed - use it to keep PDFs out of the delivery folders). Never saves the docx.
  Use when LibreOffice (soffice) is not available.
.NOTES
  Exit codes: 0 = all opened, 1 = a file failed to open, 2 = execution error / timeout.
  On timeout only WINWORD processes started after this script by COM automation
  ("/Automation" on the command line) are terminated - a Word opened by the user is left alone.
#>
param(
  [Parameter(Mandatory = $true)][string[]]$Path,
  [switch]$Pdf,
  [string]$OutDir,
  [int]$TimeoutSec = 600
)
$ErrorActionPreference = 'Stop'
$files = @($Path | ForEach-Object { (Resolve-Path -LiteralPath $_).Path })
# -OutDir implies -Pdf; PDFs keep the docx base name (two docx with one name would collide: refused)
if ($OutDir) {
  $Pdf = [switch]$true
  $OutDir = [IO.Path]::GetFullPath($(if ([IO.Path]::IsPathRooted($OutDir)) { $OutDir } else { Join-Path (Get-Location) $OutDir }))
  $null = New-Item -ItemType Directory -Force -Path $OutDir
  $dupes = @($files | Group-Object { [IO.Path]::GetFileNameWithoutExtension($_).ToLowerInvariant() } | Where-Object Count -gt 1)
  if ($dupes.Count) { Write-Error "opencheck-word: -OutDir: several docx named $($dupes[0].Name) would write one PDF"; exit 2 }
}
$before = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object Id)

$job = Start-Job -ArgumentList ($files -join '|'), $Pdf.IsPresent, $(if ($OutDir) { $OutDir } else { '' }) -ScriptBlock {
  param($joined, $pdf, $outDir)
  $files = $joined -split '\|'
  $out = @()
  $word = New-Object -ComObject Word.Application
  try {
    $word.Visible = $false
    $word.DisplayAlerts = 0
    foreach ($f in $files) {
      $r = [ordered]@{ path = $f; opened = $false; pages = $null; paragraphs = $null; tables = $null; tocs = $null; pdf = $null; error = $null }
      try {
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $doc = $word.Documents.Open($f, $false, $true, $false)
        $r.opened = $true
        $r.tocs = $doc.TablesOfContents.Count
        foreach ($t in $doc.TablesOfContents) { $null = $t.Update() }
        $r.pages = $doc.ComputeStatistics(2)       # wdStatisticPages
        $r.paragraphs = $doc.Paragraphs.Count
        $r.tables = $doc.Tables.Count
        if ($pdf) {
          $p = if ($outDir) { Join-Path $outDir ([IO.Path]::GetFileNameWithoutExtension($f) + '.pdf') } else { [IO.Path]::ChangeExtension($f, '.pdf') }
          $doc.ExportAsFixedFormat($p, 17)          # wdExportFormatPDF
          $r.pdf = $p
        }
        $doc.Close(0)                               # wdDoNotSaveChanges
        $r.seconds = [math]::Round($sw.Elapsed.TotalSeconds, 1)
      } catch { $r.error = $_.Exception.Message }
      $out += [pscustomobject]$r
    }
  } finally {
    $word.Quit(0)
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)
  }
  $out
}

if (-not (Wait-Job $job -Timeout $TimeoutSec)) {
  Stop-Job $job
  # Ours = started after this script AND launched by COM automation ("/Automation" on the
  # command line). A Word the user opened meanwhile has no such switch and is left alone.
  $new = @(Get-CimInstance Win32_Process -Filter "Name = 'WINWORD.EXE'" -ErrorAction SilentlyContinue |
    Where-Object { $before -notcontains $_.ProcessId -and $_.CommandLine -match '(?i)[/-]Automation' } |
    ForEach-Object { [pscustomobject]@{ Id = $_.ProcessId } })
  foreach ($p in $new) { Stop-Process -Id $p.Id -Force }
  Write-Error "opencheck-word: timeout after $TimeoutSec s (terminated own WINWORD PIDs: $($new.Id -join ','))"
  exit 2
}
try { $res = @(Receive-Job $job -ErrorAction Stop) } catch { Write-Error "opencheck-word: $($_.Exception.Message)"; exit 2 }
Remove-Job $job
$fail = $false
foreach ($r in $res) {
  if ($r.opened -and -not $r.error) {
    $pdfInfo = if ($r.pdf) { "  pdf=$($r.pdf) ($((Get-Item -LiteralPath $r.pdf).Length) bytes)" } else { '' }
    "OK   $($r.path)  pages=$($r.pages) paragraphs=$($r.paragraphs) tables=$($r.tables) tocs=$($r.tocs) seconds=$($r.seconds)$pdfInfo"
  } else { $fail = $true; "FAIL $($r.path)  $($r.error)" }
}
if ($fail) { exit 1 } else { exit 0 }
