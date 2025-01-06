import socket
import numpy
from time import sleep, perf_counter
from PyQt6 import QtCore
import pyedflib

# Worker class for opening a socket and generating a sine wave to read from
class DebugWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal()

    def __init__(self, settings, electrodes_model):
        super().__init__()
        port = settings['socket']['port']
        self.openSocket(port)
        self.samples = settings['biosemi']['samples']
        self.fs = settings['biosemi']['fs']
        self.electrodes_model = electrodes_model

    def openSocket(self, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(1)
        print("Opened socket with port", port)

    def terminate(self):
        self.terminated = True

    def generateSignal(self):
        self.terminated = False
        (client, port) = self.sock.accept()
        total_channels = self.electrodes_model.rowCount()
        t = 0
        while True:
            data = bytearray()
            lspace = numpy.linspace(t, t+(self.samples/self.fs), self.samples)
            noise_power = 0.01 * self.fs/2
            noise = numpy.random.normal(scale=numpy.sqrt(noise_power), size=lspace.shape)
            for j, i in enumerate(lspace):
                for _ in range(total_channels):
                    if t < 20: val_orig = int(numpy.sin(2 * numpy.pi * 10 * i)*10000 + noise[j]) 
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
                self.finished.emit()
                return
            if self.terminated:
                print("Terminating debug thread!")
                self.finished.emit()
                return

            t += self.samples/self.fs
            t = t % 40
            sleep(self.samples/self.fs)

    def generateSignalFromFile(self):
        self.terminated = False
        total_channels = self.electrodes_model.rowCount()
        f = pyedflib.EdfReader("../files/S001/S001R01.edf")
        n = f.signals_in_file
        signal_labels = f.getSignalLabels()
        sigbufs = numpy.zeros((n, f.getNSamples()[0]), dtype=numpy.int16)
        for i in numpy.arange(n):
            sigbufs[i, :] = f.readSignal(i)
        file_length = sigbufs.shape[1]
        sigbufs_bytes = bytearray()
        for samples in sigbufs.T:
            for sample in samples:
                val = int(sample).to_bytes(3, byteorder='little', signed=True)
                if(len(val) > 3):
                    val = val[-3:]
                sigbufs_bytes.extend(val)
        (client, port) = self.sock.accept()
        for i in range(0, file_length):
            # print("Sending data", sigbufs_bytes[(i*self.samples*total_channels*3):((i+1)*self.samples*total_channels*3)])
            # print(self.samples, self.fs)
            # print("Slices:", (i*self.samples*total_channels*3), ((i+1)*self.samples*total_channels*3))
            sent = client.send(sigbufs_bytes[(i*self.samples*total_channels*3):((i+1)*self.samples*total_channels*3)])
            if sent == 0:
                print("No data sent, terminating!")
                self.sock.close()
                self.finished.emit()
                return
            if self.terminated:
                print("Terminating debug thread!")
                self.finished.emit()
                return
            sleep(self.samples/self.fs)
        print("No more file to read, terminating")
        self.finished.emit()
        return