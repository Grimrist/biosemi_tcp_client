from pyqtgraph import PlotWidget, PlotCurveItem, PlotItem, InfiniteLine
import pyqtgraph
from dvg_ringbuffer import RingBuffer
from time import perf_counter_ns
import numpy
import tsdownsample
from utils import RollingRingBuffer

class RealTimePlot(PlotWidget):
    def initializeGraphs(self, fs, total_channels, buffer_size, rolling_view):
        self.buffer_size = buffer_size
        self._last_update = 0
        self._received = 0
        self.offset_factor = 2
        self.avgs = numpy.zeros(total_channels)
        self.time_buffer = RingBuffer(capacity=self.buffer_size, dtype='float64')
        self.rolling_view = rolling_view
        # Generate plots for time-domain graphing
        self.plots = []
        self.buffers = []
        for i in range(total_channels):
            color = pyqtgraph.hsvColor(i/(total_channels), 0.8, 0.9)
            plot = PlotCurveItem(pen=pyqtgraph.mkPen(color=color, width=1), skipFiniteCheck=True, clickable=True)
            plot.sigClicked.connect(self.autoscaleToData)
            plot.setSkipFiniteCheck(True)
            plot.setSegmentedLineMode('on')
            self.addItem(plot)
            self.plots.append(plot)
            if(self.rolling_view):
                buffer = RollingRingBuffer(capacity=self.buffer_size, dtype='float64')
            else:
                buffer = RingBuffer(capacity=self.buffer_size, dtype='float64')
            self.buffers.append(buffer)
        if self.rolling_view:
            self.time_buffer.extend(range(self.buffer_size))
            self.roll_line = InfiniteLine(pen='r')
            self.addItem(self.roll_line)
            self.setLimits(xMin=self.time_buffer[0], xMax=self.time_buffer[-1])
        
    def cleanup(self):
        print("Cleaning up")
        self.is_capturing = False
        for plot in self.plots:
            self.removeItem(plot)
            plot.deleteLater()
        if self.rolling_view:
            self.removeItem(self.roll_line)
            self.roll_line.deleteLater()

    def updatePlots(self, channels, data, time_range):
        self.update_rate = 30

        if not self.rolling_view:
            # Scrolling faster than our update rate makes the graphing feel smoother
            self.scroll_rate = 30
            self.time_buffer.extend(time_range)
            self._received += 1
            if perf_counter_ns() > self._last_update + ((10**9)/self.scroll_rate):
                if self.time_buffer.is_full:
                    time_unit = time_range[1] - time_range[0]
                    self.getViewBox().translateBy(x=(time_range[-1] - time_range[0] + time_unit)*self._received)
                    self.setLimits(xMin=self.time_buffer[0], xMax=self.time_buffer[-1])
                self._received = 0
        
        for i, channel in enumerate(channels):
            self.buffers[channel].extend(data[i] - self.avgs[channel])
        if perf_counter_ns() < self._last_update + ((10**9)/self.update_rate):
            return
        if self.rolling_view: 
            self.roll_line.setPos(self.buffers[channels[0]]._idx_L)
            print(data.shape[1])
            if self.buffers[channels[0]]._idx_L >= self.buffer_size-(4*data.shape[1]):
                print("Calculating avg")
                for channel in channels:
                    self.avgs[channel] = numpy.average(self.buffers[channel] + self.avgs[channel])

        self._last_update = perf_counter_ns()
        time_unit = self.time_buffer[1] - self.time_buffer[0]
        (w,h) = self.getViewBox().viewPixelSize()
        [[xmin, xmax], [ymin, ymax]] = self.getViewBox().viewRange()
        block_size = int(numpy.ceil(w / time_unit))
        num_bin = int(numpy.ceil((len(self.time_buffer) // block_size)/2.) * 2)
        if num_bin < 3:
            num_bin = 3
        for i, channel in enumerate(channels):
            buffer = self.buffers[channel].__array__() - self.offset_factor*i
            if not ((buffer >= ymin) & (buffer <= ymax)).any():
                continue
            time = self.time_buffer.__array__()
            view = tsdownsample.MinMaxLTTBDownsampler().downsample(buffer, n_out=num_bin, parallel=True)
            clip = numpy.clip(buffer[view], a_min=ymin, a_max=ymax)
            self.plots[channel].setData(y=clip, x=time[view])

    def autoscaleToData(self, item):
        idx = self.plots.index(item)
        min_val = numpy.min(self.buffers[idx]) - self.offset_factor*idx
        max_val = numpy.max(self.buffers[idx]) - self.offset_factor*idx
        self.setYRange(min=min_val, max=max_val)