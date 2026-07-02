from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QStyledItemDelegate,
    QPushButton,
    QLabel,
    QLineEdit,
    QMessageBox,
    QHeaderView,
)

from .models import (
    NetworkData,
    Area,
    AreaRES,
    Generator,
    Interconnection,
    Load,
    Store,
    PumpedHydro,
    Converter,
    CustomComponentInstance,
    CARRIERS,
    AREA_CARRIERS,
)


@dataclass
class _Column:
    header: str
    attr: str
    kind: str = "str"  # str | float | int | bool
    editable: bool = True


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _to_bool(text: str) -> bool:
    return str(text).strip().lower() in ("1", "true", "yes", "y", "on")


class _ComboDelegate(QStyledItemDelegate):
    """Read-only combobox editor delegate for table cells."""

    def __init__(self, options_getter, parent=None):
        super().__init__(parent)
        self._options_getter = options_getter

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.setEditable(False)
        options = list(self._options_getter())
        if not options:
            options = [""]
        combo.addItems(options)
        return combo

    def setEditorData(self, editor, index):
        if not isinstance(editor, QComboBox):
            return
        val = str(index.model().data(index, Qt.ItemDataRole.EditRole) or "")
        i = editor.findText(val)
        editor.setCurrentIndex(i if i >= 0 else 0)

    def setModelData(self, editor, model, index):
        if not isinstance(editor, QComboBox):
            return
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)


