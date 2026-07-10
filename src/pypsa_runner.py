"""QThread worker that runs PyPSA optimization for one or more planning years."""
from __future__ import annotations

import io
import logging
import os
import re
import sys
import tempfile
import traceback
from contextlib import redirect_stdout, redirect_stderr

# ANSI エスケープシーケンスを除去する正規表現
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
# tqdm 進捗バー行を検出する正規表現 (例: "Writing constraints.:  25%|####  | 3/12 [00:00<00:00, 21it/s]")
_TQDM_RE = re.compile(r'.*\d+%\|')

from PyQt6.QtCore import QThread, pyqtSignal

from .models import NetworkData, ScenarioData, TimeSeriesData, OptimizationResults, YearResult, CF_CARRIERS, ScenarioProfile
from .config_generator import build_network


class OptimizationWorker(QThread):
    """Run PyPSA optimize() in a background thread.

    Signals
    -------
    log_line(str)        — one line of text for the log window
    year_done(int, YearResult) — emitted after each planning year finishes
    finished(OptimizationResults) — emitted when all years complete (or error)
    """
    log_line  = pyqtSignal(str)
    year_done = pyqtSignal(int, object)   # (year, YearResult)
    finished  = pyqtSignal(object)        # OptimizationResults

    def __init__(
        self,
        network: NetworkData,
        scenario: ScenarioData,
        timeseries: TimeSeriesData,
        years: list[int],
        solver: str = "highs",
        output_dir: str | None = None,
        active_profiles: list[ScenarioProfile] | None = None,
        snapshot_step: int = 1,
        parent=None,
    ):
        super().__init__(parent)
        self._network         = network
        self._scenario        = scenario
        self._timeseries      = timeseries
        self._years           = years
        self._solver          = solver
        self._output_dir      = output_dir
        self._active_profiles = active_profiles or []
        self._snapshot_step   = max(1, snapshot_step)
        self._stop            = False

    def stop(self):
        self._stop = True

    # ------------------------------------------------------------------
    def run(self):
        results = OptimizationResults(scenario_name=self._scenario.name)
        full_log: list[str] = []

        for year in self._years:
            if self._stop:
                self._emit_log("--- ユーザーによって停止されました ---")
                break

            self._emit_log(f"\n{'='*60}")
            self._emit_log(f"  計画年 {year} の最適化を開始します")
            self._emit_log(f"{'='*60}")

            yr = self._run_year(year, full_log)
            results.year_results.append(yr)
            self.year_done.emit(year, yr)

        results.log = "\n".join(full_log)
        self.finished.emit(results)

    # ------------------------------------------------------------------
    def _run_year(self, year: int, full_log: list[str]) -> YearResult:
        yr = YearResult(year=year, snapshot_step=max(1, self._snapshot_step))
        buf = _LogBuffer(self._emit_log, full_log)
        log_handler = _QtLogHandler(self._emit_log, full_log)
        log_handler.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))

        # Attach to pypsa and linopy loggers so their logging.* calls appear in the GUI
        _target_loggers = [logging.getLogger(n) for n in ("pypsa", "linopy")]
        for lg in _target_loggers:
            lg.addHandler(log_handler)
            if lg.level == logging.NOTSET or lg.level > logging.DEBUG:
                lg.setLevel(logging.DEBUG)

        try:
            self._emit_log(f"[{year}] ネットワークを構築中…")
            n = build_network(self._network, self._scenario, self._timeseries,
                              year, active_profiles=self._active_profiles,
                              solver_name=self._solver,
                              snapshot_step=self._snapshot_step)

            self._emit_log(f"[{year}] ソルバー: {self._solver}  最適化開始…")

            solver_opts = {
                "simplex_scale_strategy": 2,
                "simplex_crash_strategy": 9,  # reduce memory by using crash basis
            }
            with redirect_stdout(buf), redirect_stderr(buf):
                status, cond = n.optimize(solver_name=self._solver,
                                          solver_options=solver_opts)

            yr.status = str(status) if status else "unknown"
            self._emit_log(f"[{year}] ステータス: {yr.status}  条件: {cond}")

            if yr.status in ("ok", "optimal", "feasible"):
                yr.objective = float(n.objective) if hasattr(n, "objective") else 0.0
                self._extract_results(n, yr)
                self._extract_timeseries(n, yr)
                self._emit_log(f"[{year}] 目的関数値: {yr.objective:,.0f} Currency")
                self._emit_log(f"[{year}] CO₂排出量: {yr.co2_emissions:,.0f} tCO₂")
                self._save_netcdf(n, year)
            else:
                self._emit_log(f"[{year}] 最適化失敗: {yr.status}")

        except MemoryError:
            tb = traceback.format_exc()
            step = max(1, self._snapshot_step)
            msg = (
                f"[{year}] メモリ不足エラー (MemoryError: bad allocation)\n"
                f"  現在の snapshot_step = {step} "
                f"({'全時点' if step == 1 else f'約{8760 // step}時点'})\n"
                f"  対策: 実行パネルの「スナップショット間隔」を大きくしてください。\n"
                f"        例) step=24 → 約365時点 (メモリ使用量を大幅削減)\n"
                f"            step=8  → 約1095時点\n"
                f"  詳細:\n{tb}"
            )
            self._emit_log(msg)
            yr.status = "error"
            full_log.append(msg)

        except Exception:
            tb = traceback.format_exc()
            self._emit_log(f"[{year}] エラー:\n{tb}")
            yr.status = "error"
            full_log.append(tb)

        finally:
            for lg in _target_loggers:
                lg.removeHandler(log_handler)

        return yr

    # ------------------------------------------------------------------
    def _extract_timeseries(self, n, yr: YearResult):
        extract_year_timeseries(n, yr)

    # ------------------------------------------------------------------
    def _make_filename(self, year: int) -> str:
        import re
        def sanitize(s: str) -> str:
            return re.sub(r'[\\/:*?"<>|]', '_', s).strip('_ ') or "unnamed"
        step_part = f"step{max(1, int(self._snapshot_step))}"
        parts = ["result", sanitize(self._scenario.name), str(year), step_part]
        for p in self._active_profiles:
            parts.append(sanitize(p.name))
        return "_".join(parts) + ".nc"

    def _save_netcdf(self, n, year: int):
        if not self._output_dir:
            return
        try:
            os.makedirs(self._output_dir, exist_ok=True)
            final_path = os.path.join(self._output_dir, self._make_filename(year))
            # Windows: netCDF4 C ライブラリが非ASCII パスを扱えない場合があるため
            # ASCII 名の一時ファイルに保存してからリネームする
            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.nc', dir=self._output_dir)
            os.close(tmp_fd)
            try:
                n.export_to_netcdf(tmp_path)
                # os.replace は Windows Unicode API (MoveFileExW) を使いアトミックに上書きする
                os.replace(tmp_path, final_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            self._emit_log(f"[{year}] netCDF保存: {final_path}")
        except Exception:
            tb = traceback.format_exc()
            self._emit_log(f"[{year}] netCDF保存エラー:\n{tb}")

    # ------------------------------------------------------------------
    def _extract_results(self, n, yr: YearResult):
        extract_year_results(n, yr)

    # ------------------------------------------------------------------
    def _emit_log(self, text: str):
        self.log_line.emit(text)


class _LogBuffer(io.StringIO):
    """Capture stdout/stderr from PyPSA/solver and forward to Qt signal."""
    def __init__(self, emit_fn, full_log: list[str]):
        super().__init__()
        self._emit = emit_fn
        self._full = full_log
        self._buf  = ""

    def write(self, s: str) -> int:
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            # \r が含まれる場合は最後のセグメントのみ使用 (tqdm の上書き動作を模倣)
            if "\r" in line:
                line = line.rsplit("\r", 1)[-1]
            # ANSI コードを除去してから tqdm 進捗バー行かどうか判定
            plain = _ANSI_RE.sub("", line)
            if _TQDM_RE.match(plain):
                continue  # 進捗バー行は表示しない
            self._emit(line)
            self._full.append(line)
        return len(s)

    def flush(self):
        if self._buf:
            self._emit(self._buf)
            self._full.append(self._buf)
            self._buf = ""


class _QtLogHandler(logging.Handler):
    """Forward Python logging records (from pypsa/linopy) to the Qt signal."""
    def __init__(self, emit_fn, full_log: list[str]):
        super().__init__()
        self._emit = emit_fn
        self._full = full_log

    def emit(self, record: logging.LogRecord):
        line = self.format(record)
        self._emit(line)
        self._full.append(line)


# ======================================================================
# Module-level extraction helpers (shared with results_panel for netCDF loading)
# ======================================================================

def extract_year_results(n, yr: YearResult) -> None:
    """Populate YearResult summary fields from an optimized pypsa.Network."""
    # ── Generators ────────────────────────────────────────────────────
    if not n.generators.empty:
        p_nom_opt = n.generators.get("p_nom_opt", n.generators.get("p_nom", 0))
        for carrier in n.generators.carrier.unique():
            mask = n.generators.carrier == carrier
            cap  = float(p_nom_opt[mask].sum())
            yr.capacity_by_carrier[carrier] = yr.capacity_by_carrier.get(carrier, 0) + cap

            if hasattr(n, "generators_t") and "p" in n.generators_t:
                gen_mwh = float(n.generators_t.p.loc[:, mask.index[mask]].sum().sum())
            else:
                gen_mwh = 0.0
            yr.generation_by_carrier[carrier] = (
                yr.generation_by_carrier.get(carrier, 0) + gen_mwh)

            cap_cost = float((n.generators.loc[mask, "capital_cost"] * p_nom_opt[mask]).sum())
            yr.capex_by_carrier[carrier] = yr.capex_by_carrier.get(carrier, 0) + cap_cost

            if hasattr(n, "generators_t") and "p" in n.generators_t:
                marg = n.generators.loc[mask, "marginal_cost"]
                p_t  = n.generators_t.p.loc[:, mask.index[mask]]
                opex = float((p_t * marg).sum().sum())
            else:
                opex = 0.0
            yr.opex_by_carrier[carrier] = yr.opex_by_carrier.get(carrier, 0) + opex

    # ── CO₂ emissions ─────────────────────────────────────────────────
    total_co2 = 0.0
    if not n.generators.empty and hasattr(n, "generators_t") and "p" in n.generators_t:
        for carrier in n.generators.carrier.unique():
            co2_int = (n.carriers.loc[carrier, "co2_emissions"]
                       if carrier in n.carriers.index else 0.0)
            mask = n.generators.carrier == carrier
            eff  = n.generators.loc[mask, "efficiency"].fillna(1.0)
            p_t  = n.generators_t.p.loc[:, mask.index[mask]]
            total_co2 += float((p_t / eff * co2_int).sum().sum())
    yr.co2_emissions = total_co2


def extract_year_timeseries(n, yr: YearResult) -> None:
    """Populate YearResult hourly time-series fields from an optimized pypsa.Network."""
    import pandas as pd

    # Generator dispatch grouped by carrier
    if not n.generators.empty and hasattr(n, "generators_t") and "p" in n.generators_t:
        gen_p = n.generators_t.p
        carrier_cols = {}
        for carrier in n.generators.carrier.unique():
            mask  = n.generators.carrier == carrier
            units = [u for u in mask.index[mask] if u in gen_p.columns]
            if units:
                carrier_cols[carrier] = gen_p[units].sum(axis=1)
        if carrier_cols:
            yr.dispatch_df = pd.DataFrame(carrier_cols)

    # Links that cross the AC boundary: pumped hydro (Link + Store + Water bus)
    # as well as any sector-coupling Converter whose bus0/bus1 sits on the AC bus
    # (heat pump, electrolyzer, CHP, gas boiler, etc.). One endpoint is on an
    # AC-carrier bus and the other is not → the AC-side flow is treated as either
    # generation (non-AC → AC) or demand (AC → non-AC) in the supply-demand
    # balance chart, grouped by the *other* bus's carrier (e.g. "Water", "heat",
    # "hydrogen", "gas").
    # PyPSA sign convention: p1 = -efficiency * p0 → p1 is NEGATIVE in stored results.
    ac_boundary_links: set = set()
    if not n.links.empty and hasattr(n, "links_t"):
        bus_carrier = n.buses["carrier"] if "carrier" in n.buses.columns else pd.Series(dtype=str)

        def _is_ac_bus(bus_name: str) -> bool:
            return bus_carrier.get(bus_name, "") == "AC"

        gen_cols: dict = {}
        charge_cols: dict = {}

        p0_df = n.links_t.p0 if "p0" in n.links_t else pd.DataFrame()
        p1_df = n.links_t.p1 if "p1" in n.links_t else pd.DataFrame()

        for lk_name, lk in n.links.iterrows():
            bus0_ac = _is_ac_bus(lk.bus0)
            bus1_ac = _is_ac_bus(lk.bus1)

            # Both AC (inter-area transmission) or neither AC → not part of the
            # AC supply-demand balance chart.
            if bus0_ac == bus1_ac:
                continue

            ac_boundary_links.add(lk_name)

            if bus0_ac:
                # AC → non-AC: power leaves the AC bus (pump / sector coupling)
                if lk_name in p0_df.columns:
                    label = bus_carrier.get(lk.bus1, lk_name)
                    charge_cols[label] = charge_cols.get(
                        label, pd.Series(0.0, index=n.snapshots)) - p0_df[lk_name]
            else:
                # non-AC → AC: power enters the AC bus (turbine / fuel cell / CHP)
                label = bus_carrier.get(lk.bus0, lk_name)
                if lk_name in p1_df.columns:
                    gen = -p1_df[lk_name]
                elif lk_name in p0_df.columns:
                    gen = p0_df[lk_name] * float(lk.get("efficiency", 1.0))
                else:
                    continue
                gen_cols[label] = gen_cols.get(
                    label, pd.Series(0.0, index=n.snapshots)) + gen

        if gen_cols:
            yr.link_gen_df = pd.DataFrame(gen_cols)
        if charge_cols:
            yr.link_charge_df = pd.DataFrame(charge_cols)

    # AC-carrier Link power flow (p0 per individual link) — pure inter-area
    # transmission only. Links already classified as AC-boundary-crossing above
    # (pumped hydro, sector-coupling converters) are excluded here so they don't
    # get double-counted / misidentified as transmission lines.
    if not n.links.empty and hasattr(n, "links_t") and "p0" in n.links_t:
        p0_df = n.links_t.p0
        carrier_col = n.links.get("carrier", pd.Series("", index=n.links.index)).fillna("")
        ac_links = [
            lk for lk in n.links.index[carrier_col == "AC"]
            if lk in p0_df.columns and lk not in ac_boundary_links
        ]
        if ac_links:
            yr.link_flow_df = p0_df[ac_links].copy()

    # Renewable curtailment (p_max_pu * p_nom_opt - p) per CF carrier
    if not n.generators.empty and hasattr(n, "generators_t") and "p" in n.generators_t:
        import numpy as np
        gen_p = n.generators_t.p
        p_max_t = n.generators_t.p_max_pu if "p_max_pu" in n.generators_t else pd.DataFrame()
        curtailment_cols: dict = {}
        for carrier in CF_CARRIERS:
            mask  = n.generators.carrier == carrier
            units = [u for u in n.generators.index[mask] if u in gen_p.columns]
            if not units:
                continue
            total = pd.Series(0.0, index=n.snapshots)
            for unit in units:
                if unit not in p_max_t.columns:
                    continue  # 時系列制約なし → 経済的非選択でありカーテイルメントではない
                p_nom_opt = (n.generators.at[unit, "p_nom_opt"]
                             if "p_nom_opt" in n.generators.columns
                             else n.generators.at[unit, "p_nom"])
                p_max = p_max_t[unit] * float(p_nom_opt)
                total += np.maximum(p_max - gen_p[unit], 0.0)
            if total.sum() > 1e-3:
                curtailment_cols[carrier] = total
        if curtailment_cols:
            yr.curtailment_df = pd.DataFrame(curtailment_cols)

    # Total demand
    if hasattr(n, "loads_t"):
        if "p_set" in n.loads_t and not n.loads_t.p_set.empty:
            yr.demand_ts = n.loads_t.p_set.sum(axis=1)
        elif "p" in n.loads_t and not n.loads_t.p.empty:
            yr.demand_ts = n.loads_t.p.sum(axis=1)
