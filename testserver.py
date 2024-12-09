import numpy    # Used to calculate DFT
import socket   # used for TCP/IP communication

import sys
from threading import Thread
from time import sleep

from PyQt6.QtWidgets import QApplication

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
PHYS_MAX = 262143
PHYS_MIN = -262144
DIGI_MAX = 8388607
DIGI_MIN = -8388608

# Open socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((TCP_IP, TCP_PORT))

# pgplot example
app = QApplication(sys.argv)
# , y_range_controller=LiveAxisRange(fixed_range=[-100, 100])
plot_widget = LivePlotWidget(title="Line Plot @ 100Hz")
plot_curve = LiveLinePlot()
plot_curve
plot_widget.addItem(plot_curve)
# DataConnector holding 600 points and plots @ 100Hz
data_connector = DataConnector(plot_curve, max_points=600, update_rate=100)

def readData(connector):
    x = 0
    while True:
        # Read the next packet from the network
        data = s.recv(BUFFER_SIZE)
        # Extract all channel samples from the packet
        for m in range(SAMPLES):
            offset = (m * 3 * (CHANNELS+EX_NODES))
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
        
plot_widget.show()
# Start sin_wave_generator in new Thread and send data to data_connector
Thread(target=readData, args=(data_connector,)).start()
app.exec()
