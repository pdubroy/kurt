# Kurt: A minimal, cross-platform text editor.

Kurt is a simple, modern text editor written in pure Python, and built on PyQt4. So far, it has been developed and tested on Windows, but it should work without modification on Mac OS and Linux.

## Installing and Running

Kurt requires Python >= 2.6, and PyQt4, which can be acquired from <http://www.riverbankcomputing.co.uk/software/pyqt/download>.

To run kurt, just run the file kurt.py in the python interpreter. For self-hosting, i.e. to use kurt to develop its own source code, use the script kurt-dev.py.

## Keyboard Shortcuts

- Ctrl-T: Open a new tab
- Ctrl-W: Close the current tab
- Ctrl-O: Open a file in a new tab
- Ctrl-S: Save the current file (unnecessary, since kurt autosaves)
- Ctrl-F: Incremental search
- Ctrl-R: Restart the editor and reload the script from the file system (useful for self-hosting)

## License

Kurt is Copyright (c) 2010 Patrick Dubroy <pdubroy@gmail.com>

This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License version 2 as published by the Free Software Foundation.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
