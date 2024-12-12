import numpy
import socket   # used for TCP/IP communication
from settings import SettingsHandler
import sys
from threading import Thread
from time import sleep
from collections import deque
from PyQt6 import QtWidgets, QtCore, QtGui
from scipy import signal # Filtering
import pyqtgraph
from pglive.sources.data_connector import DataConnector
from pglive.sources.live_plot import LiveLinePlot
from pglive.sources.live_plot_widget import LivePlotWidget
from pglive.sources.live_axis_range import LiveAxisRange

DEBUG = True

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

        # Load settings
        self.settings = {}
        self.settingsHandler = SettingsHandler("settings.json", self.settings)

        # Initialize main window
        self.setWindowTitle("Biosemi TCP Reader")
        main_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QHBoxLayout()
        self.initialize_models()

        # Initialize selection window and graph display window
        selection_window = SelectionWindow(self.settings, self.electrodes_model)
        selection_window.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        graph_window = GraphWindow(self.settings, self.electrodes_model)

        # Add to layout and attach to main window
        main_layout.addWidget(selection_window)
        main_layout.addWidget(graph_window)
        main_widget.setLayout(main_layout)

        ### Signal connections
        # Connection settings
        selection_window.ip_box.textChanged.connect(self.settingsHandler.setIp)
        selection_window.port_box.textChanged.connect(self.settingsHandler.setPort)
        selection_window.samples_box.textChanged.connect(self.settingsHandler.setSamples)
        selection_window.fs_box.textChanged.connect(self.settingsHandler.setFs)
        selection_window.channels_box.textChanged.connect(graph_window.setTotalChannels)

        # Graph control
        selection_window.channel_selector.selectionModel().selectionChanged.connect(graph_window.setActiveChannels)
        selection_window.reference_selector.selectionModel().selectionChanged.connect(graph_window.setReference)
        
        selection_window.start_button.clicked.connect(graph_window.startCapture)
        selection_window.stop_button.clicked.connect(graph_window.stopCapture)

        # FFT settings
        selection_window.welch_window_box.valueChanged.connect(self.settingsHandler.setWelchWindow)
        selection_window.fft_checkbox.checkStateChanged.connect(self.settingsHandler.setWelchEnabled)
        ###

        # Show window
        self.setCentralWidget(main_widget)
        self.show()

    def initialize_models(self):
        self.electrodes_model = None
        electrodes = QtGui.QStandardItemModel()
        for (group, number) in self.settings['biosemi']['channels']:
            for i in range(number):
                name = QtGui.QStandardItem(group + str(i+1))
                view_status = QtGui.QStandardItem()
                view_status.setData(QtCore.QVariant(False))
                ref_status = QtGui.QStandardItem()
                ref_status.setData(QtCore.QVariant(False))
                electrodes.appendRow([name, view_status, ref_status])
        self.electrodes_model = electrodes

