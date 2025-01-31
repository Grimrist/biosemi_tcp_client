from pyqtgraph import PlotWidget, PlotCurveItem, PlotItem, InfiniteLine
import pyqtgraph
from dvg_ringbuffer import RingBuffer
from time import perf_counter_ns
import numpy
import tsdownsample
from utils import RollingRingBuffer

class RealTimePlot(PlotWidget):
    def __init__(self, parent=None, background='default', plotItem=None, **kargs):
        super().__init__(parent, background, plotItem, **kargs)
        self._init = False
        self.ref_channel = -1

    def initializeGraphs(self, fs, total_channels, buffer_size, rolling_view, active_channels):
        self.buffer_size = buffer_size
        self._last_update = 0
        self._received = 0
        self.offset_factor = 1
        self.avgs = numpy.zeros(total_channels)
        self.time_buffer = RingBuffer(capacity=self.buffer_size, dtype='float64')
        self.rolling_view = rolling_view
        self.active_channels = active_channels
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
        self._init = True

    def cleanup(self):
        print("Cleaning up")
        self.is_capturing = False
        for plot in self.plots:
            self.removeItem(plot)
            plot.deleteLater()
        if self.rolling_view:
            self.removeItem(self.roll_line)
            self.roll_line.deleteLater()
        self._init = False

    def setActiveChannels(self, channels, total_channels):
        self.active_channels = channels
        if self._init:
            for i in range(total_channels):
                if i in channels:
                    self.plots[i].show()
                else: self.plots[i].hide()

    def setReferenceChannel(self, channel):
        self.ref_channel = channel

    def updatePlots(self, data, time_range):
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
        
        # Fill buffers with the new data
        # TODO: Rethink this, the reference should definitely not be applied directly to our storage
        if self.ref_channel != -1:
            ref = data[self.ref_channel]
        else:
            ref = 0
        for i, channel in enumerate(data):
            self.buffers[i].extend((channel - ref) - self.avgs[i])

        # Only request to draw the data at our specified update rate
        # This could potentially be completely replaced by a QTimer
        if perf_counter_ns() < self._last_update + ((10**9)/self.update_rate):
            return
        self._last_update = perf_counter_ns()

        # If rolling view, then we want to draw the scrolling red line, as well as try to lump the data together
        if self.rolling_view: 
            self.roll_line.setPos(self.buffers[self.active_channels[0]]._idx_L)
            if self.buffers[self.active_channels[0]]._idx_L >= self.buffer_size-(4*data.shape[1]):
                print("Calculating avg")
                for channel in range(len(self.buffers)):
                    self.avgs[channel] = numpy.average(self.buffers[channel] + self.avgs[channel])

        # Determine the pixel size of our data so that we can properly bin it for downsampling
        time_unit = self.time_buffer[1] - self.time_buffer[0]
        (w,h) = self.getViewBox().viewPixelSize()
        [[xmin, xmax], [ymin, ymax]] = self.getViewBox().viewRange()
        block_size = int(numpy.ceil(w / time_unit))
        num_bin = int(numpy.ceil((len(self.time_buffer) // block_size)/2.) * 2)
        if num_bin < 3:
            num_bin = 3

        # Plot the data based on the currently active channels
        # If no channels are selected, we don't need to plot anything.
        if len(self.active_channels) == 0:
            return
        # Loop through active channels and plot only the ones we want
        for i, channel in enumerate(self.active_channels):
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