# One-directory helper with macOS code/data separation supplied by BUNDLE.
# console=True preserves the private job/--version CLI; this helper has no UI.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).resolve().parent
numpy_data, numpy_binaries, numpy_imports = collect_all('numpy')
a = Analysis([str(root / 'analyzer/src/faxto_analyzer/standalone.py')],
             pathex=[str(root / 'analyzer/src')], binaries=numpy_binaries,
             datas=numpy_data, hiddenimports=numpy_imports, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='faxto-helper',
          console=True, target_arch='arm64', strip=False, upx=False)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='faxto-helper')
app = BUNDLE(collection, name='faxto-helper.app', bundle_identifier='music.faxto.visualizer.analyzer',
             version='0.1.0', info_plist={'LSUIElement': True, 'LSMinimumSystemVersion': '15.0'})
