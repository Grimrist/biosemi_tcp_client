from PyQt6 import QtCore
from dvg_ringbuffer import RingBuffer
import numpy
from scipy import signal, fft
import pyfftw
fft.set_global_backend(pyfftw.interfaces.scipy_fft)
pyfftw.interfaces.cache.enable()
pyfftw.interfaces.cache.set_keepalive_time(3)

import global_vars

class FFTWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal()

    def __init__(self, settings, electrodes_model, freq_bands_model):
        super().__init__()
        # Give worker access to the models we use
        self.settings = settings
        self.electrodes_model = electrodes_model
        self.freq_bands_model = freq_bands_model

    def terminate(self):
        self.finished.emit()

    def updateBuffers(self, channel, samples):
        self.welch_buffers[channel].extend(samples)

    def initializeBuffers(self, total_channels):
        self.welch_buffers = []
        for i in range(total_channels):
            buf = RingBuffer(capacity=self.welch_window)
            buf.extend(numpy.zeros(self.welch_window))
            self.welch_buffers.append(buf)

    def setDataConnector(self, connector):
        self.data_connector = connector

    def initializeWorker(self):
        self.welch_window = self.settings['fft']['welch_window']
        self.fs = self.settings['biosemi']['fs']
        self.total_channels = self.electrodes_model.rowCount()
        # Determine which channels we're interested in reading from
        self.active_channels = []
        for i in range(self.total_channels):
            # Select active channels
            idx = self.electrodes_model.index(i,1)
            if self.electrodes_model.itemFromIndex(idx).data(): 
                self.active_channels.append(i)
        self.initializeBuffers(self.total_channels)

    def plotFFT(self):
        active_buffers = []
        for i in self.active_channels:
            active_buffers.append(self.welch_buffers[i])
        active_buffers = numpy.vstack(active_buffers)
        avg_buffer = numpy.average(active_buffers, axis=0)
        f, pxx = signal.welch(x=avg_buffer, fs=self.fs, nperseg=self.welch_window//5)
        pxx[pxx == 0] = 0.0000000001
        log_pxx = 10*numpy.log10(pxx*1000)
        self.data_connector.cb_set_data(log_pxx, f)
        for band, [lower, upper] in global_vars.FREQ_BANDS.items():
            freq_filter = (f >= lower) & (f <= upper)
            band_values = pxx[freq_filter]
            idx = self.freq_bands_model.match(self.freq_bands_model.index(0,0), QtCore.Qt.ItemDataRole.DisplayRole, band)[0]
            band_sum = numpy.sum(band_values)
            pxx_sum = numpy.sum(pxx)
            if pxx_sum == 0 or band_sum == 0:
                div = 0
            else: div = float(band_sum / pxx_sum)
            self.freq_bands_model.setValue(idx.siblingAtColumn(1), div)