from PyQt6 import QtCore
from collections import deque
from scipy import signal, fft
from time import sleep
import numpy
import global_vars
import threading
import struct
from utils import RingBuffer

## Seems to be slower...
# import pyfftw
# fft.set_global_backend(pyfftw.interfaces.scipy_fft)
# pyfftw.interfaces.cache.enable()
# pyfftw.interfaces.cache.set_keepalive_time(30)

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

    def startSocket(self, ip, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((ip, port))

    def terminate(self):
        self.is_capturing = False

    def readData(self):
        if not global_vars.DEBUG:
            self.startSocket(self.ip, self.port)
        x = 0
        packet_failed = 0
        decimate_enabled = False
        active_channels = []
        active_reference = -1
        # Make the right amount of space for receiving data
        total_channels = self.electrodes_model.rowCount()
        buffer_size = total_channels * self.samples * 3
        # Forcing this to true for now, might add a hard disable later
        welch_enabled = True
        welch_window = self.settings['fft']['welch_window']
        welch_buffers = []
        # We're seeking a 45 Hz update rate for the plots right now, so we calculate
        # how often we need to update in terms of samples received
        update_rate = int(self.fs/45)
        print("Update rate in samples:", update_rate)

        decimate_factor = self.settings['filter']['decimating_factor']
        if decimate_factor > 1: 
            decimate_enabled = True
            alias_filter = signal.firwin(numtaps=self.settings['filter']['lowpass_taps'], cutoff=self.fs/decimate_factor, pass_zero='lowpass', fs=self.fs)
        zf = [None for i in range(len(self.data_connectors))]
        # Initialize our buffers for FFT
        # We could skip this if FFT is not enabled, but I don't think it slows down regular time graphing too much
        for i in range(total_channels):
            buf = deque(maxlen=welch_window)
            buf.append(numpy.zeros(welch_window))
            welch_buffers.append(buf)

        for i in range(total_channels):
            # Select active channels
            idx = self.electrodes_model.index(i,1)
            if self.electrodes_model.itemFromIndex(idx).data(): 
                active_channels.append(i)
            # Select reference point
            idx = self.electrodes_model.index(i,2)
            if self.electrodes_model.itemFromIndex(idx).data():
                active_reference = i
        self.data_connectors[active_channels[0]].ignore_auto_range = False
        for i in active_channels:
            self.plots[i].show()
            self.data_connectors[i].resume()
            self.plots[i+total_channels].show()
            self.data_connectors[i+total_channels].resume()
        if global_vars.DEBUG:
            t = 0 # Used for generating sine signal continuously
        self.is_capturing = True
        while True:
            if global_vars.DEBUG:
                rng = numpy.random.default_rng()
                # data = rng.bytes(buffer_size)
                # Instead of doing random values, let's try generating a 10 [Hz] sine wave with some noise
                data = bytearray()
                lspace = numpy.linspace(t, t+(self.samples/self.fs), self.samples)
                noise_power = 0.00001 * self.fs/2
                noise = rng.normal(scale=numpy.sqrt(noise_power), size=lspace.shape)
                for j, i in enumerate(lspace):
                    for _ in range(total_channels):
                        if t > 2: val_orig = int((numpy.sin(2 * numpy.pi * 100 * i) + noise[j])*100) 
                        else: val_orig = int((numpy.sin(2 * numpy.pi * 10 * i) + noise[j])*10000) 
                        val = (val_orig).to_bytes(3, byteorder='little', signed=True)
                        if(len(val) > 3):
                            val = val[-3:]
                        data.extend(val)
                t += self.samples/self.fs
            else:
                # Read the next packet from the network
                data = self.sock.recv(buffer_size)

            # Extract all channel samples from the packet
            # We use a try statement as occasionally packet loss messes up the data
            try:
                # To increase CMRR, we can pick a reference point and subtract it from every other point we are reading
                if(active_reference > -1):
                    ref_values = data[n::total_channels]
                    ref_values = numpy.fromiter((int.from_bytes(data[idx:idx+3], 'little', signed=True) for idx in range(0,self.samples*3,3)), dtype=numpy.int32, count=self.samples)
                    print(ref_values)
                else:
                    ref_values = numpy.zeros(self.samples)
                
                for n in active_channels:
                    # Each data packet comes with multiple 3-byte samples at a time, interleaved such that
                    # the first sample of each channel is sent, then the second sample, and so on.
                    # We de-interleave the data to keep only the channels we care about.
                    samples_bytes = [data[idx:idx+3] for idx in range(n*3,buffer_size,total_channels)]
                    # The 3 bytes of each sample are formatted in little endian.
                    # We convert them to a 32bit integer, which automatically appends a zero to the LSB,
                    # to retain the signedness of the value.
                    samples = numpy.fromiter((int.from_bytes(samples_bytes[idx], 'little', signed=True) for idx in range(self.samples)), dtype=numpy.int32, count=self.samples)
                    
                    # We apply the reference value and gain
                    samples = (samples - ref_values)*self.gain
                    welch_buffers[n].append(samples)

                    # Send sample to plot
                    # Rate limited to only calculate the spectrum every once in a while, to avoid lag
                    # Since we're working with an entire set of samples, we need the corresponding x values
                    samples_time = numpy.linspace(x/self.fs, (x+self.samples)/self.fs, num=self.samples)
                    if welch_enabled:
                        if x % update_rate == 0:
                            if len(welch_buffers[n]) == welch_buffers[n].maxlen:
                                f, pxx = signal.welch(x=welch_buffers[n], fs=self.fs, nperseg=welch_window/5)
                                values = numpy.stack((f, pxx))
                                log_pxx = 10*numpy.log10(pxx)
                                self.data_connectors[n + (total_channels)].cb_set_data(log_pxx, f)
                                for band, [lower, upper] in global_vars.FREQ_BANDS.items():
                                    freq_filter = (values[0, :] >= lower) & (values[0, :] <= upper)
                                    band_values = values[1, freq_filter]
                                    idx = self.freq_bands_model.match(self.freq_bands_model.index(0,0), QtCore.Qt.ItemDataRole.DisplayRole, band)[0]
                                    try:
                                        self.freq_bands_model.setValue(idx.siblingAtColumn(1), float(numpy.sum(band_values)/numpy.sum(pxx)))
                                    except ZeroDivisionError:
                                        pass

                    if decimate_enabled:
                        if zf[n] is None:
                            zf[n] = signal.lfiltic(b=alias_filter, a=1, y=samples[0])
                            self.data_connectors[n].cb_append_data_array(samples, samples_time)
                        else: 
                            [samples], zf[n] = signal.lfilter(b=alias_filter, a=1, x=[samples], zi=zf[n])
                        if x % decimate_factor == 0:
                            self.data_connectors[n].cb_append_data_array(samples, samples_time)
                    else:
                        self.data_connectors[n].cb_append_data_array(samples, samples_time)

                    if not self.is_capturing:
                        self.finished.emit()
                        return

                x += self.samples
                if global_vars.DEBUG:
                    sleep(self.samples/self.fs)
                if packet_failed > 0:
                    packet_failed -= 1
                
            except IndexError:
                packet_failed += 1
                print("Packet reading failed! Failed attempts:", packet_failed)
                if packet_failed > global_vars.MAX_ERRORS:
                    print("Failed to read packets too many times, dropping connection")
                    self.finished.emit()
                    return
