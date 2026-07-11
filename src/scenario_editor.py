from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QDoubleSpinBox, QSpinBox, QScrollArea, QPushButton, QLabel,
    QMessageBox, QDialog, QDialogButtonBox, QComboBox, QLineEdit,
    QSplitter, QInputDialog, QTabWidget, QCheckBox,
)
from PyQt6.QtCore import Qt

from .models import (
    CARRIERS, DEFAULT_CARRIER_COSTS, ScenarioData, NetworkData,
    ComponentOverrideRule, ScenarioProfile,
)


def _fmt(v) -> str:
    """Format a value for table display: floats drop unnecessary trailing zeros."""
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


class _AdaptiveSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that hides trailing zeros in the display."""
    def textFromValue(self, value: float) -> str:
        return f"{value:g}"

_COMPONENT_PARAMS: dict = {
    "Generator": [
        "p_nom", "p_nom_extendable", "p_nom_max", "marginal_cost",
        "capital_cost", "efficiency", "build_year",
        "p_max_pu", "p_min_pu", "committable",
        "min_up_time", "ramp_limit_up", "ramp_limit_down",
    ],
    "Store": ["e_nom", "e_nom_extendable", "e_nom_max", "capital_cost", "marginal_cost"],
    "PumpedHydro": [
        "p_nom_turbine", "efficiency_turbine", "p_nom_pump", "efficiency_pump",
        "e_nom", "p_nom_extendable", "capital_cost", "marginal_cost", "build_year",
    ],
    "Converter": [
        "efficiency", "efficiency2", "p_nom", "p_nom_extendable", "p_nom_max",
        "marginal_cost", "capital_cost", "build_year",
    ],
    "Interconnection": [
        "efficiency", "p_nom", "p_nom_reverse", "p_nom_extendable",
        "capital_cost", "marginal_cost", "build_year",
    ],
    "Load": ["demand_scale", "p_set"],
    "CustomComponentInstance": [],
}
_COMPONENT_TYPES = list(_COMPONENT_PARAMS.keys())


class RuleDialog(QDialog):
    """コンポーネントオーバーライドルールを追加・編集するダイアログ。"""

    def __init__(self, parent=None, rule: ComponentOverrideRule = None,
                 network=None):
        super().__init__(parent)
        self._network = network  # NetworkData | None
        self.setWindowTitle(self.tr("ルールの追加") if rule is None else self.tr("ルールの編集"))
        self.setMinimumWidth(420)

        form = QFormLayout(self)

        self.type_combo = QComboBox()
        self.type_combo.addItems(_COMPONENT_TYPES)
        self.type_combo.currentTextChanged.connect(self._update_name_combo)
        self.type_combo.currentTextChanged.connect(self._update_param_combo)

        self.name_combo = QComboBox()
        self.name_combo.setEditable(True)
        self.name_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        self.param_combo = QComboBox()
        self.param_combo.setEditable(True)

        self.year_spin = QSpinBox()
        self.year_spin.setRange(2020, 2100)
        self.year_spin.setValue(2030)

        self.value_edit = QLineEdit("0.0")
        self.value_edit.setPlaceholderText(self.tr("数値で入力"))

        form.addRow(self.tr("コンポーネント種別:"), self.type_combo)
        form.addRow(self.tr("コンポーネント名:"), self.name_combo)
        form.addRow(self.tr("パラメータ:"), self.param_combo)
        form.addRow(self.tr("年:"), self.year_spin)
        form.addRow(self.tr("値:"), self.value_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

        self._update_name_combo(self.type_combo.currentText())
        self._update_param_combo(self.type_combo.currentText())

        if rule is not None:
            self.type_combo.setCurrentText(rule.component_type)
            self.name_combo.setCurrentText(rule.component_name)
            self.param_combo.setCurrentText(rule.parameter)
            self.year_spin.setValue(rule.year)
            self.value_edit.setText(str(rule.value))

    def _names_for_type(self, ctype: str) -> list[str]:
        """NetworkData から種別に対応するコンポーネント名一覧を返す。"""
        if self._network is None:
            return []
        mapping = {
            "Generator":              [g.name for g in self._network.all_generators],
            "Store":                  [s.name for s in self._network.all_stores],
            "PumpedHydro":            [p.name for p in self._network.all_pumped_hydros],
            "Converter":              [c.name for c in self._network.all_converters],
            "Interconnection":        [i.name for i in self._network.interconnections],
            "Load":                   [l.name for l in self._network.all_loads],
            "CustomComponentInstance":[ci.name for ci in self._network.all_custom_instances],
        }
        return mapping.get(ctype, [])

    def _update_name_combo(self, ctype: str):
        current = self.name_combo.currentText()
        self.name_combo.clear()
        names = self._names_for_type(ctype)
        self.name_combo.addItems(names)
        # 元の値を保持（編集中の場合）
        if current:
            self.name_combo.setCurrentText(current)

    def _update_param_combo(self, ctype: str):
        self.param_combo.clear()
        params = _COMPONENT_PARAMS.get(ctype, [])
        if params:
            self.param_combo.addItems(params)
            self.param_combo.setEditable(False)
        else:
            self.param_combo.setEditable(True)
            self.param_combo.setPlaceholderText(self.tr("例: main.capital_cost"))

    def _on_accept(self):
        if not self.name_combo.currentText().strip():
            QMessageBox.warning(self, self.tr("入力エラー"), self.tr("コンポーネント名を入力してください。"))
            return
        if not self.param_combo.currentText().strip():
            QMessageBox.warning(self, self.tr("入力エラー"), self.tr("パラメータを入力してください。"))
            return
        try:
            float(self.value_edit.text())
        except ValueError:
            QMessageBox.warning(self, self.tr("入力エラー"), self.tr("値は数値で入力してください。"))
            return
        self.accept()

    def get_rule(self) -> ComponentOverrideRule:
        return ComponentOverrideRule(
            component_type=self.type_combo.currentText(),
            component_name=self.name_combo.currentText().strip(),
            parameter=self.param_combo.currentText().strip(),
            year=self.year_spin.value(),
            value=float(self.value_edit.text()),
        )


class ScenarioEditor(QWidget):
    """シナリオ・プロファイル管理タブ。NetworkData 内のシナリオとプロファイルを編集する。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._net   = NetworkData()
        self._net.scenarios = [ScenarioData()]
        self._block = False
        self._setup_ui()
        self._populate_scenario_table()

    # ══════════════════════════════════════════════════════════════════
    # UI構築
    # ══════════════════════════════════════════════════════════════════

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── 上段: シナリオ ────────────────────────────────────────────
        splitter.addWidget(self._build_scenario_section())

        # ── 下段: プロファイル ────────────────────────────────────────
        splitter.addWidget(self._build_profile_section())

        splitter.setSizes([280, 500])
        outer.addWidget(splitter)

    # ── Scenario section ──────────────────────────────────────────────

    def _build_scenario_section(self) -> QWidget:
        group = QGroupBox(self.tr("シナリオ一覧"))
        vlayout = QVBoxLayout(group)

        h = QHBoxLayout()

        # Scenario list table
        self.scenario_table = QTableWidget(0, 5)
        self.scenario_table.setHorizontalHeaderLabels(
            [self.tr("シナリオ名"), self.tr("基準年"), self.tr("計画年"), self.tr("割引率"), self.tr("最適化")])
        self.scenario_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.scenario_table.verticalHeader().setVisible(False)
        self.scenario_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.scenario_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.scenario_table.itemSelectionChanged.connect(self._on_scenario_selected)
        h.addWidget(self.scenario_table, 2)

        # Scenario detail form
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(8, 0, 0, 0)

        self.sc_name  = QLineEdit()
        self.sc_base_year = QSpinBox()
        self.sc_base_year.setRange(1990, 2050)
        self.sc_discount = _AdaptiveSpinBox()
        self.sc_discount.setRange(0, 1)
        self.sc_discount.setDecimals(4)
        self.sc_discount.setSingleStep(0.005)

        form.addRow(self.tr("名前:"), self.sc_name)
        form.addRow(self.tr("基準年:"), self.sc_base_year)
        form.addRow(self.tr("割引率:"), self.sc_discount)

        # Planning years sub-table
        form.addRow(QLabel(self.tr("計画年:")))
        yr_h = QHBoxLayout()
        self.sc_year_table = QTableWidget(0, 1)
        self.sc_year_table.setHorizontalHeaderLabels([self.tr("年")])
        self.sc_year_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.sc_year_table.verticalHeader().setVisible(False)
        self.sc_year_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sc_year_table.setMaximumHeight(100)
        yr_h.addWidget(self.sc_year_table)

        yr_btn = QVBoxLayout()
        self.sc_new_year = QSpinBox()
        self.sc_new_year.setRange(2020, 2100)
        self.sc_new_year.setValue(2030)
        btn_add_yr = QPushButton(self.tr("追加"))
        btn_del_yr = QPushButton(self.tr("削除"))
        btn_add_yr.clicked.connect(self._add_planning_year)
        btn_del_yr.clicked.connect(self._del_planning_year)
        yr_btn.addWidget(self.sc_new_year)
        yr_btn.addWidget(btn_add_yr)
        yr_btn.addWidget(btn_del_yr)
        yr_btn.addStretch()
        yr_h.addLayout(yr_btn)
        form.addRow(yr_h)

        self.sc_multi_period = QCheckBox(self.tr("完全予見（multi-period）最適化"))
        self.sc_multi_period.setToolTip(
            "有効にすると、全計画年を1つのネットワークとして同時最適化します。\n"
            "投資期間間の設備退役・追加が最適化されます（計画年が2つ以上必要）。\n"
            "注意: メモリ・計算時間が大幅に増加します。"
        )
        form.addRow(self.tr("最適化モード:"), self.sc_multi_period)

        self.sc_name.editingFinished.connect(self._save_scenario_fields)
        self.sc_base_year.valueChanged.connect(self._save_scenario_fields)
        self.sc_discount.valueChanged.connect(self._save_scenario_fields)
        self.sc_multi_period.toggled.connect(self._save_scenario_fields)

        h.addWidget(form_widget, 3)
        vlayout.addLayout(h)

        btn_row = QHBoxLayout()
        btn_add_sc = QPushButton(self.tr("シナリオ追加"))
        btn_del_sc = QPushButton(self.tr("シナリオ削除"))
        btn_add_sc.clicked.connect(self._add_scenario)
        btn_del_sc.clicked.connect(self._del_scenario)
        btn_row.addWidget(btn_add_sc)
        btn_row.addWidget(btn_del_sc)
        btn_row.addStretch()
        vlayout.addLayout(btn_row)

        return group

    # ── Profile section ───────────────────────────────────────────────

    def _build_profile_section(self) -> QWidget:
        group = QGroupBox(self.tr("シナリオプロファイル一覧"))
        vlayout = QVBoxLayout(group)

        h_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: profile list
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        self.profile_table = QTableWidget(0, 3)
        self.profile_table.setHorizontalHeaderLabels([self.tr("適用"), self.tr("プロファイル名"), self.tr("説明")])
        self.profile_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self.profile_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.profile_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self.profile_table.verticalHeader().setVisible(False)
        self.profile_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.profile_table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked)
        self.profile_table.itemSelectionChanged.connect(self._on_profile_selected)
        self.profile_table.itemChanged.connect(self._on_profile_item_changed)
        ll.addWidget(self.profile_table)

        p_btns = QHBoxLayout()
        for label, slot in [(self.tr("追加"), self._add_profile), (self.tr("削除"), self._del_profile),
                             (self.tr("上へ"), self._move_profile_up), (self.tr("下へ"), self._move_profile_dn)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            p_btns.addWidget(b)
        p_btns.addStretch()
        ll.addLayout(p_btns)

        h_splitter.addWidget(left)

        # Right: profile detail tabs
        self.profile_tabs = QTabWidget()
        self.profile_tabs.addTab(self._build_co2_tab(),     self.tr("CO₂設定"))
        self.profile_tabs.addTab(self._build_carrier_tab(), self.tr("キャリアコスト"))
        self.profile_tabs.addTab(self._build_rules_tab(),   self.tr("コンポーネントオーバーライド"))

        h_splitter.addWidget(self.profile_tabs)
        h_splitter.setSizes([220, 560])

        vlayout.addWidget(h_splitter)
        return group

    def _build_co2_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        self.co2_table = QTableWidget(0, 3)
        self.co2_table.setHorizontalHeaderLabels(
            [self.tr("年"), self.tr("CO₂上限 (tCO₂/年)"), self.tr("CO₂価格 (Currency/tCO₂)")])
        self.co2_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.co2_table.verticalHeader().setVisible(False)
        self.co2_table.cellChanged.connect(self._on_co2_cell_changed)
        v.addWidget(self.co2_table)

        btn_row = QHBoxLayout()
        self.co2_new_year = QSpinBox()
        self.co2_new_year.setRange(2020, 2100)
        self.co2_new_year.setValue(2030)
        btn_add = QPushButton(self.tr("年を追加"))
        btn_del = QPushButton(self.tr("選択行を削除"))
        btn_add.clicked.connect(self._add_co2_row)
        btn_del.clicked.connect(self._del_co2_row)
        btn_row.addWidget(QLabel(self.tr("年:")))
        btn_row.addWidget(self.co2_new_year)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        v.addLayout(btn_row)
        return w

    def _build_carrier_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        self.carrier_table = QTableWidget(len(CARRIERS), 5)
        self.carrier_table.setHorizontalHeaderLabels(
            [self.tr("電源種別"), self.tr("建設費 (Currency/MW)"), self.tr("変動費 (Currency/MWh)"),
             self.tr("CO₂強度 (tCO₂/MWh)"), self.tr("設備寿命 (年)")])
        self.carrier_table.verticalHeader().setVisible(False)
        self.carrier_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        for i, carrier in enumerate(CARRIERS):
            ci = QTableWidgetItem(carrier)
            ci.setFlags(ci.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.carrier_table.setItem(i, 0, ci)
            for j in range(1, 5):
                self.carrier_table.setItem(i, j, QTableWidgetItem("0"))

        self.carrier_table.cellChanged.connect(self._on_carrier_cell_changed)
        v.addWidget(self.carrier_table)
        return w

    def _build_rules_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        self._profile_label = QLabel("（プロファイルを選択してください）")
        v.addWidget(self._profile_label)

        self.rule_table = QTableWidget(0, 5)
        self.rule_table.setHorizontalHeaderLabels(
            [self.tr("種別"), self.tr("コンポーネント名"), self.tr("パラメータ"), self.tr("年"), self.tr("値")])
        self.rule_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rule_table.verticalHeader().setVisible(False)
        self.rule_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.rule_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        v.addWidget(self.rule_table)

        r_btns = QHBoxLayout()
        for label, slot in [(self.tr("ルール追加"), self._add_rule),
                             (self.tr("ルール編集"), self._edit_rule),
                             (self.tr("ルール削除"), self._del_rule)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            r_btns.addWidget(b)
        r_btns.addStretch()
        v.addLayout(r_btns)
        return w

    # ══════════════════════════════════════════════════════════════════
    # シナリオ操作
    # ══════════════════════════════════════════════════════════════════

    def _populate_scenario_table(self):
        self._block = True
        self.scenario_table.setRowCount(0)
        for s in self._net.scenarios:
            r = self.scenario_table.rowCount()
            self.scenario_table.insertRow(r)
            years_str = ", ".join(str(y) for y in sorted(s.planning_years))
            self.scenario_table.setItem(r, 0, QTableWidgetItem(s.name))
            self.scenario_table.setItem(r, 1, QTableWidgetItem(str(s.base_year)))
            self.scenario_table.setItem(r, 2, QTableWidgetItem(years_str))
            self.scenario_table.setItem(r, 3, QTableWidgetItem(_fmt(s.discount_rate)))
            mode_str = "完全予見" if s.multi_period else "単年度"
            self.scenario_table.setItem(r, 4, QTableWidgetItem(mode_str))
        self._block = False

    def _on_scenario_selected(self):
        row = self.scenario_table.currentRow()
        if row < 0 or row >= len(self._net.scenarios):
            return
        s = self._net.scenarios[row]
        self._block = True
        self.sc_name.setText(s.name)
        self.sc_base_year.setValue(s.base_year)
        self.sc_discount.setValue(s.discount_rate)
        self.sc_multi_period.setChecked(s.multi_period)
        self._populate_sc_year_table(s)
        self._block = False
        # プロファイルテーブルのチェック状態をこのシナリオに合わせて更新
        self._populate_profile_table()

    def _refresh_sc_profile_combo(self):
        """(後方互換: 何もしない)"""
        pass

    def _populate_sc_year_table(self, s: ScenarioData):
        self.sc_year_table.setRowCount(0)
        for year in sorted(s.planning_years):
            r = self.sc_year_table.rowCount()
            self.sc_year_table.insertRow(r)
            self.sc_year_table.setItem(r, 0, QTableWidgetItem(str(year)))

    def _save_scenario_fields(self):
        if self._block:
            return
        row = self.scenario_table.currentRow()
        if row < 0 or row >= len(self._net.scenarios):
            return
        s = self._net.scenarios[row]
        s.name         = self.sc_name.text().strip() or s.name
        s.base_year    = self.sc_base_year.value()
        s.discount_rate = self.sc_discount.value()
        s.multi_period  = self.sc_multi_period.isChecked()
        self._populate_scenario_table()
        self.scenario_table.selectRow(row)

    def _add_planning_year(self):
        row = self.scenario_table.currentRow()
        if row < 0 or row >= len(self._net.scenarios):
            return
        s    = self._net.scenarios[row]
        year = self.sc_new_year.value()
        if year in s.planning_years:
            QMessageBox.warning(self, self.tr("警告"), self.tr("{}年は既に追加されています。").format(year))
            return
        s.planning_years.append(year)
        s.planning_years.sort()
        self._populate_sc_year_table(s)
        self._populate_scenario_table()
        self.scenario_table.selectRow(row)

    def _del_planning_year(self):
        row = self.scenario_table.currentRow()
        if row < 0 or row >= len(self._net.scenarios):
            return
        s       = self._net.scenarios[row]
        yr_row  = self.sc_year_table.currentRow()
        if yr_row < 0:
            return
        if len(s.planning_years) <= 1:
            QMessageBox.warning(self, self.tr("警告"), self.tr("計画年は1つ以上必要です。"))
            return
        year = int(self.sc_year_table.item(yr_row, 0).text())
        s.planning_years.remove(year)
        self._populate_sc_year_table(s)
        self._populate_scenario_table()
        self.scenario_table.selectRow(row)

    def _add_scenario(self):
        name, ok = QInputDialog.getText(self, self.tr("シナリオの追加"), self.tr("シナリオ名:"))
        if not ok or not name.strip():
            return
        self._net.scenarios.append(ScenarioData(name=name.strip()))
        self._populate_scenario_table()
        self.scenario_table.selectRow(self.scenario_table.rowCount() - 1)

    def _del_scenario(self):
        row = self.scenario_table.currentRow()
        if row < 0:
            return
        if len(self._net.scenarios) <= 1:
            QMessageBox.warning(self, self.tr("警告"), self.tr("シナリオは1つ以上必要です。"))
            return
        name = self._net.scenarios[row].name
        ans  = QMessageBox.question(
            self, self.tr("削除確認"), self.tr("シナリオ「{}」を削除しますか？").format(name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._net.scenarios.pop(row)
        self._populate_scenario_table()

    # ══════════════════════════════════════════════════════════════════
    # プロファイル操作
    # ══════════════════════════════════════════════════════════════════

    def _populate_profile_table(self):
        """profile_table を再構築する。現在選択中のシナリオにリンクされたプロファイルはチェック済みになる。"""
        sc_row = self.scenario_table.currentRow()
        linked: set[str] = set()
        if 0 <= sc_row < len(self._net.scenarios):
            linked = set(self._net.scenarios[sc_row].profile_names)
        self._block = True
        self.profile_table.setRowCount(0)
        for p in self._net.scenario_profiles:
            r = self.profile_table.rowCount()
            self.profile_table.insertRow(r)
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(
                Qt.CheckState.Checked if p.name in linked else Qt.CheckState.Unchecked)
            self.profile_table.setItem(r, 0, chk)
            self.profile_table.setItem(r, 1, QTableWidgetItem(p.name))
            self.profile_table.setItem(r, 2, QTableWidgetItem(p.description))
        self._block = False

    def _on_profile_item_changed(self, item: QTableWidgetItem):
        """チェックボックス・プロファイル名・説明の変更を反映する。"""
        if self._block:
            return
        pf_row = item.row()
        if pf_row < 0 or pf_row >= len(self._net.scenario_profiles):
            return
        col = item.column()
        if col == 0:
            # チェックボックス → 現在シナリオの profile_names を更新
            sc_row = self.scenario_table.currentRow()
            if sc_row < 0 or sc_row >= len(self._net.scenarios):
                return
            s = self._net.scenarios[sc_row]
            pf_name = self._net.scenario_profiles[pf_row].name
            if item.checkState() == Qt.CheckState.Checked:
                if pf_name not in s.profile_names:
                    s.profile_names.append(pf_name)
            else:
                s.profile_names = [n for n in s.profile_names if n != pf_name]
        elif col == 1:
            # プロファイル名の変更
            new_name = item.text().strip()
            if not new_name:
                return
            p = self._net.scenario_profiles[pf_row]
            old_name = p.name
            if old_name == new_name:
                return
            # 全シナリオの profile_names 内の参照を更新
            for s in self._net.scenarios:
                s.profile_names = [new_name if n == old_name else n for n in s.profile_names]
            p.name = new_name
            # 詳細ラベルを更新
            if self._profile_label.text() == f"ルール一覧：{old_name}":
                self._profile_label.setText(f"ルール一覧：{new_name}")
        elif col == 2:
            # 説明の変更
            self._net.scenario_profiles[pf_row].description = item.text()

    def _on_profile_selected(self):
        row = self.profile_table.currentRow()
        self._populate_profile_detail(row)

    def _populate_profile_detail(self, row: int):
        if row < 0 or row >= len(self._net.scenario_profiles):
            self._profile_label.setText("（プロファイルを選択してください）")
            self.co2_table.setRowCount(0)
            self.rule_table.setRowCount(0)
            self._populate_carrier_table_from({})
            return
        p = self._net.scenario_profiles[row]
        self._profile_label.setText(f"ルール一覧：{p.name}")
        self._populate_co2_table(p)
        self._populate_carrier_table_from(p.carrier_costs)
        self._populate_rule_table(p)

    def _current_profile(self):
        row = self.profile_table.currentRow()
        if row < 0 or row >= len(self._net.scenario_profiles):
            return None
        return self._net.scenario_profiles[row]

    def _add_profile(self):
        name, ok = QInputDialog.getText(self, self.tr("プロファイルの追加"), self.tr("プロファイル名:"))
        if not ok or not name.strip():
            return
        self._net.scenario_profiles.append(ScenarioProfile(name=name.strip()))
        self._populate_profile_table()
        self.profile_table.selectRow(self.profile_table.rowCount() - 1)

    def _del_profile(self):
        row = self.profile_table.currentRow()
        if row < 0:
            return
        name = self._net.scenario_profiles[row].name
        ans  = QMessageBox.question(
            self, self.tr("削除確認"), self.tr("プロファイル「{}」を削除しますか？").format(name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes:
            return
        # 全シナリオの profile_names から当該名を除去
        for s in self._net.scenarios:
            s.profile_names = [n for n in s.profile_names if n != name]
        self._net.scenario_profiles.pop(row)
        self._populate_profile_table()
        self._populate_profile_detail(-1)

    def _move_profile_up(self):
        row = self.profile_table.currentRow()
        if row <= 0:
            return
        lst = self._net.scenario_profiles
        lst[row - 1], lst[row] = lst[row], lst[row - 1]
        self._populate_profile_table()
        self.profile_table.selectRow(row - 1)

    def _move_profile_dn(self):
        row = self.profile_table.currentRow()
        lst = self._net.scenario_profiles
        if row < 0 or row >= len(lst) - 1:
            return
        lst[row], lst[row + 1] = lst[row + 1], lst[row]
        self._populate_profile_table()
        self.profile_table.selectRow(row + 1)

    # ── CO2 tab ────────────────────────────────────────────────────────

    def _populate_co2_table(self, profile: ScenarioProfile):
        self._block = True
        self.co2_table.setRowCount(0)
        for year in sorted(profile.co2_settings.keys()):
            cfg = profile.co2_settings[year]
            r   = self.co2_table.rowCount()
            self.co2_table.insertRow(r)
            yi = QTableWidgetItem(str(year))
            yi.setFlags(yi.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.co2_table.setItem(r, 0, yi)
            self.co2_table.setItem(r, 1, QTableWidgetItem(_fmt(cfg.get("co2_limit", 1e18))))
            self.co2_table.setItem(r, 2, QTableWidgetItem(_fmt(cfg.get("co2_price", 0.0))))
        self._block = False

    def _on_co2_cell_changed(self, row, col):
        if self._block or col == 0:
            return
        p = self._current_profile()
        if p is None:
            return
        year_item = self.co2_table.item(row, 0)
        val_item  = self.co2_table.item(row, col)
        if not year_item or not val_item:
            return
        try:
            year = int(year_item.text())
            val  = float(val_item.text())
        except ValueError:
            return
        cfg = p.co2_settings.setdefault(year, {"co2_limit": 1e18, "co2_price": 0.0})
        if col == 1:
            cfg["co2_limit"] = val
        elif col == 2:
            cfg["co2_price"] = val

    def _add_co2_row(self):
        p = self._current_profile()
        if p is None:
            QMessageBox.information(self, "情報", "プロファイルを選択してください。")
            return
        year = self.co2_new_year.value()
        if year in p.co2_settings:
            QMessageBox.warning(self, "警告", f"{year}年は既に設定されています。")
            return
        p.co2_settings[year] = {"co2_limit": 1e18, "co2_price": 0.0}
        self._populate_co2_table(p)

    def _del_co2_row(self):
        p = self._current_profile()
        if p is None:
            return
        row = self.co2_table.currentRow()
        if row < 0:
            return
        year_item = self.co2_table.item(row, 0)
        if not year_item:
            return
        year = int(year_item.text())
        p.co2_settings.pop(year, None)
        self._populate_co2_table(p)

    # ── Carrier costs tab ──────────────────────────────────────────────

    def _populate_carrier_table_from(self, carrier_costs: dict):
        self._block = True
        for i, carrier in enumerate(CARRIERS):
            costs = carrier_costs.get(carrier, {})
            self.carrier_table.setItem(
                i, 1, QTableWidgetItem(_fmt(costs.get("capital_cost",  0))))
            self.carrier_table.setItem(
                i, 2, QTableWidgetItem(_fmt(costs.get("marginal_cost", 0))))
            self.carrier_table.setItem(
                i, 3, QTableWidgetItem(_fmt(costs.get("co2_intensity", 0))))
            self.carrier_table.setItem(
                i, 4, QTableWidgetItem(str(int(costs.get("lifetime",  25)))))
        self._block = False

    def _on_carrier_cell_changed(self, row, col):
        if self._block or col == 0:
            return
        p = self._current_profile()
        if p is None:
            return
        carrier  = self.carrier_table.item(row, 0)
        val_item = self.carrier_table.item(row, col)
        if not carrier or not val_item:
            return
        try:
            raw = float(val_item.text())
            val = int(raw) if col == 4 else raw
        except ValueError:
            return
        keys = {1: "capital_cost", 2: "marginal_cost", 3: "co2_intensity", 4: "lifetime"}
        p.carrier_costs.setdefault(carrier.text(), {})[keys[col]] = val

    # ── Rules tab ──────────────────────────────────────────────────────

    def _populate_rule_table(self, profile: ScenarioProfile):
        self.rule_table.setRowCount(0)
        for rule in profile.rules:
            r = self.rule_table.rowCount()
            self.rule_table.insertRow(r)
            self.rule_table.setItem(r, 0, QTableWidgetItem(rule.component_type))
            self.rule_table.setItem(r, 1, QTableWidgetItem(rule.component_name))
            self.rule_table.setItem(r, 2, QTableWidgetItem(rule.parameter))
            self.rule_table.setItem(r, 3, QTableWidgetItem(str(rule.year)))
            self.rule_table.setItem(r, 4, QTableWidgetItem(_fmt(rule.value)))

    def _add_rule(self):
        p = self._current_profile()
        if p is None:
            QMessageBox.information(self, "情報", "プロファイルを選択してください。")
            return
        dlg = RuleDialog(self, network=self._net)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            p.rules.append(dlg.get_rule())
            self._populate_rule_table(p)

    def _edit_rule(self):
        p = self._current_profile()
        if p is None:
            return
        rule_row = self.rule_table.currentRow()
        if rule_row < 0 or rule_row >= len(p.rules):
            return
        dlg = RuleDialog(self, rule=p.rules[rule_row], network=self._net)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            p.rules[rule_row] = dlg.get_rule()
            self._populate_rule_table(p)

    def _del_rule(self):
        p = self._current_profile()
        if p is None:
            return
        rule_row = self.rule_table.currentRow()
        if rule_row < 0 or rule_row >= len(p.rules):
            return
        p.rules.pop(rule_row)
        self._populate_rule_table(p)

    # ══════════════════════════════════════════════════════════════════
    # 外部インターフェース
    # ══════════════════════════════════════════════════════════════════

    def set_network(self, net: NetworkData):
        """NetworkData をロードしてUIに反映する。"""
        self._net = net
        if not self._net.scenarios:
            self._net.scenarios = [ScenarioData()]
        self._populate_scenario_table()
        self._populate_profile_table()
        self._populate_profile_detail(-1)
        if self._net.scenarios:
            self.scenario_table.selectRow(0)

    def get_network(self) -> NetworkData:
        """現在の編集内容を反映した NetworkData を返す。"""
        return self._net

    def get_scenario(self) -> ScenarioData:
        """現在選択中のシナリオを返す（後方互換）。"""
        row = self.scenario_table.currentRow()
        if 0 <= row < len(self._net.scenarios):
            return self._net.scenarios[row]
        return self._net.scenarios[0] if self._net.scenarios else ScenarioData()

    def load_scenario(self, scenario: ScenarioData):
        """旧形式互換: 単一シナリオをロードする。"""
        self._net.scenarios = [scenario]
        self._populate_scenario_table()
        if self._net.scenarios:
            self.scenario_table.selectRow(0)
