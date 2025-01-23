from pyqtgraph import PlotWidget, PlotCurveItem
import pyqtgraph
from dvg_ringbuffer import RingBuffer
from time import perf_counter_ns
import numpy
import tsdownsample
from utils import PlotMultiCurveItem

class RealTimePlot(PlotWidget):
    def initializeGraphs(self, fs, total_channels):
        time_length = 1.5 # Data buffer length in seconds
        self.buffer_size = int(fs*time_length)
        self._last_update = 0
        self._received = 0
        self.time_buffer = RingBuffer(capacity=self.buffer_size, dtype='float64')
        # Generate plots for time-domain graphing
        self.plots = []
        self.buffers = []
        # Pre-emptively generate color array for curves
        self.colors = numpy.zeros((total_channels, 4))
        for i in range(total_channels):
            self.colors[i,:] = [i/(total_channels), 0.8, 0.9, 1]
        self.plot = PlotMultiCurveItem(skipFiniteCheck=True, connect='pairs', clickable=True)
        self.plot.sigClicked.connect(self.autoscaleToData)
        self.plot.setSkipFiniteCheck(True)
        self.plot.setSegmentedLineMode('on')
        self.addItem(self.plot)
        buffer = RingBuffer(capacity=self.buffer_size, dtype='float64')
        self.buffers.append(buffer)

    def cleanup(self):
        print("Cleaning up")
        self.is_capturing = False
        self.removeItem(self.plot)
        self.plot.deleteLater()

    def updatePlots(self, channels, data, time_range):
        self.update_rate = 5
        # Scrolling faster than our update rate makes the graphing feel smoother
        self.scroll_rate = 30
        self.time_buffer.extend(time_range)
        self._received += 1
        for i, channel in enumerate(channels):
            self.buffers[channel].extend(data[i])
        if perf_counter_ns() > self._last_update + ((10**9)/self.scroll_rate):
            if self.time_buffer.is_full:
                time_unit = time_range[1] - time_range[0]
                self.getViewBox().translateBy(x=(time_range[-1] - time_range[0] + time_unit)*self._received)
                self.setLimits(xMin=self.time_buffer[0], xMax=self.time_buffer[-1])
            self._received = 0
        if perf_counter_ns() < self._last_update + ((10**9)/self.update_rate):
            return
        self._last_update = perf_counter_ns()
        time_unit = time_range[1] - time_range[0]
        (w,h) = self.getViewBox().viewPixelSize()
        [[xmin, xmax], [ymin, ymax]] = self.getViewBox().viewRange()
        block_size = int(numpy.ceil(w / time_unit))
        num_bin = int(numpy.ceil((len(self.time_buffer) // block_size)/2.) * 2)
        if num_bin < 3:
            num_bin = 3
        self.offset_factor = 400
        for i, channel in enumerate(channels):
            buffer = self.buffers[channel].__array__() - self.offset_factor*i
            if not ((buffer >= ymin) & (buffer <= ymax)).any():
                continue
            time = self.time_buffer.__array__()
            view = tsdownsample.MinMaxLTTBDownsampler().downsample(buffer, n_out=num_bin, parallel=True)
            clip = numpy.clip(buffer[view], a_min=ymin, a_max=ymax)
            self.plot.setData(y=clip, x=time[view], colors=color)

    def autoscaleToData(self, item):
        idx = self.plots.index(item)
        min_val = numpy.min(self.buffers[idx]) - self.offset_factor*idx
        max_val = numpy.max(self.buffers[idx]) - self.offset_factor*idx
        self.setYRange(min=min_val, max=max_val)
