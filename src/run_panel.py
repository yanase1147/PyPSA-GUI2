"""Run panel: solver selector, year checkboxes, run/stop buttons, log window."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QComboBox,
    QCheckBox, QPushButton, QTextEdit, QLabel, QProgressBar, QLineEdit,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QDialogButtonBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from .models import NetworkData, ScenarioData, TimeSeriesData, OptimizationResults, YearResult, ScenarioProfile
from .pypsa_runner import OptimizationWorker


_SOLVERS = ["highs", "cplex", "gurobi", "glpk", "cbc"]


class _YearSelectionDialog(QDialog):
    def __init__(self, scenario: ScenarioData, selected_years: set[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("計画年の選択: {}").format(scenario.name))
        lay = QVBoxLayout(self)
        self._checks: dict[int, QCheckBox] = {}
        for y in sorted(scenario.planning_years):
            cb = QCheckBox(str(y))
            cb.setChecked(y in selected_years)
            lay.addWidget(cb)
            self._checks[y] = cb
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def selected_years(self) -> set[int]:
        return {y for y, cb in self._checks.items() if cb.isChecked()}


class RunPanel(QWidget):
    """Widget shown in the RUN tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: OptimizationWorker | None = None
        self._results: OptimizationResults | None = None
        self._scenarios: list[ScenarioData] = []
        self._scenario_enabled: dict[str, bool] = {}
        self._scenario_year_selection: dict[str, set[int]] = {}
        self._batch_queue: list[tuple[ScenarioData, list[int], list[ScenarioProfile]]] = []
        self._batch_results: dict[str, OptimizationResults] = {}
        self._current_batch_scenario: str = ""
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # ── Scenario selection (batch targets) ───────────────────
        sc_grp = QGroupBox(self.tr("実行対象シナリオ（シナリオごとに計画年を選択）"))
        sc_lay = QHBoxLayout(sc_grp)
        self.scenario_table = QTableWidget(0, 3)
        self.scenario_table.setHorizontalHeaderLabels(
            [self.tr("実行"), self.tr("シナリオ名"), self.tr("選択計画年")])
        self.scenario_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.scenario_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.scenario_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.scenario_table.verticalHeader().setVisible(False)
        self.scenario_table.setMaximumHeight(150)
        self.scenario_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.scenario_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.scenario_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        sc_lay.addWidget(self.scenario_table)

        sc_btn = QVBoxLayout()
        btn_year = QPushButton(self.tr("年を選択..."))
        btn_all = QPushButton(self.tr("全選択"))
        btn_none = QPushButton(self.tr("全解除"))
        btn_year.clicked.connect(self._edit_selected_scenario_years)
        btn_all.clicked.connect(self._select_all_scenarios)
        btn_none.clicked.connect(self._clear_all_scenarios)
        sc_btn.addWidget(btn_year)
        sc_btn.addWidget(btn_all)
        sc_btn.addWidget(btn_none)
        sc_btn.addStretch()
        sc_lay.addLayout(sc_btn)
        layout.addWidget(sc_grp)

        # ── Top: solver + year selection + run/stop ──────────────────
        top_row = QHBoxLayout()

        # Solver
        solver_grp = QGroupBox(self.tr("ソルバー"))
        solver_lay = QHBoxLayout(solver_grp)
        self.solver_combo = QComboBox()
        self.solver_combo.addItems(_SOLVERS)
        solver_lay.addWidget(self.solver_combo)
        top_row.addWidget(solver_grp)

        # Time step
        from PyQt6.QtWidgets import QSpinBox as _QSpinBox
        step_grp = QGroupBox(self.tr("時間解像度（ステップ）"))
        step_lay = QHBoxLayout(step_grp)
        self.snapshot_step_spin = _QSpinBox()
        self.snapshot_step_spin.setRange(1, 168)
        self.snapshot_step_spin.setValue(1)
        self.snapshot_step_spin.setSuffix(self.tr(" 時間おき"))
        self.snapshot_step_spin.setToolTip(
            "1=全8760時間（最高精度）、2=4380時間、24=365時間（1日1点）\n"
            "大規模モデルでメモリ不足が発生する場合は大きい値に設定してください。"
        )
        step_lay.addWidget(self.snapshot_step_spin)
        top_row.addWidget(step_grp)

        # Run / Stop
        btn_grp = QGroupBox(self.tr("実行"))
        btn_lay = QVBoxLayout(btn_grp)
        self.btn_run  = QPushButton(self.tr("▶ RUN"))
        self.btn_stop = QPushButton(self.tr("■ STOP"))
        self.btn_stop.setEnabled(False)
        self.btn_run.clicked.connect(self._on_run)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_run.setMinimumWidth(100)
        self.btn_stop.setMinimumWidth(100)
        btn_lay.addWidget(self.btn_run)
        btn_lay.addWidget(self.btn_stop)
        top_row.addWidget(btn_grp)

        layout.addLayout(top_row)

        # ── Output folder ─────────────────────────────────────────────
        out_grp = QGroupBox(self.tr("netCDF出力フォルダ"))
        out_lay = QHBoxLayout(out_grp)
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText(
            self.tr("フォルダを選択してくださь（空欄の場合は保存しません）"))
        self.output_dir_edit.setReadOnly(True)
        btn_browse = QPushButton(self.tr("参照..."))
        btn_browse.setFixedWidth(72)
        btn_browse.clicked.connect(self._browse_output_dir)
        out_lay.addWidget(self.output_dir_edit, stretch=1)
        out_lay.addWidget(btn_browse)
        layout.addWidget(out_grp)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)   # indeterminate
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # ── Log window ────────────────────────────────────────────────
        log_grp = QGroupBox(self.tr("ログ"))
        log_lay = QVBoxLayout(log_grp)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        # 日本語を含むログが正しく表示されるよう、日本語対応フォントを優先リストに含める
        mono = QFont()
        mono.setFamilies(["Consolas", "Yu Gothic", "Meiryo", "MS Gothic", "Courier New"])
        mono.setPointSize(9)
        self.log_view.setFont(mono)
        self.log_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        log_lay.addWidget(self.log_view)

        btn_clear = QPushButton(self.tr("ログをクリア"))
        btn_clear.clicked.connect(self.log_view.clear)
        log_lay.addWidget(btn_clear, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(log_grp, stretch=1)

    # ── Scenario selection helpers ────────────────────────────────────
    def _scenario_years_text(self, scenario_name: str) -> str:
        years = sorted(self._scenario_year_selection.get(scenario_name, set()))
        return ", ".join(str(y) for y in years) if years else self.tr("(未選択)")

    def _sync_scenario_enabled_from_table(self):
        for r in range(self.scenario_table.rowCount()):
            chk = self.scenario_table.item(r, 0)
            name = self.scenario_table.item(r, 1)
            if chk and name:
                self._scenario_enabled[name.text()] = (chk.checkState() == Qt.CheckState.Checked)

    def _update_scenario_table(self):
        self._sync_scenario_enabled_from_table()
        self.scenario_table.setRowCount(0)
        for sc in self._scenarios:
            r = self.scenario_table.rowCount()
            self.scenario_table.insertRow(r)

            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Checked if self._scenario_enabled.get(sc.name, True)
                              else Qt.CheckState.Unchecked)
            self.scenario_table.setItem(r, 0, chk)
            self.scenario_table.setItem(r, 1, QTableWidgetItem(sc.name))
            self.scenario_table.setItem(r, 2, QTableWidgetItem(self._scenario_years_text(sc.name)))

    def _edit_selected_scenario_years(self):
        row = self.scenario_table.currentRow()
        if row < 0 or row >= len(self._scenarios):
            self._append_log(self.tr("計画年を編集するシナリオを選択してくださь。"))
            return
        sc = self._scenarios[row]
        current = self._scenario_year_selection.get(sc.name, set(sc.planning_years))
        dlg = _YearSelectionDialog(sc, current, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._scenario_year_selection[sc.name] = dlg.selected_years()
            self._update_scenario_table()
            self.scenario_table.selectRow(row)

    def _select_all_scenarios(self):
        for sc in self._scenarios:
            self._scenario_enabled[sc.name] = True
        self._update_scenario_table()

    def _clear_all_scenarios(self):
        for sc in self._scenarios:
            self._scenario_enabled[sc.name] = False
        self._update_scenario_table()

    def update_profiles(self, net: NetworkData):
        """互換のため保持。実際の適用プロファイルはシナリオのprofile_namesから自動決定する。"""
        self._available_profiles: list[ScenarioProfile] = list(net.scenario_profiles)

    # ── Public API ────────────────────────────────────────────────────
    def _get_profiles_for_scenario(self, scenario: ScenarioData) -> list[ScenarioProfile]:
        available = getattr(self, "_available_profiles", [])
        profile_names = set(scenario.profile_names)
        return [p for p in available if p.name in profile_names]

    def update_scenario(self, scenario: ScenarioData):
        """後方互換: 単一シナリオを設定する（シナリオリストが未設定の場合のみ使用）。"""
        if not self._scenarios:
            self.update_scenarios([scenario])

    def update_scenarios(self, scenarios: list[ScenarioData]):
        """シナリオ一覧をRUNタブに反映する。"""
        prev_enabled = dict(self._scenario_enabled)
        prev_years = {k: set(v) for k, v in self._scenario_year_selection.items()}

        self._scenarios = list(scenarios)
        self._scenario_enabled.clear()
        self._scenario_year_selection.clear()

        for sc in self._scenarios:
            self._scenario_enabled[sc.name] = prev_enabled.get(sc.name, True)
            saved = prev_years.get(sc.name, set(sc.planning_years))
            self._scenario_year_selection[sc.name] = set(y for y in saved if y in set(sc.planning_years))
            if not self._scenario_year_selection[sc.name]:
                self._scenario_year_selection[sc.name] = set(sc.planning_years)

        self._update_scenario_table()

    def get_results(self) -> OptimizationResults | None:
        return self._results

    # ── Slots ─────────────────────────────────────────────────────────
    def _on_run(self):
        # These are set by main_window before run starts
        if not hasattr(self, "_network"):
            self._append_log(self.tr("ERROR: プロジェクトデータが設定されていません。"))
            return

        self._sync_scenario_enabled_from_table()
        run_items: list[tuple[ScenarioData, list[int], list[ScenarioProfile]]] = []
        for sc in self._scenarios:
            if not self._scenario_enabled.get(sc.name, True):
                continue
            years = sorted(self._scenario_year_selection.get(sc.name, set()))
            if not years:
                self._append_log(f"シナリオ '{sc.name}' は計画年が未選択のためスキップします。")
                continue
            run_items.append((sc, years, self._get_profiles_for_scenario(sc)))

        if not run_items:
            self._append_log(self.tr("実行対象がありません。シナリオと計画年を選択してくださь。"))
            return

        solver = self.solver_combo.currentText()
        self._append_log(f"\n開始: ソルバー={solver}  対象シナリオ={len(run_items)}")
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.setVisible(True)
        self._results = None
        self._batch_results = {}
        self._batch_queue = run_items

        output_dir     = self.output_dir_edit.text().strip() or None
        snapshot_step  = self.snapshot_step_spin.value()
        self._run_options = {
            "solver": solver,
            "output_dir": output_dir,
            "snapshot_step": snapshot_step,
        }
        self._start_next_worker()

    def _start_next_worker(self):
        if not self._batch_queue:
            self.btn_run.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self.progress.setVisible(False)
            self._append_log(self.tr("\n最適化完了。「結果」タブで確認してくださь。"))
            mw = self.window()
            if hasattr(mw, "on_optimization_finished"):
                mw.on_optimization_finished(dict(self._batch_results))
            return

        sc, years, active_profiles = self._batch_queue.pop(0)
        self._current_batch_scenario = sc.name
        self._append_log(f"\n--- シナリオ開始: {sc.name}  対象年={years} ---")

        self._worker = OptimizationWorker(
            self._network, sc, self._timeseries,
            years,
            self._run_options["solver"],
            output_dir=self._run_options["output_dir"],
            active_profiles=active_profiles,
            snapshot_step=self._run_options["snapshot_step"],
            parent=self,
        )
        self._worker.log_line.connect(self._append_log)
        self._worker.year_done.connect(self._on_year_done)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _browse_output_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("netCDF出力フォルダを選択"), self.output_dir_edit.text() or "")
        if folder:
            self.output_dir_edit.setText(folder)

    def _on_stop(self):
        if self._worker:
            self._worker.stop()
            self._batch_queue.clear()
            self._append_log(self.tr("--- 停止リクエスト送信 ---"))

    def _on_year_done(self, year: int, yr: YearResult):
        self._append_log(
            f"\n[{self._current_batch_scenario} | {year}] 完了: status={yr.status}  "
            f"objective={yr.objective:,.0f} Currency  CO₂={yr.co2_emissions:,.0f}tCO₂"
        )

    def _on_finished(self, results: OptimizationResults):
        self._results = results
        self._batch_results[results.scenario_name or self._current_batch_scenario] = results
        self._start_next_worker()

    def _append_log(self, text: str):
        self.log_view.append(text)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── Called by main_window before each run ─────────────────────────
    def set_run_data(self, network: NetworkData, scenario: ScenarioData,
                     timeseries: TimeSeriesData):
        self._network    = network
        self._scenario   = scenario
        self._timeseries = timeseries

    def set_output_dir(self, path: str):
        """Set netCDF output directory."""
        if path:
            self.output_dir_edit.setText(path)
