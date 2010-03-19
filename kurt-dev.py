import sys
import traceback

import kurt

CRASH_FILENAME = "crash.txt"

if __name__ == "__main__":
	files = sys.argv[1:]
	crash_count = 0

	# A return code of 1 indicates that the editor should restart gracefully
	rc = 1
	while rc == 1:
		try:
			reload(kurt)
			rc = kurt.start_editor(files)
		except Exception as e:
			crash_count += 1
			
			if crash_count >= 10:
				sys.stderr.write("Recursive crashing encountered!\n\n")
				raise e

			# Restore the previous state
			files = kurt.state.open_files

			# Also open a new file with the crash info
			with open(CRASH_FILENAME, "w") as f:
				traceback.print_exc(file=f)
			files.append(CRASH_FILENAME)
		else:
			files = kurt.state.open_files
