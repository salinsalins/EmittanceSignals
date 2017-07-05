# coding: utf-8
'''
Created on Jul 2, 2017

@author: sanin
'''
# used to parse files more easily
from __future__ import with_statement

import os.path
import shelve
import sys

try:
    from PyQt4.QtGui import QMainWindow
    from PyQt4.QtGui import QApplication
    from PyQt4.QtGui import qApp
    from PyQt4.QtGui import QFileDialog
    from PyQt4.QtGui import QTableWidgetItem
    from PyQt4 import uic
except:
    from PyQt5.QtWidgets import QMainWindow
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtWidgets import qApp
    from PyQt5.QtWidgets import QFileDialog
    from PyQt5.QtWidgets import QTableWidgetItem
    from PyQt5 import uic

import numpy as np
from findRegions import *
from my_isfread import my_isfread as isfread
from smooth import smooth
from readTekFiles import readTekFiles
import scipy.integrate
from scipy.integrate import simps
from scipy.interpolate import interp1d
from printl import printl 
from gaussfit import gaussfit 

_progName = 'Emittance'
_progVersion = '_1_0'
_settingsFile = _progName + '_init.dat'
_initScript =  _progName + '_init.py'
_logFile =  _progName + '_log.log'

class DesignerMainWindow(QMainWindow):
    """Customization for Qt Designer created window"""
    def __init__(self, parent = None):
        # initialization of the superclass
        super(DesignerMainWindow, self).__init__(parent)
        # setup the GUI --> function generated by pyuic4
        uic.loadUi('Emittance.ui', self)
        #self.setupUi(self)
        # connect the signals with the slots
        self.pushButton.clicked.connect(self.plotRaw)
        self.pushButton_3.clicked.connect(self.plotProcessed)
        self.actionOpen.triggered.connect(self.selectFolder)
        self.pushButton_2.clicked.connect(self.selectFolder)
        self.actionQuit.triggered.connect(qApp.quit)
        self.pushButton_4.clicked.connect(self.processFolder)
        self.pushButton_5.clicked.connect(self.plotXsub)
        self.pushButton_6.clicked.connect(self.calculateEmittance)
        # variables definition
        self.data = None
        self.paramsAuto = None
        self.fleNames = []
        # restore settings from default location
        self.restoreSettings()
        # read data files
        self.parseFolder(folder = self.lineEdit.text())
        # restore local settings
        if not self.restoreSettings(folder = self.lineEdit.text()):
            self.processFolder()
    
    def selectFolder(self):
        """Opens a dataFolder select dialog"""
        # open the dialog and get the selected dataFolder
        folder = self.lineEdit.text()
        fileOpenDialog = QFileDialog(caption='Select directory with data files', directory=folder)
        # select folder, not file
        dataFolder = fileOpenDialog.getExistingDirectory()
        # if a dataFolder is selected
        if dataFolder:
            # update the lineEdit text with the selected filename
            self.lineEdit.setText(dataFolder)
            # parse selected folder
            self.parseFolder(dataFolder)
            # restore local settings
            if not self.restoreSettings(folder=dataFolder):
                self.processFolder()
 
    def parseFolder(self, folder, mask='*.isf'):
        self.listWidget.clear()
        # read data
        self.data, self.fileNames = readTekFiles(folder, mask)
        # number of files
        nx = len(self.fileNames)
        if nx <= 0 :
            return
        # short file names list
        names = [name.replace(folder, '')[1:] for name in self.fileNames]
        for i in range(nx):
            names[i] = '%3d - %s'%(i,names[i])
        # fill tableWidget
        #self.tableWidget.setRowCount(nx)
        #self.tableWidget.setColumnCount(2)
        #self.tableWidget.setHorizontalHeaderLabels(('File','Parameters'))
        #self.tableWidget.setVerticalHeaderLabels([str(i) for i in range(nx)])
        #for i in range(nx):
        #    self.tableWidget.setItem(i, 0, QTableWidgetItem(names[i]))
        #self.tableWidget.resizeColumnToContents(0)
        # fill listWidget
        self.listWidget.addItems(names)
        printl('', fileName = os.path.join(str(folder), _logFile))
    
    def clearPicture(self, force=False):
        if force | self.checkBox.isChecked():
            # clear the axes
            self.mplWidget.canvas.ax.clear()
        
    def plotRaw(self):
        self.clearPicture()
        if self.data is None :
            return
        # draw chart
        ns = self.spinBox.value()
        axes = self.mplWidget.canvas.ax
        #table = self.tableWidget
        #indexes = table.selectedIndexes()
        indexes = self.listWidget.selectedIndexes()
        y = self.data[0, :]
        ix = self.spinBox_2.value()
        if ix >= 0:
            x = self.data[ix, :].copy()
            smooth(x, self.spinBox.value())
            xTitle = 'Scan Voltage, V'
        else:
            x = np.arange(len(y))
            xTitle = 'Point index'
        for i in indexes :
            row = i.row()
            y = self.data[row, :].copy()
            smooth(y, ns)
            z = self.readZero(row) + self.readParameter(row, 'offset')
            axes.plot(x, y, label='raw'+str(row))
            axes.plot(x, z, label='zero'+str(row))
        axes.plot(axes.get_xlim(), [0.0,0.0], color='k')
        axes.grid(True)
        axes.set_title('Signals from Tektronix oscilloscope')
        axes.set_xlabel(xTitle)
        axes.set_ylabel('Signal Voltage, V')
        axes.legend(loc='best') 
        self.mplWidget.canvas.draw()

    def removeInersections(self, y1, y2, index):
        # calculate relative first derivatives
        d1 = np.diff(y1)
        d1 = np.append(d1, d1[-1])
        d2 = np.diff(y2)
        d2 = np.append(d2, d2[-1])
        regout = []
        reg = findRegions(index)
        #print('Initial regions  %s'%str(reg))
        for r in reg:
            if y1[r[0]] > y2[r[0]] and y1[r[1]-1] < y2[r[1]-1]:
                if np.all(d1[r[0]:r[1]]*d2[r[0]:r[1]] < 0.0):
                    continue
            if y1[r[0]] < y2[r[0]] and y1[r[1]-1] > y2[r[1]-1]:
                if np.all(d1[r[0]:r[1]]*d2[r[0]:r[1]] < 0.0):
                    continue
            regout.append(r)
        #print('Filtered regions %s'%str(regout))
        return regout

    def processFolder(self):
        def plot(*args, **kwargs):
            axes = self.mplWidget.canvas.ax
            axes.plot(*args, **kwargs)
            zoplot()
            axes.grid(True)
            axes.legend(loc='best') 
            self.mplWidget.canvas.draw()

        def draw():
            self.mplWidget.canvas.draw()

        def zoplot(v=0.0, color='k'):
            axes = self.mplWidget.canvas.ax
            xlim = axes.get_xlim()
            axes.plot(xlim, [v, v], color=color)
            axes.set_xlim(xlim)

        def voplot(v=0.0, color='k'):
            axes = self.mplWidget.canvas.ax
            ylim = axes.get_ylim()
            axes.plot([v, v], ylim, color=color)
            axes.set_ylim(ylim)

        def cls():
            self.clearPicture()
            
        axes = self.mplWidget.canvas.ax
        folder = self.lineEdit.text()
        printl('Processing folder %s'%folder)
        print('Reading data ...')
        data,files  = readTekFiles(folder)
        nx = len(files)
        if nx <= 0 :
            print('Nothing to process')
            return False
        print('%d files fond'%nx)
        # default smooth by
        ns = 1
        try:
            ns = int(self.spinBox.value())
        except:
            pass
        # determine Y size of data for one scan - ny
        y = isfread(files[0])[1]
        ny = len(y)
        # default parameters array
        params = [{'smooth':ns, 'offset':0.0, 'zero':np.zeros(ny), 'scale': 1.95} for i in range(nx)]
        # read data array
        # define arrays
        zero  = np.zeros((nx, ny), dtype=np.float64)
        count = np.zeros((nx, ny), dtype=np.float64)
        ix = np.arange(ny)
        # sooth data array
        print('Smoothing data ...')
        for i in range(nx) :
            y = data[i,:]
            smooth(y, params[i]['smooth'])
        # channel 0 is scan voltage by default
        x = data[0,:].copy()
        smooth(x, params[0]['smooth']*2)
        # find longest monotonic region of scan voltage
        xdiff = np.diff(x)
        xdiff = np.append(xdiff, xdiff[-1])
        mask1 = xdiff >= 0.0
        regions1 = findRegions(np.where(mask1)[0])         
        xr = [0,0]
        for r in regions1:
            if r[1]-r[0] >= xr[1]-xr[0]:
                xr = r
        mask2 = xdiff <= 0.0
        regions2 = findRegions(np.where(mask2)[0])         
        for r in regions2:
            if r[1]-r[0] >= xr[1]-xr[0]:
                xr = r
        xi = np.arange(xr[0], xr[1])
        params[0]['range'] = xr
        print('Using %s region of scan voltage'%str(xr))
        if int(self.comboBox.currentIndex()) == 8:
            # draw
            cls()
            plot(ix, x, label='Scan voltage')
            plot(ix[xi], x[xi], '.')
                    
        # auto process data for zero line and offset
        print('Processing zero line ...')
        for i in range(1,nx-1) :
            print('Channel %d'%(i))
            y1 = data[i,:].copy()
            offset1 = params[i]['offset']
            y1 = y1 - offset1
            y2 = data[i+1,:].copy()
            offset2 = params[i+1]['offset']
            y2 = y2 - offset2
            # double smooth because zero line is slow 
            smooth(y1, params[i]['smooth']*2)
            smooth(y2, params[i+1]['smooth']*2)
            # offsets calculated from upper 10%
            y1min = np.min(y1)
            y1max = np.max(y1)
            dy1 = y1max - y1min
            y2min = np.min(y2)
            y2max = np.max(y2)
            dy2 = y2max - y2min
            dy = max([dy1, dy2])
            i1 = np.where(y1 > (y1max - 0.1*dy))[0]
            o1 = np.average(y1[i1])
            #print('Offset 1 %f'%o1)
            i2 = np.where(y2 > (y2max - 0.1*dy))[0]
            o2 = np.average(y2[i2])
            #print('Offset 2 %f'%o2)
            # draw
            #cls()
            #plot(y1,'r', label='r'+str(i))
            #zoplot(o1,'r')
            #plot(y2,'b', label='r'+str(i+1))
            #zoplot(o2,'b')
            #plot(i1, y1[i1], '.')
            #plot(i2, y2[i2], '.')
            # correct y2 and offset2 for calculated offsets
            y2 = y2 - o2 + o1
            offset2 = offset2 + o2 - o1 
            # zero line = where 2 signals are equal
            mask = np.abs(y1 - y2) < 0.05*dy1
            index = np.where(mask)[0]
            #print(findRegionsText(index))
            index = restoreFromRegions(findRegions(index, 50, 300, 100, 100, length=ny))
            if len(index) <= 0:
                index = np.where(mask)[0]
            #print(findRegionsText(index))
            # filter signal intersections
            #r1 = self.removeInersections(y1, y2, index)
            #i1 = restoreFromRegions(r1)
            # new offset
            offset = np.average(y2[index] - y1[index])
            #print('Offset for channel %d = %f'%((i+1), offset))
            # shift y2 and offset2
            y2 = y2 - offset
            offset2 = offset2 + offset 
            # index with new offset
            #print('4% index with corrected offset')
            mask = np.abs(y1 - y2) < 0.04*dy1
            index = np.where(mask)[0]
            #print(findRegionsText(index))
            # filter signal intersection
            regions = findRegions(index, 50)
            index = restoreFromRegions(regions, 0, 150, length=ny)
            #print(findRegionsText(index))
            # choose largest values
            mask[:] = False
            mask[index] = True
            mask3 = np.logical_and(mask, y1 >= y2)
            index3 = np.where(mask3)[0]
            # update zero for all channels
            for j in range(1,nx) :
                w = 1.0/((abs(i - j))**2 + 1.0)
                zero[j,index3] = (zero[j,index3]*count[j,index3] + y1[index3]*w)/(count[j,index3] + w)
                count[j,index3] += w
            mask4 = np.logical_and(mask, y1 <= y2)
            index4 = np.where(mask4)[0]
            # update zero for all channels
            for j in range(1,nx) :
                w = 1.0/((abs(i + 1 - j))**2 + 1.0)
                zero[j,index4] = (zero[j,index4]*count[j,index4] + y2[index4]*w)/(count[j,index4] + w)
                count[j,index4] += w
            # save processed parameters
            params[i+1]['offset'] = offset2
            # plot intermediate results
            indexes = self.listWidget.selectedIndexes()
            if len(indexes) > 0:
                k = indexes[0].row()             
                self.clearPicture()
                axes.plot(ix, data[k,:], label='s'+str(k))
                y = zero[k].copy() + params[k]['offset']
                smooth(y,params[k]['smooth']*2)
                axes.plot(ix[:len(y)], y, label='z'+str(k))
                axes.plot(axes.get_xlim(), [0.0,0.0], color='k')
                axes.grid(True)
                axes.legend(loc='best') 
                self.mplWidget.canvas.draw()
                pass
        # save processed zero line
        for i in range(nx) :
            params[i]['zero'] = zero[i]
        # determine signal area
        print('Processing signals ...')
        xu = x[xi].copy()
        for i in range(1, nx) :
            #print('Channel %d'%i)
            y0 = data[i,:].copy()[xi]
            smooth(y0, params[i]['smooth'])
            z = zero[i].copy()[xi] + params[i]['offset']
            smooth(z, params[i]['smooth']*2)
            y = y0 - z
            ymin = np.min(y)
            ymax = np.max(y)
            dy = ymax - ymin
            mask = y < (ymax - 0.5*dy)
            index = np.where(mask)[0]
            ra = findRegions(index)
            params[i]['scale'] = 10.0 / (xu.max() - xu.min()) # [mm/Volt]
            params[i]['range'] = xr
            i1 = 0
            try:
                i1 = np.argmin(y[ra[0][0]:ra[0][1]]) + ra[0][0]
            except:
                pass
            i2 = -1
            try:
                i2 = np.argmin(y[ra[1][0]:ra[1][1]]) + ra[1][0]
            except:
                pass
            params[i]['scale'] = 10.0/(xu[i2] - xu[i1])   # [mm/Volt]
            #print('scale %f'%params[i]['scale'])
            if np.abs(xu[i1]) < np.abs(xu[i2]) :
                index = i1
            else:
                index = i2
            di = int(abs(i2 - i1)/2.0)
            i1 = max([xi[0], index - di + xi[0]])
            i2 = min([xi[-1], index + di + xi[0]])
            params[i]['range'] = [i1, i2]
            #print('range %s'%str(params[i]['range']))
            # draw
            #cls()
            #plot(ix[xi], y, label='p'+str(i))
            #plot(ix[i1:i2], y[i1 - xi[0]:i2 - xi[0]], '.', label='r'+str(i))
            #voplot(i1 + xi[0], 'r')
            #voplot(index2 + xi[0], 'b')
            #pass
        # filter scales
        sc = np.array([params[i]['scale'] for i in range(1,nx)])
        asc = np.average(sc)
        ssc = np.std(sc)
        index = np.where(abs(sc - asc) < 2.0*ssc)[0]
        asc1 = np.average(sc[index])
        index = np.where(abs(sc - asc) >= 2.0*ssc)[0]
        sc[index] = asc1
        for i in range(1,nx) :
            params[i]['scale'] = sc[i-1] 
        # common parameters
        print('Set default parameters')
