import numpy
import socket   # used for TCP/IP communication
from settings import SettingsHandler
import sys
import threading
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

DEBUG = True ## SET TO FALSE IF RECORDING!!
FREQ_BANDS = {
    "Delta": [1, 3],
    "Theta": [4, 7],
    "Alpha": [8, 12],
    "Beta": [13, 30],
    "Gamma": [30, 100]
}
MAX_ERRORS = 5

# MainWindow holds all other windows, initializes the settings,
# and connects every needed signal to its respective slot.
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("QMainWindow { background-color: #263238; color: #ffffff }"
                           "QFrame { background-color: #455A64; color: #ffffff }"
                           "QCheckBox { color: #ffffff }"
                           "QCheckBox::indicator::unchecked { background-color: #CFD8DC }"
                           "QCheckBox::indicator::checked { background-color: #B0BEC5; border-image: url(./check.svg)}"
                           "QLineEdit { background-color: #CFD8DC }"
                           "QScrollBar:vertical { background: #CFD8DC }"
                           "QSpinBox { background: #CFD8DC }"
                           "QListView::item:selected { background: #546E7A }"
                           "QListView::item:selected:!active { }"
                           "QPushButton { background: #CFD8DC }"
                           "QComboBox { background: #CFD8DC; selection-background-color: #546E7A }"
                           "QTabWidget { border: #CFD8DC; background: #263238; background-color: #263238 }"
                           "QTabWidget > QWidget { background-color: #37474F }"
                           "QTabBar { background: #546E7A; color: #ffffff }")

        # Load settings
        self.settings = {}
        self.settingsHandler = SettingsHandler("settings.json", self.settings)
        # Initialize main window
        self.setWindowTitle("Biosemi TCP Reader")
        main_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QHBoxLayout()
        # Initialize models
        self.electrodes_model = None
        self.initialize_electrodes()
        self.freq_bands_model = None
        self.initialize_bands()

        # Initialize selection window and graph display window
        self.selection_window = SelectionWindow(self.settings, self.electrodes_model, self.freq_bands_model)
        self.selection_window.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        self.graph_window = GraphWindow(self.settings, self.electrodes_model, self.freq_bands_model)

        # Add to layout and attach to main window
        main_layout.addWidget(self.selection_window)
        main_layout.addWidget(self.graph_window)
        main_widget.setLayout(main_layout)

        ### Signal connections
        # Connection settings
        self.selection_window.ip_box.textChanged.connect(self.settingsHandler.setIp)
        self.selection_window.port_box.textChanged.connect(self.settingsHandler.setPort)
        self.selection_window.samples_box.textChanged.connect(self.settingsHandler.setSamples)
        self.selection_window.fs_box.textChanged.connect(self.settingsHandler.setFs)
        self.selection_window.channels_box.currentTextChanged.connect(self.setTotalChannels)
        self.selection_window.ex_electrodes_box.checkStateChanged.connect(self.setExEnabled)

        # Graph control
        self.selection_window.channel_selector.selectionModel().selectionChanged.connect(self.setActiveChannels)
        self.selection_window.reference_selector.selectionModel().selectionChanged.connect(self.setReference)
        
        self.selection_window.start_button.clicked.connect(self.graph_window.startCapture)
        self.selection_window.stop_button.clicked.connect(self.graph_window.stopCapture)

        # Filter settings
        self.selection_window.decimating_factor_box.valueChanged.connect(self.settingsHandler.setDecimatingFactor)
        self.selection_window.decimating_taps_box.valueChanged.connect(self.settingsHandler.setLowpassTaps)

        # FFT settings
        self.selection_window.welch_window_box.valueChanged.connect(self.settingsHandler.setWelchWindow)
        self.selection_window.fft_checkbox.checkStateChanged.connect(self.settingsHandler.setWelchEnabled)
        ###

        # Show window
        self.setCentralWidget(main_widget)
        self.show()

    # Initializes the model that holds the channel and reference selection
    def initialize_electrodes(self):
        if(self.electrodes_model is not None):
            self.electrodes_model.clear()
        else: self.electrodes_model = QtGui.QStandardItemModel()
        for (group, number) in self.settings['biosemi']['channels'].items():
            for i in range(number):
                name = QtGui.QStandardItem(group + str(i+1))
                view_status = QtGui.QStandardItem()
                view_status.setData(QtCore.QVariant(False))
                ref_status = QtGui.QStandardItem()
                ref_status.setData(QtCore.QVariant(False))
                self.electrodes_model.appendRow([name, view_status, ref_status])

    def initialize_bands(self):
        if(self.freq_bands_model is not None):
            self.freq_bands_model.clear()
        else: 
            data = [[k,0] for k in FREQ_BANDS.keys()]
            self.freq_bands_model = TableModel(data, ["Bands", "Frequency"])

    def setTotalChannels(self, channels):
        self.settingsHandler.setChannels(channels)
        self.initialize_electrodes()

    def setExEnabled(self, enable):
        self.settingsHandler.setExEnabled(enable)
        self.initialize_electrodes()

    def setActiveChannels(self, selection, deselection):
        for i in deselection.indexes():
            self.electrodes_model.itemFromIndex(i.siblingAtColumn(1)).setData(QtCore.QVariant(False))
        for i in selection.indexes():
            self.electrodes_model.itemFromIndex(i.siblingAtColumn(1)).setData(QtCore.QVariant(True))

    def setReference(self, selection, deselection):
        for i in range(self.electrodes_model.rowCount()):
            idx = self.electrodes_model.index(i, 2)
            self.electrodes_model.itemFromIndex(idx).setData(QtCore.QVariant(False))
        for i in selection.indexes():
            self.electrodes_model.itemFromIndex(i.siblingAtColumn(2)).setData(QtCore.QVariant(True))

    def closeEvent(self, event):
        self.settingsHandler.saveSettings()
        self.graph_window.is_capturing = False
        # I feel like this isn't a good way to do this, maybe
        # these members should always exist?
        if hasattr(self.graph_window, 'data_thread'):
            self.graph_window.data_thread.join()
        if hasattr(self.graph_window, 'sock'):
            self.graph_window.sock.close()
        event.accept()

