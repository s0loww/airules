#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('bootstrap', 'doctor', 'analyze', 'deploy', 'test', 'unit', 'serve', 'stop')]
    [string]$Command = 'doctor',

    [string]$Profile = (Join-Path (Get-Location) 'agent-1c.json'),
    [switch]$Apply,

    # test: как Vanessa подключается к файловой ИБ — напрямую (/F) или через ibsrv
    # (/WS). Пусто — из профиля vanessa.connection, иначе file.
    [ValidateSet('', 'file', 'ibsrv')]
    [string]$Connection = '',

    # test: прогнать Vanessa на невидимом рабочем столе Windows — окна тест-клиента
    # не появляются на мониторе (lib/hidden-desktop.ps1).
    [switch]$Hidden,

    # Optional DSH workflow protocol. All fields are required together for an
    # identified deploy; ordinary CLI use keeps its historical report format.
    [string]$WorkflowRunId = '',
    [string]$WorkflowStepId = '',
    [string]$WorkflowSourceDigest = '',
    [string]$WorkflowTargetDigest = '',
    [string]$WorkflowProfileDigest = '',
    [string]$WorkflowExactBuild = '',
    [string]$WorkflowTargetPath = '',
    [ValidateSet('file', 'server')][string]$WorkflowTargetKind = 'file',
    [string]$WorkflowTargetServer = '',
    [string]$WorkflowTargetRef = ''
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$script:Steps = New-Object System.Collections.ArrayList
$script:Warnings = New-Object System.Collections.ArrayList
$script:Artifacts = New-Object System.Collections.ArrayList
$script:ExitCode = 0
$script:StartedAt = [DateTime]::UtcNow
$script:WorkflowMutationState = 'not-applied'
$script:WorkflowProtocol = $false
$script:ToolRoot = Join-Path $env:LOCALAPPDATA 'agent-1c\tools'
$script:LockPath = Join-Path $PSScriptRoot 'toolchain.lock.json'

function Assert-WorkflowPathNoReparse {
    param([string]$Path)
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'WORKFLOW_PATH_ALIAS_FORBIDDEN' }
        }
        $parent = [IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) { break }
        $cursor = $parent.FullName
    }
}

function Assert-WorkflowPlatformTool {
    param([string]$Path)
    if (-not $script:WorkflowProtocol) { return }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'WORKFLOW_PLATFORM_TOOL_MISSING' }
    Assert-WorkflowPathNoReparse $Path
    $tool = Get-Item -LiteralPath $Path
    $version = $tool.VersionInfo
    $build = '{0}.{1}.{2}.{3}' -f $version.FileMajorPart, $version.FileMinorPart, $version.FileBuildPart, $version.FilePrivatePart
    if ($tool.Directory.Parent.Name -ne $WorkflowExactBuild -or $build -ne $WorkflowExactBuild) { throw 'WORKFLOW_PLATFORM_BUILD_MISMATCH' }
}

function Get-WorkflowServerIdentity {
    param([string]$Server, [string]$Ref)
    if ($Server.Length -gt 300) { throw 'WORKFLOW_SERVER_TARGET_INVALID' }
    $endpoint = $Server.Trim().ToLowerInvariant()
    $port = 1541
    if ($endpoint.StartsWith('[')) {
        if ($endpoint -notmatch '^\[([^\]]+)\](?::(\d{1,5}))?$') { throw 'WORKFLOW_SERVER_TARGET_INVALID' }
        $addressText = $Matches[1]; $portText = $Matches[2]
        $address = $null
        if (-not [Net.IPAddress]::TryParse($addressText, [ref]$address) -or $address.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetworkV6) { throw 'WORKFLOW_SERVER_TARGET_INVALID' }
        $bytes = $address.GetAddressBytes(); $groups = @()
        for ($i = 0; $i -lt 16; $i += 2) { $groups += ('{0:x2}{1:x2}' -f $bytes[$i], $bytes[$i+1]) }
        $hostName = '[' + ($groups -join ':') + ']'
        if ($portText) { $port = [int]$portText }
    } else {
        if ($endpoint -notmatch '^([a-z0-9_][a-z0-9_.-]*)(?::(\d{1,5}))?$') { throw 'WORKFLOW_SERVER_TARGET_INVALID' }
        $hostName = $Matches[1].TrimEnd('.'); $portText = $Matches[2]
        if (-not $hostName -or @($hostName.Split('.') | Where-Object { -not $_ -or $_.StartsWith('-') -or $_.EndsWith('-') }).Count -gt 0) { throw 'WORKFLOW_SERVER_TARGET_INVALID' }
        if ($portText) { $port = [int]$portText }
    }
    if ($port -lt 1 -or $port -gt 65535 -or $Ref.Length -gt 200 -or $Ref -match '[\\/;"\x00-\x1f]' -or $Ref.Contains("'")) { throw 'WORKFLOW_SERVER_TARGET_INVALID' }
    $reference = $Ref.Trim().Normalize().ToLowerInvariant()
    if (-not $reference) { throw 'WORKFLOW_SERVER_TARGET_INVALID' }
    return @{ server = ($hostName + ':' + $port); ref = $reference }
}

# Сторож над 1cv8 и межпроцессный лок на базу. Скрипты проекта, ходящие в ту
# же ИБ мимо этого контура, обязаны подключать ЭТОТ же файл: лок, накрывающий
# один путь из двух, не гарантирует ничего.
. (Join-Path $PSScriptRoot 'lib\1c-guard.ps1')

function Get-1CBaseIdentity {
    <# Строка, однозначно определяющая базу, — ключ лока. #>
    param($Target, [string]$ResolvedPath)

    if ($Target.kind -eq 'file') { return $ResolvedPath }
    if ($Target.kind -eq 'server') { return ([string]$Target.server + '/' + [string]$Target.ref) }
    return ''
}

function Add-Step {
    param([string]$Name, [string]$Status, [string]$Message)
    [void]$script:Steps.Add([ordered]@{ name = $Name; status = $Status; message = $Message })
}

function Resolve-ProjectPath {
    param([string]$PathValue, [string]$ProjectRoot)
    if ([IO.Path]::IsPathRooted($PathValue)) { return [IO.Path]::GetFullPath($PathValue) }
    return [IO.Path]::GetFullPath((Join-Path $ProjectRoot $PathValue))
}

function Read-EnvSection {
    param([string]$Path, [string]$Section)
    $values = @{}
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) { return $values }
    $currentSection = ''
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $text = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($text) -or $text.StartsWith('#')) { continue }
        if ($text -match '^\[(.+)\]$') { $currentSection = $Matches[1].Trim(); continue }
        if ($currentSection -ne $Section) { continue }
        if ($text -match '^([^=]+?)\s*=\s*(.*)$') {
            $key = $Matches[1].Trim()
            $value = $Matches[2].Trim().Trim('"').Trim("'")
            $values[$key] = $value
        }
    }
    return $values
}

function Resolve-TargetCredentials {
    param($Target)
    $result = [ordered]@{ user = $null; password = $null; path = $null }  # airules:allow creds-password (field init, not a hardcoded secret)
    $envValues = @{}
    if ($Target.envFile) {
        $envPath = Resolve-ProjectPath $Target.envFile $script:ProjectRoot
        $envValues = Read-EnvSection $envPath ([string]$Target.envSection)
    }
    if ($Target.userEnv) {
        $envUser = [Environment]::GetEnvironmentVariable([string]$Target.userEnv)
        if ($envUser) { $result.user = $envUser }
    }
    if (-not $result.user -and $envValues.ContainsKey('Login')) { $result.user = $envValues['Login'] }
    if ($Target.passwordEnv) {
        $envPassword = [Environment]::GetEnvironmentVariable([string]$Target.passwordEnv)  # airules:allow creds-password (reads env var, no literal secret)
        if ($envPassword) { $result.password = $envPassword }  # airules:allow creds-password (assignment from env, no literal secret)
    }
    if (-not $result.password -and $envValues.ContainsKey('Pass')) { $result.password = $envValues['Pass'] }  # airules:allow creds-password (reads .env value, no literal secret)
    if ($Target.path) { $result.path = Resolve-ProjectPath $Target.path $script:ProjectRoot }
    elseif ($envValues.ContainsKey('Path')) { $result.path = $envValues['Path'] }
    elseif ($envValues.ContainsKey('File')) { $result.path = $envValues['File'] }
    return $result
}

function Quote-IfNeeded {
    param([string]$Value)
    if ($Value -match '[\s"]') { return '"' + ($Value -replace '"', '\"') + '"' }
    return $Value
}

function Format-DeployCommandLine {
    param([string]$Exe, $Arguments, [string]$Secret)
    $line = (Quote-IfNeeded $Exe) + ' ' + (($Arguments | ForEach-Object { [string]$_ }) -join ' ')
    if (-not [string]::IsNullOrEmpty($Secret)) { $line = $line.Replace($Secret, '<hidden>') }
    return $line
}