# Parameters of Measurements
#R  = 2.0e5        ; Ohm    Resistor for beamlet scanner FC
#d1 = 0.4          ; mm    Analyzer hole diameter
#d2 = 0.5          ; mm    Collector Slit Width
#l1 = 213.0        ; mm    Distance From emission hole to analyzer hole
#l2 = 200.0        ; mm    Distance From analyzer hole to slit collector
        params[0]['R'] = 2.0e5
        params[0]['d1'] = 0.4
        params[0]['d2'] = 0.5
        l1 = 213.0
        params[0]['l1'] = l1
        l2 = 200.0
        params[0]['l2'] = l2
        # x0 - position of scanner
        for i in range(1, nx) :
            params[i]['x0'] = (-(nx-1)/2.0 + i)*2.0
        # ndh
        for i in range(1, nx) :
            y0 = data[i,:].copy()
            smooth(y0, params[i]['smooth'])
            z = zero[i].copy() + params[i]['offset']
            smooth(z, params[i]['smooth']*2)
            y = y0 - z
            r = params[i]['range']
            index = np.argmin(y[r[0]:r[1]]) + r[0]
            v = l2/l1*params[i]['x0'] + params[i]['scale']*x[index]
            params[i]['ndh'] = v
            #print('ndh %f'%v)
        # save processed to member variable
        self.paramsAuto = params
        return True
                
    def calculateEmittance(self):
        def plot(*args, **kwargs):
            axes = self.mplWidget.canvas.ax
            axes.plot(*args, **kwargs)
            #zoplot()
            #xlim = axes.get_xlim()
            #axes.plot(xlim, [0.0,0.0], color='k')
            #axes.set_xlim(xlim)
            axes.grid(True)
            axes.legend(loc='best') 
            self.mplWidget.canvas.draw()

        def draw():
            self.mplWidget.canvas.draw()

        def zoplot(v=0.0, color='k'):
            axes = self.mplWidget.canvas.ax
            xlim = axes.get_xlim()
            axes.plot(xlim, [v, v], color=color)
            axes.set_xlim(xlim)

        def voplot(v=0.0, color='k'):
            axes = self.mplWidget.canvas.ax
            ylim = axes.get_ylim()
            axes.plot([v, v], ylim, color=color)
            axes.set_ylim(ylim)

        def cls():
            self.clearPicture()
            
        if self.data is None :
            return
        nx = len(self.fileNames) 
        if nx <= 0 :
            return
        self.execInitScript()
        # calculate common values
        # x0
        x0 = np.zeros(nx-1)                         # [mm] X coordinates of scans
        ndh = np.zeros(nx-1)                        # [mm] displacement of analyzer slit (number n) from axis
        for i in range(1, nx) :
            x0[i-1] = self.readParameter(i, 'x0', 0.0, float)
            ndh[i-1] = self.readParameter(i, 'ndh', 0.0, float)
            #print('%d ndh %f'%(i,ndh[i-1]))
