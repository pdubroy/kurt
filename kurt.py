import os
import sys

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class KeyFilter(QObject):

	SHORTCUTS = {
		("Control", "T"): lambda w, t: w.new_tab(),
		("Control", "S"): lambda w, t: t.save(),
		("Control", "W"): lambda w, t: t.close()
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
		return QObject.eventFilter(self, obj, event)
		
class EditorTab(QWidget):
	def __init__(self, window, *args):
		QWidget.__init__(self, *args)
		
		self.window = window
		self.path = None
		
		self.textEdit = QTextEdit()
		self.connect(self.textEdit.document(), SIGNAL("modificationChanged(bool)"), self.modified)

		# Config options
		self.textEdit.setStyleSheet("""
			color: #eeeeee;
			background-color: #303030;
			font-family: Consolas, Courier, monospace;
			font-size: 10pt;
		""")
		
		layout = QVBoxLayout()
		layout.setContentsMargins(0, 2, 0, 0)
		self.setLayout(layout)
		layout.addWidget(self.textEdit)
		self.setFocusProxy(self.textEdit)
		
		self.keyFilter = KeyFilter(window, self)
		self.setEventFilter(self.keyFilter)
		
	def modified(self, modified):
		self.window.tab_modified(self, modified)
		
	def isModified(self):
		return self.textEdit.document().isModified()
		
	def open_file(self, path):
		if os.path.exists(path):
			self.textEdit.setPlainText(open(path, "r").read())
			self.textEdit.document().setModified(False)
		filename = os.path.basename(path)
		self.window.set_tab_title(self, filename)
		self.path = path

	def save(self):
		if self.path is None:
			self.path = str(QFileDialog.getSaveFileName(self.window))

			# If the user didn't select a file, abort the save operation
			if len(self.path) == 0:
				self.path = None
				return

		# Rename the original file, if it exists
		overwrite = os.path.exists(self.path)
		if overwrite:
			temp_path = self.path + "~"
			if os.path.exists(temp_path):
				os.remove(temp_path)
			os.rename(self.path, temp_path)

		# Save the new contents
		with open(self.path, "w") as f:
			f.write(self.textEdit.document().toPlainText())

		if overwrite:
			os.remove(temp_path)
		self.window.set_tab_title(self, os.path.basename(self.path))
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
		
		self.connect(self.tabWidget, SIGNAL("currentChanged(int)"), self.tabSwitched)
		
	def showEvent(self, event):
		# If no tabs exist yet, create a default one
		if self.tabWidget.count() == 0:
			self.new_tab()

	def updateWindowTitle(self):
		path = self.tabWidget.currentWidget().path
		filename = os.path.basename(path) if path else "New File"
		self.setWindowTitle(filename + "[*] - Kurt")

	def tabSwitched(self, index):
		self.setWindowModified(self.tabWidget.currentWidget().isModified())
		self.updateWindowTitle()

	def new_tab(self, title="New File"):	
		editorTab = EditorTab(self)
		index = self.tabWidget.addTab(editorTab, title)
		self.tabWidget.setCurrentIndex(index) # Switch to the new tab
		editorTab.setFocus()
		return editorTab
		
	def close_tab(self, tab):
		self.tabWidget.removeTab(self.tabWidget.indexOf(tab))
		self.tabWidget.currentWidget().setFocus()
		
	def set_tab_title(self, tab, title):
		self.tabWidget.setTabText(self.tabWidget.indexOf(tab), title)
		
	def tab_modified(self, tab, modified):
		index = self.tabWidget.indexOf(tab)
		color = Qt.darkGray if modified else Qt.black
		self.tabWidget.tabBar().setTabTextColor(index, color)
		self.setWindowModified(modified)
		
	def open_file(self, filename):
		self.new_tab().open_file(filename)
		
if __name__== "__main__":
	app = QApplication(sys.argv)
	win = MainWindow()
	for each in sys.argv[1:]:
		win.open_file(each)
	# 624x722 is exactly half the screen on a 13" MacBook running Windows 7
	win.resize(624, 600)
	win.show()
	app.connect(app, SIGNAL("lastWindowClosed()"), app, SLOT("quit()"))
	app.exec_()
