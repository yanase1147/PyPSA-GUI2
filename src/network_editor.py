import json
import math
import html as _html_mod
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QFormLayout,
    QLineEdit, QDoubleSpinBox, QSpinBox, QCheckBox, QComboBox,
    QDialogButtonBox, QLabel, QMessageBox, QSplitter, QStackedWidget,
    QInputDialog, QMenu,
    QAbstractItemView, QFrame,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem,
    QGraphicsLineItem, QGraphicsPolygonItem, QGraphicsItem, QGraphicsEllipseItem,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QUrl, Qt, pyqtSignal, QPointF, QRectF, QTimer
from PyQt6.QtGui import QFont, QBrush, QPen, QColor, QPolygonF, QPainter

from .models import (
    NetworkData, Area, AreaRES, Generator, Interconnection, Load, Store, PumpedHydro,
    Converter, CustomComponentInstance, TimeSeriesData,
    CARRIERS, AREA_CARRIERS, CONVERTER_PRESETS, AVAILABLE_EXPOSED_PARAMS,
)
from .map_bridge import MapBridge
from .network_manager import NetworkManagerWindow
from .component_template_editor import ComponentTemplateEditorDialog, CustomInstanceDialog
from .unit_widgets import UnitValueBox


def _fmt(v) -> str:
    """Format a value for table display: floats drop unnecessary trailing zeros."""
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


# ── RES diagram constants ────────────────────────────────────────────────
_BUS_COLORS_RES = {
    "AC":       "#2980b9",
    "heat":     "#e74c3c",
    "hydrogen": "#00acc1",
    "gas":      "#f39c12",
}
_CARRIER_ORDER_RES = ["gas", "AC", "heat", "hydrogen"]


class _ZoomableView(QGraphicsView):
    """QGraphicsView with Ctrl+wheel zoom."""
    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)


class _ResBoxItem(QGraphicsRectItem):
    """Interactable labeled box in the RES diagram.

    Double-click opens the component editor.
    """
    def __init__(self, x: float, y: float, w: float, h: float, label: str,
                 kind: str, name: str, editor,
                 face: str = "#ecf0f1", edge: str = "#7f8c8d", lw: float = 1.5):
        super().__init__(x, y, w, h)
        self._kind   = kind
        self._name   = name
        self._editor = editor
        self._lw     = lw
        self.setBrush(QBrush(QColor(face)))
        self.setPen(QPen(QColor(edge), lw))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"ダブルクリックして編集: {name}")
        # ── centered text ────────────────────────────────────────────
        safe = (_html_mod.escape(label)
                .replace("\n", "<br>"))
        ti = QGraphicsTextItem(self)
        ti.setHtml(f"<div style='text-align:center; margin:0; padding:0;'>{safe}</div>")
        f = QFont(); f.setPointSize(10)
        ti.setFont(f)
        ti.setTextWidth(w - 6)
        ti.adjustSize()
        th = ti.boundingRect().height()
        ti.setPos(x + 3, y + max(0.0, (h - th) / 2.0))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._editor._res_component_context_menu(self._kind, self._name, event.screenPos())
            event.accept()
            return
        self._editor._show_component_table(self._kind, self._name)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._editor._edit_component_by_name(self._kind, self._name)
        event.accept()

    def hoverEnterEvent(self, event):
        p = QPen(self.pen()); p.setWidthF(p.widthF() + 1.5); self.setPen(p)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        p = QPen(self.pen()); p.setWidthF(max(0.5, p.widthF() - 1.5)); self.setPen(p)
        super().hoverLeaveEvent(event)


class _ResEllipseItem(QGraphicsEllipseItem):
    """Circular RES-diagram node (需要/Load terminal, per 4.2節の表記: ○=需要).

    Mirrors _ResBoxItem's interaction (click/double-click/right-click/hover)
    but renders as an ellipse instead of a rectangle.
    """
    def __init__(self, x: float, y: float, w: float, h: float, label: str,
                 kind: str, name: str, editor,
                 face: str = "#ecf0f1", edge: str = "#7f8c8d", lw: float = 1.5):
        super().__init__(x, y, w, h)
        self._kind   = kind
        self._name   = name
        self._editor = editor
        self.setBrush(QBrush(QColor(face)))
        self.setPen(QPen(QColor(edge), lw))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"ダブルクリックして編集: {name}")
        safe = (_html_mod.escape(label).replace("\n", "<br>"))
        ti = QGraphicsTextItem(self)
        ti.setHtml(f"<div style='text-align:center; margin:0; padding:0;'>{safe}</div>")
        f = QFont(); f.setPointSize(9)
        ti.setFont(f)
        ti.setTextWidth(w - 10)
        ti.adjustSize()
        th = ti.boundingRect().height()
        ti.setPos(x + 5, y + max(0.0, (h - th) / 2.0))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._editor._res_component_context_menu(self._kind, self._name, event.screenPos())
            event.accept()
            return
        self._editor._show_component_table(self._kind, self._name)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._editor._edit_component_by_name(self._kind, self._name)
        event.accept()

    def hoverEnterEvent(self, event):
        p = QPen(self.pen()); p.setWidthF(p.widthF() + 1.5); self.setPen(p)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        p = QPen(self.pen()); p.setWidthF(max(0.5, p.widthF() - 1.5)); self.setPen(p)
        super().hoverLeaveEvent(event)


def _res_arrowhead(scene: QGraphicsScene, tx: float, ty: float,
                   fx: float, fy: float, color: str, size: float = 9.0):
    """Draw a small filled triangle at (tx, ty) pointing away from (fx, fy)."""
    dx, dy = tx - fx, ty - fy
    ln = math.hypot(dx, dy)
    if ln < 1:
        return
    ux, uy = dx / ln, dy / ln
    px, py = -uy, ux
    tip = QPointF(tx, ty)
    b1  = QPointF(tx - size * ux + size * 0.4 * px, ty - size * uy + size * 0.4 * py)
    b2  = QPointF(tx - size * ux - size * 0.4 * px, ty - size * uy - size * 0.4 * py)
    head = QGraphicsPolygonItem(QPolygonF([tip, b1, b2]))
    head.setBrush(QBrush(QColor(color)))
    head.setPen(QPen(QColor(color), 0.5))
    scene.addItem(head)


def _res_draw_arrow(scene: QGraphicsScene, x1: float, y1: float,
                    x2: float, y2: float, color: str,
                    bidirectional: bool = False):
    """Draw a line with arrowhead(s) between two points."""
    line = QGraphicsLineItem(x1, y1, x2, y2)
    line.setPen(QPen(QColor(color), 1.5))
    scene.addItem(line)
    _res_arrowhead(scene, x2, y2, x1, y1, color)
    if bidirectional:
        _res_arrowhead(scene, x1, y1, x2, y2, color)


def _res_box_anchor_x(box_x: float, box_w: float, other_x: float) -> float:
    """Return the box edge x (left/right) facing the other endpoint."""
    cx = box_x + box_w * 0.5
    return box_x if other_x <= cx else box_x + box_w


def _res_label(scene: QGraphicsScene, text: str, x: float, y: float,
               color: str = "#555555", pt: int = 11, bold: bool = False) -> QGraphicsTextItem:
    """Add a simple text label to the scene."""
    ti = scene.addText(text)
    f  = QFont(); f.setPointSize(pt); f.setBold(bold)
    ti.setFont(f)
    ti.setDefaultTextColor(QColor(color))
    ti.setPos(x, y)
    return ti


class _AdaptiveSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that hides trailing zeros in the display."""
    def textFromValue(self, value: float) -> str:
        return f"{value:g}"

MAP_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Network Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<style>
  body { margin:0; padding:0; }
  #map  { height:100vh; width:100%; }
  #mode-badge {
    position:absolute; top:10px; left:50%; transform:translateX(-50%);
    z-index:1000; background:rgba(0,0,0,0.65); color:#fff;
    padding:4px 16px; border-radius:12px; font:13px/1.4 Arial,sans-serif;
    pointer-events:none;
  }
</style>
</head>
<body>
<div id="map"></div>
<div id="mode-badge">モード: 選択</div>
<script>
var map = L.map('map').setView([36.2048, 138.2529], 5);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
  maxZoom:18, attribution:'© OpenStreetMap contributors'
}).addTo(map);

var mode = 'select';
var markers = {};
var linkPolylines = {};
var linkFirstBus = null;
var bridge = null;

var LABELS = {select:'選択', add_bus:'エリア追加', add_link:'連系線追加', delete:'削除'};

new QWebChannel(qt.webChannelTransport, function(ch){ bridge = ch.objects.bridge; });

function setMode(m){
  if(linkFirstBus && markers[linkFirstBus]) markers[linkFirstBus].setOpacity(1);
  linkFirstBus = null;
  mode = m;
  document.getElementById('mode-badge').textContent = 'モード: '+(LABELS[m]||m);
}

map.on('click', function(e){
  if(mode === 'add_bus' && bridge) bridge.onMapClick(e.latlng.lat, e.latlng.lng);
});

function makeBusIcon(){
  return L.divIcon({
    className:'',
    html:'<div style="width:14px;height:14px;background:#e74c3c;border:2px solid #922b21;'+
         'border-radius:50%;box-shadow:0 1px 4px rgba(0,0,0,.5);"></div>',
    iconSize:[14,14], iconAnchor:[7,7]
  });
}

function addBusMarker(name, lat, lon){
  var m = L.marker([lat,lon],{draggable:true, icon:makeBusIcon()})
    .bindTooltip(name,{permanent:true, direction:'top', offset:[0,-10]})
    .addTo(map);

  m.on('dragend', function(e){
    var ll = e.target.getLatLng();
    if(bridge) bridge.onBusMoved(name, ll.lat, ll.lng);
  });

  m.on('click', function(e){
    L.DomEvent.stopPropagation(e);
    if(mode==='select' && bridge){ bridge.onBusClicked(name); }
    else if(mode==='add_link'){
      if(!linkFirstBus){ linkFirstBus=name; m.setOpacity(0.4); }
      else if(linkFirstBus!==name){
        if(bridge) bridge.onLinkAdded(linkFirstBus, name);
        if(markers[linkFirstBus]) markers[linkFirstBus].setOpacity(1);
        linkFirstBus=null;
      }
    } else if(mode==='delete' && bridge){ bridge.onBusDeleted(name); }
  });

  m.on('contextmenu', function(e){
    L.DomEvent.stopPropagation(e);
    if(bridge) bridge.onBusDeleted(name);
  });

  markers[name] = m;
}

function removeBusMarker(name){
  if(markers[name]){ map.removeLayer(markers[name]); delete markers[name]; }
}

function updateBusPosition(name, lat, lon){
  if(markers[name]) markers[name].setLatLng([lat,lon]);
}

function addLinkLayer(linkName, lat0, lon0, lat1, lon1){
  var pl = L.polyline([[lat0,lon0],[lat1,lon1]],
    {color:'#2980b9', weight:3, opacity:0.85}).addTo(map);
  pl.bindTooltip(linkName + ' (連系線)', {sticky:true});
  pl.on('click', function(e){
    L.DomEvent.stopPropagation(e);
    if(mode==='delete' && bridge) bridge.onLinkDeleted(linkName);
  });
  pl.on('contextmenu', function(e){
    L.DomEvent.stopPropagation(e);
    if(bridge) bridge.onLinkDeleted(linkName);
  });
  linkPolylines[linkName] = pl;
}

function removeLinkLayer(name){
  if(linkPolylines[name]){ map.removeLayer(linkPolylines[name]); delete linkPolylines[name]; }
}

function updateLinkLayer(name, lat0, lon0, lat1, lon1){
  if(linkPolylines[name]) linkPolylines[name].setLatLngs([[lat0,lon0],[lat1,lon1]]);
}

function clearMap(){
  Object.keys(markers).forEach(function(n){ map.removeLayer(markers[n]); });
  Object.keys(linkPolylines).forEach(function(n){ map.removeLayer(linkPolylines[n]); });
  markers={}; linkPolylines={};
}
</script>
</body>
</html>"""

_YES = QMessageBox.StandardButton.Yes
_NO  = QMessageBox.StandardButton.No


