# coding: utf-8
'''
Created on 31 мая 2017 г.

@author: Sanin
'''
from matplotlib.figure import Figure
# Python Qt4 or Qt5 bindings for GUI objects
try:
    from PyQt4 import QtGui
    from matplotlib.backends.backend_qt4agg \
      import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt4agg \
      import NavigationToolbar2QT as NavigationToolbar
except:
    from PyQt5 import QtWidgets as QtGui
    from matplotlib.backends.backend_qt5agg \
      import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt5agg \
      import NavigationToolbar2QT as NavigationToolbar


# import the Qt4Agg FigureCanvas object, that binds Figure to
# Qt4Agg backend. It also inherits from QWidget
# Matplotlib Figure object
# import the NavigationToolbar Qt4Agg widget
class MplCanvas(FigureCanvas):
    """Class to represent the FigureCanvas widget"""
    def __init__(self):
        # setup Matplotlib Figure and Axis
        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)
        # initialization of the canvas
        FigureCanvas.__init__(self, self.fig)
        # we define the widget as expandable
        FigureCanvas.setSizePolicy(self,
                                   QtGui.QSizePolicy.Expanding,
                                   QtGui.QSizePolicy.Expanding)
        # notify the system of updated policy
        FigureCanvas.updateGeometry(self)

class MplWidget(QtGui.QWidget):
    """Widget defined in Qt Designer"""
    def __init__(self, parent = None):
        # initialization of Qt MainWindow widget
        QtGui.QWidget.__init__(self, parent)
        # set the canvas to the Matplotlib widget
        self.canvas = MplCanvas()
        # create a vertical box layout
        self.vbl = QtGui.QVBoxLayout()
        
        self.ntb = NavigationToolbar(self.canvas, parent)
        self.vbl.addWidget(self.ntb)
        
        # add mpl widget to vertical box
        self.vbl.addWidget(self.canvas)
        # set the layout to the vertical box
        self.setLayout(self.vbl)
        