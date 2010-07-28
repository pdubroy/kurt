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

from __future__ import with_statement

__all__ = ["start_editor"]

import errno
import inspect
import keyword
import logging
from multiprocessing.connection import Listener, Client
import os
import shutil
import socket
import StringIO
import sys
import thread
import token
import tokenize
import traceback

from PyQt4.QtCore import *
from PyQt4.QtGui import *

logging.basicConfig(
	level=logging.DEBUG,
	format="[%(levelname)s] %(message)s")
MAC_OS = sys.platform.startswith("darwin")

def abs_path(relpath):
	"""Given a path relative to this script, return the absolute path."""
	return os.path.join(os.path.dirname(__file__), relpath)

def pyqt_guarded(f):
	"""A decorator to prevent unhandled exceptions to be thrown outside of
	Python code. Should be used for any methods that are called directly
	from PyQt."""
	def wrapper(*args):
		try:
			return f(*args)
		except Exception, e:
			sys.stderr.write("Unhandled exception in wrapper around %s\n" % f)
			traceback.print_exc()
	return wrapper

# A decorator to be used for Python methods which override a Qt method.
pyqt_override = pyqt_guarded

def safe_connect(signal, slot):
	"""Connects a PyQt signal to a slot (a Python callable), while ensuring
	that no unhandled exceptions are raised in the slot.
	"""
	signal.connect(pyqt_guarded(slot))
	
def signal_connect(signal1, signal2):
	"""Connects two PyQt signals together. Not necessary, but here to provide
	symmetry with safe_connect().
	"""
	signal1.connect(signal2)

def keyEventMatches(event, key, modifier="No"):
	"""Helper for hanlding Qt key events. 'key' is a string representing
	the key to look for, and 'modifier' is one of "Shift", "Control", etc.
	"""
	qt_key = getattr(Qt, "Key_" + key)
	if event.key() != qt_key:
		return False
	return event.modifiers() == getattr(Qt, modifier + "Modifier")

class KeyFilter(QObject):

	def __init__(self, win, tab, *args):
		QObject.__init__(self, *args)
		self._handlers = {}

		shortcuts = {
			("Control", "T"): win.new_tab,
			("Control", "O"): win.open_file,
			("Control", "S"): tab.save,
			("Control", "W"): tab.closeTab,
			("Control", "R"): win.reloadAndRestart,
			("Control", "F"): tab.find,
			("Control", "L"): tab.gotoLine
		}
		
		# Map from our simplified shortcut representation to an internal one,
		# which will make it easier to look up handlers for Qt events
		for shortcut, handler in shortcuts.iteritems():
			modifiers = shortcut[0]
			if not isinstance(modifiers, list):
				modifiers = [modifiers]
			# See the Qt::KeyboardModifiers enum
			qt_mod_code = Qt.NoModifier
			for each in modifiers:
				qt_mod_code |= getattr(Qt, each + "Modifier")
			# See the Qt::Key enum
			qt_keycode = getattr(Qt, "Key_" + shortcut[1].upper())
			
			# Unfortunately, we can't use a QtCore.KeyboardModifiers object
			# as a key in a dictionary, although we can test for equality.
			# So store the modifiers in the value, and iterate through all
			# handlers for a particular key.
			handlers = self._handlers.get(qt_keycode, [])
			handlers.append((qt_mod_code, handler))
			self._handlers[qt_keycode] = handlers

	def get_handler(self, key, modifier):
		for modifiers, handler in self._handlers.get(key, []):
			if modifiers == modifier:
				return handler
		return None

	@pyqt_override
	def eventFilter(self, obj, event):
		# Ignore everything but keypresses
		if event.type() != QEvent.KeyPress:
			return False

		# Filter on the regular keys (ASCII key codes)
		if event.key() < 256:
			handler = self.get_handler(event.key(), event.modifiers())
			if handler:
				handler()
				return True # Swallow the event

		return False
		
class ImageButton(QPushButton):
	def __init__(self, name, width, height):
		QPushButton.__init__(self)
		self.setStyleSheet("""
			QPushButton {
				background-image: url(%s) no-repeat;
				background-repeat: no repeat;
				background-position: center;
				min-width: %dpx;
				min-height: %dpx;
				border: 0;
			}
			QPushButton:pressed {
				background-image: url(%s);
			}
		""" % (abs_path("graphics/%s.png" % name), width, height, abs_path("graphics/%s_pressed.png" % name)))
		self.setFlat(True)
		self.setFixedSize(width, height)

