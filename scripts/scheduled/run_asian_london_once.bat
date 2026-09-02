@echo off
cd /d "D:\ddev\AG profit trading"
python scripts\run_post_asian_pilot.py --once --json >> "%TEMP%\ag_shadow_asian_london.log" 2>&1
