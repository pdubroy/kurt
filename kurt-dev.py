import sys
import traceback

import kurt

CRASH_FILENAME = "crash.txt"

if __name__ == "__main__":
	files = sys.argv[1:]
	crash_count = 0

	while True:
		try:
			rc = kurt.start_editor(files)
			if rc == 0:
				sys.exit(0)
		except Exception as e:
			crash_count += 1
			
			# Once we hit 10 crashes, don't attempt to restart
			if crash_count < 10:
				# Save the traceback to a file, and open it in a new tab
				with open(CRASH_FILENAME, "w") as f:
					traceback.print_exc(file=f)
				files = [CRASH_FILENAME]
			else:
				traceback.print_exc(file=sys.stderr)
				sys.exit(1)
		reload(kurt)