class PythonHighlighter(QSyntaxHighlighter):
	def __init__(self, *args):
		QSyntaxHighlighter.__init__(self, *args)

		self.commentFmt = QTextCharFormat()
		self.commentFmt.setForeground(QColor("#0065ff"))

		self.keywordFmt = QTextCharFormat()
		self.keywordFmt.setForeground(QColor("#215ee6"))

		self.stringFmt = QTextCharFormat()
		self.stringFmt.setForeground(QColor("#009900"))

		self.identifierFmt = QTextCharFormat()
		self.identifierFmt.setForeground(QColor("#ff8e4b"))

		self.keywordFmt = QTextCharFormat()
		self.keywordFmt.setForeground(QColor("#33bbff"))
		self.keywordFmt.setProperty(QTextFormat.FontWeight, 600)

	@pyqt_override
	def highlightBlock(self, text):
		stripped_line = str(text).lstrip()
		if len(stripped_line) > 0 and stripped_line[0] == "#":
			self.setFormat(0, len(text), self.commentFmt)
		else:
			f = StringIO.StringIO(str(text))
			try:
				awaiting_decl = False
				for each in tokenize.generate_tokens(f.readline):
					token_type, text, start, end, line = each
					_, start_col = start
					_, end_col = end
					length  = end_col - start_col
					name = token.tok_name[token_type]
					if name == "STRING":
						self.setFormat(start_col, length, self.stringFmt)
					elif name == "NAME":
						if text in keyword.kwlist:
							self.setFormat(start_col, length, self.keywordFmt)
							awaiting_decl = text in ["def", "class"]
						else:
							if awaiting_decl:
								self.setFormat(start_col, length, self.identifierFmt)
								awaiting_decl = False
					prev_tok_name = name
			except tokenize.TokenError:
				pass