#R  = 2.0e5        ; Ohm   Resistor for beamlet scaner FC
#d1 = 0.4          ; mm    Analyzer hole diameter
#d2 = 0.5          ; mm    Collector Slit Width
#l1 = 213.0        ; mm    Distance From emission hole to analyzer hole
#l2 = 200.0        ; mm    Distance From analyzer hole to slit collector
        # R
        #R = self.readParameter(0, 'R', 2.0e5, float)    # [Ohm] Faraday cup load rezistior
        # l1
        l1 = self.readParameter(0, 'l1', 213.0, float)  # [mm] distance from source to analyzer aperture
        # l2
        l2 = self.readParameter(0, 'l2', 200.0, float)  # [mm] analyzer base
        # d1 and hole area
        d1 = self.readParameter(0, 'd1', 0.4, float)    # [mm] analyzer hole diameter
        a1 = np.pi*d1*d1/4.0                            # [mm**2] analyzer hole area    
        # d2
        d2 = self.readParameter(0, 'd2', 0.5, float)    # [mm] analyzer slit width
        # calculate maximum and integral profiles
        profilemax = np.zeros(nx-1)
        profileint = np.zeros(nx-1)
        for i in range(1, nx) :
            try:
                x,y,index = self.processSignal(i)           # x - [milliRadians] y - [mkA]
                yy = y[index]
                xx = x[index]
                h = np.where(np.diff(xx) != 0.0)[0]
                xx = xx[h]
                yy = yy[h]
                profilemax[i-1] = -1.0 * np.min(yy)         # [mkA]
                k = 1.0
                if xx[0] < xx[-1]:
                    k = -1.0
                # simps() returns nan if x of 2 points coincide
                #profileint[i-1] = k * scipy.integrate.simps(yy,xx) * l2 / d2 /1000.0  # [mkA] 1000.0 from milliradians
                # integrate by rectangles method
                profileint[i-1] = k * np.sum(yy[:-1]*np.diff(xx)) * l2 / d2 /1000.0  # [mkA] 1000.0 from milliradians
                #print(profileint[i-1])
            except:
                pass
        # sort in x0 increasing order
        ix0 = np.argsort(x0)
        print(ix0)
        x0s = x0[ix0]
        profileint = profileint[ix0]
        profilemax = profilemax[ix0]
        # remove average x
        #xavg = simps(x0s * profilemax, x0s) / simps(profilemax, x0s)
        xavg = simps(x0s * profileint, x0s) / simps(profileint, x0s)
        printl('Average X %f mm'%xavg)
        x0s = x0s - xavg
        # calculate total current
        index = np.where(x0s >= 0.0)[0]
        Ir = simps(x0s[index]*profileint[index], x0s[index])*2.0*np.pi/a1/1000.0
        print('Total current right %f [mA]'%Ir)
        index = np.where(x0s <= 0.0)[0]
        Il = -1.0*simps(x0s[index]*profileint[index], x0s[index])*2.0*np.pi/a1/1000.0
        print('Total current left %f [mA]'%Il)
        I = (Il + Ir)/2.0
        printl('Total current %f [mA]'%I)
        # save profile data
        folder = self.lineEdit.text()
        fn = os.path.join(str(folder), 'InegralProfile.txt')
        np.savetxt(fn, np.array([x0,profileint]).T, delimiter='; ' )
        fn = os.path.join(str(folder), 'MaximumProfile.txt')
        np.savetxt(fn, np.array([x0,profilemax]).T, delimiter='; ' )
        # plot profiles
        axes = self.mplWidget.canvas.ax
        # plot integral profile
        if int(self.comboBox.currentIndex()) == 0:
            self.clearPicture()
            axes.plot(x0s, profileint, 'd-', label='Integral Profile')
            #axes.plot(x0s, gaussfit(x0s,profileint,x0s), '--', label='Gaussian fit')
            axes.grid(True)
            axes.set_title('Integral profile')
            axes.set_xlabel('X, mm')
            axes.set_ylabel('Beamlet current, mkA')
            axes.legend(loc='best') 
            self.mplWidget.canvas.draw()
            return
        # plot maximal profile
        if int(self.comboBox.currentIndex()) == 1:
            self.clearPicture()
            axes.plot(x0s, profilemax, 'o-', label='Maximum Profile')
            #axes.plot(x0s, gaussfit(x0s,profilemax,x0s), '--', label='Gaussian fit')
            axes.grid(True)
            axes.set_title('Maximum profile')
            axes.set_xlabel('X, mm')
            axes.set_ylabel('Maximal current, mkA')
            axes.legend(loc='best') 
            self.mplWidget.canvas.draw()
            return
        # calculate emittance contour plot
        # number of points for emittance matrix
        N = 300
        # calculate nx-1 x N arrays
        # X [mm]
        X = np.zeros((N,nx-1), dtype=np.float64)
        # X' [milliRadians]
        Y = np.zeros((N,nx-1), dtype=np.float64)
        # current density [?]
        Z = np.zeros((N,nx-1), dtype=np.float64)
        # selected subarrays of data points
        v = []
        xsmin = 1e99
        xsmax = -1e99
        for i in range(1, nx) :
            X[:,i-1] = self.readParameter(i, 'x0', 0.0, float) - xavg
            x,y,index = self.processSignal(i)           # x in [milliRadians]; y < 0.0 in [mkA]
            # center the plot over X
            x = x - xavg/l1 * 1000.0
            v.append((x[index], -y[index]))
            xx = x[index].min()
            if xsmin > xx:
                xsmin = xx
            xx = x[index].max()
            if xsmax < xx:
                xsmax = xx
        # X' range array
        xs = np.linspace(xsmin, xsmax, N)
        # fill data arrays
        for i in range(nx-1) :
            Y[:,i] = xs
            #Z[:,i] = np.interp(Y[:,i] + x0[i]/l1*1000.0, v[i][0], v[i][1])
            f = interp1d(v[i][0], v[i][1], kind='linear', bounds_error=False, fill_value=0.0)
            #Z[:,i] = f(Y[:,i] + X[:,i]/l1*1000.0)
            Z[:,i] = f(Y[:,i])
        # sort data according rising x0
        X2 = X.copy()
        Y2 = Y.copy()
        Z2 = Z.copy()
        for i in range(nx-1) :
            X2[:,ix0[i]] = X[:,i]
            Y2[:,ix0[i]] = Y[:,i]
            Z2[:,ix0[i]] = Z[:,i]
        # debug plot
        if int(self.comboBox.currentIndex()) == 6:
            self.clearPicture()
            axes.contour(X2, Y2, Z2)
            axes.grid(True)
            axes.set_title('Calculated data')
            self.mplWidget.canvas.draw()
            return
        # reduce regular divergence
        for i in range(nx-1) :
            f = interp1d(v[i][0], v[i][1], kind='linear', bounds_error=False, fill_value=0.0)
            Z2[:,ix0[i]] = f(Y[:,ix0[i]] + X[:,ix0[i]]/l1*1000.0)
        # debug plot
        if int(self.comboBox.currentIndex()) == 7:
            self.clearPicture()
            axes.contour(X2, Y2, Z2)
            axes.grid(True)
            axes.set_title('Regular divergence reduced')
            self.mplWidget.canvas.draw()
            return
        # calculate NxN array
        X1 = np.zeros((N, N), dtype=np.float64)
        Y1 = np.zeros((N, N), dtype=np.float64)
        Z1 = np.zeros((N, N), dtype=np.float64)
        for i in range(N) :
            X1[i,: ] = np.linspace(x0.min(), x0.max(), N)
        for i in range(N) :
            Y1[:,i] = xs
        for i in range(N) :
            #Z1[i,:] = np.interp(X1[i,:], X[i,:], Z[i,:])
            f = interp1d(X2[i,:], Z2[i,:], kind='linear', bounds_error=False, fill_value=0.0)
            Z1[i,:] = f(X1[i,:])
        # remove negative currents
        Z1[Z1 < 0.0] = 0.0
        # return regular divergence back
        for i in range(N) :
            #Z1[:,i] = np.interp(Y1[:,i] - X1[:,i]/l1*1000.0, Y1[:,i], Z1[:,i])
            f = interp1d(Y1[:,i], Z1[:,i], kind='linear', bounds_error=False, fill_value=0.0)
            Z1[:,i] = f(Y1[:,i] - X1[:,i]/l1*1000.0)
        # remove negative currents
        Z1[Z1 < 0.0] = 0.0
        # save data to text file
        fn = os.path.join(str(folder), _progName + '_PlotX.gz')
        np.savetxt(fn, X1, delimiter='; ' )
        fn = os.path.join(str(folder), _progName + '_PlotY.gz')
        np.savetxt(fn, Y1, delimiter='; ' )
        fn = os.path.join(str(folder), _progName + '_PlotZ.gz')
        np.savetxt(fn, Z1, delimiter='; ' )
        
        self.clearPicture()
        if int(self.comboBox.currentIndex()) == 2:
            #print('Contour plot')
            axes.contour(X1, Y1, Z1, linewidths=0.5)
        if int(self.comboBox.currentIndex()) == 3:
            axes.contourf(X1, Y1, Z1)
        axes.grid(True)
        axes.set_title('Emittance contour plot')
        axes.set_ylim([xsmin,xsmax])
        axes.set_xlabel('X, mm')
        axes.set_ylabel('X\', milliRadians')
        self.mplWidget.canvas.draw()
        # calculate emittance values
        q=1.6e-19        # [Q] electron charge
        m=1.6726e-27     # [kg]  proton mass
        c=2.9979e8       # [m/s] speed of light
        #U=32.7*1000.0   # [V] beam energy
        U = self.readParameter(0, 'energy', 32000.0, float)
        beta = np.sqrt(2.0*q*U/m)/c
        # RMS Emittance
        zt = np.sum(Z1)
        XZ = X1*Z1
        YZ = Y1*Z1
        Xavg = np.sum(XZ)/zt
        Yavg = np.sum(YZ)/zt
        XYavg = np.sum(X1*Y1*Z1)/zt
        XXavg = np.sum(X1*XZ)/zt
        YYavg = np.sum(Y1*YZ)/zt
        RMS = np.sqrt(XXavg*YYavg-XYavg*XYavg)
        printl('Normalized RMS Emittance %5.3f Pi*mm*mrad'%(RMS*beta))

        nz = 100
        zl = np.linspace(0.0, Z1.max(), nz)
        zi = np.zeros(nz)
        zn = np.zeros(nz)
        zr = np.zeros(nz)

        for i in range(nz):
            mask = Z1 >= zl[i]
            #print(len(index))
            zn[i] = np.sum(mask)
            zi[i] = np.sum(Z1[mask])
            za = Z1[mask]
            xa = X1[mask]
            ya = Y1[mask]
            zt = np.sum(za)
            xys = np.sum(xa*ya*za)/zt
            xxs = np.sum(xa*xa*za)/zt
            yys = np.sum(ya*ya*za)/zt
            #print(xxs*yys-xys*xys)
            zr[i] = np.sqrt(max(xxs*yys-xys*xys, 0.0))

        # levels to draw
        fractions = np.array([0.5,0.7,0.9])    # fraction of the beam current
        levels = fractions*0.0
        emit = fractions*0.0
        rms = fractions*0.0
        mzl = zi.max()
        for i in range(len(fractions)):
            index = np.where(zi > fractions[i]*mzl)[0]
            n = index.max()
            levels[i] = zl[n]
            emit[i] = zn[n]
            rms[i] = zr[n]
        
        emit = emit*(X1[0,0]-X1[0,1])*(Y1[0,0]-Y1[1,0])/np.pi*beta
        rms = rms*beta
        printl('Current  Normalized emittance      Normalized RMS emittance')
        for i in range(len(levels)):
            printl('%2.0f %%     %5.3f Pi*mm*milliradians  %5.3f Pi*mm*milliradians'%(fractions[i]*100.0,emit[i],rms[i]))
        # plot levels
        if int(self.comboBox.currentIndex()) == 4:
            self.clearPicture()
            axes.contour(X1, Y1, Z1, linewidths=0.7, levels=levels[::-1])
            axes.grid(True)
            axes.set_title('Emittance contour plot')
            axes.set_ylim([xsmin,xsmax])
            axes.set_xlabel('X, mm')
            axes.set_ylabel('X\', milliRadians')
            self.mplWidget.canvas.draw()
        
    def readParameter(self, row, name, default=None, dtype=None, debug=False):
        if name == 'zero':
            return self.readZero(row)
        v = default
        t = 'default'
        try:
            v = self.paramsAuto[row][name]
            t = 'auto'
        except:
            pass
        try:
            #s = eval(str(self.tableWidget.item(row,1).text()))
            #v = s[name]
            v = self.paramsManual[row][name]
            t = 'manual'
        except:
            pass
        if dtype is not None :
            v = dtype(v)
        if debug :
            print('row:%d name:%s %s value:%s'%(row, name, t, str(v)))
        return v

    def readZero(self, row):
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
                    z0 = self.data[zi[0], :].copy()
                    ns0 = self.readParameter(zi[0], "smooth", 1, int)
                    of0 = self.readParameter(zi[0], "offset", 0.0, float)
                    smooth(z0, 2*ns0)
                    z[zi[1]:zi[2]] = z0[zi[1]:zi[2]] + of0
                except:
                    pass
        except:
            pass
        return z

    def processSignal(self, row):
        if self.data is None :
            return
        #print('Processing %d'%row)
        # scan voltage
        u = self.data[0, :].copy()
        # smooth
        ns = self.readParameter(0, "smooth", 1, int)
        smooth(u, ns)
        # parameters
        # scanner base
        l2 = self.readParameter(0, "l2", 200.0, float)
        # load resistor
        R = self.readParameter(0, "R", 2.0e5, float)
        # signal
        y = self.data[row, :].copy()
        # smooth
        ns = self.readParameter(row, "smooth", 1, int)
        # offset
        of = self.readParameter(row, "offset", 0.0, float)
        # zero line
        z = self.readZero(row)
        # smooth
        smooth(y, ns)
        smooth(z, 2*ns)
        # subtract offset and zero
        y = y - z - of
        # convert signal to microAmperes
        y = y/R*1.0e6
        # signal region
        r0 = self.readParameter(0, "range", (0, len(y)))
        r = self.readParameter(row, "range", r0)
        index = np.arange(r[0],r[1])
        # scale
        sc = self.readParameter(row, "scale", 1.0, float)
        # ndh
        ndh = self.readParameter(row, "ndh", 0.0, float)
        # x' in milliRadians
        xsub = (ndh - sc*u) / l2 * 1000.0
        return (xsub, y, index)

    def plotProcessed(self):
        """Plots processed signals"""
        if self.data is None :
            return
        self.execInitScript()
        axes = self.mplWidget.canvas.ax
        # clear the Axes
        self.clearPicture()
        # draw chart
        #table = self.tableWidget
        #indexes = table.selectedIndexes()
        indexes = self.listWidget.selectedIndexes()
        y = self.data[0, :]
        ix = self.spinBox_2.value()
        if ix >= 0:
            x = self.data[ix, :].copy()
            ns = 1
            try:
                ns = self.readParameter(ix, "smooth", 1, int)
            except:
                pass
            try:
                ns = int(self.spinBox.value())
            except:
                pass
            smooth(x, ns)
            xTitle = 'Scan Voltage, V'
        else:
            x = np.arange(len(y))
            xTitle = 'Point index'
        for i in indexes :
            row = i.row()
            u,y,index = self.processSignal(row)
            # convert to volts
            y = y * self.readParameter(0, "R", 2.0e5, float) / 1.0e6
            # plot processed signal
            axes.plot(x, y, label='p'+str(row))
            # highlight signal region
            axes.plot(x[index], y[index], label='range'+str(row))
            print('Signal %d'%row)
            self.readParameter(row, "smooth", 1, int, True)
            self.readParameter(row, "offset", 0.0, float, True)
            self.readParameter(row, "scale", 0.0, float, True)
            self.readParameter(row, "zero", (), None, True)
            self.readParameter(row, "range", (), None, True)
            self.readParameter(row, "x0", 0.0, float, True)
            self.readParameter(row, "ndh", 0.0, float, True)
        # plot zero line
        axes.plot(axes.get_xlim(), [0.0,0.0], color='k')
        # decorate the plot
        axes.grid(True)
        axes.set_title('Processed Signals')
        axes.set_xlabel(xTitle)
        axes.set_ylabel('Voltage, V')
        axes.legend(loc='best') 
        # force an image redraw
        self.mplWidget.canvas.draw()

    def plotXsub(self):
        """Plots processed signals vs Xsub"""
        if self.data is None :
            return
        self.execInitScript()
        axes = self.mplWidget.canvas.ax
        self.clearPicture()
        # draw chart
        indexes = self.listWidget.selectedIndexes()
        xTitle = 'X\', milliRadians'
        for i in indexes :
            row = i.row()
            x,y,index = self.processSignal(row)
            xx = x[index]
            yy = -1.0*y[index]
            axes.plot(xx, yy, label='jet '+str(row))
            #axes.plot(xx, gaussfit(xx, yy), '--', label='gauss '+str(row))
            pass
        # plot zero line
        axes.plot(axes.get_xlim(), [0.0,0.0], color='k')
        # decorate the plot
        axes.grid(True)
        axes.set_title('Elementary jet profile')
        axes.set_xlabel(xTitle)
        axes.set_ylabel('Signal, mkA')
        axes.legend(loc='best') 
        self.mplWidget.canvas.draw()

    def onQuit(self) :
        # save settings to folder
        self.saveSettings(folder = self.lineEdit.text())
        # save global settings
        self.saveSettings()

    def saveSettings(self, folder='', fileName=_settingsFile) :
        fullName = os.path.join(str(folder), fileName)
        dbase = shelve.open(fullName, flag='n')
        # data folder
        dbase['folder'] = str(self.lineEdit.text())
        # default smooth
        dbase['smooth'] = int(self.spinBox.value())
        # scan voltage channel number
        dbase['scan'] = int(self.spinBox_2.value())
        # result combo
        dbase['result'] = int(self.comboBox.currentIndex())
        ## save table
        #table = self.tableWidget
        #n = table.rowCount()
        #dbase['tableRowCount'] = n
        #m = table.columnCount()
        #dbase['tableColumnCount'] = m
        #for i in range(n) :
        #    for j in range(m) :
        #        item = table.item(i, j)
        #        if item is None :
        #            s = ''
        #        else:
        #            s = str(item.text())
        #        dbase['table_%d_%d'%(i,j)] = s
        # save paramsAuto
        dbase['paramsAuto'] = self.paramsAuto
        dbase.close()
        print('Configuration saved to %s'%fullName)
        return True
   
    def restoreSettings(self, folder='', fileName=_settingsFile) :
        self.execInitScript(folder)
        try :
            fullName = os.path.join(str(folder), fileName)
            dbase = shelve.open(fullName)
            # data folder
            self.lineEdit.setText(dbase['folder'])
            # default smooth
            self.spinBox.setValue(dbase['smooth'])
            # result combo
            self.comboBox.setCurrentIndex(dbase['result'])
            # scan voltage channel number
            self.spinBox_2.setValue(dbase['scan'])
            ## restore table
            #table = self.tableWidget
            #n = dbase['tableRowCount']
            #table.setRowCount(n)
            #m = dbase['tableColumnCount']
            #table.setColumnCount(m)
            #for i in range(n) :
            #    for j in range(m) :
            #        s = dbase['table_%d_%d'%(i,j)]
            #        table.setItem(i, j, QTableWidgetItem(s))
            #        #if j == 3 :
            #        #    table.setItem(i, 1, QTableWidgetItem(s))
            #table.setHorizontalHeaderLabels(('File','Parameters'))
            #table.setVerticalHeaderLabels([str(i) for i in range(n)])
            #table.resizeColumnsToContents()
            ##table.resizeColumnToContents(0)
            # restore paramsAuto
            self.paramsAuto = dbase['paramsAuto']
            dbase.close()
            print('Configuration restored from %s'%fullName)
            return True
        except :
            (type, value, traceback) = sys.exc_info()
            print('Exception : %s'%value)
            print('Configuration file %s restore error.'%fullName)
            return False

    def execInitScript(self, folder=None, fileName=_initScript):
        if folder is None :
            folder = self.lineEdit.text()
        try:
            fullName = os.path.join(str(folder), fileName)
            exec(open(fullName).read(), globals(), locals())
            print('Init script %s executed'%fullName)
        except:
            (type, value, traceback) = sys.exc_info()
            print('Exception : %s'%value)
            print('Init script %s error'%fullName)

if __name__ == '__main__':
    # create the GUI application
    app = QApplication(sys.argv)
    # instantiate the main window
    dmw = DesignerMainWindow()
    app.aboutToQuit.connect(dmw.onQuit)
    # show it
    dmw.show()
    # start the Qt main loop execution, exiting from this script
    # with the same return code of Qt application
    sys.exit(app.exec_())