#Requires -Version 5.1
<#
.SYNOPSIS
    The one entry point to the writing tools of 1c-metadata-manage: DryRun by
    default, -Apply to write (airules script contract).

.DESCRIPTION
    The tool scripts under tools/ are vendored from upstream (cc-1c-skills via
    comol/ai_rules_1c) and each writes its own files. Rather than patching the
    contract into every one of them - lost on the next sync - each writing tool
    carries a short gate that refuses to run unless launched from here, and the
    contract lives in this one file (ci/sync_metadata_manage.py re-inserts the
    gates on every sync).

    How a tool is driven depends on what it writes:

    - file tools (meta-edit, form-compile, skd-edit, ...): without -Apply the
      tool really runs, the diff of everything it changed is printed, and the
      tree is put back. Inside a git repository the whole repository is watched
      (`git status` before and after), and files that were already dirty are
      saved by content first, so work in progress survives the rollback. Outside
      git a content snapshot of the target's scope is used instead.
    - tools with their own -DryRun (meta-remove, remove-form, remove-template,
      db-load-git, web-unpublish): without -Apply that flag is passed. With
      -Apply the confirmation switch -Force is added where it only confirms
      (remove-form, remove-template, web-unpublish) - never for meta-remove,
      where -Force means "remove despite references".
    - platform / server tools (db-*, epf-build, epf-dump, web-*, ...): without
      -Apply the planned call is printed and nothing runs.

    Read-only tools (*-info, *-validate, decompilers) run as they are.

.PARAMETER Tool
    Script name without .ps1: meta-edit, form-add, db-update. The two scaffold
    init scripts are epf-scaffold/init and erf-scaffold/init.

.PARAMETER Object
    Logical address resolved to the tool's path parameter: Справочник.Контрагенты,
    Документ.Реализация.Форма.ФормаДокумента, Роль.ПолныеПрава.

.PARAMETER Root
    Configuration dump root for -Object. Default: EXPORT_PATH from .dev.env, else
    the nearest folder with a Configuration.xml.

.PARAMETER Apply
    Write for real. Without it nothing is left changed.

.PARAMETER PasswordEnv
    Name of the environment variable holding the infobase password; passed to
    the tool as -Password. A literal -Password argument is refused.

.PARAMETER Scope
    Extra paths to snapshot when the dump is not in git.

.EXAMPLE
    # DryRun: shows the diff, changes nothing
    Invoke-1CEdit.ps1 -Tool meta-edit -Object Справочник.Контрагенты -Operation add-attribute -Value "ИНН: String(12)"

.EXAMPLE
    # the same, written
    Invoke-1CEdit.ps1 -Tool meta-edit -Object Справочник.Контрагенты -Operation add-attribute -Value "ИНН: String(12)" -Apply

.EXAMPLE
    Invoke-1CEdit.ps1 -Tool db-update -InfoBasePath <ib-path> -UserName Admin -PasswordEnv IB_PASSWORD -Apply
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Tool,

    [string]$Object,

    [string]$Root,

    [switch]$Apply,

    [Alias('Preview')]
    [switch]$DryRun,

    [string]$PasswordEnv,

    [string[]]$Scope,

    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]]$ToolArgs
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot 'DevEnv.ps1')
. (Join-Path $PSScriptRoot 'MetadataAddress.ps1')

# Tools that launch the platform or touch a server: DryRun = print the plan.
$ExternalTools = @(
    'db-create', 'db-dump-cf', 'db-dump-dt', 'db-dump-xml', 'db-load-cf', 'db-load-dt',
    'db-load-xml', 'db-run', 'db-update', 'install-files-update', 'epf-build', 'epf-dump',
    'stub-db-create', 'web-publish', 'web-stop')
# Native -DryRun tools whose -Force is a plain confirmation of the reviewed plan.
$ApplyAddsForce = @('remove-form', 'remove-template', 'web-unpublish')
# Above this many already-dirty files a rollback-safe DryRun is refused.
$MaxDirtySnapshot = 3000

