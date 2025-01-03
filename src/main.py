import socket   # used for TCP/IP communication
from settings import SettingsHandler    
import sys
from PyQt6 import QtWidgets, QtCore, QtGui
import pyqtgraph
from pglive.sources.data_connector import DataConnector
from pglive.sources.live_plot import LiveLinePlot
from pglive.sources.live_plot_widget import LivePlotWidget
from pglive.sources.live_axis_range import LiveAxisRange
from pglive.sources.live_axis import LiveAxis
from data_parser import DataWorker
from custom_live_plot import CustomLivePlotWidget
import global_vars

if len(sys.argv) > 1 and sys.argv[1] == "-d":
    global_vars.DEBUG = True

# MainWindow holds all other windows, initializes the settings,
# and connects every needed signal to its respective slot.
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
        self.selection_window.channels_box.currentTextChanged.connect(self.setTotalChannels)
        self.selection_window.ex_electrodes_box.checkStateChanged.connect(self.setExEnabled)

        # Graph control
        self.selection_window.channel_selector.selectionModel().selectionChanged.connect(self.setActiveChannels)
        self.selection_window.reference_selector.selectionModel().selectionChanged.connect(self.setReference)
        
        self.selection_window.start_button.clicked.connect(self.graph_window.startCapture)
        self.selection_window.stop_button.clicked.connect(self.graph_window.stopCapture)

        self.selection_window.fft_checkbox.checkStateChanged.connect(self.graph_window.toggleFFT)

        # Filter settings
        self.selection_window.decimating_factor_box.valueChanged.connect(self.settings_handler.setDecimatingFactor)
        self.selection_window.decimating_taps_box.valueChanged.connect(self.settings_handler.setLowpassTaps)

        # FFT settings
        self.selection_window.welch_window_box.valueChanged.connect(self.settings_handler.setWelchWindow)
        self.selection_window.fft_checkbox.checkStateChanged.connect(self.settings_handler.setWelchEnabled)

        # Thresholds
        # Just a quick prototype, this needs custom classes
        self.selection_window.alpha_threshold_box.valueChanged.connect(self.settings_handler.setAlphaThreshold)
        self.selection_window.alpha_threshold_box.valueChanged.connect(self.selection_window.setAlphaThreshold)

        self.freq_bands_model.thresholdChanged.connect(self.selection_window.updateThresholdDisplay)
        ###

        # Show window
        self.setCentralWidget(main_widget)
        self.show()

    # Initializes the model that holds the channel and reference selection
    def initializeElectrodes(self):
        if self.electrodes_model is not None:
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

    def initializeBands(self):
        if self.freq_bands_model is not None:
            self.freq_bands_model.clear()
        else: 
            data = [[k,0, 0.5, False] for k in global_vars.FREQ_BANDS.keys()]
            self.freq_bands_model = FreqTableModel(data, ["Bands", "Relative Power", "Threshold", "Status"])

    def setTotalChannels(self, channels):
        self.settings_handler.setChannels(channels)
        self.initializeElectrodes()

    def setExEnabled(self, enable):
        self.settings_handler.setExEnabled(enable)
        self.initializeElectrodes()

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
        self.settings_handler.saveSettings()
        self.graph_window.stopCapture()
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
        self.freq_bands_model = freq_bands_model
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
        freq_bands_table.setColumnHidden(2, True)
        freq_bands_table.setColumnHidden(3, True)
        measurements_layout.addWidget(freq_bands_table)
        
        # Thresholds
        threshold_settings = QtWidgets.QWidget()
        threshold_settings_layout = QtWidgets.QFormLayout()
        self.alpha_threshold_box = QtWidgets.QDoubleSpinBox()
        self.alpha_threshold_box.setRange(0, 1)
        self.alpha_threshold_box.setValue(self.settings['threshold']['alpha'])
        threshold_settings_layout.addRow(QtWidgets.QLabel("Alpha threshold"), self.alpha_threshold_box)
        threshold_settings.setLayout(threshold_settings_layout)
        measurements_layout.addWidget(threshold_settings)

        # TODO: Revisit this eventually, feels like it could be designed better
        self.red_icon = QtGui.QPixmap("./icons/red_icon.png")
        self.black_icon = QtGui.QPixmap("./icons/black_icon.png")
        indicator_widget = QtWidgets.QWidget()
        indicator_layout = QtWidgets.QFormLayout()
        self.band_indicators = []
        for freq_band in global_vars.FREQ_BANDS.keys():
            indicator = QtWidgets.QLabel(freq_band + " under threshold.")
            indicator_img = QtWidgets.QLabel()
            indicator_img.setPixmap(self.black_icon)
            indicator_layout.addRow(indicator_img, indicator)
            self.band_indicators.append((indicator, indicator_img))
        indicator_widget.setLayout(indicator_layout)
        measurements_layout.addWidget(indicator_widget)
        
        verticalSpacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        measurements_layout.addItem(verticalSpacer) 
        measurements_window.setLayout(measurements_layout)
        self.addTab(measurements_window, "Measurements")

    def updateThresholdDisplay(self, index, status):
        band = self.band_indicators[index.row()][0].text().split()[0]
        if status == True:
            self.band_indicators[index.row()][0].setText(band + " over threshold")
            self.band_indicators[index.row()][1].setPixmap(self.red_icon)
        else:
            self.band_indicators[index.row()][0].setText(band + " under threshold")
            self.band_indicators[index.row()][1].setPixmap(self.black_icon)

    def setAlphaThreshold(self, value):
        alpha = self.freq_bands_model.match(self.freq_bands_model.index(0,0), QtCore.Qt.ItemDataRole.DisplayRole, "Alpha")[0]
        self.freq_bands_model.setData(alpha.siblingAtColumn(2), value)

