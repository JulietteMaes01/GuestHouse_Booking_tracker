@echo off
cd /d %~dp0
python run_daily_update.py >> update_log.txt 2>&1