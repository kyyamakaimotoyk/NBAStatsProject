@echo off
rem ============================================================================
rem Nightly home-side NBA ingest + S3 handoff.
rem Scheduled via Windows Task Scheduler (11:30 daily, JST). Everything the
rem run prints is appended to logs\home_ingest.log - check there when the
rem freshness alarm emails you.
rem NOTE: this file must stay ASCII with CRLF line endings. cmd.exe misparses
rem LF-only batch files at 512-byte block boundaries and executes fragments.
rem ============================================================================
cd /d D:\Kai\PycharmProjects\NBAStatsProject
if not exist logs mkdir logs
call .venv\Scripts\activate.bat
echo ============================================================ >> logs\home_ingest.log
python data_engineering\home_ingest_push.py >> logs\home_ingest.log 2>&1
exit /b %ERRORLEVEL%
