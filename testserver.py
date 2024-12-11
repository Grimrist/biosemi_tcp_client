import numpy
import socket   # used for TCP/IP communication

import sys
from threading import Thread
from time import sleep

from PyQt6 import QtWidgets, QtCore, QtGui
from scipy import signal # Filtering
import pyqtgraph
from pglive.sources.data_connector import DataConnector
from pglive.sources.live_plot import LiveLinePlot
from pglive.sources.live_plot_widget import LivePlotWidget
from pglive.sources.live_axis_range import LiveAxisRange

DEBUG = True

# TCP/IP setup
TCP_IP = '127.0.0.1' # ActiView is running on the same PC
TCP_PORT = 8888 # This is the port ActiView listens on
CHANNELS = 32 # Amount of channels sent via TCP
SAMPLES = 64 # Samples per channel
EX_NODES = 8 # EX electrodes
BUFFER_SIZE = (CHANNELS+EX_NODES) * SAMPLES * 3 # Data packet size 
PHYS_MAX = 262143 # Physical maximum value 
PHYS_MIN = -262144 # Physical minimum value
DIGI_MAX = 8388607 # Digital maximum value
DIGI_MIN = -8388608 # Digital minimum value
ACTIVE_CHANNEL = 1 # Channel being measured

# Open socket
# s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# s.connect((TCP_IP, TCP_PORT))

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("QMainWindow { background-color: #263238; color: #ffffff }"
                           "QFrame { background-color: #37474F; color: #ffffff }"
                           "QCheckBox { color: #ffffff }"
                           "QCheckBox::indicator::unchecked { background-color: #CFD8DC }"
                           "QCheckBox::indicator::checked { background-color: #B0BEC5; border-image: url(./check.svg)}"
                           "QLineEdit { background-color: #CFD8DC }"
                           "QScrollBar:vertical { background: #CFD8DC }"
                           "QSpinBox { background: #CFD8DC }"
                           "QListView::item:selected { background: #546E7A }"
                           "QListView::item:selected:!active { }"
                           "QPushButton { background: #CFD8DC }")
        # Initialize main window
        self.setWindowTitle("Biosemi TCP Reader")
        main_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QHBoxLayout()
        self.initialize_models()

        # Initialize selection window and graph display window
        selection_window = SelectionWindow(self.electrodes_model)
        selection_window.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        graph_window = GraphWindow(self.electrodes_model)

        # Add to layout and attach to main window
        main_layout.addWidget(selection_window)
        main_layout.addWidget(graph_window)
        main_widget.setLayout(main_layout)

        ## Connect events
        # Connection settings
        selection_window.ip_box.textChanged.connect(graph_window.setIP)
        selection_window.port_box.textChanged.connect(graph_window.setPort)

        # Graph control
        selection_window.channel_selector.selectionModel().selectionChanged.connect(graph_window.setActiveChannels)
        selection_window.reference_selector.selectionModel().selectionChanged.connect(graph_window.setReference)

        selection_window.start_button.clicked.connect(graph_window.startCapture)
        selection_window.stop_button.clicked.connect(graph_window.stopCapture)
        # Show window
        self.setCentralWidget(main_widget)
        self.show()

    def initialize_models(self):
        # Initialize 32 A Electrodes
        electrodesA = QtGui.QStandardItemModel(32,3)
        for i in range(32):
            name = QtGui.QStandardItem("A" + str(i+1))
            electrodesA.setItem(i,0,name)
            status = QtGui.QStandardItem()
            status.setData(QtCore.QVariant(False))
            electrodesA.setItem(i,1,status)

        # Initialize 32 B Electrodes
        electrodesB = QtGui.QStandardItemModel(32,3)
        for i in range(32):
            name = QtGui.QStandardItem("B" + str(i+1))
            electrodesB.setItem(i,0,name)
            status = QtGui.QStandardItem()
            status.setData(QtCore.QVariant(False))
            electrodesB.setItem(i,1,status)

        # Initialize 8 EX Electrodes
        electrodesEX = QtGui.QStandardItemModel(8,3)
        for i in range(8):
            name = QtGui.QStandardItem("EX" + str(i+1))
            electrodesEX.setItem(i,0,name)
            status = QtGui.QStandardItem()
            status.setData(QtCore.QVariant(False))
            electrodesEX.setItem(i,1,status)
        self.electrodes_model = [electrodesA, electrodesB, electrodesEX]