function Get-VrunnerPath {
    $command = Get-Command 'vrunner' -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidates = @(
        (Join-Path $script:ToolRoot 'onescript\bin\vrunner.bat'),
        (Join-Path $script:ToolRoot 'onescript\bin\vrunner')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

function Get-Platform {
    param($ProfileData)
    if ($ProfileData.platform.executable) {
        $explicit = Resolve-ProjectPath $ProfileData.platform.executable $script:ProjectRoot
        if (Test-Path -LiteralPath $explicit -PathType Leaf) { return Get-Item -LiteralPath $explicit }
    }

    $candidates = @()
    foreach ($root in @('C:\Program Files\1cv8', 'C:\Program Files (x86)\1cv8')) {
        if (Test-Path -LiteralPath $root) {
            $candidates += Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
                Where-Object { -not $ProfileData.platform.versionPrefix -or $_.Name.StartsWith([string]$ProfileData.platform.versionPrefix) } |
                ForEach-Object { Get-Item -LiteralPath (Join-Path $_.FullName 'bin\1cv8.exe') -ErrorAction SilentlyContinue }
        }
    }
    return $candidates | Sort-Object { try { [version]$_.Directory.Parent.Name } catch { [version]'0.0' } } -Descending | Select-Object -First 1
}

function Get-BslExecutable {
    $lock = Get-Content -LiteralPath $script:LockPath -Raw | ConvertFrom-Json
    $base = Join-Path $script:ToolRoot ("bsl-language-server\" + $lock.bslLanguageServer.version)
    return Join-Path $base $lock.bslLanguageServer.executable
}

function Install-BslLanguageServer {
    $lock = Get-Content -LiteralPath $script:LockPath -Raw | ConvertFrom-Json
    $target = Join-Path $script:ToolRoot ("bsl-language-server\" + $lock.bslLanguageServer.version)
    $exe = Join-Path $target $lock.bslLanguageServer.executable
    if (Test-Path -LiteralPath $exe) {
        Add-Step 'bootstrap.bsl' 'skipped' ("Уже установлен: " + $exe)
        return $exe
    }

    New-Item -ItemType Directory -Path $target -Force | Out-Null
    $archive = Join-Path $env:TEMP ("bsl-language-server-" + $lock.bslLanguageServer.version + '.zip')
    Invoke-WebRequest -Uri $lock.bslLanguageServer.url -OutFile $archive -UseBasicParsing
    $actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
    if ($actualHash -ne $lock.bslLanguageServer.sha256) {
        throw "Контрольная сумма BSL LS не совпала. Ожидалась $($lock.bslLanguageServer.sha256), получена $actualHash"
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $target -Force
    if (-not (Test-Path -LiteralPath $exe)) { throw "BSL LS распакован, но executable не найден: $exe" }
    Add-Step 'bootstrap.bsl' 'ok' ("Установлен BSL LS " + $lock.bslLanguageServer.version)
    return $exe
}

function Get-TargetArguments {
    param($Target, $ResolvedPath)
    if ($Target.kind -eq 'file') {
        if ([string]::IsNullOrWhiteSpace($ResolvedPath)) { throw 'Путь файловой ИБ не определён (testTarget.path пуст и не найден Path в envFile).' }
        return @('/F', ('"' + $ResolvedPath + '"'))
    }
    if ($Target.kind -eq 'server') { return @('/S', ('"' + $Target.server + '/' + $Target.ref + '"')) }
    throw 'Тестовая цель не настроена.'
}

function Add-Credentials {
    param([System.Collections.ArrayList]$Arguments, $Credentials)
    if ($Credentials.user) { [void]$Arguments.Add('/N'); [void]$Arguments.Add((Quote-IfNeeded $Credentials.user)) }
    if ($Credentials.password) { [void]$Arguments.Add('/P'); [void]$Arguments.Add((Quote-IfNeeded $Credentials.password)) }
}

function Invoke-Doctor {
    $platform = Get-Platform $script:ProfileData
    if ($platform) { Add-Step 'doctor.platform' 'ok' $platform.FullName } else { Add-Step 'doctor.platform' 'error' '1cv8.exe не найден'; $script:ExitCode = 2 }

    $bsl = Get-BslExecutable
    if (Test-Path -LiteralPath $bsl) {
        $lock = Get-Content -LiteralPath $script:LockPath -Raw | ConvertFrom-Json
        Add-Step 'doctor.bsl' 'ok' ("$bsl (закреплена версия $($lock.bslLanguageServer.version))")
    } else {
        Add-Step 'doctor.bsl' 'warning' 'BSL LS не установлен; выполните bootstrap'
        [void]$script:Warnings.Add('BSL LS недоступен')
    }

    if ($platform) {
        foreach ($tool in @('ibcmd.exe', 'ibsrv.exe')) {
            $found = Get-PlatformBinTool $platform $tool
            if ($found) { Add-Step "doctor.$tool" 'ok' $found }
            else { Add-Step "doctor.$tool" 'optional' "Нет в сборке $($platform.Directory.Parent.Name): установлен только клиент. Для deploy через ibcmd и serve нужен компонент сервера той же сборки." }
        }
        $target = $script:ProfileData.testTarget
        if ($target -and $target.kind -and $target.kind -ne 'none') { Add-Step 'doctor.engine' 'ok' ("deploy пойдёт через: " + (Get-DeployEngine $target $platform)) }
    }

    $vrunner = Get-VrunnerPath
    if ($vrunner) { Add-Step 'doctor.vanessa-runner' 'ok' $vrunner } else { Add-Step 'doctor.vanessa-runner' 'optional' 'Не установлен' }
}

function Get-BslFilesWithoutBom {
    <# Модули .bsl без сигнатуры UTF-8. Такой файл с кириллицей роняет
       /LoadConfigFromFiles МОЛЧА: пустой лог, нечитаемый код возврата. Расширение
       грузится целиком, поэтому один файл блокирует деплой всем сразу. У .xml
       кодировка объявлена внутри файла — сигнатура ему не нужна. #>
    param([string]$Source)
    $result = New-Object System.Collections.Generic.List[string]
    foreach ($file in (Get-ChildItem -LiteralPath $Source -Recurse -Filter '*.bsl' -File)) {
        if ($file.Length -eq 0) { continue }  # пустой модуль читать нечем — не ломает
        $head = New-Object byte[] 3
        $stream = [System.IO.File]::OpenRead($file.FullName)
        try { $read = $stream.Read($head, 0, 3) } finally { $stream.Dispose() }
        if ($read -lt 3 -or $head[0] -ne 0xEF -or $head[1] -ne 0xBB -or $head[2] -ne 0xBF) {
            $result.Add($file.FullName.Substring($Source.Length).TrimStart('\', '/'))
        }
    }
    return $result.ToArray()
}

function Format-BomFileList {
    # Список бывает на десятки файлов: показываем первые, остальное считаем.
    param([string[]]$Files, [int]$Limit = 10)
    if ($Files.Count -le $Limit) { return ($Files -join '; ') }
    return (($Files[0..($Limit - 1)]) -join '; ') + "; и ещё $($Files.Count - $Limit)"
}

function Invoke-Analyze {
    $bsl = Get-BslExecutable
    if (-not (Test-Path -LiteralPath $bsl)) { throw 'BSL LS не установлен. Сначала выполните bootstrap.' }
    $source = Resolve-ProjectPath $script:ProfileData.sourceDir $script:ProjectRoot
    if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "Каталог исходников не найден: $source" }

    # Кодировка: анализу сигнатура не нужна — BSL LS читает UTF-8 и без неё, поэтому
    # здесь предупреждение. Отказ живёт в Invoke-Deploy, где сигнатура решает.
    $withoutBom = @(Get-BslFilesWithoutBom $source)
    if ($withoutBom.Count -gt 0) {
        Add-Step 'analyze.encoding' 'warning' ("Модули .bsl без UTF-8 BOM ($($withoutBom.Count)): " + (Format-BomFileList $withoutBom) + '. Анализу не мешает, но деплой через конфигуратор упадёт без внятной ошибки — исправить до деплоя.')
    }
    else {
        Add-Step 'analyze.encoding' 'ok' 'Все модули .bsl в UTF-8 с сигнатурой'
    }
    $out = Join-Path $script:RunDir 'bsl'
    New-Item -ItemType Directory -Path $out -Force | Out-Null
    $stdout = Join-Path $out 'stdout.log'
    $stderr = Join-Path $out 'stderr.log'
    $arguments = @('analyze', '--srcDir', ('"' + $source + '"'), '--workspaceDir', ('"' + $script:ProjectRoot + '"'), '--outputDir', ('"' + $out + '"'), '--reporter', 'json', '--reporter', 'junit', '--reporter', 'sarif', '--silent')
    $process = Start-Process -FilePath $bsl -ArgumentList $arguments -Wait -PassThru -NoNewWindow -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $code = $process.ExitCode
    [void]$script:Artifacts.Add($out)
    if ($code -ne 0) { Add-Step 'analyze.bsl' 'error' "BSL LS завершился с кодом $code"; $script:ExitCode = $code }
    else {
        $jsonReport = Join-Path $out 'bsl-json.json'
        $severityCounts = @{}
        if (Test-Path -LiteralPath $jsonReport) {
            $analysis = Get-Content -LiteralPath $jsonReport -Raw | ConvertFrom-Json
            foreach ($diagnostic in ($analysis.fileinfos | ForEach-Object { @($_.diagnostics) })) {
                if ($diagnostic.severity) {
                    if (-not $severityCounts.ContainsKey($diagnostic.severity)) { $severityCounts[$diagnostic.severity] = 0 }
                    $severityCounts[$diagnostic.severity]++
                }
            }
        }
        $summary = ($severityCounts.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ', '
        if ($severityCounts.ContainsKey('Error') -and $severityCounts['Error'] -gt 0) {
            Add-Step 'analyze.bsl' 'error' "Найдены ошибки: $summary. Отчёты: $out"
            $script:ExitCode = 4
        } else {
            Add-Step 'analyze.bsl' 'ok' "Результат: $summary. Отчёты: $out"
        }
    }
}

function Get-PlatformBinTool {
    <# ibcmd.exe / ibsrv.exe из каталога ТОЙ ЖЕ сборки, что выбранный 1cv8.exe.
       Клиентская установка их не содержит — тогда $null. #>
    param($Platform, [string]$Name)
    if (-not $Platform) { return $null }
    $candidate = Join-Path $Platform.Directory.FullName $Name
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { Assert-WorkflowPlatformTool $candidate; return $candidate }
    return $null
}

function Get-DeployEngine {
    <# designer | ibcmd. auto: ibcmd для файловой ИБ, если он есть в выбранной сборке.
       База под кластером — только конфигуратор: ibcmd в её СУБД мимо кластера не ходит. #>
    param($Target, $Platform)
    $engine = 'auto'
    if ($script:ProfileData.platform -and $script:ProfileData.platform.engine) { $engine = [string]$script:ProfileData.platform.engine }
    if ($Target.kind -eq 'server') {
        if ($engine -eq 'ibcmd') { throw 'engine=ibcmd для серверной ИБ запрещён: база под кластером обслуживается только через кластер (rules/test-model.md). Уберите platform.engine или поставьте designer.' }
        return 'designer'
    }
    if ($engine -eq 'designer') { return 'designer' }
    $ibcmd = Get-PlatformBinTool $Platform 'ibcmd.exe'
    if ($engine -eq 'ibcmd' -and -not $ibcmd) { throw "engine=ibcmd, но в сборке $($Platform.Directory.Parent.Name) нет ibcmd.exe (установлен только клиент; нужен компонент сервера)." }
    if ($ibcmd) { return 'ibcmd' }
    return 'designer'
}

function Get-ServerDataDir {
    <# Каталог состояния автономного сервера — рядом с базой, НЕ внутри неё:
       его можно стереть, не тронув саму ИБ. #>
    param($Target, [string]$ResolvedPath)
    if ($Target.dataDir) { return Resolve-ProjectPath $Target.dataDir $script:ProjectRoot }
    return ($ResolvedPath.TrimEnd('\', '/') + '_ServerData')
}

function Get-IbsrvDataDir {
    <# Каталог данных ibsrv — ОТДЕЛЬНЫЙ от каталога ibcmd (Get-ServerDataDir).
       В общем каталоге сеансы веб-клиента ibsrv, погашенного нештатно, остаются в
       session-data, и следующий `ibcmd config apply` видит их активными и падает на
       «Ошибка исключительной блокировки» — при том что живого сервера уже нет.
       Раздельные каталоги: мусор ibsrv не мешает деплою, а каталог ibsrv можно
       стереть целиком, не трогая ни базу, ни состояние ibcmd. #>
    param($Target, [string]$ResolvedPath)
    if ($Target.ibsrvDataDir) { return Resolve-ProjectPath $Target.ibsrvDataDir $script:ProjectRoot }
    return ($ResolvedPath.TrimEnd('\', '/') + '_ibsrv')
}

function Get-IbcmdBaseArgs {
    param([string]$DbPath, [string]$DataDir, $Credentials)
    $list = @(('--db-path="' + $DbPath + '"'), ('--data="' + $DataDir + '"'))
    if ($Credentials.user) { $list += ('--user=' + (Quote-IfNeeded $Credentials.user)) }
    if ($Credentials.password) { $list += ('--password=' + (Quote-IfNeeded $Credentials.password)) }  # airules:allow creds-password (value from resolved credentials, redacted in reports)
    return $list
}

function Get-ServedIbsrv {
    <# Процессы ibsrv, обслуживающие ЭТУ базу, — по командной строке, а не по
       файлу состояния: файл мог пережить перезагрузку, процесс — нет. #>
    param([string]$DbPath)
    # Путь сравнивается ЦЕЛИКОМ, вместе с закрывающей кавычкой --db-path: подстрока
    # «<каталог>\ERP» совпала бы и с ibsrv базы «<каталог>\ERP_Sub», и serve/deploy одной
    # базы гасили бы сервер другой.
    $needle = ('--db-path="' + $DbPath.TrimEnd('\') + '"').ToLowerInvariant()
    return @(Get-CimInstance Win32_Process -Filter "Name='ibsrv.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine.ToLowerInvariant().Contains($needle) })
}

function Invoke-IbcmdBounded {
    <# Вызов ibcmd с потолком по времени. `ibcmd --pid=<pid> session list` без учётки
       или при подвисшем сервере ждёт бесконечно — прежний stop висел на нём. По
       истечении срока процесс снимается, вызывающий получает $null и идёт дальше. #>
    param([string]$Ibcmd, [string[]]$Arguments, [int]$Seconds = 15)
    $out = [IO.Path]::GetTempFileName(); $err = [IO.Path]::GetTempFileName()
    try {
        $p = Start-Process -FilePath $Ibcmd -ArgumentList $Arguments -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $out -RedirectStandardError $err
        [void]$p.Handle  # PS 5.1: без обращения к Handle ExitCode приходит $null
        if (-not $p.WaitForExit($Seconds * 1000)) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            return $null
        }
        return @(Get-Content -LiteralPath $out -Encoding UTF8 -ErrorAction SilentlyContinue)
    }
    finally {
        Remove-Item -LiteralPath $out, $err -Force -ErrorAction SilentlyContinue
    }
}

function Get-1CClientIds {
    return @(Get-Process -Name 1cv8, 1cv8c -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
}

function Wait-New1CClientsExit {
    <# Дождаться выхода клиентов 1С, появившихся после снимка $Before. vrunner
       возвращается раньше, чем тест-клиент отпускает файл базы; ibsrv, поднятый в
       этот зазор, стартует, но на запросы не отвечает. Возвращает число клиентов,
       не вышедших за срок. #>
    param([int[]]$Before, [int]$Seconds = 60)
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        $fresh = @(Get-1CClientIds | Where-Object { $Before -notcontains $_ })
        if ($fresh.Count -eq 0) { return 0 }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    return $fresh.Count
}

function Wait-1CProcessExit {
    param([int]$ProcessId, [int]$Seconds)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Stop-ServedIbsrv {
    <# Штатно закрыть сеансы (ibcmd --pid session terminate) и остановить ibsrv
       этой базы. Возвращает число остановленных процессов. Вызовы ibcmd - с учёткой
       базы и с потолком по времени (Invoke-IbcmdBounded): без них stop висел на
       `session list`, процесс снимали руками, и сеансы оставались в каталоге данных. #>
    param([string]$DbPath, [string]$Ibcmd, $Credentials = $null)
    $stopped = 0
    $auth = @()
    if ($Credentials -and $Credentials.user) { $auth += ('--user=' + (Quote-IfNeeded $Credentials.user)) }
    if ($Credentials -and $Credentials.password) { $auth += ('--password=' + (Quote-IfNeeded $Credentials.password)) }  # airules:allow creds-password (value from resolved credentials, never logged)
    foreach ($proc in (Get-ServedIbsrv $DbPath)) {
        $procId = [int]$proc.ProcessId
        if ($Ibcmd) {
            try {
                $listing = Invoke-IbcmdBounded $Ibcmd (@("--pid=$procId", 'session', 'list') + $auth) 15
                foreach ($line in @($listing)) {
                    if ([string]$line -match '^\s*session\s*:\s*([0-9a-fA-F-]{36})') {
                        [void](Invoke-IbcmdBounded $Ibcmd (@("--pid=$procId", 'session', 'terminate', "--session=$($Matches[1])", '--error-message="agent-1c maintenance"') + $auth) 15)
                    }
                }
            } catch { }
        }
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        [void](Wait-1CProcessExit $procId 15)
        $stopped++
    }
    return $stopped
}

function Suspend-TargetServices {
    <# Службы, держащие сеансы базы (веб-публикация, мост), останавливает сам
       скрипт, а не человек. Возвращает список реально остановленных. #>
    $stopped = @()
    if (-not $script:ProfileData.suspendServices) { return $stopped }
    foreach ($name in @($script:ProfileData.suspendServices)) {
        $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
        if (-not $svc) { Add-Step "services.suspend.$name" 'warning' 'Служба не найдена'; continue }
        if ($svc.Status -ne 'Running') { continue }
        try { Stop-Service -Name $name -Force -ErrorAction Stop }
        catch { throw "Не удалось остановить службу $name (нужны права администратора?): $($_.Exception.Message)" }
        $stopped += $name
        Add-Step "services.suspend.$name" 'ok' 'Остановлена на время операции'
    }
    return $stopped
}

function Resume-TargetServices {
    param($Names)
    foreach ($name in @($Names)) {
        if (-not $name) { continue }
        try { Start-Service -Name $name -ErrorAction Stop; Add-Step "services.resume.$name" 'ok' 'Запущена' }
        catch { Add-Step "services.resume.$name" 'error' "Не запустилась: $($_.Exception.Message)"; $script:ExitCode = 1 }
    }
}

function Add-DumpResult {
    <# /DumpResult — третий сигнал вердикта DESIGNER рядом с кодом выхода и /Out:
       1cv8 возвращает 0 и при проваленной пакетной операции (типично — «Не найден
       метод» перехватчика расширения), а число в этом файле — нет (0 = успех). #>
    param($ArgList, [string]$Path)
    [void]$ArgList.Add('/DumpResult'); [void]$ArgList.Add(('"' + $Path + '"'))
}

function Read-DumpResult {
    <# Число из файла /DumpResult; $null — файл не записан или не число. #>
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $text = ([IO.File]::ReadAllText($Path)).Trim([char]0xFEFF, [char]0x20, [char]0x0D, [char]0x0A, [char]0x09)
    $n = 0
    if ([int]::TryParse($text, [ref]$n)) { return $n }
    return $null
}

function Invoke-GuardedRun {
    <# Один запуск под сторожем с проверкой кода; общий для DESIGNER и ibcmd.
       Для DESIGNER ($Run.result) вердикт — код выхода И /DumpResult. #>
    param([string]$Exe, $Run, [string]$GuardLog, [string]$Prefix)
    # Устаревший файл результата прочитался бы как вердикт этого запуска.
    if ($Run.result -and (Test-Path -LiteralPath $Run.result)) { Remove-Item -LiteralPath $Run.result -Force }
    $params = @{ FilePath = $Exe; ArgumentList = ([string[]]$Run.args); Label = "$Prefix/$($Run.name)"; LogPath = $GuardLog }
    if ($Run.stdout) { $params['RedirectStandardOutput'] = $Run.stdout; $params['RedirectStandardError'] = $Run.stderr }
    $guard = Invoke-Guarded1C @params
    if ($Run.log) { [void]$script:Artifacts.Add($Run.log) }
    if ($Run.stdout) { [void]$script:Artifacts.Add($Run.stdout); [void]$script:Artifacts.Add($Run.stderr) }
    if ($guard.Killed) {
        $hint = ''
        if ($guard.DialogSeen) { $hint = ' У процесса было окно — вероятен модальный диалог платформы.' }
        Add-Step "$Prefix.$($Run.name)" 'error' "Сторож снял процесс: $($guard.Reason).$hint"
        throw "$Prefix ($($Run.name)) снят сторожем: $($guard.Reason).$hint См. $GuardLog"
    }
    if ($guard.ExitCode -ne 0) {
        $where = if ($Run.stdout) { $Run.stdout } else { $Run.log }
        throw "$Prefix ($($Run.name)) завершился с кодом $($guard.ExitCode). См. $where"
    }
    if ($Run.result) {
        $dump = Read-DumpResult $Run.result
        if ($null -eq $dump) { throw "$Prefix ($($Run.name)): код выхода 0, но /DumpResult не записан — результат пакетной операции неизвестен. См. $($Run.log)" }
        if ($dump -ne 0) { throw "$Prefix ($($Run.name)): код выхода 0, но /DumpResult = $dump — операция не выполнена. См. $($Run.log)" }
    }
    Add-Step "$Prefix.$($Run.name)" 'ok' "Шаг выполнен за $($guard.DurationSec) с, пик памяти $($guard.PeakPrivateGb) ГБ"
}

function Get-IbcmdDeployRuns {
    param([string]$Source, [string]$ExtensionName, [string[]]$BaseArgs)
    $ext = @()
    if ($ExtensionName) { $ext = @('--extension=' + (Quote-IfNeeded $ExtensionName)) }
    $steps = @()
    $steps += @{ name = 'import'; args = (@('infobase', 'config', 'import') + $BaseArgs + $ext + @('"' + $Source + '"')) }
    if ($ExtensionName -and $script:ProfileData.extension.scope) {
        # Расширение, меняющее общую структуру данных, требует области infobase ДО apply.
        $steps += @{ name = 'scope'; args = (@('infobase', 'config', 'extension', 'update') + $BaseArgs + @('--name=' + (Quote-IfNeeded $ExtensionName), '--scope=' + [string]$script:ProfileData.extension.scope)) }
    }
    $steps += @{ name = 'apply'; args = (@('infobase', 'config', 'apply') + $BaseArgs + $ext + @('--force')) }
    if ($ExtensionName -and ($script:ProfileData.extension.PSObject.Properties.Name -contains 'safeMode') -and ($script:ProfileData.extension.safeMode -eq $false)) {
        $steps += @{ name = 'safe-mode'; args = (@('infobase', 'config', 'extension', 'update') + $BaseArgs + @('--name=' + (Quote-IfNeeded $ExtensionName), '--safe-mode=no', '--unsafe-action-protection=no')) }
    }
    foreach ($step in $steps) {
        $step['stdout'] = Join-Path $script:RunDir ("ibcmd-" + $step.name + ".log")
        $step['stderr'] = Join-Path $script:RunDir ("ibcmd-" + $step.name + ".err.log")
    }
    return $steps
}

function Invoke-PostDeployProbe {
    <# Exit 0 загрузки — не доказательство. Проба: /CheckModules по контекстам
       из профиля (probe.checkModules). Лог /Out 8.3.27 — UTF-8 с BOM. #>
    param($Platform, $Target, $Credentials, [string]$GuardLog)
    if (-not $script:ProfileData.probe -or -not $script:ProfileData.probe.checkModules) {
        Add-Step 'deploy.probe' 'skipped' 'probe.checkModules не задан в профиле — проба после деплоя не выполнялась'
        return
    }
    $log = Join-Path $script:RunDir 'probe-checkmodules.log'
    $probeArgs = New-Object System.Collections.ArrayList
    [void]$probeArgs.Add('DESIGNER')
    foreach ($a in (Get-TargetArguments $Target $Credentials.path)) { [void]$probeArgs.Add($a) }
    Add-Credentials $probeArgs $Credentials
    [void]$probeArgs.Add('/DisableStartupDialogs')
    [void]$probeArgs.Add('/CheckModules')
    foreach ($ctx in @($script:ProfileData.probe.checkModules)) { [void]$probeArgs.Add('-' + [string]$ctx) }
    if ($script:ProfileData.extension -and $script:ProfileData.extension.name) {
        [void]$probeArgs.Add('-Extension'); [void]$probeArgs.Add((Quote-IfNeeded ([string]$script:ProfileData.extension.name)))
    }
    [void]$probeArgs.Add('/Out'); [void]$probeArgs.Add(('"' + $log + '"'))
    $resultPath = Join-Path $script:RunDir 'probe-checkmodules.result'
    if (Test-Path -LiteralPath $resultPath) { Remove-Item -LiteralPath $resultPath -Force }
    Add-DumpResult $probeArgs $resultPath
    $guard = Invoke-Guarded1C -FilePath $Platform.FullName -ArgumentList ([string[]]$probeArgs) -Label 'probe/checkmodules' -LogPath $GuardLog
    [void]$script:Artifacts.Add($log)
    $contexts = (@($script:ProfileData.probe.checkModules) -join ', ')
    if ($guard.Killed) { Add-Step 'deploy.probe' 'error' "Сторож снял /CheckModules: $($guard.Reason)"; $script:ExitCode = 5; return }
    $dump = Read-DumpResult $resultPath
    $dumpText = if ($null -eq $dump) { 'не записан' } else { [string]$dump }

    # Зрелый проект почти всегда несёт исторические ошибки модулей. Гейт — только
    # НОВЫЕ относительно baseline (та же политика, что у analyze). Ошибка — строка
    # вида {Модуль(стр,кол)}: текст; номера строк и колонок из ключа убираются,
    # иначе любая правка выше по модулю "создаёт" новую ошибку.
    $found = @()
    if (Test-Path -LiteralPath $log) {
        $found = @([IO.File]::ReadAllLines($log, [Text.Encoding]::UTF8) |
            Where-Object { $_ -match '^\{[^}]+\}:' } |
            ForEach-Object { ($_ -replace '\(\d+,\d+\)', '').Trim() } | Sort-Object -Unique)
    }
    # Чисто — только когда сходятся все три сигнала: код выхода, /DumpResult и лог.
    # Код 0 сам по себе не вердикт: провал проверки платформа отдаёт и с нулём.
    if ($guard.ExitCode -eq 0 -and $dump -eq 0 -and $found.Count -eq 0) { Add-Step 'deploy.probe' 'ok' "/CheckModules чист по контекстам: $contexts"; return }
    if ($found.Count -eq 0) { Add-Step 'deploy.probe' 'error' "/CheckModules: код $($guard.ExitCode), /DumpResult $dumpText, ошибок в логе не разобрано — смотрите $log"; $script:ExitCode = 5; return }
    $baselineRel = [string]$script:ProfileData.probe.baseline
    if (-not $baselineRel) {
        Add-Step 'deploy.probe' 'error' "/CheckModules: $($found.Count) ошибок ($contexts). Baseline не задан (probe.baseline) — гейт по абсолютному нулю. Лог: $log"
        $script:ExitCode = 5; return
    }
    $baselinePath = Resolve-ProjectPath $baselineRel $script:ProjectRoot
    if (-not (Test-Path -LiteralPath $baselinePath)) {
        [IO.File]::WriteAllLines($baselinePath, [string[]]$found, (New-Object Text.UTF8Encoding($true)))
        Add-Step 'deploy.probe' 'warning' "Baseline создан: $($found.Count) исторических ошибок записаны в $baselinePath. Закоммитьте его; следующие деплои гейтятся только по новым."
        [void]$script:Warnings.Add('probe baseline создан этим прогоном')
        return
    }
    $known = @([IO.File]::ReadAllLines($baselinePath, [Text.Encoding]::UTF8))
    $new = @($found | Where-Object { $known -notcontains $_ })
    $gone = @($known | Where-Object { $_ -and ($found -notcontains $_) }).Count
    if ($new.Count -gt 0) {
        $newLog = Join-Path $script:RunDir 'probe-new-errors.txt'
        [IO.File]::WriteAllLines($newLog, [string[]]$new, (New-Object Text.UTF8Encoding($true)))
        [void]$script:Artifacts.Add($newLog)
        Add-Step 'deploy.probe' 'error' "/CheckModules: $($new.Count) НОВЫХ ошибок относительно baseline (всего $($found.Count), ушло $gone). Новые: $newLog"
        $script:ExitCode = 5
    } else {
        Add-Step 'deploy.probe' 'ok' "/CheckModules: новых ошибок нет (исторических $($found.Count), ушло $gone) по контекстам: $contexts"
    }
}

function Get-ServeEndpoint {
    <# Адрес и порт ibsrv из профиля (serve.address / serve.port), по умолчанию
       127.0.0.1:18085. Url — без завершающего слеша. #>
    $address = '127.0.0.1'; $port = 18085
    if ($script:ProfileData.serve) {
        if ($script:ProfileData.serve.address) { $address = [string]$script:ProfileData.serve.address }
        if ($script:ProfileData.serve.port) { $port = [int]$script:ProfileData.serve.port }
    }
    return @{ Address = $address; Port = $port; Url = "http://${address}:$port" }
}

function Write-IbsrvPublication {
    <# Файл --config для ibsrv: публикация HTTP-сервисов основной конфигурации и
       расширений по умолчанию плюс явный список serve.httpServices профиля
       ([{ name, root }]) — сервисы, которые должны отвечать по заданному корню. #>
    param([string]$Path)
    $lines = New-Object System.Collections.ArrayList
    [void]$lines.Add('http:')
    [void]$lines.Add('  - base: /')
    [void]$lines.Add('    http-services:')
    [void]$lines.Add('      publish-by-default: true')
    [void]$lines.Add('      publish-extensions-by-default: true')
    $services = @()
    if ($script:ProfileData.serve -and $script:ProfileData.serve.httpServices) { $services = @($script:ProfileData.serve.httpServices) }
    if ($services.Count -gt 0) {
        [void]$lines.Add('      service:')
        foreach ($s in $services) {
            [void]$lines.Add('        - name: ' + [string]$s.name)
            [void]$lines.Add('          root: ' + [string]$s.root)
            [void]$lines.Add('          publish: true')
        }
    }
    [IO.File]::WriteAllText($Path, (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
}

function Invoke-Serve {
    <# Поднять ibsrv над локальной файловой ИБ: веб-клиент и HTTP-сервисы на
       127.0.0.1:<порт>. Только файловая база — серверная обслуживается кластером. #>
    $target = $script:ProfileData.testTarget
    if (-not $target -or $target.kind -ne 'file') { throw 'serve работает только с файловой тестовой ИБ (testTarget.kind = file).' }
    if ($target.environment -eq 'production') { throw 'serve в production запрещён политикой agent-1c.' }
    $platform = Get-Platform $script:ProfileData
    $ibsrv = Get-PlatformBinTool $platform 'ibsrv.exe'
    $ibcmd = Get-PlatformBinTool $platform 'ibcmd.exe'
    if (-not $ibsrv) { throw "В сборке $($platform.Directory.Parent.Name) нет ibsrv.exe (нужен компонент сервера)." }
    $credentials = Resolve-TargetCredentials $target
    $dbPath = $credentials.path
    $dataDir = Get-IbsrvDataDir $target $dbPath
    $endpoint = Get-ServeEndpoint
    $address = $endpoint.Address; $port = $endpoint.Port

    $already = Stop-ServedIbsrv $dbPath $ibcmd $credentials
    if ($already -gt 0) { Add-Step 'serve.restart' 'ok' "Остановлен прежний ibsrv этой базы: $already" }

    # Веб-публикация той же файловой базы (служба из suspendServices) и ibsrv вместе
    # базу не держат. Службы гасятся на всё время работы ibsrv; список погашенных
    # запоминается в его каталоге данных, и stop поднимает их обратно.
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    $suspendedFile = Join-Path $dataDir 'suspended-services.txt'
    # Прежний serve мог погасить службы и не быть остановлен штатно - список не терять.
    $suspended = @(Read-ServiceList $suspendedFile) + @(Suspend-TargetServices)
    Write-ServiceList $suspendedFile $suspended

    # Файл публикации: без него ibsrv отдаёт только HTTP-сервисы основной
    # конфигурации, а на сервис расширения отвечает 503 «sessionId != kUUIDNull».
    # Лежит в каталоге данных ibsrv — это его состояние, живёт вместе с ним.
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    $publication = Join-Path $dataDir 'publication.yml'
    Write-IbsrvPublication $publication
    Add-Step 'serve.publication' 'ok' "Публикация HTTP-сервисов (в т.ч. расширений): $publication"

    # БЕЗ -RedirectStandard*: с перенаправлением Start-Process создаёт процесс с
    # наследованием дескрипторов, ibsrv уносит пайп вызывающего шелла, и тот
    # висит, пока сервер жив (живой случай: агентский инструмент не вернулся).
    # Без перенаправления запуск идёт через ShellExecute — дескрипторы не
    # наследуются. Журнал сервера живёт в его каталоге данных.
    # Регламентные задания по умолчанию запрещены (serve.scheduleJobs = deny). ibsrv,
    # в отличие от файловой базы под веб-сервером, планирует их сам: на копии рабочей
    # базы это внешние вызовы (обмены, загрузки из интернета) и конфликты блокировок
    # с тестом. Живой случай: задание ЭДО держало блокировку, типовой обработчик
    # записи контрагента гасил конфликт ОтменитьТранзакцию, и запись молча
    # откатывалась без исключения.
    $scheduleJobs = 'deny'
    if ($script:ProfileData.serve -and $script:ProfileData.serve.scheduleJobs) { $scheduleJobs = [string]$script:ProfileData.serve.scheduleJobs }
    if ($scheduleJobs -notin @('allow', 'deny')) { throw "serve.scheduleJobs: допустимо allow или deny, задано «$scheduleJobs»." }
    $srvArgs = @(('--db-path="' + $dbPath + '"'), ('--data="' + $dataDir + '"'), "--address=$address", "--port=$port", ('--config="' + $publication + '"'), "--schedule-jobs=$scheduleJobs")
    $proc = Start-Process -FilePath $ibsrv -ArgumentList $srvArgs -WindowStyle Hidden -PassThru

    $url = "http://${address}:$port/"
    $ready = $false
    # Срок по часам, а не по числу попыток: запрос к молчащему серверу сам ждёт
    # до 3 с, и 60 попыток растягивались на четыре минуты.
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 1
        if ($proc.HasExited) { break }
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 -MaximumRedirection 0 -ErrorAction Stop
            if ($resp.StatusCode -lt 500) { $ready = $true; break }
        } catch {
            $code = 0
            try { $code = [int]$_.Exception.Response.StatusCode } catch { }
            if ($code -ge 300 -and $code -lt 500) { $ready = $true; break }
        }
    }
    if (-not $ready) {
        if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
        Resume-ServeSuspendedServices $dataDir
        throw "ibsrv не ответил на $url за 60 с (порт занят? другой ibsrv держит каталог данных ${dataDir}? клиент ещё держит файл базы?)."
    }
    $state = [ordered]@{ pid = $proc.Id; url = $url; dbPath = $dbPath; dataDir = $dataDir; build = $platform.Directory.Parent.Name }
    $state | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:RunDir 'ibsrv.state.json') -Encoding UTF8
    Add-Step 'serve' 'ok' "ibsrv PID $($proc.Id) обслуживает $dbPath на $url (веб-клиент: ${url}ru_RU/, HTTP-сервисы: ${url}hs/<rootUrl>/). Пока он работает, файловую базу не открыть ничем другим: deploy/unit остановят его сами."
}

function Invoke-Stop {
    $target = $script:ProfileData.testTarget
    if (-not $target -or $target.kind -ne 'file') { Add-Step 'stop' 'skipped' 'Нет файловой тестовой ИБ'; return }
    $platform = Get-Platform $script:ProfileData
    $credentials = Resolve-TargetCredentials $target
    $n = Stop-ServedIbsrv $credentials.path (Get-PlatformBinTool $platform 'ibcmd.exe') $credentials
    Add-Step 'stop' 'ok' "Остановлено процессов ibsrv этой базы: $n"
    Resume-ServeSuspendedServices (Get-IbsrvDataDir $target $credentials.path)
}

function Resume-ServeSuspendedServices {
    <# Поднять службы, которые погасил serve (список в каталоге данных ibsrv), и
       очистить список. Службы, поднятые кем-то раньше, Start-Service не трогает. #>
    param([string]$DataDir)
    $file = Join-Path $DataDir 'suspended-services.txt'
    if (-not (Test-Path -LiteralPath $file)) { return }
    Resume-TargetServices @(Read-ServiceList $file)
    Write-ServiceList $file @()
}

# Список имён служб в файле - строками по одной, без JSON: ConvertTo-Json в
# Windows PowerShell 5.1 заворачивает вложенный массив в {value, Count}.
function Read-ServiceList {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    return @(Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Select-Object -Unique)
}

function Write-ServiceList {
    param([string]$Path, $Names)
    $list = @(@($Names) | Where-Object { $_ } | ForEach-Object { [string]$_ } | Select-Object -Unique)
    [IO.File]::WriteAllLines($Path, [string[]]$list, (New-Object System.Text.UTF8Encoding($false)))
}

function Invoke-Unit {
    <# Юнит-контур без интерфейса: 1cv8 ENTERPRISE /C "<launchParameter>" →
       отчёт JUnit. Плейсхолдер {report} в launchParameter — путь отчёта прогона.
       Коды: 0 зелёный, 1 есть провалы, 2 отчёта нет (движок не стартовал). #>
    $target = $script:ProfileData.testTarget
    if (-not $target -or $target.kind -eq 'none') { Add-Step 'unit' 'planned' 'Тестовая ИБ не настроена'; return }
    if ($target.environment -eq 'production') { throw 'Тесты в production запрещены политикой agent-1c.' }
    if (-not $script:ProfileData.unit -or -not $script:ProfileData.unit.launchParameter) {
        Add-Step 'unit' 'unavailable' 'В профиле нет unit.launchParameter — юнит-контур не настроен'; $script:ExitCode = 3; return
    }
    $platform = Get-Platform $script:ProfileData
    if (-not $platform) { throw '1cv8.exe не найден.' }
    $credentials = Resolve-TargetCredentials $target
    $report = Join-Path $script:RunDir 'junit.xml'
    $launch = ([string]$script:ProfileData.unit.launchParameter).Replace('{report}', $report)
    $outLog = Join-Path $script:RunDir 'unit-out.log'

    $runArgs = New-Object System.Collections.ArrayList
    [void]$runArgs.Add('ENTERPRISE')
    foreach ($a in (Get-TargetArguments $target $credentials.path)) { [void]$runArgs.Add($a) }
    Add-Credentials $runArgs $credentials
    [void]$runArgs.Add('/C'); [void]$runArgs.Add(('"' + $launch + '"'))
    [void]$runArgs.Add('/DisableStartupMessages'); [void]$runArgs.Add('/DisableStartupDialogs')
    foreach ($extra in @($script:ProfileData.unit.extraArgs)) { if ($extra) { [void]$runArgs.Add([string]$extra) } }
    [void]$runArgs.Add('/Out'); [void]$runArgs.Add(('"' + $outLog + '"'))
    Add-Step 'unit.command' 'planned' (Format-DeployCommandLine $platform.FullName $runArgs $credentials.password)

    $guardLog = Join-Path $script:RunDir 'guard.log'
    $baseId = Get-1CBaseIdentity $target $credentials.path
    $lock = $null
    if ($baseId) { $lock = Enter-1CBaseLock -Target $baseId -LogPath $guardLog }
    $reserve = $false
    try {
        if ($target.kind -eq 'file') {
            $n = Stop-ServedIbsrv $credentials.path (Get-PlatformBinTool $platform 'ibcmd.exe') $credentials
            if ($n -gt 0) { $reserve = $true; Add-Step 'unit.ibsrv' 'ok' "Остановлен ibsrv этой базы ($n) на время прогона: пока он работает, ENTERPRISE базу не откроет" }
            Resume-ServeSuspendedServices (Get-IbsrvDataDir $target $credentials.path)
        }
        $before = @(Get-Process -Name 1cv8 -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
        $timeout = 30
        if ($script:ProfileData.unit.timeoutMinutes) { $timeout = [int]$script:ProfileData.unit.timeoutMinutes }
        $guard = Invoke-Guarded1C -FilePath $platform.FullName -ArgumentList ([string[]]$runArgs) -Label 'unit/enterprise' -LogPath $guardLog -TimeoutMinutes $timeout
        # ENTERPRISE может отцепить дочерний процесс и выйти раньше, чем тесты
        # допишут отчёт: ждём новые 1cv8, появившиеся после старта.
        $deadline = (Get-Date).AddMinutes($timeout)
        while ((Get-Date) -lt $deadline) {
            $fresh = @(Get-Process -Name 1cv8 -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id })
            if ($fresh.Count -eq 0) { break }
            Start-Sleep -Seconds 2
        }
    }
    finally {
        Exit-1CBaseLock $lock
        [void]$script:Artifacts.Add($guardLog)
        [void]$script:Artifacts.Add($outLog)
        if ($reserve) {
            try { Invoke-Serve } catch { Add-Step 'unit.ibsrv' 'error' "ibsrv не поднялся после прогона: $($_.Exception.Message)"; $script:ExitCode = 1 }
        }
    }
    if ($guard.Killed) { Add-Step 'unit' 'error' "Сторож снял прогон: $($guard.Reason). См. $guardLog"; $script:ExitCode = 1; return }
    if (-not (Test-Path -LiteralPath $report)) {
        Add-Step 'unit' 'error' "Отчёта нет: движок тестов не стартовал или упал до записи (обработчик параметра запуска в тестовом расширении?). Лог: $outLog; журнал регистрации — ibcmd eventlog export."
        $script:ExitCode = 2; return
    }
    [void]$script:Artifacts.Add($report)
    [xml]$xml = [IO.File]::ReadAllText($report, [Text.Encoding]::UTF8)
    $tests = 0; $failed = 0
    foreach ($suite in @($xml.SelectNodes('//testsuite'))) {
        $tests += [int]$suite.GetAttribute('tests')
        $f = $suite.GetAttribute('failures'); if ($f) { $failed += [int]$f }
        $e = $suite.GetAttribute('errors'); if ($e) { $failed += [int]$e }
    }
    if ($tests -eq 0) { Add-Step 'unit' 'error' "Отчёт пуст (0 тестов): набор не обнаружен — это не зелёный прогон. $report"; $script:ExitCode = 2; return }
    if ($failed -gt 0) {
        $names = @($xml.SelectNodes('//testcase[failure or error]') | ForEach-Object { $_.GetAttribute('name') }) -join ', '
        Add-Step 'unit' 'error' "Провалено $failed из $tests`: $names. Отчёт: $report"
        $script:ExitCode = 1
    } else {
        Add-Step 'unit' 'ok' "Все $tests тестов прошли. Отчёт: $report"
    }
}

function Invoke-Deploy {
    $target = $script:ProfileData.testTarget
    if (-not $target -or $target.kind -eq 'none') { Add-Step 'deploy' 'planned' 'Тестовая ИБ не настроена; мутации отсутствуют'; return }
    if ($target.environment -eq 'production') { throw 'Deploy в production запрещён политикой agent-1c.' }
    $platform = Get-Platform $script:ProfileData
    if (-not $platform) { throw '1cv8.exe не найден.' }
    $source = Resolve-ProjectPath $script:ProfileData.sourceDir $script:ProjectRoot

    $extensionName = $null
    if ($script:ProfileData.extension -and $script:ProfileData.extension.name) { $extensionName = [string]$script:ProfileData.extension.name }

    $credentials = Resolve-TargetCredentials $target
    if ($script:WorkflowProtocol) {
        if ($target.kind -ne $WorkflowTargetKind -or $target.environment -notin @('test', 'development')) { throw 'WORKFLOW_TARGET_NOT_ALLOWED' }
        Assert-WorkflowPlatformTool $platform.FullName
        if ($WorkflowTargetKind -eq 'file') {
            if (-not $credentials.path -or -not [IO.Path]::IsPathRooted($credentials.path)) { throw 'WORKFLOW_TARGET_PATH_REQUIRED' }
            if (-not [string]::Equals([IO.Path]::GetFullPath($credentials.path), [IO.Path]::GetFullPath($WorkflowTargetPath), [StringComparison]::OrdinalIgnoreCase)) { throw 'WORKFLOW_TARGET_PATH_MISMATCH' }
            Assert-WorkflowPathNoReparse $WorkflowTargetPath
        } else {
            $identity = Get-WorkflowServerIdentity ([string]$target.server) ([string]$target.ref)
            if ($identity.server -cne $WorkflowTargetServer -or $identity.ref -cne $WorkflowTargetRef) { throw 'WORKFLOW_SERVER_TARGET_MISMATCH' }
            # The exact canonical endpoint/reference bound to the resource is also
            # used by DESIGNER; aliases/whitespace cannot diverge from the plan.
            $target.server = $identity.server
            $target.ref = $identity.ref
        }
        Assert-WorkflowPathNoReparse $source
        $currentProfileHash = (Get-FileHash -LiteralPath $profilePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($currentProfileHash -ne $WorkflowProfileDigest) { throw 'WORKFLOW_PROFILE_CHANGED' }
    }
    $engine = Get-DeployEngine $target $platform
    $planMessage = "Загрузить XML из $source и обновить тестовую ИБ ($($target.kind)); движок: $engine, сборка $($platform.Directory.Parent.Name)"
    if ($extensionName) { $planMessage += "; расширение $extensionName" }
    Add-Step 'deploy.plan' 'ok' $planMessage

    # Гейт кодировки — до первого запуска, чтобы не оставить базу в промежуточном
    # состоянии. Для конфигуратора отказ: /LoadConfigFromFiles на .bsl без сигнатуры
    # падает молча и уносит загрузку всего расширения. Для ibcmd то же поведение
    # не подтверждено — там предупреждение.
    $withoutBom = @(Get-BslFilesWithoutBom $source)
    if ($withoutBom.Count -gt 0) {
        $bomList = "модули .bsl без UTF-8 BOM ($($withoutBom.Count)): " + (Format-BomFileList $withoutBom)
        if ($engine -eq 'ibcmd') {
            Add-Step 'deploy.encoding' 'warning' ("В исходниках $bomList. Конфигуратор такую загрузку роняет без внятной ошибки; для ibcmd не проверено.")
        }
        else {
            Add-Step 'deploy.encoding' 'error' ("Деплой остановлен: $bomList. Платформа не прочитает такой файл и уронит загрузку без внятной ошибки.")
            $script:ExitCode = 1
            return
        }
    }

    $runs = New-Object System.Collections.ArrayList
    $exe = $platform.FullName
    if ($engine -eq 'ibcmd') {
        $exe = Get-PlatformBinTool $platform 'ibcmd.exe'
        if (-not (Test-Path -LiteralPath (Join-Path $credentials.path '1Cv8.1CD'))) {
            Add-Step 'deploy.create' 'planned' "ИБ по пути $($credentials.path) нет — будет создана (ibcmd infobase create)"
        }
        $dataDir = Get-ServerDataDir $target $credentials.path
        $baseArgs = Get-IbcmdBaseArgs $credentials.path $dataDir $credentials
        foreach ($r in (Get-IbcmdDeployRuns $source $extensionName $baseArgs)) { [void]$runs.Add($r) }
    }
    else {
        # Общая часть командной строки DESIGNER — переиспользуется каждым запуском.
        $common = New-Object System.Collections.ArrayList
        [void]$common.Add('DESIGNER')
        foreach ($arg in (Get-TargetArguments $target $credentials.path)) { [void]$common.Add($arg) }
        Add-Credentials $common $credentials
        [void]$common.Add('/DisableStartupDialogs')

        if ($extensionName) {
            # Платформа (проверено на 8.3.27) отвергает /LoadConfigFromFiles -Extension и
            # /UpdateDBCfg -Extension в ОДНОМ запуске DESIGNER. Для расширения деплой
            # выполняется двумя последовательными запусками с теми же флагами; для основной
            # конфигурации совмещённый запуск работает и остаётся одним.
            $loadLog = Join-Path $script:RunDir 'deploy-load.log'
            $load = New-Object System.Collections.ArrayList
            [void]$load.AddRange($common)
            [void]$load.Add('/LoadConfigFromFiles'); [void]$load.Add(('"' + $source + '"'))
            [void]$load.Add('-Extension'); [void]$load.Add((Quote-IfNeeded $extensionName))
            [void]$load.Add('-Format'); [void]$load.Add('Hierarchical')
            [void]$load.Add('/Out'); [void]$load.Add(('"' + $loadLog + '"'))
            $loadResult = Join-Path $script:RunDir 'deploy-load.result'
            Add-DumpResult $load $loadResult
            [void]$runs.Add(@{ name = 'load'; args = $load; log = $loadLog; result = $loadResult })

            $updateLog = Join-Path $script:RunDir 'deploy-update.log'
            $update = New-Object System.Collections.ArrayList
            [void]$update.AddRange($common)
            [void]$update.Add('/UpdateDBCfg'); [void]$update.Add('-Extension'); [void]$update.Add((Quote-IfNeeded $extensionName))
            [void]$update.Add('/Out'); [void]$update.Add(('"' + $updateLog + '"'))
            $updateResult = Join-Path $script:RunDir 'deploy-update.result'
            Add-DumpResult $update $updateResult
            [void]$runs.Add(@{ name = 'update'; args = $update; log = $updateLog; result = $updateResult })
        }
        else {
            $log = Join-Path $script:RunDir 'deploy.log'
            $single = New-Object System.Collections.ArrayList
            [void]$single.AddRange($common)
            [void]$single.Add('/LoadConfigFromFiles'); [void]$single.Add(('"' + $source + '"'))
            [void]$single.Add('/UpdateDBCfg')
            [void]$single.Add('/Out'); [void]$single.Add(('"' + $log + '"'))
            $singleResult = Join-Path $script:RunDir 'deploy.result'
            Add-DumpResult $single $singleResult
            [void]$runs.Add(@{ name = 'load+update'; args = $single; log = $log; result = $singleResult })
        }
    }

    foreach ($run in $runs) {
        $redactedCommand = Format-DeployCommandLine $exe $run.args $credentials.password
        Add-Step "deploy.command.$($run.name)" 'planned' $redactedCommand
    }

    if (-not $Apply) { Add-Step 'deploy.apply' 'dry-run' 'Для применения требуется -Apply'; return }

    # Лок держится на ВСЕ запуски: между загрузкой и применением конфигурация в
    # базе уже изменена, но не применена — чужой деплой в этот промежуток ломает обе стороны.
    $guardLog = Join-Path $script:RunDir 'guard.log'
    $baseId = Get-1CBaseIdentity $target $credentials.path
    $lock = $null
    if ($baseId) { $lock = Enter-1CBaseLock -Target $baseId -LogPath $guardLog }
    $suspended = @()
    $reserve = $false
    try {
        # Even service suspension may change target availability. A killed
        # process cannot subsequently prove that no target changes occurred.
        if ($script:WorkflowProtocol) { $script:WorkflowMutationState = 'unknown' }
        # Сеансы держат ibsrv этой базы и службы из профиля — их гасит сам деплой.
        # ibsrv, который работал до деплоя, поднимается после него: он и есть
        # постоянный сервер базы (веб-клиент, HTTP-сервисы).
        if ($target.kind -eq 'file') {
            $n = Stop-ServedIbsrv $credentials.path (Get-PlatformBinTool $platform 'ibcmd.exe') $credentials
            if ($n -gt 0) { $reserve = $true; Add-Step 'deploy.ibsrv' 'ok' "Остановлен ibsrv этой базы ($n) на время деплоя" }
            Resume-ServeSuspendedServices (Get-IbsrvDataDir $target $credentials.path)
        }
        $suspended = Suspend-TargetServices
        if ($engine -eq 'ibcmd' -and -not (Test-Path -LiteralPath (Join-Path $credentials.path '1Cv8.1CD'))) {
            New-Item -ItemType Directory -Path $credentials.path -Force | Out-Null
            $createRun = @{ name = 'create'; args = (@('infobase', 'create') + (Get-IbcmdBaseArgs $credentials.path (Get-ServerDataDir $target $credentials.path) @{})); stdout = (Join-Path $script:RunDir 'ibcmd-create.log'); stderr = (Join-Path $script:RunDir 'ibcmd-create.err.log') }
            Invoke-GuardedRun $exe $createRun $guardLog 'deploy.apply'
        }
        foreach ($run in $runs) { Invoke-GuardedRun $exe $run $guardLog 'deploy.apply' }
        if ($script:WorkflowProtocol) { $script:WorkflowMutationState = 'applied' }
        Invoke-PostDeployProbe $platform $target $credentials $guardLog
    }
    finally {
        Resume-TargetServices $suspended
        Exit-1CBaseLock $lock
        [void]$script:Artifacts.Add($guardLog)
        if ($reserve) {
            try { Invoke-Serve } catch { Add-Step 'deploy.ibsrv' 'error' "ibsrv не поднялся после деплоя: $($_.Exception.Message)"; $script:ExitCode = 1 }
        }
    }
    Add-Step 'deploy.apply' 'ok' ("Тестовая ИБ обновлена ($engine); запусков: " + $runs.Count)
}

function Get-OneScriptBin {
    return Join-Path $script:ToolRoot 'onescript\bin'
}

function Get-VanessaEpfPath {
    # Приоритет: свежий vanessa-automation (GitHub-релиз). bddRunner из opm-пакета add (6.8.0, 2021)
    # несовместим с платформой 8.3.27 — падает на разборе версии режима совместимости при загрузке плагинов.
    $vanessaRoot = Join-Path $script:ToolRoot 'vanessa'
    if (Test-Path -LiteralPath $vanessaRoot -PathType Container) {
        $found = Get-ChildItem -LiteralPath $vanessaRoot -Directory |
            Sort-Object Name -Descending |
            ForEach-Object { Get-Item -LiteralPath (Join-Path $_.FullName 'vanessa-automation-single.epf') -ErrorAction SilentlyContinue } |
            Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    $fallback = Join-Path $script:ToolRoot 'onescript\lib\add\bddRunner.epf'
    if (Test-Path -LiteralPath $fallback -PathType Leaf) { return $fallback }
    return $null
}

function ConvertTo-JsonScalar {
    param($Value)
    $json = ConvertTo-Json -InputObject ([string]$Value) -Compress
    return $json.Substring(1, $json.Length - 2)
}

function Expand-TemplateToFile {
    param([string]$TemplatePath, [hashtable]$Replacements, [string]$OutputPath)
    $text = Get-Content -LiteralPath $TemplatePath -Raw -Encoding UTF8
    foreach ($key in $Replacements.Keys) {
        $text = $text.Replace('{{' + $key + '}}', (ConvertTo-JsonScalar $Replacements[$key]))
    }
    # UTF-8 строго С BOM: VAParams читает 1С — ЧтениеТекста определяет кодировку по BOM,
    # без BOM на ru-Windows файл читается как windows-1251 и JSON с кириллическими ключами не парсится
    # (симптом: модалка «Не удалось прочитать файл настроек JSON»).
    $encoding = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($OutputPath, $text, $encoding)
}

function Publish-FeatureSet {
    <# Подстановка {{ТОКЕН}} в тексте фич — те же плейсхолдеры, что у
       Expand-TemplateToFile, но для .feature, а не JSON (например, путь к .env из
       testTarget.envFile, чтобы не хардкодить его в сценариях). Каталог фич
       копируется в каталог прогона целиком, переписываются только файлы с токенами;
       BOM сохраняется как в исходнике. Возвращает каталог, из которого запускать:
       без токенов в фичах — исходный, без копирования. #>
    param([string]$SourceDir, [string]$DestDir, [hashtable]$Replacements)
    $withTokens = @(Get-ChildItem -LiteralPath $SourceDir -Recurse -Filter '*.feature' -File | Where-Object {
        $text = [System.IO.File]::ReadAllText($_.FullName, [Text.Encoding]::UTF8)
        @($Replacements.Keys | Where-Object { $text.Contains('{{' + $_ + '}}') }).Count -gt 0
    })
    if ($withTokens.Count -eq 0) { return $SourceDir }

    if (Test-Path -LiteralPath $DestDir) { Remove-Item -LiteralPath $DestDir -Recurse -Force }
    Copy-Item -LiteralPath $SourceDir -Destination $DestDir -Recurse -Force
    $root = $SourceDir.TrimEnd('\', '/')
    foreach ($file in $withTokens) {
        $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
        $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
        $text = [System.IO.File]::ReadAllText($file.FullName, [Text.Encoding]::UTF8)
        foreach ($key in $Replacements.Keys) {
            $text = $text.Replace('{{' + $key + '}}', [string]$Replacements[$key])
        }
        $staged = Join-Path $DestDir $file.FullName.Substring($root.Length).TrimStart('\', '/')
        [System.IO.File]::WriteAllText($staged, $text, (New-Object System.Text.UTF8Encoding($hasBom)))
    }
    Add-Step 'test.features' 'ok' "Токены подставлены в фичах: $($withTokens.Count); прогон из $DestDir"
    return $DestDir
}

function Remove-SecretFromFiles {
    param([string[]]$Files, [string]$Secret)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    foreach ($file in $Files) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { continue }
        $content = Get-Content -LiteralPath $file -Raw -ErrorAction SilentlyContinue
        if (-not $content) { continue }
        $masked = $content
        if (-not [string]::IsNullOrEmpty($Secret)) { $masked = $masked.Replace($Secret, '<hidden>') }
        # Пароль тест-клиента передаётся аргументом /P с кавычками (ДопПараметры VAParams) — маскируем и его след  # airules:allow creds-p-flag (masking pattern, not a secret)
        $masked = [regex]::Replace($masked, '/P"[^"]*"', '/P"<hidden>"')  # airules:allow creds-p-flag (masking pattern, not a secret)
        if ($masked -ne $content) {
            [System.IO.File]::WriteAllText($file, $masked, $encoding)
        }
    }
}

function Invoke-TestHidden {
    <# test -Hidden: тот же прогон, перезапуском себя на невидимом рабочем столе. Все
       дочерние процессы (vrunner, тест-менеджер, тест-клиент) наследуют этот стол.
       Внутренний прогон пишет свой каталог *-test; отсюда берутся его шаги и код. #>
    . (Join-Path $PSScriptRoot 'lib\hidden-desktop.ps1')
    $resultRoot = Split-Path -Parent $script:RunDir
    $before = @(Get-ChildItem -LiteralPath $resultRoot -Directory -Filter '*-test' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    $inner = @('powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        ('"' + $PSCommandPath + '"'), 'test', '-Profile', ('"' + ([IO.Path]::GetFullPath($Profile)) + '"'))
    if ($Connection) { $inner += @('-Connection', $Connection) }
    $timeout = [int](Get-1CGuardSetting 'AGENT1C_TEST_TIMEOUT_MIN' 45) + 10
    Add-Step 'test.hidden' 'ok' "Прогон на невидимом рабочем столе (таймаут $timeout мин)"
    $code = Invoke-OnHiddenDesktop -CommandLine ($inner -join ' ') -WorkingDirectory $script:ProjectRoot -TimeoutMinutes $timeout
    $innerDir = Get-ChildItem -LiteralPath $resultRoot -Directory -Filter '*-test' -ErrorAction SilentlyContinue |
        Where-Object { $before -notcontains $_.FullName -and $_.FullName -ne $script:RunDir } |
        Sort-Object Name | Select-Object -Last 1
    if ($code -eq -1) { Add-Step 'test.hidden' 'error' "Прогон снят по таймауту $timeout мин"; $script:ExitCode = 1 }
    if (-not $innerDir) { Add-Step 'test.hidden' 'error' "Внутренний прогон не оставил каталога (код $code)"; $script:ExitCode = 1; return }
    [void]$script:Artifacts.Add($innerDir.FullName)
    $innerResult = Join-Path $innerDir.FullName 'result.json'
    if (Test-Path -LiteralPath $innerResult) {
        $r = Get-Content -LiteralPath $innerResult -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($s in @($r.steps)) { Add-Step ('hidden.' + $s.name) $s.status $s.message }
    }
    if ($code -ne 0 -and $code -ne -1) { $script:ExitCode = $code }
    Add-Step 'test.hidden' $(if ($code -eq 0) { 'ok' } else { 'error' }) "Внутренний прогон: код $code, каталог $($innerDir.FullName)"
}

function Invoke-Test {
    $vrunner = Get-VrunnerPath
    if (-not $vrunner) { Add-Step 'test.vanessa' 'unavailable' 'Vanessa Runner не установлен или не добавлен в PATH'; $script:ExitCode = 3; return }
    $vanessaEpf = Get-VanessaEpfPath
    if (-not $vanessaEpf) { Add-Step 'test.vanessa' 'unavailable' 'Vanessa-Automation не установлена: положите vanessa-automation-single.epf в %LOCALAPPDATA%\agent-1c\tools\vanessa\<версия>\'; $script:ExitCode = 3; return }

    $target = $script:ProfileData.testTarget
    if (-not $target -or $target.kind -eq 'none') { Add-Step 'test.vanessa' 'planned' 'Тестовая ИБ не настроена; смоук пропущен'; return }
    if ($target.environment -eq 'production') { throw 'Тестирование в production запрещено политикой agent-1c.' }
    if ($target.kind -ne 'file') { throw 'Vanessa-смоук настроен только для файловой ИБ (testTarget.kind = file).' }

    $platform = Get-Platform $script:ProfileData
    if (-not $platform) { throw '1cv8.exe не найден.' }
    $v8version = $platform.Directory.Parent.Name

    $credentials = Resolve-TargetCredentials $target
    if ([string]::IsNullOrWhiteSpace($credentials.path)) { throw 'Путь файловой ИБ не определён (testTarget.path пуст и не найден Path в envFile).' }

    $featuresRel = 'tools/agent-1c/vanessa-suite/features'
    $settingsTemplateRel = 'tools/agent-1c/vanessa-suite/vanessa-settings.template.json'
    $addTemplateRel = 'tools/agent-1c/vanessa-suite/vanessa-add-params.template.json'
    $testClientTimeout = 300
    $ordinaryApp = 0
    if ($script:ProfileData.vanessa) {
        $vanessaCfg = $script:ProfileData.vanessa
        if ($vanessaCfg.featuresDir) { $featuresRel = [string]$vanessaCfg.featuresDir }
        if ($vanessaCfg.settingsTemplate) { $settingsTemplateRel = [string]$vanessaCfg.settingsTemplate }
        if ($vanessaCfg.addParamsTemplate) { $addTemplateRel = [string]$vanessaCfg.addParamsTemplate }
        if ($vanessaCfg.testClientTimeoutSeconds) { $testClientTimeout = [int]$vanessaCfg.testClientTimeoutSeconds }
        if ($null -ne $vanessaCfg.ordinaryApp) { $ordinaryApp = [int]$vanessaCfg.ordinaryApp }
    }

    $featuresDir = Resolve-ProjectPath $featuresRel $script:ProjectRoot
    $settingsTemplate = Resolve-ProjectPath $settingsTemplateRel $script:ProjectRoot
    $addTemplate = Resolve-ProjectPath $addTemplateRel $script:ProjectRoot
    if (-not (Test-Path -LiteralPath $featuresDir -PathType Container)) { throw "Каталог фич не найден: $featuresDir" }
    if (-not (Test-Path -LiteralPath $settingsTemplate -PathType Leaf)) { throw "Шаблон настроек не найден: $settingsTemplate" }
    if (-not (Test-Path -LiteralPath $addTemplate -PathType Leaf)) { throw "Шаблон Vanessa-ADD не найден: $addTemplate" }

    $envFilePath = ''
    if ($target.envFile) { $envFilePath = (Resolve-ProjectPath $target.envFile $script:ProjectRoot) -replace '\\', '/' }
    $featuresDir = Publish-FeatureSet $featuresDir (Join-Path $script:RunDir 'features') @{ ENV_FILE = $envFilePath }

    $outputDir = Join-Path $script:RunDir 'reports'
    New-Item -ItemType Directory -Path (Join-Path $outputDir 'junit') -Force | Out-Null

    # Имена БЕЗ ведущей точки: VA не читает settings-файл с именем, начинающимся с точки
    # (симптом: модалка «Не удалось прочитать файл настроек JSON»).
    $settingsTmp = Join-Path $script:RunDir 'vrunner-settings.tmp.json'
    $addTmp = Join-Path $script:RunDir 'vanessa-add-params.tmp.json'
    $stdout = Join-Path $script:RunDir 'vanessa-stdout.log'
    $stderr = Join-Path $script:RunDir 'vanessa-stderr.log'

    # Библиотечные шаги VA (пакет add: открытие внешнего файла и прочие) подхватываются
    # только через КаталогиБиблиотек временного VAParams. Путь — ТОЛЬКО прямыми слешами:
    # с обратными VA каталог молча не находит и шаги остаются нераспознанными.
    $vaLibrariesDir = Join-Path $script:ToolRoot 'onescript\lib\add\features\libraries'
    if (-not (Test-Path -LiteralPath $vaLibrariesDir -PathType Container)) {
        Add-Step 'test.vanessa.libraries' 'warning' "Каталог библиотечных фич не найден: $vaLibrariesDir; шаги пакета add будут нераспознаны (поставьте пакет через opm)"
    }
    # Подключение: напрямую к файлу (/F) либо через ibsrv (/WS) — второе быстрее
    # на длинном наборе и не держит файл базы клиентом. ibsrv поднимается сам, если
    # не запущен; тест-менеджер и «Этот клиент» VA идут по одному адресу.
    $mode = $Connection
    $reserveTest = $false
    $clientsBefore = Get-1CClientIds
    if (-not $mode -and $script:ProfileData.vanessa -and $script:ProfileData.vanessa.connection) { $mode = [string]$script:ProfileData.vanessa.connection }
    if (-not $mode) { $mode = 'file' }
    if ($mode -eq 'ibsrv') {
        if ((Get-ServedIbsrv $credentials.path).Count -eq 0) { Invoke-Serve }
        $wsUrl = (Get-ServeEndpoint).Url
        $ibConnection = '/WS' + $wsUrl
        $ibFileConnection = 'ws="' + $wsUrl + '";'
    }
    else {
        # /F и работающий ibsrv базу вместе не держат: ibsrv гасится на время прогона
        # и поднимается после него (finally ниже).
        if ((Stop-ServedIbsrv $credentials.path (Get-PlatformBinTool $platform 'ibcmd.exe') $credentials) -gt 0) {
            $reserveTest = $true
            Add-Step 'test.ibsrv' 'ok' 'Остановлен ibsrv этой базы на время прогона по /F'
        }
        $ibConnection = '/F' + ($credentials.path -replace '\\', '/')
        $ibFileConnection = 'File="' + $credentials.path + '";'
    }

    Add-Step 'test.plan' 'ok' "Смоук Vanessa-Automation против $($ibConnection) ($mode) под '$($credentials.user)'; epf: $vanessaEpf; фичи: $featuresDir; тонкий клиент: $([bool]($ordinaryApp -eq 0))"

    $previousPath = $env:PATH
    $hadPwdVar = Test-Path Env:\RUNNER_DBPWD
    $previousPwd = if ($hadPwdVar) { $env:RUNNER_DBPWD } else { $null }
    try {
        Expand-TemplateToFile $settingsTemplate ([ordered]@{
            IB_CONNECTION = $ibConnection
            LOGIN         = $credentials.user
            V8VERSION     = $v8version
        }) $settingsTmp

        # ДанныеКлиентовТестирования: vrunner передаёт /P только тест-МЕНЕДЖЕРУ; профиль
        # «Этот клиент» VA собирает без пароля → интерактивное окно логина → таймаут.
        # Поэтому логин/пароль тест-клиента уходят в ДопПараметры временного VAParams
        # (файл живёт до выхода vrunner, затирается и удаляется в finally).
        Expand-TemplateToFile $addTemplate ([ordered]@{
            V8VERSION          = $v8version
            OUTPUT_DIR         = ($outputDir -replace '\\', '/')
            FEATURES_DIR       = ($featuresDir -replace '\\', '/')
            TESTCLIENT_TIMEOUT = [string]$testClientTimeout
            IB_FILE_CONNECTION = $ibFileConnection
            VA_LIBRARIES_DIR   = ($vaLibrariesDir -replace '\\', '/')
            LOGIN              = [string]$credentials.user
            PASSWORD           = [string]$credentials.password  # airules:allow creds-password (template value from resolved credentials, no literal secret)
        }) $addTmp

        # Под ibsrv у базы свой журнал регистрации и своя строка соединения: сценарии,
        # которые на них опираются, помечены @ТолькоФайл и здесь исключаются. Правка
        # текстом, не через ConvertFrom/To-Json: в Windows PowerShell 5.1 обратная
        # сериализация портит вложенные массивы VAParams. BOM сохраняется (VA без него
        # читает файл как windows-1251).
        if ($mode -eq 'ibsrv') {
            $vaText = [IO.File]::ReadAllText($addTmp, [Text.Encoding]::UTF8)
            $vaPatched = [regex]::Replace($vaText, '"СписокТеговИсключение"\s*:\s*\[\s*\]', '"СписокТеговИсключение": ["ТолькоФайл"]')
            if ($vaPatched -eq $vaText) { Add-Step 'test.tags' 'warning' 'Не удалось исключить тег ТолькоФайл: в шаблоне VAParams нет пустого СписокТеговИсключение' }
            else {
                [IO.File]::WriteAllText($addTmp, $vaPatched, (New-Object System.Text.UTF8Encoding($true)))
                Add-Step 'test.tags' 'ok' 'Под ibsrv исключены сценарии с тегом @ТолькоФайл'
            }
        }

        $env:PATH = (Get-OneScriptBin) + ';' + $env:PATH
        if ($credentials.password) { $env:RUNNER_DBPWD = $credentials.password } else { $env:RUNNER_DBPWD = '' }

        $arguments = New-Object System.Collections.ArrayList
        [void]$arguments.Add('vanessa')
        [void]$arguments.Add('--settings');        [void]$arguments.Add($settingsTmp)
        [void]$arguments.Add('--vanessasettings');  [void]$arguments.Add($addTmp)
        [void]$arguments.Add('--pathvanessa');      [void]$arguments.Add($vanessaEpf)
        [void]$arguments.Add('--path');             [void]$arguments.Add($featuresDir)
        [void]$arguments.Add('--ordinaryapp');      [void]$arguments.Add([string]$ordinaryApp)
        [void]$arguments.Add('--v8version');        [void]$arguments.Add($v8version)
        [void]$arguments.Add('--workspace');        [void]$arguments.Add($script:RunDir)
        [void]$arguments.Add('--additional-keys');  [void]$arguments.Add('DisableFirstRunHelper')

        $displayCommand = (Quote-IfNeeded $vrunner) + ' ' + (($arguments | ForEach-Object { Quote-IfNeeded ([string]$_) }) -join ' ')
        Add-Step 'test.command' 'planned' ($displayCommand + '  [секрет: RUNNER_DBPWD=<hidden> в окружении + /P с кавычками во временном VAParams (затирается в finally)]')

        # Тест тоже держит базу: деплой, влезший в середину прогона Vanessa,
        # меняет конфигурацию под работающими сценариями. Лок — тот же, что у деплоя.
        # Память здесь НЕ сторожим: vrunner лишь ждёт дочерние 1cv8 и всегда
        # выглядит пустым и стоящим; остаётся таймаут (прогон длиннее деплоя).
        $guardLog = Join-Path $script:RunDir 'guard.log'
        $baseId = Get-1CBaseIdentity $target $credentials.path
        $testLock = $null
        if ($baseId) { $testLock = Enter-1CBaseLock -Target $baseId -LogPath $guardLog }
        try {
            $guard = Invoke-Guarded1C -FilePath $vrunner -ArgumentList ([string[]]$arguments) `
                -Label 'test/vrunner' -TimeoutOnly -LogPath $guardLog `
                -TimeoutMinutes ([int](Get-1CGuardSetting 'AGENT1C_TEST_TIMEOUT_MIN' 45)) `
                -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        }
        finally {
            Exit-1CBaseLock $testLock
            [void]$script:Artifacts.Add($guardLog)
        }
        if ($guard.Killed) {
            Add-Step 'test.vanessa' 'error' "Сторож снял прогон: $($guard.Reason). См. $guardLog"
            $script:ExitCode = 1
            return
        }
        $code = $guard.ExitCode

        Remove-SecretFromFiles @($stdout, $stderr, (Join-Path $outputDir 'vanessaonline.txt'), (Join-Path $outputDir 'message.txt')) $credentials.password
        [void]$script:Artifacts.Add($outputDir)
        [void]$script:Artifacts.Add($stdout)

        $statusPath = Join-Path $outputDir 'buildstatus.log'
        $statusText = ''
        if (Test-Path -LiteralPath $statusPath -PathType Leaf) { $statusText = (Get-Content -LiteralPath $statusPath -Raw -ErrorAction SilentlyContinue) }
        if ($statusText) { $statusText = $statusText.Trim() }

        if ($code -eq 0) {
            Add-Step 'test.vanessa' 'ok' "Смоук пройден (exit 0). buildstatus: '$statusText'. Отчёты: $outputDir"
        } else {
            Add-Step 'test.vanessa' 'error' "Смоук завершился с кодом $code. buildstatus: '$statusText'. Логи: $stdout / $stderr; отчёты: $outputDir"
            $script:ExitCode = $code
        }
    } finally {
        if (Test-Path -LiteralPath $settingsTmp -PathType Leaf) { Remove-Item -LiteralPath $settingsTmp -Force -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $addTmp -PathType Leaf) {
            # VAParams содержит пароль тест-клиента — затираем содержимое перед удалением
            try { [System.IO.File]::WriteAllText($addTmp, '{}') } catch {}
            Remove-Item -LiteralPath $addTmp -Force -ErrorAction SilentlyContinue
        }
        $env:PATH = $previousPath
        if ($hadPwdVar) { $env:RUNNER_DBPWD = $previousPwd } else { Remove-Item Env:\RUNNER_DBPWD -ErrorAction SilentlyContinue }
        if ($reserveTest) {
            $left = Wait-New1CClientsExit $clientsBefore 60
            if ($left -gt 0) { Add-Step 'test.ibsrv' 'warning' "Клиенты 1С после прогона не вышли за 60 с ($left) — ibsrv может не открыть базу" }
            try { Invoke-Serve } catch { Add-Step 'test.ibsrv' 'error' "ibsrv не поднялся после прогона: $($_.Exception.Message)"; $script:ExitCode = 1 }
        }
    }
}

try {
    $profilePath = [IO.Path]::GetFullPath($Profile)
    if (-not (Test-Path -LiteralPath $profilePath)) { throw "Профиль не найден: $profilePath" }
    $script:ProjectRoot = Split-Path -Parent $profilePath
    $script:ProfileData = Get-Content -LiteralPath $profilePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($script:ProfileData.schemaVersion -ne 1) { throw 'Неподдерживаемая версия профиля.' }
    $workflowFields = @($WorkflowRunId, $WorkflowStepId, $WorkflowSourceDigest, $WorkflowTargetDigest, $WorkflowProfileDigest, $WorkflowExactBuild)
    if (@(($workflowFields + @($WorkflowTargetPath, $WorkflowTargetServer, $WorkflowTargetRef)) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count -gt 0 -or $WorkflowTargetKind -ne 'file') {
        if ($Command -ne 'deploy' -or @($workflowFields | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count -gt 0) { throw 'WORKFLOW_CONTEXT_INCOMPLETE' }
        if ($WorkflowRunId -notmatch '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$' -or $WorkflowStepId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') { throw 'WORKFLOW_ID_INVALID' }
        foreach ($value in @($WorkflowSourceDigest, $WorkflowTargetDigest, $WorkflowProfileDigest)) { if ($value -notmatch '^[a-f0-9]{64}$') { throw 'WORKFLOW_DIGEST_INVALID' } }
        if ($WorkflowExactBuild -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'WORKFLOW_TARGET_CONTEXT_INVALID' }
        if ($WorkflowTargetKind -eq 'file') {
            if (-not [IO.Path]::IsPathRooted($WorkflowTargetPath) -or $WorkflowTargetServer -or $WorkflowTargetRef) { throw 'WORKFLOW_TARGET_CONTEXT_INVALID' }
        } else {
            if ($WorkflowTargetPath) { throw 'WORKFLOW_TARGET_CONTEXT_INVALID' }
            $identity = Get-WorkflowServerIdentity $WorkflowTargetServer $WorkflowTargetRef
            if ($identity.server -cne $WorkflowTargetServer -or $identity.ref -cne $WorkflowTargetRef) { throw 'WORKFLOW_SERVER_TARGET_INVALID' }
        }
        if ((Get-FileHash -LiteralPath $profilePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $WorkflowProfileDigest) { throw 'WORKFLOW_PROFILE_CHANGED' }
        $script:WorkflowProtocol = $true
    }
    $resultRoot = Resolve-ProjectPath $script:ProfileData.resultDir $script:ProjectRoot
    # test -Hidden пишет в свой каталог *-test-hidden: внутренний прогон (*-test)
    # стартует в ту же секунду и иначе попал бы в тот же каталог.
    $runLabel = if ($Hidden -and $Command -eq 'test') { 'test-hidden' } else { $Command }
    if ($script:WorkflowProtocol) {
        Assert-WorkflowPathNoReparse $resultRoot
        $workflowRoot = Join-Path $resultRoot ('workflow-' + $WorkflowRunId)
        Assert-WorkflowPathNoReparse $workflowRoot
        New-Item -ItemType Directory -Path $workflowRoot -Force | Out-Null
        $freshRunDir = Join-Path $workflowRoot $WorkflowStepId
        # No -Force: reusing an existing evidence directory is an error.
        New-Item -ItemType Directory -Path $freshRunDir -ErrorAction Stop | Out-Null
        $script:RunDir = $freshRunDir
    } else {
        $script:RunDir = Join-Path $resultRoot ((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + $runLabel)
        New-Item -ItemType Directory -Path $script:RunDir -Force | Out-Null
    }

    switch ($Command) {
        'bootstrap' { [void](Install-BslLanguageServer); Invoke-Doctor }
        'doctor' { Invoke-Doctor }
        'analyze' { Invoke-Analyze }
        'deploy' { Invoke-Deploy }
        'test' { if ($Hidden) { Invoke-TestHidden } else { Invoke-Test } }
        'unit' { Invoke-Unit }
        'serve' { Invoke-Serve }
        'stop' { Invoke-Stop }
    }
} catch {
    $script:ExitCode = 1
    Add-Step $Command 'error' $_.Exception.Message
} finally {
    if ($script:RunDir) {
        $report = [ordered]@{
            schemaVersion = 1
            projectId = if ($script:ProfileData) { $script:ProfileData.projectId } else { $null }
            command = $Command
            apply = [bool]$Apply
            startedAtUtc = $script:StartedAt.ToString('o')
            finishedAtUtc = [DateTime]::UtcNow.ToString('o')
            exitCode = $script:ExitCode
            steps = @($script:Steps)
            warnings = @($script:Warnings)
            artifacts = @($script:Artifacts)
        }
        if ($script:WorkflowProtocol) {
            $report.workflow = [ordered]@{ schemaVersion = 1; runId = $WorkflowRunId; stepId = $WorkflowStepId;
                sourceDigest = $WorkflowSourceDigest; targetDigest = $WorkflowTargetDigest; profileDigest = $WorkflowProfileDigest;
                mutationState = $script:WorkflowMutationState }
        }
        $reportPath = Join-Path $script:RunDir 'result.json'
        $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
        Write-Host "Отчёт: $reportPath"
    }
}

exit $script:ExitCode
