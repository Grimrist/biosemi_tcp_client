import numpy    # Used to calculate DFT
import socket   # used for TCP/IP communication

import sys
from threading import Thread
from time import sleep

from PyQt6 import QtWidgets, QtCore, QtGui

from pglive.sources.data_connector import DataConnector
from pglive.sources.live_plot import LiveLinePlot
from pglive.sources.live_plot_widget import LivePlotWidget
from pglive.sources.live_axis_range import LiveAxisRange

# TCP/IP setup
TCP_IP = '127.0.0.1' # ActiView is running on the same PC
TCP_PORT = 8888       # This is the port ActiView listens on
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

        # Initialize selection window and graph display window
        self.selection_window = SelectionWindow()
        self.graph_window = GraphWindow()

        # Add to layout and attach to main window
        self.main_layout.addWidget(self.selection_window)
        self.main_layout.addWidget(self.graph_window)
        self.main_widget.setLayout(self.main_layout)

        # Connect events? I genuinely don't know if I'm just doing this wrong, but this is horrible
        self.selection_window.channel_selector.currentIndexChanged.connect(self.graph_window.setCurrentChannel)

        # Show window
        self.setCentralWidget(self.main_widget)
        self.show()

class SelectionWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.selection_layout = QtWidgets.QVBoxLayout()

        # Channel selection
        self.channel_selector = QtWidgets.QComboBox()
        for i in range(CHANNELS):

            self.channel_selector.addItem("Channel " + str(i+1))
        
        self.selection_layout.addWidget(self.channel_selector)

        self.verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        self.selection_layout.addItem(self.verticalSpacer) 
        self.setLayout(self.selection_layout)

class GraphWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.graph_layout = QtWidgets.QVBoxLayout()
        # , y_range_controller=LiveAxisRange(fixed_range=[-100, 100])
        self.plot_widget = LivePlotWidget(title="Line Plot @ 100Hz")
        self.plot_curve = LiveLinePlot()
        self.plot_widget.addItem(self.plot_curve)
        self.current_channel = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((TCP_IP, TCP_PORT))
        self.data_connector = DataConnector(self.plot_curve, max_points=600, update_rate=100)
        self.data_thread = Thread(target=self.readData, args=(self.data_connector,)).start()
        self.graph_layout.addWidget(self.plot_widget)
        self.setLayout(self.graph_layout)

    def setCurrentChannel(self, channel):
        self.current_channel = channel

    def readData(self, connector):
        x = 0
        while True:
            # Read the next packet from the network
            data = s.recv(BUFFER_SIZE)
            # Extract all channel samples from the packet
            for m in range(SAMPLES):
                offset = (m * 3 * (CHANNELS+EX_NODES)) + self.current_channel
                # The 3 bytes of each sample arrive in reverse order (little endian)
                # We convert them to a 32bit integer via bytearray extending
                # According to documentation, we add a zero byte as LSB
                sample = bytearray(1)
                sample.append(data[offset])
                sample.append(data[offset+1])
                sample.append(data[offset+2])
                value = int.from_bytes(sample, byteorder='little', signed=True)

                # Apply gain based on physical max/min and digital max/min
                gain = (PHYS_MAX - PHYS_MIN)/(DIGI_MAX - DIGI_MIN)
                # Send sample to plot
                connector.cb_append_data_point(value*gain, x)
                x += 1
            global data_stopped
            if data_stopped:
                break
app = QtWidgets.QApplication(sys.argv)
window = MainWindow()

# Start sin_wave_generator in new Thread and send data to data_connector
# data_thread = Thread(target=readData, args=(data_connector,)).start()
#data_stopped = True
#data_thread.join()
sys.exit(app.exec())