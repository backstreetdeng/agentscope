@echo off
setlocal
rem Historical Excel monthly Skill demo; not the current BI monthly pipeline.
title Market Monthly Report Skill CLI Demo
pushd "%~dp0.."
if errorlevel 1 exit /b 1
set "DEMO_PYTHON=%~dp0..\..\Scripts\python.exe"

echo ============================================================
echo  Step 1: run WITHOUT dataset (data gate should BLOCK)
echo ============================================================
"%DEMO_PYTHON%" -X utf8 -m skills.market_analysis_skill.cli --question "Please generate the August 2026 China passenger vehicle monthly report."
echo.
pause

echo ============================================================
echo  Step 2: run WITH demo dataset (gate passes, prints context)
echo ============================================================
"%DEMO_PYTHON%" -X utf8 -m skills.market_analysis_skill.cli --input "skills\market_analysis_skill\profiles\passenger_vehicle_monthly\assets\demo_monthly_data.xlsx" --question "Please generate the August 2026 China passenger vehicle monthly report."
echo.
echo ============================================================
echo  Demo done. After editing rules in runtime.py, rerun Step 2.
echo ============================================================
popd
pause
endlocal
