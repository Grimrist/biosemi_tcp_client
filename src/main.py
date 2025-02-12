from settings import SettingsHandler    
import sys
from PyQt6 import QtWidgets, QtCore, QtGui, QtSerialPort
import pyqtgraph
import pyqtgraph.exporters
import OpenGL
pyqtgraph.setConfigOption('useOpenGL', True)
pyqtgraph.setConfigOption('enableExperimental', True)
pyqtgraph.setConfigOption('antialias', False)
pyqtgraph.setConfigOption('exitCleanup', True)

from pyqtgraph import PlotCurveItem, PlotWidget, AxisItem, GridItem, PlotDataItem, BarGraphItem, GraphicsView, InfiniteLine
from pyqtgraph.dockarea import Dock, DockArea

from data_parser import DataWorker
from fft_parser import FFTWorker
import global_vars
from dvg_ringbuffer import RingBuffer
import numpy
from time import perf_counter_ns
import tsdownsample

if len(sys.argv) > 1 and sys.argv[1] == "-d":
    pyqtgraph.setConfigOption('crashWarning', True)

from debug_source import DebugWorker
from serial import SerialHandler
from file_tab import FileTab
from real_time_plot import RealTimePlot
from utils import LogAxis, CustomPlotItem

# MainWindow holds all other windows, initializes the settings, and connects every needed signal to its respective slot.
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("QMainWindow { background-color: #263238; color: #ffffff }"
                           "QFrame { background-color: #455A64; color: #ffffff }"
                           "QCheckBox { color: #ffffff }"
                           "QCheckBox::indicator::unchecked { background-color: #CFD8DC }"
                           "QCheckBox::indicator::checked { background-color: #B0BEC5; border-image: url(./icons/check.svg)}"
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
        self.settings_handler = SettingsHandler("settings.json", self.settings)
        
        # Initialize main window
        self.setWindowTitle("Biosemi TCP Reader")
        main_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QHBoxLayout()

        # Initialize models
        self.electrodes_model = None
        self.initializeElectrodes()
        self.freq_bands_model = None
        self.initializeBands()

        # Initialize serial handler
        self.serial_handler = SerialHandler(self.settings['serial']['enabled'])

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
        self.selection_window.ip_box.textChanged.connect(self.settings_handler.setIp)
        self.selection_window.port_box.textChanged.connect(self.settings_handler.setPort)
        self.selection_window.samples_box.textChanged.connect(self.settings_handler.setSamples)
        self.selection_window.fs_box.textChanged.connect(self.settings_handler.setFs)
        self.selection_window.channels_box.textActivated.connect(self.setTotalChannels)
        self.selection_window.ex_electrodes_box.checkStateChanged.connect(self.setExEnabled)

        # Graph control
        self.selection_window.channel_selector.selectionModel().selectionChanged.connect(self.setActiveChannels)
        self.selection_window.reference_selector.selectionModel().selectionChanged.connect(self.setReference)
        
        self.selection_window.start_button.clicked.connect(self.graph_window.startCapture)
        self.selection_window.stop_button.clicked.connect(self.graph_window.stopCapture)
        self.graph_window.captureStarted.connect(self.graph_window.worker.readData)
        self.graph_window.captureStarted.connect(self.graph_window.fft_worker.initializeWorker)
        self.graph_window.startFile.connect(self.graph_window.debug_worker.generateSignalFromFile)

        self.selection_window.fft_checkbox.checkStateChanged.connect(self.graph_window.toggleFFT)

        # File replay control
        self.selection_window.file_tab.start_button.clicked.connect(self.graph_window.startCaptureFromFile)
        self.selection_window.file_tab.stop_button.clicked.connect(self.graph_window.stopCapture)

        # Filter settings
        # self.selection_window.decimating_factor_box.valueChanged.connect(self.settings_handler.setDecimatingFactor)
        # self.selection_window.decimating_taps_box.valueChanged.connect(self.settings_handler.setLowpassTaps)

        # View control
        self.selection_window.rolling_checkbox.checkStateChanged.connect(self.graph_window.setRollingView)
        self.selection_window.rolling_checkbox.checkStateChanged.connect(self.settings_handler.setRollingEnabled)

        # FFT settings
        self.selection_window.welch_window_box.valueChanged.connect(self.settings_handler.setWelchWindow)
        self.selection_window.fft_checkbox.checkStateChanged.connect(self.settings_handler.setWelchEnabled)

        # Serial settings
        self.selection_window.serial_port_box.textActivated.connect(self.settings_handler.setSerialPort)
        self.selection_window.serial_baud_box.textActivated.connect(self.settings_handler.setBaudRate)
        self.selection_window.serial_checkbox.checkStateChanged.connect(self.settings_handler.setSerialEnabled)
        self.selection_window.serial_checkbox.checkStateChanged.connect(self.serial_handler.setWriteEnabled)
        self.graph_window.captureStarted.connect(self.startSerial)
        self.graph_window.captureStopped.connect(self.serial_handler.stopSerial)
        self.selection_window.sendSerial.connect(self.serial_handler.write)

        # Thresholds
        # Just a quick prototype, this needs more robust support
        self.selection_window.alpha_threshold_box.editingFinished.connect(self.updateAlphaThreshold)
        self.freq_bands_model.thresholdChanged.connect(self.selection_window.updateThresholdDisplay)
        self.graph_window.fft_worker.bandsUpdated.connect(self.selection_window.updateBandDisplay)

        # File view settings
        self.selection_window.file_tab.activeFileChanged.connect(self.settings_handler.setFile)
        self.selection_window.file_tab.directoryChanged.connect(self.settings_handler.setDirectory)
        self.selection_window.file_tab.doubleClickedFile.connect(self.graph_window.startCapture)

        # Show window
        self.setCentralWidget(main_widget)
        self.show()

    # Function to update settings and selection window safely via editingFinished
    # This is more of a hotfix, if we plan to support setting the other thresholds,
    # this should be generalized.
    def updateAlphaThreshold(self):
        value = self.selection_window.alpha_threshold_box.value()
        self.settings_handler.setAlphaThreshold(value)
        self.selection_window.setAlphaThreshold(value)

    # Initializes the model that holds the channel and reference selection
    def initializeElectrodes(self):
        if self.electrodes_model is not None:
            self.electrodes_model.clear()
        else: self.electrodes_model = QtGui.QStandardItemModel()
        for (group, number) in self.settings['biosemi']['channels'].items():
            for i in range(number):
                if group == "A":
                    name = QtGui.QStandardItem(global_vars.CHANNELS[i])
                elif group == "B": 
                    name = QtGui.QStandardItem(global_vars.CHANNELS[i+32])
                view_status = QtGui.QStandardItem()
                view_status.setData(QtCore.QVariant(False))
                ref_status = QtGui.QStandardItem()
                ref_status.setData(QtCore.QVariant(False))
                self.electrodes_model.appendRow([name, view_status, ref_status])

    # Initializes model for band display as well as storing threshold information
    def initializeBands(self):
        if self.freq_bands_model is not None:
            self.freq_bands_model.clear()
        else: 
            data = []
            for k in global_vars.FREQ_BANDS.keys():
                if k == "Alpha":
                    data.append([k, 0, self.settings['threshold']['alpha'], False])
                else: data.append([k, 0, 1, False])
            self.freq_bands_model = FreqTableModel(data, ["Bands", "Relative Power", "Threshold", "Status"])

    # Sets the total amount of channels and re-initializes electrodes model to update the UI
    def setTotalChannels(self, channels):
        self.settings_handler.setChannels(channels)
        self.initializeElectrodes()

    # Enables EX-Electrodes and re-initializes electrodes model
    def setExEnabled(self, enable):
        self.settings_handler.setExEnabled(enable)
        self.initializeElectrodes()

    # Updates electrodes model with the currently selected channels in the UI
    def setActiveChannels(self, selection, deselection):
        for i in deselection.indexes():
            self.electrodes_model.itemFromIndex(i.siblingAtColumn(1)).setData(QtCore.QVariant(False))
        for i in selection.indexes():
            self.electrodes_model.itemFromIndex(i.siblingAtColumn(1)).setData(QtCore.QVariant(True))
        self.graph_window.setActiveChannels()

    # Updates electrodes model with the currently selected reference in the UI
    def setReference(self, selection, deselection):
        for i in range(self.electrodes_model.rowCount()):
            idx = self.electrodes_model.index(i, 2)
            self.electrodes_model.itemFromIndex(idx).setData(QtCore.QVariant(False))
        for i in selection.indexes():
            self.electrodes_model.itemFromIndex(i.siblingAtColumn(2)).setData(QtCore.QVariant(True))
        self.graph_window.setReferenceChannel()

    def startSerial(self):
        port = self.settings['serial']['port']
        baud = int(self.settings['serial']['baud_rate'])
        self.serial_handler.startSerial(port, baud)

    # Attempts to safely close the program. Doesn't work very reliably right now
    def closeEvent(self, event):
        self.settings_handler.saveSettings()
        self.graph_window.stopCapture()
        self.graph_window.data_thread.wait(100)
        self.graph_window.fft_thread.wait(100)
        self.graph_window.debug_thread.wait(100)
        self.graph_window.fft_plot_widget.close()
        self.graph_window.plot_widget.close()
        self.selection_window.freq_bands_view.close()
        event.accept()        

# SelectionWindow implements all the configuration UI.
# Pending to implement: QScrollArea to contain all the widgets, to allow further expanding of the UI.
# Potential TODO: Break this up into individual functions or even classes. I'm not sure if I'm a fan of this
# because it might become really cluttered with what's otherwise just simple composition
class SelectionWindow(QtWidgets.QTabWidget):
    sendSerial = QtCore.pyqtSignal(bytes)

    def __init__(self, settings, electrodes_model, freq_bands_model):
        super().__init__()
        self.settings = settings
        self.electrodes_model = electrodes_model
        self.freq_bands_model = freq_bands_model
        # Timer to ensure serial doesn't fire too easily
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(1000)
        # Two tabs: one for settings, the other for value monitoring
        # New tab: file selection, useful for debugging and also calibrating thresholds
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
        # I can't think of a good way to do this right now, so here's my terrible solution
        if "B" in self.settings['biosemi']['channels']:
            self.channels_box.setCurrentIndex(0)
        elif self.settings['biosemi']['channels']["A"] == 32:
            self.channels_box.setCurrentIndex(1)
        elif self.settings['biosemi']['channels']["A"] == 16:
            self.channels_box.setCurrentIndex(2)
        else: self.channels_box.setCurrentIndex(3)
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
        # item_height = self.channel_selector.visualRect(self.channel_selector.indexAt(QtCore.QPoint(0,0))).height()
        # self.channel_selector.setMinimumHeight(item_height*10)
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
        # filter_frame = QtWidgets.QFrame()
        # filter_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)
        # filter_layout = QtWidgets.QVBoxLayout()

        # filter_settings = QtWidgets.QWidget()
        # filter_settings_layout = QtWidgets.QFormLayout()
        # self.decimating_factor_box = QtWidgets.QSpinBox()
        # self.decimating_factor_box.setRange(1, 2**31-1)
        # self.decimating_factor_box.setValue(self.settings['filter']['decimating_factor'])
        # filter_settings_layout.addRow(QtWidgets.QLabel("Decimating factor"), self.decimating_factor_box)
        # self.decimating_taps_box = QtWidgets.QSpinBox()
        # self.decimating_taps_box.setRange(0, 2**31-1)
        # self.decimating_taps_box.setValue(self.settings['filter']['lowpass_taps'])
        # filter_settings_layout.addRow(QtWidgets.QLabel("Alias filter taps"), self.decimating_taps_box)
        # filter_settings.setLayout(filter_settings_layout)

        # filter_layout.addWidget(filter_settings)
        # filter_frame.setLayout(filter_layout)
        # selection_layout.addWidget(filter_frame)

        # verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        # selection_layout.addItem(verticalSpacer) 

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

        verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        selection_layout.addItem(verticalSpacer) 

        # View settings
        view_frame = QtWidgets.QFrame()
        view_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)
        view_layout = QtWidgets.QVBoxLayout()

        self.rolling_checkbox = QtWidgets.QCheckBox("Rolling view")
        self.rolling_checkbox.setChecked(self.settings['view']['rolling_enabled'])

        view_layout.addWidget(self.rolling_checkbox)

        view_frame.setLayout(view_layout)
        selection_layout.addWidget(view_frame)

        verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        selection_layout.addItem(verticalSpacer) 

        # Serial configuration
        serial_frame = QtWidgets.QFrame()
        serial_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)
        serial_layout = QtWidgets.QVBoxLayout()
        serial_frame.setLayout(serial_layout)
        selection_layout.addWidget(serial_frame)
        self.serial_port_box = QtWidgets.QComboBox()
        self.serial_port_box.addItem(" ")
        for port in QtSerialPort.QSerialPortInfo().availablePorts():
            self.serial_port_box.addItem(port.portName())
        serial_layout.addWidget(self.serial_port_box)
        idx = self.serial_port_box.findText(self.settings['serial']['port'])
        if not idx == -1:
            self.serial_port_box.setCurrentIndex(idx)
    
        self.serial_baud_box = QtWidgets.QComboBox()
        for baud_rate in QtSerialPort.QSerialPortInfo().standardBaudRates():
            self.serial_baud_box.addItem(str(baud_rate))
        idx = self.serial_baud_box.findText(self.settings['serial']['baud_rate'])
        if not idx == -1:
            self.serial_baud_box.setCurrentIndex(idx)
        
        serial_layout.addWidget(self.serial_baud_box)

        self.serial_checkbox = QtWidgets.QCheckBox()
        self.serial_checkbox.setText("Enable serial")
        self.serial_checkbox.setChecked(self.settings['serial']['enabled'])
        serial_layout.addWidget(self.serial_checkbox)

        # Finish building tab
        settings_window.setLayout(selection_layout)
        self.addTab(settings_window, "Settings")

        self.file_tab = FileTab(settings)
        self.addTab(self.file_tab, "File")

        ## Measurements tab
        measurements_window = QtWidgets.QWidget()
        measurements_layout = QtWidgets.QVBoxLayout()

        # Bar chart to display band intensity
        band_frame = QtWidgets.QFrame()
        band_layout = QtWidgets.QVBoxLayout()
        band_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)
        self.freq_bands_view = PlotWidget(background=pyqtgraph.mkColor("#455A64"))
        self.freq_bands_view.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Minimum)
        self.freq_bands_view.setMaximumWidth(300)
        self.freq_bands_view.setMaximumHeight(300)
        total_bands = len(global_vars.FREQ_BANDS.keys())
        band_width = 0.8
        color = pyqtgraph.mkColor("#808080")
        self.freq_bands_chart = BarGraphItem(height=0.1, width=band_width, x=range(total_bands), y0=0, brushes=[color]*total_bands)
        ax = self.freq_bands_view.getAxis('bottom')
        grey = pyqtgraph.mkColor("#d4d4d4")
        ax.setTextPen(grey)
        ax.setPen(grey)
        ax.setTicks([[(i, band) for i,band in enumerate(global_vars.FREQ_BANDS.keys())],[]])
        ax = self.freq_bands_view.getAxis('left')
        ax.setTextPen(grey)
        ax.setPen(grey)
        self.freq_bands_view.addItem(self.freq_bands_chart)
        self.freq_bands_view.setRange(xRange=[0-(band_width/1.5),4+(band_width/1.5)], yRange=[0,1.05], disableAutoRange=True, padding=0)
        self.freq_bands_view.setMouseEnabled(x=False,y=False)
        self.freq_bands_view.hideButtons()
        alpha_threshold = self.settings['threshold']['alpha']
        self.threshold_line = InfiniteLine(angle=0, pen='r', label='Alpha', pos=alpha_threshold, movable=True, bounds=[0,1])
        self.threshold_line.sigPositionChangeFinished.connect(self.setAlphaThresholdFromLine)
        self.freq_bands_view.addItem(self.threshold_line)
        band_layout.addWidget(self.freq_bands_view)
        band_frame.setLayout(band_layout)
        measurements_layout.addWidget(band_frame)
        
        # Thresholds
        threshold_widget = QtWidgets.QWidget()
        threshold_layout = QtWidgets.QFormLayout()
        self.alpha_threshold_box = QtWidgets.QDoubleSpinBox()
        self.alpha_threshold_box.setRange(0, 1)
        self.alpha_threshold_box.setValue(self.settings['threshold']['alpha'])
        threshold_layout.addRow(QtWidgets.QLabel("Alpha threshold"), self.alpha_threshold_box)
        threshold_widget.setLayout(threshold_layout)
        band_layout.addWidget(threshold_widget)

        # TODO: Revisit this eventually, feels like it could be designed better
        self.red_icon = QtGui.QPixmap("./icons/red_icon.png")
        self.black_icon = QtGui.QPixmap("./icons/black_icon.png")
        indicator_frame = QtWidgets.QFrame()
        indicator_frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Raised)
        indicator_layout = QtWidgets.QFormLayout()
        self.band_indicators = []
        for freq_band in global_vars.FREQ_BANDS.keys():
            indicator = QtWidgets.QLabel(freq_band + " under threshold.")
            indicator_img = QtWidgets.QLabel()
            indicator_img.setPixmap(self.black_icon)
            indicator_layout.addRow(indicator_img, indicator)
            self.band_indicators.append((indicator, indicator_img))
        indicator_frame.setLayout(indicator_layout)
        measurements_layout.addWidget(indicator_frame)
        
        verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        measurements_layout.addItem(verticalSpacer) 
        measurements_window.setLayout(measurements_layout)
        self.addTab(measurements_window, "Measurements")

    # Updates indicators when the model signals that it has surpassed the set threshold
    def updateThresholdDisplay(self, index, status):
        band = self.band_indicators[index.row()][0].text().split()[0]
        color = pyqtgraph.mkColor("#808080")
        if status:
            self.band_indicators[index.row()][0].setText(band + " over threshold")
            self.band_indicators[index.row()][1].setPixmap(self.red_icon)
            red = pyqtgraph.mkColor("#ff0000")
            self.freq_bands_chart.setOpts(brushes=[color,color,red,color,color])
        else:
            self.band_indicators[index.row()][0].setText(band + " under threshold")
            self.band_indicators[index.row()][1].setPixmap(self.black_icon)
            self.freq_bands_chart.setOpts(brushes=[color]*5)

        # Send signal to connected serial output (e.g Arduino)
        if band == "Alpha":
            if status:
                self.sendEnableSignal()
            else:
                self.sendDisableSignal()

    # TODO: Expose this in the configuration side so that you can specify the signals
    def sendDisableSignal(self):
        self.sendSerial.emit(b'0')

    def sendEnableSignal(self):
        self.sendSerial.emit(b'1')

    # Sets the threshold for the frequency band detection, either from the line or via manual input
    def setAlphaThreshold(self, value):
        alpha = self.freq_bands_model.match(self.freq_bands_model.index(0,0), QtCore.Qt.ItemDataRole.DisplayRole, "Alpha")[0]
        self.freq_bands_model.setData(alpha.siblingAtColumn(2), value)
        self.threshold_line.setValue(value)

    def setAlphaThresholdFromLine(self, ev):
        value = self.threshold_line.value()
        self.alpha_threshold_box.setValue(value)
        self.setAlphaThreshold(value)

    def updateBandDisplay(self, bands):
        self.freq_bands_chart.setOpts(height=bands)