# SelectionWindow implements all the configuration UI,
# as well as handling its' display on the interface.
# Pending to implement: QScrollArea to contain all the widgets,
# to allow adding even more options.
class SelectionWindow(QtWidgets.QTabWidget):
    def __init__(self, settings, electrodes_model, freq_bands_model):
        super().__init__()
        self.settings = settings
        self.electrodes_model = electrodes_model

        # Two tabs: one for settings, the other for value monitoring
        ## Settings tab
        settings_window = QtWidgets.QWidget()
        selection_layout = QtWidgets.QVBoxLayout()

        # Connection settings
        connection_frame = QtWidgets.QFrame()
        connection_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)
        connection_layout = QtWidgets.QFormLayout()
        self.ip_box = QtWidgets.QLineEdit()
        self.ip_box.setText(self.settings['socket']['ip'])
        self.port_box = QtWidgets.QLineEdit()
        self.port_box.setText(str(self.settings['socket']['port']))
        self.samples_box = QtWidgets.QLineEdit()
        self.samples_box.setText(str(self.settings['biosemi']['samples']))
        self.fs_box = QtWidgets.QLineEdit()
        self.fs_box.setText(str(self.settings['biosemi']['fs']))
        self.channels_box = QtWidgets.QComboBox()
        self.channels_box.addItems(["A1-B32 (64)", "A1-A32 (32)", "A1-A16 (16)", "A1-A8 (8)"])
        self.ex_electrodes_box = QtWidgets.QCheckBox()
        self.ex_electrodes_box.setText("8 EX-Electrodes")
        self.ex_electrodes_box.setChecked(self.settings['biosemi']['ex_enabled'])

        connection_layout.addRow(QtWidgets.QLabel("IP"), self.ip_box)
        connection_layout.addRow(QtWidgets.QLabel("Port"), self.port_box)
        connection_layout.addRow(QtWidgets.QLabel("Samples"), self.samples_box)
        connection_layout.addRow(QtWidgets.QLabel("Sampling rate [Hz]"), self.fs_box)
        connection_layout.addRow(QtWidgets.QLabel("Channels"), self.channels_box)
        connection_layout.addWidget(self.ex_electrodes_box)
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

        # Filter settings
        filter_frame = QtWidgets.QFrame()
        filter_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)
        filter_layout = QtWidgets.QVBoxLayout()

        filter_settings = QtWidgets.QWidget()
        filter_settings_layout = QtWidgets.QFormLayout()
        self.decimating_factor_box = QtWidgets.QSpinBox()
        self.decimating_factor_box.setRange(1, 2**31-1)
        self.decimating_factor_box.setValue(self.settings['filter']['decimating_factor'])
        filter_settings_layout.addRow(QtWidgets.QLabel("Decimating factor"), self.decimating_factor_box)
        self.decimating_taps_box = QtWidgets.QSpinBox()
        self.decimating_taps_box.setRange(0, 2**31-1)
        self.decimating_taps_box.setValue(self.settings['filter']['lowpass_taps'])
        filter_settings_layout.addRow(QtWidgets.QLabel("Alias filter taps"), self.decimating_taps_box)
        filter_settings.setLayout(filter_settings_layout)

        filter_layout.addWidget(filter_settings)
        filter_frame.setLayout(filter_layout)
        selection_layout.addWidget(filter_frame)

        verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        selection_layout.addItem(verticalSpacer) 

        # FFT settings
        fft_frame = QtWidgets.QFrame()
        fft_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)
        fft_layout = QtWidgets.QVBoxLayout()
        self.fft_checkbox = QtWidgets.QCheckBox("FFT")
        self.fft_checkbox.setChecked(self.settings['fft']['welch_enabled'])
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

        settings_window.setLayout(selection_layout)
        self.addTab(settings_window, "Settings")

        ## Measurements tab
        measurements_window = QtWidgets.QWidget()
        measurements_layout = QtWidgets.QVBoxLayout()

        freq_bands_table = QtWidgets.QTableView()
        freq_bands_table.setModel(freq_bands_model)
        measurements_layout.addWidget(freq_bands_table)

        verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        measurements_layout.addItem(verticalSpacer) 
        measurements_window.setLayout(measurements_layout)
        self.addTab(measurements_window, "Measurements")


