#! /usr/bin/env python2.6

# Copyright (c) 2010 Patrick Dubroy <pdubroy@gmail.com>
#
# This program is free software; you can redistribute it and/or modify it 
# under the terms of the GNU General Public License version 2 as published 
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT 
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or 
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for 
# more details.

import sys
import traceback

if __name__ == "__main__":
	files = sys.argv[1:]
	tabContents = []

	restart = True
	while restart:
		try:
			import kurt
			rc = kurt.start_editor(files, tabContents)
			# A return code of zero indicates a clean, user-initiated exit
			if rc == 0:
				restart = False
		except Exception as e:
			# When the editor is restarted, open a new tab with the traceback
			tabContents = traceback.format_exc()
		files = []
		if "kurt" in sys.modules:
			del(sys.modules["kurt"])
		else:
			sys.stderr.write(tabContents)
			restart = False
