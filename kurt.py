import os
import shutil
import sys

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# Keep a list of the files that are open. This should remain synchronized
# with the tab state. Mostly used for debugging, so we can restore the state.
class _EditorState:
	pass
state = _EditorState()
state.open_files = []
state.current_tab_index = -1

class KeyFilter(QObject):

	SHORTCUTS = {
		("Control", "T"): lambda w, t: w.new_tab(),
		("Control", "O"): lambda w, t: w.open_file(),
		("Control", "S"): lambda w, t: t.save(),
		("Control", "W"): lambda w, t: t.close(),
		("Control", "R"): lambda w, t: w.close()
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
		
class EditorTab(QWidget):

	# Emitted when the title of the tab has changed
	titleChanged = pyqtSignal(str)
	
	# Emitted when the document modification state has changed
	modificationChanged = pyqtSignal(bool)

	def __init__(self, window, *args):
		QWidget.__init__(self, *args)
		
		self.window = window
		self.path = None # Path to the file that is open in this tab
		
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
		
		layout = QVBoxLayout()
		layout.setContentsMargins(0, 2, 0, 0)
		self.setLayout(layout)
		layout.addWidget(self.textEdit)
		self.setFocusProxy(self.textEdit)
		
		self.keyFilter = KeyFilter(window, self)
		self.setEventFilter(self.keyFilter)
		
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
		
	def close(self):
		self.window.close_tab(self)
		
	def setEventFilter(self, filter):
		self.textEdit.installEventFilter(filter)	

class MainWindow(QMainWindow):
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

	def close(self):
		self.currentTab().save()
		QApplication.exit(1)

	def currentTab(self):
		return self.tabWidget.currentWidget()
		
	def updateWindowTitle(self):
		path = self.tabWidget.currentWidget().path
		filename = os.path.basename(path) if path else "New File"
		self.setWindowTitle(filename + " - Kurt")

	def tabSwitched(self, index):
		self.updateWindowTitle()

		# Maintain global editor state, for restoring the session
		state.current_tab_index = index
		if len(state.open_files) == index:
			state.open_files.append(None)

	def new_tab(self, filename=None):
		editorTab = EditorTab(self)
		editorTab.modificationChanged.connect(self.tabModificationChanged)
		editorTab.titleChanged.connect(self.tabTitleChanged)

		index = self.tabWidget.addTab(editorTab, editorTab.getTitle())

		if filename:
			editorTab.open_file(filename)
		self.tabWidget.setCurrentIndex(index) # Switch to the new tab
		editorTab.setFocus()
		return editorTab

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
		
	def tabTitleChanged(self, title):
		tab = self.sender()
		self.setTabTitle(tab, title)
		if tab == self.tabWidget.currentWidget():
			self.updateWindowTitle()
		
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
			state.open_files[state.current_tab_index] = filename

def backup_filename(path):
	return path + ".bak"
		
def start_editor(files):
	app = QApplication(sys.argv)
	win = MainWindow()
	for each in files:
		win.open_file(each)
	# 624 is half the screen width on a 13" MacBook running Windows 7
	win.resize(624, 600)
	win.show()
	app.lastWindowClosed.connect(app.quit)
	return app.exec_()

if __name__== "__main__":
	start_editor(sys.argv[1:])
