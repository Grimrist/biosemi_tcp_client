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
        # Define our default settings, and then overwrite them with whatever is saved in settings
        # This should prevent a broken settings file from breaking the whole program
        self.settings['socket'] = {}
        self.settings['socket']['ip'] = "127.0.0.1"
        self.settings['socket']['port'] = 8888
        self.settings['biosemi'] = {}
        self.settings['biosemi']['phys_max'] = 262143 # Physical maximum value
        self.settings['biosemi']['phys_min'] = -262144 # Physical minimum value
        self.settings['biosemi']['digi_max'] = 8388607 # Digital maximum value
        self.settings['biosemi']['digi_min'] = -8388608 # Digital minimum value
        self.settings['biosemi']['fs'] = 16000 # Sampling rate
        self.settings['biosemi']['channels'] = {'A': 32, 'B': 32, 'EX': 8} # (Set, Amount)
        self.settings['biosemi']['ex_enabled'] = False
        self.settings['biosemi']['samples'] = 64 # Samples per channel
        self.settings['filter'] = {}
        self.settings['filter']['decimating_factor'] = 16 # Decimating factor
        self.settings['filter']['lowpass_taps'] = 15 # Taps used for anti-aliasing filter
        self.settings['fft'] = {}
        self.settings['fft']['welch_enabled'] = False
        self.settings['fft']['welch_window'] = 64*16

        try:
            with open(self.file_name, 'r') as file:
                # Since settings are a dictionary, we update across all "categories" of our settings
                temp_settings = json.load(file)
                for k in self.settings.keys():
                    self.settings[k].update(temp_settings[k])
        except FileNotFoundError:
            # Can't read file, so we use defaults
            pass
        except JSONDecodeError:
            # Settings file is broken, so we ignore it
            pass

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
        