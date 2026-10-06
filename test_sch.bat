@echo off
schtasks /create /tn "MemOptimaRestoreTest" /tr "powershell.exe -WindowStyle Hidden -NoProfile -Command 'Get-CimInstance Win32_ComputerSystem | Set-CimInstance -Property @{AutomaticManagedPagefile=$true}; Unregister-ScheduledTask -TaskName MemOptimaRestoreTest -Confirm:$false'" /sc onstart /ru SYSTEM /rl HIGHEST /f
echo exit code: %errorlevel%