function Write-Section([string]$Text) { Write-Host ''; Write-Host "== $Text" -ForegroundColor Cyan }

function Fail([string]$Text, [int]$Code = 2) {
    Write-Host $Text -ForegroundColor Red
    exit $Code
}

function Resolve-ToolScript {
    # By file name under tools/, so a tool added by a later sync needs no edit
    # here. 'epf-scaffold/init' picks init.ps1 under 1c-epf-scaffold.
    param([string]$Name)
    $toolsRoot = Split-Path $PSScriptRoot -Parent
    $folder = $null
    $leafName = $Name
    if ($Name.Contains('/')) { $folder, $leafName = $Name.Split('/', 2) }
    if (-not $leafName.EndsWith('.ps1')) { $leafName = "$leafName.ps1" }
    $hits = @(Get-ChildItem -LiteralPath $toolsRoot -Recurse -File -Filter $leafName -ErrorAction SilentlyContinue |
        Where-Object { -not $folder -or $_.FullName -match [regex]::Escape("1c-$folder") })
    if ($hits.Count -eq 0) {
        $known = (Get-ChildItem -LiteralPath $toolsRoot -Recurse -File -Filter '*.ps1' |
            Where-Object { $_.DirectoryName -notlike '*_common*' } |
            ForEach-Object { $_.BaseName } | Sort-Object -Unique) -join ', '
        Fail "Unknown tool '$Name'. Known: $known"
    }
    if ($hits.Count -gt 1) {
        Fail ("Ambiguous tool '{0}': {1}. Use <folder>/<name>, e.g. epf-scaffold/init." -f $Name, (($hits | ForEach-Object { $_.FullName }) -join '; '))
    }
    return $hits[0].FullName
}

function Get-ScriptParameters {
    param([string]$ScriptPath)
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
    $result = @{}
    if (-not $ast.ParamBlock) { return $result }
    foreach ($p in $ast.ParamBlock.Parameters) {
        $name = $p.Name.VariablePath.UserPath
        $aliases = @()
        foreach ($attr in $p.Attributes) {
            if ($attr -is [System.Management.Automation.Language.AttributeAst] -and $attr.TypeName.Name -eq 'Alias') {
                foreach ($arg in $attr.PositionalArguments) {
                    if ($arg -is [System.Management.Automation.Language.StringConstantExpressionAst]) { $aliases += $arg.Value }
                }
            }
        }
        $result[$name] = [pscustomobject]@{
            Name     = $name
            Aliases  = $aliases
            IsSwitch = ($p.StaticType -and $p.StaticType.Name -eq 'SwitchParameter')
        }
    }
    return $result
}

function Find-Parameter {
    # Canonical name of a tool parameter given a name or an alias, or $null.
    param($Parameters, [string]$Name)
    foreach ($p in $Parameters.Values) {
        if ($p.Name -eq $Name -or $p.Aliases -contains $Name) { return $p.Name }
    }
    return $null
}

function Find-PathParameter {
    param($Parameters)
    foreach ($p in $Parameters.Values) { if ($p.Aliases -contains 'Path') { return $p.Name } }
    $candidates = @($Parameters.Values | Where-Object { $_.Name -match 'Path$' -and -not $_.IsSwitch })
    if ($candidates.Count -eq 1) { return $candidates[0].Name }
    return $null
}