class SelectionWindow(QtWidgets.QWidget):
    def __init__(self, electrodes_model):
        super().__init__()

        selection_layout = QtWidgets.QVBoxLayout()

        # Connection settings
        connection_frame = QtWidgets.QFrame()
        connection_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)
        connection_layout = QtWidgets.QFormLayout()
        self.ip_box = QtWidgets.QLineEdit()
        self.ip_box.setText(TCP_IP)
        self.port_box = QtWidgets.QLineEdit()
        self.port_box.setText(str(TCP_PORT))
        connection_layout.addRow(QtWidgets.QLabel("IP"), self.ip_box)
        connection_layout.addRow(QtWidgets.QLabel("Port"), self.port_box)
        selection_layout.addWidget(connection_frame)
        connection_frame.setLayout(connection_layout)

        verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        selection_layout.addItem(verticalSpacer) 
        
        # Channel selection
        channel_frame = QtWidgets.QFrame()
        channel_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)
        channel_layout = QtWidgets.QVBoxLayout()
        channel_layout.addWidget(QtWidgets.QLabel("Active Channels"))
        self.channel_selector = QtWidgets.QListView()
        self.channel_selector.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.channel_selector.setModel(electrodes_model[0])
        self.channel_selector.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        channel_layout.addWidget(self.channel_selector)
        channel_frame.setLayout(channel_layout)
        selection_layout.addWidget(channel_frame)

        verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        selection_layout.addItem(verticalSpacer) 

        # Reference selection
        reference_frame = QtWidgets.QFrame()
        reference_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)

        reference_layout = QtWidgets.QVBoxLayout()

        reference_layout.addWidget(QtWidgets.QLabel("Reference Channel"))
        self.reference_selector = SingleSelectQListView()
        self.reference_selector.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.reference_selector.setModel(electrodes_model[0])
        self.reference_selector.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        reference_layout.addWidget(self.reference_selector)
        reference_frame.setLayout(reference_layout)
        selection_layout.addWidget(reference_frame)

        verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        selection_layout.addItem(verticalSpacer) 

        # Filter settings (FIR)
        filter_frame = QtWidgets.QFrame()
        filter_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)
        filter_layout = QtWidgets.QVBoxLayout()
        self.filter_checkbox = QtWidgets.QCheckBox("Filtering")
        filter_layout.addWidget(self.filter_checkbox)

        filter_settings = QtWidgets.QWidget()
        filter_settings_layout = QtWidgets.QFormLayout()
        self.lowpass_box = QtWidgets.QSpinBox()
        self.lowpass_box.setValue(1)
        self.highpass_box = QtWidgets.QSpinBox()
        self.highpass_box.setValue(1)
        filter_settings_layout.addRow(QtWidgets.QLabel("Low pass FIR Filter Cut-off [Hz]"), self.lowpass_box)
        filter_settings_layout.addRow(QtWidgets.QLabel("High pass FIR Filter Cut-off [Hz]"), self.highpass_box)
        filter_layout.addWidget(filter_settings)

        filter_settings.setLayout(filter_settings_layout)
        filter_frame.setLayout(filter_layout)
        selection_layout.addWidget(filter_frame)

        verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        selection_layout.addItem(verticalSpacer) 


        # Control buttons
        button_widget = QtWidgets.QWidget()
        button_layout = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("Start")
        self.stop_button = QtWidgets.QPushButton("Stop")
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_widget.setLayout(button_layout)
        selection_layout.addWidget(button_widget)

        self.setLayout(selection_layout)

