@echo off
rem ============================================================================
rem Pre-tip injury refresh (E28 follow-up, added 2026-11-13).
rem Scrapes TODAY's NBA official injury report (US Eastern date) and ships only
rem historical_injury_report to S3, so the cloud's 5:45 PM ET prediction run uses
rem the same availability source the models were trained on.
rem Schedule: daily at 07:20 JST = 17:20 EST (Nov-Mar). During US daylight time
rem (Mar-Nov) move it to 06:20 JST, or it lands after the 5:45 PM ET run.
rem Output is appended to logs\home_injuries.log.
rem NOTE: this file must stay ASCII with CRLF line endings.
rem ============================================================================
cd /d D:\Kai\PycharmProjects\NBAStatsProject
if not exist logs mkdir logs
call .venv\Scripts\activate.bat
echo ============================================================ >> logs\home_injuries.log
python data_engineering\home_ingest_push.py --injuries-only >> logs\home_injuries.log 2>&1
exit /b %ERRORLEVEL%
