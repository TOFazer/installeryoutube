@echo off
echo === Construction de OverLoad.exe ===
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name OverLoad --collect-all customtkinter --collect-all imageio_ffmpeg overload.py
echo.
echo Termine ! L'application est dans le dossier dist\OverLoad.exe
pause
