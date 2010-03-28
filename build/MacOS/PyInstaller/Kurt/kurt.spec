# -*- mode: python -*-
a = Analysis([os.path.join(HOMEPATH,'support/_mountzlib.py'), os.path.join(HOMEPATH,'support/useUnicode.py'), '../src/kurt.py'],
             pathex=['/Users/pdubroy/dev/kurt/build'])
pyz = PYZ(a.pure)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=1,
          name=os.path.join('build/pyi.darwin/kurt', 'kurt'),
          debug=False,
          strip=False,
          upx=True,
          console=1 )
coll = COLLECT( exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name=os.path.join('dist', 'kurt'))
import sys
if sys.platform.startswith("darwin"):
   app = BUNDLE(exe,
                appname="Kurt",
                version="0.1")
