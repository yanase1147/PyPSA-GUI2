"""Time-series data editor (8760 h): Solar CF, Wind CF, Demand."""
import os

import openpyxl

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QFileDialog, QLabel, QMessageBox, QAbstractItemView, QSplitter,
    QProgressDialog, QApplication,
)
from PyQt6.QtCore import Qt

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from .models import TimeSeriesData, NetworkData, CF_CARRIERS

N_HOURS = 8760
_PREVIEW = 168   # show one week in table by default


class _SeriesTab(QWidget):
    """Single tab for one series type (solar CF / wind CF / demand)."""

    def __init__(self, label: str, unit: str, y_max: float,
                 selector_label: str = "バス選択", mode_toggle: bool = False, parent=None):
        super().__init__(parent)
        self.label          = label
        self.unit           = unit
        self.y_max          = y_max
        self.selector_label = selector_label
        self._mode_toggle   = mode_toggle
        self._data: dict[str, list[float]] = {}   # bus -> 8760 values
        self._current_bus: str | None = None
        self._mode: dict[str, str] = {}                      # gen_name -> "cf" | "mw"
        self._fixed_output: dict[str, bool] = {}             # gen_name -> True (固定) / False (変動)
        self._gen_meta: dict[str, tuple[bool, float]] = {}   # gen_name -> (extendable, p_nom)
        self._active_y_max: float = y_max
        self._active_unit: str = unit
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ── Top bar ───────────────────────────────────────────────────
        top = QHBoxLayout()
        top.addWidget(QLabel(f"{self.selector_label}:"))
        self.bus_combo = QComboBox()
        self.bus_combo.currentTextChanged.connect(self._on_bus_changed)
        top.addWidget(self.bus_combo)
        if self._mode_toggle:
            self.btn_mode = QPushButton("CF")
            self.btn_mode.setCheckable(True)
            self.btn_mode.setFixedWidth(52)
            self.btn_mode.setToolTip(self.tr("設備利用率 (CF) / 実出力 (MW) を切り替えます"))
            self.btn_mode.clicked.connect(self._on_mode_toggled)
            top.addWidget(self.btn_mode)
            self.btn_fixed = QPushButton(self.tr("変動"))
            self.btn_fixed.setCheckable(True)
            self.btn_fixed.setFixedWidth(52)
            self.btn_fixed.setToolTip(self.tr("出力を固定する（p_min_pu = p_max_pu）"))
            self.btn_fixed.clicked.connect(self._on_fixed_toggled)
            top.addWidget(self.btn_fixed)
        top.addStretch()

        btn_import = QPushButton(self.tr("Excelインポート"))
        btn_export = QPushButton(self.tr("Excelエクスポート"))
        btn_plot   = QPushButton(self.tr("グラフ表示"))
        btn_import.clicked.connect(self._import_excel)
        btn_export.clicked.connect(self._export_excel)
        btn_plot.clicked.connect(self._show_plot)
        for b in (btn_import, btn_export, btn_plot):
            top.addWidget(b)
        layout.addLayout(top)

        self.info_label = QLabel(self.tr("表示: 最初の168時間（1週間）"))
        layout.addWidget(self.info_label)

        # ── Splitter: table | chart ───────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.table = QTableWidget(min(N_HOURS, _PREVIEW), 2)
        self.table.setHorizontalHeaderLabels([self.tr("時刻 (h)"), self.unit])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.cellChanged.connect(self._on_cell_changed)
        _orig_kp = self.table.keyPressEvent
        def _table_kp(event, _orig=_orig_kp):
            if (event.key() == Qt.Key.Key_V and
                    event.modifiers() == Qt.KeyboardModifier.ControlModifier):
                self._paste_from_clipboard()
            else:
                _orig(event)
        self.table.keyPressEvent = _table_kp
        splitter.addWidget(self.table)

        fig = Figure(figsize=(5, 3), dpi=90, tight_layout=True)
        self.ax  = fig.add_subplot(111)
        self.canvas = FigureCanvas(fig)
        splitter.addWidget(self.canvas)
        splitter.setSizes([300, 400])

        layout.addWidget(splitter)

    # ------------------------------------------------------------------
    def set_keys(self, key_names: list[str]):
        """Populate the selector with bus names or generator names."""
        current = self.bus_combo.currentText()
        self.bus_combo.blockSignals(True)
        self.bus_combo.clear()
        self.bus_combo.addItems(key_names)
        if current in key_names:
            self.bus_combo.setCurrentText(current)
        self.bus_combo.blockSignals(False)
        self._on_bus_changed(self.bus_combo.currentText())

    def get_data(self) -> dict[str, list[float]]:
        return self._data

    def set_data(self, data: dict[str, list[float]]):
        self._data = {k: list(v) for k, v in data.items()}
        self._on_bus_changed(self.bus_combo.currentText())

    def ensure_key(self, key_name: str):
        if key_name and key_name not in self._data:
            self._data[key_name] = [0.0] * N_HOURS

    # ------------------------------------------------------------------
    def _on_bus_changed(self, bus_name: str):
        self._current_bus = bus_name
        if not bus_name:
            return
        self.ensure_key(bus_name)
        self._update_mode_button()
        self._update_fixed_button()
        self._reload_table()
        self._update_chart()

    def _reload_table(self):
        if not self._current_bus:
            return
        vals = self._data.get(self._current_bus, [0.0] * N_HOURS)
        self.table.blockSignals(True)
        self.table.setRowCount(N_HOURS)
        for r, v in enumerate(vals[:N_HOURS]):
            hour_item = QTableWidgetItem(str(r))
            hour_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(r, 0, hour_item)
            self.table.setItem(r, 1, QTableWidgetItem(f"{v:.4f}"))
        self.table.blockSignals(False)
        self.info_label.setText(
            f"全{N_HOURS}時間  "
            f"平均: {sum(vals)/N_HOURS:.3f}  最大: {max(vals):.3f}"
        )

    def _on_cell_changed(self, row, col):
        if col != 1 or not self._current_bus:
            return
        item = self.table.item(row, col)
        if not item:
            return
        try:
            val = float(item.text())
            val = max(0.0, min(self._active_y_max, val))
        except ValueError:
            return
        vals = self._data.setdefault(self._current_bus, [0.0] * N_HOURS)
        if row < len(vals):
            vals[row] = val
        self._update_chart()

    def _paste_from_clipboard(self):
        if not self._current_bus:
            return
        text = QApplication.clipboard().text()
        if not text:
            return
        lines = text.splitlines()
        start_row = self.table.currentRow()
        if start_row < 0:
            start_row = 0
        vals = self._data.setdefault(self._current_bus, [0.0] * N_HOURS)
        self.table.blockSignals(True)
        for i, line in enumerate(lines):
            r = start_row + i
            if r >= N_HOURS:
                break
            cell_text = line.split('\t')[0].strip()
            try:
                val = float(cell_text)
                val = max(0.0, min(self._active_y_max, val))
                vals[r] = val
                item = self.table.item(r, 1)
                if item is None:
                    item = QTableWidgetItem()
                    self.table.setItem(r, 1, item)
                item.setText(f"{val:.4f}")
            except ValueError:
                continue
        self.table.blockSignals(False)
        self._update_chart()

    def _update_chart(self):
        if not self._current_bus:
            return
        vals = self._data.get(self._current_bus, [0.0] * N_HOURS)
        self.ax.clear()
        self.ax.plot(vals, linewidth=0.6, color="#2980b9")
        self.ax.set_xlabel("時刻 (h)")
        self.ax.set_ylabel(self._active_unit)
        self.ax.set_title(f"{self.label} — {self._current_bus}")
        self.ax.set_xlim(0, N_HOURS)
        self.canvas.draw()

    def _show_plot(self):
        if not self._current_bus:
            return
        vals = self._data.get(self._current_bus, [0.0] * N_HOURS)
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(vals, linewidth=0.5)
        ax.set_xlabel("時刻 (h)")
        ax.set_ylabel(self._active_unit)
        ax.set_title(f"{self.label} — {self._current_bus}")
        fig.tight_layout()
        plt.show()

    def _import_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, f"{self.label} Excelインポート", "",
            "Excel Files (*.xlsx);;All Files (*)")
        if not path:
            return
        try:
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            ws = wb.active
            rows = ws.iter_rows(values_only=True)
            header = next(rows, None)
            if not header:
                wb.close()
                return
            buses = [str(b) for b in header if b is not None]
            data: dict[str, list[float]] = {b: [] for b in buses}
            for row in rows:
                for i, b in enumerate(buses):
                    val = row[i] if i < len(row) else None
                    try:
                        data[b].append(float(val) if val is not None else 0.0)
                    except (TypeError, ValueError):
                        data[b].append(0.0)
            wb.close()
            for b in buses:
                d = data[b]
                if len(d) < N_HOURS:
                    d.extend([0.0] * (N_HOURS - len(d)))
                self._data[b] = d[:N_HOURS]
            self._on_bus_changed(self.bus_combo.currentText())
            QMessageBox.information(self, self.tr("完了"), self.tr("Excelをインポートしました: ") + os.path.basename(path))
        except Exception as e:
            QMessageBox.critical(self, self.tr("エラー"), self.tr("インポート失敗:\n") + str(e))

    def _export_excel(self):
        if not self._data:
            QMessageBox.information(self, self.tr("情報"), self.tr("データがありません。"))
            return
        default_name = f"{self.label.lower().replace(' ', '_')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("{} Excelエクスポート").format(self.label), default_name,
            "Excel Files (*.xlsx);;All Files (*)")
        if not path:
            return
        try:
            wb = openpyxl.Workbook(write_only=True)
            ws = wb.create_sheet()
            buses = list(self._data.keys())
            ws.append(buses)
            for h in range(N_HOURS):
                ws.append([self._data[b][h] if h < len(self._data[b]) else 0.0
                           for b in buses])
            wb.save(path)
            QMessageBox.information(self, self.tr("完了"), self.tr("Excelをエクスポートしました:\n") + path)
        except Exception as e:
            QMessageBox.critical(self, self.tr("エラー"), self.tr("エクスポート失敗:\n") + str(e))

    # ------------------------------------------------------------------
    # Mode toggle helpers
    # ------------------------------------------------------------------
    def set_generator_meta(self, meta: dict[str, tuple[bool, float]]):
        """meta: {gen_name: (p_nom_extendable, p_nom)}"""
        self._gen_meta = meta
        self._update_mode_button()

    def get_mode(self) -> dict[str, str]:
        return dict(self._mode)

    def set_mode(self, mode: dict[str, str]):
        self._mode = dict(mode)
        self._update_mode_button()

    def _update_mode_button(self):
        if not self._mode_toggle:
            return
        key = self._current_bus
        if not key:
            self.btn_mode.setEnabled(True)
            return
        extendable, p_nom = self._gen_meta.get(key, (False, self.y_max))
        if extendable:
            self._mode[key] = "cf"
            self.btn_mode.setChecked(False)
            self.btn_mode.setText("CF")
            self.btn_mode.setEnabled(False)
            self.btn_mode.setToolTip(self.tr("拡張可能発電機はCFモード固定です（p_nomが未確定のためMW入力不可）"))
        else:
            self.btn_mode.setEnabled(True)
            is_mw = self._mode.get(key, "cf") == "mw"
            self.btn_mode.setChecked(is_mw)
            self.btn_mode.setText("MW" if is_mw else "CF")
            self.btn_mode.setToolTip(self.tr("設備利用率 (CF) / 実出力 (MW) を切り替えます"))
        self._sync_active_params()

    def _on_mode_toggled(self, checked: bool):
        if not self._current_bus:
            return
        self._mode[self._current_bus] = "mw" if checked else "cf"
        self.btn_mode.setText("MW" if checked else "CF")
        self._sync_active_params()
        self._reload_table()
        self._update_chart()

    def _sync_active_params(self):
        key = self._current_bus
        is_mw = bool(key and self._mode.get(key, "cf") == "mw")
        if is_mw:
            _, p_nom = self._gen_meta.get(key, (False, 1e9))
            self._active_y_max = p_nom if p_nom > 0 else 1e9
            self._active_unit = self.tr("出力 (MW)")
        else:
            self._active_y_max = self.y_max
            self._active_unit = self.unit
        self.table.setHorizontalHeaderLabels([self.tr("時刻 (h)"), self._active_unit])

    # ------------------------------------------------------------------
    # Fixed-output helpers
    # ------------------------------------------------------------------
    def get_fixed_output(self) -> dict[str, bool]:
        return dict(self._fixed_output)

    def set_fixed_output(self, data: dict[str, bool]):
        self._fixed_output = dict(data)
        self._update_fixed_button()

    def _update_fixed_button(self):
        if not self._mode_toggle:
            return
        key = self._current_bus
        if not key:
            self.btn_fixed.setEnabled(False)
            return
        extendable, _ = self._gen_meta.get(key, (False, self.y_max))
        if extendable:
            self._fixed_output[key] = False
            self.btn_fixed.setChecked(False)
            self.btn_fixed.setText(self.tr("変動"))
            self.btn_fixed.setEnabled(False)
            self.btn_fixed.setToolTip(self.tr("拡張可能発電機は出力固定できません（p_nomが未確定）"))
        else:
            self.btn_fixed.setEnabled(True)
            is_fixed = self._fixed_output.get(key, False)
            self.btn_fixed.setChecked(is_fixed)
            self.btn_fixed.setText(self.tr("固定") if is_fixed else self.tr("変動"))
            self.btn_fixed.setToolTip(self.tr("出力を固定する（p_min_pu = p_max_pu）"))

    def _on_fixed_toggled(self, checked: bool):
        if not self._current_bus:
            return
        self._fixed_output[self._current_bus] = checked
        self.btn_fixed.setText(self.tr("固定") if checked else self.tr("変動"))


class TimeSeriesEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        info = QLabel(
            self.tr("太陽光・風力の設備利用率（0～1）と時間別需要（MW）を設定します。"
            " Excelフォーマット: 1行目=バス名、2行目以降=8760時間分の値")
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.tabs = QTabWidget()
        self.solar_tab   = _SeriesTab(self.tr("太陽光 CF"),    self.tr("設備利用率 (-)"), 1.0, selector_label=self.tr("発電設備選択"), mode_toggle=True)
        self.wind_tab    = _SeriesTab(self.tr("風力 CF"),      self.tr("設備利用率 (-)"), 1.0, selector_label=self.tr("発電設備選択"), mode_toggle=True)
        self.hydro_tab   = _SeriesTab(self.tr("水力 CF"),      self.tr("設備利用率 (-)"), 1.0, selector_label=self.tr("発電設備選択"), mode_toggle=True)
        self.biomass_tab = _SeriesTab(self.tr("バイオマス CF"), self.tr("設備利用率 (-)"), 1.0, selector_label=self.tr("発電設備選択"), mode_toggle=True)
        self.demand_tab  = _SeriesTab(self.tr("需要"),          self.tr("需要 (MW)"),     1e9, selector_label=self.tr("負荷選択"))
        self.tabs.addTab(self.solar_tab,   self.tr("太陽光 CF"))
        self.tabs.addTab(self.wind_tab,    self.tr("風力 CF"))
        self.tabs.addTab(self.hydro_tab,   self.tr("水力 CF"))
        self.tabs.addTab(self.biomass_tab, self.tr("バイオマス CF"))
        self.tabs.addTab(self.demand_tab,  self.tr("需要 (MW)"))
        layout.addWidget(self.tabs)

    # ------------------------------------------------------------------
    def update_network(self, network: NetworkData):
        """Sync selector lists: solar/wind/hydro tabs use generator names, demand tab uses area|carrier keys."""
        solar_gens   = [g for g in network.all_generators if g.carrier == "Solar"]
        wind_gens    = [g for g in network.all_generators
                        if g.carrier in ("Wind", "Wave and Tidal")]
        hydro_gens   = [g for g in network.all_generators if g.carrier == "Hydro"]
        biomass_gens = [g for g in network.all_generators if g.carrier == "Biomass"]
        demand_keys  = sorted(TimeSeriesData.make_load_key(ld.area, ld.name) for ld in network.all_loads)

        self.solar_tab.set_keys([g.name for g in solar_gens])
        self.wind_tab.set_keys([g.name for g in wind_gens])
        self.hydro_tab.set_keys([g.name for g in hydro_gens])
        self.biomass_tab.set_keys([g.name for g in biomass_gens])
        self.demand_tab.set_keys(demand_keys)

        self.solar_tab.set_generator_meta(
            {g.name: (g.p_nom_extendable, g.p_nom) for g in solar_gens})
        self.wind_tab.set_generator_meta(
            {g.name: (g.p_nom_extendable, g.p_nom) for g in wind_gens})
        self.hydro_tab.set_generator_meta(
            {g.name: (g.p_nom_extendable, g.p_nom) for g in hydro_gens})
        self.biomass_tab.set_generator_meta(
            {g.name: (g.p_nom_extendable, g.p_nom) for g in biomass_gens})

        for g in solar_gens:
            self.solar_tab.ensure_key(g.name)
        for g in wind_gens:
            self.wind_tab.ensure_key(g.name)
        for g in hydro_gens:
            self.hydro_tab.ensure_key(g.name)
        for g in biomass_gens:
            self.biomass_tab.ensure_key(g.name)
        for bus_key in demand_keys:
            self.demand_tab.ensure_key(bus_key)

    def update_buses(self, network: NetworkData):
        """Backward-compat alias."""
        self.update_network(network)

    def get_timeseries(self) -> TimeSeriesData:
        ts_mode: dict[str, str] = {}
        fixed_output: dict[str, bool] = {}
        for tab in (self.solar_tab, self.wind_tab, self.hydro_tab, self.biomass_tab):
            ts_mode.update(tab.get_mode())
            fixed_output.update(tab.get_fixed_output())
        return TimeSeriesData(
            solar_cf     = self.solar_tab.get_data(),
            wind_cf      = self.wind_tab.get_data(),
            hydro_cf     = self.hydro_tab.get_data(),
            biomass_cf   = self.biomass_tab.get_data(),
            demand_mw    = self.demand_tab.get_data(),
            ts_mode      = ts_mode,
            fixed_output = fixed_output,
        )

    def load_timeseries(self, ts: TimeSeriesData):
        self.solar_tab.set_data(ts.solar_cf)
        self.wind_tab.set_data(ts.wind_cf)
        self.hydro_tab.set_data(ts.hydro_cf)
        self.biomass_tab.set_data(ts.biomass_cf)
        self.demand_tab.set_data(ts.demand_mw)
        for tab in (self.solar_tab, self.wind_tab, self.hydro_tab, self.biomass_tab):
            tab.set_mode(ts.ts_mode)
            tab.set_fixed_output(ts.fixed_output)