class FindBar(QWidget):
	def __init__(self, parent, textEdit, *args):
		QWidget.__init__(self, parent, *args)
		self._leftCorner = QPixmap(abs_path("graphics/bottom-left.png"))
		self._rightCorner = QPixmap(abs_path("graphics/bottom-right.png"))

		self.textEdit = textEdit
		layout = QHBoxLayout()
		layout.setContentsMargins(4, 4, 4, 4)
		layout.setSpacing(2)
		self.setLayout(layout)
		
		label = QLabel(text="Find:")
		layout.addWidget(label)

		self.lineEdit = QLineEdit()
		layout.addWidget(self.lineEdit)
		
		closeButton = ImageButton("close", 16, 16)
		safe_connect(closeButton.clicked, self.closeButtonClicked)
		layout.addWidget(closeButton)
		
		self.lineEdit.installEventFilter(self)
		safe_connect(self.lineEdit.textEdited, self._findText)
		self.setFocusProxy(self.lineEdit)
		
		self.setObjectName("findBar") # For styling purposes
		self.setStyleSheet("""
			#findBar { border: 0; border-bottom: 1px solid #737373; }
			QLabel { font-size: 10pt; padding-top: 2px; }
			QLineEdit { font-size: 10pt; border: 1px solid DarkGray; }
		""")
		
		self._originalCursor = None
		
		self._animationTimer = QTimer(self)
		safe_connect(self._animationTimer.timeout, self._animationCallback)
		
		self.offsetY = 0
		self.hideThyself(False)
	
	@pyqt_override
	def eventFilter(self, obj, event):
		if (event.type() == QEvent.KeyPress
		and event.modifiers() == Qt.NoModifier):
			key = event.key()
			if key == Qt.Key_Escape:
				self._clearSelection()
				self.hideThyself()
				return True
			elif key == Qt.Key_Return or key == Qt.Key_Down:
				# Go to the next match
				self._findText(self.lineEdit.text(), False)
				return True
			elif key == Qt.Key_Up:
				# Go to the previous match
				self._findText(self.lineEdit.text(), False, False)
				return True
		return QObject.eventFilter(self, obj, event)

	@pyqt_override
	def paintEvent(self, event):
		p = QPainter(self)
		rect = self.rect()
		# Pull the bottom up by 1 pixel to prevent clipping
		rect.adjust(0, 0, -1, 0)

		p.setBrush(QApplication.palette().brush(QPalette.Window))
		p.setPen(Qt.NoPen)
		p.drawRoundedRect(rect.adjusted(1, -110, -1, -1), 4, 4)
		
		p.setPen(QColor(142, 142, 142))
		x = rect.left()
		imageY = rect.bottom() - self._leftCorner.height() + 1
		p.drawLine(rect.left(), rect.top(), x, imageY)
		p.drawPixmap(rect.left(), imageY, self._leftCorner)
		p.drawLine(rect.right(), rect.top(), rect.right(), imageY)
		p.drawPixmap(rect.right() - self._rightCorner.width() + 1, imageY, self._rightCorner)
		p.drawLine(
			rect.left() + self._leftCorner.width(), 
			rect.bottom(),
			rect.right() - self._rightCorner.width(),
			rect.bottom())
		QWidget.paintEvent(self, event)
		
	def _clearSelection(self):
		cursor = self.textEdit.textCursor()
		cursor.clearSelection()
		self.textEdit.setTextCursor(cursor)
		
	def _setBackground(self, found):
		foundStyle = "QLineEdit { background-color: white; color: black; }"
		notFoundStyle = "QLineEdit { background-color: #FF6666; color: white; }"
		self.lineEdit.setStyleSheet(foundStyle if found else notFoundStyle)
		
	def _findText(self, text, includeSelection=True, forwards=True):
		if len(text) == 0:
			self._setBackground(found=True)
			self._clearSelection()
			if self._originalCursor:
				self.textEdit.setTextCursor(self._originalCursor)
				self._originalCursor = None
		else:
			cursor = self.textEdit.textCursor()
			if includeSelection or not forwards:
				start = cursor.selectionStart()
			else:
				start = cursor.selectionEnd()
			flags = QTextDocument.FindFlags()
			if not forwards:
				flags = QTextDocument.FindBackward
			cursor = self.textEdit.document().find(text, start, flags)
			if not cursor.isNull():
				self.textEdit.setTextCursor(cursor)
			self._setBackground(found=not cursor.isNull())
			
	def _updatePos(self):
		self.move(self.x(), self.offsetY)
			
	def _animationCallback(self):
		newOffsetY = self.offsetY + self._animationStep
		minVal = -self.sizeHint().height()
		maxVal = 0
		if not minVal < newOffsetY < maxVal:
			self._animationTimer.stop()
		if newOffsetY <= minVal:
			self.hide()
		newOffsetY = max(minVal, min(newOffsetY, maxVal))
		self.offsetY = newOffsetY
		self._updatePos()

	def _animate(self, duration_msecs, showing=True):
		endOffset = 0 if showing else -self.sizeHint().height()

		interval = 33 # 30 FPS
		# TODO: We don't need more than 1 frame per pixel of height
		frames = max(1, duration_msecs / interval)
		
		self._animationTimer.stop()
		self._animationStep = abs(endOffset - self.offsetY) * 1. / frames
		if showing:
			self.show()
		else:
			self._animationStep *= -1
		if duration_msecs == 0:
			self._animationCallback()
		else:
			self._animationTimer.start(interval)
			
	def showThyself(self, animated=True):
		duration = 200 if animated else 0
		self._animate(duration, True)
		
	def hideThyself(self, animated=True):
		self.textEdit.setFocus()
		duration = 200 if animated else 0
		self._animate(duration, False)

	def open(self, text=None):
		"""Basically just a synonym for show(), but allows the text to be set."""
		if text:
			self.lineEdit.setText(text)
		self.lineEdit.selectAll()
		self.setFocus()
		self.showThyself()

	def closeButtonClicked(self, checked):
		self.hideThyself()
		
	@pyqt_override
	def focusEvent(self, event):
		self._originalCursor = self.textEdit.textCursor()