class NetworkEditor(QWidget):
    network_changed = pyqtSignal(object)

    # テンプレートごとのカスタムタブテーブル { テンプレート名: QTableWidget }
    _STATIC_TAB_COUNT = 5   # 発電機・需要・貯蔵・揚水発電所・変換器

    def __init__(self, parent=None):
        super().__init__(parent)
        self.network: NetworkData     = NetworkData()
        self._current_res: Optional[AreaRES] = None
        self._area_counter = 0
        self._map_ready    = False
        self._pending_js   = []
        self._currency     = "CURRENCY"
        self._res_tabs: Optional[QTabWidget] = None
        self._custom_tab_tables: dict = {}
        self._res_scene: Optional[QGraphicsScene] = None
        self._res_view:  Optional[_ZoomableView]  = None
        self._table_window: Optional[QWidget] = None
        self._network_manager: Optional[NetworkManagerWindow] = None
        self._timeseries_editor = None   # set by MainWindow via set_timeseries_editor()
        self._setup_ui()
        self.network_changed.connect(lambda _n: self._sync_network_manager())

    def set_timeseries_editor(self, ts_editor) -> None:
        """MainWindow から TimeSeriesEditor への参照を設定する。"""
        self._timeseries_editor = ts_editor

    def _area_carriers(self) -> list[str]:
        return self.network.area_carriers() if self.network else list(AREA_CARRIERS)

    def _multi_carriers(self) -> list[str]:
        return self.network.multi_carriers() if self.network else [
            c for c in AREA_CARRIERS if c not in ("DC", "other", "")
        ]

    def _generator_carriers(self) -> list[str]:
        vals = list(CARRIERS)
        for c in self._area_carriers():
            if c not in vals:
                vals.append(c)
        return vals

    def _carrier_in_use(self, carrier: str) -> bool:
        for res in self.network.area_res_list:
            if any(g.bus_carrier == carrier for g in res.generators):
                return True
            if any(ld.bus_carrier == carrier for ld in res.loads):
                return True
            if any(st.carrier == carrier for st in res.stores):
                return True
            if any(carrier in (cv.carrier_in, cv.carrier_out, cv.carrier_out2)
                   for cv in res.converters):
                return True
        if any(ic.carrier == carrier for ic in self.network.interconnections):
            return True
        return False

    def _manage_carriers(self):
        actions = [self.tr("追加"), self.tr("削除")]
        action, ok = QInputDialog.getItem(
            self._res_window if hasattr(self, "_res_window") else self,
            self.tr("キャリア管理"),
            self.tr("操作を選択:"),
            actions,
            editable=False,
        )
        if not ok:
            return

        if action == self.tr("追加"):
            text, ok = QInputDialog.getText(
                self._res_window if hasattr(self, "_res_window") else self,
                self.tr("キャリア追加"),
                self.tr("新しいキャリア名:"),
            )
            if not ok:
                return
            name = text.strip()
            if not name:
                return
            if not self.network.add_user_carrier(name):
                QMessageBox.information(
                    self, self.tr("情報"), self.tr("キャリア '{}' は既に存在します。").format(name)
                )
                return
            self._refresh_res_tables()
            self._refresh_overview_tables()
            self.network_changed.emit(self.network)
            return

        removable = [c for c in self.network.user_carriers]
        if not removable:
            QMessageBox.information(self, self.tr("情報"), self.tr("削除可能なユーザー定義キャリアがありません。"))
            return
        name, ok = QInputDialog.getItem(
            self._res_window if hasattr(self, "_res_window") else self,
            self.tr("キャリア削除"),
            self.tr("削除するキャリア:"),
            removable,
            editable=False,
        )
        if not ok:
            return
        if self._carrier_in_use(name):
            QMessageBox.warning(self, self.tr("警告"), self.tr("'{}' は使用中のため削除できません。").format(name))
            return
        self.network.remove_user_carrier(name)
        self._refresh_res_tables()
        self._refresh_overview_tables()
        self.network_changed.emit(self.network)

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        self.btn_select   = QPushButton(self.tr("選択"))
        self.btn_add_area = QPushButton(self.tr("エリア追加"))
        self.btn_add_ic   = QPushButton(self.tr("連系線追加"))
        self.btn_delete   = QPushButton(self.tr("削除"))
        for btn in (self.btn_select, self.btn_add_area, self.btn_add_ic, self.btn_delete):
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            toolbar.addWidget(btn)
        self.btn_select.setChecked(True)
        toolbar.addStretch()
        self.btn_tmpl_editor = QPushButton(self.tr("コンポーネント定義"))
        self.btn_network_manager = QPushButton(self.tr("ネットワークマネージャー"))
        self.btn_network_manager.setFixedHeight(28)
        self.btn_network_manager.clicked.connect(self._open_network_manager)
        toolbar.addWidget(self.btn_network_manager)
        self.btn_tmpl_editor.setFixedHeight(28)
        self.btn_tmpl_editor.clicked.connect(self._open_template_editor)
        toolbar.addWidget(self.btn_tmpl_editor)
        layout.addLayout(toolbar)

        self.btn_select.clicked.connect(lambda: self._set_mode("select"))
        self.btn_add_area.clicked.connect(lambda: self._set_mode("add_bus"))
        self.btn_add_ic.clicked.connect(lambda: self._set_mode("add_link"))
        self.btn_delete.clicked.connect(lambda: self._set_mode("delete"))

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Map ───────────────────────────────────────────────────────
        self.web_view = QWebEngineView()
        self.channel  = QWebChannel()
        self.bridge   = MapBridge()
        self.channel.registerObject("bridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        self.web_view.page().loadFinished.connect(self._on_map_loaded)
        self.web_view.setHtml(MAP_HTML, QUrl("https://unpkg.com/"))
        splitter.addWidget(self.web_view)

        self.bridge.area_added.connect(self._on_area_added)
        self.bridge.area_clicked.connect(self._on_area_clicked)
        self.bridge.area_moved.connect(self._on_area_moved)
        self.bridge.area_deleted.connect(self._on_area_deleted)
        self.bridge.interconnection_added.connect(self._on_ic_added_from_map)
        self.bridge.interconnection_deleted.connect(self._on_ic_deleted_from_map)

        # ── Right panel: overview only ────────────────────────────────
        splitter.addWidget(self._build_overview_panel())
        splitter.setSizes([500, 500])
        layout.addWidget(splitter)

        # ── Floating RES editor (non-modal) ───────────────────────────
        self._res_window = QWidget(None, Qt.WindowType.Window)
        self._res_window.setWindowTitle(self.tr("RES編集"))
        self._res_window.resize(1050, 740)
        self._build_res_window_ui()

    # ── Overview panel (エリア一覧 + 連系線) ─────────────────────────
    def _build_overview_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 0)

        tabs = QTabWidget()

        # エリアタブ
        self.area_table = self._make_table([self.tr("名前"), self.tr("緯度"), self.tr("経度"), self.tr("国")])
        self.area_table.cellDoubleClicked.connect(
            lambda r, c: self._open_res_window_from_table())
        area_tab = self._wrap_table(
            self.area_table,
            edit_cb=self._edit_area_dialog,
            del_cb=self._delete_area_from_table,
            note=self.tr("ダブルクリックまたはマップクリックRES編集ウィンドウを開く"),
        )
        tabs.addTab(area_tab, self.tr("エリア"))

        # 連系線タブ
        cur = self._currency
        self.ic_table = self._make_table([
            self.tr("名前"), self.tr("エリア0"), self.tr("エリア1"), self.tr("種別"), self.tr("効率"),
            self.tr("容量(MW)"), self.tr("逆方向容量(MW)"), self.tr("拡張可能"), self.tr(f"建設費({cur}/MW)"), self.tr(f"変動費({cur}/MWh)"),
        ])
        self.ic_table.cellDoubleClicked.connect(lambda r, c: self._edit_ic_dialog())
        ic_tab = self._wrap_table(
            self.ic_table,
            add_cb=self._add_ic_dialog,
            edit_cb=self._edit_ic_dialog,
            del_cb=lambda: self._delete_ic_selected(),
            note=self.tr("マップの「連系線追加」モードで2エリアをクリックしても追加可"),
        )
        tabs.addTab(ic_tab, self.tr("連系線"))

        lay.addWidget(tabs)
        return w

    # ── Floating RES window UI ───────────────────────────────────────
    def _build_res_window_ui(self):
        """Build the RES editor UI inside self._res_window."""
        lay = QVBoxLayout(self._res_window)
        lay.setContentsMargins(6, 6, 6, 6)

        header = QHBoxLayout()
        self._area_label = QLabel(self.tr("エリア: —"))
        font = QFont(); font.setBold(True); font.setPointSize(11)
        self._area_label.setFont(font)
        header.addWidget(self._area_label)
        header.addStretch()
        self.btn_edit_area = QPushButton(self.tr("エリア編集"))
        self.btn_edit_area.setFixedHeight(26)
        self.btn_edit_area.clicked.connect(self._edit_area_dialog_from_res)
        self.btn_table = QPushButton(self.tr("テーブル表示"))
        self.btn_table.setFixedHeight(26)
        self.btn_table.setCheckable(True)
        self.btn_table.setToolTip(self.tr("コンポーネントテーブルを別ウィンドウで表示します"))
        self.btn_table.clicked.connect(self._toggle_table_window)
        btn_tmpl = QPushButton(self.tr("コンポーネント定義"))
        btn_tmpl.setFixedHeight(26)
        btn_tmpl.clicked.connect(lambda: self._open_template_editor(self._res_window))
        btn_carrier = QPushButton(self.tr("キャリア管理"))
        btn_carrier.setFixedHeight(26)
        btn_carrier.clicked.connect(self._manage_carriers)
        self.btn_add_custom = QPushButton(self.tr("＋ コンポーネント追加"))
        self.btn_add_custom.setFixedHeight(26)
        self.btn_add_custom.setToolTip(self.tr("テンプレートから新しいコンポーネントを追加します"))
        self.btn_add_custom.clicked.connect(lambda: self._add_custom_dialog())
        header.addWidget(self.btn_edit_area)
        header.addWidget(self.btn_table)
        header.addWidget(self.btn_add_custom)
        header.addWidget(btn_tmpl)
        header.addWidget(btn_carrier)
        lay.addLayout(header)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        # ── 未接続コンポーネント警告バナー（4.2節） ──────────────────────
        self._res_warning_label = QLabel("")
        self._res_warning_label.setWordWrap(True)
        self._res_warning_label.setStyleSheet(
            "background:#fdecea; color:#c0392b; padding:5px 8px; border-radius:3px;")
        self._res_warning_label.hide()
        lay.addWidget(self._res_warning_label)

        # ── コンポーネントパレット + QGraphicsView (RES diagram) ─────────
        body = QHBoxLayout()
        body.addWidget(self._build_res_palette())

        self._res_scene = QGraphicsScene()
        self._res_view  = _ZoomableView(self._res_scene)
        self._res_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._res_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._res_view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        body.addWidget(self._res_view, stretch=1)
        lay.addLayout(body, stretch=1)

        # ── Floating table window ─────────────────────────────────────
        self._build_table_window_ui()

    def _build_res_palette(self) -> QWidget:
        """左サイドパネル: 5カテゴリのコンポーネント追加パレット（4.2節）。"""
        w = QWidget()
        w.setFixedWidth(134)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 4, 0)
        v.setSpacing(6)

        title = QLabel(self.tr("コンポーネント追加"))
        f = QFont(); f.setBold(True); f.setPointSize(9)
        title.setFont(f)
        title.setStyleSheet("color:#555;")
        v.addWidget(title)

        def _cat_btn(label: str, cb, tip: str, color: str):
            b = QPushButton(label)
            b.setFixedHeight(32)
            b.setToolTip(tip)
            b.setStyleSheet(
                f"text-align:left; padding-left:8px; border-left:4px solid {color};")
            b.clicked.connect(cb)
            v.addWidget(b)
            return b

        _cat_btn(self.tr("＋ 1次資源"), self._add_generator_dialog,
                 self.tr("一次資源→キャリア変換（発電機）を追加"), "#27ae60")
        _cat_btn(self.tr("＋ 変換プロセス"), self._add_converter_dialog,
                 self.tr("キャリア間の変換器を追加"), "#e67e22")
        _cat_btn(self.tr("＋ 需要"), self._add_load_dialog,
                 self.tr("需要（Load）を追加"), "#7f8c8d")
        _cat_btn(self.tr("＋ エネルギー貯蔵"), self._add_storage_menu,
                 self.tr("蓄電池等（Store）または揚水発電所を追加"), "#1abc9c")
        _cat_btn(self.tr("キャリア管理"), self._manage_carriers,
                 self.tr("エリアで使用するエネルギーキャリア（縦線）を追加/削除"), "#2980b9")
        v.addStretch()

        hint = QLabel(self.tr("右クリック: 編集/削除\nダブルクリック: 編集"))
        hint.setStyleSheet("color:#999; font-size:10px;")
        v.addWidget(hint)
        return w

    def _add_storage_menu(self):
        menu = QMenu(self._res_window)
        act_store = menu.addAction(self.tr("蓄電池等 (Store)"))
        act_ph = menu.addAction(self.tr("揚水発電所"))
        sender = self.sender()
        pos = (sender.mapToGlobal(sender.rect().bottomLeft())
               if isinstance(sender, QWidget) else self._res_window.mapToGlobal(
                   self._res_window.rect().center()))
        act = menu.exec(pos)
        if act == act_store:
            self._add_store_dialog()
        elif act == act_ph:
            self._add_pumped_hydro_dialog()

    # ------------------------------------------------------------------
    # Table window (separate window for component tables)
    # ------------------------------------------------------------------
    def _build_table_window_ui(self):
        self._table_window = QWidget(None, Qt.WindowType.Window)
        self._table_window.setWindowTitle(self.tr("コンポーネントテーブル"))
        self._table_window.resize(960, 420)

        def _close_event(event):
            self.btn_table.setChecked(False)
            event.accept()
        self._table_window.closeEvent = _close_event

        lay = QVBoxLayout(self._table_window)
        lay.setContentsMargins(6, 6, 6, 6)

        # フィルタ状態を示すラベル + クリアボタン
        filter_bar = QHBoxLayout()
        self._filter_label = QLabel(self.tr("すべて表示"))
        self._filter_label.setStyleSheet("color: #555; font-size: 11px;")
        btn_clear_filter = QPushButton(self.tr("フィルタをクリア"))
        btn_clear_filter.setFixedHeight(24)
        btn_clear_filter.clicked.connect(self._clear_table_filter)
        filter_bar.addWidget(self._filter_label)
        filter_bar.addStretch()
        filter_bar.addWidget(btn_clear_filter)
        lay.addLayout(filter_bar)

        res_tabs = QTabWidget()
        cur = self._currency

        self.gen_table = self._make_table([
            self.tr("名前"), self.tr("エリア"), self.tr("種別"), self.tr("接続バス"), self.tr("容量(MW)"), self.tr("拡張可能"),
            self.tr("最大容量(MW)"), self.tr(f"変動費({cur}/MWh)"), self.tr(f"建設費({cur}/MW)"), self.tr("効率"), self.tr("建設年"),
        ])
        self.gen_table.cellDoubleClicked.connect(lambda r, c: self._edit_generator_dialog())
        res_tabs.addTab(
            self._wrap_table(self.gen_table,
                             add_cb=self._add_generator_dialog,
                             edit_cb=self._edit_generator_dialog,
                             del_cb=lambda: self._delete_res_component("generators")),
            self.tr("発電機"))

        self.load_table = self._make_table([self.tr("名前"), self.tr("エリア"), self.tr("バスキャリア"), self.tr("需要(MW)")])
        self.load_table.cellDoubleClicked.connect(lambda r, c: self._edit_load_dialog())
        res_tabs.addTab(
            self._wrap_table(self.load_table,
                             add_cb=self._add_load_dialog,
                             edit_cb=self._edit_load_dialog,
                             del_cb=lambda: self._delete_res_component("loads")),
            self.tr("需要"))

        self.store_table = self._make_table([self.tr("名前"), self.tr("エリア"), self.tr("エネルギー容量(MWh)"), self.tr("種別")])
        self.store_table.cellDoubleClicked.connect(lambda r, c: self._edit_store_dialog())
        res_tabs.addTab(
            self._wrap_table(self.store_table,
                             add_cb=self._add_store_dialog,
                             edit_cb=self._edit_store_dialog,
                             del_cb=lambda: self._delete_res_component("stores")),
            self.tr("貯蔵"))

        self.ph_table = self._make_table([
            self.tr("名前"), self.tr("ACエリア"), self.tr("タービン容量(MW)"), self.tr("タービン効率"),
            self.tr("ポンプ容量(MW)"), self.tr("ポンプ効率"), self.tr("貯水容量(MWh)"),
            self.tr("拡張可能"), self.tr(f"建設費({cur}/MW)"), self.tr(f"変動費({cur}/MWh)"), self.tr("建設年"),
        ])
        self.ph_table.cellDoubleClicked.connect(lambda r, c: self._edit_pumped_hydro_dialog())
        res_tabs.addTab(
            self._wrap_table(self.ph_table,
                             add_cb=self._add_pumped_hydro_dialog,
                             edit_cb=self._edit_pumped_hydro_dialog,
                             del_cb=lambda: self._delete_res_component("pumped_hydros")),
            self.tr("揚水発電所"))

        self.conv_table = self._make_table([
            self.tr("名前"), self.tr("エリア"), self.tr("入力キャリア"), self.tr("出力キャリア1"), self.tr("出力キャリア2"),
            self.tr("効率１"), self.tr("効率２"), self.tr("容量(MW)"), self.tr("拡張可能"), self.tr(f"建設費({cur}/MW)"), self.tr(f"変動費({cur}/MWh)"), self.tr("建設年"),
        ])
        self.conv_table.cellDoubleClicked.connect(lambda r, c: self._edit_converter_dialog())
        res_tabs.addTab(
            self._wrap_table(self.conv_table,
                             add_cb=self._add_converter_dialog,
                             edit_cb=self._edit_converter_dialog,
                             del_cb=lambda: self._delete_res_component("converters")),
            self.tr("変換器"))

        # カスタムタブはエリアごとに動的に生成 (_rebuild_custom_tabs で追加)
        self._res_tabs = res_tabs
        lay.addWidget(res_tabs, stretch=1)

    def _toggle_table_window(self, checked: bool):
        if checked:
            self._clear_table_filter()
            self._table_window.show()
            self._table_window.raise_()
            self._table_window.activateWindow()
        else:
            self._table_window.hide()

    def _show_component_table(self, kind: str, name: str):
        """RES図のコンポーネントボックスクリック時に呼び出され、
        該当コンポーネントだけテーブルに表示する。"""
        if not self._table_window:
            return

        # テーブルウィンドウを表示する
        self.btn_table.setChecked(True)
        self._table_window.show()
        self._table_window.raise_()
        self._table_window.activateWindow()

        # kind → (tab_index, table_widget, filter_col, filter_value)
        # filter_col=-1 は全行表示
        if kind in ("generator", "generator_group"):
            tab_idx = 0
            table   = self.gen_table
            # generator_group の場合 name = "carrier|bus" → col2/3でフィルタ
            # generator の場合 name = 発電機名   → col0(名前)でフィルタ
            if kind == "generator_group":
                carrier, _, bus_carrier = name.partition("|")
                filter_col = -2
                filter_val = (carrier, bus_carrier)
                label = self.tr("フィルタ: 発電機  {} [{}]").format(carrier, bus_carrier)
            else:
                filter_col = 0
                filter_val = name
                label = self.tr("フィルタ: 発電機  {}").format(name)
        elif kind == "load":
            tab_idx = 1; table = self.load_table
            filter_col = 0; filter_val = name
            label = self.tr("フィルタ: 負荷  {}").format(name)
        elif kind == "store":
            tab_idx = 2; table = self.store_table
            filter_col = 0; filter_val = name
            label = self.tr("フィルタ: 豌蔽  {}").format(name)
        elif kind in ("pumped_hydro", "pumped_hydro_group"):
            tab_idx = 3; table = self.ph_table
            filter_col = 0 if kind == "pumped_hydro" else -1
            filter_val = name
            label = self.tr("フィルタ: 揚水発電所  {}").format(name)
        elif kind == "converter":
            tab_idx = 4; table = self.conv_table
            filter_col = 0; filter_val = name
            label = self.tr("フィルタ: 変換器  {}").format(name)
        else:
            # custom ・未知次笮からカスタムタブを探す
            if self._res_tabs:
                for i in range(self._res_tabs.count()):
                    w = self._res_tabs.widget(i)
                    t = getattr(w, "_table", None)
                    if t is None:
                        # _wrap_table の内部構造: QWidget > QVBoxLayout > QTableWidget
                        for child in w.findChildren(QTableWidget):
                            t = child; break
                    if t is not None:
                        for r in range(t.rowCount()):
                            item = t.item(r, 0)
                            if item and item.text() == name:
                                self._res_tabs.setCurrentIndex(i)
                                t.selectRow(r)
                                self._filter_label.setText(
                                    self.tr("フィルタ: カスタム  {}").format(name))
                                return
            return

        # タブ切り替え
        if self._res_tabs:
            self._res_tabs.setCurrentIndex(tab_idx)

        # 行フィルタ
        if filter_col == -2 and isinstance(filter_val, tuple):
            carrier, bus_carrier = filter_val
            for r in range(table.rowCount()):
                c_item = table.item(r, 2)
                b_item = table.item(r, 3)
                match = (
                    c_item is not None and b_item is not None
                    and c_item.text() == carrier and b_item.text() == bus_carrier
                )
                table.setRowHidden(r, not match)
                if match:
                    table.selectRow(r)
        elif filter_col >= 0:
            for r in range(table.rowCount()):
                item = table.item(r, filter_col)
                match = item is not None and item.text() == filter_val
                table.setRowHidden(r, not match)
                if match:
                    table.selectRow(r)
        else:
            # 全行表示
            for r in range(table.rowCount()):
                table.setRowHidden(r, False)

        self._filter_label.setText(label)

    def _clear_table_filter(self):
        """RESテーブルのフィルタを解除し、全行を表示する。"""
        for table in (self.gen_table, self.load_table, self.store_table,
                      self.ph_table, self.conv_table):
            for r in range(table.rowCount()):
                table.setRowHidden(r, False)
        if hasattr(self, "_filter_label"):
            self._filter_label.setText(self.tr("すべて表示"))

    def _fit_res_view(self):
        if self._res_scene and self._res_view:
            rect = self._res_scene.itemsBoundingRect().adjusted(-24, -24, 24, 24)
            if not rect.isEmpty():
                self._res_view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    # ------------------------------------------------------------------
    # Currency helpers
    # ------------------------------------------------------------------
    def _refresh_currency_headers(self):
        cur = self._currency
        self.gen_table.setHorizontalHeaderLabels([
            "名前", "エリア", "種別", "接続バス", "容量(MW)", "拡張可能",
            "最大容量(MW)", f"変動費({cur}/MWh)", f"建設費({cur}/MW)", "効率", "建設年",
        ])
        self.ic_table.setHorizontalHeaderLabels([
            "名前", "エリア0", "エリア1", "種別", "効率",
            "容量(MW)", "逆方向容量(MW)", "拡張可能", f"建設費({cur}/MW)", f"変動費({cur}/MWh)",
        ])
        self.ph_table.setHorizontalHeaderLabels([
            "名前", "ACエリア", "タービン容量(MW)", "タービン効率",
            "ポンプ容量(MW)", "ポンプ効率", "貯水容量(MWh)",
            "拡張可能", f"建設費({cur}/MW)", f"変動費({cur}/MWh)", "建設年",
        ])
        self.conv_table.setHorizontalHeaderLabels([
            "名前", "エリア", "入力キャリア", "出力キャリア1", "出力キャリア2",
            "効率1", "効率2", "容量(MW)", "拡張可能",
            f"建設費({cur}/MW)", f"変動費({cur}/MWh)", "建設年",
        ])

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------
    def _show_overview(self):
        self._current_res = None
        self._res_window.hide()

    def _open_res_window(self, area_name: str):
        res = self.network.get_area_res(area_name)
        if not res:
            return
        self._current_res = res
        self._area_label.setText(self.tr("エリア: {}").format(area_name))
        self._res_window.setWindowTitle(self.tr("RES編集: {}").format(area_name))
        self._table_window.setWindowTitle(self.tr("コンポーネントテーブル: {}").format(area_name))
        self._refresh_res_tables()
        self._res_window.show()
        self._res_window.raise_()
        self._res_window.activateWindow()
        if self.btn_table.isChecked():
            self._table_window.show()
            self._table_window.raise_()
        QTimer.singleShot(0, self._fit_res_view)

    def _open_res_window_from_table(self):
        row = self.area_table.currentRow()
        if row < 0:
            return
        name = self.area_table.item(row, 0).text()
        self._open_res_window(name)

    # ------------------------------------------------------------------
    # Table / widget factories
    # ------------------------------------------------------------------
    @staticmethod
    def _make_table(headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        return t

    @staticmethod
    def _wrap_table(table, add_cb=None, edit_cb=None, del_cb=None, note=""):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 0)
        btn_row = QHBoxLayout()
        if add_cb:
            ba = QPushButton(table.tr("追加")); ba.clicked.connect(add_cb); btn_row.addWidget(ba)
        if edit_cb:
            be = QPushButton(table.tr("編集")); be.clicked.connect(edit_cb); btn_row.addWidget(be)
        if del_cb:
            bd = QPushButton(table.tr("削除")); bd.clicked.connect(del_cb); btn_row.addWidget(bd)
        btn_row.addStretch()
        if note:
            btn_row.addWidget(QLabel(f"  ※ {note}"))
        lay.addLayout(btn_row)
        lay.addWidget(table)
        return w

    def _update_table_row(self, table, row, values):
        for c, v in enumerate(values):
            table.setItem(row, c, QTableWidgetItem(_fmt(v)))

    # ------------------------------------------------------------------
    # Map helpers
    # ------------------------------------------------------------------
    def _on_map_loaded(self, ok):
        self._map_ready = ok
        for js in self._pending_js:
            self.web_view.page().runJavaScript(js)
        self._pending_js.clear()

    def _run_js(self, js):
        if self._map_ready:
            self.web_view.page().runJavaScript(js)
        else:
            self._pending_js.append(js)

    def _set_mode(self, mode):
        for btn, m in [(self.btn_select, "select"), (self.btn_add_area, "add_bus"),
                       (self.btn_add_ic, "add_link"), (self.btn_delete, "delete")]:
            btn.setChecked(m == mode)
        self._run_js(f"setMode({json.dumps(mode)});")

    # ------------------------------------------------------------------
    # Bridge signal handlers
    # ------------------------------------------------------------------
    def _on_area_added(self, lat, lon):
        self._area_counter += 1
        name = f"Area{self._area_counter}"
        area = Area(name=name, lat=lat, lon=lon)
        self.network.areas.append(area)
        res = self.network.get_or_create_area_res(area)
        res.loads.append(Load(name=f"Load-{name}", area=name, p_set=0.0))
        self._run_js(f"addBusMarker({json.dumps(name)},{lat},{lon});")
        self._refresh_overview_tables()
        self.network_changed.emit(self.network)

    def _on_area_clicked(self, name):
        self._open_res_window(name)

    def _on_area_moved(self, name, lat, lon):
        area = next((a for a in self.network.areas if a.name == name), None)
        if not area:
            return
        area.lat = lat; area.lon = lon
        self._refresh_overview_tables()
        area_map = {a.name: a for a in self.network.areas}
        for ic in self.network.interconnections:
            if ic.area0 == name or ic.area1 == name:
                a0 = area_map.get(ic.area0); a1 = area_map.get(ic.area1)
                if a0 and a1:
                    self._run_js(
                        f"updateLinkLayer({json.dumps(ic.name)},"
                        f"{a0.lat},{a0.lon},{a1.lat},{a1.lon});")

    def _on_area_deleted(self, name):
        reply = QMessageBox.question(
            self, self.tr("確認"), self.tr("エリア '{}' と関連コンポーネントを削除しますか？").format(name), _YES | _NO)
        if reply != _YES:
            return
        for ic in [i for i in self.network.interconnections if i.area0 == name or i.area1 == name]:
            self._run_js(f"removeLinkLayer({json.dumps(ic.name)});")
        self.network.area_res_list    = [r for r in self.network.area_res_list    if r.area.name != name]
        self.network.interconnections = [i for i in self.network.interconnections if i.area0 != name and i.area1 != name]
        self.network.areas            = [a for a in self.network.areas            if a.name != name]
        self._run_js(f"removeBusMarker({json.dumps(name)});")
        if self._current_res and self._current_res.area.name == name:
            self._show_overview()
        else:
            self._refresh_overview_tables()
        self.network_changed.emit(self.network)

    def _on_ic_added_from_map(self, area0_name: str, area1_name: str):
        area_map = {a.name: a for a in self.network.areas}
        a0 = area_map.get(area0_name); a1 = area_map.get(area1_name)
        if not (a0 and a1):
            return
        dlg = InterconnectionDialog(self.network.areas, self,
                                    preset_area0=area0_name, preset_area1=area1_name,
                                    cur=self._currency,
                                    area_carriers=self._area_carriers())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self._set_mode("select")
            return
        ic = dlg.get_interconnection()
        self.network.interconnections.append(ic)
        a0 = area_map.get(ic.area0); a1 = area_map.get(ic.area1)
        if a0 and a1:
            self._run_js(f"addLinkLayer({json.dumps(ic.name)},{a0.lat},{a0.lon},{a1.lat},{a1.lon});")
        self._refresh_overview_tables()
        self._set_mode("add_link")

    def _on_ic_deleted_from_map(self, name):
        ic = next((i for i in self.network.interconnections if i.name == name), None)
        if not ic:
            return
        reply = QMessageBox.question(self, self.tr("確認"), self.tr("連系線 '{}' を削除しますか？").format(name), _YES | _NO)
        if reply != _YES:
            return
        self.network.interconnections.remove(ic)
        self._run_js(f"removeLinkLayer({json.dumps(name)});")
        self._refresh_overview_tables()

    # ------------------------------------------------------------------
    # Refresh helpers
    # ------------------------------------------------------------------
    def _refresh_overview_tables(self):
        self.area_table.setRowCount(0)
        for area in self.network.areas:
            r = self.area_table.rowCount(); self.area_table.insertRow(r)
            self._update_table_row(self.area_table, r,
                [area.name, round(area.lat, 6), round(area.lon, 6), area.country])

        self.ic_table.setRowCount(0)
        for ic in self.network.interconnections:
            r = self.ic_table.rowCount(); self.ic_table.insertRow(r)
            self._update_table_row(self.ic_table, r,
                [ic.name, ic.area0, ic.area1, ic.carrier, ic.efficiency,
                 ic.p_nom, ic.p_nom_reverse, ic.p_nom_extendable, ic.capital_cost, ic.marginal_cost])

    # ------------------------------------------------------------------
    # Dynamic custom tabs (per template)
    # ------------------------------------------------------------------
    def _rebuild_custom_tabs(self, res: AreaRES):
        """インスタンスが存在するテンプレートごとに動的タブを生成する。"""
        if self._res_tabs is None:
            return

        # 静的タブ以降を全削除
        while self._res_tabs.count() > self._STATIC_TAB_COUNT:
            self._res_tabs.removeTab(self._STATIC_TAB_COUNT)
        self._custom_tab_tables.clear()

        for tmpl in self.network.component_templates:
            instances = [ci for ci in res.custom_instances if ci.template_name == tmpl.name]
            if not instances:
                continue

            # exposed_params を (sub_id, param) ペアで収集（重複排除・無効パラム除外）
            seen: set = set()
            exposed_keys: list = []   # list of (sub_id, param_name)
            for sub in tmpl.sub_components:
                valid = AVAILABLE_EXPOSED_PARAMS.get(sub.component_type, [])
                for p in sub.exposed_params:
                    if p not in valid:
                        continue
                    key = f"{sub.sub_id}.{p}"
                    if key not in seen:
                        seen.add(key)
                        exposed_keys.append((sub.sub_id, p))

            from .component_template_editor import PARAM_LABELS
            headers = [self.tr("名前"), self.tr("エリア")] + [
                PARAM_LABELS.get(p, p) for _, p in exposed_keys]
            table = self._make_table(headers)
            for ci in instances:
                r = table.rowCount()
                table.insertRow(r)
                row_vals = [ci.name, ci.area] + [
                    ci.param_values.get(f"{sid}.{p}", "") for sid, p in exposed_keys]
                self._update_table_row(table, r, row_vals)

            tmpl_name = tmpl.name  # lambda キャプチャ用
            table.cellDoubleClicked.connect(
                lambda row, col, t=tmpl_name, tbl=table: self._edit_custom_dialog_for_template(t, tbl))
            self._res_tabs.addTab(
                self._wrap_table(
                    table,
                    add_cb=lambda t=tmpl_name: self._add_custom_dialog(preset_template=t),
                    edit_cb=lambda t=tmpl_name, tbl=table: self._edit_custom_dialog_for_template(t, tbl),
                    del_cb=lambda t=tmpl_name, tbl=table: self._delete_custom_for_template(t, tbl),
                ),
                tmpl_name)
            self._custom_tab_tables[tmpl_name] = table

    def _refresh_res_tables(self):
        if not self._current_res:
            return
        res = self._current_res

        self.gen_table.setRowCount(0)
        for g in res.generators:
            r = self.gen_table.rowCount(); self.gen_table.insertRow(r)
            self._update_table_row(self.gen_table, r,
                [g.name, g.area, g.carrier, g.bus_carrier, g.p_nom, g.p_nom_extendable,
                 g.p_nom_max, g.marginal_cost, g.capital_cost, g.efficiency, g.build_year])

        self.load_table.setRowCount(0)
        for ld in res.loads:
            r = self.load_table.rowCount(); self.load_table.insertRow(r)
            self._update_table_row(self.load_table, r, [ld.name, ld.area, ld.bus_carrier, ld.p_set])

        self.store_table.setRowCount(0)
        for st in res.stores:
            r = self.store_table.rowCount(); self.store_table.insertRow(r)
            self._update_table_row(self.store_table, r,
                [st.name, st.area, st.e_nom, st.carrier])

        self.ph_table.setRowCount(0)
        for ph in res.pumped_hydros:
            r = self.ph_table.rowCount(); self.ph_table.insertRow(r)
            self._update_table_row(self.ph_table, r,
                [ph.name, ph.ac_area,
                 ph.p_nom_turbine, ph.efficiency_turbine,
                 ph.p_nom_pump, ph.efficiency_pump,
                 ph.e_nom, ph.p_nom_extendable,
                 ph.capital_cost, ph.marginal_cost, ph.build_year])

        self.conv_table.setRowCount(0)
        for conv in res.converters:
            r = self.conv_table.rowCount(); self.conv_table.insertRow(r)
            self._update_table_row(self.conv_table, r,
                [conv.name, conv.area, conv.carrier_in, conv.carrier_out, conv.carrier_out2,
                 conv.efficiency, conv.efficiency2, conv.p_nom, conv.p_nom_extendable,
                 conv.capital_cost, conv.marginal_cost, conv.build_year])

        self._rebuild_custom_tabs(res)

        self._update_res_warnings(res)
        self._draw_res_diagram(self._current_res)

    # ------------------------------------------------------------------
    def _update_res_warnings(self, res: AreaRES):
        """未接続コンポーネントの検出結果を警告バナーに反映する（4.2節）。"""
        if not hasattr(self, "_res_warning_label"):
            return
        warnings = self._res_validate_warnings(res)
        if warnings:
            self._res_warning_label.setText("⚠ " + "  /  ".join(warnings))
            self._res_warning_label.show()
        else:
            self._res_warning_label.hide()

    def _res_validate_warnings(self, res: AreaRES) -> List[str]:
        """エリア内で供給元のないキャリアに接続された需要/変換器/貯蔵を検出する。

        AC は基幹系統（連系線経由の外部供給もあり得る）とみなし常に「供給あり」扱いとする。
        """
        produced: set = {"AC"}
        for g in res.generators:
            produced.add(g.bus_carrier or "AC")
        for c in res.converters:
            if c.carrier_out:
                produced.add(c.carrier_out)
            if c.carrier_out2:
                produced.add(c.carrier_out2)
        for ci in res.custom_instances:
            tmpl = self.network.get_template(ci.template_name)
            if tmpl:
                for sub in tmpl.sub_components:
                    for ref in sub.bus_connections.values():
                        if ref and ref.startswith("area:"):
                            produced.add(ref[5:] or "AC")

        warnings: List[str] = []
        for ld in res.loads:
            c = ld.bus_carrier or "AC"
            if c not in produced:
                warnings.append(
                    self.tr("需要「{}」({}): 供給元がありません").format(ld.name, c))
        for st in res.stores:
            c = st.carrier or "AC"
            if c not in produced and c != "AC":
                warnings.append(
                    self.tr("貯蔵「{}」({}): 供給元がありません").format(st.name, c))
        for conv in res.converters:
            c = conv.carrier_in
            if c and c not in produced and c != "AC":
                warnings.append(
                    self.tr("変換器「{}」: 入力キャリア({})の供給元がありません").format(conv.name, c))
        return warnings

    # ------------------------------------------------------------------
    def _draw_res_diagram(self, res: Optional[AreaRES],
                          _scene: Optional[QGraphicsScene] = None):
        """Draw the RES energy-flow diagram using QGraphicsScene (pixel coords)."""
        scene = _scene if _scene is not None else self._res_scene
        if scene is None:
            return
        scene.clear()
        if res is None:
            return

        # ── Layout constants (px) ─────────────────────────────────────
        BOX_H        = 54
        BOX_W_GEN    = 124
        BOX_W_CONV   = 124
        BOX_W_LOAD   = 124
        BOX_W_CUSTOM = 144
        SRC_SPACING  = 100
        CARR_SPACING = 224
        GEN_COL_GAP  = 84
        CARR_GAP     = 84
        LOAD_OFFSET  = 76
        SLOT         = 76
        Y_START      = 50
        X_MARGIN     = 50
        CARR_EXTRA   = 32   # carrier line extension above/below components

        BUS_COLORS = _BUS_COLORS_RES

        # ── Generators grouped by (carrier, bus_carrier) ─────────────
        gen_groups: dict = {}
        for g in res.generators:
            key = (g.carrier, g.bus_carrier or "AC")
            gen_groups.setdefault(key, []).append(g)
        sorted_gen_keys = sorted(gen_groups.keys(), key=lambda k: (k[0], k[1]))
        sorted_src = sorted({k[0] for k in sorted_gen_keys})
        n_src = len(sorted_src)

        # ── Active carrier lines ──────────────────────────────────────
        active_bus: set = {"AC"}
        for gen in res.generators:
            if gen.bus_carrier:
                active_bus.add(gen.bus_carrier)
        for conv in res.converters:
            for c in (conv.carrier_in, conv.carrier_out, conv.carrier_out2):
                if c:
                    active_bus.add(c)
        for ld in res.loads:
            if ld.bus_carrier:
                active_bus.add(ld.bus_carrier)
        for st in res.stores:
            if st.carrier in self._multi_carriers():
                active_bus.add(st.carrier)
        for ci in res.custom_instances:
            tmpl = self.network.get_template(ci.template_name)
            if tmpl:
                for sub in tmpl.sub_components:
                    for ref in sub.bus_connections.values():
                        if ref and ref.startswith("area:"):
                            c = ref[5:]
                            if c:
                                active_bus.add(c)

        sorted_carr = [c for c in _CARRIER_ORDER_RES if c in active_bus]
        for c in sorted(active_bus):
            if c not in sorted_carr:
                sorted_carr.append(c)
        n_carr = len(sorted_carr)

        # ── X positions ───────────────────────────────────────────────
        x0_src = X_MARGIN
        if n_src > 0:
            src_xs    = {c: int(x0_src + i * SRC_SPACING) for i, c in enumerate(sorted_src)}
            x_gen_col = int(x0_src + (n_src - 1) * SRC_SPACING + SRC_SPACING * 0.5 + GEN_COL_GAP)
            x_carr0   = x_gen_col + BOX_W_GEN // 2 + CARR_GAP
        else:
            src_xs    = {}
            x_gen_col = None
            x_carr0   = X_MARGIN + 110

        carr_xs  = {c: x_carr0 + j * CARR_SPACING for j, c in enumerate(sorted_carr)}
        x_ac     = carr_xs.get("AC", x_carr0)
        x_ph_col = x_gen_col if x_gen_col is not None else x_ac - BOX_W_GEN // 2 - 60

        # ── Y positions (top-down) ────────────────────────────────────
        y_cur = Y_START
        all_y: list = [y_cur]

        gen_ys: dict = {}
        for key in sorted_gen_keys:
            gen_ys[key] = y_cur
            y_cur += SLOT
            all_y.append(y_cur)

        ph_y = None
        if res.pumped_hydros:
            ph_y = y_cur
            y_cur += SLOT
            all_y.append(y_cur)

        conv_ys: list = []
        for _ in res.converters:
            conv_ys.append(y_cur)
            y_cur += SLOT
            all_y.append(y_cur)

        load_by_bus: dict = {}
        for ld in res.loads:
            load_by_bus.setdefault(ld.bus_carrier or "AC", []).append(ld)

        load_ys: dict = {}
        for bus_c, lds in sorted(load_by_bus.items()):
            load_ys[bus_c] = []
            for ld in lds:
                load_ys[bus_c].append((ld, y_cur))
                y_cur += SLOT
                all_y.append(y_cur)

        store_ys: dict = {}
        for st in res.stores:
            carrier = st.carrier if st.carrier in self._multi_carriers() else "AC"
            store_ys.setdefault(carrier, []).append((st, y_cur))
            y_cur += SLOT
            all_y.append(y_cur)

        ext_custom_ys: list = []
        local_custom_ys: list = []
        for ci in res.custom_instances:
            _tmpl = self.network.get_template(ci.template_name)
            _is_ext = bool(_tmpl) and any(
                ref and ":" in ref and not ref.startswith("area:")
                for sub in _tmpl.sub_components
                for ref in sub.bus_connections.values()
            )
            if _is_ext:
                ext_custom_ys.append((ci, y_cur))
            else:
                local_custom_ys.append((ci, y_cur))
            y_cur += SLOT
            all_y.append(y_cur)

        y_line_top = (min(all_y) - CARR_EXTRA) if all_y else 0
        y_line_bot = (max(all_y) + CARR_EXTRA) if all_y else 200

        # ── Source lines ──────────────────────────────────────────────
        for src_c, sx in src_xs.items():
            ln = QGraphicsLineItem(sx, y_line_top, sx, y_line_bot)
            ln.setPen(QPen(QColor("#bdc3c7"), 1.5))
            scene.addItem(ln)
            ti = _res_label(scene, src_c, 0, y_line_top - 26, "#7f8c8d", pt=9, bold=True)
            ti.setPos(sx - ti.boundingRect().width() / 2, y_line_top - 26)

        # ── Carrier bus lines ─────────────────────────────────────────
        for carr_c, cx in carr_xs.items():
            col = BUS_COLORS.get(carr_c, "#7f8c8d")
            ln = QGraphicsLineItem(cx, y_line_top, cx, y_line_bot)
            ln.setPen(QPen(QColor(col), 3))
            scene.addItem(ln)
            ti = _res_label(scene, carr_c, 0, y_line_top - 26, col, pt=10, bold=True)
            ti.setPos(cx - ti.boundingRect().width() / 2, y_line_top - 26)

        # ── Generator boxes ───────────────────────────────────────────
        for src_c, bus_c in sorted_gen_keys:
            gens     = gen_groups[(src_c, bus_c)]
            total_mw = sum(g.p_nom for g in gens)
            label    = f"{src_c}\n×{len(gens)} / {total_mw:.0f} MW"
            gy       = gen_ys[(src_c, bus_c)]
            sx       = src_xs[src_c]
            gx       = x_gen_col - BOX_W_GEN // 2
            cx_bus = carr_xs.get(bus_c, x_ac)
            kind = "generator" if len(gens) == 1 else "generator_group"
            name = gens[0].name if len(gens) == 1 else f"{src_c}|{bus_c}"
            scene.addItem(_ResBoxItem(
                gx, gy, BOX_W_GEN, BOX_H, label, kind, name, self,
                face="#ecf0f1", edge="#7f8c8d", lw=1.0))
            mid_y = gy + BOX_H // 2
            gen_in_x = _res_box_anchor_x(gx, BOX_W_GEN, sx)
            gen_out_x = _res_box_anchor_x(gx, BOX_W_GEN, cx_bus)
            _res_draw_arrow(scene, sx, mid_y, gen_in_x, mid_y, "#bdc3c7")
            _res_draw_arrow(scene, gen_out_x, mid_y, cx_bus, mid_y, "#7f8c8d")

        # ── Pumped hydro box ──────────────────────────────────────────
        if res.pumped_hydros and ph_y is not None:
            total_t = sum(ph.p_nom_turbine for ph in res.pumped_hydros)
            total_p = sum(ph.p_nom_pump    for ph in res.pumped_hydros)
            n_ph    = len(res.pumped_hydros)
            label   = f"揚水 ×{n_ph}\nT:{total_t:.0f} P:{total_p:.0f} MW"
            px_box  = x_ph_col - BOX_W_GEN // 2
            kind = "pumped_hydro" if n_ph == 1 else "pumped_hydro_group"
            name = res.pumped_hydros[0].name if n_ph == 1 else "pumped_hydros"
            scene.addItem(_ResBoxItem(
                px_box, ph_y, BOX_W_GEN, BOX_H, label, kind, name, self,
                face="#d6eaf8", edge="#2980b9", lw=1.5))
            mid_y = ph_y + BOX_H // 2
            ph_x = _res_box_anchor_x(px_box, BOX_W_GEN, x_ac)
            _res_draw_arrow(scene, ph_x, mid_y, x_ac, mid_y,
                            "#2980b9", bidirectional=True)

        # ── Converter boxes ───────────────────────────────────────────
        for idx, conv in enumerate(res.converters):
            cy    = conv_ys[idx]
            in_x  = carr_xs.get(conv.carrier_in,  x_ac)
            out_x = carr_xs.get(conv.carrier_out, x_ac)
            has_out2 = bool(conv.carrier_out2 and conv.carrier_out2 in carr_xs)
            if has_out2:
                out2_x = carr_xs[conv.carrier_out2]
                # ボックスを入力と「最も近い出力」の間に配置する。
                # こうすることでキャリア縦線とボックスの重なりを防ぐ。
                nearest_out_x = out_x if abs(out_x - in_x) <= abs(out2_x - in_x) else out2_x
                conv_cx = (in_x + nearest_out_x) / 2
            else:
                conv_cx = (in_x + out_x) / 2
            bx    = int(conv_cx - BOX_W_CONV / 2)
            label = f"{conv.name}\n{conv.p_nom:.0f} MW"
            scene.addItem(_ResBoxItem(
                bx, cy, BOX_W_CONV, BOX_H, label, "converter", conv.name, self,
                face="#fef9e7", edge="#e67e22", lw=1.0))
            mid_y = cy + BOX_H // 2
            in_col  = BUS_COLORS.get(conv.carrier_in,  "#555")
            out_col = BUS_COLORS.get(conv.carrier_out, "#555")
            in_box_x = _res_box_anchor_x(bx, BOX_W_CONV, in_x)
            out_box_x = _res_box_anchor_x(bx, BOX_W_CONV, out_x)
            if has_out2:
                # 2出力はY方向に±9pxずらして視覚的に分離
                _res_draw_arrow(scene, in_x, mid_y, in_box_x, mid_y, in_col)
                _res_draw_arrow(scene, out_box_x, mid_y - 9, out_x, mid_y - 9, out_col)
                out2_col = BUS_COLORS.get(conv.carrier_out2, "#555")
                out2_box_x = _res_box_anchor_x(bx, BOX_W_CONV, out2_x)
                _res_draw_arrow(scene, out2_box_x, mid_y + 9, out2_x, mid_y + 9, out2_col)
            else:
                _res_draw_arrow(scene, in_x, mid_y, in_box_x, mid_y, in_col)
                _res_draw_arrow(scene, out_box_x, mid_y, out_x, mid_y, out_col)

        # ── Load boxes ────────────────────────────────────────────────
        for bus_c, entries in load_ys.items():
            cx      = carr_xs.get(bus_c, x_ac)
            box_x   = cx + LOAD_OFFSET
            bus_col = BUS_COLORS.get(bus_c, "#7f8c8d")
            for ld, ly in entries:
                label = f"{ld.name}\n{ld.p_set:.0f} MW"
                scene.addItem(_ResEllipseItem(
                    box_x, ly, BOX_W_LOAD, BOX_H, label, "load", ld.name, self,
                    face="#fdfefe", edge="#7f8c8d", lw=1.0))
                load_x = _res_box_anchor_x(box_x, BOX_W_LOAD, cx)
                _res_draw_arrow(scene, cx, ly + BOX_H // 2, load_x, ly + BOX_H // 2, bus_col)

        # ── Store boxes ───────────────────────────────────────────────
        for carrier, entries in store_ys.items():
            cx      = carr_xs.get(carrier, x_ac)
            box_x   = cx + LOAD_OFFSET
            bus_col = BUS_COLORS.get(carrier, "#7f8c8d")
            for st, sy in entries:
                label = f"{st.name}\n{st.e_nom:.0f} MWh"
                scene.addItem(_ResBoxItem(
                    box_x, sy, BOX_W_LOAD, BOX_H, label, "store", st.name, self,
                    face="#e8f8f5", edge="#1abc9c", lw=1.0))
                store_x = _res_box_anchor_x(box_x, BOX_W_LOAD, cx)
                _res_draw_arrow(scene, cx, sy + BOX_H // 2, store_x, sy + BOX_H // 2,
                                "#1abc9c", bidirectional=True)

        # ── External custom boxes (left of generator column) ──────────
        for ci, cy in ext_custom_ys:
            tmpl = self.network.get_template(ci.template_name)
            ext_refs: set   = set()
            local_carriers: set = set()
            if tmpl:
                for sub in tmpl.sub_components:
                    for ref in sub.bus_connections.values():
                        if not ref:
                            continue
                        if ref.startswith("area:"):
                            c = ref[5:]
                            if c:
                                local_carriers.add(c)
                        elif ":" in ref:
                            ext_refs.add(ref)
            if not local_carriers:
                local_carriers = {"AC"}
            bx    = x_ph_col - BOX_W_CUSTOM // 2
            label = f"{ci.name}\n{ci.template_name}"
            scene.addItem(_ResBoxItem(
                bx, cy, BOX_W_CUSTOM, BOX_H, label, "custom", ci.name, self,
                face="#e8f4fd", edge="#1565c0", lw=1.5))
            mid_y  = cy + BOX_H // 2
            src_x  = bx - 60
            if ext_refs:
                ext_lbl = ", ".join(sorted(ext_refs))
                ti = scene.addText(ext_lbl)
                f  = QFont(); f.setPointSize(7)
                ti.setFont(f); ti.setDefaultTextColor(QColor("#1565c0"))
                ti.setPos(src_x - ti.boundingRect().width() / 2, mid_y - 22)
            in_box_x = _res_box_anchor_x(bx, BOX_W_CUSTOM, src_x)
            _res_draw_arrow(scene, src_x, mid_y, in_box_x, mid_y, "#1565c0")
            for carrier in sorted(local_carriers):
                bus_x   = carr_xs.get(carrier, x_ac)
                bus_col = BUS_COLORS.get(carrier, "#1565c0")
                out_box_x = _res_box_anchor_x(bx, BOX_W_CUSTOM, bus_x)
                _res_draw_arrow(scene, out_box_x, mid_y, bus_x, mid_y, bus_col)

        # ── Local custom boxes ────────────────────────────────────────
        for ci, cy in local_custom_ys:
            tmpl = self.network.get_template(ci.template_name)
            touched: set = set()
            if tmpl:
                for sub in tmpl.sub_components:
                    for ref in sub.bus_connections.values():
                        if ref and ref.startswith("area:"):
                            c = ref[5:]
                            if c:
                                touched.add(c)
            if not touched:
                touched = {"AC"}
            touched_xs = {c: carr_xs.get(c, x_ac) for c in touched}
            if len(touched_xs) >= 2:
                min_x  = min(touched_xs.values())
                max_x  = max(touched_xs.values())
                box_cx = (min_x + max_x) // 2
                bx     = box_cx - BOX_W_CUSTOM // 2
            else:
                primary_x = next(iter(touched_xs.values()))
                bx     = primary_x + LOAD_OFFSET
                box_cx = bx + BOX_W_CUSTOM // 2
            label = f"{ci.name}\n{ci.template_name}"
            scene.addItem(_ResBoxItem(
                bx, cy, BOX_W_CUSTOM, BOX_H, label, "custom", ci.name, self,
                face="#f5eef8", edge="#8e44ad", lw=1.5))
            mid_y = cy + BOX_H // 2
            for carrier in sorted(touched):
                bus_x   = carr_xs.get(carrier, x_ac)
                bus_col = BUS_COLORS.get(carrier, "#8e44ad")
                box_x = _res_box_anchor_x(bx, BOX_W_CUSTOM, bus_x)
                _res_draw_arrow(scene, bus_x, mid_y, box_x, mid_y,
                                bus_col, bidirectional=True)

        # ── Fit view ──────────────────────────────────────────────────
        if _scene is None and self._res_view is not None:
            rect = scene.itemsBoundingRect().adjusted(-24, -24, 24, 24)
            scene.setSceneRect(rect)
            self._res_view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _edit_component_by_name(self, kind: str, name: str):
        """コンポーネント名を直接指定して編集ダイアログを開く。"""
        if not self._current_res:
            return
        res = self._current_res

        if kind == "generator":
            orig = next((g for g in res.generators if g.name == name), None)
            dlg = GeneratorDialog(self.network.areas, self._res_window,
                                  existing=orig, preset_area=res.area.name, cur=self._currency,
                                  generator_carriers=self._generator_carriers(),
                                  area_carriers=self._area_carriers())
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            new_obj = dlg.get_generator()
            for r in self.network.area_res_list:
                for i, g in enumerate(r.generators):
                    if g.name == name:
                        r.generators[i] = new_obj; break

        elif kind == "generator_group":
            # 同キャリアに複数の発電機 → 発電機タブに切替
            if self._res_tabs:
                self._res_tabs.setCurrentIndex(0)
            return

        elif kind == "load":
            orig = next((l for l in res.loads if l.name == name), None)
            ts_vals = []
            if self._timeseries_editor is not None and orig is not None:
                ts_vals = self._timeseries_editor.get_timeseries().get_demand_for_load(res.area.name, name)
            dlg = LoadDialog(self.network.areas, self._res_window,
                             existing=orig, preset_area=res.area.name,
                             area_carriers=self._area_carriers(),
                             ts_values=ts_vals)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            new_obj = dlg.get_load()
            for r in self.network.area_res_list:
                for i, l in enumerate(r.loads):
                    if l.name == name:
                        r.loads[i] = new_obj; break
            self._write_back_load_ts(dlg, new_obj.area, new_obj.name,
                                     old_area=res.area.name, old_name=name)

        elif kind == "store":
            orig = next((s for s in res.stores if s.name == name), None)
            dlg = StoreDialog(self.network.areas, self._res_window,
                              existing=orig, preset_area=res.area.name,
                              area_carriers=self._area_carriers())
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            new_obj = dlg.get_store()
            for r in self.network.area_res_list:
                for i, s in enumerate(r.stores):
                    if s.name == name:
                        r.stores[i] = new_obj; break

        elif kind == "pumped_hydro":
            orig = next((p for p in res.pumped_hydros if p.name == name), None)
            dlg = PumpedHydroDialog(self.network.areas, self._res_window,
                                    existing=orig, preset_area=res.area.name, cur=self._currency)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            new_obj = dlg.get_pumped_hydro()
            for r in self.network.area_res_list:
                for i, p in enumerate(r.pumped_hydros):
                    if p.name == name:
                        r.pumped_hydros[i] = new_obj; break

        elif kind == "pumped_hydro_group":
            # 複数揚水 → 揚水タブに切替
            if self._res_tabs:
                self._res_tabs.setCurrentIndex(2)
            return

        elif kind == "converter":
            orig = next((c for c in res.converters if c.name == name), None)
            dlg = ConverterDialog(self.network.areas, self._res_window,
                                  existing=orig, preset_area=res.area.name, cur=self._currency,
                                  multi_carriers=self._multi_carriers())
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            new_obj = dlg.get_converter()
            for r in self.network.area_res_list:
                for i, c in enumerate(r.converters):
                    if c.name == name:
                        r.converters[i] = new_obj; break

        elif kind == "custom":
            orig = next((c for c in res.custom_instances if c.name == name), None)
            dlg = CustomInstanceDialog(
                self.network.component_templates, self.network.areas, self._res_window,
                existing=orig, preset_area=res.area.name, cur=self._currency)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            new_obj = dlg.get_instance()
            for r in self.network.area_res_list:
                for i, c in enumerate(r.custom_instances):
                    if c.name == name:
                        r.custom_instances[i] = new_obj; break

        else:
            return

        self._refresh_res_tables()
        self.network_changed.emit(self.network)

    # ------------------------------------------------------------------
    # Delete helpers
    # ------------------------------------------------------------------
    def _delete_area_from_table(self):
        row = self.area_table.currentRow()
        if row < 0:
            return
        name = self.area_table.item(row, 0).text()
        self._on_area_deleted(name)

    def _delete_ic_selected(self):
        row = self.ic_table.currentRow()
        if row < 0:
            return
        name = self.ic_table.item(row, 0).text()
        reply = QMessageBox.question(self, self.tr("確認"), self.tr("連系線 '{}' を削除しますか？").format(name), _YES | _NO)
        if reply != _YES:
            return
        self.network.interconnections = [i for i in self.network.interconnections if i.name != name]
        self._run_js(f"removeLinkLayer({json.dumps(name)});")
        self._refresh_overview_tables()

    def _delete_res_component(self, ctype: str):
        """Delete selected row from the currently visible RES component table."""
        if not self._current_res:
            return
        table_map = {
            "generators":    self.gen_table,
            "loads":         self.load_table,
            "stores":        self.store_table,
            "pumped_hydros": self.ph_table,
            "converters":    self.conv_table,
        }
        table = table_map.get(ctype)
        if not table:
            return
        row = table.currentRow()
        if row < 0:
            return
        name = table.item(row, 0).text()
        self._delete_res_component_by_name(ctype, name, confirm=True)

    # kind (RES diagram) -> ctype (AreaRES list attribute name)
    _KIND_TO_CTYPE = {
        "generator": "generators", "load": "loads", "store": "stores",
        "pumped_hydro": "pumped_hydros", "converter": "converters",
    }

    def _delete_res_component_by_name(self, ctype: str, name: str, confirm: bool = True):
        """Remove a single named component from the current AreaRES and refresh."""
        if not self._current_res:
            return
        if confirm:
            reply = QMessageBox.question(self._res_window, self.tr("確認"), self.tr("'{}' を削除しますか？").format(name), _YES | _NO)
            if reply != _YES:
                return
        res = self._current_res
        if ctype == "generators":
            res.generators = [g for g in res.generators if g.name != name]
        elif ctype == "loads":
            res.loads = [l for l in res.loads if l.name != name]
        elif ctype == "stores":
            res.stores = [s for s in res.stores if s.name != name]
        elif ctype == "pumped_hydros":
            res.pumped_hydros = [p for p in res.pumped_hydros if p.name != name]
        elif ctype == "converters":
            res.converters = [c for c in res.converters if c.name != name]
        else:
            return
        self._refresh_res_tables()
        self.network_changed.emit(self.network)

    def _res_component_context_menu(self, kind: str, name: str, screen_pos):
        """RES図のノード右クリック時のコンテキストメニュー（編集/削除）。"""
        ctype = self._KIND_TO_CTYPE.get(kind)
        menu = QMenu(self._res_window)
        act_edit = menu.addAction(self.tr("編集"))
        act_del = menu.addAction(self.tr("削除")) if ctype else None
        pos = screen_pos.toPoint() if hasattr(screen_pos, "toPoint") else screen_pos
        act = menu.exec(pos)
        if act == act_edit:
            self._edit_component_by_name(kind, name)
        elif act is not None and act == act_del and ctype:
            self._delete_res_component_by_name(ctype, name, confirm=True)

    # ------------------------------------------------------------------
    # Area edit (overview & RES header)
    # ------------------------------------------------------------------
    def _edit_area_dialog(self):
        row = self.area_table.currentRow()
        if row < 0:
            QMessageBox.information(self, self.tr("情報"), self.tr("編集するエリアを選択してください。")); return
        old_name = self.area_table.item(row, 0).text()
        self._do_edit_area(old_name)

    def _edit_area_dialog_from_res(self):
        if not self._current_res:
            return
        self._do_edit_area(self._current_res.area.name, dlg_parent=self._res_window)

    def _do_edit_area(self, old_name: str, dlg_parent=None):
        area = next((a for a in self.network.areas if a.name == old_name), None)
        if not area:
            return
        dlg = AreaEditDialog(area, dlg_parent or self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_name, lat, lon, country = dlg.get_values()

        if new_name != old_name:
            self._run_js(f"removeBusMarker({json.dumps(old_name)});")
            self._run_js(f"addBusMarker({json.dumps(new_name)},{lat},{lon});")
            for res in self.network.area_res_list:
                if res.area.name == old_name:
                    for g  in res.generators:   g.area     = new_name
                    for ld in res.loads:         ld.area    = new_name
                    for st in res.stores:        st.area    = new_name
                    for ph in res.pumped_hydros: ph.ac_area = new_name
            for ic in self.network.interconnections:
                if ic.area0 == old_name: ic.area0 = new_name
                if ic.area1 == old_name: ic.area1 = new_name
        else:
            self._run_js(f"updateBusPosition({json.dumps(new_name)},{lat},{lon});")
            area_map = {a.name: a for a in self.network.areas}
            area_map[new_name] = Area(name=new_name, lat=lat, lon=lon)
            for ic in self.network.interconnections:
                if ic.area0 == new_name or ic.area1 == new_name:
                    a0 = area_map.get(ic.area0); a1 = area_map.get(ic.area1)
                    if a0 and a1:
                        self._run_js(
                            f"updateLinkLayer({json.dumps(ic.name)},"
                            f"{a0.lat},{a0.lon},{a1.lat},{a1.lon});")

        area.name = new_name; area.lat = lat; area.lon = lon; area.country = country
        self._refresh_overview_tables()
        if self._current_res and self._current_res.area.name in (old_name, new_name):
            self._area_label.setText(self.tr("エリア: {}").format(new_name))
            self._res_window.setWindowTitle(self.tr("RES編集: {}").format(new_name))
        self.network_changed.emit(self.network)

    # ------------------------------------------------------------------
    # Interconnection dialogs (overview)
    # ------------------------------------------------------------------
    def _add_ic_dialog(self):
        if len(self.network.areas) < 2:
            QMessageBox.warning(self, self.tr("警告"), self.tr("エリアが2つ以上必要です。")); return
        dlg = InterconnectionDialog(self.network.areas, self, cur=self._currency,
                        area_carriers=self._area_carriers())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ic = dlg.get_interconnection()
            self.network.interconnections.append(ic)
            area_map = {a.name: a for a in self.network.areas}
            a0 = area_map.get(ic.area0); a1 = area_map.get(ic.area1)
            if a0 and a1:
                self._run_js(f"addLinkLayer({json.dumps(ic.name)},{a0.lat},{a0.lon},{a1.lat},{a1.lon});")
            self._refresh_overview_tables()

    def _edit_ic_dialog(self):
        row = self.ic_table.currentRow()
        if row < 0:
            QMessageBox.information(self, self.tr("情報"), self.tr("編集する連系線を選択してください。")); return
        old_name = self.ic_table.item(row, 0).text()
        ic = next((i for i in self.network.interconnections if i.name == old_name), None)
        if not ic:
            return
        dlg = InterconnectionDialog(self.network.areas, self, existing=ic, cur=self._currency,
                        area_carriers=self._area_carriers())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_ic = dlg.get_interconnection()
        area_map = {a.name: a for a in self.network.areas}
        a0 = area_map.get(new_ic.area0); a1 = area_map.get(new_ic.area1)
        if new_ic.name != old_name:
            self._run_js(f"removeLinkLayer({json.dumps(old_name)});")
            if a0 and a1:
                self._run_js(f"addLinkLayer({json.dumps(new_ic.name)},{a0.lat},{a0.lon},{a1.lat},{a1.lon});")
        elif a0 and a1:
            self._run_js(f"updateLinkLayer({json.dumps(new_ic.name)},{a0.lat},{a0.lon},{a1.lat},{a1.lon});")
        idx = self.network.interconnections.index(ic)
        self.network.interconnections[idx] = new_ic
        self._refresh_overview_tables()

    # ------------------------------------------------------------------
    # RES component dialogs (RES panel — operate on self._current_res)
    # ------------------------------------------------------------------
    def _add_generator_dialog(self):
        if not self._current_res:
            return
        dlg = GeneratorDialog(self.network.areas, self._res_window,
                              preset_area=self._current_res.area.name, cur=self._currency,
                              generator_carriers=self._generator_carriers(),
                              area_carriers=self._area_carriers())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            gen = dlg.get_generator()
            res = self.network.get_area_res(gen.area) or self._current_res
            res.generators.append(gen)
            self._write_back_ts(dlg, gen.name, gen.carrier)
            self._refresh_res_tables()
            self.network_changed.emit(self.network)

    def _edit_generator_dialog(self):
        row = self.gen_table.currentRow()
        if row < 0:
            QMessageBox.information(self._res_window, self.tr("情報"), self.tr("編集する発電機を選択してください。")); return
        old_name = self.gen_table.item(row, 0).text()
        existing_gen = self._find_generator(old_name)
        ts_vals = []
        if self._timeseries_editor is not None and existing_gen is not None:
            ts = self._timeseries_editor.get_timeseries()
            ts_vals = ts.get_gen_cf(old_name, existing_gen.carrier)
        dlg = GeneratorDialog(self.network.areas, self._res_window,
                              existing=existing_gen,
                              preset_area=self._current_res.area.name if self._current_res else None,
                              cur=self._currency,
                              ts_values=ts_vals,
                              generator_carriers=self._generator_carriers(),
                              area_carriers=self._area_carriers())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_gen = dlg.get_generator()
        for res in self.network.area_res_list:
            for i, g in enumerate(res.generators):
                if g.name == old_name:
                    res.generators[i] = new_gen; break
        self._write_back_ts(dlg, new_gen.name, new_gen.carrier, old_name=old_name)
        self._refresh_res_tables()
        self.network_changed.emit(self.network)

    def _write_back_ts(self, dlg: "GeneratorDialog", gen_name: str, carrier: str,
                       old_name: str = None) -> None:
        """TS値を TimeSeriesEditor に書き戻す。"""
        if self._timeseries_editor is None:
            return
        ts = self._timeseries_editor.get_timeseries()
        # 名前変更時は旧エントリを削除
        if old_name and old_name != gen_name:
            for d in (ts.solar_cf, ts.wind_cf, ts.hydro_cf, ts.biomass_cf, ts.gen_cf,
                      ts.ts_mode, ts.fixed_output):
                d.pop(old_name, None)
        vals = dlg.get_ts_values()
        if any(v != 0.0 for v in vals):
            ts.set_gen_cf(gen_name, carrier, vals)
            ts.ts_mode[gen_name]      = dlg.get_ts_mode()
            ts.fixed_output[gen_name] = dlg.get_ts_fixed()
        self._timeseries_editor.load_timeseries(ts)

    def _write_back_load_ts(self, dlg: "LoadDialog", area: str, load_name: str,
                            old_area: str = None, old_name: str = None) -> None:
        """需要TS値を TimeSeriesEditor に書き戻す。"""
        if self._timeseries_editor is None:
            return
        ts = self._timeseries_editor.get_timeseries()
        # エリア・名前変更時は旧エントリを削除
        if old_name and (old_area != area or old_name != load_name):
            ts.demand_mw.pop(TimeSeriesData.make_load_key(old_area, old_name), None)
        vals = dlg.get_ts_values()
        if any(v != 0.0 for v in vals):
            ts.set_demand_for_load(area, load_name, vals)
        self._timeseries_editor.load_timeseries(ts)

    def _add_load_dialog(self):
        if not self._current_res:
            return
        dlg = LoadDialog(self.network.areas, self._res_window,
                         preset_area=self._current_res.area.name,
                         area_carriers=self._area_carriers())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ld = dlg.get_load()
            res = self.network.get_area_res(ld.area) or self._current_res
            res.loads.append(ld)
            self._write_back_load_ts(dlg, ld.area, ld.name)
            self._refresh_res_tables()
            self.network_changed.emit(self.network)

    def _edit_load_dialog(self):
        row = self.load_table.currentRow()
        if row < 0:
            QMessageBox.information(self._res_window, self.tr("情報"), self.tr("編集する負荷を選択してください。")); return
        old_name = self.load_table.item(row, 0).text()
        old_area = self._current_res.area.name if self._current_res else None
        orig = next((l for l in (self._current_res.loads if self._current_res else []) if l.name == old_name), None)
        ts_vals = []
        if self._timeseries_editor is not None and orig is not None:
            ts_vals = self._timeseries_editor.get_timeseries().get_demand_for_load(old_area, old_name)
        dlg = LoadDialog(self.network.areas, self._res_window, existing=orig,
                         preset_area=old_area,
                         area_carriers=self._area_carriers(),
                         ts_values=ts_vals)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_ld = dlg.get_load()
        for res in self.network.area_res_list:
            for i, l in enumerate(res.loads):
                if l.name == old_name:
                    res.loads[i] = new_ld; break
        self._write_back_load_ts(dlg, new_ld.area, new_ld.name, old_area=old_area, old_name=old_name)
        self._refresh_res_tables()
        self.network_changed.emit(self.network)

    def _add_store_dialog(self):
        if not self._current_res:
            return
        dlg = StoreDialog(self.network.areas, self._res_window,
                          preset_area=self._current_res.area.name,
                          area_carriers=self._area_carriers())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            st = dlg.get_store()
            res = self.network.get_area_res(st.area) or self._current_res
            res.stores.append(st)
            self._refresh_res_tables()
            self.network_changed.emit(self.network)

    def _edit_store_dialog(self):
        row = self.store_table.currentRow()
        if row < 0:
            QMessageBox.information(self._res_window, self.tr("情報"), self.tr("編集する貯蔵を選択してください。")); return
        old_name = self.store_table.item(row, 0).text()
        orig = next((s for s in (self._current_res.stores if self._current_res else []) if s.name == old_name), None)
        dlg = StoreDialog(self.network.areas, self._res_window, existing=orig,
                          preset_area=self._current_res.area.name if self._current_res else None,
                          area_carriers=self._area_carriers())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_st = dlg.get_store()
        for res in self.network.area_res_list:
            for i, s in enumerate(res.stores):
                if s.name == old_name:
                    res.stores[i] = new_st; break
        self._refresh_res_tables()
        self.network_changed.emit(self.network)

    def _add_pumped_hydro_dialog(self):
        if not self._current_res:
            return
        dlg = PumpedHydroDialog(self.network.areas, self._res_window,
                                preset_area=self._current_res.area.name, cur=self._currency)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ph = dlg.get_pumped_hydro()
            res = self.network.get_area_res(ph.ac_area) or self._current_res
            res.pumped_hydros.append(ph)
            self._refresh_res_tables()
            self.network_changed.emit(self.network)

    def _edit_pumped_hydro_dialog(self):
        row = self.ph_table.currentRow()
        if row < 0:
            QMessageBox.information(self._res_window, self.tr("情報"), self.tr("編集する揚水発電所を選択してください。")); return
        old_name = self.ph_table.item(row, 0).text()
        orig = next((p for p in (self._current_res.pumped_hydros if self._current_res else []) if p.name == old_name), None)
        dlg = PumpedHydroDialog(self.network.areas, self._res_window, existing=orig,
                                preset_area=self._current_res.area.name if self._current_res else None,
                                cur=self._currency)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_ph = dlg.get_pumped_hydro()
        for res in self.network.area_res_list:
            for i, p in enumerate(res.pumped_hydros):
                if p.name == old_name:
                    res.pumped_hydros[i] = new_ph; break
        self._refresh_res_tables()
        self.network_changed.emit(self.network)

    def _add_converter_dialog(self):
        if not self._current_res:
            return
        dlg = ConverterDialog(self.network.areas, self._res_window,
                              preset_area=self._current_res.area.name, cur=self._currency,
                              multi_carriers=self._multi_carriers())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            conv = dlg.get_converter()
            res = self.network.get_area_res(conv.area) or self._current_res
            res.converters.append(conv)
            self._refresh_res_tables()
            self.network_changed.emit(self.network)

    def _edit_converter_dialog(self):
        row = self.conv_table.currentRow()
        if row < 0:
            QMessageBox.information(self._res_window, self.tr("情報"), self.tr("編集する変換器を選択してください。")); return
        old_name = self.conv_table.item(row, 0).text()
        orig = next((c for c in (self._current_res.converters if self._current_res else [])
                     if c.name == old_name), None)
        dlg = ConverterDialog(self.network.areas, self._res_window, existing=orig,
                              preset_area=self._current_res.area.name if self._current_res else None,
                              cur=self._currency,
                              multi_carriers=self._multi_carriers())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_conv = dlg.get_converter()
        for res in self.network.area_res_list:
            for i, c in enumerate(res.converters):
                if c.name == old_name:
                    res.converters[i] = new_conv; break
        self._refresh_res_tables()
        self.network_changed.emit(self.network)

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Custom component instance dialogs
    # ------------------------------------------------------------------
    def _add_custom_dialog(self, preset_template: str = ""):
        if not self._current_res:
            return
        if not self.network.component_templates:
            QMessageBox.information(
                self._res_window, self.tr("情報"),
                self.tr("テンプレートがありません。\n「コンポーネント定義」から作成してください。"))
            return
        # preset_template が指定されたらそのテンプレートのみ渡す
        if preset_template:
            templates = [t for t in self.network.component_templates if t.name == preset_template]
            if not templates:
                templates = self.network.component_templates
        else:
            templates = self.network.component_templates
        dlg = CustomInstanceDialog(
            templates, self.network.areas, self._res_window,
            preset_area=self._current_res.area.name, cur=self._currency)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ci = dlg.get_instance()
            res = self.network.get_area_res(ci.area) or self._current_res
            res.custom_instances.append(ci)
            self._refresh_res_tables()
            self.network_changed.emit(self.network)

    def _edit_custom_dialog_for_template(self, tmpl_name: str, table=None):
        """指定テンプレートのタブで選択中のインスタンスを編集する。"""
        if table is None:
            table = self._custom_tab_tables.get(tmpl_name)
        if not table:
            QMessageBox.warning(self._res_window, self.tr("警告"),
                                self.tr("テーブルが見つかりません（テンプレート: {}）").format(tmpl_name))
            return
        rows = table.selectionModel().selectedRows()
        row = rows[0].row() if rows else table.currentRow()
        if row < 0:
            QMessageBox.information(self._res_window, self.tr("情報"),
                                    self.tr("編集するコンポーネントを選択してください。"))
            return
        old_name = table.item(row, 0).text()
        orig = next(
            (c for c in (self._current_res.custom_instances if self._current_res else [])
             if c.name == old_name), None)
        dlg = CustomInstanceDialog(
            self.network.component_templates, self.network.areas, self._res_window,
            existing=orig,
            preset_area=self._current_res.area.name if self._current_res else "",
            cur=self._currency)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_ci = dlg.get_instance()
        for res in self.network.area_res_list:
            for i, c in enumerate(res.custom_instances):
                if c.name == old_name:
                    res.custom_instances[i] = new_ci
                    break
        self._refresh_res_tables()
        self.network_changed.emit(self.network)

    def _delete_custom_for_template(self, tmpl_name: str, table=None):
        """指定テンプレートのタブで選択中のインスタンスを削除する。"""
        if table is None:
            table = self._custom_tab_tables.get(tmpl_name)
        if not table:
            QMessageBox.warning(self._res_window, self.tr("警告"),
                                self.tr("テーブルが見つかりません（テンプレート: {}）").format(tmpl_name))
            return
        if not self._current_res:
            QMessageBox.warning(self._res_window, self.tr("警告"),
                                self.tr("エリアが選択されていません。"))
            return
        rows = table.selectionModel().selectedRows()
        row = rows[0].row() if rows else table.currentRow()
        if row < 0:
            QMessageBox.warning(
                self._res_window, self.tr("警告"),
                self.tr("削除するインスタンスを選択してください。"))
            return
        name = table.item(row, 0).text()
        reply = QMessageBox.question(
            self._res_window, self.tr("確認"),
            self.tr("'{}' を削除しますか？").format(name), _YES | _NO)
        if reply != _YES:
            return
        self._current_res.custom_instances = [
            c for c in self._current_res.custom_instances if c.name != name]
        self._refresh_res_tables()
        self.network_changed.emit(self.network)

    # ------------------------------------------------------------------
    # Template editor
    # ------------------------------------------------------------------
    def _open_template_editor(self, parent_widget=None):
        dlg = ComponentTemplateEditorDialog(
            self.network.component_templates, parent_widget or self)
        dlg.templates_changed.connect(self._on_templates_changed)
        dlg.exec()

    def _on_templates_changed(self, templates):
        self.network.component_templates = templates
        self.network_changed.emit(self.network)

    def _open_network_manager(self):
        if self._network_manager is None:
            self._network_manager = NetworkManagerWindow(self.network, None)
            self._network_manager.network_updated.connect(self._on_network_manager_updated)
        else:
            self._network_manager.set_network(self.network)
        self._network_manager.show()
        self._network_manager.raise_()
        self._network_manager.activateWindow()

    def _sync_network_manager(self):
        if self._network_manager is not None and self._network_manager.isVisible():
            self._network_manager.refresh_from_network()

    def _on_network_manager_updated(self, _network):
        self._refresh_overview_tables()
        if self._current_res:
            self._refresh_res_tables()
        # map markers / links are reconstructed from current network state
        area_map = {a.name: a for a in self.network.areas}
        parts = ["clearMap();"]
        for area in self.network.areas:
            parts.append(f"addBusMarker({json.dumps(area.name)},{area.lat},{area.lon});")
        for ic in self.network.interconnections:
            a0 = area_map.get(ic.area0)
            a1 = area_map.get(ic.area1)
            if a0 and a1:
                parts.append(
                    f"addLinkLayer({json.dumps(ic.name)},"
                    f"{a0.lat},{a0.lon},{a1.lat},{a1.lon});")
        self._run_js("".join(parts))
        self.network_changed.emit(self.network)

    def _find_generator(self, name: str) -> Optional[Generator]:
        for res in self.network.area_res_list:
            for g in res.generators:
                if g.name == name:
                    return g
        return None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def load_network(self, network: NetworkData):
        self.network = network
        if self._network_manager is not None:
            self._network_manager.set_network(network)
        for area in network.areas:
            try:
                self._area_counter = max(self._area_counter, int(area.name.replace("Area", "")))
            except ValueError:
                pass
        # restore currency
        self._currency = "CURRENCY"
        self.network.currency = "CURRENCY"
        self._refresh_currency_headers()
        self._show_overview()
        self._refresh_overview_tables()
        area_map = {a.name: a for a in network.areas}
        parts = ["clearMap();"]
        for area in network.areas:
            parts.append(f"addBusMarker({json.dumps(area.name)},{area.lat},{area.lon});")
        for ic in network.interconnections:
            a0 = area_map.get(ic.area0); a1 = area_map.get(ic.area1)
            if a0 and a1:
                parts.append(
                    f"addLinkLayer({json.dumps(ic.name)},"
                    f"{a0.lat},{a0.lon},{a1.lat},{a1.lon});")
        self._run_js("".join(parts))
        self.network_changed.emit(self.network)

    def get_network(self) -> NetworkData:
        return self.network


# ======================================================================
# Dialogs
# ======================================================================

_OK_CANCEL = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel


class _GenTsDialog(QDialog):
    """時系列データ（p_max_pu CF）を発電機単位で編集するサブダイアログ。"""

    def __init__(self, gen_name: str, carrier: str, values: list, parent=None):
        from .timeseries_editor import _SeriesTab
        super().__init__(parent)
        self.setWindowTitle(self.tr("時系列データ編集: {}  [{}]").format(gen_name, carrier))
        self.resize(1000, 640)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self._gen_name = gen_name
        self._tab = _SeriesTab(
            self.tr("設備利用率 CF"),
            self.tr("設備利用率 (-)"),
            y_max=1.0,
            selector_label=self.tr("発電設備"),
            mode_toggle=True,
        )
        self._tab.set_keys([gen_name])
        if values and len(values) == 8760:
            self._tab.set_data({gen_name: list(values)})
        self._tab.bus_combo.setCurrentText(gen_name)
        layout.addWidget(self._tab)

        btns = QDialogButtonBox(_OK_CANCEL)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_values(self) -> list:
        data = self._tab.get_data()
        return data.get(self._gen_name, [0.0] * 8760)

    def get_mode(self) -> str:
        modes = self._tab.get_mode()
        return modes.get(self._gen_name, "cf")

    def get_fixed_output(self) -> bool:
        fo = self._tab.get_fixed_output()
        return fo.get(self._gen_name, False)


class _LoadTsDialog(QDialog):
    """時系列データ（需要 p_set）を負荷単位で編集するサブダイアログ。"""

    def __init__(self, load_name: str, values: list, parent=None):
        from .timeseries_editor import _SeriesTab
        super().__init__(parent)
        self.setWindowTitle(self.tr("時系列データ編集: {}").format(load_name))
        self.resize(1000, 640)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self._load_name = load_name
        self._tab = _SeriesTab(
            self.tr("需要"),
            self.tr("需要 (MW)"),
            y_max=1e9,
            selector_label=self.tr("負荷"),
        )
        self._tab.set_keys([load_name])
        if values and len(values) == 8760:
            self._tab.set_data({load_name: list(values)})
        self._tab.bus_combo.setCurrentText(load_name)
        layout.addWidget(self._tab)

        btns = QDialogButtonBox(_OK_CANCEL)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_values(self) -> list:
        data = self._tab.get_data()
        return data.get(self._load_name, [0.0] * 8760)


class _FormDialog(QDialog):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        self._layout = QFormLayout(self)

    def _add_buttons(self):
        bb = QDialogButtonBox(_OK_CANCEL)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self._layout.addRow(bb)

    @staticmethod
    def _dspin(lo=0.0, hi=1e9, val=0.0, step=None, decimals=2, suffix="", unit_family=None):
        if unit_family:
            return UnitValueBox(unit_family, lo=lo, hi=hi, val=val, step=step, decimals=decimals)
        s = _AdaptiveSpinBox()
        s.setRange(lo, hi); s.setValue(val); s.setDecimals(decimals)
        if step is not None: s.setSingleStep(step)
        if suffix: s.setSuffix(suffix)
        return s

    @staticmethod
    def _ispin(lo=1900, hi=2200, val=2020):
        s = QSpinBox(); s.setRange(lo, hi); s.setValue(val); return s


class AreaEditDialog(_FormDialog):
    def __init__(self, area: Area, parent=None):
        super().__init__("エリアの編集", parent)
        self.setWindowTitle(self.tr("エリアの編集"))
        self.name_edit    = QLineEdit(area.name)
        self.lat_spin     = self._dspin(-90, 90,   area.lat, step=0.001, decimals=6)
        self.lon_spin     = self._dspin(-180, 180, area.lon, step=0.001, decimals=6)
        self.country_edit = QLineEdit(area.country)
        for lbl, w in [(self.tr("名前:"), self.name_edit), (self.tr("緯度:"), self.lat_spin),
                        (self.tr("経度:"), self.lon_spin), (self.tr("国:"), self.country_edit)]:
            self._layout.addRow(lbl, w)
        self._add_buttons()

    def get_values(self):
        return (self.name_edit.text(), self.lat_spin.value(),
                self.lon_spin.value(), self.country_edit.text())


class GeneratorDialog(_FormDialog):
    _counter = 0

    def __init__(self, areas, parent=None, existing: Generator = None,
                 preset_area: str = None, cur: str = "Currency",
                 ts_values: list = None,
                 generator_carriers: list[str] = None,
                 area_carriers: list[str] = None):
        title = "発電機の編集" if existing else "発電機の追加"
        super().__init__(title, parent)
        self.setWindowTitle(self.tr("発電機の編集") if existing else self.tr("発電機の追加"))
        if not existing:
            GeneratorDialog._counter += 1
        default_name = f"Gen{GeneratorDialog._counter}" if not existing else existing.name
        self._ts_values: list = list(ts_values) if ts_values else [0.0] * 8760
        self._ts_mode: str = "cf"
        self._ts_fixed: bool = False
        self.name_edit     = QLineEdit(default_name)
        self.area_combo    = QComboBox(); self.area_combo.addItems([a.name for a in areas])
        self.carrier_combo = QComboBox(); self.carrier_combo.addItems(generator_carriers or list(CARRIERS))
        self.bus_carrier_combo = QComboBox(); self.bus_carrier_combo.addItems(area_carriers or list(AREA_CARRIERS))
        self.p_nom         = self._dspin(0, 1e9, 100.0, unit_family="power")
        self.ext_chk       = QCheckBox()
        self.p_max         = self._dspin(0, 1e9, 0.0, unit_family="power")
        self.mc            = self._dspin(0, 1e6, 0.0, suffix=f" {cur}/MWh")
        self.cc            = self._dspin(0, 1e9, 0.0, suffix=f" {cur}/MW")
        self.eff           = self._dspin(0.01, 1.0, 0.4, step=0.01, decimals=3)
        self.yr            = self._ispin(val=2020)
        self.p_max_pu      = self._dspin(0.0, 1.0, 1.0, step=0.01, decimals=3)
        self.p_min_pu      = self._dspin(0.0, 1.0, 0.0, step=0.01, decimals=3)
        self.committable   = QCheckBox()
        self.min_up_time   = self._ispin(lo=0, hi=8760, val=0)
        self.ramp_limit_up = self._dspin(0.0, 1.0, 1.0, step=0.01, decimals=3)
        self.ramp_limit_dn = self._dspin(0.0, 1.0, 1.0, step=0.01, decimals=3)
        self.btn_ts_edit   = QPushButton(self.tr("時系列を編集…"))
        self.btn_ts_edit.clicked.connect(self._open_ts_dialog)
        for lbl, w in [(self.tr("名前:"), self.name_edit), (self.tr("エリア:"), self.area_combo),
                (self.tr("種別:"), self.carrier_combo), (self.tr("接続バス:"), self.bus_carrier_combo),
                (self.tr("設備容量:"), self.p_nom),
                        (self.tr("拡張可能:"), self.ext_chk), (self.tr("最大容量:"), self.p_max),
                        (self.tr("変動費:"), self.mc), (self.tr("建設費:"), self.cc),
                        (self.tr("効率:"), self.eff), (self.tr("建設年:"), self.yr),
                        ("p_max_pu:", self.p_max_pu), ("p_min_pu:", self.p_min_pu),
                        (self.tr("コミットメント:"), self.committable),
                        (self.tr("最低運転時間(h):"), self.min_up_time),
                        ("ramp_limit_up:", self.ramp_limit_up),
                        ("ramp_limit_down:", self.ramp_limit_dn),
                        (self.tr("時系列データ:"), self.btn_ts_edit)]:
            self._layout.addRow(lbl, w)
        self._add_buttons()
        if preset_area and preset_area in [a.name for a in areas]:
            self.area_combo.setCurrentText(preset_area)
        if existing:
            self._prefill(existing)

    def _prefill(self, g: Generator):
        self.name_edit.setText(g.name)
        self.area_combo.setCurrentText(g.area)
        self.carrier_combo.setCurrentText(g.carrier)
        self.bus_carrier_combo.setCurrentText(g.bus_carrier)
        self.p_nom.setValue(g.p_nom)
        self.ext_chk.setChecked(g.p_nom_extendable)
        self.p_max.setValue(g.p_nom_max)
        self.mc.setValue(g.marginal_cost)
        self.cc.setValue(g.capital_cost)
        self.eff.setValue(g.efficiency)
        self.yr.setValue(g.build_year)
        self.p_max_pu.setValue(g.p_max_pu)
        self.p_min_pu.setValue(g.p_min_pu)
        self.committable.setChecked(g.committable)
        self.min_up_time.setValue(g.min_up_time)
        self.ramp_limit_up.setValue(g.ramp_limit_up)
        self.ramp_limit_dn.setValue(g.ramp_limit_down)

    def get_generator(self):
        return Generator(
            name=self.name_edit.text(), area=self.area_combo.currentText(),
            carrier=self.carrier_combo.currentText(), bus_carrier=self.bus_carrier_combo.currentText(),
            p_nom=self.p_nom.value(),
            p_nom_extendable=self.ext_chk.isChecked(), p_nom_max=self.p_max.value(),
            marginal_cost=self.mc.value(), capital_cost=self.cc.value(),
            efficiency=self.eff.value(), build_year=self.yr.value(),
            p_max_pu=self.p_max_pu.value(), p_min_pu=self.p_min_pu.value(),
            committable=self.committable.isChecked(),
            min_up_time=self.min_up_time.value(),
            ramp_limit_up=self.ramp_limit_up.value(),
            ramp_limit_down=self.ramp_limit_dn.value(),
        )

    def _open_ts_dialog(self):
        gen_name = self.name_edit.text() or "Generator"
        carrier  = self.carrier_combo.currentText()
        dlg = _GenTsDialog(gen_name, carrier, self._ts_values, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._ts_values = dlg.get_values()
            self._ts_mode   = dlg.get_mode()
            self._ts_fixed  = dlg.get_fixed_output()

    def get_ts_values(self) -> list:
        return self._ts_values

    def get_ts_mode(self) -> str:
        return self._ts_mode

    def get_ts_fixed(self) -> bool:
        return self._ts_fixed


class InterconnectionDialog(_FormDialog):
    _counter = 0

    def __init__(self, areas, parent=None, existing: Interconnection = None,
                 preset_area0: str = None, preset_area1: str = None, cur: str = "Currency",
                 area_carriers: list[str] = None):
        title = "連系線の編集" if existing else "連系線の追加"
        super().__init__(title, parent)
        self.setWindowTitle(self.tr("連系線の編集") if existing else self.tr("連系線の追加"))
        if not existing:
            InterconnectionDialog._counter += 1
        default_name = f"IC{InterconnectionDialog._counter}" if not existing else existing.name
        names = [a.name for a in areas]
        self.name_edit = QLineEdit(default_name)
        self.a0_combo  = QComboBox(); self.a0_combo.addItems(names)
        self.a1_combo  = QComboBox(); self.a1_combo.addItems(names)
        if preset_area0 and preset_area0 in names:
            self.a0_combo.setCurrentText(preset_area0)
        if preset_area1 and preset_area1 in names:
            self.a1_combo.setCurrentText(preset_area1)
        elif len(names) > 1 and not existing and not preset_area1:
            self.a1_combo.setCurrentIndex(1)
        self.carrier_combo = QComboBox(); self.carrier_combo.addItems([""] + (area_carriers or list(AREA_CARRIERS)))
        self.eff  = self._dspin(0.01, 1.0, 1.0, step=0.01, decimals=3)
        self.pnom = self._dspin(0, 1e9, 1000.0, unit_family="power")
        self.prev = self._dspin(0, 1e9, 0.0, unit_family="power")
        self.ext  = QCheckBox()
        self.cc   = self._dspin(0, 1e9, 0.0, suffix=f" {cur}/MW")
        self.mc   = self._dspin(0, 1e6, 0.0, suffix=f" {cur}/MWh")
        self.yr   = self._ispin(val=2020)
        for lbl, w in [(self.tr("名前:"), self.name_edit), (self.tr("エリア0:"), self.a0_combo),
                        (self.tr("エリア1:"), self.a1_combo), (self.tr("種別:"), self.carrier_combo),
                        (self.tr("効率:"), self.eff),
                        (self.tr("容量(順方向):"), self.pnom), (self.tr("容量(逆方向):"), self.prev),
                        (self.tr("拡張可能:"), self.ext),
                        (self.tr("建設費:"), self.cc), (self.tr("変動費:"), self.mc),
                        (self.tr("建設年:"), self.yr)]:
            self._layout.addRow(lbl, w)
        self._add_buttons()
        if existing:
            self._prefill(existing)

    def _prefill(self, ic: Interconnection):
        self.name_edit.setText(ic.name)
        self.a0_combo.setCurrentText(ic.area0)
        self.a1_combo.setCurrentText(ic.area1)
        self.carrier_combo.setCurrentText(ic.carrier)
        self.eff.setValue(ic.efficiency)
        self.pnom.setValue(ic.p_nom)
        self.prev.setValue(ic.p_nom_reverse)
        self.ext.setChecked(ic.p_nom_extendable)
        self.cc.setValue(ic.capital_cost)
        self.mc.setValue(ic.marginal_cost)
        self.yr.setValue(ic.build_year)

    def get_interconnection(self):
        return Interconnection(
            name=self.name_edit.text(), area0=self.a0_combo.currentText(),
            area1=self.a1_combo.currentText(),
            carrier=self.carrier_combo.currentText(),
            efficiency=self.eff.value(),
            p_nom=self.pnom.value(), p_nom_reverse=self.prev.value(),
            p_nom_extendable=self.ext.isChecked(),
            capital_cost=self.cc.value(), marginal_cost=self.mc.value(),
            build_year=self.yr.value(),
        )


class LoadDialog(_FormDialog):
    _counter = 0

    def __init__(self, areas, parent=None, existing: Load = None,
                 preset_area: str = None,
                 area_carriers: list[str] = None,
                 ts_values: list = None):
        title = "負荷の編集" if existing else "負荷の追加"
        super().__init__(title, parent)
        self.setWindowTitle(self.tr("負荷の編集") if existing else self.tr("負荷の追加"))
        if not existing:
            LoadDialog._counter += 1
        default_name = f"Load{LoadDialog._counter}" if not existing else existing.name
        self._ts_values: list = list(ts_values) if ts_values else [0.0] * 8760
        self.name_edit  = QLineEdit(default_name)
        self.area_combo = QComboBox(); self.area_combo.addItems([a.name for a in areas])
        self.bus_carrier_combo = QComboBox(); self.bus_carrier_combo.addItems(area_carriers or list(AREA_CARRIERS))
        self.p_set      = self._dspin(0, 1e9, 100.0, unit_family="power")
        self.btn_ts_edit = QPushButton(self.tr("時系列を編集…"))
        self.btn_ts_edit.clicked.connect(self._open_ts_dialog)
        for lbl, w in [(self.tr("名前:"), self.name_edit), (self.tr("エリア:"), self.area_combo),
                (self.tr("バスキャリア:"), self.bus_carrier_combo), (self.tr("需要:"), self.p_set),
                (self.tr("時系列データ:"), self.btn_ts_edit)]:
            self._layout.addRow(lbl, w)
        self._add_buttons()
        if preset_area and preset_area in [a.name for a in areas]:
            self.area_combo.setCurrentText(preset_area)
        if existing:
            self.name_edit.setText(existing.name)
            self.area_combo.setCurrentText(existing.area)
            self.bus_carrier_combo.setCurrentText(existing.bus_carrier)
            self.p_set.setValue(existing.p_set)

    def get_load(self):
        return Load(name=self.name_edit.text(),
                    area=self.area_combo.currentText(),
                    bus_carrier=self.bus_carrier_combo.currentText(),
                    p_set=self.p_set.value())

    def _open_ts_dialog(self):
        load_name = self.name_edit.text() or "Load"
        dlg = _LoadTsDialog(load_name, self._ts_values, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._ts_values = dlg.get_values()

    def get_ts_values(self) -> list:
        return self._ts_values


class StoreDialog(_FormDialog):
    _counter = 0

    def __init__(self, areas, parent=None, existing: Store = None,
                 preset_area: str = None,
                 area_carriers: list[str] = None):
        title = "貯蔵の編集" if existing else "貯蔵の追加"
        super().__init__(title, parent)
        self.setWindowTitle(self.tr("貯蔵の編集") if existing else self.tr("貯蔵の追加"))
        if not existing:
            StoreDialog._counter += 1
        default_name = f"Store{StoreDialog._counter}" if not existing else existing.name
        self.name_edit    = QLineEdit(default_name)
        self.area_combo   = QComboBox(); self.area_combo.addItems([a.name for a in areas])
        self.e_nom        = self._dspin(0, 1e12, 0.0, unit_family="energy")
        self.carrier_edit = QComboBox()
        self.carrier_edit.setEditable(True)
        self.carrier_edit.addItems([""] + (area_carriers or list(AREA_CARRIERS)))
        for lbl, w in [(self.tr("名前:"), self.name_edit), (self.tr("エリア:"), self.area_combo),
                        (self.tr("エネルギー容量:"), self.e_nom), (self.tr("種別:"), self.carrier_edit)]:
            self._layout.addRow(lbl, w)
        self._add_buttons()
        if preset_area and preset_area in [a.name for a in areas]:
            self.area_combo.setCurrentText(preset_area)
        if existing:
            self.name_edit.setText(existing.name)
            self.area_combo.setCurrentText(existing.area)
            self.e_nom.setValue(existing.e_nom)
            self.carrier_edit.setCurrentText(existing.carrier)

    def get_store(self):
        return Store(
            name=self.name_edit.text(),
            area=self.area_combo.currentText(),
            e_nom=self.e_nom.value(),
            carrier=self.carrier_edit.currentText(),
        )


class PumpedHydroDialog(_FormDialog):
    _counter = 0

    def __init__(self, areas, parent=None, existing: PumpedHydro = None,
                 preset_area: str = None, cur: str = "Currency"):
        title = "揚水発電所の編集" if existing else "揚水発電所の追加"
        super().__init__(title, parent)
        self.setWindowTitle(self.tr("揚水発電所の編集") if existing else self.tr("揚水発電所の追加"))
        if not existing:
            PumpedHydroDialog._counter += 1
        default_name = f"PumpedHydro{PumpedHydroDialog._counter}" if not existing else existing.name
        self.name_edit   = QLineEdit(default_name)
        self.area_combo  = QComboBox(); self.area_combo.addItems([a.name for a in areas])
        self.p_turbine   = self._dspin(0, 1e9, 100.0, unit_family="power")
        self.eff_turbine = self._dspin(0.01, 1.0, 0.9, step=0.01, decimals=3)
        self.p_pump      = self._dspin(0, 1e9, 100.0, unit_family="power")
        self.eff_pump    = self._dspin(0.01, 1.0, 0.85, step=0.01, decimals=3)
        self.e_nom       = self._dspin(0, 1e12, 0.0, unit_family="energy")
        self.ext_chk     = QCheckBox()
        self.cc          = self._dspin(0, 1e9, 0.0, suffix=f" {cur}/MW")
        self.mc          = self._dspin(0, 1e6, 0.0, suffix=f" {cur}/MWh")
        self.yr          = self._ispin(val=2020)
        for lbl, w in [(self.tr("名前:"), self.name_edit), (self.tr("ACエリア:"), self.area_combo),
                        (self.tr("タービン容量:"), self.p_turbine), (self.tr("タービン効率:"), self.eff_turbine),
                        (self.tr("ポンプ容量:"), self.p_pump), (self.tr("ポンプ効率:"), self.eff_pump),
                        (self.tr("貯水容量:"), self.e_nom), (self.tr("拡張可能:"), self.ext_chk),
                        (self.tr("建設費:"), self.cc), (self.tr("変動費:"), self.mc),
                        (self.tr("建設年:"), self.yr)]:
            self._layout.addRow(lbl, w)
        self._add_buttons()
        if preset_area and preset_area in [a.name for a in areas]:
            self.area_combo.setCurrentText(preset_area)
        if existing:
            self._prefill(existing)

    def _prefill(self, ph: PumpedHydro):
        self.name_edit.setText(ph.name)
        self.area_combo.setCurrentText(ph.ac_area)
        self.p_turbine.setValue(ph.p_nom_turbine)
        self.eff_turbine.setValue(ph.efficiency_turbine)
        self.p_pump.setValue(ph.p_nom_pump)
        self.eff_pump.setValue(ph.efficiency_pump)
        self.e_nom.setValue(ph.e_nom)
        self.ext_chk.setChecked(ph.p_nom_extendable)
        self.cc.setValue(ph.capital_cost)
        self.mc.setValue(ph.marginal_cost)
        self.yr.setValue(ph.build_year)

    def get_pumped_hydro(self):
        return PumpedHydro(
            name=self.name_edit.text(),
            ac_area=self.area_combo.currentText(),
            p_nom_turbine=self.p_turbine.value(),
            efficiency_turbine=self.eff_turbine.value(),
            p_nom_pump=self.p_pump.value(),
            efficiency_pump=self.eff_pump.value(),
            e_nom=self.e_nom.value(),
            p_nom_extendable=self.ext_chk.isChecked(),
            capital_cost=self.cc.value(),
            marginal_cost=self.mc.value(),
            build_year=self.yr.value(),
        )


class ConverterDialog(_FormDialog):
    _counter = 0

    def __init__(self, areas, parent=None, existing: Converter = None,
                 preset_area: str = None, cur: str = "Currency",
                 multi_carriers: list[str] = None):
        title = "変換器の編集" if existing else "変換器の追加"
        super().__init__(title, parent)
        self.setWindowTitle(self.tr("変換器の編集") if existing else self.tr("変換器の追加"))
        if not existing:
            ConverterDialog._counter += 1
        default_name = f"Conv{ConverterDialog._counter}" if not existing else existing.name

        carriers = multi_carriers or ["AC", "heat", "hydrogen", "gas"]
        self.name_edit          = QLineEdit(default_name)
        self.area_combo         = QComboBox(); self.area_combo.addItems([a.name for a in areas])
        self.preset_combo       = QComboBox()
        self.preset_combo.addItems(["(カスタム)"] + list(CONVERTER_PRESETS.keys()))
        self.carrier_in_combo   = QComboBox(); self.carrier_in_combo.addItems(carriers)
        self.carrier_out_combo  = QComboBox(); self.carrier_out_combo.addItems(carriers)
        self.carrier_out2_combo = QComboBox()
        self.carrier_out2_combo.addItems(["(なし)"] + carriers)
        self.eff   = self._dspin(0.01, 1.0, 0.9, step=0.01, decimals=3)
        self.eff2  = self._dspin(0.0,  1.0, 0.0, step=0.01, decimals=3)
        self.p_nom = self._dspin(0, 1e9, 100.0, unit_family="power")
        self.ext_chk = QCheckBox()
        self.p_max = self._dspin(0, 1e9, 0.0, unit_family="power")
        self.mc    = self._dspin(0, 1e6, 0.0, suffix=f" {cur}/MWh")
        self.cc    = self._dspin(0, 1e9, 0.0, suffix=f" {cur}/MW")
        self.yr    = self._ispin(val=2020)

        for lbl, w in [
            (self.tr("名前:"), self.name_edit), (self.tr("エリア:"), self.area_combo),
            (self.tr("プリセット:"), self.preset_combo),
            (self.tr("入力キャリア:"), self.carrier_in_combo),
            (self.tr("出力キャリア1:"), self.carrier_out_combo),
            (self.tr("出力キャリア2:"), self.carrier_out2_combo),
            (self.tr("効率1:"), self.eff), (self.tr("効率2 (CHP用):"), self.eff2),
            (self.tr("容量:"), self.p_nom), (self.tr("拡張可能:"), self.ext_chk),
            (self.tr("最大容量:"), self.p_max), (self.tr("変動費:"), self.mc),
            (self.tr("建設費:"), self.cc), (self.tr("建設年:"), self.yr),
        ]:
            self._layout.addRow(lbl, w)
        self._add_buttons()

        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        if preset_area and preset_area in [a.name for a in areas]:
            self.area_combo.setCurrentText(preset_area)
        if existing:
            self._prefill(existing)

    def _on_preset_changed(self, name: str):
        preset = CONVERTER_PRESETS.get(name)
        if not preset:
            return
        self.carrier_in_combo.setCurrentText(preset["carrier_in"])
        self.carrier_out_combo.setCurrentText(preset["carrier_out"])
        out2 = preset.get("carrier_out2", "")
        self.carrier_out2_combo.setCurrentText(out2 if out2 else "(なし)")

    def _prefill(self, conv: Converter):
        self.name_edit.setText(conv.name)
        self.area_combo.setCurrentText(conv.area)
        self.carrier_in_combo.setCurrentText(conv.carrier_in)
        self.carrier_out_combo.setCurrentText(conv.carrier_out)
        self.carrier_out2_combo.setCurrentText(
            conv.carrier_out2 if conv.carrier_out2 else "(なし)")
        self.eff.setValue(conv.efficiency)
        self.eff2.setValue(conv.efficiency2)
        self.p_nom.setValue(conv.p_nom)
        self.ext_chk.setChecked(conv.p_nom_extendable)
        self.p_max.setValue(conv.p_nom_max)
        self.mc.setValue(conv.marginal_cost)
        self.cc.setValue(conv.capital_cost)
        self.yr.setValue(conv.build_year)

    def get_converter(self) -> Converter:
        out2 = self.carrier_out2_combo.currentText()
        return Converter(
            name=self.name_edit.text(),
            area=self.area_combo.currentText(),
            carrier_in=self.carrier_in_combo.currentText(),
            carrier_out=self.carrier_out_combo.currentText(),
            carrier_out2="" if out2 == "(なし)" else out2,
            efficiency=self.eff.value(),
            efficiency2=self.eff2.value(),
            p_nom=self.p_nom.value(),
            p_nom_extendable=self.ext_chk.isChecked(),
            p_nom_max=self.p_max.value(),
            marginal_cost=self.mc.value(),
            capital_cost=self.cc.value(),
            build_year=self.yr.value(),
        )
