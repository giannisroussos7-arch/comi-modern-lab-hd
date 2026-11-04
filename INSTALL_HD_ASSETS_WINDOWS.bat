@echo off
setlocal
cd /d "%~dp0"
echo COMI Modern Lab HD v0.11 - Install first HD room sidecar
echo ---------------------------------------------------------
set /p GAME=Paste your COMI game data folder: 
if not exist "%GAME%\COMI.LA0" (
  echo ERROR: COMI.LA0 not found in that folder.
  pause
  exit /b 1
)
if not exist "%GAME%\modernlab_hd" mkdir "%GAME%\modernlab_hd"
copy /Y "%~dp0modernlab_hd\enabled.flag" "%GAME%\modernlab_hd\enabled.flag" >nul
copy /Y "%~dp0modernlab_hd\room_09.mlhd" "%GAME%\modernlab_hd\room_09.mlhd" >nul
echo.
echo Installed HD cannon-hold sidecar into:
echo %GAME%\modernlab_hd
echo.
echo Use the custom Modern Lab ScummVM executable, start a NEW GAME,
echo and press F10 to toggle Original / HD background live.
pause
