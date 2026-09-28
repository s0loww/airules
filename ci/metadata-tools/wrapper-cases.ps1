# airules: regression cases for OUR wrapper (tools/_common/Invoke-1CEdit.ps1).
# Dot-sourced by metadata-tools-regression.ps1 in place of upstream's wrapper cases
# (ci/sync_metadata_manage.py cuts those out): upstream's wrapper applies by default
# and refuses a dirty tree; ours is DryRun by default and protects a dirty tree.
# Helpers (Register-Case, Copy-Fixture, Invoke-Tool, Get-DumpFacts, ...) come from
# the host script.

function Test-InsideGitRepo([string]$Dir) {
    $ErrorActionPreference = 'Continue'
    & git -C $Dir rev-parse --is-inside-work-tree 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Get-GitStatusSet([string]$Dir) {
    return (@(& git -C $Dir status --porcelain --untracked-files=all) | Sort-Object) -join '|'
}

Register-Case 'airules wrapper: DryRun under git shows the diff, restores the tree, keeps work in progress' {
    param($work)
    $dump = Join-Path $work 'dump'
    Copy-Fixture 'config-dump' $dump
    Initialize-GitDump $dump

    $module = Join-Path $dump 'Catalogs\TestCatalog\Ext\ObjectModule.bsl'
    Add-Content -LiteralPath $module -Value '// uncommitted work'
    $notes = Join-Path $dump 'notes.txt'
    [IO.File]::WriteAllText($notes, 'untracked work')
    $moduleHash = (Get-FileHash -LiteralPath $module).Hash
    $statusBefore = Get-GitStatusSet $dump

    $run = Invoke-Tool $InvokeEdit @('-Tool', 'meta-edit', '-Object', 'Catalog.TestCatalog',
        '-Root', $dump, '-Operation', 'add-attribute', '-Value', 'DryProbe: String', '-NoValidate') $dump

    Assert-Equal 0 $run.ExitCode "DryRun failed (stdout: $($run.StdOut) stderr: $($run.StdErr))"
    Assert-True ($run.StdOut -match 'DryProbe') 'the diff did not show the attribute the run added'
    Assert-True ($run.StdOut -match 'tree restored') 'the run did not report the restore'
    Assert-Equal $moduleHash (Get-FileHash -LiteralPath $module).Hash 'work in progress in a tracked file'
    Assert-Equal 'untracked work' ([IO.File]::ReadAllText($notes)) 'an untracked file'
    Assert-Equal $statusBefore (Get-GitStatusSet $dump) 'git status after the DryRun'
    Assert-True ((Get-FileFacts (Join-Path $dump 'Catalogs\TestCatalog.xml')).Text -notmatch 'DryProbe') `
        'the DryRun left the attribute in the object'
}

Register-Case 'airules wrapper: DryRun outside git restores the scope byte-for-byte' {
    param($work)
    $dump = Join-Path $work 'dump'
    Copy-Fixture 'config-dump' $dump
    Assert-True (-not (Test-InsideGitRepo $dump)) "precondition: $dump must not be inside a git repository"
    $before = Get-DumpFacts $dump

    $run = Invoke-Tool $InvokeEdit @('-Tool', 'meta-edit', '-Object', 'Catalog.TestCatalog',
        '-Root', $dump, '-Operation', 'add-attribute', '-Value', 'PreviewProbe: String', '-NoValidate') $dump

    Assert-True ($run.StdOut -match 'PreviewProbe') 'the diff did not show the attribute the run added'
    Assert-True ($run.StdOut -match 'scope restored') 'the run did not report the restore'
    Assert-DumpIdentical $before (Get-DumpFacts $dump) 'the DryRun left changes behind'
}

Register-Case 'airules wrapper: -Apply writes' {
    param($work)
    $dump = Join-Path $work 'dump'
    Copy-Fixture 'config-dump' $dump
    $target = Join-Path $dump 'Catalogs\TestCatalog.xml'
    $before = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash

    $run = Invoke-Tool $InvokeEdit @('-Tool', 'meta-edit', '-Object', 'Catalog.TestCatalog',
        '-Root', $dump, '-Operation', 'add-attribute', '-Value', 'AppliedProbe: String', '-NoValidate', '-Apply') $dump
    Assert-Equal 0 $run.ExitCode "apply failed (stdout: $($run.StdOut) stderr: $($run.StdErr))"

    Assert-True ($before -ne (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash) 'the apply path changed nothing'
    $facts = Get-FileFacts $target
    Assert-True ($facts.Text -match 'AppliedProbe') 'the attribute is missing from the applied file'
    Assert-True $facts.Bom 'the applied file lost its BOM'
}

Register-Case 'airules wrapper: a writing tool called directly exits 3 and writes nothing' {
    param($work)
    $dump = Join-Path $work 'dump'
    Copy-Fixture 'config-dump' $dump
    $before = Get-DumpFacts $dump
    $saved = $env:AIRULES_1C_GATE
    Remove-Item Env:\AIRULES_1C_GATE -ErrorAction SilentlyContinue
    try {
        $run = Invoke-Tool $MetaEdit @('-ObjectPath', (Join-Path $dump 'Catalogs\TestCatalog.xml'),
            '-Operation', 'add-attribute', '-Value', 'Direct: String', '-NoValidate') $dump
    } finally {
        $env:AIRULES_1C_GATE = $saved
    }
    Assert-Equal 3 $run.ExitCode 'a direct call of a writing tool'
    Assert-True ($run.StdErr -match 'Invoke-1CEdit') 'the refusal does not name the wrapper'
    Assert-DumpIdentical $before (Get-DumpFacts $dump) 'the gated tool wrote anyway'
}

Register-Case 'airules wrapper: platform tools print a masked plan; a literal -Password is refused' {
    param($work)
    $env:AIRULES_PROBE_PW = 'probe-s3cret'
    try {
        $plan = Invoke-Tool $InvokeEdit @('-Tool', 'db-update', '-InfoBasePath', (Join-Path $work 'ib'),
            '-UserName', 'Admin', '-PasswordEnv', 'AIRULES_PROBE_PW') $work
        $literal = Invoke-Tool $InvokeEdit @('-Tool', 'db-update', '-InfoBasePath', (Join-Path $work 'ib'),
            '-UserName', 'Admin', '-Password', 'probe-s3cret', '-Apply') $work
    } finally {
        Remove-Item Env:\AIRULES_PROBE_PW -ErrorAction SilentlyContinue
    }
    Assert-Equal 0 $plan.ExitCode "the DryRun plan (stderr: $($plan.StdErr))"
    Assert-True ($plan.StdOut -match 'DRY RUN: would run db-update') 'no plan was printed'
    Assert-True ($plan.StdOut -match '-Password "\*\*\*"') 'the password from -PasswordEnv did not reach the plan masked'
    Assert-True (($plan.StdOut + $plan.StdErr) -notmatch 'probe-s3cret') 'the password leaked into the output'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $work 'ib'))) 'the DryRun touched the infobase path'
    Assert-Equal 2 $literal.ExitCode 'a literal -Password'
}

Register-Case 'airules wrapper: a tool with its own -DryRun gets it; meta-remove -Object passes through' {
    param($work)
    $src = Join-Path $work 'src'
    Copy-Fixture 'epf-with-form' $src
    $before = Get-DumpFacts $src
    $run = Invoke-Tool $InvokeEdit @('-Tool', 'remove-form', '-ObjectName', 'Obrabotka', '-FormName', 'MainForm',
        '-SrcDir', $src) $src
    Assert-True ($run.StdOut -match 'own -DryRun') 'the native dry-run path was not taken'
    Assert-DumpIdentical $before (Get-DumpFacts $src) 'the native dry-run wrote to the tree'

    $dump = Join-Path $work 'dump'
    Copy-Fixture 'config-dump' $dump
    $beforeDump = Get-DumpFacts $dump
    $rm = Invoke-Tool $InvokeEdit @('-Tool', 'meta-remove', '-ConfigDir', $dump, '-Object', 'Catalog.TestCatalog') $dump
    Assert-True (($rm.StdOut + $rm.StdErr) -notmatch 'takes no single path parameter') '-Object was resolved instead of passed through'
    Assert-True ($rm.StdOut -match 'DRY-RUN') "meta-remove did not run its own dry run (stdout: $($rm.StdOut) stderr: $($rm.StdErr))"
    Assert-DumpIdentical $beforeDump (Get-DumpFacts $dump) 'meta-remove dry run wrote to the dump'
}

Register-Case 'airules wrapper: a read-only tool exits 0, a tool failure keeps its own code' {
    param($work)
    $ext = Join-Path $work 'Roles\ProbeRole\Ext'
    New-Item -ItemType Directory -Path $ext -Force | Out-Null
    $rights = Join-Path $ext 'Rights.xml'
    [IO.File]::WriteAllText($rights, (
        '<?xml version="1.0" encoding="UTF-8"?>' + "`n" +
        '<Rights xmlns="http://v8.1c.ru/8.2/roles" version="2.17">' + "`n" +
        "`t<object><name>Catalog.TestCatalog</name><right><name>Read</name><value>true</value></right></object>`n" +
        '</Rights>' + "`n"), (New-Object Text.UTF8Encoding($true)))

    $run = Invoke-Tool $InvokeEdit @('-Tool', 'role-info', '-Path', $rights) $work
    Assert-True ($run.StdOut -match 'TestCatalog: Read') "the role rights were not printed (stderr: $($run.StdErr))"
    Assert-Equal 0 $run.ExitCode 'a successful read-only run'

    $missing = Join-Path $ext 'Missing.xml'
    $run = Invoke-Tool $InvokeEdit @('-Tool', 'role-info', '-Path', $missing) $work
    Assert-True ($run.StdOut -match 'File not found') "the failure probe did not reach the tool (stdout: $($run.StdOut))"
    Assert-Equal 1 $run.ExitCode 'the tool own failure through the wrapper'
}