class KTextEdit(QTextEdit):
	
	def __init__(self, *args):
		QTextEdit.__init__(self, *args)
		# TODO: This should be a config option
		self.setStyleSheet("""
			QTextEdit {
				color: #eeeeee;
				background-color: #303030;
				border: 0;
			}
		""")

	def _unindentAt(self, cursor):
		# Helper for un-indenting a line.
		# TODO: Make this function smarter than just deleting leading tab
		if self.document().characterAt(cursor.position()) == QChar("\t"):
			cursor.deleteChar()

	@pyqt_override
	def keyPressEvent(self, event):
		# Handle tabs specially: if there's a selection spanning multiple 
		# lines, hitting tab indents all the spanned lines.

		indent = keyEventMatches(event, "Tab")
		unindent = keyEventMatches(event, "Backtab", "Shift")

		# TODO: Both of these handlers should be smarter, and detect/insert
		# a logical tab (e.g. 4 spaces) rather than looking for \t

		if indent or unindent:
			cursor = self.textCursor()
			# Don't use cursor.selectedText(), it uses \u2029 instead of \n
			if cursor.selection().toPlainText().contains("\n"):
				# Append a tab at the beginning of every line in the selection,
				# except the last line if the cursor is at position 0.
				ins_cursor = QTextCursor(cursor)
				ins_cursor.beginEditBlock()
				ins_cursor.setPosition(cursor.selectionStart())
				ins_cursor.movePosition(QTextCursor.StartOfLine)
				while ins_cursor.position() < cursor.position():
					if indent:
						ins_cursor.insertText("\t")
					else:
						self._unindentAt(ins_cursor)
					# Move to the beginning of the next line
					ins_cursor.movePosition(QTextCursor.NextBlock)
				ins_cursor.endEditBlock()
				return # Swallow the event
		elif keyEventMatches(event, "Return"):
			# Check the indentation level of the current line
			cursor = self.textCursor()
			cursor.movePosition(QTextCursor.StartOfLine)
			while self.document().characterAt(cursor.position()) == QChar("\t"):
				cursor.movePosition(QTextCursor.Right)
			indent_level = cursor.columnNumber()

			# Insert a line break and match the indentation level
			self.textCursor().insertText("\n" + indent_level * "\t")
			return
			
		QTextEdit.keyPressEvent(self, event)

