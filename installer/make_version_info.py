"""Génère installer/version_info.txt (métadonnées Windows de l'exe) depuis version.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from version import __version__  # noqa: E402

v = tuple(int(x) for x in __version__.split(".")) + (0,) * (4 - len(__version__.split(".")))
tpl = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}),
  kids=[StringFileInfo([StringTable('040C04B0', [
    StringStruct('CompanyName', 'OverLoad'),
    StringStruct('FileDescription', 'OverLoad - Fast downloads for editors'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('ProductName', 'OverLoad'),
    StringStruct('ProductVersion', '{__version__}'),
    StringStruct('OriginalFilename', 'OverLoad.exe')])]),
    VarFileInfo([VarStruct('Translation', [1036, 1200])])])
"""
open(os.path.join(os.path.dirname(__file__), "version_info.txt"), "w", encoding="utf-8").write(tpl)
print(__version__)
