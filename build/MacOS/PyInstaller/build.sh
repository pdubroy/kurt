#! /bin/bash

echo Running PyInstaller...
python pyinstaller/Build.py Kurt/kurt.spec
patch Kurt.app/Contents/Info.plist < Info.plist.patch
cp -rv Kurt/dist/kurt/* Kurt.app/Contents/MacOS
cp -rv /usr/local/Trolltech/Qt-4.6.2/lib/QtGui.framework/Versions/Current/Resources/qt_menu.nib Kurt.app/Contents/Resources
echo Build complete.
