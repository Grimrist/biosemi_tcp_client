from pyqtgraph import AxisItem, PlotCurveItem
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

# PlotCurveItem that can handle painting multiple curves at once
# My intent is to only support the OpenGL backend for this purpose,
# but I might need to adjust all the methods regardless.
class PlotMultiCurveItem(PlotCurveItem):
    def updateData(self, *args, **kargs):
        # profiler = debug.Profiler()

        if 'compositionMode' in kargs:
            self.setCompositionMode(kargs['compositionMode'])

        if len(args) == 1:
            kargs['y'] = args[0]
        elif len(args) == 2:
            kargs['x'] = args[0]
            kargs['y'] = args[1]

        if 'y' not in kargs or kargs['y'] is None:
            kargs['y'] = np.array([])
        if 'x' not in kargs or kargs['x'] is None:
            kargs['x'] = np.arange(len(kargs['y']))

        for k in ['x', 'y']:
            data = kargs[k]
            if isinstance(data, list):
                data = np.array(data)
                kargs[k] = data
            if not isinstance(data, np.ndarray) or data.ndim > 1:
                raise Exception("Plot data must be 1D ndarray.")
            if data.dtype.kind == 'c':
                raise Exception("Can not plot complex data types.")


        # profiler("data checks")

        #self.setCacheMode(QtWidgets.QGraphicsItem.CacheMode.NoCache)  ## Disabling and re-enabling the cache works around a bug in Qt 4.6 causing the cached results to display incorrectly
                                                        ##    Test this bug with test_PlotWidget and zoom in on the animated plot
        self.yData = kargs['y'].view(np.ndarray)
        self.xData = kargs['x'].view(np.ndarray)
        
        self.invalidateBounds()
        self.prepareGeometryChange()
        self.informViewBoundsChanged()

        # profiler('copy')

        if 'stepMode' in kargs:
            self.opts['stepMode'] = kargs['stepMode']

        if self.opts['stepMode'] in ("center", True):  ## check against True for backwards compatibility
            if self.opts['stepMode'] is True:
                warnings.warn(
                    'stepMode=True is deprecated and will result in an error after October 2022. Use stepMode="center" instead.',
                    DeprecationWarning, stacklevel=3
                )
            if len(self.xData) != len(self.yData)+1:  ## allow difference of 1 for step mode plots
                raise Exception("len(X) must be len(Y)+1 since stepMode=True (got %s and %s)" % (self.xData.shape, self.yData.shape))
        else:
            if self.xData.shape != self.yData.shape:  ## allow difference of 1 for step mode plots
                raise Exception("X and Y arrays must be the same shape--got %s and %s." % (self.xData.shape, self.yData.shape))

        self.path = None
        self.fillPath = None
        self._fillPathList = None
        self._mouseShape = None
        self._lineSegmentsRendered = False

        if 'name' in kargs:
            self.opts['name'] = kargs['name']
        if 'connect' in kargs:
            self.opts['connect'] = kargs['connect']
        if 'pen' in kargs:
            self.setPen(kargs['pen'])
        if 'shadowPen' in kargs:
            self.setShadowPen(kargs['shadowPen'])
        if 'fillLevel' in kargs:
            self.setFillLevel(kargs['fillLevel'])
        if 'fillOutline' in kargs:
            self.opts['fillOutline'] = kargs['fillOutline']
        if 'brush' in kargs:
            self.setBrush(kargs['brush'])
        if 'antialias' in kargs:
            self.opts['antialias'] = kargs['antialias']
        if 'skipFiniteCheck' in kargs:
            self.opts['skipFiniteCheck'] = kargs['skipFiniteCheck']
        if 'colors' in kargs:
            self.colors = self.setColors(kargs['colors'])

        # profiler('set')
        self.update()
        # profiler('update')
        self.sigPlotChanged.emit(self)
        # profiler('emit')

    def setColors(self, colors):
        self.colors = colors

    def paintGL(self, p, opt, widget):
        p.beginNativePainting()
        import OpenGL.GL as gl

        if sys.platform == 'win32':
            # If Qt is built to dynamically load OpenGL, then the projection and
            # modelview matrices are not setup.
            # https://doc.qt.io/qt-6/windows-graphics.html
            # https://code.woboq.org/qt6/qtbase/src/opengl/qopenglpaintengine.cpp.html
            # Technically, we could enable it for all platforms, but for now, just
            # enable it where it is required, i.e. Windows
            gl.glMatrixMode(gl.GL_PROJECTION)
            gl.glLoadIdentity()
            gl.glOrtho(0, widget.width(), widget.height(), 0, -999999, 999999)
            gl.glMatrixMode(gl.GL_MODELVIEW)
            mat = QtGui.QMatrix4x4(self.sceneTransform())
            gl.glLoadMatrixf(np.array(mat.data(), dtype=np.float32))

        ## set clipping viewport
        view = self.getViewBox()
        if view is not None:
            rect = view.mapRectToItem(self, view.boundingRect())
            #gl.glViewport(int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height()))

            #gl.glTranslate(-rect.x(), -rect.y(), 0)

            gl.glEnable(gl.GL_STENCIL_TEST)
            gl.glColorMask(gl.GL_FALSE, gl.GL_FALSE, gl.GL_FALSE, gl.GL_FALSE) # disable drawing to frame buffer
            gl.glDepthMask(gl.GL_FALSE)  # disable drawing to depth buffer
            gl.glStencilFunc(gl.GL_NEVER, 1, 0xFF)
            gl.glStencilOp(gl.GL_REPLACE, gl.GL_KEEP, gl.GL_KEEP)

            ## draw stencil pattern
            gl.glStencilMask(0xFF)
            gl.glClear(gl.GL_STENCIL_BUFFER_BIT)
            gl.glBegin(gl.GL_TRIANGLES)
            gl.glVertex2f(rect.x(), rect.y())
            gl.glVertex2f(rect.x()+rect.width(), rect.y())
            gl.glVertex2f(rect.x(), rect.y()+rect.height())
            gl.glVertex2f(rect.x()+rect.width(), rect.y()+rect.height())
            gl.glVertex2f(rect.x()+rect.width(), rect.y())
            gl.glVertex2f(rect.x(), rect.y()+rect.height())
            gl.glEnd()

            gl.glColorMask(gl.GL_TRUE, gl.GL_TRUE, gl.GL_TRUE, gl.GL_TRUE)
            gl.glDepthMask(gl.GL_TRUE)
            gl.glStencilMask(0x00)
            gl.glStencilFunc(gl.GL_EQUAL, 1, 0xFF)

        try:
            x, y = self.getData()
            pos = np.empty((len(x), 2), dtype=np.float32)
            colors = self.colors()
            pos[:,0] = x
            pos[:,1] = y
            gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
            try:
                gl.glVertexPointerf(pos)
                gl.glColorPointerf(colors)
                width = pen.width()
                if pen.isCosmetic() and width < 1:
                    width = 1
                gl.glPointSize(width)
                gl.glLineWidth(width)

                # enable antialiasing if requested
                if self._exportOpts is not False:
                    aa = self._exportOpts.get('antialias', True)
                else:
                    aa = self.opts['antialias']
                if aa:
                    gl.glEnable(gl.GL_LINE_SMOOTH)
                    gl.glEnable(gl.GL_BLEND)
                    gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
                    gl.glHint(gl.GL_LINE_SMOOTH_HINT, gl.GL_NICEST)
                else:
                    gl.glDisable(gl.GL_LINE_SMOOTH)

                gl.glDrawArrays(gl.GL_LINES, 0, pos.shape[0])
            finally:
                gl.glDisableClientState(gl.GL_VERTEX_ARRAY)
        finally:
            p.endNativePainting()