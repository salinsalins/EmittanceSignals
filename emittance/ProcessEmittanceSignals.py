# coding: utf-8
"""
Created on Jul 2, 2017

@author: sanin
"""
# from __future__ import with_statement
# from __future__ import print_function

import os.path
import shelve
import sys
import time
import json
import logging

from emittance.findRegions import find_regions as find_regions
from emittance.findRegions import restoreFromRegions as restoreFromRegions
from emittance.smooth import smooth
from emittance.readTekFiles import readTekFiles

from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import qApp
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtWidgets import QMessageBox
from PyQt5 import uic
from PyQt5.QtCore import QPoint, QSize

import numpy as np
from scipy.integrate import trapz
from scipy.interpolate import interp1d
from scipy.interpolate import griddata
import matplotlib.pyplot as plt

_progName = 'Emittance'
_progVersion = '_8_3'
_settings_file_name = _progName + '.json'
_initScript = _progName + '_init.py'
_logFile = _progName + '.log'
_dataFile = _progName + '.dat'

# logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)
# formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
# console_handler = logging.StreamHandler()
# console_handler.setLevel(logging.WARNING)
# console_handler.setFormatter(formatter)
# file_handler = logging.FileHandler('logger.log')
# file_handler.setLevel(logging.INFO)
# file_handler.setFormatter(formatter)
# logger.addHandler(console_handler)
# logger.addHandler(file_handler)


class TextEditHandler(logging.Handler):
    def __init__(self, wdgt=None):
        logging.Handler.__init__(self)
        self.widget = wdgt

    def emit(self, record):
        log_entry = self.format(record)
        if self.widget is not None:
            self.widget.appendPlainText(log_entry)


