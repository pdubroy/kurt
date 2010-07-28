#! /bin/bash

echo Setting up PyInstaller...
PREV_DIR=`pwd`
cd pyinstaller/source/linux
python ./Make.py
make
cd $PREV_DIR
python pyinstaller/Configure.py
echo Done PyInstaller setup.

echo Generating build spec...
python pyinstaller/Makespec.py --out=Kurt ../../../src/kurt.py
patch Kurt/kurt.spec < kurt.spec.patch
echo Done generating build spec.

echo Running PyInstaller...
python pyinstaller/Build.py Kurt/kurt.spec
patch Kurt.app/Contents/Info.plist < Info.plist.patch
cp -rv Kurt/dist/kurt/* Kurt.app/Contents/MacOS
cp -rv /usr/local/Trolltech/Qt-4.6.2/lib/QtGui.framework/Versions/Current/Resources/qt_menu.nib Kurt.app/Contents/Resources
echo Build complete.
