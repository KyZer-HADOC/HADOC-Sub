@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -m pip install -r requirements.txt
    if errorlevel 1 goto failed
    py -m py_compile app.py
    if errorlevel 1 goto failed
    py -m unittest discover -s tests -v
    if errorlevel 1 goto failed
    py make_icon.py
    if errorlevel 1 goto failed
    py -m PyInstaller --noconfirm --clean --onefile --windowed --icon icon.ico --add-data "icon.ico;." --collect-all customtkinter --collect-all darkdetect --collect-all imageio_ffmpeg --name HADOC-Sub app.py
) else (
    python -m pip install -r requirements.txt
    if errorlevel 1 goto failed
    python -m py_compile app.py
    if errorlevel 1 goto failed
    python -m unittest discover -s tests -v
    if errorlevel 1 goto failed
    python make_icon.py
    if errorlevel 1 goto failed
    python -m PyInstaller --noconfirm --clean --onefile --windowed --icon icon.ico --add-data "icon.ico;." --collect-all customtkinter --collect-all darkdetect --collect-all imageio_ffmpeg --name HADOC-Sub app.py
)

if errorlevel 1 goto failed
echo.
echo Build successful: dist\HADOC-Sub.exe
pause
exit /b 0

:failed
echo.
echo Build failed. Check the error messages above.
pause
exit /b 1