function ConvertTo-ParameterTable {
    # Flat "-Name value -Switch" tokens into a hashtable splatted by name:
    # array splatting would bind "-Operation" positionally as a value.
    param([object[]]$Arguments, $Parameters)
    $table = @{}
    $i = 0
    while ($i -lt $Arguments.Count) {
        $token = [string]$Arguments[$i]
        if ([string]::IsNullOrWhiteSpace($token)) { $i++; continue }
        if (-not $token.StartsWith('-')) { Fail "Cannot pass '$token' through: expected a -ParameterName before it." }
        $name = $token.TrimStart('-')
        $canonical = Find-Parameter $Parameters $name
        $isSwitch = $false
        if ($canonical) { $isSwitch = $Parameters[$canonical].IsSwitch }
        if ($isSwitch -or $i + 1 -ge $Arguments.Count) { $table[$name] = [switch]$true; $i++; continue }
        $next = [string]$Arguments[$i + 1]
        if ($next.StartsWith('-') -and $next.Length -gt 1 -and -not ($next -match '^-\d')) {
            $table[$name] = [switch]$true; $i++; continue
        }
        $value = $Arguments[$i + 1]
        # PowerShell 5.1 splits a remaining argument with commas into an array,
        # which shreds JSON values; join it back.
        if ($value -is [System.Array]) { $value = ($value -join ',') }
        $table[$name] = $value
        $i += 2
    }
    return $table
}

function Format-CallForDisplay {
    param([string]$ToolName, $CallArgs)
    $parts = @($ToolName)
    foreach ($k in ($CallArgs.Keys | Sort-Object)) {
        $v = $CallArgs[$k]
        if ($v -is [switch]) { $parts += "-$k"; continue }
        if ($k -eq 'Password') { $v = '***' }
        $parts += "-$k"
        $parts += ('"' + [string]$v + '"')
    }
    return ($parts -join ' ')
}

function Get-ToolSynopsis {
    param([string]$ScriptPath)
    $text = [System.IO.File]::ReadAllText($ScriptPath)
    $m = [regex]::Match($text, '\.SYNOPSIS\s*\r?\n\s*(.+)')
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return ''
}

function Invoke-Tool {
    # Run the tool in-process with the gate open; return its exit code.
    param([string]$ScriptPath, $CallArgs)
    $env:AIRULES_1C_GATE = '1'
    try {
        # A tool that succeeds by falling off its end leaves $LASTEXITCODE alone.
        $global:LASTEXITCODE = 0
        # Out-Host: tool output must not become part of this function's return value.
        & $ScriptPath @CallArgs | Out-Host
        return [int]$LASTEXITCODE
    } finally {
        Remove-Item Env:\AIRULES_1C_GATE -ErrorAction SilentlyContinue
    }
}

