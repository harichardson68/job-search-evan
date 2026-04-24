@echo off
chcp 65001 > nul
cd /d "C:\Users\haric\Evan Jobsearch"
python weekly_review_evan.py
echo Evan weekly review completed at %date% %time%
