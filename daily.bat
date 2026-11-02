@echo off
rem Daily job: apply unsubscribes/bounces from both inboxes, then send due sequence emails.
rem Schedule it with Windows Task Scheduler (see README).
cd /d "%~dp0"
if not exist data mkdir data
".venv\Scripts\python.exe" -m engine tick --live >> data\daily.log 2>&1