# GraphWindow currently serves the dual purpose of handling the graph display as well as
# implementing the plotting logic itself. It might be a good idea to separate the two
class GraphWindow(QtWidgets.QWidget):
    captureStarted = QtCore.pyqtSignal()
    captureStopped = QtCore.pyqtSignal()
    startFile = QtCore.pyqtSignal()

    def __init__(self, settings, electrodes_model, freq_bands_model):
        super().__init__()
        self.settings = settings
        self.electrodes_model = electrodes_model
        self.freq_bands_model = freq_bands_model
        self.welch_enabled = True
        self.is_capturing = False
        self.restart_queued = False
        self.rolling_view = self.settings['view']['rolling_enabled']
        self.graph_layout = QtWidgets.QVBoxLayout()
        self.initializePlotWidgets()
        if not self.settings['fft']['welch_enabled']:
            self.fft_plot_widget.hide()
        self.setLayout(self.graph_layout)
        self.plots = []
        self.initializeWorker()

    # Toggles displaying the FFT window
    def toggleFFT(self, checked):
        if(checked == QtCore.Qt.CheckState.Checked):
            self.fft_plot_widget.show()
        else:
            self.fft_plot_widget.hide()

    # Initializes the plot widgets, alongside their axis configuration
    def initializePlotWidgets(self):
        fs = self.settings['biosemi']['fs']
        dock_area = DockArea()
        dock_1 = Dock("Dock 1")
        dock_2 = Dock("Dock 2")
        dock_area.addDock(dock_1, 'top')
        dock_area.addDock(dock_2, 'bottom')
        self.plot_widget = RealTimePlot(plotItem=CustomPlotItem(title="EEG time-domain plot"))
        self.plot_widget.getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_widget.getAxis('left').enableAutoSIPrefix(False)
        self.plot_widget.getAxis('bottom').setStyle(autoReduceTextSpace=True)
        self.plot_widget.setLabel('bottom', "Time", "s")
        self.plot_widget.setLabel('left', "Magnitude", "uV")
        self.plot_widget.getViewBox().disableAutoRange()
        grid = GridItem()
        self.plot_widget.addItem(grid)
        dock_1.addWidget(self.plot_widget)

        fft_bottom_axis = LogAxis('bottom')
        self.fft_plot_widget = PlotWidget(title="Power spectral density graph", axisItems={'bottom':fft_bottom_axis})
        self.fft_plot_widget.setLogMode(True, False)
        self.fft_plot_widget.getAxis('bottom').enableAutoSIPrefix(False)
        self.fft_plot_widget.getAxis('left').enableAutoSIPrefix(False)
        grid = GridItem()
        grid.setTickSpacing(x=[1.0])
        self.fft_plot_widget.addItem(grid)
        self.fft_plot_widget.setLabel('bottom', "Frequency", "Hz")
        self.fft_plot_widget.setLabel('left', "Power", "dB")
    
        dock_2.addWidget(self.fft_plot_widget)

        self.graph_layout.addWidget(dock_area)

    # Initializes PlotDataItems in both our separate plot widget and GraphWindow
    def initializeGraphs(self):
        fs = self.settings['biosemi']['fs']
        total_channels = self.electrodes_model.rowCount()
        time_length = 8 # Data buffer length in seconds, consider exposing to UI
        self.buffer_size = int(fs*time_length)

        # Select active channels and initialize time-domain plot
        active_channels = []
        for i in range(total_channels):
            idx = self.electrodes_model.index(i,1)
            if self.electrodes_model.itemFromIndex(idx).data(): 
                active_channels.append(i)
        self.plot_widget.initializeGraphs(fs, total_channels, self.buffer_size, self.rolling_view, active_channels)

        # Initialize plot for FFT graphing
        self._last_fft_update = 0
        self.fft_plot = PlotDataItem(pen=pyqtgraph.hsvColor(1/(total_channels), 0.8, 0.9), skipFiniteCheck=True)
        self.fft_plot_widget.addItem(self.fft_plot)
        padding = 0
        self.plot_widget.setXRange(0,self.buffer_size/fs,padding)
        self.fft_plot_widget.getViewBox().enableAutoRange(enable=False)
        # We can completely predict the range of the spectrum, so we clamp the view ahead of time
        # I have no idea why this doesn't work for the xMin, some kind of artifact of the log implementation
        # self.fft_plot_widget.setLimits(xMin=0.01, xMax=numpy.log10(fs/2))

    def startCaptureFromFile(self):
        if not self.is_capturing:
            self.startFile.emit()
            self.startCapture()
        else:
            self.startCapture()
            self.startFile.emit()

    # Start capturing, either from an active capture or from a fully stopped state
    def startCapture(self):
        if not self.is_capturing:
            self.initializeGraphs()
            self.captureStarted.emit()
            self.plot_widget.setLimits(xMin=0)
            self.is_capturing = True
        else:
            self.restart_queued = True
            self.stopCapture()

    # Stop capturing, which terminates our worker threads and cleans up plots
    def stopCapture(self):
        if not self.is_capturing:
            return
        self.is_capturing = False
        self.worker.terminate()
        self.debug_worker.terminate()
        self.captureStopped.emit()

    # Clean up all the objects used for plotting.
    # Having to delete all the plots is partially just technical debt from
    # when we were using a different library, but it works so I haven't changed it
    def cleanup(self):
        self.is_capturing = False
        self.plot_widget.cleanup()
        self.fft_plot_widget.removeItem(self.fft_plot)
        self.fft_plot.deleteLater()
        self.disableThresholds()
        if self.restart_queued:
            self.initializeGraphs()
            self.captureStarted.emit()
            self.is_capturing = True
            self.restart_queued = False

    # Forces thresholds to disable, used during cleanup so active thresholds don't stay on
    def disableThresholds(self):
        print("Disabling thresholds")
        for row in range(self.freq_bands_model.rowCount()):
            self.freq_bands_model.setThresholdState(row, False)

    # Initializes thread workers, which handle data capture and FFT calculation.
    # The workers are connected such that when they finish execution, they handle their own deletion.
    def initializeWorker(self):
        # Start our debug worker, used to play back files
        self.debug_thread = QtCore.QThread()
        self.debug_worker = DebugWorker(self.settings, self.electrodes_model)
        self.debug_worker.moveToThread(self.debug_thread)
        self.debug_worker.finished.connect(self.debug_thread.quit)
        self.debug_worker.finished.connect(self.debug_worker.deleteLater)
        self.debug_thread.finished.connect(self.debug_thread.deleteLater)
        self.debug_worker.finishedRead.connect(self.stopCapture)
        self.debug_thread.start()
        self.data_thread = QtCore.QThread()
        self.worker = DataWorker(self.settings, self.electrodes_model, self.freq_bands_model, self.plots)
        self.worker.moveToThread(self.data_thread)
        self.worker.finished.connect(self.data_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.data_thread.finished.connect(self.data_thread.deleteLater)
        self.worker.finishedCapture.connect(self.cleanup)
        self.worker.newDataReceived.connect(self.plot_widget.updatePlots)

        self.fft_thread = QtCore.QThread()
        self.fft_worker = FFTWorker(self.settings, self.electrodes_model, self.freq_bands_model)
        self.fft_worker.moveToThread(self.fft_thread)
        self.fft_worker.finished.connect(self.fft_thread.quit)
        self.fft_worker.finished.connect(self.fft_worker.deleteLater)
        self.fft_thread.finished.connect(self.fft_thread.deleteLater)
        self.worker.welchBufferChanged.connect(self.fft_worker.updateBuffers)
        self.worker.triggerFFT.connect(self.fft_worker.plotFFT)
        self.worker.finished.connect(self.fft_worker.terminate)
        self.fft_worker.newDataReceived.connect(self.updateFFTPlot)
        self.data_thread.start()
        self.fft_thread.start()

    # Requests redraw of the FFT plot with the data sent in buffer by the rate specified by fft_rate
    # We could reduce signal overhead by moving this pseudo-timer to the FFT thread.
    def updateFFTPlot(self, f, pxx):
        self.fft_rate = 15
        if perf_counter_ns() < self._last_fft_update + ((10**9)/self.fft_rate):
            return
        self.fft_plot.setData(y=pxx, x=f)
        self._last_fft_update = perf_counter_ns()

    # Toggles usage of rolling view (updates left to right, overwriting instead of scrolling the view)
    def setRollingView(self, enable):
        if(enable == QtCore.Qt.CheckState.Checked):
            self.rolling_view = True
        else:
            self.rolling_view = False

    # Informs the underlying plots of which channels are active
    def setActiveChannels(self):
        total_channels = self.electrodes_model.rowCount()
        active_channels = []
        for i in range(total_channels):
            # Select active channels
            idx = self.electrodes_model.index(i,1)
            if self.electrodes_model.itemFromIndex(idx).data(): 
                active_channels.append(i)
        self.plot_widget.setActiveChannels(active_channels, total_channels)
        self.fft_worker.setActiveChannels(active_channels)

    # Informs the underlying plots of which reference channel is active
    def setReferenceChannel(self):
        total_channels = self.electrodes_model.rowCount()
        active_reference = -1
        for i in range(total_channels):
            # Select reference channels
            idx = self.electrodes_model.index(i,2)
            if self.electrodes_model.itemFromIndex(idx).data():
                active_reference = i
        self.plot_widget.setReferenceChannel(active_reference)
        self.fft_worker.setReferenceChannel(active_reference)

# Custom class for allowing only one item selected at a time
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

# Table model that allows defining a fixed table
# For some reason, there's no existing implementation for this interface,
# so we make our own, even though it really doesn't need to do anything fancy.
# Currently designed as an array and can't be expanded after initialization. 
class TableModel(QtCore.QAbstractTableModel):
    def __init__(self, data, header):
        super().__init__()
        self._header = header
        self._data = data
    
    # Our table is stored as row-major, so we just need the array's length
    def rowCount(self, parent = QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._data)

    # We assume all subarrays are the correct size in our _data array.
    def columnCount(self, parent = QtCore.QModelIndex()):
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

    def headerData(self, section, orientation, role = QtCore.Qt.ItemDataRole.DisplayRole):
        if orientation == QtCore.Qt.Orientation.Horizontal and role == QtCore.Qt.ItemDataRole.DisplayRole:
            return QtCore.QVariant(self._header[section])
        return QtCore.QVariant() 

    # Our table is for viewing only, so we just return NoItemFlags.
    def flags(self, index):
        return QtCore.Qt.ItemFlag.NoItemFlags

# Extending TableModel for our specific purpose of defining thresholds and signals for said thresholds
# Table must be defined such that there are 4 columns, with the third column being the thresholds, and the fourth being
# whether the threshold is currently active or not (to prevent emit spam)
class FreqTableModel(TableModel):
    thresholdChanged = QtCore.pyqtSignal(QtCore.QModelIndex, bool)

    def __init__(self, data, header):
        super().__init__(data, header)

    def setValue(self, index, value, role = QtCore.Qt.ItemDataRole.EditRole):
        self.setData(index, value, role)
        if not self.data(index.siblingAtColumn(3)).value():
            if value > self.data(index.siblingAtColumn(2)).value():
                self.thresholdChanged.emit(index, True)
                self.setData(index.siblingAtColumn(3), True)
                return
        elif value < self.data(index.siblingAtColumn(2)).value():
            self.thresholdChanged.emit(index, False)
            self.setData(index.siblingAtColumn(3), False)

    # Allow us to reset the threshold state when starting a new capture
    def setThresholdState(self, row, state):
        idx = self.index(row, 3)
        self.setData(idx, state)
        self.thresholdChanged.emit(idx, False)

app = QtWidgets.QApplication(sys.argv)
window = MainWindow()
sys.exit(app.exec())