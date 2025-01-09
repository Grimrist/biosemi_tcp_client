from PyQt6 import QtCore, QtSerialPort

class SerialHandler(QtCore.QObject):
    def __init__(self, write_enabled):
        super().__init__()
        self.is_open = False
        self.write_enabled = write_enabled

    def startSerial(self, port, baud):
        self.serial = QtSerialPort.QSerialPort(port)
        self.serial.setBaudRate(baud)
        self.is_open = self.serial.open(QtCore.QIODeviceBase.OpenModeFlag.WriteOnly)
        self.serial.readyRead.connect(self.read)
        if not self.is_open:
            print('\033[91m' + "Failed to open serial port!" + '\033[0m')
            return

    def stopSerial(self):
        if not self.is_open:
            return
        self.write(b'0')
        self.serial.waitForBytesWritten(100)
        self.serial.close()
        self.is_open = False

    def write(self, data):
        if not self.is_open or not self.write_enabled:
            return
        print("Writing", data)
        if self.serial.write(data) == -1:
            print("Failed to write!", self.serial.errorString())

    def setWriteEnabled(self, enable):
        if(enable == QtCore.Qt.CheckState.Checked):
            self.write_enabled = True
        else:
            self.write_enabled = False
            # TODO: Consider how this should work, we likely want it to fully turn off
            # when turning off the serial, and possibly send a signal when the
            # threshold is active when checked
            self.write(b'0')
    
    def read(self):
        print("Reading!")
        print(self.serial.readAll())