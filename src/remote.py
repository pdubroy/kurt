#! /usr/bin/env python2.6

import atexit
import errno
import fcntl
import logging
from multiprocessing.connection import Listener, Client
import os
import socket
import sys

from PyQt4.QtCore import *

MAC_OS = sys.platform.startswith("darwin")

logging.basicConfig(
	level=logging.DEBUG,
	format="[%(levelname)s] %(message)s")

	def main():
		# On Mac OS, there is an extra arg with the process serial number
		# when we are launched from Finder. Just ignore it.
		if MAC_OS and len(sys.argv) > 1 and sys.argv[1].startswith("-psn_"):
			file_args.pop(0)
		args = sys.argv[1:]

		settings = QSettings(
			QSettings.IniFormat, 
			QSettings.UserScope, 
			"dubroy.com", 
			"kurt")
		configDirName = os.path.dirname(str(settings.fileName()))
		pipeName = os.path.join(configDirName, "comm_pipe")

		# Try to create a Listener. If successful, it means no other process is
		# running. If it fails, then connect to the running process and tell
		# it to open up the given file(s).
		listener = None
		try:
			listener = Listener(pipeName)
			logging.debug("Starting new instance")
			import kurt
			k = kurt.Kurt(settings, listener)
			k.start()
		except socket.error, e:
			# If we get "Address already in use", than another process is running
			if e.errno != errno.EADDRINUSE:
				raise

			logging.debug("Connecting to existing instance")

			conn = Client(pipeName)
			# TODO: Parse the command line properly
			# For now, we assume that everything is a filename
			if len(sys.argv) > 1:
				for each in sys.argv[1:]:
					conn.send("open " + each)
			else:
				conn.send("raise")
			conn.close()
		finally:
			if listener: os.unlink(pipeName)
		
if __name__ == "__main__":	
	main()
