from collections.abc import Sequence
import numpy as np

## Ring buffer using Numpy, meant to replace a 1D deque for more efficiency
# As a caveat, this does need me to change the data parsing to work in blocks, but it should've done that from the start anyway.
class RingBuffer(Sequence):
    def __init__(self, maxlen, dtype=float):
        self._arr = np.empty(maxlen, dtype)
        self._idx = 0
        self.maxlen = maxlen

    def append(self, arr):
        arr = [arr]
        maxlen = self.maxlen
        for i, val in enumerate(arr):
            self._idx = (self._idx + i) % maxlen
            self._arr[self._idx] = val

    def __len__(self):
        return self.maxlen

    def __getitem__(self, item):
        return self._arr[item]
