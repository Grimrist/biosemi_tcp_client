import numpy
import socket   # used for TCP/IP communication

import sys
from threading import Thread
from time import sleep

from PyQt6 import QtWidgets, QtCore, QtGui

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

        # Initialize main window
        self.setWindowTitle("Biosemi TCP Reader")
        self.main_widget = QtWidgets.QWidget()
        self.main_layout = QtWidgets.QHBoxLayout()
        self.initialize_models()

        # Initialize selection window and graph display window
        self.selection_window = SelectionWindow(self.electrodes_model)
        self.graph_window = GraphWindow(self.electrodes_model)

        # Add to layout and attach to main window
        self.main_layout.addWidget(self.selection_window)
        self.main_layout.addWidget(self.graph_window)
        self.main_widget.setLayout(self.main_layout)

        ## Connect events
        # Connection settings
        self.selection_window.ip_box.textChanged.connect(self.graph_window.setIP)
        self.selection_window.port_box.textChanged.connect(self.graph_window.setPort)

        # Graph control
        self.selection_window.channel_selector.selectionModel().selectionChanged.connect(self.graph_window.setActiveChannels)
        self.selection_window.start_button.clicked.connect(self.graph_window.startCapture)
        self.selection_window.stop_button.clicked.connect(self.graph_window.stopCapture)
        # Show window
        self.setCentralWidget(self.main_widget)
        self.show()

    def initialize_models(self):
        # Initialize 32 A Electrodes
        electrodesA = QtGui.QStandardItemModel(32,2)
        for i in range(32):
            name = QtGui.QStandardItem("A" + str(i+1))
            electrodesA.setItem(i,0,name)
            status = QtGui.QStandardItem()
            status.setData(QtCore.QVariant(False))
            electrodesA.setItem(i,1,status)

        # Initialize 32 B Electrodes
        electrodesB = QtGui.QStandardItemModel(32,2)
        for i in range(32):
            name = QtGui.QStandardItem("B" + str(i+1))
            electrodesB.setItem(i,0,name)
            status = QtGui.QStandardItem()
            status.setData(QtCore.QVariant(False))
            electrodesB.setItem(i,1,status)

        # Initialize 8 EX Electrodes
        electrodesEX = QtGui.QStandardItemModel(8,2)
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

        self.selection_layout = QtWidgets.QVBoxLayout()

        # Connection settings
        self.connection_settings = QtWidgets.QFrame()
        connection_layout = QtWidgets.QFormLayout()
        self.ip_box = QtWidgets.QLineEdit()
        self.ip_box.setText(TCP_IP)
        self.port_box = QtWidgets.QLineEdit()
        self.port_box.setText(str(TCP_PORT))
        connection_layout.addRow(QtWidgets.QLabel("IP"), self.ip_box)
        connection_layout.addRow(QtWidgets.QLabel("Port"), self.port_box)
        self.selection_layout.addWidget(self.connection_settings)
        self.connection_settings.setLayout(connection_layout)

        verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        self.selection_layout.addItem(verticalSpacer) 
        
        # Channel selection
        self.channel_selector = QtWidgets.QListView()
        self.channel_selector.setModel(electrodes_model[0])
        self.channel_selector.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.selection_layout.addWidget(self.channel_selector)

        verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        self.selection_layout.addItem(verticalSpacer) 

        # Control buttons
        self.button_widget = QtWidgets.QWidget()
        self.button_layout = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("Start")
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.button_layout.addWidget(self.start_button)
        self.button_layout.addWidget(self.stop_button)
        self.button_widget.setLayout(self.button_layout)
        self.selection_layout.addWidget(self.button_widget)

        self.setLayout(self.selection_layout)

class GraphWindow(QtWidgets.QWidget):
    def __init__(self, electrodes_model):
        super().__init__()
        self.ip = TCP_IP
        self.port = TCP_PORT
        self.is_capturing = False
        self.electrodes_model = electrodes_model
        self.graph_layout = QtWidgets.QVBoxLayout()
        # , y_range_controller=LiveAxisRange(fixed_range=[-100, 100])
        self.plot_widget = LivePlotWidget(title="Line Plot @ 100Hz")
        self.graph_layout.addWidget(self.plot_widget)
        self.setLayout(self.graph_layout)
        
    def setActiveChannels(self, selection):
        for i in range(self.electrodes_model[0].rowCount()):
            idx = self.electrodes_model[0].index(i, 1)
            self.electrodes_model[0].itemFromIndex(idx).setData(QtCore.QVariant(False))
        
        for i in selection.indexes():
            self.electrodes_model[0].itemFromIndex(i.siblingAtColumn(1)).setData(QtCore.QVariant(True))
            
        # print("Stored bools")
        # for i in range(self.electrodes_model[0].rowCount()):
        #     idx = self.electrodes_model[0].index(i, 1)
            
        #     print(self.electrodes_model[0].itemFromIndex(idx).data())
        # print("======")

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

    def readData(self, electrodes_model, data_connectors):
        x = 0
        # Apply gain based on physical max/min and digital max/min
        gain = (PHYS_MAX - PHYS_MIN)/(DIGI_MAX - DIGI_MIN)
        total_data = CHANNELS+EX_NODES
        active_channels = []
        model = electrodes_model[0]
        for i in range(model.rowCount()):
            idx = model.index(i,1)
            if model.itemFromIndex(idx).data():
                active_channels.append(i)
        while True:
            if not DEBUG:
                # Read the next packet from the network
                data = self.sock.recv(BUFFER_SIZE)
            # Extract all channel samples from the packet
            for m in range(total_data):
                for n in active_channels:
                    if DEBUG:
                        rng = numpy.random.default_rng()
                        value = rng.random()
                    else:
                        # Samples are sent in bulk of size SAMPLES, interleaved such that
                        # the first sample of each channel is sent, then the second sample,
                        # and so on.
                        offset = (m * 3 * total_data) + (n*3)
                        # The 3 bytes of each sample arrive in reverse order (little endian).
                        # We convert them to a 32bit integer by appending the bytes together,
                        # and adding a zero byte as LSB.
                        sample = bytearray(1)
                        sample.append(data[offset])
                        sample.append(data[offset+1])
                        sample.append(data[offset+2])
                        value = int.from_bytes(sample, byteorder='little', signed=True)

                    # # Send sample to plot
                    data_connectors[n].cb_append_data_point(value*gain, x)
                if not self.is_capturing:
                    return
                x += 1
                sleep(0.05)
            
    def setIP(self, ip):
        self.ip = ip
    
    def setPort(self, port):
        self.port = int(port)

app = QtWidgets.QApplication(sys.argv)
window = MainWindow()
sys.exit(app.exec())