# GraphWindow currently serves the dual purpose of handling the graph display as well as
# implementing the plotting logic itself. It might be a good idea to separate the two, 
# in order to allow creating multiple plot windows if needed.
class GraphWindow(QtWidgets.QWidget):
    def __init__(self, settings, electrodes_model, freq_bands_model):
        super().__init__()
        self.settings = settings
        self.electrodes_model = electrodes_model
        self.freq_bands_model = freq_bands_model
        self.welch_enabled = True
        self.is_capturing = False
        self.graph_layout = QtWidgets.QVBoxLayout()
        # , y_range_controller=LiveAxisRange(fixed_range=[-100, 100])
        self.plot_widget = LivePlotWidget(title="EEG Channels @ 30Hz")
        self.plot_widget.add_crosshair(crosshair_pen=pyqtgraph.mkPen(color="red", width=1), crosshair_text_kwargs={"color": "white"})
        self.graph_layout.addWidget(self.plot_widget)
        self.setLayout(self.graph_layout)

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
        # Generate plots for time-domain graphing
        for i in range(total_channels-1):
            plot = LiveLinePlot(pen=pyqtgraph.hsvColor(i/(total_channels-1), 0.8, 0.9))
            self.data_connectors.append(DataConnector(plot, max_points=(fs*1)/self.settings['filter']['decimating_factor'], plot_rate=30))
            self.plots.append(plot)
            self.plot_widget.addItem(plot)
        # Generate plots for FFT graphing. We don't define max_points because we just set the data directly.
        for i in range(total_channels-1):
            plot = LiveLinePlot(pen=pyqtgraph.hsvColor(i/(total_channels-1), 0.8, 0.9))
            self.data_connectors.append(DataConnector(plot, plot_rate=30))
            self.plots.append(plot)
            self.plot_widget.addItem(plot)
        self.is_capturing = True
        if self.settings['fft']['welch_enabled']:
            self.plot_widget.setLogMode(True, False)
        self.data_thread = Thread(target=self.readData, args=(self.data_connectors,))
        # self.data_thread = QtCore.QThread()
        # worker = DataWorker()
        # worker.moveToThread(data_thread)
        self.data_thread.start()
        print("Reading from ip %s and port %s" % (self.settings['socket']['ip'], self.settings['socket']['port']))

    def stopCapture(self):
        if not self.is_capturing:
            return
        self.is_capturing = False
        if not threading.current_thread() == self.data_thread:
            self.data_thread.join()
        for connector in self.data_connectors:
            connector.deleteLater()
        ## This was causing errors when stopping before FFT deque was full
        ## Possibly because none of the connectors have received data yet?
        # for plot in self.plots:
        #     plot.deleteLater()
        self.plot_widget.deleteLater()
        self.plot_widget = LivePlotWidget(title="EEG Channels @ 30Hz")
        self.plot_widget.add_crosshair(crosshair_pen=pyqtgraph.mkPen(color="red", width=1), crosshair_text_kwargs={"color": "white"})
        self.graph_layout.addWidget(self.plot_widget)
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
        packet_failed = 0
        decimate_enabled = False
        # Apply gain based on physical max/min and digital max/min
        phys_range = self.settings['biosemi']['phys_max'] - self.settings['biosemi']['phys_min']
        digi_range = self.settings['biosemi']['digi_max'] - self.settings['biosemi']['digi_min']
        # Pre-emptively fetch a few values that will be called very often
        samples = self.settings['biosemi']['samples']
        fs = self.settings['biosemi']['fs']
        total_channels = self.electrodes_model.rowCount()
        gain = phys_range/(digi_range * 2**8)
        active_channels = []
        active_reference = -1
        welch_enabled = self.settings['fft']['welch_enabled']
        welch_window = self.settings['fft']['welch_window']
        welch_buffers = []
        decimate_factor = self.settings['filter']['decimating_factor']
        print("Decimate factor:", decimate_factor)
        if decimate_factor > 1: 
            decimate_enabled = True
            alias_filter = signal.firwin(numtaps=self.settings['filter']['lowpass_taps'], cutoff=fs/decimate_factor, pass_zero='lowpass', fs=fs)
        zf = [None for i in range(len(data_connectors))]
        # Generate our buffers for FFT
        # We could skip this if FFT is not enabled, but I don't think it 
        # slows down regular time graphing too much
        for i in range(total_channels):
            buf = deque(maxlen=welch_window)
            buf.extend(numpy.zeros(welch_window))
            welch_buffers.append(buf)

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
        if DEBUG:
            t = 0 # Used for generating sine signal continuously
        while True:
            if DEBUG:
                rng = numpy.random.default_rng()
                # data = rng.bytes(buffer_size)
                # Instead of doing random values, let's try generating a 10 [Hz] sine wave with some noise
                data = bytearray()
                lspace = numpy.linspace(t, t+(samples/fs), samples)
                noise_power = 0.00001 * fs/2
                noise = rng.normal(scale=numpy.sqrt(noise_power), size=lspace.shape)
                for j, i in enumerate(lspace):
                    for k in range(total_channels):
                        if t > 15: val_orig = int((numpy.sin(2 * numpy.pi * 100 * i) + noise[j])*10000) 
                        else: val_orig = int((numpy.sin(2 * numpy.pi * 10 * i) + noise[j])*10000) 
                        val = (val_orig).to_bytes(3, byteorder='little', signed=True)
                        if(len(val) > 3):
                            val = val[-3:]
                        val_rec = bytearray(1)
                        val_rec.append(val[0])
                        val_rec.append(val[1])
                        val_rec.append(val[2])
                        val_rec = int.from_bytes(val, byteorder='little', signed=True)
                        # if not rng.integers(0, 100) > 50:
                        data.extend(val)
                t += samples/fs
            else:
                # Read the next packet from the network
                data = self.sock.recv(buffer_size)

            # Extract all channel samples from the packet
            # We use a try statement as occasionally packet loss messes up the data
            try:
                for m in range(samples):
                    # To increase CMRR, we can pick a reference point and subtract it from every other point we are reading
                    if(active_reference > -1):
                        ref_offset = (m * 3 * total_channels) + (active_reference*3)
                        sample = bytearray(1)
                        sample.append(data[ref_offset])
                        sample.append(data[ref_offset+1])
                        sample.append(data[ref_offset+2])
                        ref_value = int.from_bytes(sample, byteorder='little', signed=True)
                    else:
                        ref_value = 0
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
                        # Apply reference value and gain
                        value = (value - ref_value)*gain
                        welch_buffers[n].append(value)
                        
                        # Send sample to plot
                        # Rate limited to only check every full set of samples
                        if welch_enabled:
                            if x % samples == 0:
                                if len(welch_buffers[n]) == welch_buffers[n].maxlen:
                                    f, pxx = signal.welch(x=welch_buffers[n], fs=fs, nperseg=welch_window/5)
                                    self.data_connectors[n + (total_channels)].cb_set_data(pxx, f)
                                    alpha_avg = []
                                    for i, freq in enumerate(f):
                                        if FREQ_BANDS['Alpha'][0] <= freq <= FREQ_BANDS['Alpha'][1]:
                                            alpha_avg.append(pxx[i])
                                    self.freq_bands_model.setData(self.freq_bands_model.index(2,1), int(sum(alpha_avg)/len(alpha_avg)))

                        elif decimate_enabled:
                            if zf[n] is None:
                                zf[n] = signal.lfiltic(b=alias_filter, a=1, y=value)
                                self.data_connectors[n].cb_append_data_point(value, x/fs)
                            else: 
                                [value], zf[n] = signal.lfilter(b=alias_filter, a=1, x=[value], zi=zf[n])
                            if x % decimate_factor == 0:
                                self.data_connectors[n].cb_append_data_point(value, x/fs)
                        else:
                            self.data_connectors[n].cb_append_data_point(value, x/fs)

                    if not self.is_capturing:
                        return
                    x += 1
                    if DEBUG:
                        sleep(1/self.settings['biosemi']['fs'])
                if packet_failed > 0:
                    packet_failed -= 1
                
            except IndexError:
                packet_failed += 1
                print("Packet reading failed! Failed attempts:", packet_failed)
                if packet_failed > MAX_ERRORS:
                    print("Failed to read packets too many times, dropping connection")
                    #self.stopCapture()
                    return
                

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

