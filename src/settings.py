## Load settings from JSON file

import json
from PyQt6.QtCore import Qt
# SettingsHandler serves as the interface through which other modules
# can update the global settings variable, which serves as an unique source 
# of truth across the program. It also initializes the settings off of a local settings file.
class SettingsHandler():
    def __init__(self, file_name, settings):
        self.file_name = file_name
        self.settings = settings
        try:
            # Since settings are a dictionary, we update across all "categories" of our settings
            with open(self.file_name, 'r') as file:
                temp_settings = json.load(file)
                self.settings.update(temp_settings)
        # Can't read file, so we use defaults
        except (FileNotFoundError, ValueError):
            pass
        # Define our default settings, and then overwrite them with whatever is saved in settings
        # This should prevent a broken settings file from breaking the whole program
        self.settings.setdefault("socket", {})
        self.settings['socket'].setdefault("ip", "127.0.0.1")
        self.settings['socket'].setdefault("port", 8888)
        self.settings.setdefault("biosemi", {})
        self.settings['biosemi'].setdefault("phys_max", 262143)
        self.settings['biosemi'].setdefault("phys_min", -262144)
        self.settings['biosemi'].setdefault("digi_max", 8388607)
        self.settings['biosemi'].setdefault("digi_min", -8388608)
        self.settings['biosemi'].setdefault("fs", 2048)
        self.settings['biosemi'].setdefault("channels", {'A': 32, 'B': 32, 'EX': 8}) # (Set, Amount)
        self.settings['biosemi'].setdefault("ex_enabled", False)
        self.settings['biosemi'].setdefault("samples", 64)
        self.settings.setdefault("filter", {})
        self.settings['filter'].setdefault("decimating_factor", 1)
        self.settings['filter'].setdefault("lowpass_taps", 101)
        self.settings.setdefault("fft", {})
        self.settings['fft'].setdefault("welch_enabled", True)
        self.settings['fft'].setdefault("welch_window", 2048*4)
        self.settings.setdefault("threshold", {})
        self.settings['threshold'].setdefault("alpha", 0.5)
        self.settings.setdefault("serial", {})
        self.settings['serial'].setdefault("enabled", True)
        self.settings['serial'].setdefault("port", "ttyUSB0")
        self.settings['serial'].setdefault("baud_rate", '115200')
        self.settings.setdefault("file", {})
        self.settings['file'].setdefault('current_file', None)
        self.settings['file'].setdefault('directory', None)

    def saveSettings(self):
        try:
            with open(self.file_name, 'w+') as file:
                json.dump(self.settings, file)
        except Exception as err:
            print("Failed to save settings:", err)

    def setIp(self, ip):
        self.settings['socket']['ip'] = ip

    def setPort(self, port):
        self.settings['socket']['port'] = int(port)
    
    def setFs(self, fs):
        self.settings['biosemi']['fs'] = int(fs)
    
    # TODO: Utilize a more flexible scheme to allow extending more easily
    def setChannels(self, channels):
        if channels == "A1-B32 (64)":
            self.settings['biosemi']['channels'] = {'A': 32, 'B': 32}
        elif channels == "A1-A32 (32)":
            self.settings['biosemi']['channels'] = {'A': 32}
        elif channels == "A1-A16 (16)":
            self.settings['biosemi']['channels'] = {'A': 16}
        elif channels == "A1-A8 (8)":
            self.settings['biosemi']['channels'] = {'A': 8}
        else: return
        if self.settings['biosemi']['ex_enabled']:
            self.settings['biosemi']['channels']['EX'] = 8

    # Actiview calculates this based on the channels sent, could automate?
    def setSamples(self, samples):
        self.settings['biosemi']['samples'] = int(samples)

    def setDecimatingFactor(self, factor):
        self.settings['filter']['decimating_factor'] = int(factor)

    def setLowpassTaps(self, taps):
        self.settings['filter']['lowpass_taps'] = int(taps)

    def setWelchEnabled(self, enable):
        if(enable == Qt.CheckState.Checked):
            self.settings['fft']['welch_enabled'] = True
        else:
            self.settings['fft']['welch_enabled'] = False

    def setWelchWindow(self, window):
        self.settings['fft']['welch_window'] = int(window)

    def setExEnabled(self, enable):
        if(enable == Qt.CheckState.Checked):
            self.settings['biosemi']['ex_enabled'] = True
            self.settings['biosemi']['channels']['EX'] = 8
        else:
            self.settings['biosemi']['ex_enabled'] = False
            self.settings['biosemi']['channels'].pop('EX', None)
        
    def setAlphaThreshold(self, value):
        self.settings['threshold']['alpha'] = float(value)
        
    def setSerialEnabled(self, enable):
        if(enable == Qt.CheckState.Checked):
            self.settings['serial']['enabled'] = True
        else:
            self.settings['serial']['enabled'] = False

    def setSerialPort(self, port):
        self.settings['serial']['port'] = str(port)

    def setBaudRate(self, baud):
        self.settings['serial']['baud_rate'] = str(baud)

    def setFile(self, file):
        self.settings['file']['current_file'] = str(file)

    def setDirectory(self, directory):
        self.settings['file']['directory'] = str(directory)