from pyqtgraph import AxisItem
import numpy as np
import math

# Class that inherits from AxisItem to provide better tick display for logarithmic axes.
# TODO: Add detection for text overlapping, not clear if I can use boundingRect for this
# For now: using https://github.com/pyqtgraph/pyqtgraph/issues/322#issuecomment-503541303
class LogAxis(AxisItem):
    # def logTickStrings(self, values, scale, spacing):
    #     estrings = ["%0.1g"%x for x in 10 ** np.array(values).astype(float) * np.array(scale)]
    #     convdict = {"0": "⁰",
    #                 "1": "¹",
    #                 "2": "²",
    #                 "3": "³",
    #                 "4": "⁴",
    #                 "5": "⁵",
    #                 "6": "⁶",
    #                 "7": "⁷",
    #                 "8": "⁸",
    #                 "9": "⁹",
    #                 }
    #     dstrings = []
    #     for e in estrings:
    #         if e.count("e"):
    #             v, p = e.split("e")
    #             sign = "⁻" if p[0] == "-" else ""
    #             pot = "".join([convdict[pp] for pp in p[1:].lstrip("0")])
    #             if v == "1":
    #                 v = ""
    #             else:
    #                 v = v + "·"
    #             dstrings.append(v + "10" + sign + pot)
    #         else:
    #             dstrings.append(e)
    #     return dstrings

    def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):
        # profiler = debug.Profiler()

        p.setRenderHint(p.RenderHint.Antialiasing, False)
        p.setRenderHint(p.RenderHint.TextAntialiasing, True)

        ## draw long line along axis
        pen, p1, p2 = axisSpec
        p.setPen(pen)
        p.drawLine(p1, p2)
        # p.translate(0.5,0)  ## resolves some damn pixel ambiguity

        ## draw ticks
        for pen, p1, p2 in tickSpecs:
            p.setPen(pen)
            p.drawLine(p1, p2)
        # profiler('draw ticks')

        # Draw all text
        if self.style['tickFont'] is not None:
            p.setFont(self.style['tickFont'])
        p.setPen(self.textPen())
        bounding = self.boundingRect().toAlignedRect()
        p.setClipRect(bounding)

        max_width = 0
        self._angle = 45
        self._angle = self._angle % 90

        for rect, flags, text in textSpecs:
            p.save()  # save the painter state

            p.translate(rect.center())   # move coordinate system to center of text rect
            p.rotate(self._angle)  # rotate text
            p.translate(-rect.center())  # revert coordinate system

            x_offset = math.ceil(math.fabs(math.sin(math.radians(self._angle)) * rect.width()))
            if self._angle < 0:
                x_offset = -x_offset
            p.translate(x_offset/2, 0)  # Move the coordinate system (relatively) downwards

            p.drawText(rect, flags, text)
            p.restore()  # restore the painter state
            offset = math.fabs(x_offset)
            max_width = offset if max_width < offset else max_width

        # profiler('draw text')
        #  Adjust the height
        # if not self._height_updated:
        #     self.setHeight(self.height() + max_width)
        #     self._height_updated = True
