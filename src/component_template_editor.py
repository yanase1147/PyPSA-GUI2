"""Component template editor dialog + custom instance placement dialog."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QLineEdit,
    QComboBox, QCheckBox, QDoubleSpinBox, QSpinBox, QFormLayout,
    QGroupBox, QDialogButtonBox, QMessageBox, QScrollArea,
    QTextEdit, QAbstractItemView, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class _AdaptiveSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that hides trailing zeros in the display."""
    def textFromValue(self, value: float) -> str:
        return f"{value:g}"

from .models import (
    ComponentTemplate, SubComponentDef, CustomComponentInstance,
    MULTI_CARRIERS, CARRIERS, AVAILABLE_EXPOSED_PARAMS,
    PARAM_DEFAULTS, PARAM_SUFFIX, get_param_suffix,
)
from .node_graph import NodeGraphWidget

_OK_CANCEL = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel

# Human-readable labels for exposed parameters shown in CustomInstanceDialog
PARAM_LABELS: dict[str, str] = {
    "e_nom":                    "エネルギー容量 (MWh)",
    "e_nom_extendable":         "容量拡張可能",
    "e_nom_max":                "最大容量 (MWh)",
    "e_nom_min":                "最小容量 (MWh)",
    "e_min_pu":                 "最小充電率",
    "e_max_pu":                 "最大充電率",
    "e_initial":                "初期エネルギー",
    "standing_loss":            "自己放電率",
    "cyclic_state_of_charge":   "周期的充放電",
    "capital_cost":             "建設費",
    "marginal_cost":            "変動費",
    "p_nom":                    "設備容量 (MW)",
    "p_nom_extendable":         "容量拡張可能",
    "p_nom_max":                "最大容量 (MW)",
    "p_nom_min":                "最小容量 (MW)",
    "p_max_pu":                 "最大出力率",
    "p_min_pu":                 "最小出力率",
    "efficiency":               "効率",
    "efficiency2":              "効率2",
    "build_year":               "建設年",
    "lifetime":                 "耐用年数 (年)",
    "committable":              "コミットメント",
    "min_up_time":              "最低運転時間 (h)",
    "ramp_limit_up":            "上昇ランプ率",
    "ramp_limit_down":          "下降ランプ率",
}

# ── carrier choices per component type ─────────────────────────────────
_CARRIER_OPTIONS: Dict[str, List[str]] = {
    "Bus":       ["AC", "DC"] + MULTI_CARRIERS + ["other"],
    "Generator": CARRIERS,
    "Store":     [""] + MULTI_CARRIERS,
    "Link":      [""] + MULTI_CARRIERS,
}


