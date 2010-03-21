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
