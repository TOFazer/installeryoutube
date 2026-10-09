# PyInstaller — build : pyinstaller overload.spec
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [("assets", "assets")] + collect_data_files("imageio_ffmpeg")
a = Analysis(["main.py"], datas=datas,
             hiddenimports=collect_submodules("yt_dlp.extractor") + ["PySide6.QtSvg"],
             excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtQuick",
                       "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="OverLoad", console=False,
          icon="assets/logo/overload.ico", version="installer/version_info.txt")
coll = COLLECT(exe, a.binaries, a.datas, name="OverLoad")
