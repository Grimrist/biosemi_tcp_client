from PyQt6 import QtCore
from collections import deque

import numpy
# try:
#     from cupyx.scipy import signal
#     import cupyx.scipy.fft as cufft
#     from scipy import fft
#     fft.set_global_backend(cufft)
#     cuda_enabled = True
# except ImportError: 
from scipy import signal, fft
cuda_enabled = False
from dvg_ringbuffer import RingBuffer
import global_vars
from time import sleep, perf_counter_ns
import threading
import struct
import socket

## Seems to be slower...
import pyfftw
fft.set_global_backend(pyfftw.interfaces.scipy_fft)
pyfftw.interfaces.cache.enable()
pyfftw.interfaces.cache.set_keepalive_time(3)

## Controller for the worker so we don't hang the thread when we need stuff to happen

## Class definition for thread that receives data
# This was decoupled from the main application as it needed some custom signals for proper termination
class DataWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(str)

    def __init__(self, settings, electrodes_model, freq_bands_model, plots, data_connectors):
        super().__init__()
        ## Initialize all data derived from the client configuration
        self.samples = settings['biosemi']['samples']
        self.fs = settings['biosemi']['fs']
        # Give worker access to the models we use
        self.electrodes_model = electrodes_model
        self.freq_bands_model = freq_bands_model
        self.plots = plots
        self.data_connectors = data_connectors
        # Gain calculation to map quantized values to actual voltage (in uV)
        phys_range = settings['biosemi']['phys_max'] - settings['biosemi']['phys_min']
        digi_range = settings['biosemi']['digi_max'] - settings['biosemi']['digi_min']
        self.gain = phys_range/(digi_range * 2**8)
        # Network information
        self.ip = settings['socket']['ip']
        self.port = settings['socket']['port']
        self.settings = settings

    def setCapturing(self, status):
        self.is_capturing = status

    def startSocket(self, ip, port, buffer_size):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, buffer_size)
        self.sock.connect((ip, port))

    def terminate(self):
        self.is_capturing = False

    def readData(self):
        global cuda_enabled
        x = 0
        packet_failed = 0
        decimate_enabled = False
        active_channels = []
        active_reference = -1
        # Make the right amount of space for receiving data
        total_channels = self.electrodes_model.rowCount()
        buffer_size = total_channels * self.samples * 3
        # Start our socket with the right buffer limit
        self.startSocket(self.ip, self.port, buffer_size*2)
        # Forcing this to true for now, might add a hard disable later
        welch_enabled = True
        welch_window = self.settings['fft']['welch_window']
        welch_buffers = []
        # We're seeking a 45 Hz update rate for the plots right now, so we calculate
        # how often we need to update in terms of samples received
        update_rate = int(numpy.ceil(self.fs / 45 / self.samples))
        print("Update rate in packet count (aiming for 45 Hz):", update_rate)

        decimate_factor = self.settings['filter']['decimating_factor']
        if decimate_factor > 1: 
            decimate_enabled = True
            alias_filter = signal.firwin(numtaps=self.settings['filter']['lowpass_taps'], cutoff=self.fs/decimate_factor, pass_zero='lowpass', fs=self.fs)
        zf = [None for i in range(len(self.data_connectors))]
        # Initialize our buffers for FFT
        # We could skip this if FFT is not enabled, but I don't think it slows down regular time graphing too much
        for i in range(total_channels):
            buf = RingBuffer(capacity=welch_window)
            buf.extend(numpy.zeros(welch_window))
            welch_buffers.append(buf)

        # Determine which channels we're interested in reading from
        for i in range(total_channels):
            # Select active channels
            idx = self.electrodes_model.index(i,1)
            if self.electrodes_model.itemFromIndex(idx).data(): 
                active_channels.append(i)
            # Select reference point
            idx = self.electrodes_model.index(i,2)
            if self.electrodes_model.itemFromIndex(idx).data():
                active_reference = i
        # If there are no active channels, we have nothing to capture, so we abort
        if len(active_channels) == 0:
            print("No channels selected, stopping capture")
            self.finished.emit()
            return
        # Enable connectors that we will be using
        self.data_connectors[active_channels[0]].ignore_auto_range = False
        for i in active_channels:
            self.plots[i].show()
            self.data_connectors[i].resume()
            self.plots[i+total_channels].show()
            self.data_connectors[i+total_channels].resume()

        self.is_capturing = True
        while True:
            recv_data = self.sock.recv(buffer_size*2)
            start_total = perf_counter_ns()
            # if(len(recv_data) > buffer_size):
                # print("recv_data length:", len(recv_data), "buffer size", buffer_size)
            # Extract all channel samples from the packet
            # We use a try statement as occasionally packet loss messes up the data
            packets = int(len(recv_data) / buffer_size)
            for i in range(packets):
                data = recv_data[i*buffer_size:(i+1)*buffer_size]
                try:
                    start = perf_counter_ns()
                    a = numpy.zeros((total_channels, self.samples, 4), dtype='uint8')
                    # Each data packet comes with multiple 3-byte samples at a time, interleaved such that
                    # the first sample of each channel is sent, then the second sample, and so on.
                    # First we reshape the matrix such that each row is one 24-bit integer
                    start_test = perf_counter_ns()
                    reshaped_data = numpy.frombuffer(buffer=data, dtype='<b').reshape(-1, 3)
                    # De-interleave by transposing (Fortran order) and then reshaping into (channels * samples * bytes) shaped array
                    deinterleave_data = reshaped_data.reshape((total_channels, self.samples, 3), order='F')
                    # Copy bytes into new 4-byte array, change view to uint32, filter by only the channels we need and squeeze dimensions
                    a[:,:,-3:] = deinterleave_data
                    samples = a.view('int32')[[active_channels], :].reshape(len(active_channels), self.samples)
                    stop_test = perf_counter_ns()
                    # print("My method (ms):", (stop_test - start_test)/(10**6))
                    # To increase CMRR, we can pick a reference point and subtract it from every other point we are reading
                    if(active_reference > -1):
                        ref_values = a.view('int32')[active_reference, :].reshape(1, self.samples)
                    else:
                        ref_values = numpy.zeros(self.samples)

                    # We apply the reference value and gain
                    samples = (samples - ref_values)*self.gain
                    active_buffers = []
                    stop = perf_counter_ns()
                    # print("Processing time (ms):", (stop - start)/(10**6) )
                    # Send sample to plot
                    # Rate limited to only calculate the spectrum every once in a while, to avoid lag
                    # Since we're working with an entire set of samples, we need the corresponding x values
                    samples_time = numpy.linspace(x/self.fs, (x+self.samples)/self.fs, num=self.samples)
                    if welch_enabled:
                        if x % update_rate == 0:
                            for i, channel in enumerate(active_channels):
                                welch_buffers[channel].extend(samples[i])
                                active_buffers.append(welch_buffers[channel])
                            active_buffers = numpy.vstack(active_buffers)
                            avg_buffer = numpy.average(active_buffers, axis=0)
                            f, pxx = signal.welch(x=avg_buffer, fs=self.fs, nperseg=welch_window/5)
                            pxx[pxx == 0] = 0.0000000001
                            log_pxx = 10*numpy.log10(pxx)
                            if cuda_enabled:
                                self.data_connectors[n + (total_channels)].cb_set_data(log_pxx.get(), f.get())
                            else: 
                                self.data_connectors[channel + (total_channels)].cb_set_data(log_pxx, f)
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
                            stop = perf_counter_ns()
                            # print("Welch time (ms): ", (stop - start)/(10**6))

                        # if decimate_enabled:
                        #     if zf[n] is None:
                        #         zf[n] = signal.lfiltic(b=alias_filter, a=1, y=samples[0])
                        #         self.data_connectors[n].cb_append_data_array(samples, samples_time)
                        #     else: 
                        #         [samples], zf[n] = signal.lfilter(b=alias_filter, a=1, x=[samples], zi=zf[n])
                        #     if x % decimate_factor == 0:
                        #         self.data_connectors[n].cb_append_data_array(samples, samples_time)
                        # else:
                    start = perf_counter_ns()
                    for i, channel in enumerate(active_channels):
                        # print("Samples:", samples)
                        self.data_connectors[channel].cb_append_data_array(samples[i], samples_time)

                    if not self.is_capturing:
                        self.finished.emit()
                        return
                    stop = perf_counter_ns()
                    # print("Allocate data (ms):", (stop - start)/(10**6))
                    x += self.samples
                    if packet_failed > 0:
                        packet_failed -= 1
                    
                except IndexError:
                    packet_failed += 1
                    print("Packet reading failed! Failed attempts:", packet_failed)
                    if packet_failed > global_vars.MAX_ERRORS:
                        print("Failed to read packets too many times, dropping connection")
                        self.finished.emit()
                        return
            stop_total = perf_counter_ns()
            # print("Total time (ms):", (stop_total - start_total)/(10**6))