class DesignerMainWindow(QMainWindow):
    """Customization for Qt Designer created window"""

    def __init__(self, parent=None):
        # initialization of the superclass
        super(DesignerMainWindow, self).__init__(parent)
        # load the GUI 
        uic.loadUi(r'.\Emittance1.ui', self)
        # connect the signals with the slots
        self.pushButton_2.clicked.connect(self.selectFolder)
        self.pushButton_4.clicked.connect(self.processFolder)
        self.pushButton_6.clicked.connect(self.pushPlotButton)
        self.pushButton_7.clicked.connect(self.erasePicture)
        self.comboBox_2.currentIndexChanged.connect(self.selectionChanged)
        # menu actions connection
        self.actionOpen.triggered.connect(self.selectFolder)
        self.actionQuit.triggered.connect(qApp.quit)
        self.actionPlot.triggered.connect(self.showPlot)
        self.actionLog.triggered.connect(self.showLog)
        self.actionParameters.triggered.connect(self.showParameters)
        self.actionAbout.triggered.connect(self.showAbout)
        # additional configuration
        # disable text wrapping in log window
        self.plainTextEdit.setLineWrapMode(0)
        # variables definition
        self.conf = {}
        self.folderName = ''
        self.fleNames = []
        self.nx = 0
        self.data = None
        self.scanVoltage = None
        self.paramsAuto = None
        self.paramsManual = {}
        # configure logging
        self.logger = logging.getLogger(_progName + _progVersion)
        self.logger.setLevel(logging.DEBUG)
        self.f_str = '%(asctime)s,%(msecs)3d %(levelname)-7s %(filename)s %(funcName)s(%(lineno)s) %(message)s'
        self.log_formatter = logging.Formatter(self.f_str, datefmt='%H:%M:%S')
        self.console_handler = logging.StreamHandler()
        # self.console_handler.setLevel(logging.WARNING)
        self.console_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.console_handler)
        self.file_handler = logging.FileHandler(_logFile)
        self.file_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.file_handler)
        self.text_edit_handler = TextEditHandler(self.plainTextEdit)
        self.text_edit_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.text_edit_handler)

        # welcome message
        self.logger.info(_progName + _progVersion + ' started')

        # restore global settings from default location
        self.restore_settings()

        # read data files
        self.parseFolder()

        # restore local settings
        if not self.restoreData(folder=self.folderName):
            self.processFolder()

        # connect mouse button press event
        # self.cid = self.mplWidget.canvas.mpl_connect('button_press_event', self.onclick)
        # self.mplWidget.canvas.mpl_disconnect(cid)

    def showAbout(self):
        QMessageBox.information(self, 'About', _progName + ' Version ' + _progVersion +
                                '\nBeam emittance calculation program.', QMessageBox.Ok)

    def showPlot(self):
        self.stackedWidget.setCurrentIndex(0)
        self.actionPlot.setChecked(True)
        self.actionLog.setChecked(False)
        self.actionParameters.setChecked(False)

    def showLog(self):
        self.stackedWidget.setCurrentIndex(1)
        self.actionPlot.setChecked(False)
        self.actionLog.setChecked(True)
        self.actionParameters.setChecked(False)

    def showParameters(self):
        self.stackedWidget.setCurrentIndex(2)
        self.actionPlot.setChecked(False)
        self.actionLog.setChecked(False)
        self.actionParameters.setChecked(True)
        self.tableWidget.horizontalHeader().setVisible(True)

    def selectFolder(self):
        """Opens a file select dialog"""
        # open the dialog and get the selected dataFolder
        folder = self.folderName
        fileOpenDialog = QFileDialog(caption='Select directory with data files', directory=folder)
        # select folder, not file
        dataFolder = fileOpenDialog.getExistingDirectory()
        # if a dataFolder is selected
        if dataFolder:
            if self.folderName == dataFolder:
                return
            i = self.comboBox_2.findText(dataFolder)
            if i >= 0:
                self.comboBox_2.setCurrentIndex(i)
            else:
                # add item to history  
                self.comboBox_2.insertItem(-1, dataFolder)
                self.comboBox_2.setCurrentIndex(0)

    def selectionChanged(self, i):
        # self.logger.debug('Selection changed to %s'%str(i))
        if i < 0:
            return
        newFolder = str(self.comboBox_2.currentText())
        if not os.path.isdir(newFolder):
            self.logger.warning('Folder %s is not found' % newFolder)
            self.comboBox_2.removeItem(i)
            return
        if self.folderName != newFolder:
            self.clearPicture()
            # restore local settings
            # self.restoreSettings(folder=newFolder)
            self.folderName = newFolder
            if not self.restoreData(folder=newFolder):
                self.processFolder()
            else:
                self.parseFolder(newFolder)
        # switch to data folder
        os.chdir(newFolder)

    def onQuit(self):
        # save data to local folder
        # self.saveSettings(folder = self.folderName)
        self.saveData(folder=self.folderName)
        # switch to initial folder
        os.chdir(self.cwd)
        # save global settings
        self.saveSettings()

    def clearPicture(self, force=False):
        if force or self.checkBox.isChecked():
            # clear the axes
            self.erasePicture()

    def erasePicture(self):
        self.mplWidget.canvas.ax.clear()
        self.mplWidget.canvas.draw()

    def parseFolder(self, folder=None, mask='*.isf'):
        pass
        if folder is None:
            folder = self.folderName
        self.logger.info('%s%s reading data from %s' % (_progName, _progVersion, folder))
        # read data
        self.data, self.fileNames = readTekFiles(folder, mask)
        # number of files
        nx = len(self.fileNames)
        if nx <= 0:
            self.logger.info('Nothing to process in %s' % folder)
            self.logger.info('Return to %s' % self.folderName)
            return
        self.logger.info('%d files found' % nx)
        self.folderName = folder
        self.nx = nx
        self.ny = self.data.shape[1]
        self.iy = np.arange(self.ny)
        # switch to local log file
        # printl('', stamp=False, fileName = os.path.join(str(folder), _logFile))
        self.logger.removeHandler(self.file_handler)
        self.file_handler = logging.FileHandler(os.path.join(str(folder), _logFile))
        self.file_handler.setFormatter(self.log_formatter)
        # file_handler.setLevel(logging.INFO)
        self.logger.addHandler(self.file_handler)
        self.logger.info('%s%s parsing folder %s' % (_progName, _progVersion, folder))
        # fill listWidget with file names
        self.listWidget.clear()
        # make file names list
        names = [name.replace(folder, '')[1:] for name in self.fileNames]
        for i in range(nx):
            names[i] = '%3d - %s' % (i, names[i])
        # fill listWidget
        self.listWidget.addItems(names)

    def plot_signal(self, x, y, index, **kwargs):
        axes = self.mplWidget.canvas.ax
        regions = find_regions(index)
        line = None
        for reg in regions:
            ind = np.arange(reg[0],reg[1])
            if line is None:
                line = axes.plot(x[ind], y[ind], **kwargs)
            else:
                cl = line[0].get_color()
                line = axes.plot(x[ind], y[ind], color=cl)
        self.mplWidget.canvas.draw()

    def processFolder(self, *args, **kwargs):
        folder = self.folderName
        self.logger.info('Processing folder %s', folder)
        # execute init script
        self.execInitScript()
        # parse folder
        self.parseFolder(folder)
        # read data array
        data = self.data
        files = self.fileNames
        # number of files
        nx = len(files)
        if nx <= 0:
            self.logger.info('No data files in %s', folder)
            return False
        self.logger.info('%s data files in %s', nx, folder)
        # size of Y data
        ny = len(data[0])
        # define arrays
        zero = np.zeros((nx, ny), dtype=np.float64)
        weight = np.zeros((nx, ny), dtype=np.float64)
        # index array
        ix = np.arange(ny)
        # smooth
        ns = 1
        try:
            ns = int(self.spinBox.value())
        except:
            pass
        # default parameters
        params = [{'smooth': ns, 'offset': 0.0, 'zero': np.zeros(ny), 'scale': 1.95} for i in range(nx)]

        self.paramsAuto = params
        # smooth data array
        self.logger.info('Smoothing data ...')
        for i in range(nx):
            y = data[i, :]
            smooth(y, params[i]['smooth'])
            data[i, :] = y
        # process scan voltage
        # channel 0 is by default scan voltage
        sv_index = 0
        self.logger.info('Processing scan voltage ...')
        sv_x = data[sv_index, :].copy()
        # additionally smooth x
        smooth(sv_x, params[sv_index]['smooth'] * 2)
        # find longest monotonic region of scan voltage
        sv_xdiff = np.diff(sv_x)
        sv_xdiff = np.append(sv_xdiff, sv_xdiff[-1])
        mask = sv_xdiff >= 0.0
        regions = find_regions(np.where(mask)[0])
        # find longest region
        xr = [0, 1]
        for r in regions:
            if r[1] - r[0] >= xr[1] - xr[0]:
                xr = r
        mask = sv_xdiff <= 0.0
        regions = find_regions(np.where(mask)[0])
        for r in regions:
            if r[1] - r[0] >= xr[1] - xr[0]:
                xr = r
        xi = np.arange(xr[0], xr[1])
        params[sv_index]['range'] = xr
        self.logger.info('Scan voltage region %s' % str(xr))
        # auto process data for zero line and offset
        self.logger.info('Processing zero lines and offsets ...')
        # sort data to maximal signals
        smax = np.min(data[1:, :], 1)
        sm_index = smax.argsort()
        # use the largest channel as reference
        i = sm_index[0]
        y = data[i, :].copy()
        offset = params[i]['offset']
        z = params[i]['zero']
        smooth(y, params[i]['smooth'] * 2)
        y = y - offset - z
        ymax = np.max(y)
        #z += ymax
        #params[i]['zero'] = z
        #params[i]['offset'] = ymax
        axes = self.mplWidget.canvas.ax
        # axes.plot(ix, y)
        # axes.plot(ix, z)
        # axes.set_title('Largest signal jet %s' % i)
        # axes.set_xlabel('n, Index')
        # axes.set_ylabel('Voltage, V')
        # self.mplWidget.canvas.draw()

        k = [(i, i+1) for i in range(sm_index[1] + 1, nx-1)] + [(i, i-1) for i in range(sm_index[1] + 1, 2, -1)]

        # process zero line and offset
        for j in k:
            i = j[0]
            i1 = j[1]
            self.logger.info('Processing channel %d -> %d', i, i1)
            # select adjacent channel
            y1 = data[i, :].copy()
            y2 = data[i1, :].copy()
            # subtract offset and zero
            o1 = params[i]['offset']
            #y1 = y1 - offset1 - zero1
            o2 = params[i1]['offset']
            # double smooth because zero line is slow
            smooth(y1, params[i]['smooth'] * 2)
            smooth(y2, params[i1]['smooth'] * 2)
            # zero line = where 2 signals are almost equal
            frac = 0.05
            flag = True
            dy = np.abs(y1 - y2)
            dyptp = dy.ptp()
            while flag and (frac < 0.9):
                mask = dy < (frac * dyptp)
                index = np.where(mask)[0]
                if len(index) < (len(dy) / 10.0):
                    frac *= 2.0
                    self.logger.info('Threshold is doubled %s %s', len(index), frac)
                else:
                    flag = False
            # plot interm results
            axes.plot(ix, dy, label='dy')
            self.plot_signal(ix, dy, index, label='dy[index]')
            axes.set_title('Zero line %s and %s' % (i, i1))
            axes.set_xlabel('Index')
            axes.set_ylabel('Voltage, V')
            axes.legend(loc='best')
            self.mplWidget.canvas.draw()
            # filter signal intersection regions
            index = restoreFromRegions(find_regions(index, 50, 300, 100, 100, length=ny))
            if len(index) <= 0:
                index = np.where(mask)[0]
            #
            # self.plot_signal(ix, dy, index, label='dy[index]')
            # axes.legend(loc='best')
            # self.mplWidget.canvas.draw()
            # new offset
            if len(index) > 0:
                offset = np.average(y2[index] - y1[index])
            else:
                offset = 0.0
            self.logger.info('Offset for channel %d = %f' % (i1, offset))
            # axes.plot(ix, y1, label='y1')
            # axes.plot(ix, y2, label='y2')
            # self.plot_signal(ix, y1, index, label='y1[index]')
            # self.plot_signal(ix, y2, index, label='y2[index]')
            # axes.legend(loc='best')
            # self.mplWidget.canvas.draw()
            # shift y1 y2 and set o2
            o2 = o1 + offset
            y1 = y1 - o1
            y2 = y2 - o2
            # save processed offset
            params[i1]['offset'] = o2
            # index with new offset
            # self.logger.info('4% index with corrected offset')
            dy = np.abs(y1 - y2)
            mask = dy < (0.05 * dy.ptp())
            index = np.where(mask)[0]
            # filter signal intersection
            regions = find_regions(index, 50, 300, 100, 100)
            index = restoreFromRegions(regions, 0, 150, length=ny)
            # update zero line for all channels
            for j in range(1, nx):
                if j == i:
                    w = 10.0
                    zero[j, index] = (zero[j, index] * weight[j, index] + y1[index] * w) / (weight[j, index] + w)
                elif j == i1:
                    w = 10.0
                    zero[j, index] = (zero[j, index] * weight[j, index] + y2[index] * w) / (weight[j, index] + w)
                else:
                    w = 1.0 / ((abs(i - j)) ** 2 + 1.0)
                    zero[j, index] = (zero[j, index] * weight[j, index] + (y1[index] + y2[index]) * (0.5 * w)) / (weight[j, index] + w)
                weight[j, index] += w
                self.paramsAuto[j]['zero'] = zero[j]
            #
            self.plot_signal(ix, zero[i], index, label='z1[index]')
            self.plot_signal(ix, zero[i1], index, label='z2[index]')
            axes.legend(loc='best')
            self.mplWidget.canvas.draw()
            # self.plot_raw_signals([18])
            pass
        # save processed zero line
        for i in range(nx):
            params[i]['zero'] = zero[i]

        return
        x = sv_x
        # determine signal area
        self.logger.info('Processing signals ...')
        for i in range(1, nx):
            # self.logger.info('Channel %d'%i)
            y0 = data[i, :].copy()[xi]
            smooth(y0, params[i]['smooth'])
            z = zero[i].copy()[xi] + params[i]['offset']
            smooth(z, params[i]['smooth'] * 2)
            y = y0 - z
            ymin = np.min(y)
            ymax = np.max(y)
            dy = ymax - ymin
            mask = y < (ymax - 0.6 * dy)
            index = np.where(mask)[0]
            ra = find_regions(index)
            params[i]['range'] = xr
            # determine scale
            is1 = xi[0]
            is2 = xi[-1]
            if len(ra) >= 1:
                is1 = np.argmin(y[ra[0][0]:ra[0][1]]) + ra[0][0] + xi[0]
            if len(ra) >= 2:
                is2 = np.argmin(y[ra[1][0]:ra[1][1]]) + ra[1][0] + xi[0]
            params[i]['scale'] = 10.0 / (x[is2] - x[is1])  # [mm/Volt]
            if np.abs(x[is1]) < np.abs(x[is2]):
                index = is1
            else:
                index = is2
            params[i]['minindex'] = index
            params[i]['minvoltage'] = x[index]
            di = int(abs(is2 - is1) / 2.0)
            ir1 = max([xi[0], index - di])
            ir2 = min([xi[-1], index + di])
            params[i]['range'] = [ir1, ir2]
            # debug draw 11 Range and scale calculation
            self.debugDraw([i, xi, y, ix[ir1:ir2], y[ir1 - xi[0]:ir2 - xi[0]], is1, is2])
        # filter scales
        sc0 = np.array([params[i]['scale'] for i in range(1, nx)])
        sc = sc0.copy()
        asc = np.average(sc)
        ssc = np.std(sc)
        while ssc > 0.3 * np.abs(asc):
            index1 = np.where(abs(sc - asc) <= 2.0 * ssc)[0]
            index2 = np.where(abs(sc - asc) > 2.0 * ssc)[0]
            sc[index2] = np.average(sc[index1])
            asc = np.average(sc)
            ssc = np.std(sc)
        for i in range(1, nx):
            params[i]['scale'] = sc[i - 1]
            # save processed to member variable
        self.paramsAuto = params

        # common parameters
        self.logger.info('Set common parameters ...')
        # Default parameters of measurements
        params[0]['R'] = 2.0e5  # Ohm   Resistor for scanner FC
        params[0]['d1'] = 0.5  # mm    Scanner analyzer hole diameter
        params[0]['d2'] = 0.5  # mm    Scanner FC slit width
        params[0]['l1'] = 213.0  # mm    Distance from emission hole to scanner analyzer hole
        params[0]['l2'] = 195.0  # mm    Scanner base

        # X0 and ndh calculation
        l1 = self.read_parameter(0, "l1", 213.0, float)
        l2 = self.read_parameter(0, "l2", 195.0, float)
        x00 = np.zeros(nx - 1)
        for i in range(1, nx):
            s = self.read_parameter(i, "scale", 2.0, float)
            u = self.read_parameter(i, "minvoltage", 0.0, float)
            x00[i - 1] = -s * u * l1 / l2
            # self.logger.info('%3d N=%d Umin=%f scale=%f X00=%f'%(i, j, u, s, x00[i-1]))
        npt = 0
        sp = 0.0
        nmt = 0
        sm = 0.0
        dx = x00.copy() * 0.0
        # self.logger.info('%3d X00=%f DX=%f'%(0, x00[0], 0.0))
        for i in range(1, nx - 1):
            dx[i] = x00[i] - x00[i - 1]
            if dx[i] > 0.0:
                npt += 1
                sp += dx[i]
            if dx[i] < 0.0:
                nmt += 1
                sm += dx[i]
            # self.logger.info('%3d X00=%f DX=%f'%(i, x00[i], dx[i]))
        # self.logger.info('npt=%d %f nmt=%d %f %f'%(npt,sp/npt,nmt,sm/nmt,sp/npt-l1/l2*10.))
        x01 = x00.copy()
        h = x00.copy() * 0.0
        for i in range(1, nx - 1):
            if npt > nmt:
                x01[i] = x01[i - 1] + sp / npt
                if dx[i] > 0.0:
                    h[i] = h[i - 1]
                else:
                    h[i] = h[i - 1] + 10.0
            else:
                x01[i] = x01[i - 1] + sm / nmt
                if dx[i] < 0.0:
                    h[i] = h[i - 1]
                else:
                    h[i] = h[i - 1] - 10.0
        x01 = x01 - np.average(x01)
        k = int(np.argmin(np.abs(x01)))
        h = h - h[k]
        for i in range(1, nx):
            params[i]['ndh'] = h[i - 1]
            s = self.read_parameter(i, "scale", 1.7, float)
            u = self.read_parameter(i, "minvoltage", 0.0, float)
            x01[i - 1] = (h[i - 1] - s * u) * l1 / l2
            params[i]['x0'] = x01[i - 1]
            # self.logger.info('%3d'%i, end='  ')
            # self.logger.info('X0=%f mm ndh=%4.1f mm'%(params[i]['x0'],params[i]['ndh']), end='  ')
            # self.logger.info('X00=%f mm DX=%f mm'%(x00[i-1], dx[i-1]))
        # self.logger.info calculated parameters
        self.logger.info('Calculated parameters:')
        s = ''
        for i in range(nx):
            try:
                s = 'Chan.%3d ' % i
                s = s + 'range=%s; ' % str(params[i]['range'])
                s = s + 'offset=%f V; ' % params[i]['offset']
                s = s + 'scale=%6.2f mm/V; ' % params[i]['scale']
                s = s + 'MinI=%4d; Umin=%6.2f V; ' % (params[i]['minindex'], params[i]['minvoltage'])
                s = s + 'x0=%5.1f mm; ndh=%5.1f mm' % (params[i]['x0'], params[i]['ndh'])
            except:
                pass
            self.logger.info(s)
        self.logger.info('Actual parameters:')
        for i in range(nx):
            try:
                s = 'Chan.%3d ' % i
                s = s + 'range=%s; ' % str(self.read_parameter(i, "range"))
                s = s + 'offset=%f V; ' % self.read_parameter(i, "offset")
                s = s + 'scale=%6.2f mm/V; ' % self.read_parameter(i, "scale")
                s = s + 'MinI=%4d; ' % (self.read_parameter(i, "minindex"))
                s = s + 'Umin=%6.2f V; ' % (self.read_parameter(i, "minvoltage"))
                s = s + 'x0=%5.1f mm; ' % (self.read_parameter(i, "x0"))
                s = s + 'ndh=%5.1f mm' % (self.read_parameter(i, "ndh"))
            except:
                pass
            self.logger.info(s)
        # debug draw X0 calculation
        self.debugDraw([x01, nx, k])
        # save processed to member variable
        self.paramsAuto = params
        self.logger.info('Auto parameters has been calculated')
        self.saveData(folder=self.folderName)
        return True

    def processFolder1(self, folder=None):
        folder = self.folderName
        # execute init script
        self.execInitScript()
        # parse folder
        self.parseFolder(folder)
        # read data array
        data = self.data
        files = self.fileNames
        # number of files
        nx = len(files)
        if nx <= 0:
            return False
        self.logger.info('Processing folder %s', folder)
        # size of Y data
        ny = len(data[0])
        # define arrays
        zero = np.zeros((nx, ny), dtype=np.float64)
        weight = np.zeros((nx, ny), dtype=np.float64)
        # index array
        ix = np.arange(ny)
        # smooth
        ns = 1
        try:
            ns = int(self.spinBox.value())
        except:
            pass

        # default parameters array
        params = [{'smooth': ns, 'offset': 0.0, 'zero': np.zeros(ny), 'scale': 1.95} for i in range(nx)]
        # smooth data array
        self.logger.info('Smoothing data ...')
        for i in range(nx):
            y = data[i, :]
            smooth(y, params[i]['smooth'])
            data[i, :] = y

        self.logger.info('Processing scan voltage ...')
        # channel 0 is by default scan voltage 
        x = data[0, :].copy()
        # additionally smooth x 
        smooth(x, params[0]['smooth'] * 2)
        # find longest monotonic region of scan voltage
        xdiff = np.diff(x)
        xdiff = np.append(xdiff, xdiff[-1])
        mask = xdiff >= 0.0
        regions = find_regions(np.where(mask)[0])
        # find longest region
        xr = [0, 1]
        for r in regions:
            if r[1] - r[0] >= xr[1] - xr[0]:
                xr = r
        mask = xdiff <= 0.0
        regions = find_regions(np.where(mask)[0])
        for r in regions:
            if r[1] - r[0] >= xr[1] - xr[0]:
                xr = r
        xi = np.arange(xr[0], xr[1])
        params[0]['range'] = xr
        self.logger.info('Scan voltage region %s' % str(xr))
        # debug draw 8 Scan voltage region
        # self.debugDraw([ix, x, ix[xi], x[xi]])

        # auto process data for zero line and offset
        self.logger.info('Processing zero lines and offsets ...')
        for i in range(1, nx - 1):
            # self.logger.info('Channel %d'%(i))
            y1 = data[i, :].copy()
            offset1 = params[i]['offset']
            y1 = y1 - offset1
            y2 = data[i + 1, :].copy()
            offset2 = params[i + 1]['offset']
            y2 = y2 - offset2
            # double smooth because zero line is slow 
            smooth(y1, params[i]['smooth'] * 2)
            smooth(y2, params[i + 1]['smooth'] * 2)
            # offsets calculated from upper 10%
            y1min = np.min(y1)
            y1max = np.max(y1)
            dy1 = y1max - y1min
            y2min = np.min(y2)
            y2max = np.max(y2)
            dy2 = y2max - y2min
            dy = max([dy1, dy2])
            i1 = np.where(y1 > (y1max - 0.1 * dy))[0]
            o1 = np.average(y1[i1])
            # self.logger.info('Offset 1 %f'%o1)
            i2 = np.where(y2 > (y2max - 0.1 * dy))[0]
            o2 = np.average(y2[i2])
            # self.logger.info('Offset 2 %f'%o2)
            # debug draw 9 Offset calculation
            self.debugDraw([i, ix, y1, o1, y2, o2, i1, i2])
            # correct y2 and offset2 for calculated offsets
            y2 = y2 - o2 + o1
            offset2 = offset2 + o2 - o1
            # zero line = where 2 signals are almost equal
            mask = np.abs(y1 - y2) < 0.05 * dy1
            index = np.where(mask)[0]
            # filter signal intersection regions
            index = restoreFromRegions(find_regions(index, 50, 300, 100, 100, length=ny))
            if len(index) <= 0:
                index = np.where(mask)[0]
            # new offset
            offset = np.average(y2[index] - y1[index])
            # self.logger.info('Offset for channel %d = %f'%((i+1), offset))
            # shift y2 and offset2
            y2 = y2 - offset
            offset2 = offset2 + offset
            # save processed offset
            params[i + 1]['offset'] = offset2
            # index with new offset
            # self.logger.info('4% index with corrected offset')
            mask = np.abs(y1 - y2) < 0.04 * dy1
            index = np.where(mask)[0]
            # self.logger.info(findRegionsText(index))
            # filter signal intersection
            regions = find_regions(index, 50)
            index = restoreFromRegions(regions, 0, 150, length=ny)
            # self.logger.info(findRegionsText(index))
            # choose largest values
            mask[:] = False
            mask[index] = True
            mask3 = np.logical_and(mask, y1 >= y2)
            index3 = np.where(mask3)[0]
            # update zero line for all channels
            for j in range(1, nx):
                w = 1.0 / ((abs(i - j)) ** 2 + 1.0)
                zero[j, index3] = (zero[j, index3] * weight[j, index3] + y1[index3] * w) / (weight[j, index3] + w)
                weight[j, index3] += w
            mask4 = np.logical_and(mask, y1 <= y2)
            index4 = np.where(mask4)[0]
            # update zero line for all channels
            for j in range(1, nx):
                w = 1.0 / ((abs(i + 1 - j)) ** 2 + 1.0)
                zero[j, index4] = (zero[j, index4] * weight[j, index4] + y2[index4] * w) / (weight[j, index4] + w)
                weight[j, index4] += w
            if i == 13:
                break
        # save processed zero line
        for i in range(nx):
            params[i]['zero'] = zero[i]

        # determine signal area
        self.logger.info('Processing signals ...')
        for i in range(1, nx):
            # self.logger.info('Channel %d'%i)
            y0 = data[i, :].copy()[xi]
            smooth(y0, params[i]['smooth'])
            z = zero[i].copy()[xi] + params[i]['offset']
            smooth(z, params[i]['smooth'] * 2)
            y = y0 - z
            ymin = np.min(y)
            ymax = np.max(y)
            dy = ymax - ymin
            mask = y < (ymax - 0.6 * dy)
            index = np.where(mask)[0]
            ra = find_regions(index)
            params[i]['range'] = xr
            # determine scale
            is1 = xi[0]
            is2 = xi[-1]
            if len(ra) >= 1:
                is1 = np.argmin(y[ra[0][0]:ra[0][1]]) + ra[0][0] + xi[0]
            if len(ra) >= 2:
                is2 = np.argmin(y[ra[1][0]:ra[1][1]]) + ra[1][0] + xi[0]
            params[i]['scale'] = 10.0 / (x[is2] - x[is1])  # [mm/Volt]
            if np.abs(x[is1]) < np.abs(x[is2]):
                index = is1
            else:
                index = is2
            params[i]['minindex'] = index
            params[i]['minvoltage'] = x[index]
            di = int(abs(is2 - is1) / 2.0)
            ir1 = max([xi[0], index - di])
            ir2 = min([xi[-1], index + di])
            params[i]['range'] = [ir1, ir2]
            # debug draw 11 Range and scale calculation
            self.debugDraw([i, xi, y, ix[ir1:ir2], y[ir1 - xi[0]:ir2 - xi[0]], is1, is2])
        # filter scales
        sc0 = np.array([params[i]['scale'] for i in range(1, nx)])
        sc = sc0.copy()
        asc = np.average(sc)
        ssc = np.std(sc)
        while ssc > 0.3 * np.abs(asc):
            index1 = np.where(abs(sc - asc) <= 2.0 * ssc)[0]
            index2 = np.where(abs(sc - asc) > 2.0 * ssc)[0]
            sc[index2] = np.average(sc[index1])
            asc = np.average(sc)
            ssc = np.std(sc)
        for i in range(1, nx):
            params[i]['scale'] = sc[i - 1]
            # save processed to member variable
        self.paramsAuto = params

        # common parameters
        self.logger.info('Set common parameters ...')
        # Default parameters of measurements
        params[0]['R'] = 2.0e5  # Ohm   Resistor for scanner FC
        params[0]['d1'] = 0.5  # mm    Scanner analyzer hole diameter
        params[0]['d2'] = 0.5  # mm    Scanner FC slit width
        params[0]['l1'] = 213.0  # mm    Distance from emission hole to scanner analyzer hole
        params[0]['l2'] = 195.0  # mm    Scanner base

        # X0 and ndh calculation
        l1 = self.read_parameter(0, "l1", 213.0, float)
        l2 = self.read_parameter(0, "l2", 195.0, float)
        x00 = np.zeros(nx - 1)
        for i in range(1, nx):
            s = self.read_parameter(i, "scale", 2.0, float)
            u = self.read_parameter(i, "minvoltage", 0.0, float)
            x00[i - 1] = -s * u * l1 / l2
            # self.logger.info('%3d N=%d Umin=%f scale=%f X00=%f'%(i, j, u, s, x00[i-1]))
        npt = 0
        sp = 0.0
        nmt = 0
        sm = 0.0
        dx = x00.copy() * 0.0
        # self.logger.info('%3d X00=%f DX=%f'%(0, x00[0], 0.0))
        for i in range(1, nx - 1):
            dx[i] = x00[i] - x00[i - 1]
            if dx[i] > 0.0:
                npt += 1
                sp += dx[i]
            if dx[i] < 0.0:
                nmt += 1
                sm += dx[i]
            # self.logger.info('%3d X00=%f DX=%f'%(i, x00[i], dx[i]))
        # self.logger.info('npt=%d %f nmt=%d %f %f'%(npt,sp/npt,nmt,sm/nmt,sp/npt-l1/l2*10.))
        x01 = x00.copy()
        h = x00.copy() * 0.0
        for i in range(1, nx - 1):
            if npt > nmt:
                x01[i] = x01[i - 1] + sp / npt
                if dx[i] > 0.0:
                    h[i] = h[i - 1]
                else:
                    h[i] = h[i - 1] + 10.0
            else:
                x01[i] = x01[i - 1] + sm / nmt
                if dx[i] < 0.0:
                    h[i] = h[i - 1]
                else:
                    h[i] = h[i - 1] - 10.0
        x01 = x01 - np.average(x01)
        k = int(np.argmin(np.abs(x01)))
        h = h - h[k]
        for i in range(1, nx):
            params[i]['ndh'] = h[i - 1]
            s = self.read_parameter(i, "scale", 1.7, float)
            u = self.read_parameter(i, "minvoltage", 0.0, float)
            x01[i - 1] = (h[i - 1] - s * u) * l1 / l2
            params[i]['x0'] = x01[i - 1]
            # self.logger.info('%3d'%i, end='  ')
            # self.logger.info('X0=%f mm ndh=%4.1f mm'%(params[i]['x0'],params[i]['ndh']), end='  ')
            # self.logger.info('X00=%f mm DX=%f mm'%(x00[i-1], dx[i-1]))
        # self.logger.info calculated parameters
        self.logger.info('Calculated parameters:')
        s = ''
        for i in range(nx):
            try:
                s = 'Chan.%3d ' % i
                s = s + 'range=%s; ' % str(params[i]['range'])
                s = s + 'offset=%f V; ' % params[i]['offset']
                s = s + 'scale=%6.2f mm/V; ' % params[i]['scale']
                s = s + 'MinI=%4d; Umin=%6.2f V; ' % (params[i]['minindex'], params[i]['minvoltage'])
                s = s + 'x0=%5.1f mm; ndh=%5.1f mm' % (params[i]['x0'], params[i]['ndh'])
            except:
                pass
            self.logger.info(s)
        self.logger.info('Actual parameters:')
        for i in range(nx):
            try:
                s = 'Chan.%3d ' % i
                s = s + 'range=%s; ' % str(self.read_parameter(i, "range"))
                s = s + 'offset=%f V; ' % self.read_parameter(i, "offset")
                s = s + 'scale=%6.2f mm/V; ' % self.read_parameter(i, "scale")
                s = s + 'MinI=%4d; ' % (self.read_parameter(i, "minindex"))
                s = s + 'Umin=%6.2f V; ' % (self.read_parameter(i, "minvoltage"))
                s = s + 'x0=%5.1f mm; ' % (self.read_parameter(i, "x0"))
                s = s + 'ndh=%5.1f mm' % (self.read_parameter(i, "ndh"))
            except:
                pass
            self.logger.info(s)
        # debug draw X0 calculation
        self.debugDraw([x01, nx, k])
        # save processed to member variable
        self.paramsAuto = params
        self.logger.info('Auto parameters has been calculated')
        self.saveData(folder=self.folderName)
        return True

    def debugDraw(self, par=()):
        try:
            axes = self.mplWidget.canvas.ax
            # debug draw 17
            # self.debugDraw([Y3, Z3, Y1, Z1])
            if int(self.comboBox.currentIndex()) == 17:
                Y3 = par[0]
                Z3 = par[1]
                Y1 = par[2]
                Z1 = par[3]
                self.clearPicture()
                indexes = self.listWidget.selectedIndexes()
                for j in indexes:
                    k = j.row()
                    self.plot(Y3[:, k - 1] * 1e3, Z3[:, k - 1] * 1e6, '.-', label='sh' + str(k))
                    self.plot(Y1[:, k - 1] * 1e3, Z1[:, k - 1] * 1e6, '.-', label='or' + str(k))
                axes.set_title('Shifted elementary jets')
                axes.set_xlabel('X\', milliRadians')
                axes.set_ylabel('Current, mkA')
                self.mplWidget.canvas.draw()
                return
            # debug draw 11
            # self.debugDraw([X3, Y3, Z3])
            if int(self.comboBox.currentIndex()) == 11:
                X3 = par[0]
                Y3 = par[1]
                Z3 = par[2]
                self.clearPicture()
                axes.contour(X3, Y3, Z3)
                axes.grid(True)
                axes.set_title('Z3 [N,nx-1] Regular divergence reduced')
                self.mplWidget.canvas.draw()
                return
            # debug draw 12 Scan voltage region
            # self.debugDraw([ix,x,ix[xi],x[xi]])
            if int(self.comboBox.currentIndex()) == 12:
                self.clearPicture()
                axes.set_title('Scan voltage region')
                axes.set_xlabel('Point index')
                axes.set_ylabel('Voltage, V')
                axes.plot(par[0], par[1], label='Scan voltage')
                axes.plot(par[2], par[3], '.', label='Region')
                self.zoplot()
                axes.grid(True)
                axes.legend(loc='best')
                self.mplWidget.canvas.draw()
                return
            # debug draw 13 Offset calculation
            # self.debugDraw([i,ix,y1,o1,y2,o2,i1,i2])
            if int(self.comboBox.currentIndex()) == 13:
                indexes = self.listWidget.selectedIndexes()
                i = par[0]
                ix = par[1]
                y1 = par[2]
                o1 = par[3]
                y2 = par[4]
                o2 = par[5]
                i1 = par[6]
                i2 = par[7]
                if (len(indexes) > 0) and (i == indexes[0].row()):
                    self.clearPicture()
                    axes.set_title('Offset calculation')
                    axes.set_xlabel('Point index')
                    axes.set_ylabel('Signal, V')
                    axes.plot(ix, y1, 'r', label='raw' + str(i))
                    self.zoplot(o1, 'r')
                    axes.plot(ix, y2, 'b', label='raw' + str(i + 1))
                    self.zoplot(o2, 'b')
                    axes.plot(ix[i1], y1[i1], '.')
                    axes.plot(ix[i2], y2[i2], '.')
                    axes.grid(True)
                    axes.legend(loc='best')
                    self.mplWidget.canvas.draw()
                return
            # debug draw 14 zero line intermediate results
            # self.debugDraw([ix, par, zero, params])
            if int(self.comboBox.currentIndex()) == 14:
                ix = par[0]
                d = par[1]
                zero = par[2]
                params = par[3]
                indexes = self.listWidget.selectedIndexes()
                if len(indexes) > 0:
                    k = indexes[0].row()
                    self.clearPicture()
                    axes.set_title('Zero line calculation')
                    axes.set_xlabel('Point index')
                    axes.set_ylabel('Signal, V')
                    axes.plot(ix, d[k, :], label='raw ' + str(k))
                    z = zero[k].copy() + params[k]['offset']
                    smooth(z, params[k]['smooth'] * 2)
                    axes.plot(ix, z, label='zero' + str(k))
                    axes.grid(True)
                    axes.legend(loc='best')
                    self.mplWidget.canvas.draw()
                return
            # debug draw 15 Range and scale calculation
            # self.debugDraw([i,xi,y,ix[ir1:ir2],y[ir1 - xi[0]:ir2 - xi[0]],is1,is2])
            if int(self.comboBox.currentIndex()) == 15:
                indexes = self.listWidget.selectedIndexes()
                i = par[0]
                if (len(indexes) > 0) and (i == indexes[0].row()):
                    self.clearPicture()
                    axes.set_title('Range and scale calculation')
                    axes.set_xlabel('Point index')
                    axes.set_ylabel('Signal, V')
                    axes.plot(par[1], par[2], label='proc ' + str(i))
                    axes.plot(par[3], par[4], '.', label='range' + str(i))
                    self.voplot(par[5], 'r')
                    self.voplot(par[6], 'b')
                    axes.grid(True)
                    axes.legend(loc='best')
                    self.mplWidget.canvas.draw()
            # debug draw 16 X0 calculation
            # self.debugDraw([x01,nx,k])
            if int(self.comboBox.currentIndex()) == 16:
                x01 = par[0]
                nx = par[1]
                k = par[2]
                x0 = x01.copy()
                for i in range(1, nx):
                    x0[i - 1] = self.read_parameter(i, 'x0', 0.0, float)
                self.clearPicture()
                axes.set_title('X0 calculation')
                axes.set_xlabel('Index')
                axes.set_ylabel('X0, mm')
                axes.plot(x01 - x01[k], 'o-', label='X0 calculated')
                axes.plot(x0 - x0[k], 'd-', label='X0 from parameters')
                axes.grid(True)
                axes.legend(loc='best')
                self.mplWidget.canvas.draw()
                return
        except:
            self.print_exception_info()

    def read_parameter(self, row, name, default=None, dtype=None, info=False, select=''):
        if name == 'zero':
            return self.read_zero(row)
        vd = default
        t = 'default'
        v = vd
        try:
            va = self.paramsAuto[row][name]
            t = 'auto'
            v = va
        except:
            va = None
        try:
            vm = self.paramsManual[row][name]
            t = 'manual'
            v = vm
        except:
            vm = None
        if dtype is not None:
            v = dtype(v)
        if info:
            self.logger.info('row:%d parameter:%s; return %s value:%s (default:%s; auto:%s; manual:%s)' % (
                row, name, t, str(v), str(vd), str(va), str(vm)))
        if select == 'manual':
            return vm
        if select == 'auto':
            return va
        if select == 'default':
            return vd
        return v

    def read_zero(self, row):
        if self.data is None:
            return None
        try:
            z = self.paramsAuto[row]['zero'].copy()
        except:
            z = np.zeros_like(self.data[0])
        # manual zero line
        try:
            # manual regions
            zr = self.paramsManual[row]['zero']
            for zi in zr:
                try:
                    if zi[0] == -2:
                        # linear interpolation between (x1,y1) (x2,y2) 
                        x1 = zi[1]
                        y1 = zi[2]
                        x2 = zi[3]
                        y2 = zi[4]
                        z[x1:x2 + 1] = np.interp(np.arange(x1, x2 + 1), [x1, x2], [y1, y2])
                    if zi[0] == -1:
                        # linear interpolation (-1, n1, n2)  y(n) = zeroLine(n)
                        z0 = self.data[row, :].copy()
                        ns = self.read_parameter(row, "smooth", self.spinBox.value(), int)
                        smooth(z0, ns)
                        of = self.read_parameter(row, "offset", 0.0, float)
                        z0 = z0 - of  # minus is correct !!!
                        y1 = z0[zi[1]]
                        y2 = z0[zi[2]]
                        z[zi[1]:zi[2] + 1] = np.interp(np.arange(zi[1], zi[2] + 1), [zi[1], zi[2]], [y1, y2])
                    if zi[0] > 0:
                        z0 = self.data[zi[0], :].copy()
                        ns = self.read_parameter(zi[0], "smooth", 1, int)
                        of = self.read_parameter(zi[0], "offset", 0.0, float)
                        smooth(z0, 2 * ns)
                        z[zi[1]:zi[2]] = z0[zi[1]:zi[2]] + of
                except:
                    pass
        except:
            pass
        return z

    def readSignal(self, row):
        if self.data is None:
            return (None, None, None)
        # self.logger.info('Processing %d'%row)
        # scan voltage
        u = self.data[0, :].copy()
        # smooth
        ns = self.read_parameter(0, "smooth", 100, int)
        smooth(u, 2 * ns)
        # signal
        y = self.data[row, :].copy()
        # smooth
        ns = self.read_parameter(row, "smooth", 1, int)
        # offset
        of = self.read_parameter(row, "offset", 0.0, float)
        # zero line
        z = self.read_zero(row)
        # smooth
        smooth(y, ns)
        smooth(z, 2 * ns)
        # subtract offset and zero
        y = y - z - of
        # load resistor
        R = self.read_parameter(0, "R", 2.0e5, float)
        # convert signal to Amperes
        y = y / R
        # signal region
        r0 = self.read_parameter(0, "range", (0, len(y)))
        r = self.read_parameter(row, "range", r0)
        index = np.arange(r[0], r[1])
        # scale
        s = self.read_parameter(row, "scale", 2.0, float)
        # ndh
        ndh = self.read_parameter(row, "ndh", 0.0, float)
        # scanner base
        l1 = self.read_parameter(0, "l1", 195.0, float)
        l2 = self.read_parameter(0, "l2", 195.0, float)
        x0 = self.read_parameter(row, "x0", 0.0, float)
        # x' in Radians
        xsub = (ndh - s*u)/l2
        return xsub, y, index

    def smoothX(self, x, y):
        # filter x to be unique and monotonic
        ux, ui = np.unique(x, return_index=True)
        return ux, y[ui]
        # n = len(x)
        # xmax = x.max()
        # xmin = x.min()
        # dx = (xmax - xmin) / (n - 1)
        # ys = np.zeros(n)
        # yn = np.zeros(n)
        # m = np.floor((x - xmin) / dx)
        # for i in range(n):
        #     k = int(m[i])
        #     ys[k] += y[i]
        #     yn[k] += 1.0
        # mask = yn > 0.0
        # ay = np.zeros(n)
        # ay[mask] = ys[mask] / yn[mask]
        # # maskn = np.logical_not(mask)
        # ax = np.linspace(xmin, xmax, n)
        # return (ax[mask].copy(), ay[mask].copy())

    def read_x0(self, nx=None, init=False):
        if nx is None:
            nx = len(self.fileNames)
        if nx <= 0:
            return
        if init:
            self.execInitScript()
        x0 = np.linspace(-(nx - 1)/2.0, (nx - 1)/2.0, nx - 1) # [mm] X0 coordinates of scans
        flag = self.read_parameter(0, 'autox0', False)
        for i in range(1, nx):
            if flag:
                x0[i - 1] = self.read_parameter(i, 'x0', 0.0, float, select='auto')
            else:
                x0[i - 1] = self.read_parameter(i, 'x0', 0.0, float)
        return x0

    def plot(self, *args, **kwargs):
        axes = self.mplWidget.canvas.ax
        axes.plot(*args, **kwargs)
        # zoplot()
        # xlim = axes.get_xlim()
        # axes.plot(xlim, [0.0, 0.0], color='k')
        # axes.set_xlim(xlim)
        axes.grid(True)
        axes.legend(loc='best')
        self.mplWidget.canvas.draw()

    def draw(self):
        self.mplWidget.canvas.draw()

    def zoplot(self, v=0.0, color='k'):
        axes = self.mplWidget.canvas.ax
        xlim = axes.get_xlim()
        axes.plot(xlim, [v, v], color=color)
        axes.set_xlim(xlim)

    def voplot(self, v=0.0, color='k'):
        axes = self.mplWidget.canvas.ax
        ylim = axes.get_ylim()
        axes.plot([v, v], ylim, color=color)
        axes.set_ylim(ylim)

    def cls(self):
        self.clearPicture()

    def get_x(self):
        ix = self.spinBox_2.value()
        if ix >= 0:
            x = self.data[ix, :].copy()
            ns = self.read_parameter(ix, "smooth", self.spinBox.value(), int, True)
            smooth(x, ns)
            title = 'Channel %d Voltage, V' % ix
        else:
            x = np.arange(len(self.data[0, :]))
            title = 'Index'
        return x, title

    def plot_raw_signals(self, indexes=()):
        if self.data is None:
            return
        if len(indexes) <= 0:
            indexes = self.listWidget.selectedIndexes()
        if len(indexes) <= 0:
            return
        self.execInitScript()
        self.clearPicture()
        axes = self.mplWidget.canvas.ax
        x, xTitle = self.get_x()
        for i in indexes:
            if hasattr(i, 'row'):
                row = i.row()
            else:
                row = i
            y = self.data[row, :].copy() - self.read_parameter(row, 'offset')
            ns = self.read_parameter(row, "smooth", self.spinBox.value(), int)
            smooth(y, ns)
            z = self.read_zero(row)
            axes.plot(x, y, label='raw - offset ' + str(row))
            axes.plot(x, z, label='zero' + str(row))
        self.zoplot()
        axes.grid(True)
        axes.set_title('Signals with zero line')
        axes.set_xlabel(xTitle)
        axes.set_ylabel('Voltage, V')
        axes.legend(loc='best')
        self.mplWidget.canvas.draw()

    def plotProcessedSignals(self):
        """Plots processed signals"""
        if self.data is None:
            return
        indexes = self.listWidget.selectedIndexes()
        if len(indexes) <= 0:
            return
        self.execInitScript()
        self.clearPicture()
        axes = self.mplWidget.canvas.ax
        x, x_title = self.get_x()
        # draw chart
        for i in indexes:
            row = i.row()
            u, y, index = self.readSignal(row)
            # convert back from Amperes to Volts
            y = y * self.read_parameter(0, "R", 2.0e5, float)
            # plot processed signal
            self.plot(x, y, label='proc ' + str(row))
            # highlight signal region
            self.plot(x[index], y[index], label='range' + str(row))
            self.logger.info('Plot Processed Signal %d' % row)
            # print parameters
            self.read_parameter(row, "smooth", 1, int, True)
            self.read_parameter(row, "offset", 0.0, float, True)
            self.read_parameter(row, "scale", 0.0, float, True)
            self.read_parameter(row, "x0", 0.0, float, True)
            self.read_parameter(row, "ndh", 0.0, float, True)
            # range vertical lines
            r = self.read_parameter(row, "range", (0, -1), None, True)
            self.voplot(x[r[0]])
            self.voplot(x[r[1] - 1])
        # plot zero line
        self.zoplot()
        axes.set_title('Processed Signals')
        axes.set_xlabel(x_title)
        axes.set_ylabel('Voltage, V')
        axes.legend(loc='best')
        # force an image redraw
        self.draw()

    def onclick(self, event):
        self.logger.info('button=%d, x=%d, y=%d, xdata=%f, ydata=%f' %
                         (event.button, event.x, event.y, event.xdata, event.ydata))

    def pickZeroLine(self):
        if self.data is None:
            return
        self.execInitScript()
        axes = self.mplWidget.canvas.ax
        self.clearPicture()
        indexes = self.listWidget.selectedIndexes()
        if len(indexes) <= 0:
            return
        # draw chart
        row = indexes[0].row()
        x, xTitle = self.get_x()
        y = self.data[row, :].copy()
        ns = self.read_parameter(row, "smooth", self.spinBox.value(), int)
        smooth(y, ns)
        z = self.read_zero(row) + self.read_parameter(row, 'offset')
        axes.plot(x, y, label='raw ' + str(row))
        axes.plot(x, z, label='zero' + str(row))
        self.zoplot()
        axes.grid(True)
        axes.set_title('Signal %s with zero line' % str(row))
        axes.set_xlabel(xTitle)
        axes.set_ylabel('Signal Voltage, V')
        axes.legend(loc='best')
        self.mplWidget.canvas.draw()
        # connect mouse button press event
        # self.cid = self.mplWidget.canvas.mpl_connect('button_press_event', self.onclick)
        # self.mplWidget.canvas.mpl_disconnect(cid)

    def plotElementaryJets(self):
        """Plot elementary jet profile"""
        if self.data is None:
            return
        self.execInitScript()
        axes = self.mplWidget.canvas.ax
        self.clearPicture()
        # draw chart
        indexes = self.listWidget.selectedIndexes()
        for i in indexes:
            row = i.row()
            x, y, index = self.readSignal(row)
            xx = x[index] * 1000.0  # convert to milliRadians
            yy = -1.0e6 * y[index]  # convert to microAmpers
            axes.plot(xx, yy, label='jet ' + str(row))
            # axes.plot(xx, gaussfit(xx, yy), '--', label='gauss '+str(row))
        # plot axis y=0
        axes.plot(axes.get_xlim(), [0.0, 0.0], color='k')
        # decorate the plot
        axes.grid(True)
        axes.set_title('Elementary jet profile')
        axes.set_xlabel('X\', milliRadians')
        axes.set_ylabel('Signal, mkA')
        axes.legend(loc='best')
        self.mplWidget.canvas.draw()

    def pushPlotButton(self):
        if self.data is None:
            return
        nx = len(self.fileNames)
        if nx <= 0:
            return

        if int(self.comboBox.currentIndex()) == 0:
            self.plot_raw_signals()
            return
        if int(self.comboBox.currentIndex()) == 1:
            self.plotProcessedSignals()
            return
        if int(self.comboBox.currentIndex()) == 2:
            self.plotElementaryJets()
            return
        if int(self.comboBox.currentIndex()) == 3:
            self.calculateProfiles()
            return
        if int(self.comboBox.currentIndex()) == 4:
            self.calculateProfiles()
            return
        self.calculateEmittance()

    def calculateProfiles(self):
        nx = len(self.fileNames)
        if nx <= 0:
            return

        self.execInitScript()

        # calculate common values
        x0 = np.zeros(nx - 1)  # [mm] X0 coordinates of scans
        flag = self.read_parameter(0, 'autox0', False)
        # self.logger.info('', stamp=False)
        # self.logger.info('Emittance calculation using parameters:')
        # self.logger.info('Use calculated X0 = %s'%str(flag))
        for i in range(1, nx):
            if flag:
                x0[i - 1] = self.read_parameter(i, 'x0', 0.0, float, select='auto')
            else:
                x0[i - 1] = self.read_parameter(i, 'x0', 0.0, float)
        # parameters
        # R
        R = self.read_parameter(0, 'R', 2.0e5, float)  # [Ohm] Faraday cup load resistior
        # l1
        l1 = self.read_parameter(0, 'l1', 213.0, float)  # [mm] distance from source to analyzer aperture
        # l2
        l2 = self.read_parameter(0, 'l2', 195.0, float)  # [mm] analyzer base
        # d1 and hole area
        d1 = self.read_parameter(0, 'd1', 0.4, float)  # [mm] analyzer hole diameter
        a1 = np.pi * d1 * d1 / 4.0  # [mm**2] analyzer hole area
        # d2
        d2 = self.read_parameter(0, 'd2', 0.5, float)  # [mm] analyzer slit width
        # self.logger.info('R=%fOhm l1=%fmm l2=%fmm d1=%fmm d2=%fmm'%(R,l1,l2,d1,d2))
        # calculate maximum and integral profiles
        self.profilemax = np.zeros(nx - 1)
        self.profileint = np.zeros(nx - 1)
        for i in range(1, nx):
            try:
                x, y, index = self.readSignal(i)  # x - [Radians] y - [A]
                yy = y[index]
                xx = x[index]
                # select unique x values for spline interpolation
                xu, h = np.unique(xx, return_index=True)
                # self.logger.info(i,h)
                yu = yy[h]  # [A]
                self.profilemax[i - 1] = -1.0 * np.min(yu)  # [A]
                yu = yu / (d2 / l2)  # convert Y to density [A/Radian]
                # integrate by trapezoids method
                self.profileint[i - 1] = -1.0 * trapz(yu, xu)  # [A]
                # self.logger.info(i, self.profileint[i-1])
            except:
                self.print_exception_info()
        # sort in x0 increasing order
        ix0 = np.argsort(x0)
        x0s = x0[ix0]
        # self.logger.info(x0s)
        self.profileint = self.profileint[ix0]
        # self.logger.info(self.profileint)
        self.profilemax = self.profilemax[ix0]
        # self.logger.info(self.profilemax)
        # remove average x
        xavg = trapz(x0s * self.profileint, x0s) / trapz(self.profileint, x0s)
        # self.logger.info('Average X %f mm'%xavg)
        x0s = x0s - xavg
        self.profileint = self.profileint / a1  # convert to local current density [A/mm^2]
        # cross-section current
        self.Ics = trapz(self.profileint, x0s) * d1  # [A] -  integrate over x and multiply to y width
        self.logger.info('Cross-section current %f mkA' % (self.Ics * 1e6))  # from Amperes to mA
        # calculate total current
        index = np.where(x0s >= 0.0)[0]
        Ir = trapz(x0s[index] * self.profileint[index], x0s[index]) * 2.0 * np.pi
        # self.logger.info('Total current right %f mA'%(Ir*1000.0)) # from Amperes to mA
        index = np.where(x0s <= 0.0)[0]
        Il = -1.0 * trapz(x0s[index] * self.profileint[index], x0s[index]) * 2.0 * np.pi
        # self.logger.info('Total current left %f mA'%(Il*1000.0)) # from Amperes to mA
        self.I = (Il + Ir) / 2.0  # [A]
        self.logger.info('Total current %f mA' % (self.I * 1000.0))  # from Amperes to mA
        # save profile data
        folder = self.folderName
        fn = os.path.join(str(folder), 'InegralProfile.txt')
        np.savetxt(fn, np.array([x0, self.profileint]).T, delimiter='; ')
        fn = os.path.join(str(folder), 'MaximumProfile.txt')
        np.savetxt(fn, np.array([x0, self.profilemax]).T, delimiter='; ')
        # plot profiles
        axes = self.mplWidget.canvas.ax
        # plot integral profile
        if int(self.comboBox.currentIndex()) == 3:
            self.clearPicture()
            axes.set_title('Integral profile')
            axes.set_xlabel('X0, mm')
            axes.set_ylabel('Beamlet current, mkA')
            axes.plot(x0s, self.profileint * 1.0e6, 'd-', label='Integral Profile')
            # axes.plot(x0s, gaussfit(x0s,profileint,x0s), '--', label='Gaussian fit')
            axes.grid(True)
            axes.legend(loc='best')
            axes.annotate(
                'Total current %4.1f mA' % (self.I * 1000.0) + ' Cross-section current %4.1f mkA' % (self.Ics * 1e6),
                xy=(.5, .2), xycoords='figure fraction',
                horizontalalignment='center', verticalalignment='top',
                fontsize=11)
            self.mplWidget.canvas.draw()
            return
        # plot maximal profile
        if int(self.comboBox.currentIndex()) == 4:
            self.clearPicture()
            axes.set_title('Maximum profile')
            axes.set_xlabel('X0, mm')
            axes.set_ylabel('Maximal current, mkA')
            axes.plot(x0s, self.profilemax * 1.0e6, 'o-', label='Maximum Profile')
            # axes.plot(x0s, gaussfit(x0s,profilemax,x0s), '--', label='Gaussian fit')
            axes.grid(True)
            axes.legend(loc='best')
            axes.annotate(
                'Total current %4.1f mA' % (self.I * 1000.0) + ' Cross-section current %4.1f mkA' % (self.Ics * 1e6),
                xy=(.5, .2), xycoords='figure fraction',
                horizontalalignment='center', verticalalignment='top',
                fontsize=11)
            self.mplWidget.canvas.draw()

    def map(self, f, x, y):
        result = np.zeros_like(x)
        if x.size > 1 and y.size > 1:
            if x.shape != y.shape:
                raise IndexError('X and Y shape mismatch')
        elif x.size == 1:
            x = np.full_like(y, x[0])
            result = np.zeros_like(y)
        elif y.size == 1:
            y = np.full_like(x, y[0])
        for i in range(result.size):
            result.flat[i] = f(x.flat[i], y.flat[i])
        return result

    def interpolate(self, x, s, F):
        # # linear regression into shift
        # shift_k = ((x*s).mean() - x.mean()*s.mean()) / ((x*x).mean() - x.mean()**2)
        # shift_b = s.mean() - shift_k * x.mean()
        x1 = x.copy()
        # s1 = s.copy()
        nx = len(x1)
        x_min = x1.min()
        x_max = x1.max()
        deltax = x1[1:] - x[:-1]
        deltas = s[1:] - s[:-1]
        d = deltas / deltax
        def f(x, y):
            if x > x_max or x < x_min:
                return 0.0
            for i in range(nx):
                if x1[i] > x:
                    break
            xi = i
            i1 = i - 1
            if xi == 0:
                return F[0](y)
            d1 = x - x1[i1]
            d2 = x1[xi] - x
            dd = d[i1]
            f1 = F[i1](y - dd * d1)
            f2 = F[xi](y + dd * d2)
            return (f1 * d2 + f2 * d1) / deltax[i1]
        return f

    def integrate2d(self, x, y, z):
        sh = np.shape(z)
        n = sh[1]
        v = np.zeros(n, dtype=np.float64)
        for i in range(n):
            v[i] = trapz(z[:, i], y[:, i])
        return trapz(v, x[0, :])

    def calculate_vertical_shift(self, y, f):
        nx = len(f)
        shift = np.zeros(nx)
        values = np.zeros(nx)
        for i in range(nx):
            zz = f[i](y)
            imax = np.argmax(zz)
            diap = np.linspace(y[imax-5], y[imax+5], 100)
            zz = f[i](diap)
            imax = np.argmax(zz)
            shift[i] = diap[imax]
            values[i] = zz[imax]
        return shift, values

    def grid(self, x, y, n, nx=None, ny=None):
        limx = max(abs(x.max()), abs(x.min()))
        if nx is None:
            nx = n
        xg = np.linspace(-limx, limx, nx)
        limy = max(abs(y.max()), abs(y.min()))
        if ny is None:
            ny = n
        yg = np.linspace(-limy, limy, ny)
        grid_x, grid_y = np.meshgrid(xg, yg)
        return grid_x, grid_y

    def calculateEmittance(self):
        if self.data is None:
            return
        # number of traces
        nx = len(self.fileNames)
        if nx <= 0:
            return
        # plot area axes
        axes = self.mplWidget.canvas.ax
        # init manual parameters
        self.execInitScript()
        # constants
        q = 1.6e-19         # [Q] electron charge
        mp = 1.6726e-27     # [kg] proton mass
        me = 9.1093e-31     # [kg] electron mass
        c = 2.9979e8        # [m/s] speed of light
        # parameters
        R = self.read_parameter(0, 'R', 2.0e5, float)    # [Ohm] Faraday cup load resistor
        L1 = self.read_parameter(0, 'l1', 213.0, float)  # [mm] distance from source to analyzer aperture
        L2 = self.read_parameter(0, 'l2', 195.0, float)  # [mm] analyzer base
        d1 = self.read_parameter(0, 'd1', 0.5, float)    # [mm] analyzer hole diameter
        a1 = np.pi * d1 * d1 / 4.0                      # [mm**2] analyzer hole area
        d2 = self.read_parameter(0, 'd2', 0.5, float)    # [mm] analyzer slit width
        ny = self.read_parameter(0, 'N', 200, int)        # number of points for emittance matrix
        U = self.read_parameter(0, 'energy', 32000.0, float)
        # calculated parameters
        mhm = mp + 2.0*me               # mass of H-
        V = np.sqrt(2.0 * q * U / mhm)  # [m/s] non relativistic H- speed
        beta = V / c                    # beta = V/c
        # channels parameters
        x0 = self.read_x0()         # [mm] X0 coordinates of scans
        ndh = np.zeros_like(x0)     # [mm] displacement of analyzer slit (number n) from axis
        ranges = []
        scales = []
        offsets = []
        for i in range(1, nx):
            ndh[i - 1] = self.read_parameter(i, 'ndh', 0.0, float)
            ranges.append(self.read_parameter(i, 'range', [10, 9990]))
            scales.append(self.read_parameter(i, 'scale', 2.0, float))
            offsets.append(self.read_parameter(i, 'offset', 0.0, float))
        # print parameters
        self.logger.info('\n-------------------------------------------')
        self.logger.info('Emittance calculation parameters:')
        self.logger.info('Beam energy U=%f [V]', U)
        self.logger.info('H- speed V=%e [m/s]', V)
        self.logger.info('Beam beta=%e', beta)
        self.logger.info('Load resistor R=%f [Ohm]', R)
        self.logger.info('From source to the scanner L1=%f [mm]', L1)
        self.logger.info('Scanner base L2=%f [mm]', L2)
        self.logger.info('Aperture diameter d1=%f [mm]', d1)
        self.logger.info('Slit width d2=%f [mm]', d2)
        s = ''
        for i in range(nx):
            s = 'Chan.%3d ' % i
            if i > 0:
                s += 'x0=%5.1f [mm]; ndh=%5.1f [mm]; ' % (x0[i-1], ndh[i-1])
                s += 'range=%s; ' % str(ranges[i-1])
                s += 'offset=%f [V]; ' % offsets[i-1]
                self.logger.info(s)

        # calculate maximum and integral profiles
        self.calculateProfiles()

        # test x0 for unique and sort for all channel except 0
        x0u, x0i = np.unique(x0[1:], return_index=True)
        if len(x0u) != len(x0)-1:
            self.logger.info('Non unique X0 found')
        nx = len(x0i)
        # create (N x nx) initial arrays
        # X [mm] -- X axis of emittance plot
        X0 = np.zeros((ny, nx), dtype=np.float64)
        # X' [radians] --  Y axis  of emittance plot
        Y0 = np.zeros((ny, nx), dtype=np.float64)
        # Z [V] -> [mkA] measured signals
        Z0 = np.zeros((ny, nx), dtype=np.float64)
        # F interpolating functions Z[i,j] = F[i](Y[i,j])
        F0 = list(range(nx))
        # calculate interpolating functions for initial data
        ymin = 1e9
        ymax = -1e9
        for i in range(nx):
            y, z, index = self.readSignal(x0i[i] + 1)  # y in [Radians]; z < 0.0 in [A]
            yy = y[index]
            ymin = min(ymin, yy.min())
            ymax = max(ymax, yy.max())
            # convert to [Ampere/Radian/mm^2]
            zz = z[index] * L2 / d2 / a1
            yyy, ui = np.unique(yy, return_index=True)
            zzz = zz[ui]
            F0[x0i[i]] = interp1d(yyy, -zzz, kind='cubic', bounds_error=False, fill_value=0.0)
        # symmetry for Y range
        ymax = max(abs(ymin), abs(ymax))
        ymin = -ymax
        # Y range array
        ys = np.linspace(ymin, ymax, ny)
        # fill data arrays
        for i in range(nx):
            X0[:, i] = x0u[i]
            Y0[:, i] = ys
            Z0[:, i] = F0[i](ys)
        self.logger.info('Z0 min = %s max = %s', Z0.min(), Z0.max())
        # remove negative data
        Z0[Z0 < 0.0] = 0.0
        # plot Z0 - initial signals
        if int(self.comboBox.currentIndex()) == 10:
            # initial data
            self.clearPicture()
            axes.contour(X0, Y0, Z0)
            axes.grid(True)
            axes.set_title('Z0 initial data x0 sorted')
            self.mplWidget.canvas.draw()
            plt.matshow(Z0)
            return

        # X0,Y0,Z0 -> X1,Y1,Z1 remove average X0 and Y0
        X0avg = 0.0
        Y0avg = 0.0
        if self.read_parameter(0, 'center', 'avg') == 'max':
            n = np.argmax(Z0.flat)
            X0avg = X0.flat[n]
            Y0avg = Y0.flat[n]
        if self.read_parameter(0, 'center', 'avg') == 'avg':
            Z0t = self.integrate2d(X0, Y0, Z0)
            X0avg = self.integrate2d(X0, Y0, X0 * Z0) / Z0t
            Y0avg = self.integrate2d(X0, Y0, Y0 * Z0) / Z0t
        self.logger.info('Average X0 %s, Y0 %s', X0avg, Y0avg)
        Z1 = Z0.copy()
        X1 = X0.copy() - X0avg
        Y1 = Y0.copy() - Y0avg
        self.logger.info('Z1 min = %s max = %s', Z1.min(), Z1.max())
        Z1t = self.integrate2d(X1, Y1, Z1) * d2 * 1e6  # [mkA]
        self.logger.info('Total Z1 (cross-section current) = %f mkA' % Z1t)
        # plot Z1 = Z0 with shifted average X0 and Y0
        if int(self.comboBox.currentIndex()) == 11:
            # cross-section current
            self.clearPicture()
            axes.contour(X1, Y1, Z1)
            axes.grid(True)
            axes.set_title('Z1 Average shifted')
            self.mplWidget.canvas.draw()
            plt.matshow(Z1)
            return

        # maximum shift
        shift_y, shift_i = self.calculate_vertical_shift(Y0[:, 0], F0)
        x = X0[0, :]
        y = shift_y
        # linear regression into shift
        shift_k = ((x*y).mean() - x.mean()*y.mean()) / ((x*x).mean() - x.mean()**2)
        shift_b = y.mean() - shift_k * x.mean()
        self.logger.info('Maximum shift k = %s b = %s 1/L1 = %s', shift_k, shift_b, 1.0/L1)

        # X0,Y0,Z0 -> X2,Y2,Z2 interpolate for NxN grid
        #points = np.r_['1,2,0', X1.flat, Y1.flat]
        grid_x, grid_y = self.grid(X0, Y0, ny)
        #grid_z = griddata(points, Z1.flat, (grid_x, grid_y), method='linear', fill_value=0.0)
        g = self.interpolate(X0[0, :], shift_y, F0)
        grid_z = grid_x.copy()
        for i in range(grid_x.shape[0]):
            grid_z[:, i] = g(grid_x[0, i], grid_y[:, i])
        # grid_z = self.map(g, grid_x, grid_y)
        X2 = grid_x
        Y2 = grid_y
        Z2 = grid_z
        self.logger.info('Z2 min = %s max = %s', Z2.min(), Z2.max())
        # plot Z2 -> Z1 interpolated for NxN grid
        if int(self.comboBox.currentIndex()) == 12:
            self.clearPicture()
            axes.contour(X2, Y2, Z2)
            # plt.matshow(Z2)
            axes.set_title('Z2 NxN resampled')
            axes.grid(True)
            self.mplWidget.canvas.draw()
            return

        # X2,Y2,Z2 -> X3,Y3,Z3 remove average X2 and Y2
        X2avg = 0.0
        Y2avg = 0.0
        if self.read_parameter(0, 'center', 'avg') == 'max':
            n = np.argmax(Z2.flat)
            X2avg = X2.flat[n]
            Y2avg = Y2.flat[n]
        if self.read_parameter(0, 'center', 'avg') == 'avg':
            Z2t = self.integrate2d(X2, Y2, Z2)
            X2avg = self.integrate2d(X2, Y2, X2 * Z2) / Z2t
            Y2avg = self.integrate2d(X2, Y2, Y2 * Z2) / Z2t
        self.logger.info('Average X2 %s, Y2 %s', X2avg, Y2avg)
        Z3 = Z2.copy()
        X3 = X2.copy() - X2avg
        Y3 = Y2.copy() - Y2avg
        self.logger.info('Z3 min = %s max = %s', Z3.min(), Z3.max())
        Z3t = self.integrate2d(X3, Y3, Z3) * d2 * 1e6  # [mkA]
        self.logger.info('Total Z3 (cross-section current) = %f mkA' % Z3t)
        # plot Z3 remove average X2 and Y2
        if int(self.comboBox.currentIndex()) == 13:
            self.clearPicture()
            axes.contour(X3, Y3, Z3)
            axes.grid(True)
            axes.set_title('Z3 NxN Average shifted')
            self.mplWidget.canvas.draw()
            # plt.matshow(Z3)
            return

        # Emittance contour plot of beam cross-section
        # cross section RMS emittance calculations
        # X3,Y3,Z3 -> X5,Y5,Z5
        X5 = X3
        Y5 = Y3
        Z5 = Z3 * d1  # [A/mm/Radian]
        # self.logger.info('Removing average')
        Z5t = self.integrate2d(X5, Y5, Z5)  # [A]
        X5avg = self.integrate2d(X5, Y5, X5 * Z5) / Z5t
        Y5avg = self.integrate2d(X5, Y5, Y5 * Z5) / Z5t
        # subtract average values
        X5 = X5 - X5avg
        Y5 = Y5 - Y5avg
        # calculate moments
        # self.logger.info('Calculating RMS emittance')
        XY5avg = self.integrate2d(X5, Y5, X5 * Y5 * Z5) / Z5t
        XX5avg = self.integrate2d(X5, Y5, X5 * X5 * Z5) / Z5t
        YY5avg = self.integrate2d(X5, Y5, Y5 * Y5 * Z5) / Z5t
        # cross section RMS Emittance
        self.RMScs = np.sqrt(XX5avg * YY5avg - XY5avg * XY5avg) * 1000.0  # [Pi*mm*mrad]
        self.logger.info('Normalized RMS Emittance of cross-section %f Pi*mm*mrad' % (self.RMScs * beta))
        # save data to text file
        # self.logger.info('Saving data')
        folder = self.folderName
        fn = os.path.join(str(folder), _progName + '_X_cs.gz')
        np.savetxt(fn, X5, delimiter='; ')
        fn = os.path.join(str(folder), _progName + '_Y_cs.gz')
        np.savetxt(fn, Y5, delimiter='; ')
        fn = os.path.join(str(folder), _progName + '_Z_cs.gz')
        np.savetxt(fn, Z5, delimiter='; ')
        # plot
        if int(self.comboBox.currentIndex()) == 8:
            self.clearPicture()
            axes.contour(X5, Y5, Z5, linewidths=1.5)
            axes.grid(True)
            axes.set_title('Emittance contour plot of beam cross-section')
            axes.set_xlabel('X, mm')
            axes.set_ylabel('X\', milliRadians')
            axes.annotate('Cross-section I=%5.1f mkA' % (self.Ics * 1e6) + ';\nNorm. RMS Emittance %5.3f $\pi$*mm*mrad' % (
                    self.RMScs * beta),
                          xy=(.3, .2), xycoords='figure fraction',
                          horizontalalignment='left', verticalalignment='top',
                          fontsize=18)
            self.mplWidget.canvas.draw()
            return

        # X3,Y3,Z3 -> X4,Y4,Z4 integrate emittance from cross-section to circular beam
        t0 = time.time()
        X4 = X3
        Y4 = Y3
        Z4 = Z3.copy()
        x = X4[0, :].flatten()
        xi = np.arange(x.size)
        x_delta = x[1] - x[0]
        y_delta = Y4[1, 0] - Y4[0, 0]
        x_min = x.min()
        y_min = Y4[0, 0]
        y_max = Y4[-1, -1]
        x_d = x[1] - x[0]
        y = np.zeros_like(x)
        nx_ = x.size
        ny_ = Z4[:, 0].size
        for i in range(nx_):
            #print(100.0*i/(nx_ - 1), '%')
            xi = x[i]
            dx2 = x ** 2 - xi ** 2
            dxgz = dx2 >= 0.0
            if xi >= 0:
                mask = (x >= xi) * dxgz
                y = np.sqrt(dx2[mask])
            else:
                mask = (x <= xi) * dxgz
                y = -np.sqrt(dx2[mask])
            xmask = x[mask]
            for k in range(ny_):
                xsub = Y4[k, 0] + Y2avg - shift_k * (xi - xmask)
                mask = (xsub >= y_min) * (xsub <= ymax)
                xn = ((xmask-x_min)/x_delta).astype(int)[mask]
                yn = ((xsub-y_min)/y_delta).astype(int)[mask]
                z = self.map(g, xmask + X2avg, xsub)
                #z = Z2[xn, yn].flatten()

                v = 2.0 * trapz(z, y)
                # Z4[k, i] = v
                # xsub = Y4[:, 0] + Y2avg - shift_k * (xi - xmask)
                # z = g(xmask + X2avg, xsub)
                # v = 2.0 * trapz(z, y)
                Z4[:, i] = v

        self.logger.info('Elapsed %s seconds', time.time() - t0)
        self.logger.info('Z4 min = %s max = %s', Z4.min(), Z4.max())
        Z4[Z4 < 0.0] = 0.0
        Z4t = self.integrate2d(X4, Y4, Z4) * 1000.0  # [mA]
        self.logger.info('Total Z4 (beam current) = %f mA', Z4t)
        # plot
        if int(self.comboBox.currentIndex()) == 14:
            # total beam current
            self.clearPicture()
            axes.contour(X4, Y4, Z4)
            axes.grid(True)
            axes.set_title('Z4 NxN total beam')
            self.mplWidget.canvas.draw()
            plt.matshow(Z4)
            plt.show()
            return

        # calculate emittance values
        # X4,Y4,Z4 -> X,Y,Z final array X and Y centered to plot and emittance calculation
        X = X4
        Y = Y4
        Z = Z4  # [A/mm/Radian]
        Zt = self.integrate2d(X, Y, Z)  # [A]
        # calculate average X and X'
        Xavg = self.integrate2d(X, Y, X * Z) / Zt
        Yavg = self.integrate2d(X, Y, Y * Z) / Zt
        # subtract average values 
        X = X - Xavg
        Y = Y - Yavg
        # calculate moments 
        XYavg = self.integrate2d(X, Y, X * Y * Z) / Zt
        XXavg = self.integrate2d(X, Y, X * X * Z) / Zt
        YYavg = self.integrate2d(X, Y, Y * Y * Z) / Zt
        # RMS Emittance
        self.RMS = np.sqrt(XXavg * YYavg - XYavg * XYavg) * 1000.0  # [Pi*mm*mrad]
        self.logger.info('Normalized RMS Emittance of total beam    %f Pi*mm*mrad' % (self.RMS * beta))

        # calculate emittance fraction for density levels
        # number of levels
        nz = 100
        # level
        zl = np.linspace(0.0, Z.max(), nz)
        # total beam for level zl[i]
        zi = np.zeros(nz)
        # number of points inside level (~ total emittance)
        zn = np.zeros(nz)
        # RMS emittance for level
        zr = np.zeros(nz)

        for i in range(nz):
            mask = Z[:, :] >= zl[i]
            zn[i] = np.sum(mask)
            za = Z[mask]
            xa = X[mask]
            ya = Y[mask]
            zt = np.sum(za)
            zi[i] = zt
            xys = np.sum(xa * ya * za) / zt
            xxs = np.sum(xa * xa * za) / zt
            yys = np.sum(ya * ya * za) / zt
            zr[i] = np.sqrt(max([xxs * yys - xys * xys, 0.0])) * 1000.0

        # levels to draw
        fractions = np.array(self.read_parameter(0, 'fractions', [0.5, 0.7, 0.9]))
        levels = fractions * 0.0
        emit = fractions * 0.0
        rms = fractions * 0.0
        zt = np.sum(Z)
        for i in range(len(fractions)):
            index = np.where(zi >= fractions[i] * zt)[0]
            n = index.max()
            levels[i] = zl[n]
            emit[i] = zn[n]
            rms[i] = zr[n]

        emit = emit * (X[0, 0] - X[0, 1]) * (Y[0, 0] - Y[1, 0]) / np.pi * beta * 1000.0
        rms = rms * beta
        self.logger.info('% Current  Normalized emittance      Normalized RMS emittance')
        for i in range(len(levels)):
            self.logger.info('%2.0f %%       %5.3f Pi*mm*milliRadians  %5.3f Pi*mm*milliRadians' % (
                fractions[i] * 100.0, emit[i], rms[i]))
        self.logger.info('%2.0f %%                                %5.3f Pi*mm*milliRadians' % (100.0, self.RMS * beta))

        # save data to text file
        folder = self.folderName
        fn = os.path.join(str(folder), _progName + '_X.gz')
        np.savetxt(fn, X, delimiter='; ')
        fn = os.path.join(str(folder), _progName + '_Y.gz')
        np.savetxt(fn, Y, delimiter='; ')
        fn = os.path.join(str(folder), _progName + '_Z.gz')
        np.savetxt(fn, Z, delimiter='; ')

        # plot contours
        if int(self.comboBox.currentIndex()) == 5:
            self.clearPicture()
            axes.contour(X, Y*1000.0, Z, linewidths=1.0)
            axes.grid(True)
            #axes.set_title('Emittance contour plot')
            axes.set_title('Диаграмма эмиттанса')
            # axes.set_ylim([ymin,ymax])
            # axes.set_xlabel('X, мм')
            axes.set_xlabel('X, mm')
            # axes.set_ylabel('X\', milliradians')
            axes.set_ylabel('X\', миллирадиан')
            axes.annotate('Total current %4.1f mA' % (self.I * 1000.0) + '; Norm. RMS Emittance %5.3f Pi*mm*mrad' % (
                    self.RMS * beta),
                          xy=(.5, .2), xycoords='figure fraction',
                          horizontalalignment='center', verticalalignment='top',
                          fontsize=11)
            self.mplWidget.canvas.draw()
        # plot filled contours
        if int(self.comboBox.currentIndex()) == 6:
            self.clearPicture()
            axes.contourf(X, Y*1000.0, Z)
            axes.grid(True)
            axes.set_title('Emittance color plot')
            axes.set_xlabel('X, mm')
            axes.set_ylabel('X\', milliradians')
            axes.annotate('Total current %4.1f mA' % (self.I * 1000.0) + '; Norm. RMS Emittance %5.3f $\pi$*mm*mrad' % (
                    self.RMS * beta),
                          xy=(.5, .2), xycoords='figure fraction',
                          horizontalalignment='center', verticalalignment='top',
                          fontsize=11, color='white')
            self.mplWidget.canvas.draw()
            return
        # plot levels
        if int(self.comboBox.currentIndex()) == 7:
            self.clearPicture()
            CS = axes.contour(X, Y*1000.0, Z, linewidths=1.5, levels=levels[::-1])
            axes.grid(True)
            axes.set_title('Emittance contour plot')
            axes.set_xlabel('X, mm')
            axes.set_ylabel('X\', milliradians')
            axes.set_title('Диаграмма эмиттанса')
            axes.set_xlabel('X, мм')
            axes.set_ylabel('X\', миллирадиан')
            #labels = ['%2d %% of current' % (fr * 100) for fr in np.sort(fractions)[::-1]]
            labels = ['%2d %% тока' % (fr * 100) for fr in np.sort(fractions)[::-1]]
            for i in range(len(labels)):
                CS.collections[i].set_label(labels[i])
            axes.legend(loc='upper left')
            # axes.annotate('Total current %4.1f mA' % (self.I * 1000.0) + '; Norm. RMS Emittance %5.3f Pi*mm*mrad' % (
            #             self.RMS * beta),
            #               xy=(.5, .2), xycoords='figure fraction',
            #               horizontalalignment='center', verticalalignment='top',
            #               fontsize=11)
            self.mplWidget.canvas.draw()
            return

    def saveSettings(self, folder='', fileName=_settings_file_name):
        fullName = os.path.join(str(folder), fileName)
        try:
            # save window size and position
            p = self.pos()
            s = self.size()
            self.conf['main_window'] = {'size': (s.width(), s.height()), 'position': (p.x(), p.y())}
            #
            self.conf['folder'] = self.folderName
            self.conf['smooth'] = int(self.spinBox.value())
            self.conf['scan'] = int(self.spinBox_2.value())
            self.conf['result'] = int(self.comboBox.currentIndex())
            self.conf['history'] = [str(self.comboBox_2.itemText(count)) for count in
                                    range(min(self.comboBox_2.count(), 10))]
            self.conf['history_index'] = self.comboBox_2.currentIndex()
            self.conf['log_level'] = logging.DEBUG
            self.conf['parameters'] = self.paramsManual
            with open(fullName, 'w', encoding='utf-8') as configfile:
                configfile.write(json.dumps(self.conf, indent=4))
            self.logger.info('Configuration saved to %s' % fullName)
            return True
        except:
            self.print_exception_info()
            self.logger.info('Configuration save error to %s' % fullName)
            return False

    def saveData(self, folder='', fileName=_dataFile):
        fullName = os.path.join(str(folder), fileName)
        dbase = shelve.open(fullName, flag='n')
        # save paramsAuto
        dbase['paramsAuto'] = self.paramsAuto
        dbase.close()
        self.logger.info('Processed data saved to %s' % fullName)
        return True

    def restore_settings(self, folder='', file_name=_settings_file_name):
        self.execInitScript()
        self.conf = {}
        full_file_name = os.path.join(str(folder), file_name)
        try:
            with open(full_file_name, 'r', encoding='utf-8') as configfile:
                s = configfile.read()
                self.conf = json.loads(s)
            # restore window size and position
            if 'main_window' in self.conf:
                self.resize(QSize(self.conf['main_window']['size'][0], self.conf['main_window']['size'][1]))
                self.move(QPoint(self.conf['main_window']['position'][0], self.conf['main_window']['position'][1]))
            #
            if 'folder' in self.conf:
                self.folderName = self.conf['folder']
            if 'smooth' in self.conf:
                self.spinBox.setValue(int(self.conf['smooth']))
            if 'scan' in self.conf:
                self.spinBox_2.setValue(int(self.conf['scan']))
            # read items from history
            if 'history' in self.conf:
                self.comboBox_2.currentIndexChanged.disconnect(self.selectionChanged)
                self.comboBox_2.clear()
                self.comboBox_2.addItems(self.conf['history'])
                self.comboBox_2.currentIndexChanged.connect(self.selectionChanged)
            # set history selection
            if 'result' in self.conf:
                self.comboBox.setCurrentIndex(int(self.conf['result']))
            #
            self.logger.info('Configuration restored from %s' % full_file_name)
            return True
        except:
            self.logger.warning('Configuration restore error from %s' % full_file_name)
            self.print_exception_info()
            return False

    def restoreData(self, folder='', fileName=_dataFile):
        fullName = os.path.join(str(folder), fileName)
        dbase = None
        try:
            # read saved settings
            dbase = shelve.open(fullName)
            # restore automatically processed parameters
            self.paramsAuto = dbase['paramsAuto']
            dbase.close()
            # print OK message and exit    
            self.logger.info('Data restored from %s.' % fullName)
            return True
        except:
            try:
                dbase.close()
            except:
                pass
            # print error info    
            self.print_exception_info()
            self.logger.info('Data file %s restore error.' % fullName)
            return False

    def execInitScript(self, folder=None, fileName=_initScript):
        if folder is None:
            folder = self.folderName
        fullName = os.path.join(str(folder), fileName)
        try:
            exec(open(fullName).read(), globals(), locals())
            self.logger.info('Init script %s executed.' % fullName)
        except:
            self.logger.info('Init script %s error.', fullName)
            self.logger.debug('Exception info', exc_info=True)

    def print_exception_info(self):
        (tp, value) = sys.exc_info()[:2]
        self.logger.info('Exception %s %s' % (str(tp), str(value)))
        self.logger.debug('Exception', exc_info=True)


if __name__ == '__main__':
    # create the GUI application
    app = QApplication(sys.argv)
    # instantiate the main window
    dmw = DesignerMainWindow()
    app.aboutToQuit.connect(dmw.onQuit)
    dmw.cwd = os.getcwd()
    # show it
    dmw.show()
    # start the Qt main loop execution, exiting from this script
    # with the same return code of Qt application
    sys.exit(app.exec_())