# For some reason, there's no existing implementation for this interface,
# so we make our own, even though it really doesn't need to do anything fancy.
# Currently designed as an array and can't be expanded after initialization. 
# Wouldn't be too difficult to extend later.
class TableModel(QtCore.QAbstractTableModel):
    def __init__(self, data, header):
        super().__init__()
        self._header = header
        self._data = data
    
    # Our table is stored as row-major, so we just need the array's length
    def rowCount(self, parent):
        if parent.isValid():
            return 0
        return len(self._data)

    # We assume all subarrays are the correct size in our _data array.
    def columnCount(self, parent):
        if parent.isValid():
            return 0
        return len(self._data[0])

    def data(self, index, role = QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return QtCore.QVariant(self._data[index.row()][index.column()])
        return None

    def setData(self, index, value, role = QtCore.Qt.ItemDataRole.EditRole):
        if not index.isValid():
            return False
        if role == QtCore.Qt.ItemDataRole.EditRole:
            self._data[index.row()][index.column()] = value
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    # Just ignoring orientation for now, as well as role
    def headerData(self, section, orientation, role = QtCore.Qt.ItemDataRole.DisplayRole):
        if orientation == QtCore.Qt.Orientation.Horizontal and role == QtCore.Qt.ItemDataRole.DisplayRole:
            return QtCore.QVariant(self._header[section])
        return QtCore.QVariant() 

    # Our table is for viewing only, so we just return NoItemFlags.
    def flags(self, index):
        return QtCore.Qt.ItemFlag.NoItemFlags

## Class definition for thread that receives data
# This was decoupled from the main application as it needed some custom signals for proper termination
# class DataWorker(QtCore.QObject):
#     finished = QtCore.pyqtSignal()

#     def __init__(self):
#         super().__init__()
#         if not DEBUG:
#             self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#             self.sock.connect((self.settings['socket']['ip'], self.settings['socket']['port']))
        

#     ##  TCP packet format (2 channels example). Each sample is 24-bits, little-endian.
#     ##  To convert to a 32-bit integer, we add a 0-byte to the LSB before converting to big-endian.
#     ##  ╔══════╗╔══════╗╔══════╗ ╔══════╗╔══════╗╔══════╗ ╔══════╗╔══════╗╔══════╗ ╔══════╗╔══════╗╔══════╗
#     ##  ║ C1S1 ║║ C1S1 ║║ C1S1 ║ ║ C2S1 ║║ C2S1 ║║ C2S1 ║ ║ C1S2 ║║ C1S2 ║║ C1S2 ║ ║ C2S2 ║║ C2S2 ║║ C2S2 ║
#     ##  ║  B1  ║║  B2  ║║  B3  ║ ║  B1  ║║  B2  ║║  B3  ║ ║  B1  ║║  B2  ║║  B3  ║ ║  B1  ║║  B2  ║║  B3  ║
#     ##  ╚══════╝╚══════╝╚══════╝ ╚══════╝╚══════╝╚══════╝ ╚══════╝╚══════╝╚══════╝ ╚══════╝╚══════╝╚══════╝
#     def readData(self, data_connectors, electrodes_model, settings):
#         x = 0
#         packet_failed = 0
#         decimate_enabled = False
#         # Apply gain based on physical max/min and digital max/min
#         phys_range = settings['biosemi']['phys_max'] - settings['biosemi']['phys_min']
#         digi_range = settings['biosemi']['digi_max'] - settings['biosemi']['digi_min']
#         # Pre-emptively fetch a few values that will be called very often
#         samples = settings['biosemi']['samples']
#         fs = settings['biosemi']['fs']
#         total_channels = electrodes_model.rowCount()
#         gain = phys_range/(digi_range * 2**8)
#         active_channels = []
#         active_reference = -1
#         welch_enabled = settings['fft']['welch_enabled']
#         welch_window = settings['fft']['welch_window']
#         welch_buffers = []
#         decimate_factor = settings['filter']['decimating_factor']
#         print("Decimate factor:", decimate_factor)
#         if decimate_factor > 1: 
#             decimate_enabled = True
#             alias_filter = signal.firwin(numtaps=settings['filter']['lowpass_taps'], cutoff=fs/decimate_factor, pass_zero='lowpass', fs=fs)
#         zf = [None for i in range(len(data_connectors))]
#         # Generate our buffers for FFT
#         # We could skip this if FFT is not enabled, but I don't think it 
#         # slows down regular time graphing too much
#         for i in range(total_channels):
#             welch_buffers.append(deque(maxlen=welch_window))
#         buffer_size = total_channels * settings['biosemi']['samples'] * 3
#         for i in range(total_channels):
#             # Select active channels
#             idx = electrodes_model.index(i,1)
#             if electrodes_model.itemFromIndex(idx).data(): 
#                 active_channels.append(i)
#             # Select reference point
#             idx = electrodes_model.index(i,2)
#             if electrodes_model.itemFromIndex(idx).data():
#                 active_reference = i
#         if DEBUG:
#             t = 0 # Used for generating sine signal continuously
#         while True:
#             if DEBUG:
#                 rng = numpy.random.default_rng()
#                 # data = rng.bytes(buffer_size)
#                 # Instead of doing random values, let's try generating a 10 [Hz] sine wave with some noise
#                 data = bytearray()
#                 lspace = numpy.linspace(t, t+(samples/fs), samples)
#                 noise_power = 0.00001 * fs/2
#                 noise = rng.normal(scale=numpy.sqrt(noise_power), size=lspace.shape)
#                 for j, i in enumerate(lspace):
#                     for k in range(total_channels):
#                         val_orig = int((numpy.sin(2 * numpy.pi * 10 * i) + noise[j])*10000) 
#                         val = (val_orig).to_bytes(3, byteorder='little', signed=True)
#                         if(len(val) > 3):
#                             val = val[-3:]
#                         val_rec = bytearray(1)
#                         val_rec.append(val[0])
#                         val_rec.append(val[1])
#                         val_rec.append(val[2])
#                         val_rec = int.from_bytes(val, byteorder='little', signed=True)
#                         if not rng.integers(0, 100) > 50:
#                             data.extend(val)
#                 t += samples/fs
#             else:
#                 # Read the next packet from the network
#                 data = sock.recv(buffer_size)

#             # Extract all channel samples from the packet
#             # We use a try statement as occasionally packet loss messes up the data
#             try:
#                 for m in range(samples):
#                     # To increase CMRR, we can pick a reference point and subtract it from every other point we are reading
#                     if(active_reference > -1):
#                         ref_offset = (m * 3 * total_channels) + (active_reference*3)
#                         sample = bytearray(1)
#                         sample.append(data[ref_offset])
#                         sample.append(data[ref_offset+1])
#                         sample.append(data[ref_offset+2])
#                         ref_value = int.from_bytes(sample, byteorder='little', signed=True)
#                     else:
#                         ref_value = 0
#                     for n in active_channels:
#                         # Samples are sent in bulk of size SAMPLES, interleaved such that
#                         # the first sample of each channel is sent, then the second sample,
#                         # and so on.
#                         offset = (m * 3 * total_channels) + (n*3)
#                         # The 3 bytes of each sample arrive in reverse order (little endian).
#                         # We convert them to a 32bit integer by appending the bytes together,
#                         # and adding a zero byte as LSB.
#                         sample = bytearray(1)
#                         sample.append(data[offset])
#                         sample.append(data[offset+1])
#                         sample.append(data[offset+2])
#                         value = int.from_bytes(sample, byteorder='little', signed=True)
#                         # Apply reference value and gain
#                         value = (value - ref_value)*gain
#                         welch_buffers[n].append(value)
                        
#                         # Send sample to plot
#                         if welch_enabled:
#                             if len(welch_buffers[n]) == welch_buffers[n].maxlen:
#                                 f, pxx = signal.welch(x=welch_buffers[n], fs=fs, nperseg=welch_window/5)
#                                 self.data_connectors[n + (total_channels-1)].cb_set_data(pxx, f)
#                                 alpha_avg = []
#                                 for i, freq in enumerate(f):
#                                     if FREQ_BANDS['Alpha'][0] <= freq <= FREQ_BANDS['Alpha'][1]:
#                                         alpha_avg.append(pxx[i])
#                                 self.freq_bands_model.setData(self.freq_bands_model.index(2,1), int(sum(alpha_avg)/len(alpha_avg)))

#                         elif decimate_enabled:
#                             if zf[n] is None:
#                                 zf[n] = signal.lfiltic(b=alias_filter, a=1, y=value)
#                                 self.data_connectors[n].cb_append_data_point(value, x/fs)
#                             else: 
#                                 [value], zf[n] = signal.lfilter(b=alias_filter, a=1, x=[value], zi=zf[n])

#                             if x % decimate_factor == 0:
#                                 self.data_connectors[n].cb_append_data_point(value, x/fs)
#                         else:
#                             self.data_connectors[n].cb_append_data_point(value, x/fs)

#                     if not self.is_capturing:
#                         return
#                     x += 1
#                     if DEBUG:
#                         sleep(1/self.settings['biosemi']['fs'])
#                 if packet_failed > 0:
#                     packet_failed -= 1
                
#             except IndexError:
#                 packet_failed += 1
#                 print("Packet reading failed! Failed attempts:", packet_failed)
#                 if packet_failed > MAX_ERRORS:
#                     print("Failed to read packets too many times, dropping connection")
#                     self.stopCapture()
#                     return

app = QtWidgets.QApplication(sys.argv)
window = MainWindow()
sys.exit(app.exec())