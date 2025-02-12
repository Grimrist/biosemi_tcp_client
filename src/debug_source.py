import socket
import numpy
from time import sleep, perf_counter
from PyQt6 import QtCore
import pyedflib

# Worker class for opening a socket and generating a sine wave to read from
class DebugWorker(QtCore.QObject):
    finishedRead = QtCore.pyqtSignal()
    finished = QtCore.pyqtSignal()

    def __init__(self, settings, electrodes_model):
        super().__init__()
        self.settings = settings
        self.electrodes_model = electrodes_model

    def openSocket(self, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(1)
        print("Opened socket with port", port)

    def terminate(self):
        self.terminated = True

    def initializeData(self, settings):
        self.port = settings['socket']['port']
        self.samples = settings['biosemi']['samples']
        self.fs = settings['biosemi']['fs']

    def generateSignal(self):
        self.initializeData(self.settings)
        self.openSocket(self.port)
        self.terminated = False
        (client, port) = self.sock.accept()
        total_channels = self.electrodes_model.rowCount()
        t = 0
        while True:
            data = bytearray()
            lspace = numpy.linspace(t, t+(self.samples/self.fs), self.samples)
            noise_power = 0 * self.fs/2
            for j, i in enumerate(lspace):
                for _ in range(total_channels):
                    noise = numpy.random.normal(scale=numpy.sqrt(noise_power), size=lspace.shape)
                    if t < 10: val_orig = int(numpy.sin(2 * numpy.pi * 10 * i)*1000 + noise[j]) 
                    else: val_orig = int(numpy.sin(2 * numpy.pi * 10 * i)*10 + noise[j]) 
                    val = (val_orig).to_bytes(3, byteorder='little', signed=True)
                    if(len(val) > 3):
                        val = val[-3:]
                    data.extend(val)
            sent = client.send(data)
            # If we sent no data, then the connection has been broken
            if sent == 0:
                print("No data sent, terminating!")
                self.sock.close()
                self.finishedRead.emit()
                return
            if self.terminated:
                print("Terminating debug thread!")
                self.finishedRead.emit()
                return

            t += self.samples/self.fs
            t = t % 20
            sleep(self.samples/self.fs)

    def generateSignalFromFile(self):
        self.initializeData(self.settings)
        self.openSocket(self.port)
        self.terminated = False
        total_channels = self.electrodes_model.rowCount()
        f = pyedflib.EdfReader(self.settings['file']['current_file'])
        n = f.signals_in_file
        signal_labels = f.getSignalLabels()
        print(signal_labels)
        sigbufs = numpy.zeros((total_channels, f.getNSamples()[0]), dtype=numpy.int32)
        for i in numpy.arange(total_channels):
            sigbufs[i, :] = f.readSignal(i)
        file_length = sigbufs.shape[1]
        sigbufs_bytes = bytearray()
        for samples in sigbufs.T:
            for sample in samples:
                val = int(sample).to_bytes(3, byteorder='little', signed=True)
                if(len(val) > 3):
                    val = val[-3:]
                sigbufs_bytes.extend(val)
        print("Finished processing file, waiting for client")
        (client, port) = self.sock.accept()
        print("Connected to client, sending data")
        for i in range(0, file_length):
            sent = client.send(sigbufs_bytes[(i*self.samples*total_channels*3):((i+1)*self.samples*total_channels*3)])
            if sent == 0:
                print("No data sent, terminating!")
                self.sock.close()
                f.close()
                self.finishedRead.emit()
                return
            if self.terminated:
                print("Terminating debug thread!")
                self.sock.close()
                f.close()
                self.finishedRead.emit()
                return
            sleep(self.samples/self.fs)
        print("No more file to read, terminating")
        self.sock.close()
        f.close()
        self.finishedRead.emit()
        return