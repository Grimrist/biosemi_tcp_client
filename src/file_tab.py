from PyQt6 import QtCore, QtWidgets, QtGui

class FileTab(QtWidgets.QWidget):
    directoryChanged = QtCore.pyqtSignal(str)
    activeFileChanged = QtCore.pyqtSignal(str)
    doubleClickedFile = QtCore.pyqtSignal()

    def __init__(self, settings):
        super().__init__()
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        ## Initialize file system model and view
        self.file_system = QtGui.QFileSystemModel()
        self.file_system.setRootPath('/')
        self.file_view = QtWidgets.QTreeView()
        self.file_view.setModel(self.file_system)
        self.file_view.setSortingEnabled(True)
        if settings['file']['directory']:
            self.file_view.setRootIndex(self.file_system.index(settings['file']['directory']))
        if settings['file']['current_file']:
            self.file_view.setCurrentIndex(self.file_system.index(settings['file']['current_file']))
        
        # Connect our file view to notify when the file changes
        self.file_view.clicked.connect(self.notifyFileChange)
        self.file_view.doubleClicked.connect(self.startFileDisplay)

        self.start_button = QtWidgets.QPushButton("Browse")
        self.start_button.clicked.connect(self.displayFileBrowser)
        self.file_dialog = QtWidgets.QFileDialog()
        layout.addWidget(self.start_button)
        layout.addWidget(self.file_view)        

    # This needs to handle switching drives so that it doesn't break the sorting function
    # From what I understand, that means changing the RootPath variable (eg from C: to D:)
    def displayFileBrowser(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(options=QtWidgets.QFileDialog.Option.ShowDirsOnly)
        self.file_view.setRootIndex(self.file_system.index(directory))
        self.directoryChanged.emit(directory)
    
    def notifyFileChange(self, index):
        file = self.file_system.filePath(index)
        self.activeFileChanged.emit(file)
        print(file)
        
    def startFileDisplay(self, index):
        self.notifyFileChange(index)
        self.doubleClickedFile.emit()