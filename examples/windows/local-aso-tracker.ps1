# Run this once from PowerShell after replacing the project path.
$Project = "C:\absolute\path\to\local-aso-tracker"
$Action = New-ScheduledTaskAction -Execute "$Project\.venv\Scripts\aso.exe" -Argument "--quiet check --only-missing-today" -WorkingDirectory $Project
$Trigger = New-ScheduledTaskTrigger -Daily -At 9am
Register-ScheduledTask -TaskName "Local ASO Tracker" -Action $Action -Trigger $Trigger -Description "Daily local App Store rank check"