class GraphWindow(QtWidgets.QWidget):
    def __init__(self, electrodes_model):
        super().__init__()
        self.ip = TCP_IP
        self.port = TCP_PORT
        self.is_capturing = False
        self.electrodes_model = electrodes_model
        self.graph_layout = QtWidgets.QVBoxLayout()
        # , y_range_controller=LiveAxisRange(fixed_range=[-100, 100])
        self.plot_widget = LivePlotWidget(title="EEG Channels @ 30Hz")
        self.graph_layout.addWidget(self.plot_widget)
        self.setLayout(self.graph_layout)
        
    def setActiveChannels(self, selection):
        for i in range(self.electrodes_model[0].rowCount()):
            idx = self.electrodes_model[0].index(i, 1)
            self.electrodes_model[0].itemFromIndex(idx).setData(QtCore.QVariant(False))
        
        for i in selection.indexes():
            self.electrodes_model[0].itemFromIndex(i.siblingAtColumn(1)).setData(QtCore.QVariant(True))

    def setReference(self, selection):
        for i in range(self.electrodes_model[0].rowCount()):
            idx = self.electrodes_model[0].index(i, 2)
            self.electrodes_model[0].itemFromIndex(idx).setData(QtCore.QVariant(False))
        
        for i in selection.indexes():
            self.electrodes_model[0].itemFromIndex(i.siblingAtColumn(2)).setData(QtCore.QVariant(True))

    # Something is going horribly wrong every time we restart,
    # so we just go nuclear: delete everything and rebuild.
    def startCapture(self):
        if self.is_capturing:
            self.stopCapture()
        if not DEBUG:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.ip, self.port))
        self.data_connectors = []
        self.plots = []
        for i in range(32):
            plot = LiveLinePlot(pen=pyqtgraph.hsvColor(i/32, 0.8, 0.9))
            self.data_connectors.append(DataConnector(plot, max_points=150, plot_rate=30))
            self.plots.append(plot)
            self.plot_widget.addItem(plot)
        self.is_capturing = True
        self.data_thread = Thread(target=self.readData, args=(self.electrodes_model, self.data_connectors))
        self.data_thread.start()
        print("Reading from ip %s and port %s" % (self.ip, self.port))
    def stopCapture(self):
        if not self.is_capturing:
            return
        self.is_capturing = False
        for plot in self.plots:
            plot.deleteLater()
        for connector in self.data_connectors:
            connector.deleteLater()
        self.plot_widget.deleteLater()
        self.plot_widget = LivePlotWidget(title="EEG Channels @ 30Hz")
        self.graph_layout.addWidget(self.plot_widget)
        self.data_thread.join()
        if not DEBUG:
            self.sock.close()        


    ##  TCP packet format (2 channels example). Each sample is 24-bits, little-endian.
    ##  To convert to a 32-bit integer, we add a 0-byte to the LSB before converting to big-endian.
    ##  ╔══════╗╔══════╗╔══════╗ ╔══════╗╔══════╗╔══════╗ ╔══════╗╔══════╗╔══════╗ ╔══════╗╔══════╗╔══════╗
    ##  ║ C1S1 ║║ C1S1 ║║ C1S1 ║ ║ C2S1 ║║ C2S1 ║║ C2S1 ║ ║ C1S2 ║║ C1S2 ║║ C1S2 ║ ║ C2S2 ║║ C2S2 ║║ C2S2 ║
    ##  ║  B1  ║║  B2  ║║  B3  ║ ║  B1  ║║  B2  ║║  B3  ║ ║  B1  ║║  B2  ║║  B3  ║ ║  B1  ║║  B2  ║║  B3  ║
    ##  ╚══════╝╚══════╝╚══════╝ ╚══════╝╚══════╝╚══════╝ ╚══════╝╚══════╝╚══════╝ ╚══════╝╚══════╝╚══════╝
    ##  
    ##  
    def readData(self, electrodes_model, data_connectors):
        x = 0
        # Apply gain based on physical max/min and digital max/min
        gain = (PHYS_MAX - PHYS_MIN)/(DIGI_MAX - DIGI_MIN)
        total_channels = (CHANNELS+EX_NODES)
        active_channels = []
        active_reference = -1
        model = electrodes_model[0]

        for i in range(model.rowCount()):
            # Select active channels
            idx = model.index(i,1)
            if model.itemFromIndex(idx).data():
                active_channels.append(i)
            # Select reference point
            idx = model.index(i,2)
            if model.itemFromIndex(idx).data():
                active_reference = i

        while True:
            if DEBUG:
                rng = numpy.random.default_rng()
                data = rng.bytes(BUFFER_SIZE)
            else:
                # Read the next packet from the network
                data = self.sock.recv(BUFFER_SIZE)

            # Extract all channel samples from the packet
            for m in range(SAMPLES):
                # To increase CMRR, we can pick a reference point and subtract it from every other point we are reading
                ref_offset = (m * 3 * total_channels) + (active_reference*3)
                sample = bytearray(1)
                sample.append(data[ref_offset])
                sample.append(data[ref_offset+1])
                sample.append(data[ref_offset+2])
                ref_value = int.from_bytes(sample, byteorder='little', signed=True)
                for n in active_channels:
                    # Samples are sent in bulk of size SAMPLES, interleaved such that
                    # the first sample of each channel is sent, then the second sample,
                    # and so on.
                    offset = (m * 3 * total_channels) + (n*3)
                    # The 3 bytes of each sample arrive in reverse order (little endian).
                    # We convert them to a 32bit integer by appending the bytes together,
                    # and adding a zero byte as LSB.
                    sample = bytearray(1)
                    sample.append(data[offset])
                    sample.append(data[offset+1])
                    sample.append(data[offset+2])
                    value = int.from_bytes(sample, byteorder='little', signed=True)
                    # # Send sample to plot
                    data_connectors[n].cb_append_data_point((value - ref_value)*gain, x)

                if not self.is_capturing:
                    return
                x += 1
                if DEBUG:
                    sleep(0.05)

    #def filter_data(self, data):


    def setIP(self, ip):
        self.ip = ip
    
    def setPort(self, port):
        self.port = int(port)

class SingleSelectQListView(QtWidgets.QListView):
    def __init__(self):
        super().__init__()
    
    def mousePressEvent(self, event):
        if self.indexAt(event.pos()) in self.selectedIndexes():
            self.clearSelection()
        else:
            super(SingleSelectQListView, self).mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.mousePressEvent(event)

app = QtWidgets.QApplication(sys.argv)
window = MainWindow()
sys.exit(app.exec())