class Editor(QWidget):

	# Emitted when the title of the tab has changed
	titleChanged = pyqtSignal(str)
	
	# Emitted when the document modification state has changed
	modificationChanged = pyqtSignal(bool)

	def __init__(self, window, *args):
		QWidget.__init__(self, *args)
		
		self.window = window
		self.path = None # Path to the file that is open in this tab
		
		layout = QVBoxLayout()
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)
		self.setLayout(layout)

		self.textEdit = KTextEdit(self)
		self.textEdit.setAcceptRichText(False)
		self.textEdit.setCursorWidth(1)
		doc = self.textEdit.document()
		signal_connect(doc.modificationChanged, self.modificationChanged)
		safe_connect(doc.contentsChanged, self._contentsChanged)

		# TODO: The font should be a style/config option
		fonts = [
			("Menlo", 12),
			("Monaco",  12),
			("Consolas", 10),
			("Courier New", 12)
		]
		for name, size in fonts:
			font = QFont(name, size, QFont.Normal)
			if font.exactMatch():
				self.textEdit.setCurrentFont(font)
				break
		
		layout.addWidget(self.textEdit)
		self.setFocusProxy(self.textEdit)

		# Note: FindBar is not added to the layout; we place it manually
		self.findBar = FindBar(self, self.textEdit)
		
		self.keyFilter = KeyFilter(window, self)
		self.textEdit.installEventFilter(self.keyFilter)
		
		self._save_timer = QTimer(self)		
		safe_connect(self._save_timer.timeout, self._saveTimeout)

		safe_connect(self.titleChanged, self.updateMode)

	@pyqt_override
	def showEvent(self, event):
		# Set the tab width to 4 chars (assuming monospace font)
		# If we do this in the constructor, it's not calculated correctly
		fontMetrics = self.textEdit.fontMetrics()
		self.textEdit.setTabStopWidth(fontMetrics.width("0000"))
		
	@pyqt_override
	def resizeEvent(self, event):
		# Lay out the FindBar
		sizeHint = self.findBar.sizeHint()
		self.findBar.setGeometry(
			self.width() - sizeHint.width() - 20,
			self.findBar.offsetY,
			sizeHint.width(),
			sizeHint.height())
	
	def _contentsChanged(self):
		# When the contents of the document change, save the document if no
		# more changes are made after 500 seconds have elapsed
		# Autosave is disabled for now
		if False:
			self._save_timer.stop()
			self._save_timer.start(500)
		
	def _saveTimeout(self):
		if self.path:
			self.save()
			
	def getTitle(self):
		if self.path:
			return os.path.basename(self.path)
		return "New File"
		
	def isModified(self):
		return self.textEdit.document().isModified()
		
	def open_file(self, path):
		"""Open the file indicated by 'path' into this editor. 'path' may be
		an absolute path, or relative to the current working directory."""
		if os.path.exists(path):
			self.textEdit.setPlainText(open(path, "r").read())
			self.textEdit.document().setModified(False)
		self.path = os.path.abspath(path) # Always save as absolute
		self.titleChanged.emit(self.getTitle())

	def save(self):
		if not self.textEdit.document().isModified():
			return

		if self.path is None:
			self.path = str(QFileDialog.getSaveFileName(self.window))

			# If the user didn't select a file, abort the save operation
			if len(self.path) == 0:
				self.path = None
				return
				
			self.titleChanged.emit(self.getTitle())

		# Rename the original file, if it exists
		overwrite = os.path.exists(self.path)
		if overwrite:
			temp_path = self.path + "~"
			if os.path.exists(temp_path):
				os.remove(temp_path)
			os.rename(self.path, temp_path)			

		try:
			# Save the new contents
			with open(self.path, "w") as f:
				f.write(self.textEdit.document().toPlainText())

			if overwrite:
				os.remove(temp_path)
		except:
			if overwrite and os.path.exists(temp_path):
				os.remove(self.path)
				os.rename(temp_path, self.path)
			
		self.textEdit.document().setModified(False)

	def find(self):
		cursor = self.textEdit.textCursor()
		if cursor.hasSelection():
			self.findBar.open(cursor.selectedText())
		else:
			self.findBar.open()

	def closeTab(self):
		self.window.close_tab(self)

	def gotoLine(self):
		linecount = self.textEdit.document().lineCount()
		line_num, ok = QInputDialog.getInt(self, "Go to Line", "Line number:", min=0, max=linecount)
		if ok:
			# Note: findBlockByLineNumber assumes a 0-based index
			block = self.textEdit.document().findBlockByLineNumber(line_num - 1)
			self.textEdit.setTextCursor(QTextCursor(block))

	def updateMode(self, title):
		if self.path and self.path.endswith(".py"):
			self.highlighter = PythonHighlighter(self.textEdit)
			self.highlighter.rehighlight()

