import socket
import numpy
from time import sleep, perf_counter
from PyQt6 import QtCore

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


