@echo off
chcp 65001 > nul
title VN-Swing 5M Realtime Sync Daemon
cd /d "%~dp0\.."
echo ================================================================
echo    VN-SWING QUANT SYSTEM - HE THONG DONG BO DU LIEU REALTIME
echo ================================================================
echo Dang khoi chay tien trinh dong bo 5 phut/lan kem Website Local...
python scripts/run_local_sync.py --serve --interval 300
pause
