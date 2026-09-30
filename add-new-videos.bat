@echo off
rem Double-click after dropping new videos into videos\<Category>\ .
rem Adds them to the app, pushes to GitHub and waits until they are live.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python "tools\add_new_videos.py" %*
) else (
  py -3 "tools\add_new_videos.py" %*
)
echo.
pause
