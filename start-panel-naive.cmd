@echo off
setlocal
pushd "%~dp0"
uv run --locked --all-packages python scripts/panel_demo.py naive
set "demo_exit=%errorlevel%"
popd
if not "%demo_exit%"=="0" pause
exit /b %demo_exit%
