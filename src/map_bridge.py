from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal


class MapBridge(QObject):
    area_added   = pyqtSignal(float, float)
    area_clicked = pyqtSignal(str)
    area_moved   = pyqtSignal(str, float, float)
    area_deleted = pyqtSignal(str)
    interconnection_added   = pyqtSignal(str, str)
    interconnection_deleted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    @pyqtSlot(float, float)
    def onMapClick(self, lat, lng):
        self.area_added.emit(lat, lng)

    @pyqtSlot(str)
    def onBusClicked(self, name):
        self.area_clicked.emit(name)

    @pyqtSlot(str, float, float)
    def onBusMoved(self, name, lat, lng):
        self.area_moved.emit(name, lat, lng)

    @pyqtSlot(str)
    def onBusDeleted(self, name):
        self.area_deleted.emit(name)

    @pyqtSlot(str, str)
    def onLinkAdded(self, area0, area1):
        self.interconnection_added.emit(area0, area1)

    @pyqtSlot(str)
    def onLinkDeleted(self, name):
        self.interconnection_deleted.emit(name)
