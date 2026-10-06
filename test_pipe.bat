@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_ComputerSystem | Set-CimInstance -Property @{AutomaticManagedPagefile=$false}; Write-Host 'OK: AutomaticManagedPagefile = False'"
echo exit code: %errorlevel%
