# Deploy helper. Password comes from the environment and is masked on output.
param(
    [string]$Password = $env:APP_PASSWORD  # airules:allow creds-password
)

Write-Host "Running: app.exe /P***"
