@echo off
cd /d "D:\ddev\AG profit trading"
python scripts\run_post_asian_pilot.py --once --json --pilot-config "config\pilot\AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml" >> "%TEMP%\ag_shadow_london_newyork.log" 2>&1
