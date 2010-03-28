#! /usr/bin/env python

import os
import sys

if sys.platform.startswith("darwin"):
    cwd = os.getcwd()
    os.chdir("MacOS/PyInstaller")
    os.system("./build.sh")
    os.chdir(cwd)
else:
    raise Exception("Don't know how to build for platform '%s'!" % sys.platform)
