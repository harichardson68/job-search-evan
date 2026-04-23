@echo off
chcp 65001 > nul
cd /d "C:\Users\haric\Evan Jobsearch"
python update_scoring_evan.py
echo Evan update scoring completed at %date% %time%