class MainWindow(QMainWindow):

	# Emitted when the window is moved or resized
	geometryChanged = pyqtSignal()
	
	# Emitted when tabs are opened or closed, etc.
	contentsChanged = pyqtSignal()
	
	# Emitted when the window is closed (by user action)
	windowClosed = pyqtSignal(bool)

	def __init__(self, *args):
		QMainWindow.__init__(self, *args)
		self.tabWidget = QTabWidget()
		self.tabWidget.setMovable(True)
		self.tabWidget.setDocumentMode(True)
		self.setCentralWidget(self.tabWidget)
		
		safe_connect(self.tabWidget.currentChanged, self.tabSwitched)
		
		self.closed_cleanly = True

	@pyqt_override	
	def showEvent(self, event):
		# If no tabs exist yet, create a default one
		if self.tabWidget.count() == 0:
			self.new_tab()
		QMainWindow.showEvent(self, event)
	
	@pyqt_override
	def moveEvent(self, event):
		self.geometryChanged.emit()
		QMainWindow.moveEvent(self, event)
	
	@pyqt_override
	def resizeEvent(self, event):
		self.geometryChanged.emit()
		QMainWindow.resizeEvent(self, event)

	@pyqt_override
	def closeEvent(self, event):
		self.windowClosed.emit(self.closed_cleanly)
		event.accept()
	
	@pyqt_override
	def dragEnterEvent(self, event):
		# Only accept the drag and drop if it's files
		# The TextEdit widget will accept drops of text itself
		mimeData = event.mimeData()
		if mimeData.hasUrls():
			for url in mimeData.urls():
				if url.scheme() != "file":
					return
		event.acceptProposedAction()

	@pyqt_override
	def dragMoveEvent(self, event):
		event.acceptProposedAction()

	@pyqt_override
	def dropEvent(self, event):
		# We can assume once we get here it's only file: URLs
		for url in event.mimeData().urls():
			# TODO: Do we need to check that the file exists?
			self.new_tab(url.toLocalFile())
		event.acceptProposedAction()
		
	def reloadAndRestart(self):
		self.currentTab().save()
		filename = inspect.getfile(inspect.currentframe())
		try:
			execfile(filename, {"__name__": "kurt"})
		except Exception, e:
			# If there's an error in the script, don't restart; just open
			# a new tab with the traceback
			self.new_tab(contents=traceback.format_exc())
		else:
			# Exit, and the calling script will restart the editor
			self.closed_cleanly = False
			self.close()

	def currentTab(self):
		return self.tabWidget.currentWidget()
		
	def updateWindowTitle(self):
		editor = self.tabWidget.currentWidget()
		filename = os.path.basename(editor.path) if editor.path else "New File"
		self.setWindowTitle(filename + " - Kurt")

	def tabSwitched(self, index):
		# Handle the case when the last tab is closed
		if index >= 0:
			self.updateWindowTitle()

	def new_tab(self, filename=None, contents=None):
		"""Open a new editor tab. If filename is specified, it will be loaded
		into the tab. Otherwise, if contents (a string) is specified, the
		editor text will be set to that.
		"""
		editor = Editor(self)
		safe_connect(editor.modificationChanged, self.tabModificationChanged)
		safe_connect(editor.titleChanged, self.tabTitleChanged)

		index = self.tabWidget.addTab(editor, editor.getTitle())

		if filename:
			editor.open_file(str(filename))
		elif contents:
			editor.textEdit.setText(contents)
		self.tabWidget.setCurrentIndex(index) # Switch to the new tab
		self.contentsChanged.emit()
		editor.setFocus()

	def getTab(self, widgetOrIndex):
		"""Given either the widget or its index, return the widget."""
		if isinstance(widgetOrIndex, int):
			return self.tabWidget.widget(widgetOrIndex)
		return widgetOrIndex
		
	def getTabIndex(self, widgetOrIndex):
		"""Given either the widget or its index, return its index."""
		if isinstance(widgetOrIndex, int):
			return widgetOrIndex
		return self.tabWidget.indexOf(widgetOrIndex)
		
	def setTabTitle(self, widgetOrIndex, title):
		self.tabWidget.setTabText(self.getTabIndex(widgetOrIndex), title)
		
	def close_tab(self, tab):
		self.tabWidget.removeTab(self.tabWidget.indexOf(tab))
		if self.tabWidget.count() == 0:
			self.new_tab()
		self.tabWidget.currentWidget().setFocus()
		self.contentsChanged.emit()
		
	def tabTitleChanged(self, title):
		tab = self.sender()
		self.setTabTitle(tab, title)
		if tab == self.tabWidget.currentWidget():
			self.updateWindowTitle()

		# Assume that the open files have changed
		self.contentsChanged.emit()
		
	def tabModificationChanged(self, modified):
		# Indicate whether or not a tab is modified by the color of its label
		index = self.getTabIndex(self.sender())
		color = Qt.darkGray if modified else Qt.black
		self.tabWidget.tabBar().setTabTextColor(index, color)
		
	def open_file(self, filename=None):
		if filename is None:
			filename = str(QFileDialog.getOpenFileName(self))
		if len(filename) > 0:
			self.new_tab(filename)
			
	def getOpenFiles(self):
		"""Return a list of the full paths of all the files open in the window."""
		result = []
		for i in xrange(self.tabWidget.count()):
			result.append(self.getTab(i).path)
		return result
					
