import inspect
import os
import shutil
import sys
import traceback

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class KeyFilter(QObject):

	SHORTCUTS = {
		("Control", "T"): lambda w, t: w.new_tab(),
		("Control", "O"): lambda w, t: w.open_file(),
		("Control", "S"): lambda w, t: t.save(),
		("Control", "W"): lambda w, t: t.close(),
		("Control", "R"): lambda w, t: w.reloadAndRestart(),
		("Control", "F"): lambda w, t: t.find()
	}

	def __init__(self, window, tab, *args):
		QObject.__init__(self, *args)
		self.window = window
		self.tab = tab
		self._handlers = {}
		
		# Map from our simplified shortcut representation to an internal one,
		# which will make it easier to look up handlers for Qt events
		for shortcut, handler in KeyFilter.SHORTCUTS.iteritems():
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
			
	def eventFilter(self, obj, event):
		if event.type() == QEvent.KeyPress and event.key() < 256:
			handler = self.get_handler(event.key(), event.modifiers())
			if handler:
				handler(self.window, self.tab)
				return True
		return QObject.eventFilter(self, obj, event)

class FindBar(QWidget):
	def __init__(self, textEdit, *args):
		QWidget.__init__(self, *args)
		self.textEdit = textEdit
		layout = QHBoxLayout()
		layout.setContentsMargins(4, 2, 4, 4)
		self.setLayout(layout)
		
		layout.addWidget(QLabel(text="Find:"))

		self.lineEdit = QLineEdit()
		layout.addWidget(self.lineEdit)
		
		self.lineEdit.installEventFilter(self)
		self.lineEdit.textEdited.connect(self._findText)
		self.setFocusProxy(self.lineEdit)
		
	def showEvent(self, event):
		self.lineEdit.selectAll()
		
	def eventFilter(self, obj, event):
		if (event.type() == QEvent.KeyPress
		and event.modifiers() == Qt.NoModifier):
			key = event.key()
			if key == Qt.Key_Escape:
				self._clearSelection()
				self.hide()
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

	def open(self, text=None):
		"""Basically just a synonym for show(), but allows the text to be set."""
		if text:
			self.lineEdit.setText(text)
		self._setBackground(found=True)
		self.show()
		self.setFocus()
			
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
		layout.setContentsMargins(0, 2, 0, 0)
		layout.setSpacing(0)
		self.setLayout(layout)

		self.textEdit = QTextEdit()
		doc = self.textEdit.document()
		doc.modificationChanged.connect(self.modificationChanged)
		doc.contentsChanged.connect(self._contentsChanged)

		# Config options
		self.textEdit.setStyleSheet("""
			QTextEdit {
				color: #eeeeee;
				background-color: #303030;
				font-family: Consolas, Courier, monospace;
				font-size: 10pt;
			}
		""")
		
		self.findBar = FindBar(self.textEdit)
		self.findBar.hide()
		layout.addWidget(self.findBar)

		layout.addWidget(self.textEdit)
		self.setFocusProxy(self.textEdit)
		
		self.keyFilter = KeyFilter(window, self)
		self.textEdit.installEventFilter(self.keyFilter)
		
		self._save_timer = QTimer(self)		
		self._save_timer.timeout.connect(self._saveTimeout)
		
	def showEvent(self, event):
		# Set the tab width to 4 chars (assuming monospace font)
		# If we do this in the constructor, it's not calculated correctly
		fontMetrics = self.textEdit.fontMetrics()
		self.textEdit.setTabStopWidth(fontMetrics.width("0000"))
	
	def _contentsChanged(self):
		# When the contents of the document change, save the document if no
		# more changes are made after 500 seconds have elapsed
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
		if os.path.exists(path):
			self.textEdit.setPlainText(open(path, "r").read())
			self.textEdit.document().setModified(False)
		self.path = path
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
		
	def close(self):
		self.window.close_tab(self)
		
