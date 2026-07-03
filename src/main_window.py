import os
from typing import Union

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QFileDialog, QMessageBox,
)
from PyQt6.QtGui import QAction, QActionGroup

from .network_editor   import NetworkEditor
from .scenario_editor  import ScenarioEditor
from .timeseries_editor import TimeSeriesEditor
from .run_panel        import RunPanel
from .results_panel    import ResultsPanel
from .models import NetworkData, ScenarioData, TimeSeriesData, OptimizationResults
from . import excel_handler
from .i18n import LANGUAGES, save_language, load_saved_language


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._current_file: str | None = None
        self.setWindowTitle("PyPSA GUI")
        self.setMinimumSize(1280, 860)
        self._default_results_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
        self._setup_ui()
        self._setup_menu()
        self.run_panel.set_output_dir(self._default_results_dir)

    def _setup_ui(self):
        self.tabs = QTabWidget()

        self.network_editor    = NetworkEditor()
        self.scenario_editor   = ScenarioEditor()
        self.timeseries_editor = TimeSeriesEditor()
        self.run_panel         = RunPanel()
        self.results_panel     = ResultsPanel()

        self.tabs.addTab(self.network_editor,    self.tr("ネットワーク"))
        self.tabs.addTab(self.scenario_editor,   self.tr("シナリオ"))
        self.tabs.addTab(self.run_panel,         "RUN")
        self.tabs.addTab(self.results_panel,     self.tr("結果"))
        # 時系列データタブはUI簡素化のため非表示。ウィジェット自体は
        # RES画面の時系列編集ダイアログや保存/読込のデータストアとして使い続ける。

        # Sync buses to time series editor when network changes
        self.network_editor.network_changed.connect(self._on_network_changed)
        # Give NetworkEditor a reference to TimeSeriesEditor for generator TS editing
        self.network_editor.set_timeseries_editor(self.timeseries_editor)
        # Switch to RUN tab triggers data sync
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.setCentralWidget(self.tabs)

    def _setup_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu(self.tr("ファイル(&F)"))

        def act(label, shortcut, slot):
            a = QAction(label, self)
            if shortcut: a.setShortcut(shortcut)
            a.triggered.connect(slot)
            return a

        fm.addAction(act(self.tr("新規作成(&N)"), "Ctrl+N", self._new))
        fm.addSeparator()
        fm.addAction(act(self.tr("プロジェクトを開く(&O)..."), "Ctrl+O", self._open_network))
        fm.addAction(act(self.tr("プロジェクトを保存(&S)..."), "Ctrl+S", self._save_network))
        fm.addSeparator()
        fm.addAction(act(self.tr("結果を開く(netCDF)..."), "Ctrl+R", self._open_results_netcdf))
        fm.addSeparator()
        fm.addAction(act(self.tr("終了(&Q)"), "Ctrl+Q", self.close))

        # ── Language menu ─────────────────────────────────────────────
        lm = mb.addMenu(self.tr("言語(&L)"))
        lang_group = QActionGroup(self)
        lang_group.setExclusive(True)
        current = load_saved_language()
        for code, label in LANGUAGES.items():
            a = QAction(label, self)
            a.setCheckable(True)
            a.setChecked(code == current)
            a.setData(code)
            a.triggered.connect(lambda checked, c=code: self._change_language(c))
            lang_group.addAction(a)
            lm.addAction(a)

        hm = mb.addMenu(self.tr("ヘルプ(&H)"))
        hm.addAction(act(self.tr("著作権情報(&A)..."), None, self._show_about))

    def _change_language(self, lang: str) -> None:
        """Save the chosen language and ask the user to restart."""
        save_language(lang)
        QMessageBox.information(
            self,
            self.tr("言語設定"),
            self.tr("言語を変更しました。アプリを再起動すると反映されます。"),
        )

    def _show_about(self):
        QMessageBox.about(
            self,
            self.tr("著作権情報"),
            "<h3>PyPSA GUI  v0.1.0</h3>"
            "<p>Copyright &copy; 2026 Takashi YANASE.<br>"
            "All rights reserved.</p>"
            "<p>本ソフトウェアは個人・研究目的に限り使用可能です。<br>"
            "<b>商用利用は禁止されています。</b></p>"
            "<p>無断複製・再配布・改変・販売を禁じます。</p>",
        )

    # ── Tab switch ────────────────────────────────────────────────────
    def _on_tab_changed(self, idx: int):
        """Push current data to RUN panel when RUN tab is selected."""
        if self.tabs.widget(idx) is self.run_panel:
            self._sync_all_to_run()

    def _sync_all_to_run(self):
        net      = self.scenario_editor.get_network()
        scenario = self.scenario_editor.get_scenario()
        self.run_panel.update_scenarios(net.scenarios if net.scenarios else [scenario])
        self.run_panel.update_profiles(net)
        self.run_panel.set_run_data(
            self.network_editor.get_network(),
            scenario,
            self.timeseries_editor.get_timeseries(),
        )

    # ── Network changed ───────────────────────────────────────────────
    def _on_network_changed(self, network: NetworkData):
        self.timeseries_editor.update_network(network)

    # ── Optimization finished ─────────────────────────────────────────
    def on_optimization_finished(self, results: Union[OptimizationResults, dict[str, OptimizationResults]]):
        if isinstance(results, dict):
            self.results_panel.load_results_map(results)
        else:
            self.results_panel.load_results(results)
        idx = self.tabs.indexOf(self.results_panel)
        self.tabs.setCurrentIndex(idx)

    # ── File menu ─────────────────────────────────────────────────────
    def _load_default_project(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "project.xlsx")
        if not os.path.isfile(path):
            return
        try:
            net, ts = excel_handler.load_network_with_timeseries(path)
            self.network_editor.load_network(net)
            self.timeseries_editor.update_network(net)
            self.timeseries_editor.load_timeseries(ts)
            self.scenario_editor.set_network(net)
            self.run_panel.update_profiles(net)
            self._set_current_file(path)
        except Exception:
            pass

    def _set_current_file(self, path: str | None) -> None:
        self._current_file = path
        if path:
            self.setWindowTitle(f"PyPSA GUI  —  {os.path.basename(path)}")
        else:
            self.setWindowTitle("PyPSA GUI")

    def _new(self):
        reply = QMessageBox.question(
            self, self.tr("確認"), self.tr("現在のデータを破棄して新規作成しますか？"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._set_current_file(None)
            net = NetworkData()
            self.network_editor.load_network(net)
            self.scenario_editor.set_network(net)
            self.timeseries_editor.load_timeseries(TimeSeriesData())

    def _open_network(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("プロジェクトファイルを開く"), "",
            "Excel Files (*.xlsx);;All Files (*)",
        )
        if not path: return
        try:
            net, ts = excel_handler.load_network_with_timeseries(path)
            self.network_editor.load_network(net)
            self.timeseries_editor.update_network(net)
            self.timeseries_editor.load_timeseries(ts)
            self.scenario_editor.set_network(net)
            self.run_panel.update_profiles(net)
            self.run_panel.set_output_dir(self._default_results_dir)
            self._set_current_file(path)
            self.tabs.setCurrentIndex(0)
            QMessageBox.information(self, self.tr("完了"), self.tr("プロジェクトを読み込みました。"))
        except Exception as e:
            QMessageBox.critical(self, self.tr("エラー"), self.tr("読み込みに失敗しました:\n") + str(e))

    def _save_network(self):
        default_path = self._current_file if self._current_file else "project.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("プロジェクトファイルを保存"), default_path,
            "Excel Files (*.xlsx);;All Files (*)",
        )
        if not path: return
        if not path.endswith(".xlsx"): path += ".xlsx"
        try:
            net = self.network_editor.get_network()
            sc_net = self.scenario_editor.get_network()
            net.scenarios        = sc_net.scenarios
            net.scenario_profiles = sc_net.scenario_profiles
            excel_handler.save_network_with_timeseries(
                net,
                self.timeseries_editor.get_timeseries(),
                path,
            )
            self._set_current_file(path)
            QMessageBox.information(self, self.tr("完了"), self.tr("プロジェクトを保存しました:\n") + path)
        except Exception as e:
            QMessageBox.critical(self, self.tr("エラー"), self.tr("保存に失敗しました:\n") + str(e))

    def _open_results_netcdf(self):
        os.makedirs(self._default_results_dir, exist_ok=True)
        paths, _ = QFileDialog.getOpenFileNames(
            self, self.tr("netCDF結果ファイルを開く"), self._default_results_dir,
            "NetCDF Files (*.nc);;All Files (*)",
        )
        if not paths:
            return
        self.results_panel.load_from_netcdf(paths)
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.results_panel))