# ══════════════════════════════════════════════════════════════════════
# Property panel (right side of template editor)
# ══════════════════════════════════════════════════════════════════════
class PropertyPanel(QWidget):
    """Shows/edits the properties of the currently selected SubComponentDef."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sub: Optional[SubComponentDef] = None
        self._param_checks: Dict[str, QCheckBox] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)

        title_font = QFont(); title_font.setBold(True); title_font.setPointSize(9)
        self._title = QLabel("ノード未選択")
        self._title.setFont(title_font)
        lay.addWidget(self._title)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._inner = QWidget()
        self._inner_lay = QVBoxLayout(self._inner)
        self._inner_lay.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._inner)
        lay.addWidget(scroll)

    # ── public ────────────────────────────────────────────────────────
    def load(self, sub: Optional[SubComponentDef]):
        self._sub = sub
        self._rebuild()

    # ── rebuild form ──────────────────────────────────────────────────
    def _rebuild(self):
        # clear old widgets
        while self._inner_lay.count():
            item = self._inner_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._param_checks.clear()

        if self._sub is None:
            self._title.setText("ノード未選択")
            return

        sub = self._sub
        self._title.setText(f"[{sub.component_type}] {sub.sub_id}")

        # ── Basic ─────────────────────────────────────────────────────
        grp_basic = QGroupBox("基本")
        form_basic = QFormLayout(grp_basic)

        self._name_edit = QLineEdit(sub.name_template)
        self._name_edit.textChanged.connect(self._on_name_changed)
        form_basic.addRow("名前テンプレート:", self._name_edit)

        ct = sub.component_type
        carriers = _CARRIER_OPTIONS.get(ct, [])
        if carriers:
            self._carrier_combo = QComboBox()
            self._carrier_combo.addItems(carriers)
            cur = sub.fixed_params.get("carrier", "")
            if cur in carriers:
                self._carrier_combo.setCurrentText(cur)
            elif carriers:
                self._carrier_combo.setCurrentIndex(0)
            self._carrier_combo.currentTextChanged.connect(self._on_carrier_changed)
            lbl = "キャリア:"
            form_basic.addRow(lbl, self._carrier_combo)
        else:
            self._carrier_combo = None

        self._inner_lay.addWidget(grp_basic)

        # ── Exposed params ────────────────────────────────────────────
        available = AVAILABLE_EXPOSED_PARAMS.get(ct, [])
        if available:
            grp_exp = QGroupBox("公開パラメータ (インスタンス配置時に設定)")
            vlay = QVBoxLayout(grp_exp)
            note = QLabel("チェックしたパラメータをインスタンス配置時に設定できます")
            note.setWordWrap(True)
            note.setStyleSheet("color:#666; font-size:10px;")
            vlay.addWidget(note)
            for p in available:
                chk = QCheckBox(p)
                chk.setChecked(p in sub.exposed_params)
                chk.stateChanged.connect(lambda _, pp=p: self._on_param_check(pp))
                self._param_checks[p] = chk
                vlay.addWidget(chk)
            self._inner_lay.addWidget(grp_exp)

        self._inner_lay.addStretch()

    # ── slots ─────────────────────────────────────────────────────────
    def _on_name_changed(self, text: str):
        if self._sub:
            self._sub.name_template = text
            self.changed.emit()

    def _on_carrier_changed(self, text: str):
        if self._sub:
            if text:
                self._sub.fixed_params["carrier"] = text
            else:
                self._sub.fixed_params.pop("carrier", None)
            self.changed.emit()

    def _on_param_check(self, param: str):
        if not self._sub:
            return
        chk = self._param_checks.get(param)
        if chk is None:
            return
        if chk.isChecked():
            if param not in self._sub.exposed_params:
                self._sub.exposed_params.append(param)
        else:
            if param in self._sub.exposed_params:
                self._sub.exposed_params.remove(param)
        self.changed.emit()


# ══════════════════════════════════════════════════════════════════════
# Template editor dialog
# ══════════════════════════════════════════════════════════════════════
class ComponentTemplateEditorDialog(QDialog):
    """Main dialog for creating / editing component templates."""

    templates_changed = pyqtSignal(list)   # emits updated list

    def __init__(self, templates: List[ComponentTemplate], parent=None):
        super().__init__(parent)
        self.setWindowTitle("コンポーネントテンプレートエディタ")
        self.setMinimumSize(1100, 680)
        self._templates: List[ComponentTemplate] = [t for t in templates]
        self._current: Optional[ComponentTemplate] = None
        self._sub_counter: Dict[str, int] = {}
        self._setup_ui()
        self._refresh_list()

    # ── UI setup ──────────────────────────────────────────────────────
    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)

        # ── Left: template list ───────────────────────────────────────
        left = QWidget(); left.setFixedWidth(200)
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("テンプレート一覧")
        lbl.setStyleSheet("font-weight:bold;")
        ll.addWidget(lbl)
        self._tmpl_list = QListWidget()
        self._tmpl_list.currentRowChanged.connect(self._on_tmpl_selected)
        ll.addWidget(self._tmpl_list)

        btn_row = QHBoxLayout()
        self._btn_new   = QPushButton("新規")
        self._btn_clone = QPushButton("複製")
        self._btn_del_t = QPushButton("削除")
        for b in (self._btn_new, self._btn_clone, self._btn_del_t):
            b.setFixedHeight(26); btn_row.addWidget(b)
        self._btn_new.clicked.connect(self._new_template)
        self._btn_clone.clicked.connect(self._clone_template)
        self._btn_del_t.clicked.connect(self._delete_template)
        ll.addLayout(btn_row)
        content.addWidget(left)

        # ── Center: name/desc + graph ─────────────────────────────────
        center = QWidget()
        cl = QVBoxLayout(center); cl.setContentsMargins(0, 0, 0, 0)

        meta = QHBoxLayout()
        meta.addWidget(QLabel("名前:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("テンプレート名")
        self._name_edit.textChanged.connect(self._on_tmpl_name_changed)
        meta.addWidget(self._name_edit, 1)
        meta.addWidget(QLabel("説明:"))
        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("任意の説明")
        self._desc_edit.textChanged.connect(self._on_desc_changed)
        meta.addWidget(self._desc_edit, 2)
        cl.addLayout(meta)

        self._graph = NodeGraphWidget()
        self._graph.set_add_callback(self._on_add_node)
        self._graph.set_delete_callback(self._on_del_node)
        self._graph.node_selected.connect(self._on_node_selected)
        cl.addWidget(self._graph)

        btn_bar = QHBoxLayout()
        self._btn_validate = QPushButton("接続を検証")
        self._btn_validate.clicked.connect(self._validate)
        btn_bar.addWidget(self._btn_validate)
        btn_bar.addStretch()
        cl.addLayout(btn_bar)

        content.addWidget(center, 1)

        # ── Right: property panel ─────────────────────────────────────
        self._prop = PropertyPanel()
        self._prop.setFixedWidth(240)
        self._prop.changed.connect(self._on_prop_changed)
        content.addWidget(self._prop)

        outer.addLayout(content)

        # ── Bottom buttons ────────────────────────────────────────────
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self._on_close)
        outer.addWidget(bb)

    # ── template list ─────────────────────────────────────────────────
    def _refresh_list(self):
        row = self._tmpl_list.currentRow()
        self._tmpl_list.clear()
        for t in self._templates:
            self._tmpl_list.addItem(t.name)
        if 0 <= row < self._tmpl_list.count():
            self._tmpl_list.setCurrentRow(row)
        elif self._tmpl_list.count() > 0:
            self._tmpl_list.setCurrentRow(0)

    def _on_tmpl_selected(self, row: int):
        if 0 <= row < len(self._templates):
            self._current = self._templates[row]
        else:
            self._current = None
        self._load_current()

    def _load_current(self):
        t = self._current
        blocked = self._name_edit.blockSignals(True)
        self._name_edit.setText(t.name if t else "")
        self._name_edit.blockSignals(blocked)
        blocked = self._desc_edit.blockSignals(True)
        self._desc_edit.setText(t.description if t else "")
        self._desc_edit.blockSignals(blocked)
        self._graph.load_template(t)
        self._prop.load(None)

    # ── template CRUD ─────────────────────────────────────────────────
    def _new_template(self):
        n = len(self._templates) + 1
        t = ComponentTemplate(name=f"NewTemplate{n}")
        self._templates.append(t)
        self._refresh_list()
        self._tmpl_list.setCurrentRow(len(self._templates) - 1)
        self.templates_changed.emit(self._templates)

    def _clone_template(self):
        if not self._current:
            return
        import copy
        clone = copy.deepcopy(self._current)
        clone.name += "_copy"
        self._templates.append(clone)
        self._refresh_list()
        self._tmpl_list.setCurrentRow(len(self._templates) - 1)
        self.templates_changed.emit(self._templates)

    def _delete_template(self):
        if not self._current:
            return
        reply = QMessageBox.question(
            self, "確認",
            f"テンプレート「{self._current.name}」を削除しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._templates.remove(self._current)
        self._current = None
        self._refresh_list()
        self.templates_changed.emit(self._templates)

    def _on_tmpl_name_changed(self, text: str):
        if self._current and text:
            self._current.name = text
            row = self._tmpl_list.currentRow()
            item = self._tmpl_list.item(row)
            if item:
                item.setText(text)
            self.templates_changed.emit(self._templates)

    def _on_desc_changed(self, text: str):
        if self._current:
            self._current.description = text

    # ── node add/delete ───────────────────────────────────────────────
    def _on_add_node(self, component_type: str):
        if not self._current:
            QMessageBox.information(self, "情報", "先にテンプレートを選択または作成してください。")
            return
        # generate unique sub_id
        key = component_type.lower()
        n = self._sub_counter.get(key, 0) + 1
        self._sub_counter[key] = n
        sub_id = f"{key}_{n}"
        # default name_template
        default_names = {"Bus": "{name}-bus", "Store": "{name}-store",
                         "Link": "{name}-link", "Generator": "{name}-gen"}
        name_tmpl = default_names.get(component_type, f"{{name}}-{key}")
        # default position
        n_existing = len(self._current.sub_components)
        pos_x = (n_existing % 3) * 220
        pos_y = (n_existing // 3) * 180

        sub = SubComponentDef(
            sub_id=sub_id,
            component_type=component_type,
            name_template=name_tmpl,
            pos_x=pos_x,
            pos_y=pos_y,
        )
        # default carrier for Bus
        if component_type == "Bus":
            sub.fixed_params["carrier"] = "AC"

        self._current.sub_components.append(sub)
        self._graph.scene.add_sub(sub)
        self.templates_changed.emit(self._templates)

    def _on_del_node(self, sub_id: str):
        if not self._current:
            return
        self._current.sub_components = [
            s for s in self._current.sub_components if s.sub_id != sub_id]
        self._graph.scene.remove_sub(sub_id)
        self._prop.load(None)
        self.templates_changed.emit(self._templates)

    def _on_node_selected(self, sub):
        self._prop.load(sub)

    def _on_prop_changed(self):
        # refresh node visuals
        for node in self._graph.scene._nodes.values():
            node.update()
        self.templates_changed.emit(self._templates)

    # ── validation ────────────────────────────────────────────────────
    def _validate(self):
        errors = self._graph.validate()
        if not errors:
            QMessageBox.information(self, "検証結果", "問題は見つかりませんでした。")
        else:
            QMessageBox.warning(self, "検証結果",
                                "以下の問題が見つかりました:\n\n" + "\n".join(errors))

    def _on_close(self):
        self.templates_changed.emit(self._templates)
        self.accept()

    # ── public accessor ───────────────────────────────────────────────
    def get_templates(self) -> List[ComponentTemplate]:
        return self._templates


# ══════════════════════════════════════════════════════════════════════
# Custom component instance placement dialog
# ══════════════════════════════════════════════════════════════════════
class CustomInstanceDialog(QDialog):
    """Dialog for adding or editing a CustomComponentInstance."""

    _counter = 0

    def __init__(self, templates: List[ComponentTemplate], areas,
                 parent=None, existing: Optional[CustomComponentInstance] = None,
                 preset_area: str = "", cur: str = "Currency"):
        title = "カスタムコンポーネントの編集" if existing else "カスタムコンポーネントの追加"
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self.resize(560, 640)
        self._templates = templates
        self._areas = areas
        self._cur = cur
        self._param_widgets: Dict[str, QWidget] = {}

        if not existing:
            CustomInstanceDialog._counter += 1
        default_name = (f"Custom{CustomInstanceDialog._counter}"
                        if not existing else existing.name)

        outer = QVBoxLayout(self)

        form = QFormLayout()
        self._name_edit = QLineEdit(default_name)
        form.addRow("名前:", self._name_edit)

        self._area_combo = QComboBox()
        self._area_combo.addItems([a.name for a in areas])
        if preset_area and preset_area in [a.name for a in areas]:
            self._area_combo.setCurrentText(preset_area)
        form.addRow("エリア:", self._area_combo)

        self._tmpl_combo = QComboBox()
        self._tmpl_combo.addItems([t.name for t in templates])
        form.addRow("テンプレート:", self._tmpl_combo)
        outer.addLayout(form)

        # param area (scroll)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setMinimumHeight(200)
        self._param_widget = QWidget()
        self._param_lay = QVBoxLayout(self._param_widget)
        self._scroll.setWidget(self._param_widget)
        outer.addWidget(self._scroll)

        bb = QDialogButtonBox(_OK_CANCEL)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)

        self._tmpl_combo.currentTextChanged.connect(self._rebuild_params)
        self._rebuild_params(self._tmpl_combo.currentText())

        if existing:
            self._prefill(existing)

    # ── param widgets ─────────────────────────────────────────────────
    def _rebuild_params(self, tmpl_name: str):
        while self._param_lay.count():
            item = self._param_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._param_widgets.clear()

        tmpl = next((t for t in self._templates if t.name == tmpl_name), None)
        if not tmpl:
            return

        has_any = False
        for sub in tmpl.sub_components:
            # Filter out params that don't belong to this component type
            valid_params = AVAILABLE_EXPOSED_PARAMS.get(sub.component_type, [])
            params = [p for p in sub.exposed_params if p in valid_params]
            if not params:
                continue
            has_any = True
            grp = QGroupBox(f"{sub.component_type}: {sub.name_template.replace('{name}', self._name_edit.text().strip() or '{name}')}")
            flayout = QFormLayout(grp)
            for p in params:
                key = f"{sub.sub_id}.{p}"
                w = self._make_param_widget(p)
                self._param_widgets[key] = w
                flayout.addRow(f"{PARAM_LABELS.get(p, p)}:", w)
            self._param_lay.addWidget(grp)

        if not has_any:
            msg = QLabel("このテンプレートには表示可能なパラメータがありません。\nコンポーネント定義の exposed_params を確認してください。")
            msg.setWordWrap(True)
            self._param_lay.addWidget(msg)
        self._param_lay.addStretch()

    def _make_param_widget(self, param: str) -> QWidget:
        default = PARAM_DEFAULTS.get(param, 0.0)
        suffix  = get_param_suffix(self._cur).get(param, "")
        # bool params
        if isinstance(default, bool) or param in (
                "e_nom_extendable", "p_nom_extendable", "cyclic_state_of_charge",
                "committable"):
            chk = QCheckBox()
            chk.setChecked(bool(default))
            return chk
        # int params
        if param in ("build_year", "min_up_time"):
            sp = QSpinBox()
            sp.setRange(0, 9999)
            sp.setValue(int(default))
            return sp
        # float params
        sp = _AdaptiveSpinBox()
        sp.setRange(-1e12, 1e12)
        sp.setDecimals(4)
        sp.setValue(float(default))
        if suffix:
            sp.setSuffix(suffix)
        return sp

    def _prefill(self, ci: CustomComponentInstance):
        if ci.template_name in [t.name for t in self._templates]:
            self._tmpl_combo.setCurrentText(ci.template_name)
        self._area_combo.setCurrentText(ci.area)
        for key, val in ci.param_values.items():
            w = self._param_widgets.get(key)
            if isinstance(w, QCheckBox):
                w.setChecked(bool(val))
            elif isinstance(w, QSpinBox):
                w.setValue(int(val))
            elif isinstance(w, QDoubleSpinBox):
                w.setValue(float(val))

    # ── accept ────────────────────────────────────────────────────────
    def _on_accept(self):
        if not self._name_edit.text().strip():
            QMessageBox.warning(self, "警告", "名前を入力してください。")
            return
        if not self._templates:
            QMessageBox.warning(self, "警告", "テンプレートがありません。")
            return
        self.accept()

    def get_instance(self) -> CustomComponentInstance:
        param_values: Dict[str, Any] = {}
        for key, w in self._param_widgets.items():
            if isinstance(w, QCheckBox):
                param_values[key] = w.isChecked()
            elif isinstance(w, QSpinBox):
                param_values[key] = w.value()
            elif isinstance(w, QDoubleSpinBox):
                param_values[key] = w.value()
        return CustomComponentInstance(
            name=self._name_edit.text().strip(),
            area=self._area_combo.currentText(),
            template_name=self._tmpl_combo.currentText(),
            param_values=param_values,
        )
