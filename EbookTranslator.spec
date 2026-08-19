from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPEC).resolve().parent
lxml_datas, lxml_binaries, lxml_hiddenimports = collect_all("lxml")

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT / "scripts")],
    binaries=lxml_binaries,
    datas=[(str(ROOT / "scripts"), "scripts"), (str(ROOT / "template"), "template"), *lxml_datas],
    hiddenimports=["lxml", "lxml.etree", *lxml_hiddenimports],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="EbookTranslator", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
