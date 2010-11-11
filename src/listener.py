#! /usr/bin/env python2.5

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

import errno
import logging
import multiprocessing.connection
import os

from PyQt4.QtCore import *

class _Listener(QObject):

	remoteOpenRequest = pyqtSignal(str)

	def __init__(self, mp_listener, *args):
		super(QObject, self).__init__()
		self._listener = mp_listener
	
	def start(self):
		thread.start_new_thread(self.run, ())
		
	def run(self):
		while True:
			conn = None
			try:
				conn = self._listener.accept()
				logging.debug("Connection accepted")
				message = conn.recv()
				logging.debug("Listener received message '%s'" % message)
				parts = message.split(" ", 1)
				if parts[0] == "quit":
					break
				elif parts[0] == "raise":
					self.remoteOpenRequest.emit("")
				elif parts[0] == "open":
					# Using a signal to pass the message to the UI thread
					self.remoteOpenRequest.emit(parts[1])
				else:
					logging.warning("Listener received unrecognized command '%s'" % cmd)
			finally:
				if conn: conn.close()
		logging.debug("Exiting listener thread")
		
	def shutdown(self):
		"""Shut down the listener thread. This should be called by an outside
		thread, usually the one that started the listener thread."""

		logging.debug("Attempting to shut down listener thread")
		client = None
		try:
			client = Client(self._listener.address)
			client.send("quit")
		finally:
			if client: client.close()
		self._listener.close()

def _get_pipe_name(config_dir):
	return os.path.join(config_dir, "sock")

def Listener(config_dir):
	listener = None	
	try:
		mp_listener = multiprocessing.connection.Listener(pipe_name)
		listener = _Listener(mp_listener)
	except socket.error, e:
		# If we get "Address already in use", than another process is running
		if e.errno != errno.EADDRINUSE:
			raise
			
	return listener
	
def Client(config_dir):
	return multiprocessing.connection.Client(pipe_name)
