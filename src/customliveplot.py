from typing import Optional, List, Tuple, Dict, Any
from copy import copy
import numbers
import time
from pyqtgraph import Point
from pglive.sources.live_plot_widget import LivePlotWidget
from pglive.sources.live_axis_range import LiveAxisRange
from PyQt6.QtCore import QEvent, Qt

class CustomLiveAxisRange(LiveAxisRange):
    def __init__(
        self,
        roll_on_tick: int = 1,
        offset_left: float = 0.0,
        offset_right: float = 0.0,
        offset_top: float = 0.0,
        offset_bottom: float = 0.0,
        fixed_range: Optional[List[float]] = None,
    ) -> None:
        super().__init__(roll_on_tick, offset_left, offset_right, offset_top, offset_bottom, fixed_range)
        self.aux_final_y_range = [-1, 1]

    def set_fixed_range(self, new_range):
        self.fixed_range = new_range

    def get_y_range(self, data_connector, tick: int) -> List[float]:
        _, y = data_connector.plot.getData()
        if y is None:
            return [0.0, 0.0]
        else:
            axis_range = data_connector.plot.data_bounds(ax=1, offset=self.roll_on_tick if self.roll_on_tick > 1 else 0)
        self.aux_final_y_range = list(axis_range)
        super().get_y_range(data_connector, tick)
        return self.final_y_range

    def get_max_y_range(self):
        return self.aux_final_y_range

class CustomLivePlotWidget(LivePlotWidget):
    def __init__(self, parent=None, background: str = 'default', plotItem=None,
                 x_range_controller: Optional[CustomLiveAxisRange] = None,
                 y_range_controller: Optional[CustomLiveAxisRange] = None, **kwargs: Any) -> None:
        self.x_range_controller = CustomLiveAxisRange() if x_range_controller is None else x_range_controller
        self.y_range_controller = CustomLiveAxisRange() if y_range_controller is None else y_range_controller
        super().__init__(parent, background, plotItem, self.x_range_controller, self.y_range_controller, **kwargs)

    # Most of the default pyqtgraph controls just break the plot, so we force disable them
    def mousePressEvent(self, ev: QEvent):
        if ev.buttons() in [Qt.MouseButton.RightButton]:
            ev.ignore()
        else:
            super().mousePressEvent(ev)

    # Slightly modified mouseMoveEvent from pyqtgraph's GraphicsView.py
    def mouseMoveEvent(self, ev: QEvent):
        lpos = ev.position() if hasattr(ev, 'position') else ev.localPos()
        if self.lastMousePos is None:
            self.lastMousePos = lpos
        delta = Point(lpos - self.lastMousePos)
        self.lastMousePos = lpos
        if ev.buttons() in [Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton]:  ## Allow panning by left or mid button.
            [ymin,ymax] = self.final_y_range
            dist = abs(ymax - ymin)
            tr = delta * dist * 0.05
            new_range = [ymin + tr.y(), ymax + tr.y()]
            self.y_range_controller.set_fixed_range(new_range)
        else:
            super().mouseMoveEvent(ev)
    
    # Fix auto-adjust button to not break the x-axis auto scrolling
    # We request the live axis to tell us what range we need to display the entire signal
    def auto_btn_clicked(self):
        new_range = self.y_range_controller.get_max_y_range()
        print(new_range)
        self.y_range_controller.set_fixed_range(new_range)

    def wheelEvent(self, ev):
        [ymin,ymax] = self.final_y_range
        dist = abs(ymax - ymin)
        print("Center: ", ymin + (ymax - ymin)/2)
        new_range = [ymin - dist * (30/ev.angleDelta().y()), ymax + dist * (30/ev.angleDelta().y())]
        self.y_range_controller.set_fixed_range(new_range)