# ------------------------------------------------------------------- git state
function Invoke-Git {
    # git advice on stderr must not abort a rollback under ErrorActionPreference=Stop.
    param([string[]]$GitArgs)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $full = @('-c', 'core.autocrlf=false', '-c', 'core.safecrlf=false', '-c', 'core.quotepath=false') + $GitArgs
        $out = & git @full 2>$null
        return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($out) }
    } catch {
        return [pscustomobject]@{ ExitCode = 1; Output = @() }
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Get-RepoRoot {
    param([string]$Anchor)
    $dir = $Anchor
    if (-not (Test-Path -LiteralPath $dir -PathType Container)) { $dir = Split-Path $Anchor -Parent }
    while ($dir -and -not (Test-Path -LiteralPath $dir)) { $dir = Split-Path $dir -Parent }
    if (-not $dir) { return $null }
    $r = Invoke-Git @('-C', $dir, 'rev-parse', '--show-toplevel')
    if ($r.ExitCode -ne 0 -or -not $r.Output) { return $null }
    return ([string]$r.Output[0]).Replace('/', '\')
}

function Get-DirtyMap {
    # path (relative, '/') -> status code. -z keeps names with spaces and Cyrillic intact.
    param([string]$Repo)
    $r = Invoke-Git @('-C', $Repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all')
    $map = @{}
    if ($r.ExitCode -ne 0) { return $null }
    $raw = ($r.Output -join "`n")
    $entries = $raw.Split([char]0)
    $i = 0
    while ($i -lt $entries.Count) {
        $e = $entries[$i]
        if ($e.Length -ge 4) {
            $code = $e.Substring(0, 2)
            $map[$e.Substring(3)] = $code
            if ($code[0] -eq 'R' -or $code[0] -eq 'C') { $i++ }   # rename source follows
        }
        $i++
    }
    return $map
}

function Get-FileHashOrNull([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Show-FileDiff {
    param([string]$Before, [string]$After, [string]$Label)
    $nul = 'NUL'
    $a = if ($Before) { $Before } else { $nul }
    $b = if ($After) { $After } else { $nul }
    $out = (Invoke-Git @('diff', '--no-index', '--no-color', '--', $a, $b)).Output
    if (-not $out) { return }
    Write-Host "--- a/$Label"
    Write-Host "+++ b/$Label"
    $out | Select-Object -Skip 4 | ForEach-Object { Write-Host $_ }
}

function Remove-EmptyParents {
    param([string]$Path, [string]$Stop)
    $dir = Split-Path $Path -Parent
    while ($dir -and $dir.Length -gt $Stop.Length -and (Test-Path -LiteralPath $dir) -and
           -not (Get-ChildItem -LiteralPath $dir -Force | Select-Object -First 1)) {
        Remove-Item -LiteralPath $dir -Force
        $dir = Split-Path $dir -Parent
    }
}

function Invoke-GitPreview {
    # Run, diff, restore - watching the whole repository.
    param([string]$Repo, [string]$ScriptPath, $CallArgs)

    $before = Get-DirtyMap $Repo
    if ($null -eq $before) { return $null }
    if ($before.Count -gt $MaxDirtySnapshot) {
        Fail ("DryRun refused: {0} files are already dirty in {1} - too many to protect during the rollback. Commit or stash first." -f $before.Count, $Repo)
    }
    # Work in progress is saved by content: git cannot restore what it never saw.
    $store = Join-Path ([System.IO.Path]::GetTempPath()) ('1c-dryrun-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    $null = New-Item -ItemType Directory -Path $store -Force
    $saved = @{}
    $n = 0
    foreach ($rel in $before.Keys) {
        $full = Join-Path $Repo $rel
        if (Test-Path -LiteralPath $full -PathType Leaf) {
            $n++
            $copy = Join-Path $store ('{0:D5}.bin' -f $n)
            Copy-Item -LiteralPath $full -Destination $copy -Force
            $saved[$rel] = $copy
        } else {
            $saved[$rel] = $null
        }
    }

    Write-Section 'DRY RUN - the tool runs, the diff is shown, the tree is restored'
    $code = Invoke-Tool $ScriptPath $CallArgs

    $after = Get-DirtyMap $Repo
    $changed = New-Object System.Collections.ArrayList
    $keys = @($before.Keys) + @($after.Keys) | Sort-Object -Unique
    foreach ($rel in $keys) {
        $full = Join-Path $Repo $rel
        if ($before.ContainsKey($rel)) {
            $was = $saved[$rel]
            $now = Get-FileHashOrNull $full
            $then = if ($was) { Get-FileHashOrNull $was } else { $null }
            if ($now -ne $then) { $null = $changed.Add([pscustomobject]@{ Rel = $rel; Dirty = $true; Code = $before[$rel] }) }
        } else {
            $null = $changed.Add([pscustomobject]@{ Rel = $rel; Dirty = $false; Code = $after[$rel] })
        }
    }

    Write-Section 'diff'
    if ($changed.Count -eq 0) { Write-Host '(no changes)' }
    foreach ($c in $changed) {
        $full = Join-Path $Repo $c.Rel
        if ($c.Dirty) {
            $was = $saved[$c.Rel]
            $now = if (Test-Path -LiteralPath $full -PathType Leaf) { $full } else { $null }
            Show-FileDiff $was $now $c.Rel
        } elseif ($c.Code -eq '??') {
            Show-FileDiff $null $full $c.Rel
        } else {
            (Invoke-Git @('-C', $Repo, 'diff', '--no-color', '--', $c.Rel)).Output | ForEach-Object { Write-Host $_ }
        }
    }

    Write-Section 'restore'
    $failed = $false
    foreach ($c in $changed) {
        $full = Join-Path $Repo $c.Rel
        try {
            if ($c.Dirty) {
                $was = $saved[$c.Rel]
                if ($was) { Copy-Item -LiteralPath $was -Destination $full -Force }
                elseif (Test-Path -LiteralPath $full) { Remove-Item -LiteralPath $full -Force }
            } elseif ($c.Code -eq '??') {
                Remove-Item -LiteralPath $full -Force
                Remove-EmptyParents $full $Repo
            } else {
                if ((Invoke-Git @('-C', $Repo, 'checkout', '--quiet', '--', $c.Rel)).ExitCode -ne 0) { throw 'git checkout failed' }
            }
        } catch {
            $failed = $true
            Write-Host "  restore failed: $($c.Rel) - $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    # Verify: the dirty set and every saved file are back to where they were.
    $check = Get-DirtyMap $Repo
    foreach ($rel in (@($before.Keys) + @($check.Keys) | Sort-Object -Unique)) {
        if ($before.ContainsKey($rel) -ne $check.ContainsKey($rel)) { $failed = $true; Write-Host "  not restored: $rel" -ForegroundColor Red; continue }
        if ($saved.ContainsKey($rel) -and $saved[$rel]) {
            if ((Get-FileHashOrNull (Join-Path $Repo $rel)) -ne (Get-FileHashOrNull $saved[$rel])) {
                $failed = $true; Write-Host "  content differs: $rel" -ForegroundColor Red
            }
        }
    }
    if ($failed) {
        Write-Host "Restore incomplete. Saved copies of pre-existing work: $store" -ForegroundColor Red
        exit 2
    }
    Remove-Item -LiteralPath $store -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host ("tree restored; {0} file(s) would change. Re-run with -Apply to write." -f $changed.Count) -ForegroundColor DarkGray
    return $code
}

function Invoke-CopyPreview {
    # No git: content snapshot of the watched scope.
    param([string[]]$Paths, [string]$ScriptPath, $CallArgs)
    $files = @{}
    $store = Join-Path ([System.IO.Path]::GetTempPath()) ('1c-dryrun-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    $null = New-Item -ItemType Directory -Path $store -Force
    $n = 0
    foreach ($p in $Paths) {
        if (-not (Test-Path -LiteralPath $p)) { continue }
        $items = if (Test-Path -LiteralPath $p -PathType Container) { @(Get-ChildItem -LiteralPath $p -Recurse -File) } else { @(Get-Item -LiteralPath $p) }
        if ($files.Count + $items.Count -gt $MaxDirtySnapshot) {
            Remove-Item -LiteralPath $store -Recurse -Force
            Fail "DryRun refused: the scope outside git is too large to snapshot ($p). Put the dump under git, or narrow the target."
        }
        foreach ($f in $items) {
            if ($files.ContainsKey($f.FullName)) { continue }
            $n++
            $copy = Join-Path $store ('{0:D5}.bin' -f $n)
            Copy-Item -LiteralPath $f.FullName -Destination $copy -Force
            $files[$f.FullName] = $copy
        }
    }
    Write-Section 'DRY RUN (no git: snapshot of the target scope only)'
    Write-Host ("watched: {0}" -f ($Paths -join '; ')) -ForegroundColor DarkGray
    $code = Invoke-Tool $ScriptPath $CallArgs

    $changed = New-Object System.Collections.ArrayList
    foreach ($orig in $files.Keys) {
        if ((Get-FileHashOrNull $orig) -ne (Get-FileHashOrNull $files[$orig])) { $null = $changed.Add([pscustomobject]@{ Path = $orig; Kind = 'changed' }) }
    }
    foreach ($p in $Paths) {
        if (-not (Test-Path -LiteralPath $p)) { continue }
        $items = if (Test-Path -LiteralPath $p -PathType Container) { @(Get-ChildItem -LiteralPath $p -Recurse -File) } else { @(Get-Item -LiteralPath $p) }
        foreach ($f in $items) { if (-not $files.ContainsKey($f.FullName)) { $null = $changed.Add([pscustomobject]@{ Path = $f.FullName; Kind = 'added' }) } }
    }
    Write-Section 'diff'
    if ($changed.Count -eq 0) { Write-Host '(no changes in the watched scope)' }
    foreach ($c in $changed) {
        if ($c.Kind -eq 'added') { Show-FileDiff $null $c.Path $c.Path }
        elseif (Test-Path -LiteralPath $c.Path) { Show-FileDiff $files[$c.Path] $c.Path $c.Path }
        else { Show-FileDiff $files[$c.Path] $null $c.Path }
    }
    Write-Section 'restore'
    $failed = $false
    foreach ($c in $changed) {
        try {
            if ($c.Kind -eq 'added') { Remove-Item -LiteralPath $c.Path -Force }
            else { Copy-Item -LiteralPath $files[$c.Path] -Destination $c.Path -Force }
        } catch { $failed = $true; Write-Host "  restore failed: $($c.Path)" -ForegroundColor Red }
    }
    if ($failed) { Write-Host "Restore incomplete. Snapshot kept: $store" -ForegroundColor Red; exit 2 }
    Remove-Item -LiteralPath $store -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host 'Writes outside the watched scope are not seen without git.' -ForegroundColor DarkGray
    Write-Host ("scope restored; {0} file(s) would change. Re-run with -Apply to write." -f $changed.Count) -ForegroundColor DarkGray
    return $code
}

# ======================================================================= main
if ($Apply -and $DryRun) { Fail '-Apply and -DryRun together: pick one.' }

$scriptPath = Resolve-ToolScript -Name $Tool
$toolName = [System.IO.Path]::GetFileNameWithoutExtension($scriptPath)
$parameters = Get-ScriptParameters -ScriptPath $scriptPath
$gated = ([System.IO.File]::ReadAllText($scriptPath)).Contains('AIRULES_1C_GATE')

$targetPath = $null
if ($Object -and (Find-Parameter $parameters 'Object')) {
    # meta-remove / cfe-borrow take -Object themselves: pass it through untouched.
    $ToolArgs = @('-Object', $Object) + @($ToolArgs)
    $Object = $null
}
if ($Object) {
    $dumpRoot = Resolve-1CDumpRoot -Root $Root
    if (-not $dumpRoot) { Fail 'Cannot locate the configuration dump root. Pass -Root, or set EXPORT_PATH in .dev.env.' }
    $targetPath = Resolve-1CObjectPath -Address $Object -Root $dumpRoot
    $pathParam = Find-PathParameter -Parameters $parameters
    if (-not $pathParam) { Fail "$toolName takes no single path parameter - drop -Object and pass its own parameters." }
    $ToolArgs = @("-$pathParam", $targetPath) + @($ToolArgs)
}

$callArgs = ConvertTo-ParameterTable -Arguments @($ToolArgs) -Parameters $parameters

foreach ($k in @($callArgs.Keys)) {
    if ($k -eq 'Password' -or (Find-Parameter $parameters $k) -eq 'Password') {
        Fail 'A literal -Password is refused: put the password in an environment variable and pass -PasswordEnv <NAME>.'
    }
}
if ($PasswordEnv) {
    $pwParam = Find-Parameter $parameters 'Password'
    if (-not $pwParam) { Fail "$toolName takes no -Password; drop -PasswordEnv." }
    $secret = [Environment]::GetEnvironmentVariable($PasswordEnv)
    if ([string]::IsNullOrEmpty($secret)) {
        if ($Apply) { Fail "Environment variable $PasswordEnv is empty or missing." }
        Write-Host "[WARN] Environment variable $PasswordEnv is empty or missing - an -Apply run would fail." -ForegroundColor Yellow
    } else {
        $callArgs[$pwParam] = $secret
    }
}

# ------------------------------------------------------------ read-only tools
if (-not $gated) {
    if ($Apply -and (Find-Parameter $parameters 'Apply')) { $callArgs['Apply'] = [switch]$true }
    $global:LASTEXITCODE = 0
    & $scriptPath @callArgs
    exit $LASTEXITCODE
}

# -------------------------------------------------------- native -DryRun tools
if ($parameters.ContainsKey('DryRun')) {
    if ($Apply) {
        if ($ApplyAddsForce -contains $toolName) { $callArgs['Force'] = [switch]$true }
    } else {
        $callArgs['DryRun'] = [switch]$true
        Write-Section "DRY RUN via the tool's own -DryRun ($toolName)"
    }
    $code = Invoke-Tool $scriptPath $callArgs
    if (-not $Apply) { Write-Host 'Re-run with -Apply to write.' -ForegroundColor DarkGray }
    exit $code
}

# ----------------------------------------------------- platform / server tools
if ($ExternalTools -contains $toolName) {
    if (-not $Apply) {
        Write-Host ('DRY RUN: would run {0}' -f (Format-CallForDisplay $toolName $callArgs)) -ForegroundColor Yellow
        $synopsis = Get-ToolSynopsis $scriptPath
        if ($synopsis) { Write-Host "  ($synopsis)" }
        Write-Host 'No changes made. Re-run with -Apply to execute.'
        exit 0
    }
    exit (Invoke-Tool $scriptPath $callArgs)
}

# ----------------------------------------------------------------- file tools
$anchor = $targetPath
if (-not $anchor) {
    foreach ($k in $callArgs.Keys) {
        $canonical = Find-Parameter $parameters $k
        if (-not $canonical -or $canonical -notmatch '(Path|Dir|File|Root)$') { continue }
        $v = [string]$callArgs[$k]
        if (-not $v) { continue }
        $full = if ([System.IO.Path]::IsPathRooted($v)) { $v } else { Join-Path (Get-Location).Path $v }
        if ((Test-Path -LiteralPath $full) -or (Test-Path -LiteralPath (Split-Path $full -Parent))) { $anchor = $full; break }
    }
}
if (-not $anchor) { $anchor = (Get-Location).Path }

$repo = Get-RepoRoot $anchor

if ($Apply) {
    $before = if ($repo) { Get-DirtyMap $repo } else { $null }
    $code = Invoke-Tool $scriptPath $callArgs
    if ($repo -and $null -ne $before) {
        $after = Get-DirtyMap $repo
        $new = @($after.Keys | Where-Object { -not $before.ContainsKey($_) } | Sort-Object)
        Write-Section 'written (newly changed paths; files dirty before the run are not listed)'
        if ($new.Count -eq 0) { Write-Host '(none)' } else { $new | ForEach-Object { Write-Host "  $($after[$_]) $_" } }
    }
    exit $code
}

if ($repo) {
    $code = Invoke-GitPreview -Repo $repo -ScriptPath $scriptPath -CallArgs $callArgs
    if ($null -ne $code) { exit $code }
}
$watch = @()
if ($targetPath) { $watch += Get-1CWatchPaths -TargetPath $targetPath }
elseif (Test-Path -LiteralPath $anchor -PathType Leaf) { $watch += Get-1CWatchPaths -TargetPath $anchor }
elseif (Test-Path -LiteralPath $anchor) { $watch += $anchor }
if ($Scope) { $watch += $Scope }
$watch = @($watch | Where-Object { $_ } | Sort-Object -Unique)
if ($watch.Count -eq 0) { Fail 'DryRun needs something to watch outside git: pass -Object, the tool''s path, or -Scope.' }
exit (Invoke-CopyPreview -Paths $watch -ScriptPath $scriptPath -CallArgs $callArgs)
