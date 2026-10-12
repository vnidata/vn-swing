@echo off
chcp 65001 > nul
title VN-Swing 15M Realtime Sync Daemon
cd /d "%~dp0\.."
echo ================================================================
echo    VN-SWING QUANT SYSTEM - HE THONG DONG BO DU LIEU REALTIME
echo ================================================================
echo Dang khoi chay tien trinh dong bo 15 phut/lan kem Website Local...
python scripts/run_local_sync.py --serve --interval 900
pause
