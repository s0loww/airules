<#
.SYNOPSIS
  Independent read-back of generated .docx files: unzips in memory, parses
  word/document.xml (and header/footer parts) as XML, counts structure and
  checks expected strings. Read-only.
.EXAMPLE
  ./verify-docx.ps1 -Path out/01_Mono_sp.docx -Expect 'Contenido','Versión en español'
.NOTES
  Exit codes: 0 = all files well-formed and all expected strings found,
              1 = findings (malformed XML / missing string / missing part),
              2 = execution error.
  Machine-readable report: -Report <file> (default: .\last-verify.json in the current directory).
#>
param(
  [Parameter(Mandatory = $true)][string[]]$Path,
  [string[]]$Expect = @(),
  [string]$Report = (Join-Path (Get-Location) 'last-verify.json')
)
$ErrorActionPreference = 'Stop'
try {
  Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
  $results = @()
  $fail = $false
  foreach ($p in $Path) {
    $full = (Resolve-Path -LiteralPath $p).Path
    $r = [ordered]@{ path = $full; bytes = (Get-Item -LiteralPath $full).Length; wellFormed = $false; parts = @(); missing = @(); found = @(); errors = @() }
    $zip = [System.IO.Compression.ZipFile]::OpenRead($full)
    try {
      $names = $zip.Entries | ForEach-Object FullName
      $r.parts = @($names | Where-Object { $_ -like 'word/*.xml' })
      foreach ($req in 'word/document.xml', 'word/styles.xml', '[Content_Types].xml') {
        if ($names -notcontains $req) { $r.errors += "missing part $req" }
      }
      $allText = ''
      foreach ($e in $zip.Entries | Where-Object { $_.FullName -like 'word/*.xml' }) {
        $sr = New-Object System.IO.StreamReader($e.Open(), [System.Text.Encoding]::UTF8)
        $xmlText = $sr.ReadToEnd(); $sr.Close()
        try { $x = New-Object System.Xml.XmlDocument; $x.LoadXml($xmlText) } catch { $r.errors += "$($e.FullName): not well-formed: $($_.Exception.Message)"; continue }
        if ($e.FullName -eq 'word/document.xml') {
          $ns = New-Object System.Xml.XmlNamespaceManager($x.NameTable)
          $ns.AddNamespace('w', 'http://schemas.openxmlformats.org/wordprocessingml/2006/main')
          $r.paragraphs = $x.SelectNodes('//w:body//w:p', $ns).Count
          $r.tables = $x.SelectNodes('//w:body//w:tbl', $ns).Count
          $r.tableRows = $x.SelectNodes('//w:body//w:tr', $ns).Count
          $r.headings = @{
            h1 = $x.SelectNodes("//w:pStyle[@w:val='Heading1']", $ns).Count
            h2 = $x.SelectNodes("//w:pStyle[@w:val='Heading2']", $ns).Count
            h3 = $x.SelectNodes("//w:pStyle[@w:val='Heading3']", $ns).Count
          }
          $W = $ns.LookupNamespace('w')
          $marks = @($x.SelectNodes('//w:bookmarkStart', $ns) | ForEach-Object { $_.GetAttribute('name', $W) })
          $anchors = @($x.SelectNodes('//w:hyperlink[@w:anchor]', $ns) | ForEach-Object { $_.GetAttribute('anchor', $W) })
          $r.bookmarks = $marks.Count
          $r.internalLinks = $anchors.Count
          # every internal link must hit a bookmark; bookmark names unique and within Word's rules
          # (<= 40 chars, letter first, letters/digits/underscore; "_"-prefixed = Word's hidden ones)
          $markSet = New-Object 'System.Collections.Generic.HashSet[string]'
          $dups = @(); foreach ($m in $marks) { if (-not $markSet.Add($m)) { $dups += $m } }
          $r.brokenInternalLinks = @($anchors | Where-Object { -not $markSet.Contains($_) } | Select-Object -Unique)
          $r.badBookmarks = @(@($marks | Where-Object { $_ -notmatch '^(?:[A-Za-z][A-Za-z0-9_]{0,39}|_[A-Za-z0-9_]{1,39})$' }) + @($dups | ForEach-Object { "duplicate: $_" }))
          foreach ($b in $r.brokenInternalLinks) { $r.errors += "internal link to missing bookmark $b" }
          foreach ($b in $r.badBookmarks) { $r.errors += "bad bookmark name $b" }
          $r.images = $x.SelectNodes("//*[local-name()='blip']").Count
          $r.tocField = ($xmlText -match 'TOC [^<]*\\o')
          $r.sections = @($x.SelectNodes('//w:sectPr/w:pgSz', $ns) | ForEach-Object { if ($_.GetAttribute('orient', $ns.LookupNamespace('w')) -eq 'landscape') { 'L' } else { 'P' } }) -join ''
        }
        $pt = [string]::Join("`n", @($x.SelectNodes("//*[local-name()='p']") | ForEach-Object { $_.InnerText }))
        if ($e.FullName -eq 'word/document.xml') {
          $r.words = ([regex]::Matches($pt, '\S+')).Count
          $r.pageEstimate = [math]::Ceiling($r.words / 350 + $r.tableRows / 30)
        }
        $allText += $pt + "`n"
      }
      # external hyperlinks: relative targets are resolved (percent-decoded) next to the docx;
      # a missing target is reported as a warning (the docx itself is fine, the set is not)
      $r.externalLinks = 0; $r.missingTargets = @()
      $relEntry = $zip.Entries | Where-Object { $_.FullName -eq 'word/_rels/document.xml.rels' }
      if ($relEntry) {
        $sr = New-Object System.IO.StreamReader($relEntry.Open(), [System.Text.Encoding]::UTF8); $relText = $sr.ReadToEnd(); $sr.Close()
        $rx = New-Object System.Xml.XmlDocument; $rx.LoadXml($relText)
        foreach ($rel in $rx.DocumentElement.ChildNodes) {
          if ($rel.GetAttribute('TargetMode') -ne 'External' -or $rel.GetAttribute('Type') -notlike '*/hyperlink') { continue }
          $r.externalLinks++
          $tgt = $rel.GetAttribute('Target')
          if ($tgt -match '^[A-Za-z][A-Za-z0-9+.-]*:') { continue }
          $file = [Uri]::UnescapeDataString(($tgt -split '#')[0])
          if ($file -and -not (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $full) $file))) { $r.missingTargets += $tgt }
        }
      }
      if (-not @($r.errors | Where-Object { $_ -match 'not well-formed|^missing part' }).Count) { $r.wellFormed = $true }
      foreach ($s in $Expect) { if ($allText.Contains($s)) { $r.found += $s } else { $r.missing += $s } }
    } finally { $zip.Dispose() }
    if ($r.errors.Count -or $r.missing.Count) { $fail = $true }
    $results += [pscustomobject]$r
  }
  $results | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Report -Encoding UTF8
  foreach ($r in $results) {
    $st = if ($r.errors.Count -or $r.missing.Count) { 'FAIL' } else { 'OK  ' }
    "$st $($r.path)  bytes=$($r.bytes) wellFormed=$($r.wellFormed) paragraphs=$($r.paragraphs) tables=$($r.tables) rows=$($r.tableRows) h1/h2/h3=$($r.headings.h1)/$($r.headings.h2)/$($r.headings.h3) bookmarks=$($r.bookmarks) intLinks=$($r.internalLinks) brokenIntLinks=$($r.brokenInternalLinks.Count) extLinks=$($r.externalLinks) images=$($r.images) toc=$($r.tocField) sections=$($r.sections) words=$($r.words) pages~$($r.pageEstimate)"
    foreach ($s in $r.found) { "     found:   $s" }
    foreach ($s in $r.missing) { "     MISSING: $s" }
    foreach ($s in $r.errors) { "     ERROR:   $s" }
    foreach ($s in $r.missingTargets) { "     warning: relative link target not found next to the docx: $s" }
  }
  if ($fail) { exit 1 } else { exit 0 }
} catch {
  Write-Error "verify-docx: $($_.Exception.Message)"
  exit 2
}
