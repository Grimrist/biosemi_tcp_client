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
    newDataReceived = QtCore.pyqtSignal(numpy.ndarray, numpy.ndarray)
    bandsUpdated = QtCore.pyqtSignal(list)

    def __init__(self, settings, electrodes_model, freq_bands_model):
        super().__init__()
        # Give worker access to the models we use
        self.settings = settings
        self.electrodes_model = electrodes_model
        self.freq_bands_model = freq_bands_model
        self.ref_channel = -1

    def terminate(self):
        self.finished.emit()

    def updateBuffers(self, samples):
        for i, channel in enumerate(samples):
            self.welch_buffers[i].extend(channel)

    def initializeBuffers(self, total_channels):
        self.welch_buffers = []
        for i in range(total_channels):
            buf = RingBuffer(capacity=self.welch_window)
            buf.extend(numpy.zeros(self.welch_window))
            self.welch_buffers.append(buf)

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

    def setActiveChannels(self, channels):
        self.active_channels = channels

    def setReferenceChannel(self, channel):
        self.ref_channel = channel

    def plotFFT(self):
        # No channels selected, so we don't plot anything
        if len(self.active_channels) == 0:
            return
        active_buffers = []
        if self.ref_channel != -1:
            ref = self.welch_buffers[self.ref_channel]
        else:
            ref = 0
        for i in self.active_channels:
            active_buffers.append(self.welch_buffers[i].__array__() - ref)
        active_buffers = numpy.vstack(active_buffers)
        avg_buffer = numpy.average(active_buffers, axis=0)
        f, pxx = signal.welch(x=avg_buffer, fs=self.fs, nperseg=self.welch_window//5)
        pxx[pxx == 0] = 0.0000000001
        log_pxx = 10*numpy.log10(pxx*1000)
        self.newDataReceived.emit(f, log_pxx)

        # Determine our new frequency band values, and then update our model so the rest of the app gets notified
        divs = []
        for band, [lower, upper] in global_vars.FREQ_BANDS.items():
            freq_filter = (f >= lower) & (f <= upper)
            band_values = pxx[freq_filter]
            idx = self.freq_bands_model.match(self.freq_bands_model.index(0,0), QtCore.Qt.ItemDataRole.DisplayRole, band)[0]
            band_sum = numpy.sum(band_values)
            pxx_sum = numpy.sum(pxx)
            if pxx_sum == 0 or band_sum == 0:
                div = 0
            else: div = float(band_sum / pxx_sum)
            divs.append(div)
            self.freq_bands_model.setValue(idx.siblingAtColumn(1), div)
        self.bandsUpdated.emit(divs)