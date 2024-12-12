## Load settings from JSON file

import json

class SettingsHandler():
    def __init__(self, file_name, settings):
        self.file_name = file_name
        self.settings = settings
        # Define our default settings, and then overwrite them with whatever is saved in settings
        # This should prevent a broken settings file from breaking the whole program
        self.settings['socket'] = {}
        self.settings['socket']['ip'] = "127.0.0.1"
        self.settings['socket']['port'] = 8080
        self.settings['biosemi'] = {}
        self.settings['biosemi']['phys_max'] = 262143 # Physical maximum value
        self.settings['biosemi']['phys_min'] = -262144 # Physical minimum value
        self.settings['biosemi']['digi_max'] = 8388607 # Digital maximum value
        self.settings['biosemi']['digi_min'] = -8388608 # Digital minimum value
        self.settings['biosemi']['fs'] = 16000 # Sampling rate
        self.settings['biosemi']['channels'] = [('A', 32), ('B', 32), ('EX', 8)] # (Set, Amount)
        self.settings['biosemi']['samples'] = 64 # Samples per channel
        self.settings['biosemi']['buffer_size'] = 0
        self.settings['fft'] = {}
        self.settings['fft']['welch_enabled'] = False
        self.settings['fft']['welch_window'] = 64*16

        try:
            with open(self.file_name, 'r') as file:
                self.settings.update(json.load(file))
        except FileNotFoundError:
            # Can't read file, so we use defaults
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
    
    # TODO: Implement this properly when there is actual channel mode selection
    def setChannels(self, channels):
        self.settings['biosemi']['channels'] = channels

    # Actiview calculates this based on the channels sent, could automate?
    def setSamples(self, samples):
        self.settings['biosemi']['samples'] = int(samples)

    def setBufferSize(self, buffer_size):
        self.settings['biosemi']['buffer_size'] = int(buffer_size)
    
    def setWelchEnabled(self, enable):
        self.settings['fft']['welch_enabled'] = bool(enable)

    def setWelchWindow(self, window):
        self.settings['fft']['welch_window'] = int(window)


