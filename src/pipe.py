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

import atexit
import errno
import logging
import os
import socket
import thread

from PyQt4.QtCore import *

__all__ = ["Listener", "Client"]

_socket_files = []

def _cleanup():
	for each in _socket_files:
		try:
			os.remove(each)
		except OSError, e:
			pass
	
atexit.register(_cleanup)

class _Listener(QObject):

	remoteOpenRequest = pyqtSignal(str)

	def __init__(self, sock, *args):
		super(QObject, self).__init__()
		self._socket = sock
		self._socket.listen(1)
	
	def start(self):
		thread.start_new_thread(self.run, ())

	def _handle_connection(self, conn):
		try:
			logging.debug("Connection accepted")
			message = conn.recv(1024)
			logging.debug("Listener received message '%s'" % message)
			parts = message.split(" ", 1)
			if parts[0] == "quit":
				return False
			elif parts[0] == "raise":
				self.remoteOpenRequest.emit("")
			elif parts[0] == "open":
				# Using a signal to pass the message to the UI thread
				self.remoteOpenRequest.emit(os.path.abspath(parts[1]))
			else:
				logging.warning("Listener received unrecognized command '%s'" % cmd)
		finally:
			conn.close()
		return True
		
	def run(self):
		filename = None
		try:
			filename = self._socket.getsockname()

			while True:
				conn, addr = self._socket.accept()
				if not self._handle_connection(conn):
					break
		finally:
			self._socket.close()
			if filename: os.remove(filename) # Clean up the UNIX domain socket file
		logging.debug("Exiting listener thread")
		
	def shutdown(self):
		"""Shut down the listener thread. This should be called by an outside
		thread, usually the one that started the listener thread."""

		logging.debug("Attempting to shut down listener thread")
		addr = self._socket.getsockname()
		client_sock = None
		try:
			client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
			client_sock.connect(addr)
			client_sock.send("quit")
		finally:
			if client_sock: client_sock.close()

def _get_pipe_name(config_dir):
	return os.path.join(config_dir, "sock")

def Listener(config_dir):
	listener = None	
	try:
		sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		filename = _get_pipe_name(config_dir)
		sock.bind(filename)
		_socket_files.append(filename) # Put this in the list to be cleaned up
		listener = _Listener(sock)
	except socket.error, e:
		# If we get "Address already in use", than another process is running
		if e[0] != errno.EADDRINUSE:
			raise
			
	return listener

def Client(config_dir):
	sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
	sock.connect(_get_pipe_name(config_dir))
	return sock

