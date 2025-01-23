DEBUG = False

FREQ_BANDS = {
    "Delta": [1, 3],
    "Theta": [4, 7],
    "Alpha": [8, 12],
    "Beta": [13, 30],
    "Gamma": [30, 100]
}

CHANNELS = [
    "Fp1", "AF7", "AF3", "F1", "F3", "F5", "F7", "FT7", "FC5", "FC3",
    "FC1", "C1", "C3", "C5", "T7", "TP7", "CP5", "CP3", "CP1", "P1",
    "P3", "P5", "P7", "P9", "PO7", "PO3", "O1", "Iz", "Oz", "POz",
    "Pz", "CPz", "Fpz", "Fp2", "AF8", "AF4", "AFz", "Fz", "F2", "F4",
    "F6", "F8", "FT8", "FC6", "FC4", "FC2", "FCz", "Cz", "C2", "C4",
    "C6", "T8", "TP8", "CP6", "CP4", "CP2", "P2", "P4", "P6", "P8",
    "P1O", "PO8", "PO4", "O2"
]

MAX_ERRORS = 5