class MainWindow(QMainWindow):

	# Emitted when the window is moved or resized
	geometryChanged = pyqtSignal()
	
	# Emitted when tabs are opened or closed, etc.
	contentsChanged = pyqtSignal()
	
	# Emitted when the window is closed (by user action)
	windowClosed = pyqtSignal()

	def __init__(self, *args):
		QMainWindow.__init__(self, *args)
		self.tabWidget = QTabWidget()
		self.tabWidget.setMovable(True)
		self.setCentralWidget(self.tabWidget)
		
		self.tabWidget.currentChanged.connect(self.tabSwitched)
		
	def showEvent(self, event):
		# If no tabs exist yet, create a default one
		if self.tabWidget.count() == 0:
			self.new_tab()
		QMainWindow.showEvent(self, event)
			
	def moveEvent(self, event):
		self.geometryChanged.emit()
		QMainWindow.moveEvent(self, event)
		
	def resizeEvent(self, event):
		self.geometryChanged.emit()
		QMainWindow.resizeEvent(self, event)

	def closeEvent(self, event):
		QMainWindow.closeEvent(self, event)
		
	def reloadAndRestart(self):
		self.currentTab().save()
		filename = inspect.getfile(inspect.currentframe())
		try:
			execfile(filename, {"__name__": "kurt"})
		except Exception as e:
			# If there's an error in the script, don't restart; just open
			# a new tab with the traceback
			self.new_tab(contents=traceback.format_exc())
		else:
			# Exit, and the calling script will restart the editor
			QApplication.exit(1)

	def currentTab(self):
		return self.tabWidget.currentWidget()
		
	def updateWindowTitle(self):
		path = self.tabWidget.currentWidget().path
		filename = os.path.basename(path) if path else "New File"
		self.setWindowTitle(filename + " - Kurt")

	def tabSwitched(self, index):
		self.updateWindowTitle()

	def new_tab(self, filename=None, contents=None):
		"""Open a new editor tab. If filename is specified, it will be loaded
		into the tab. Otherwise, if contents (a string) is specified, the
		editor text will be set to that.
		"""
		editor = Editor(self)
		editor.modificationChanged.connect(self.tabModificationChanged)
		editor.titleChanged.connect(self.tabTitleChanged)

		index = self.tabWidget.addTab(editor, editor.getTitle())

		if filename:
			editor.open_file(filename)
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
			
		self.restoring = False
		
		# Figure out if the last session closed cleanly
		self.closed_cleanly = True
		if self.settings.contains("session/closed-cleanly"):
			self.closed_cleanly = self.settings.value("session/closed-cleanly").toPyObject()
		self.settings.setValue("session/closed-cleanly", False)
	
	def set_window(self, win):
		win.geometryChanged.connect(self.geometryChanged)
		win.contentsChanged.connect(self.saveTabs)
		win.windowClosed.connect(self.windowClosed)
		self.win = win
		
	def geometryChanged(self):
		"""Saves the width, height, and position of the window."""
		if not self.restoring:
			self.settings.setValue("session/geometry", self.win.saveGeometry())

	def saveTabs(self):
		"""Saves a list of all the files that are currently open in tabs."""
		if not self.restoring:
			for i, filename in enumerate(self.win.getOpenFiles()):
				self.settings.setValue("session/tab%d" % i, filename)
			
	def windowClosed(self):
		self.settings.setValue("session/closed-cleanly", True)
			
	def restoreTabs(self):
		self.restoring = True
		self.settings.beginGroup("session")
		for key in self.settings.childKeys():
			if str(key).startswith("tab"):
				# The value returned is a QVariant, which requires some massaging
				val = self.settings.value(key).toPyObject()
				if val is not None:
					self.win.open_file(str(val))
				# When the tabs reach a high-water marks, some of the keys will
				# become stale. Remove all the tab keys to prevent this.
				self.settings.remove(key)
		self.settings.endGroup()
		self.restoring = False
		
	def restore_geometry(self):
		# Try to restore the previous settings
		if self.settings.contains("session/geometry"):
			self.win.restoreGeometry(self.settings.value("session/geometry").toByteArray())
		
	def restore_session(self):
		self.restore_geometry()
		self.restoreTabs()

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
	app.lastWindowClosed.connect(app.quit)
	return app.exec_()

if __name__== "__main__":
	start_editor(sys.argv[1:])
