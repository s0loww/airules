# Deploy helper. Deliberately leaks a credential for the fixture.
param(
    [string]$Password = $env:APP_PASSWORD
)

Write-Host "Running: app.exe /P`"$Password`""
