"""Node-graph widget for visual PyPSA component template editing.

Nodes represent SubComponentDef items (Bus / Store / Link / Generator) or
fixed area-bus anchors.  Edges connect a component's bus-slot port to a
Bus node's connection port, encoding the bus_connections mapping visually.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable

from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsEllipseItem, QGraphicsPathItem,
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMenu,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPainterPath, QPen, QBrush, QColor, QFont, QTransform,
)

from .models import SubComponentDef, MULTI_CARRIERS

# ── Palette ────────────────────────────────────────────────────────────
_NODE_COLORS: Dict[str, QColor] = {
    "Bus":       QColor("#2980b9"),
    "Store":     QColor("#1abc9c"),
    "Link":      QColor("#e67e22"),
    "Generator": QColor("#27ae60"),
}
_BUS_CARRIER_COLORS: Dict[str, QColor] = {
    "AC":       QColor("#2980b9"),
    "heat":     QColor("#e74c3c"),
    "hydrogen": QColor("#00acc1"),
    "gas":      QColor("#f39c12"),
    "other":    QColor("#95a5a6"),
}
_EXT_COLOR    = QColor("#8e44ad")
_SEL_COLOR    = QColor("#f39c12")
_EDGE_COLOR   = QColor("#7f8c8d")
_DRAG_COLOR   = QColor("#3498db")

PORT_R   = 9.0
NODE_W   = 170
TITLE_H  = 26
PORT_GAP = 26


# ══════════════════════════════════════════════════════════════════════
# Port
# ══════════════════════════════════════════════════════════════════════
class PortItem(QGraphicsEllipseItem):
    """Draggable connection handle on a node."""

    def __init__(self, slot_name: str, owner: QGraphicsItem):
        r = PORT_R
        super().__init__(-r, -r, r * 2, r * 2, owner)
        self.slot_name = slot_name
        self.owner     = owner          # NodeItem or ExternalBusItem
        self.edges: List[EdgeItem] = []
        self.setZValue(20)
        self.setAcceptHoverEvents(True)
        self._normal()

    # ── style helpers ─────────────────────────────────────────────────
    def _normal(self):
        self.setBrush(QBrush(QColor("#ecf0f1")))
        self.setPen(QPen(QColor("#7f8c8d"), 1.5))

    def _hover(self):
        self.setBrush(QBrush(QColor("#f39c12")))
        self.setPen(QPen(QColor("#e67e22"), 2.0))

    def hoverEnterEvent(self, e):
        self._hover(); super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        self._normal(); super().hoverLeaveEvent(e)

    def scene_center(self) -> QPointF:
        return self.mapToScene(QPointF(0, 0))

    # ── edge drag ─────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            sc = self.scene()
            if isinstance(sc, NodeGraphScene):
                sc._start_drag(self, e.scenePos())
            self.grabMouse()          # capture all move/release until button up
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        sc = self.scene()
        if isinstance(sc, NodeGraphScene) and sc._drag_port is self:
            sc._update_drag(e.scenePos())
        e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.ungrabMouse()        # release capture first
            sc = self.scene()
            if isinstance(sc, NodeGraphScene):
                sc._end_drag(e.scenePos())
            e.accept()
        else:
            super().mouseReleaseEvent(e)

    def disconnect_all(self):
        for edge in list(self.edges):
            edge.remove()


# ══════════════════════════════════════════════════════════════════════
# Node  (SubComponentDef)
# ══════════════════════════════════════════════════════════════════════
class NodeItem(QGraphicsItem):
    """Visual node for a SubComponentDef."""

    def __init__(self, sub: SubComponentDef):
        super().__init__()
        self.sub = sub
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(5)
        self._ports: Dict[str, PortItem] = {}
        self._build_ports()
        self.setPos(sub.pos_x, sub.pos_y)

    # ── port layout ───────────────────────────────────────────────────
    def _slot_names(self) -> List[str]:
        ct = self.sub.component_type
        if ct == "Bus":
            return ["conn"]
        if ct == "Store":
            return ["bus"]
        if ct == "Generator":
            return ["bus"]
        if ct == "Link":
            return ["bus0", "bus1", "bus2"]
        return []

    def _build_ports(self):
        self._ports.clear()
        for child in self.childItems():
            if isinstance(child, PortItem):
                child.setParentItem(None)

        names = self._slot_names()
        for i, name in enumerate(names):
            port = PortItem(name, self)
            x = NODE_W / 2 if self.sub.component_type == "Bus" else 0
            y = TITLE_H + 8 + i * PORT_GAP + PORT_GAP / 2
            port.setPos(x, y)
            self._ports[name] = port

    def port(self, slot_name: str) -> Optional[PortItem]:
        return self._ports.get(slot_name)

    def all_ports(self) -> Dict[str, PortItem]:
        return self._ports

    def _height(self) -> float:
        n = max(len(self._ports), 1)
        return TITLE_H + 12 + n * PORT_GAP

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, NODE_W, self._height())

    # ── color ─────────────────────────────────────────────────────────
    def _color(self) -> QColor:
        ct = self.sub.component_type
        if ct == "Bus":
            carrier = self.sub.fixed_params.get("carrier", "other")
            return _BUS_CARRIER_COLORS.get(carrier, _BUS_CARRIER_COLORS["other"])
        return _NODE_COLORS.get(ct, QColor("#95a5a6"))

    # ── paint ─────────────────────────────────────────────────────────
    def paint(self, painter: QPainter, option, widget=None):
        h = self._height()
        color = self._color()
        sel   = self.isSelected()

        # drop-shadow
        painter.setBrush(QBrush(QColor(0, 0, 0, 35)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(3, 3, NODE_W, h), 7, 7)

        # body
        painter.setBrush(QBrush(color.lighter(185)))
        painter.setPen(QPen(_SEL_COLOR if sel else color.darker(120), 2.0 if sel else 1.0))
        painter.drawRoundedRect(QRectF(0, 0, NODE_W, h), 7, 7)

        # title bar
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(QRectF(0, 0, NODE_W, TITLE_H + 6), 7, 7)
        painter.drawRect(QRectF(0, TITLE_H - 2, NODE_W, 8))

        # title text
        font = QFont(); font.setBold(True); font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QPen(Qt.GlobalColor.white))
        painter.drawText(QRectF(8, 0, NODE_W - 16, TITLE_H),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         self.sub.component_type)

        # name template
        font.setBold(False); font.setPointSize(7)
        painter.setFont(font)
        painter.setPen(QPen(color.darker(170)))
        painter.drawText(QRectF(8, TITLE_H + 2, NODE_W - 16, 18),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self.sub.name_template or f"[{self.sub.sub_id}]")

        # port labels
        font.setPointSize(6); painter.setFont(font)
        painter.setPen(QPen(color.darker(160)))
        is_bus = self.sub.component_type == "Bus"
        for slot, port in self._ports.items():
            px, py = port.x(), port.y()
            if is_bus:
                painter.drawText(QRectF(px - 58, py - 8, 50, 16),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                                 slot)
            else:
                painter.drawText(QRectF(px + PORT_R + 3, py - 8, 55, 16),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 slot)

    # ── position persistence ──────────────────────────────────────────
    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.sub.pos_x = self.x()
            self.sub.pos_y = self.y()
            for p in self._ports.values():
                for e in p.edges:
                    e.update_path()
        return super().itemChange(change, value)


# ══════════════════════════════════════════════════════════════════════
# External Bus anchor
# ══════════════════════════════════════════════════════════════════════
class ExternalBusItem(QGraphicsItem):
    """Fixed anchor representing an existing area bus (area:AC, area:hydrogen …)."""

    def __init__(self, carrier: str):
        super().__init__()
        self.carrier = carrier
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(5)

        self._port = PortItem("conn", self)
        self._port.setPos(NODE_W / 2, 32)

    def port(self, _="conn") -> PortItem:
        return self._port

    def all_ports(self) -> Dict[str, PortItem]:
        return {"conn": self._port}

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, NODE_W, 64)

    def _color(self) -> QColor:
        return _BUS_CARRIER_COLORS.get(self.carrier, _EXT_COLOR)

    def paint(self, painter: QPainter, option, widget=None):
        color = self._color()
        painter.setBrush(QBrush(QColor(0, 0, 0, 30)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(3, 3, NODE_W, 64), 9, 9)

        painter.setBrush(QBrush(color.lighter(155)))
        painter.setPen(QPen(color, 2))
        painter.drawRoundedRect(QRectF(0, 0, NODE_W, 64), 9, 9)

        font = QFont(); font.setBold(True); font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QPen(color.darker(160)))
        painter.drawText(QRectF(0, 0, NODE_W, 36),
                         Qt.AlignmentFlag.AlignCenter,
                         f"area:{self.carrier}")
        font.setBold(False); font.setPointSize(7); painter.setFont(font)
        painter.drawText(QRectF(0, 36, NODE_W, 20),
                         Qt.AlignmentFlag.AlignCenter, "(エリアバス)")

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for e in self._port.edges:
                e.update_path()
        return super().itemChange(change, value)


# ══════════════════════════════════════════════════════════════════════
# Edge
# ══════════════════════════════════════════════════════════════════════
class EdgeItem(QGraphicsPathItem):
    """Bezier curve connecting two PortItems."""

    def __init__(self, pa: PortItem, pb: PortItem):
        super().__init__()
        self.pa = pa
        self.pb = pb
        pa.edges.append(self)
        pb.edges.append(self)
        self.setZValue(1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setPen(QPen(_EDGE_COLOR, 2.0, Qt.PenStyle.SolidLine,
                         Qt.PenCapStyle.RoundCap))
        self.update_path()

    def update_path(self):
        a = self.pa.scene_center()
        b = self.pb.scene_center()
        dx = max(abs(b.x() - a.x()) * 0.55, 30)
        path = QPainterPath(a)
        path.cubicTo(a.x() + dx, a.y(), b.x() - dx, b.y(), b.x(), b.y())
        self.setPath(path)

    def paint(self, painter, option, widget=None):
        self.setPen(QPen(_SEL_COLOR if self.isSelected() else _EDGE_COLOR,
                         2.5 if self.isSelected() else 2.0))
        super().paint(painter, option, widget)

    def remove(self):
        self.pa.edges.remove(self)
        self.pb.edges.remove(self)
        if self.scene():
            self.scene().removeItem(self)


# ══════════════════════════════════════════════════════════════════════
# Scene
# ══════════════════════════════════════════════════════════════════════
class NodeGraphScene(QGraphicsScene):
    """Manages nodes, edges and connection-drag logic."""

    graph_changed = pyqtSignal()
    node_selected = pyqtSignal(object)   # SubComponentDef | None
    delete_node_requested = pyqtSignal(str)  # sub_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes: Dict[str, NodeItem]         = {}
        self._ext:   Dict[str, ExternalBusItem]  = {}
        self._edges: List[EdgeItem]              = []
        self._drag_port: Optional[PortItem]      = None
        self._drag_line: Optional[QGraphicsPathItem] = None
        self.selectionChanged.connect(self._on_sel_changed)

    # ── background grid ───────────────────────────────────────────────
    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, QColor("#f8f8f8"))
        gs = 20
        pen = QPen(QColor("#e0e0e0"), 0.5)
        painter.setPen(pen)
        lx = int(rect.left())  - (int(rect.left())  % gs)
        ty = int(rect.top())   - (int(rect.top())   % gs)
        x = lx
        while x < rect.right():
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
            x += gs
        y = ty
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
            y += gs

    # ── public: build from template ───────────────────────────────────
    def load_template(self, template):
        self.clear()
        self._nodes.clear()
        self._ext.clear()
        self._edges.clear()
        if template is None:
            return

        for sub in template.sub_components:
            self._add_node_item(sub)

        # external buses referenced
        for sub in template.sub_components:
            for ref in sub.bus_connections.values():
                if ref.startswith("area:"):
                    self._ensure_ext(ref[5:])

        # reconstruct edges
        for sub in template.sub_components:
            for slot, ref in sub.bus_connections.items():
                self._draw_edge_from_ref(sub.sub_id, slot, ref)

    # ── public: node management ───────────────────────────────────────
    def add_sub(self, sub: SubComponentDef) -> NodeItem:
        node = self._add_node_item(sub)
        self.graph_changed.emit()
        return node

    def remove_sub(self, sub_id: str):
        node = self._nodes.pop(sub_id, None)
        if node:
            for p in node.all_ports().values():
                p.disconnect_all()
            self.removeItem(node)
        self.graph_changed.emit()

    def add_ext_bus(self, carrier: str) -> ExternalBusItem:
        return self._ensure_ext(carrier)

    def remove_ext_bus(self, carrier: str):
        item = self._ext.pop(carrier, None)
        if item:
            item._port.disconnect_all()
            self.removeItem(item)

    # ── validation ────────────────────────────────────────────────────
    def validate(self) -> List[str]:
        errors: List[str] = []
        required_slots = {"Store": ["bus"], "Generator": ["bus"],
                          "Link": ["bus0", "bus1"]}
        for sub_id, node in self._nodes.items():
            ct = node.sub.component_type
            for slot in required_slots.get(ct, []):
                if slot not in node.sub.bus_connections:
                    errors.append(
                        f"「{node.sub.name_template}」の {slot} ポートが未接続です")

        # carrier compatibility warning
        for edge in self._edges:
            bp, sp = self._classify(edge.pa, edge.pb)
            if bp is None:
                continue
            bus_node = bp.owner
            slot_node = sp.owner
            if not isinstance(bus_node, (NodeItem, ExternalBusItem)):
                continue
            bus_carrier = (bus_node.carrier if isinstance(bus_node, ExternalBusItem)
                           else bus_node.sub.fixed_params.get("carrier", ""))
            if isinstance(slot_node, NodeItem):
                gen_carrier = slot_node.sub.fixed_params.get("carrier", "")
                if gen_carrier and bus_carrier and gen_carrier != bus_carrier:
                    errors.append(
                        f"「{slot_node.sub.name_template}」のキャリア({gen_carrier})"
                        f"がバスのキャリア({bus_carrier})と不一致です")
        return errors

    # ── selection signal ──────────────────────────────────────────────
    def _on_sel_changed(self):
        for item in self.selectedItems():
            if isinstance(item, NodeItem):
                self.node_selected.emit(item.sub)
                return
        self.node_selected.emit(None)

    # ── drag helpers ──────────────────────────────────────────────────
    def _start_drag(self, port: PortItem, pos: QPointF):
        self._drag_port = port
        self._drag_line = QGraphicsPathItem()
        self._drag_line.setPen(
            QPen(_DRAG_COLOR, 2.0, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap))
        self._drag_line.setZValue(100)
        self._snap_target: Optional[PortItem] = None
        self.addItem(self._drag_line)
        self._update_drag(pos)

    def _update_drag(self, pos: QPointF):
        if not (self._drag_line and self._drag_port):
            return

        # 接続可能なポートのみスナップ対象にする
        SNAP_R = 24.0
        new_snap: Optional[PortItem] = None
        best_dist = SNAP_R + 1.0
        rect = QRectF(pos.x() - SNAP_R, pos.y() - SNAP_R, SNAP_R * 2, SNAP_R * 2)
        for item in self.items(rect):
            if not isinstance(item, PortItem) or item is self._drag_port:
                continue
            # バス↔スロットの組み合わせのみスナップ可
            if self._classify(self._drag_port, item)[0] is None:
                continue
            sc = item.scene_center()
            dist = ((sc.x() - pos.x()) ** 2 + (sc.y() - pos.y()) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                new_snap = item

        # Update highlight state
        old_snap = getattr(self, "_snap_target", None)
        if old_snap is not new_snap:
            if old_snap:
                old_snap._normal()
            if new_snap:
                new_snap._hover()
            self._snap_target = new_snap

        # Draw bezier to snap target center if snapping, else to cursor
        a = self._drag_port.scene_center()
        b = new_snap.scene_center() if new_snap else pos
        dx = max(abs(b.x() - a.x()) * 0.55, 30)
        path = QPainterPath(a)
        path.cubicTo(a.x() + dx, a.y(), b.x() - dx, b.y(), b.x(), b.y())
        self._drag_line.setPath(path)
        pen_color = QColor("#2ecc71") if new_snap else _DRAG_COLOR
        self._drag_line.setPen(
            QPen(pen_color, 2.5 if new_snap else 2.0,
                 Qt.PenStyle.SolidLine if new_snap else Qt.PenStyle.DashLine,
                 Qt.PenCapStyle.RoundCap))

    def _end_drag(self, pos: QPointF):
        src = self._drag_port
        if self._drag_line:
            self.removeItem(self._drag_line)
            self._drag_line = None
        self._drag_port = None
        # Clear snap highlight
        snap = getattr(self, "_snap_target", None)
        if snap:
            snap._normal()
            self._snap_target = None
        if src is None:
            return
        # Find nearest PortItem within snap radius
        SNAP_R = 24.0
        target: Optional[PortItem] = None
        best_dist = SNAP_R + 1.0
        rect = QRectF(pos.x() - SNAP_R, pos.y() - SNAP_R, SNAP_R * 2, SNAP_R * 2)
        for item in self.items(rect):
            if not isinstance(item, PortItem) or item is src:
                continue
            sc = item.scene_center()
            dist = ((sc.x() - pos.x()) ** 2 + (sc.y() - pos.y()) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                target = item
        if target:
            self._try_add_edge(src, target)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            item = self.itemAt(e.scenePos(), QTransform())
            # PortItem はノードの子アイテムなので親を取得
            if isinstance(item, PortItem):
                item = item.parentItem()
            if isinstance(item, EdgeItem):
                self._remove_edge(item)
                e.accept()
                return
            if isinstance(item, (NodeItem, ExternalBusItem)):
                self._show_item_context_menu(item, e.screenPos())
                e.accept()
                return
        super().mousePressEvent(e)

    def _show_item_context_menu(self, item, global_pos):
        menu = QMenu()
        del_act = menu.addAction("削除")
        act = menu.exec(global_pos)
        if act == del_act:
            if isinstance(item, NodeItem):
                self.delete_node_requested.emit(item.sub.sub_id)
            elif isinstance(item, ExternalBusItem):
                self.remove_ext_bus(item.carrier)

    def mouseReleaseEvent(self, e):
        # Deliver to PortItem (or whichever grabber) FIRST, then clean up any
        # leftover drag state that the item didn't handle (e.g. grab lost).
        super().mouseReleaseEvent(e)
        if e.button() == Qt.MouseButton.LeftButton:
            if self._drag_port is not None or self._drag_line is not None:
                if self._drag_line:
                    self.removeItem(self._drag_line)
                    self._drag_line = None
                self._drag_port = None

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Delete:
            for item in list(self.selectedItems()):
                if isinstance(item, EdgeItem):
                    self._remove_edge(item)
        super().keyPressEvent(e)

    # ── edge logic ────────────────────────────────────────────────────
    def _try_add_edge(self, pa: PortItem, pb: PortItem):
        bus_p, slot_p = self._classify(pa, pb)
        if bus_p is None:
            return  # invalid: neither or both are bus ports
        # Remove existing connection from the same slot
        for existing in list(slot_p.edges):
            self._remove_edge(existing)
        edge = EdgeItem(slot_p, bus_p)
        self.addItem(edge)
        self._edges.append(edge)
        # persist into sub's bus_connections
        slot_node = slot_p.owner
        if isinstance(slot_node, NodeItem):
            ref = self._make_ref(bus_p.owner)
            if ref:
                slot_node.sub.bus_connections[slot_p.slot_name] = ref
            # 接続したバスの真横に自動配置
            self._place_beside_bus(slot_node, bus_p.owner)
        self.graph_changed.emit()

    def _place_beside_bus(self, node: NodeItem, bus_owner):
        """接続したコンポーネントをバスノードの右隣に配置する。
        同じバスに複数ノードが繋がる場合は縦に並べる。"""
        GAP = 40  # バスとノードの間隔
        if isinstance(bus_owner, (NodeItem, ExternalBusItem)):
            bx = bus_owner.x()
            by = bus_owner.y()
        else:
            return

        # このバスに既に繋がっているノードを数えて縦オフセットを決める
        bus_port = bus_owner.port("conn")
        if bus_port is None:
            return
        already = [e.pa.owner if e.pb is bus_port else e.pb.owner
                   for e in bus_port.edges
                   if isinstance(e.pa.owner, NodeItem) or isinstance(e.pb.owner, NodeItem)]
        # node 自身を除いた既存接続数でオフセット計算
        siblings = [n for n in already if n is not node and isinstance(n, NodeItem)]
        row = len(siblings)
        node_h = node._height() + 20
        node.setPos(bx + NODE_W + GAP, by + row * node_h)

    def _remove_edge(self, edge: EdgeItem):
        if edge not in self._edges:
            return
        self._edges.remove(edge)
        # clear bus_connections for the slot port
        for port in (edge.pa, edge.pb):
            if not self._is_bus_port(port) and isinstance(port.owner, NodeItem):
                port.owner.sub.bus_connections.pop(port.slot_name, None)
        edge.remove()
        self.graph_changed.emit()

    def _classify(self, pa: PortItem, pb: PortItem):
        """Return (bus_port, slot_port) or (None, None)."""
        a_bus = self._is_bus_port(pa)
        b_bus = self._is_bus_port(pb)
        if a_bus and not b_bus:
            return pa, pb
        if b_bus and not a_bus:
            return pb, pa
        return None, None

    def _is_bus_port(self, port: PortItem) -> bool:
        owner = port.owner
        if isinstance(owner, ExternalBusItem):
            return True
        if isinstance(owner, NodeItem) and owner.sub.component_type == "Bus":
            return True
        return False

    def _make_ref(self, bus_owner) -> Optional[str]:
        if isinstance(bus_owner, ExternalBusItem):
            return f"area:{bus_owner.carrier}"
        if isinstance(bus_owner, NodeItem):
            return f"internal:{bus_owner.sub.sub_id}"
        return None

    # ── private helpers ───────────────────────────────────────────────
    def _add_node_item(self, sub: SubComponentDef) -> NodeItem:
        node = NodeItem(sub)
        self.addItem(node)
        self._nodes[sub.sub_id] = node
        return node

    def _ensure_ext(self, carrier: str) -> ExternalBusItem:
        if carrier not in self._ext:
            item = ExternalBusItem(carrier)
            n = len(self._ext)
            item.setPos(-NODE_W - 80, n * 110)
            self.addItem(item)
            self._ext[carrier] = item
        return self._ext[carrier]

    def _draw_edge_from_ref(self, sub_id: str, slot: str, ref: str):
        node = self._nodes.get(sub_id)
        if not node:
            return
        slot_port = node.port(slot)
        if not slot_port:
            return
        if ref.startswith("area:"):
            bus_item = self._ext.get(ref[5:])
            bus_port = bus_item._port if bus_item else None
        elif ref.startswith("internal:"):
            bus_node = self._nodes.get(ref[9:])
            bus_port = bus_node.port("conn") if bus_node else None
        else:
            return
        if bus_port is None:
            return
        for e in self._edges:
            if {e.pa, e.pb} == {slot_port, bus_port}:
                return
        edge = EdgeItem(slot_port, bus_port)
        self.addItem(edge)
        self._edges.append(edge)


# ══════════════════════════════════════════════════════════════════════
# View
# ══════════════════════════════════════════════════════════════════════
class NodeGraphView(QGraphicsView):
    def __init__(self, scene: NodeGraphScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._zoom = 1.0

    def wheelEvent(self, e):
        factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self._zoom = max(0.15, min(4.0, self._zoom * factor))
        self.setTransform(QTransform().scale(self._zoom, self._zoom))

    def fit_all(self):
        r = self.scene().itemsBoundingRect()
        if not r.isEmpty():
            self.fitInView(r.adjusted(-40, -40, 40, 40),
                           Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = self.transform().m11()


# ══════════════════════════════════════════════════════════════════════
# Widget (toolbar + view)
# ══════════════════════════════════════════════════════════════════════
class NodeGraphWidget(QWidget):
    """Self-contained node-graph editor with add-node toolbar."""

    graph_changed = pyqtSignal()
    node_selected = pyqtSignal(object)   # SubComponentDef | None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = NodeGraphScene()
        self._scene.graph_changed.connect(self.graph_changed)
        self._scene.node_selected.connect(self.node_selected)
        self._scene.delete_node_requested.connect(self._on_delete_node_requested)
        self._view  = NodeGraphView(self._scene, self)
        self._add_cb: Optional[Callable]    = None
        self._del_cb: Optional[Callable]    = None
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        bar = QHBoxLayout()
        for label, ct in [("Bus追加", "Bus"), ("Store追加", "Store"),
                          ("Link追加", "Link"), ("Gen追加", "Generator")]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _, t=ct: self._on_add(t))
            bar.addWidget(btn)

        btn_area = QPushButton("エリアバス追加")
        btn_area.setFixedHeight(26)
        btn_area.clicked.connect(self._area_bus_menu)
        bar.addWidget(btn_area)

        btn_del = QPushButton("選択削除")
        btn_del.setFixedHeight(26)
        btn_del.clicked.connect(self._delete_selected)
        bar.addWidget(btn_del)

        btn_fit = QPushButton("全体表示")
        btn_fit.setFixedHeight(26)
        btn_fit.clicked.connect(self._view.fit_all)
        bar.addWidget(btn_fit)
        bar.addStretch()

        lay.addLayout(bar)
        lay.addWidget(self._view)

    def set_add_callback(self, cb: Callable):
        self._add_cb = cb

    def set_delete_callback(self, cb: Callable):
        self._del_cb = cb

    def _on_delete_node_requested(self, sub_id: str):
        if self._del_cb:
            self._del_cb(sub_id)

    def _on_add(self, component_type: str):
        if self._add_cb:
            self._add_cb(component_type)

    def _area_bus_menu(self):
        menu = QMenu(self)
        for c in ["AC"] + [x for x in MULTI_CARRIERS if x != "AC"]:
            menu.addAction(f"area:{c}").setData(c)
        act = menu.exec(self.sender().mapToGlobal(  # type: ignore
            self.sender().rect().bottomLeft()))      # type: ignore
        if act:
            self._scene.add_ext_bus(act.data())
            self.graph_changed.emit()

    def _delete_selected(self):
        for item in list(self._scene.selectedItems()):
            if isinstance(item, EdgeItem):
                self._scene._remove_edge(item)
            elif isinstance(item, NodeItem):
                if self._del_cb:
                    self._del_cb(item.sub.sub_id)
            elif isinstance(item, ExternalBusItem):
                self._scene.remove_ext_bus(item.carrier)

    # ── public API ────────────────────────────────────────────────────
    @property
    def scene(self) -> NodeGraphScene:
        return self._scene

    def load_template(self, template):
        self._scene.load_template(template)
        self._view.fit_all()

    def validate(self) -> List[str]:
        return self._scene.validate()