class SelectionWindow(QtWidgets.QWidget):
    def __init__(self, settings, electrodes_model):
        super().__init__()
        self.settings = settings
        self.electrodes_model = electrodes_model
        selection_layout = QtWidgets.QVBoxLayout()

        # Connection settings
        connection_frame = QtWidgets.QFrame()
        connection_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)
        connection_layout = QtWidgets.QFormLayout()
        self.ip_box = QtWidgets.QLineEdit()
        self.ip_box.setText(self.settings['socket']['ip'])
        self.port_box = QtWidgets.QLineEdit()
        self.port_box.setText(str(self.settings['socket']['port']))
        self.channels_box = QtWidgets.QLineEdit()
        self.channels_box.setText(str(64 + 8))
        self.samples_box = QtWidgets.QLineEdit()
        self.samples_box.setText(str(self.settings['biosemi']['samples']))
        self.fs_box = QtWidgets.QLineEdit()
        self.fs_box.setText(str(16000))
        connection_layout.addRow(QtWidgets.QLabel("IP"), self.ip_box)
        connection_layout.addRow(QtWidgets.QLabel("Port"), self.port_box)
        connection_layout.addRow(QtWidgets.QLabel("Total Channels"), self.channels_box)
        connection_layout.addRow(QtWidgets.QLabel("Samples"), self.samples_box)
        connection_layout.addRow(QtWidgets.QLabel("Sampling rate [Hz]"), self.fs_box)
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
        self.channel_selector.setModel(electrodes_model)
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
        self.reference_selector.setModel(electrodes_model)
        self.reference_selector.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        reference_layout.addWidget(self.reference_selector)
        reference_frame.setLayout(reference_layout)
        selection_layout.addWidget(reference_frame)

        verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        selection_layout.addItem(verticalSpacer) 

        # FFT settings
        fft_frame = QtWidgets.QFrame()
        fft_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)
        fft_layout = QtWidgets.QVBoxLayout()
        self.fft_checkbox = QtWidgets.QCheckBox("FFT")
        fft_layout.addWidget(self.fft_checkbox)

        fft_settings = QtWidgets.QWidget()
        fft_settings_layout = QtWidgets.QFormLayout()
        self.welch_window_box = QtWidgets.QSpinBox()
        self.welch_window_box.setRange(0, 2**31-1)
        self.welch_window_box.setValue(self.settings['fft']['welch_window'])
        fft_settings_layout.addRow(QtWidgets.QLabel("Welch Window [samples]"), self.welch_window_box)
        fft_settings.setLayout(fft_settings_layout)

        fft_layout.addWidget(fft_settings)
        fft_frame.setLayout(fft_layout)
        selection_layout.addWidget(fft_frame)

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
    def __init__(self, settings, electrodes_model):
        super().__init__()
        self.settings = settings
        self.electrodes_model = electrodes_model
        self.welch_enabled = True
        self.is_capturing = False
        self.graph_layout = QtWidgets.QVBoxLayout()
        # , y_range_controller=LiveAxisRange(fixed_range=[-100, 100])
        self.plot_widget = LivePlotWidget(title="EEG Channels @ 30Hz")
        self.graph_layout.addWidget(self.plot_widget)
        self.setLayout(self.graph_layout)
        
    def setActiveChannels(self, selection):
        for i in range(self.electrodes_model.rowCount()):
            idx = self.electrodes_model.index(i, 1)
            self.electrodes_model.itemFromIndex(idx).setData(QtCore.QVariant(False))
        
        for i in selection.indexes():
            self.electrodes_model.itemFromIndex(i.siblingAtColumn(1)).setData(QtCore.QVariant(True))

    def setReference(self, selection):
        for i in range(self.electrodes_model.rowCount()):
            idx = self.electrodes_model.index(i, 2)
            self.electrodes_model.itemFromIndex(idx).setData(QtCore.QVariant(False))
        
        for i in selection.indexes():
            self.electrodes_model.itemFromIndex(i.siblingAtColumn(2)).setData(QtCore.QVariant(True))

    def setSamples(self, samples):
        self.samples = int(samples)

    def setSamplingRate(self, fs):
        self.fs = int(fs)

    def setTotalChannels(self, channels):
        self.total_channels = int(channels)

    def setWelchWindow(self, window):
        self.welch_window = int(window)
    
    def enableWelch(self, enable):
        self.welch_enabled = bool(enable)
    
    
    # Something is going horribly wrong every time we restart,
    # so we just go nuclear: delete everything and rebuild.
    def startCapture(self):
        if self.is_capturing:
            self.stopCapture()
        if not DEBUG:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.settings['socket']['ip'], self.settings['socket']['port']))
        total_channels = self.electrodes_model.rowCount()
        fs = self.settings['biosemi']['fs']
        self.data_connectors = []
        self.plots = []
        for i in range(total_channels-1):
            plot = LiveLinePlot(pen=pyqtgraph.hsvColor(i/(total_channels-1), 0.8, 0.9))
            self.data_connectors.append(DataConnector(plot, max_points=fs*10, plot_rate=30))
            self.plots.append(plot)
            self.plot_widget.addItem(plot)
        #for FFT
        for i in range(total_channels-1):
            plot = LiveLinePlot(pen=pyqtgraph.hsvColor(i/(total_channels-1), 0.8, 0.9))
            self.data_connectors.append(DataConnector(plot, plot_rate=30))
            self.plots.append(plot)
            self.plot_widget.addItem(plot)
        self.is_capturing = True
        self.data_thread = Thread(target=self.readData, args=(self.data_connectors,))
        self.data_thread.start()
        print("Reading from ip %s and port %s" % (self.settings['socket']['ip'], self.settings['socket']['port']))

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
    def readData(self, data_connectors):
        x = 0
        # Apply gain based on physical max/min and digital max/min
        phys_range = self.settings['biosemi']['phys_max'] - self.settings['biosemi']['phys_min']
        digi_range = self.settings['biosemi']['digi_max'] - self.settings['biosemi']['digi_min']
        # Pre-emptively fetch a few values that will be called very often
        samples = self.settings['biosemi']['samples']
        fs = self.settings['biosemi']['fs']
        total_channels = self.electrodes_model.rowCount()

        gain = phys_range/digi_range
        active_channels = []
        active_reference = -1
        welch_enabled = self.settings['fft']['welch_enabled']
        welch_buffer = deque(maxlen=self.settings['fft']['welch_window'])
        buffer_size = total_channels * self.settings['biosemi']['samples'] * 3
        for i in range(total_channels):
            # Select active channels
            idx = self.electrodes_model.index(i,1)
            if self.electrodes_model.itemFromIndex(idx).data(): 
                active_channels.append(i)
            # Select reference point
            idx = self.electrodes_model.index(i,2)
            if self.electrodes_model.itemFromIndex(idx).data():
                active_reference = i

        while True:
            if DEBUG:
                rng = numpy.random.default_rng()
                data = rng.bytes(buffer_size)
            else:
                # Read the next packet from the network
                data = self.sock.recv(buffer_size)

            # Extract all channel samples from the packet
            for m in range(samples):
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
                    welch_buffer.append(value)
                    
                    # # Send sample to plot
                    if welch_enabled:
                        if len(welch_buffer) == welch_buffer.maxlen:
                            f, pxx = signal.welch(x=welch_buffer, fs=fs)
                            self.data_connectors[n].cb_set_data(pxx, f)
                    else:
                        self.data_connectors[n].cb_append_data_point((value - ref_value)*gain, x)

                if not self.is_capturing:
                    return
                x += 1
                if DEBUG:
                    sleep(0.01)

    def fft_data(self, data, fs):
        f, pxx = signal.welch(x=data, fs=fs)
        self.data_connectors[33].cb_set_data(pxx, f)

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