class SessionManager(QObject):
	def __init__(self):
		QObject.__init__(self)

		self.settings = QSettings(
			QSettings.IniFormat,
			QSettings.UserScope,
			"dubroy.com", 
			"kurt")
		self.configDirName = os.path.dirname(str(self.settings.fileName()))
		self.restoring = False
		
		# Figure out if the last session closed cleanly
		self.closed_cleanly = True
		if self.settings.contains("session/closed-cleanly"):
			self.closed_cleanly = self.settings.value("session/closed-cleanly").toPyObject()
		self.settings.setValue("session/closed-cleanly", False)
		
		self._pipeName = os.path.join(self.configDirName, "comm_pipe")
		try:
			listener = Listener(self._pipeName)
			thread.start_new_thread(self._listener_thread_main, (listener,))
		except socket.error, e:
			# If we get "Address already in use", than another process is running
			if e.errno != errno.EADDRINUSE:
				raise
			self._conn = Client(self._pipeName)
			self._conn.send("open foobar.txt")
			self._conn.close()
			sys.exit(0)

	def _listener_thread_main(self, listener):
		while True:
			conn = listener.accept()
			message = conn.recv()
			logging.debug("Listener received message '%s'" % message)
			parts = message.split(" ", 1)
			cmd = parts[0]
			if cmd == "quit":
				break
			elif cmd == "open":
				# Using a signal to pass the message to the UI thread
				self._remoteOpenReq.emit(parts[1])
			else:
				logging.warning("Listener received unrecognized command '%s'" % cmd)
		logging.debug("Exiting listener thread")
				
	def _shutdown_listener_thread(self):
		logging.debug("Attempting to shut down listener thread")
		conn = Client(self._pipeName)
		conn.send("quit")
		conn.close()
		
	def _openFromExternalProcess(self, filename):
		self.win.new_tab(filename)
		self.win.raise_()
	
	def set_window(self, win):
		self.win = win
		safe_connect(win.geometryChanged, self.geometryChanged)
		safe_connect(win.contentsChanged, self.saveTabs)
		safe_connect(win.windowClosed, self.windowClosed)
		safe_connect(self._remoteOpenReq, self._openFromExternalProcess)
		
	def geometryChanged(self):
		"""Saves the width, height, and position of the window."""
		if not self.restoring:
			self.settings.setValue("session/geometry", self.win.saveGeometry())
			
	def windowClosed(self, closed_cleanly):
		self.closed_cleanly = closed_cleanly
		self.settings.setValue("session/closed-cleanly", closed_cleanly)
			
	def saveTabs(self):
		"""Saves a list of all the files that are currently open in tabs."""
		if not self.restoring:
			paths = os.pathsep.join((x for x in self.win.getOpenFiles() if x is not None))
			self.settings.setValue("session/tabs", paths)

	def restoreTabs(self):
		self.restoring = True
		paths = str(self.settings.value("session/tabs").toPyObject())
		for path in paths.split(os.pathsep):
			self.win.open_file(path)
		self.restoring = False
		
	def restore_geometry(self):
		# Try to restore the previous settings
		if self.settings.contains("session/geometry"):
			self.win.restoreGeometry(self.settings.value("session/geometry").toByteArray())
		
	def restore_session(self):
		self.restore_geometry()
		self.restoreTabs()
		
	def shutDown(self):
		app = self.sender()
		self._shutdown_listener_thread()
		rc = 0 if self.closed_cleanly else 1
		app.exit(rc)
		
	_remoteOpenReq = pyqtSignal(str)
	
def start_editor(files=[], contents=[]):
	app = QApplication(sys.argv)
	# Create the session manager as early as possible, so we can properly
	# restore the state after a crash
	session_manager = SessionManager()
	win = MainWindow()
	session_manager.set_window(win)
	if not session_manager.closed_cleanly or len(files) == 0:
		session_manager.restore_session()
	else:
		session_manager.restore_geometry()
	for each in files:
		win.new_tab(filename=each)
	for each in contents:
		win.new_tab(contents=each)
	win.show()
	if MAC_OS:
		win.raise_()
	safe_connect(app.lastWindowClosed, session_manager.shutDown)
	return app.exec_()

if __name__== "__main__":
	file_args = sys.argv[1:]

	# On Mac OS, there is an extra arg with the process serial number
	# when we are launched from Finder. Just ignore it.
	if MAC_OS and len(sys.argv) > 1 and sys.argv[1].startswith("-psn_"):
		file_args.pop(0)

	start_editor(file_args)