# GraphWindow currently serves the dual purpose of handling the graph display as well as
# implementing the plotting logic itself. It might be a good idea to separate the two
class GraphWindow(QtWidgets.QWidget):
    def __init__(self, settings, electrodes_model, freq_bands_model):
        super().__init__()
        self.settings = settings
        self.electrodes_model = electrodes_model
        self.freq_bands_model = freq_bands_model
        self.welch_enabled = True
        self.is_capturing = False
        self.restart_queued = False
        self.graph_layout = QtWidgets.QVBoxLayout()
        self.initializePlotWidgets()
        if not self.settings['fft']['welch_enabled']:
            self.fft_plot.hide()
        self.setLayout(self.graph_layout)

    def toggleFFT(self, checked):
        if(checked == QtCore.Qt.CheckState.Checked):
            self.fft_plot.show()
        else:
            self.fft_plot.hide()

    # Initializes the plot widgets, alongside their axis configuration
    def initializePlotWidgets(self):
        self.plot_widget = CustomLivePlotWidget(title="EEG time-domain plot")
        self.plot_widget.add_crosshair(crosshair_pen=pyqtgraph.mkPen(color="red", width=1), crosshair_text_kwargs={"color": "white"})
        self.plot_widget.getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_widget.getAxis('left').enableAutoSIPrefix(False)
        self.plot_widget.setLabel('bottom', "Time", "s")
        self.plot_widget.setLabel('left', "Magnitude", "uV")
        self.graph_layout.addWidget(self.plot_widget)
        fft_plot_bottom_axis = LiveAxis("bottom", tick_angle=45)
        fft_plot_left_axis = LiveAxis("left")
        self.fft_plot = LivePlotWidget(title="Power spectral density graph", axisItems={'bottom': fft_plot_bottom_axis, 'left': fft_plot_left_axis})
        self.fft_plot.setLogMode(True, False)
        self.fft_plot.getAxis('bottom').enableAutoSIPrefix(False)
        self.fft_plot.getAxis('left').enableAutoSIPrefix(False)
        self.fft_plot.setLabel('bottom', "Frequency", "Hz")
        self.fft_plot.setLabel('left', "Power", "dB")
        self.fft_plot.getAxis('bottom').setStyle(tickTextWidth=1)
        self.fft_plot.add_crosshair(crosshair_pen=pyqtgraph.mkPen(color="red", width=1), crosshair_text_kwargs={"color": "white"})
        self.graph_layout.addWidget(self.fft_plot)

    # Initializes graphs so I don't have to constantly repeat myself
    def initializeGraphs(self):
        total_channels = self.electrodes_model.rowCount()
        fs = self.settings['biosemi']['fs']
        self.data_connectors = []
        self.plots = []
        # Generate plots for time-domain graphing
        for i in range(total_channels):
            plot = LiveLinePlot(pen=pyqtgraph.hsvColor(i/(total_channels), 0.8, 0.9))
            data_connector = DataConnector(plot, max_points=(fs*2)/self.settings['filter']['decimating_factor'], plot_rate=30, ignore_auto_range=True)
            data_connector.pause()
            self.data_connectors.append(data_connector)
            self.plots.append(plot)
            self.plot_widget.addItem(plot)
            plot.hide()
        # Generate plots for FFT graphing. We don't define max_points because we just set the data directly.
        for i in range(total_channels):
            plot = LiveLinePlot(pen=pyqtgraph.hsvColor(i/(total_channels), 0.8, 0.9))
            data_connector = DataConnector(plot, plot_rate=30)
            data_connector.pause()
            self.data_connectors.append(data_connector)
            self.plots.append(plot)
            self.fft_plot.addItem(plot)
            plot.hide()
        return

    # Something is going horribly wrong every time we restart,
    # so we just go nuclear: delete everything and rebuild.
    def startCapture(self):
        if not self.is_capturing:
            self.initializeGraphs()
            self.initializeWorker()
        else:
            self.restart_queued = True
            self.stopCapture()

    def stopCapture(self):
        if not self.is_capturing:
            return
        self.worker.terminate()

    def cleanup(self):
        self.is_capturing = False
        for connector in self.data_connectors:
            connector.deleteLater()
        for plot in self.plots:
            plot.deleteLater()
        self.plot_widget.deleteLater()
        self.fft_plot.deleteLater()
        self.initializePlotWidgets()
        if not self.settings['fft']['welch_enabled']:
            self.fft_plot.hide()
        if not global_vars.DEBUG:
            self.sock.close()
        if self.restart_queued:
            self.initializeGraphs()
            self.initializeWorker()

    # Initialize data worker and thread
    def initializeWorker(self):
        self.data_thread = QtCore.QThread()
        self.worker = DataWorker(self.settings, self.electrodes_model, self.freq_bands_model, self.plots, self.data_connectors)
        self.worker.moveToThread(self.data_thread)
        self.data_thread.started.connect(self.worker.readData)
        self.worker.finished.connect(self.data_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.data_thread.finished.connect(self.data_thread.deleteLater)
        self.data_thread.finished.connect(self.cleanup)
        self.data_thread.start()
        print("Reading from ip %s and port %s" % (self.settings['socket']['ip'], self.settings['socket']['port']))
        self.is_capturing = True
        self.restart_queued = False


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

app = QtWidgets.QApplication(sys.argv)
window = MainWindow()
sys.exit(app.exec())