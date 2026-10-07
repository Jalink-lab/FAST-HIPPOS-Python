import ij.IJ
import ij.WindowManager
import ij.gui.PlotWindow

def myWindow = WindowManager.getActiveWindow() as PlotWindow
def myPlot  = myWindow.getPlot()

for (i in 0..<myPlot.getNumPlotObjects()) {
    IJ.log(myPlot.getPlotObjectStyle(i))
}
