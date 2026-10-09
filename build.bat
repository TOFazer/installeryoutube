@echo off
echo === Construction de OverLoad ===
python -m pip install -r requirements-dev.txt || goto :err
python installer\make_version_info.py > version.tmp || goto :err
set /p VER=<version.tmp
del version.tmp
python -m PyInstaller --noconfirm overload.spec || goto :err
where iscc >nul 2>nul && iscc /DMyAppVersion=%VER% installer\overload.iss
echo.
echo Termine ! Application : dist\OverLoad\OverLoad.exe
echo Installateur (si Inno Setup est installe) : dist\OverLoad-Setup-%VER%.exe
pause
exit /b 0
:err
echo Erreur pendant la construction.
pause
exit /b 1