class NetworkManagerWindow(QWidget):
    network_updated = pyqtSignal(object)

    def __init__(self, network: NetworkData, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(self.tr("ネットワークマネージャー"))
        self.resize(1250, 720)

        self._network = network
        self._mute_item_changed = False
        self._tables: dict[str, QTableWidget] = {}
        self._rows: dict[str, list] = {}
        self._filters: dict[str, QLineEdit] = {}
        self._combo_delegates: list[_ComboDelegate] = []

        self._setup_ui()
        self.refresh_from_network()

    def set_network(self, network: NetworkData) -> None:
        self._network = network
        self.refresh_from_network()

    def refresh_from_network(self) -> None:
        self._refresh_areas()
        self._refresh_generators()
        self._refresh_interconnections()
        self._refresh_loads()
        self._refresh_stores()
        self._refresh_pumped_hydros()
        self._refresh_converters()
        self._refresh_customs()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        info = QLabel(self.tr("セル編集はフォーカス移動時に自動適用されます。"))
        info.setStyleSheet("color:#555;")
        layout.addWidget(info)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self._add_tab(
            "areas",
            self.tr("エリア"),
            [
                _Column(self.tr("名前"), "name"),
                _Column(self.tr("緯度"), "lat", "float"),
                _Column(self.tr("経度"), "lon", "float"),
                _Column(self.tr("国"), "country"),
            ],
        )
        self._add_tab(
            "generators",
            self.tr("発電機"),
            [
                _Column(self.tr("名前"), "name"),
                _Column(self.tr("エリア"), "area"),
                _Column(self.tr("種別"), "carrier"),
                _Column(self.tr("接続バス"), "bus_carrier"),
                _Column(self.tr("容量(MW)"), "p_nom", "float"),
                _Column(self.tr("拡張可能"), "p_nom_extendable", "bool"),
                _Column(self.tr("最大容量(MW)"), "p_nom_max", "float"),
                _Column(self.tr("変動費"), "marginal_cost", "float"),
                _Column(self.tr("建設費"), "capital_cost", "float"),
                _Column(self.tr("効率"), "efficiency", "float"),
                _Column(self.tr("建設年"), "build_year", "int"),
                _Column("p_max_pu", "p_max_pu", "float"),
                _Column("p_min_pu", "p_min_pu", "float"),
            ],
        )
        self._add_tab(
            "interconnections",
            self.tr("連系線"),
            [
                _Column(self.tr("名前"), "name"),
                _Column(self.tr("エリア0"), "area0"),
                _Column(self.tr("エリア1"), "area1"),
                _Column(self.tr("種別"), "carrier"),
                _Column(self.tr("効率"), "efficiency", "float"),
                _Column(self.tr("容量(MW)"), "p_nom", "float"),
                _Column(self.tr("逆方向容量(MW)"), "p_nom_reverse", "float"),
                _Column(self.tr("拡張可能"), "p_nom_extendable", "bool"),
                _Column(self.tr("建設費"), "capital_cost", "float"),
                _Column(self.tr("変動費"), "marginal_cost", "float"),
                _Column(self.tr("建設年"), "build_year", "int"),
            ],
        )
        self._add_tab(
            "loads",
            self.tr("需要"),
            [
                _Column(self.tr("名前"), "name"),
                _Column(self.tr("エリア"), "area"),
                _Column(self.tr("需要(MW)"), "p_set", "float"),
                _Column(self.tr("バスキャリア"), "bus_carrier"),
            ],
        )
        self._add_tab(
            "stores",
            self.tr("貯蔵"),
            [
                _Column(self.tr("名前"), "name"),
                _Column(self.tr("エリア"), "area"),
                _Column(self.tr("エネルギー容量(MWh)"), "e_nom", "float"),
                _Column(self.tr("種別"), "carrier"),
                _Column(self.tr("拡張可能"), "e_nom_extendable", "bool"),
                _Column(self.tr("建設費"), "capital_cost", "float"),
                _Column(self.tr("寿命"), "lifetime", "int"),
            ],
        )
        self._add_tab(
            "pumped_hydros",
            self.tr("揚水発電所"),
            [
                _Column(self.tr("名前"), "name"),
                _Column(self.tr("ACエリア"), "ac_area"),
                _Column(self.tr("タービン容量(MW)"), "p_nom_turbine", "float"),
                _Column(self.tr("タービン効率"), "efficiency_turbine", "float"),
                _Column(self.tr("ポンプ容量(MW)"), "p_nom_pump", "float"),
                _Column(self.tr("ポンプ効率"), "efficiency_pump", "float"),
                _Column(self.tr("貯水容量(MWh)"), "e_nom", "float"),
                _Column(self.tr("拡張可能"), "p_nom_extendable", "bool"),
                _Column(self.tr("建設費"), "capital_cost", "float"),
                _Column(self.tr("変動費"), "marginal_cost", "float"),
                _Column(self.tr("建設年"), "build_year", "int"),
            ],
        )
        self._add_tab(
            "converters",
            self.tr("変換器"),
            [
                _Column(self.tr("名前"), "name"),
                _Column(self.tr("エリア"), "area"),
                _Column(self.tr("入力キャリア"), "carrier_in"),
                _Column(self.tr("出力キャリア1"), "carrier_out"),
                _Column(self.tr("出力キャリア2"), "carrier_out2"),
                _Column(self.tr("効率1"), "efficiency", "float"),
                _Column(self.tr("効率2"), "efficiency2", "float"),
                _Column(self.tr("容量(MW)"), "p_nom", "float"),
                _Column(self.tr("拡張可能"), "p_nom_extendable", "bool"),
                _Column(self.tr("最大容量(MW)"), "p_nom_max", "float"),
                _Column(self.tr("建設費"), "capital_cost", "float"),
                _Column(self.tr("変動費"), "marginal_cost", "float"),
                _Column(self.tr("建設年"), "build_year", "int"),
            ],
        )
        self._add_tab(
            "customs",
            self.tr("カスタム"),
            [
                _Column(self.tr("名前"), "name"),
                _Column(self.tr("エリア"), "area"),
                _Column(self.tr("テンプレート"), "template_name"),
                _Column(self.tr("寿命"), "lifetime", "int", editable=False),
            ],
        )

    def _add_tab(self, key: str, title: str, columns: list[_Column]) -> None:
        wrapper = QWidget()
        lay = QVBoxLayout(wrapper)
        lay.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        btn_add = QPushButton(self.tr("追加"))
        btn_del = QPushButton(self.tr("削除"))
        btn_add.clicked.connect(lambda: self._add_row(key))
        btn_del.clicked.connect(lambda: self._delete_selected(key))
        bar.addWidget(btn_add)
        bar.addWidget(btn_del)
        bar.addStretch()
        filter_edit = QLineEdit()
        filter_edit.setPlaceholderText(self.tr("フィルタ…"))
        filter_edit.setClearButtonEnabled(True)
        filter_edit.setFixedWidth(220)
        filter_edit.textChanged.connect(lambda text, k=key: self._apply_filter(k, text))
        bar.addWidget(QLabel(self.tr("検索:")))
        bar.addWidget(filter_edit)
        self._filters[key] = filter_edit
        lay.addLayout(bar)

        table = QTableWidget()
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels([c.header for c in columns])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.itemChanged.connect(lambda item, k=key, cols=columns: self._on_item_changed(k, cols, item))
        self._install_combo_delegates(key, table, columns)
        lay.addWidget(table, 1)

        self._tables[key] = table
        self._rows[key] = []
        self.tabs.addTab(wrapper, title)

    def _install_combo_delegates(self, key: str, table: QTableWidget, columns: list[_Column]) -> None:
        area_options = lambda: [a.name for a in self._network.areas]
        area_carrier_options = lambda: self._network.area_carriers()
        template_options = lambda: [t.name for t in self._network.component_templates]

        for idx, col in enumerate(columns):
            getter = None
            if col.attr in ("area", "area0", "area1", "ac_area"):
                getter = area_options
            elif key == "generators" and col.attr == "carrier":
                getter = lambda: CARRIERS
            elif key == "generators" and col.attr == "bus_carrier":
                getter = area_carrier_options
            elif key == "loads" and col.attr == "bus_carrier":
                getter = area_carrier_options
            elif key == "customs" and col.attr == "template_name":
                getter = template_options

            if getter is not None:
                delegate = _ComboDelegate(getter, table)
                table.setItemDelegateForColumn(idx, delegate)
                self._combo_delegates.append(delegate)

    def _refresh_table(self, key: str, columns: list[_Column], rows: list[Any]) -> None:
        table = self._tables[key]
        self._rows[key] = rows

        self._mute_item_changed = True
        try:
            table.setRowCount(0)
            for r, row_obj in enumerate(rows):
                table.insertRow(r)
                for c, col in enumerate(columns):
                    item = QTableWidgetItem(_fmt(getattr(row_obj, col.attr, "")))
                    if not col.editable:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    table.setItem(r, c, item)
        finally:
            self._mute_item_changed = False

        # フィルタを再適用
        if key in self._filters:
            self._apply_filter(key, self._filters[key].text())

    def _apply_filter(self, key: str, text: str) -> None:
        table = self._tables.get(key)
        if table is None:
            return
        needle = text.strip().lower()
        for row in range(table.rowCount()):
            if not needle:
                table.setRowHidden(row, False)
                continue
            match = False
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if item and needle in item.text().lower():
                    match = True
                    break
            table.setRowHidden(row, not match)

    def _area_names(self) -> set[str]:
        return {a.name for a in self._network.areas}

    def _find_res(self, area_name: str) -> AreaRES | None:
        return self._network.get_area_res(area_name)

    def _emit_updated(self) -> None:
        self.network_updated.emit(self._network)

    def _refresh_areas(self) -> None:
        cols = [
            _Column(self.tr("名前"), "name"),
            _Column(self.tr("緯度"), "lat", "float"),
            _Column(self.tr("経度"), "lon", "float"),
            _Column(self.tr("国"), "country"),
        ]
        self._refresh_table("areas", cols, list(self._network.areas))

    def _refresh_generators(self) -> None:
        cols = [
            _Column(self.tr("名前"), "name"), _Column(self.tr("エリア"), "area"), _Column(self.tr("種別"), "carrier"),
            _Column(self.tr("接続バス"), "bus_carrier"),
            _Column(self.tr("容量(MW)"), "p_nom", "float"), _Column(self.tr("拡張可能"), "p_nom_extendable", "bool"),
            _Column(self.tr("最大容量(MW)"), "p_nom_max", "float"), _Column(self.tr("変動費"), "marginal_cost", "float"),
            _Column(self.tr("建設費"), "capital_cost", "float"), _Column(self.tr("効率"), "efficiency", "float"),
            _Column(self.tr("建設年"), "build_year", "int"), _Column("p_max_pu", "p_max_pu", "float"),
            _Column("p_min_pu", "p_min_pu", "float"),
        ]
        self._refresh_table("generators", cols, list(self._network.all_generators))

    def _refresh_interconnections(self) -> None:
        cols = [
            _Column(self.tr("名前"), "name"), _Column(self.tr("エリア0"), "area0"), _Column(self.tr("エリア1"), "area1"),
            _Column(self.tr("種別"), "carrier"), _Column(self.tr("効率"), "efficiency", "float"),
            _Column(self.tr("容量(MW)"), "p_nom", "float"), _Column(self.tr("逆方向容量(MW)"), "p_nom_reverse", "float"),
            _Column(self.tr("拡張可能"), "p_nom_extendable", "bool"), _Column(self.tr("建設費"), "capital_cost", "float"),
            _Column(self.tr("変動費"), "marginal_cost", "float"), _Column(self.tr("建設年"), "build_year", "int"),
        ]
        self._refresh_table("interconnections", cols, list(self._network.interconnections))

    def _refresh_loads(self) -> None:
        cols = [
            _Column(self.tr("名前"), "name"), _Column(self.tr("エリア"), "area"),
            _Column(self.tr("需要(MW)"), "p_set", "float"), _Column(self.tr("バスキャリア"), "bus_carrier"),
        ]
        self._refresh_table("loads", cols, list(self._network.all_loads))

    def _refresh_stores(self) -> None:
        cols = [
            _Column(self.tr("名前"), "name"), _Column(self.tr("エリア"), "area"), _Column(self.tr("エネルギー容量(MWh)"), "e_nom", "float"),
            _Column(self.tr("種別"), "carrier"), _Column(self.tr("拡張可能"), "e_nom_extendable", "bool"),
            _Column(self.tr("建設費"), "capital_cost", "float"), _Column(self.tr("寿命"), "lifetime", "int"),
        ]
        self._refresh_table("stores", cols, list(self._network.all_stores))

    def _refresh_pumped_hydros(self) -> None:
        cols = [
            _Column(self.tr("名前"), "name"), _Column(self.tr("ACエリア"), "ac_area"), _Column(self.tr("タービン容量(MW)"), "p_nom_turbine", "float"),
            _Column(self.tr("タービン効率"), "efficiency_turbine", "float"), _Column(self.tr("ポンプ容量(MW)"), "p_nom_pump", "float"),
            _Column(self.tr("ポンプ効率"), "efficiency_pump", "float"), _Column(self.tr("貯水容量(MWh)"), "e_nom", "float"),
            _Column(self.tr("拡張可能"), "p_nom_extendable", "bool"), _Column(self.tr("建設費"), "capital_cost", "float"),
            _Column(self.tr("変動費"), "marginal_cost", "float"), _Column(self.tr("建設年"), "build_year", "int"),
        ]
        self._refresh_table("pumped_hydros", cols, list(self._network.all_pumped_hydros))

    def _refresh_converters(self) -> None:
        cols = [
            _Column(self.tr("名前"), "name"), _Column(self.tr("エリア"), "area"), _Column(self.tr("入力キャリア"), "carrier_in"),
            _Column(self.tr("出力キャリア1"), "carrier_out"), _Column(self.tr("出力キャリア2"), "carrier_out2"),
            _Column(self.tr("効率1"), "efficiency", "float"), _Column(self.tr("効率2"), "efficiency2", "float"),
            _Column(self.tr("容量(MW)"), "p_nom", "float"), _Column(self.tr("拡張可能"), "p_nom_extendable", "bool"),
            _Column(self.tr("最大容量(MW)"), "p_nom_max", "float"), _Column(self.tr("建設費"), "capital_cost", "float"),
            _Column(self.tr("変動費"), "marginal_cost", "float"), _Column(self.tr("建設年"), "build_year", "int"),
        ]
        self._refresh_table("converters", cols, list(self._network.all_converters))

    def _refresh_customs(self) -> None:
        cols = [
            _Column(self.tr("名前"), "name"), _Column(self.tr("エリア"), "area"), _Column(self.tr("テンプレート"), "template_name"),
            _Column(self.tr("寿命"), "lifetime", "int", editable=False),
        ]
        self._refresh_table("customs", cols, list(self._network.all_custom_instances))

    def _parse(self, kind: str, text: str, fallback: Any) -> Any:
        try:
            if kind == "float":
                return float(text)
            if kind == "int":
                return int(float(text))
            if kind == "bool":
                return _to_bool(text)
            return str(text)
        except Exception:
            return fallback

    def _on_item_changed(self, key: str, columns: list[_Column], item: QTableWidgetItem) -> None:
        if self._mute_item_changed:
            return
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._rows[key]) or col < 0 or col >= len(columns):
            return

        obj = self._rows[key][row]
        column = columns[col]
        old_value = getattr(obj, column.attr, "")
        new_value = self._parse(column.kind, item.text(), old_value)

        if key == "areas" and column.attr == "name":
            old_name = str(old_value)
            new_name = str(new_value)
            if new_name and new_name != old_name:
                if new_name in self._area_names():
                    self.refresh_from_network()
                    QMessageBox.warning(self, self.tr("警告"), self.tr("同名エリアが存在します。"))
                    return
                self._rename_area_references(old_name, new_name)

        if key == "generators" and column.attr == "area":
            if str(new_value) not in self._area_names():
                self.refresh_from_network()
                return
            self._move_generator(obj, str(new_value))
        elif key == "loads" and column.attr == "area":
            if str(new_value) not in self._area_names():
                self.refresh_from_network()
                return
            self._move_load(obj, str(new_value))
        elif key == "stores" and column.attr == "area":
            if str(new_value) not in self._area_names():
                self.refresh_from_network()
                return
            self._move_store(obj, str(new_value))
        elif key == "pumped_hydros" and column.attr == "ac_area":
            if str(new_value) not in self._area_names():
                self.refresh_from_network()
                return
            self._move_pumped_hydro(obj, str(new_value))
        elif key == "converters" and column.attr == "area":
            if str(new_value) not in self._area_names():
                self.refresh_from_network()
                return
            self._move_converter(obj, str(new_value))
        elif key == "customs" and column.attr == "area":
            if str(new_value) not in self._area_names():
                self.refresh_from_network()
                return
            self._move_custom(obj, str(new_value))
        elif key == "interconnections" and column.attr in ("area0", "area1"):
            if str(new_value) not in self._area_names():
                self.refresh_from_network()
                return
            setattr(obj, column.attr, str(new_value))
        elif key == "generators" and column.attr == "carrier":
            if str(new_value) not in CARRIERS:
                self.refresh_from_network()
                return
            setattr(obj, column.attr, str(new_value))
        elif key == "generators" and column.attr == "bus_carrier":
            if str(new_value) not in self._network.area_carriers():
                self.refresh_from_network()
                return
            setattr(obj, column.attr, str(new_value))
        elif key == "loads" and column.attr == "bus_carrier":
            if str(new_value) not in self._network.area_carriers():
                self.refresh_from_network()
                return
            setattr(obj, column.attr, str(new_value))
        else:
            setattr(obj, column.attr, new_value)

        self.refresh_from_network()
        self._emit_updated()

    def _rename_area_references(self, old_name: str, new_name: str) -> None:
        area = next((a for a in self._network.areas if a.name == old_name), None)
        if area:
            area.name = new_name

        res = self._find_res(old_name)
        if res:
            res.area.name = new_name
            for g in res.generators:
                g.area = new_name
            for ld in res.loads:
                ld.area = new_name
            for st in res.stores:
                st.area = new_name
            for ph in res.pumped_hydros:
                ph.ac_area = new_name
            for c in res.converters:
                c.area = new_name
            for ci in res.custom_instances:
                ci.area = new_name

        for ic in self._network.interconnections:
            if ic.area0 == old_name:
                ic.area0 = new_name
            if ic.area1 == old_name:
                ic.area1 = new_name

    def _move_generator(self, g: Generator, new_area: str) -> None:
        old_res = self._find_res(g.area)
        new_res = self._find_res(new_area)
        if old_res is None or new_res is None:
            return
        if g in old_res.generators:
            old_res.generators.remove(g)
        g.area = new_area
        new_res.generators.append(g)

    def _move_load(self, ld: Load, new_area: str) -> None:
        old_res = self._find_res(ld.area)
        new_res = self._find_res(new_area)
        if old_res is None or new_res is None:
            return
        if ld in old_res.loads:
            old_res.loads.remove(ld)
        ld.area = new_area
        new_res.loads.append(ld)

    def _move_store(self, st: Store, new_area: str) -> None:
        old_res = self._find_res(st.area)
        new_res = self._find_res(new_area)
        if old_res is None or new_res is None:
            return
        if st in old_res.stores:
            old_res.stores.remove(st)
        st.area = new_area
        new_res.stores.append(st)

    def _move_pumped_hydro(self, ph: PumpedHydro, new_area: str) -> None:
        old_res = self._find_res(ph.ac_area)
        new_res = self._find_res(new_area)
        if old_res is None or new_res is None:
            return
        if ph in old_res.pumped_hydros:
            old_res.pumped_hydros.remove(ph)
        ph.ac_area = new_area
        new_res.pumped_hydros.append(ph)

    def _move_converter(self, conv: Converter, new_area: str) -> None:
        old_res = self._find_res(conv.area)
        new_res = self._find_res(new_area)
        if old_res is None or new_res is None:
            return
        if conv in old_res.converters:
            old_res.converters.remove(conv)
        conv.area = new_area
        new_res.converters.append(conv)

    def _move_custom(self, ci: CustomComponentInstance, new_area: str) -> None:
        old_res = self._find_res(ci.area)
        new_res = self._find_res(new_area)
        if old_res is None or new_res is None:
            return
        if ci in old_res.custom_instances:
            old_res.custom_instances.remove(ci)
        ci.area = new_area
        new_res.custom_instances.append(ci)

    def _unique_name(self, prefix: str, used: set[str]) -> str:
        i = 1
        while f"{prefix}{i}" in used:
            i += 1
        return f"{prefix}{i}"

    def _add_row(self, key: str) -> None:
        if key == "areas":
            used = {a.name for a in self._network.areas}
            name = self._unique_name("Area", used)
            area = Area(name=name, lat=0.0, lon=0.0, country="")
            self._network.areas.append(area)
            self._network.get_or_create_area_res(area)
        else:
            if not self._network.areas:
                QMessageBox.warning(self, self.tr("警告"), self.tr("先にエリアを追加してください。"))
                return
            area_name = self._network.areas[0].name
            res = self._network.get_or_create_area_res(self._network.areas[0])

            if key == "generators":
                used = {g.name for g in self._network.all_generators}
                res.generators.append(Generator(name=self._unique_name("Gen", used), area=area_name, carrier="Solar"))
            elif key == "interconnections":
                if len(self._network.areas) < 2:
                    QMessageBox.warning(self, self.tr("警告"), self.tr("連系線には2つ以上のエリアが必要です。"))
                    return
                used = {ic.name for ic in self._network.interconnections}
                self._network.interconnections.append(
                    Interconnection(
                        name=self._unique_name("IC", used),
                        area0=self._network.areas[0].name,
                        area1=self._network.areas[1].name,
                    )
                )
            elif key == "loads":
                used = {ld.name for ld in self._network.all_loads}
                res.loads.append(Load(name=self._unique_name("Load", used), area=area_name, p_set=0.0))
            elif key == "stores":
                used = {st.name for st in self._network.all_stores}
                res.stores.append(Store(name=self._unique_name("Store", used), area=area_name))
            elif key == "pumped_hydros":
                used = {ph.name for ph in self._network.all_pumped_hydros}
                res.pumped_hydros.append(PumpedHydro(name=self._unique_name("PH", used), ac_area=area_name))
            elif key == "converters":
                used = {cv.name for cv in self._network.all_converters}
                res.converters.append(Converter(name=self._unique_name("Conv", used), area=area_name, carrier_in="AC", carrier_out="heat"))
            elif key == "customs":
                used = {ci.name for ci in self._network.all_custom_instances}
                tmpl = self._network.component_templates[0].name if self._network.component_templates else ""
                res.custom_instances.append(CustomComponentInstance(name=self._unique_name("Custom", used), area=area_name, template_name=tmpl))
            else:
                return

        self.refresh_from_network()
        self._emit_updated()

    def _delete_selected(self, key: str) -> None:
        table = self._tables[key]
        row = table.currentRow()
        if row < 0 or row >= len(self._rows[key]):
            return
        obj = self._rows[key][row]

        if key == "areas":
            name = obj.name
            self._network.interconnections = [
                ic for ic in self._network.interconnections if ic.area0 != name and ic.area1 != name
            ]
            self._network.area_res_list = [r for r in self._network.area_res_list if r.area.name != name]
            self._network.areas = [a for a in self._network.areas if a.name != name]
        elif key == "interconnections":
            self._network.interconnections = [ic for ic in self._network.interconnections if ic is not obj]
        elif key == "generators":
            res = self._find_res(obj.area)
            if res and obj in res.generators:
                res.generators.remove(obj)
        elif key == "loads":
            res = self._find_res(obj.area)
            if res and obj in res.loads:
                res.loads.remove(obj)
        elif key == "stores":
            res = self._find_res(obj.area)
            if res and obj in res.stores:
                res.stores.remove(obj)
        elif key == "pumped_hydros":
            res = self._find_res(obj.ac_area)
            if res and obj in res.pumped_hydros:
                res.pumped_hydros.remove(obj)
        elif key == "converters":
            res = self._find_res(obj.area)
            if res and obj in res.converters:
                res.converters.remove(obj)
        elif key == "customs":
            res = self._find_res(obj.area)
            if res and obj in res.custom_instances:
                res.custom_instances.remove(obj)
        else:
            return

        self.refresh_from_network()
        self._emit_updated()
