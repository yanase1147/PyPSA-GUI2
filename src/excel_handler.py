import json
import dataclasses
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from .models import (
    NetworkData, Area, AreaRES, Generator, Interconnection, Load, Store, PumpedHydro,
    Converter, ComponentTemplate, SubComponentDef, CustomComponentInstance,
    ScenarioData, ComponentOverrideRule, ScenarioProfile,
    TimeSeriesData,
)

_HDR_FILL  = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
_HDR_FONT  = Font(color="FFFFFF", bold=True)
_HDR_ALIGN = Alignment(horizontal="center")

N_HOURS = 8760


def _style_ws(ws):
    for cell in ws[1]:
        cell.fill  = _HDR_FILL
        cell.font  = _HDR_FONT
        cell.alignment = _HDR_ALIGN
    for col in ws.columns:
        width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = max(12, width + 3)


def _flt(d, k, default=0.0):
    v = d.get(k)
    return float(v) if v is not None else default

def _boo(d, k):
    v = d.get(k)
    if isinstance(v, bool): return v
    return str(v).lower() in ("true", "1", "yes")

def _itn(d, k, default=2020):
    v = d.get(k)
    return int(v) if v is not None else default


# ══════════════════════════════════════════════════════════════════════
# Network
# ══════════════════════════════════════════════════════════════════════

def _write_network_sheets(wb, network: NetworkData):
    """Add network sheets (areas/generators/…) to an existing workbook."""
    ws = wb.create_sheet("areas")
    ws.append(["name", "lat", "lon", "country"])
    for a in network.areas:
        ws.append([a.name, a.lat, a.lon, a.country])
    _style_ws(ws)

    ws = wb.create_sheet("carriers")
    ws.append(["name", "is_default"])
    for c in network.user_carriers:
        ws.append([c, False])
    _style_ws(ws)

    ws = wb.create_sheet("generators")
    ws.append(["name", "area", "carrier", "bus_carrier", "p_nom", "p_nom_extendable", "p_nom_max",
               "marginal_cost", "capital_cost", "efficiency", "build_year",
               "p_max_pu", "p_min_pu",
               "committable", "min_up_time", "ramp_limit_up", "ramp_limit_down", "lifetime"])
    for g in network.all_generators:
        ws.append([g.name, g.area, g.carrier, g.bus_carrier, g.p_nom, g.p_nom_extendable,
                   g.p_nom_max, g.marginal_cost, g.capital_cost,
                   g.efficiency, g.build_year, g.p_max_pu, g.p_min_pu,
                   g.committable, g.min_up_time, g.ramp_limit_up, g.ramp_limit_down,
                   g.lifetime])
    _style_ws(ws)

    ws = wb.create_sheet("interconnections")
    ws.append(["name", "area0", "area1", "carrier", "efficiency", "p_nom", "p_nom_reverse",
               "p_nom_extendable", "capital_cost", "marginal_cost", "build_year", "lifetime"])
    for ic in network.interconnections:
        ws.append([ic.name, ic.area0, ic.area1, ic.carrier, ic.efficiency, ic.p_nom,
                   ic.p_nom_reverse, ic.p_nom_extendable, ic.capital_cost, ic.marginal_cost,
                   ic.build_year, ic.lifetime])
    _style_ws(ws)

    ws = wb.create_sheet("loads")
    ws.append(["name", "area", "p_set", "bus_carrier"])
    for ld in network.all_loads:
        ws.append([ld.name, ld.area, ld.p_set, ld.bus_carrier])
    _style_ws(ws)

    ws = wb.create_sheet("converters")
    ws.append(["name", "area", "carrier_in", "carrier_out", "carrier_out2",
               "efficiency", "efficiency2", "p_nom", "p_nom_extendable", "p_nom_max",
               "marginal_cost", "capital_cost", "build_year", "lifetime"])
    for conv in network.all_converters:
        ws.append([conv.name, conv.area, conv.carrier_in, conv.carrier_out, conv.carrier_out2,
                   conv.efficiency, conv.efficiency2, conv.p_nom, conv.p_nom_extendable,
                   conv.p_nom_max, conv.marginal_cost, conv.capital_cost, conv.build_year,
                   conv.lifetime])
    _style_ws(ws)

    ws = wb.create_sheet("stores")
    ws.append(["name", "area", "e_nom", "carrier", "e_nom_extendable", "capital_cost", "lifetime"])
    for st in network.all_stores:
        ws.append([st.name, st.area, st.e_nom, st.carrier,
                   st.e_nom_extendable, st.capital_cost, st.lifetime])
    _style_ws(ws)

    ws = wb.create_sheet("pumped_hydro")
    ws.append(["name", "ac_area", "p_nom_turbine", "efficiency_turbine",
               "p_nom_pump", "efficiency_pump", "e_nom",
               "p_nom_extendable", "capital_cost", "marginal_cost", "build_year", "lifetime"])
    for ph in network.all_pumped_hydros:
        ws.append([ph.name, ph.ac_area, ph.p_nom_turbine, ph.efficiency_turbine,
                   ph.p_nom_pump, ph.efficiency_pump, ph.e_nom,
                   ph.p_nom_extendable, ph.capital_cost, ph.marginal_cost,
                   ph.build_year, ph.lifetime])
    _style_ws(ws)

    # ── Component templates (JSON in one cell) ──────────────────────
    ws = wb.create_sheet("component_templates")
    ws.append(["json_data"])
    if network.component_templates:
        ws.append([json.dumps(
            [dataclasses.asdict(t) for t in network.component_templates],
            ensure_ascii=False)])
    _style_ws(ws)

    # ── Custom component instances ──────────────────────────────────
    ws = wb.create_sheet("custom_instances")
    ws.append(["json_data"])
    all_ci = network.all_custom_instances
    if all_ci:
        ws.append([json.dumps(
            [dataclasses.asdict(ci) for ci in all_ci],
            ensure_ascii=False)])
    _style_ws(ws)

    # ── Scenarios ────────────────────────────────────────────────────
    ws = wb.create_sheet("scenarios")
    ws.append(["name", "base_year", "planning_years", "discount_rate", "profile_names", "multi_period"])
    for s in network.scenarios:
        ws.append([s.name, s.base_year, json.dumps(s.planning_years), s.discount_rate,
                   json.dumps(s.profile_names), s.multi_period])
    _style_ws(ws)

    # ── Scenario profiles ────────────────────────────────────────────
    ws = wb.create_sheet("profiles")
    ws.append(["name", "description"])
    for p in network.scenario_profiles:
        ws.append([p.name, p.description])
    _style_ws(ws)

    ws = wb.create_sheet("profile_co2")
    ws.append(["profile_name", "year", "co2_limit", "co2_price"])
    for p in network.scenario_profiles:
        for year, settings in sorted(p.co2_settings.items()):
            ws.append([p.name, year,
                       settings.get("co2_limit", 1e18),
                       settings.get("co2_price", 0.0)])
    _style_ws(ws)

    ws = wb.create_sheet("profile_carrier_costs")
    ws.append(["profile_name", "carrier", "parameter", "value"])
    for p in network.scenario_profiles:
        for carrier, costs in p.carrier_costs.items():
            for param, val in costs.items():
                ws.append([p.name, carrier, param, val])
    _style_ws(ws)

    ws = wb.create_sheet("profile_overrides")
    ws.append(["profile_name", "component_type", "component_name", "parameter", "year", "value"])
    for p in network.scenario_profiles:
        for r in p.rules:
            ws.append([p.name, r.component_type, r.component_name,
                       r.parameter, r.year, r.value])
    _style_ws(ws)


def _write_timeseries_sheets(wb, ts: TimeSeriesData):
    """Add timeseries sheets (solar_cf/wind_cf/hydro_cf/demand_mw) to an existing workbook."""
    for sheet_name, data in [
        ("solar_cf",   ts.solar_cf),
        ("wind_cf",    ts.wind_cf),
        ("hydro_cf",   ts.hydro_cf),
        ("biomass_cf", ts.biomass_cf),
        ("gen_cf",     ts.gen_cf),
        ("demand_mw",  ts.demand_mw),
    ]:
        ws = wb.create_sheet(sheet_name)
        keys = list(data.keys())
        ws.append(keys)
        for h in range(N_HOURS):
            ws.append([data[k][h] if h < len(data[k]) else 0.0 for k in keys])

    # ── ts_mode (CF/MW per generator) ──────────────────────────────
    ws = wb.create_sheet("ts_mode")
    ws.append(["gen_name", "mode"])
    for gen_name, mode in ts.ts_mode.items():
        ws.append([gen_name, mode])

    # ── fixed_output (forced dispatch per generator) ────────────────
    ws = wb.create_sheet("ts_fixed_output")
    ws.append(["gen_name", "fixed"])
    for gen_name, fixed in ts.fixed_output.items():
        ws.append([gen_name, fixed])


def save_network_with_timeseries(network: NetworkData, ts: TimeSeriesData, filepath: str):
    """Save network + timeseries into one Excel file."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _write_network_sheets(wb, network)
    _write_timeseries_sheets(wb, ts)
    wb.save(filepath)


def _migrate_legacy_demand(network: NetworkData, ts: TimeSeriesData) -> None:
    """旧形式の需要時系列キーを現行の area|load_name 形式へ移行する。

    現行形式のキーは "area|load_name"。過去には以下の2形式が存在した:
      - "area|bus_carrier"（エリア+バスキャリア単位で複数Loadが共有）
      - "load_name"（"|" なし。Load名のみで複数エリアが共有）
    キーの第2要素がそのエリア内の実在するLoad名と一致すればすでに現行形式とみなし、
    そうでなければ旧形式として該当する全Loadへ値をコピーする
    （現行形式キーが未設定のLoadのみ、初期値として複製する）。
    """
    loads_by_area: dict[str, list] = {}
    for ld in network.all_loads:
        loads_by_area.setdefault(ld.area, []).append(ld)

    def _already_current_format(area_name: str, rest: str) -> bool:
        return any(ld.name == rest for ld in loads_by_area.get(area_name, []))

    # ── "area|bus_carrier" 形式 ──────────────────────────────────────
    legacy_bus_keys = [
        k for k in ts.demand_mw
        if "|" in k and not _already_current_format(*k.split("|", 1))
    ]
    for key in legacy_bus_keys:
        area_name, carrier = key.split("|", 1)
        carrier = carrier or "AC"
        values = ts.demand_mw.pop(key)
        for ld in loads_by_area.get(area_name, []):
            if ld.bus_carrier == carrier:
                new_key = TimeSeriesData.make_load_key(ld.area, ld.name)
                if new_key not in ts.demand_mw:
                    ts.demand_mw[new_key] = list(values)

    # ── "load_name" のみ（"|" なし）の形式 ───────────────────────────
    legacy_name_keys = [k for k in ts.demand_mw if "|" not in k]
    for key in legacy_name_keys:
        values = ts.demand_mw.pop(key)
        for ld in network.all_loads:
            if ld.name == key:
                new_key = TimeSeriesData.make_load_key(ld.area, ld.name)
                if new_key not in ts.demand_mw:
                    ts.demand_mw[new_key] = list(values)


def load_network_with_timeseries(filepath: str) -> tuple:
    """Load network + timeseries from a combined Excel file.

    Returns (NetworkData, TimeSeriesData).
    """
    network = load_network(filepath)
    ts      = load_timeseries(filepath)
    _migrate_legacy_demand(network, ts)
    return network, ts


def save_network(network: NetworkData, filepath: str):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _write_network_sheets(wb, network)
    wb.save(filepath)


def load_network(filepath: str) -> NetworkData:
    wb = openpyxl.load_workbook(filepath, data_only=True)
    network = NetworkData()

    def sheet_rows(name, fallback=None):
        target = name if name in wb.sheetnames else fallback
        if not target or target not in wb.sheetnames:
            return []
        ws = wb[target]
        headers = [c.value for c in next(ws.iter_rows(max_row=1))]
        result = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(v is None for v in row):
                continue
            result.append(dict(zip(headers, row)))
        return result

    # areas sheet (fallback: legacy "buses" sheet)
    for r in sheet_rows("areas", fallback="buses"):
        network.areas.append(Area(
            name=str(r.get("name", "")),
            lat=_flt(r, "lat"),
            lon=_flt(r, "lon"),
            country=str(r.get("country") or ""),
        ))

    # user-defined carriers (optional in legacy files)
    for r in sheet_rows("carriers"):
        c = str(r.get("name") or "").strip()
        if c:
            network.add_user_carrier(c)

    # ── Load components into temporary lists, then assign to AreaRES ──
    _generators: list = []
    for r in sheet_rows("generators"):
        area_val = r.get("area") or r.get("bus") or ""
        _generators.append(Generator(
            name=str(r.get("name", "")), area=str(area_val),
            carrier=str(r.get("carrier", "")),
            bus_carrier=str(r.get("bus_carrier") or "AC"),
            p_nom=_flt(r, "p_nom"),
            p_nom_extendable=_boo(r, "p_nom_extendable"), p_nom_max=_flt(r, "p_nom_max"),
            marginal_cost=_flt(r, "marginal_cost"), capital_cost=_flt(r, "capital_cost"),
            efficiency=_flt(r, "efficiency", 1.0), build_year=_itn(r, "build_year"),
            p_max_pu=_flt(r, "p_max_pu", 1.0), p_min_pu=_flt(r, "p_min_pu", 0.0),
            committable=_boo(r, "committable"),
            min_up_time=_itn(r, "min_up_time", 0),
            ramp_limit_up=_flt(r, "ramp_limit_up", 1.0),
            ramp_limit_down=_flt(r, "ramp_limit_down", 1.0),
            lifetime=_itn(r, "lifetime", 0),
        ))

    # interconnections sheet (fallback: legacy "links" sheet)
    for r in sheet_rows("interconnections", fallback="links"):
        area0_val = r.get("area0") or r.get("bus0") or ""
        area1_val = r.get("area1") or r.get("bus1") or ""
        network.interconnections.append(Interconnection(
            name=str(r.get("name", "")),
            area0=str(area0_val),
            area1=str(area1_val),
            carrier=str(r.get("carrier") or ""),
            efficiency=_flt(r, "efficiency", 1.0),
            p_nom=_flt(r, "p_nom"),
            p_nom_reverse=_flt(r, "p_nom_reverse", 0.0),
            p_nom_extendable=_boo(r, "p_nom_extendable"),
            capital_cost=_flt(r, "capital_cost"), marginal_cost=_flt(r, "marginal_cost"),
            build_year=_itn(r, "build_year"),
            lifetime=_itn(r, "lifetime", 0),
        ))

    _loads: list = []
    for r in sheet_rows("loads"):
        area_val = r.get("area") or r.get("bus") or ""
        _loads.append(Load(
            name=str(r.get("name", "")), area=str(area_val),
            p_set=_flt(r, "p_set"),
            bus_carrier=str(r.get("bus_carrier") or "AC"),
        ))

    _stores: list = []
    for r in sheet_rows("stores"):
        area_val = r.get("area") or r.get("bus") or ""
        _stores.append(Store(
            name=str(r.get("name", "")), area=str(area_val),
            e_nom=_flt(r, "e_nom"), carrier=str(r.get("carrier") or ""),
            e_nom_extendable=_boo(r, "e_nom_extendable"),
            capital_cost=_flt(r, "capital_cost"),
            lifetime=_itn(r, "lifetime", 0),
        ))

    _pumped_hydros: list = []
    for r in sheet_rows("pumped_hydro"):
        ac_area_val = r.get("ac_area") or r.get("ac_bus") or ""
        _pumped_hydros.append(PumpedHydro(
            name=str(r.get("name", "")), ac_area=str(ac_area_val),
            p_nom_turbine=_flt(r, "p_nom_turbine"),
            efficiency_turbine=_flt(r, "efficiency_turbine", 0.9),
            p_nom_pump=_flt(r, "p_nom_pump"),
            efficiency_pump=_flt(r, "efficiency_pump", 0.85),
            e_nom=_flt(r, "e_nom"),
            p_nom_extendable=_boo(r, "p_nom_extendable"),
            capital_cost=_flt(r, "capital_cost"),
            marginal_cost=_flt(r, "marginal_cost"),
            build_year=_itn(r, "build_year"),
            lifetime=_itn(r, "lifetime", 0),
        ))

    _converters: list = []
    for r in sheet_rows("converters"):
        _converters.append(Converter(
            name=str(r.get("name", "")),
            area=str(r.get("area") or ""),
            carrier_in=str(r.get("carrier_in") or "AC"),
            carrier_out=str(r.get("carrier_out") or "AC"),
            carrier_out2=str(r.get("carrier_out2") or ""),
            efficiency=_flt(r, "efficiency", 0.9),
            efficiency2=_flt(r, "efficiency2", 0.0),
            p_nom=_flt(r, "p_nom"),
            p_nom_extendable=_boo(r, "p_nom_extendable"),
            p_nom_max=_flt(r, "p_nom_max"),
            marginal_cost=_flt(r, "marginal_cost"),
            capital_cost=_flt(r, "capital_cost"),
            build_year=_itn(r, "build_year"),
            lifetime=_itn(r, "lifetime", 0),
        ))

    # ── Component templates ────────────────────────────────────────────
    _templates: list = []
    if "component_templates" in wb.sheetnames:
        ws_t = wb["component_templates"]
        rows_t = list(ws_t.iter_rows(min_row=2, values_only=True))
        if rows_t and rows_t[0][0]:
            try:
                for td in json.loads(rows_t[0][0]):
                    subs = [SubComponentDef(**s) for s in td.get("sub_components", [])]
                    _templates.append(ComponentTemplate(
                        name=td["name"],
                        description=td.get("description", ""),
                        sub_components=subs,
                    ))
            except Exception:
                pass
    network.component_templates = _templates

    # ── Custom instances ────────────────────────────────────────────
    _custom_instances: list = []
    if "custom_instances" in wb.sheetnames:
        ws_ci = wb["custom_instances"]
        rows_ci = list(ws_ci.iter_rows(min_row=2, values_only=True))
        if rows_ci and rows_ci[0][0]:
            try:
                for cd in json.loads(rows_ci[0][0]):
                    _custom_instances.append(CustomComponentInstance(
                        name=str(cd["name"]),
                        area=str(cd["area"]),
                        template_name=str(cd["template_name"]),
                        param_values=cd.get("param_values", {}),
                        lifetime=int(cd.get("lifetime", 0)),
                    ))
            except Exception:
                pass

    # Build AreaRES for each area
    for area in network.areas:
        n = area.name
        res = AreaRES(
            area=area,
            generators    = [g  for g  in _generators    if g.area     == n],
            loads         = [ld for ld in _loads          if ld.area    == n],
            stores        = [st for st in _stores         if st.area    == n],
            pumped_hydros = [ph for ph in _pumped_hydros  if ph.ac_area == n],
            converters    = [c  for c  in _converters     if c.area     == n],
            custom_instances = [ci for ci in _custom_instances if ci.area == n],
        )
        network.area_res_list.append(res)

    # ── Scenarios ────────────────────────────────────────────────────
    for r in sheet_rows("scenarios"):
        py_raw = r.get("planning_years")
        if isinstance(py_raw, str):
            try:
                planning_years = json.loads(py_raw)
            except Exception:
                planning_years = [2030]
        else:
            planning_years = [int(py_raw)] if py_raw is not None else [2030]
        mp_raw = r.get("multi_period")
        multi_period = bool(mp_raw) if mp_raw is not None else False
        network.scenarios.append(ScenarioData(
            name=str(r.get("name") or "Scenario1"),
            base_year=_itn(r, "base_year"),
            planning_years=planning_years,
            discount_rate=_flt(r, "discount_rate", 0.05),
            profile_names=json.loads(r["profile_names"]) if isinstance(r.get("profile_names"), str) else [],
            multi_period=multi_period,
        ))

    # ── Scenario profiles ────────────────────────────────────────────
    profiles_map: dict = {}
    for r in sheet_rows("profiles"):
        name = str(r.get("name") or "")
        if name:
            profiles_map[name] = ScenarioProfile(
                name=name,
                description=str(r.get("description") or ""),
            )

    for r in sheet_rows("profile_co2"):
        pname = str(r.get("profile_name") or "")
        if pname in profiles_map:
            year = _itn(r, "year")
            profiles_map[pname].co2_settings[year] = {
                "co2_limit": _flt(r, "co2_limit", 1e18),
                "co2_price": _flt(r, "co2_price", 0.0),
            }

    for r in sheet_rows("profile_carrier_costs"):
        pname = str(r.get("profile_name") or "")
        if pname in profiles_map:
            carrier = str(r.get("carrier") or "")
            param   = str(r.get("parameter") or "")
            val     = _flt(r, "value")
            if carrier and param:
                if carrier not in profiles_map[pname].carrier_costs:
                    profiles_map[pname].carrier_costs[carrier] = {}
                profiles_map[pname].carrier_costs[carrier][param] = val

    for r in sheet_rows("profile_overrides"):
        pname = str(r.get("profile_name") or "")
        if pname in profiles_map:
            try:
                profiles_map[pname].rules.append(ComponentOverrideRule(
                    component_type=str(r.get("component_type") or ""),
                    component_name=str(r.get("component_name") or ""),
                    parameter=str(r.get("parameter") or ""),
                    year=_itn(r, "year"),
                    value=_flt(r, "value"),
                ))
            except (TypeError, ValueError):
                pass

    network.scenario_profiles = list(profiles_map.values())

    return network


# ══════════════════════════════════════════════════════════════════════
# Scenario  (multi-year format)
# ══════════════════════════════════════════════════════════════════════

def save_scenario(scenario: ScenarioData, filepath: str):
    """旧フォーマット互換のシナリオ単体保存（後方互換用）。

    新規保存は save_network_with_timeseries / save_project を使用。
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    ws = wb.create_sheet("settings")
    ws.append(["parameter", "value"])
    ws.append(["base_year",     scenario.base_year])
    ws.append(["discount_rate", scenario.discount_rate])
    _style_ws(ws)

    ws = wb.create_sheet("year_settings")
    ws.append(["year", "co2_limit", "co2_price"])
    for year in sorted(scenario.planning_years):
        ws.append([year, 1e18, 0.0])
    _style_ws(ws)

    wb.save(filepath)


def load_scenario(filepath: str):
    """旧フォーマットのシナリオファイルを読み込む。

    Returns:
        tuple[ScenarioData, list[ScenarioProfile]]:
            旧フォーマットの year_settings / carrier_costs は
            「インポート済みプロファイル」として ScenarioProfile に変換して返す。
    """
    wb = openpyxl.load_workbook(filepath, data_only=True)
    scenario = ScenarioData()

    def sheet_rows(name):
        if name not in wb.sheetnames:
            return []
        ws = wb[name]
        headers = [c.value for c in next(ws.iter_rows(max_row=1))]
        result = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(v is None for v in row):
                continue
            result.append(dict(zip(headers, row)))
        return result

    # ── Basic settings ────────────────────────────────────────────
    if "settings" in wb.sheetnames:
        for row in wb["settings"].iter_rows(min_row=2, values_only=True):
            if not row or row[0] is None:
                continue
            k, v = row[0], row[1]
            if k == "base_year":
                scenario.base_year = int(str(v)) if v is not None else scenario.base_year
            elif k == "discount_rate":
                scenario.discount_rate = float(str(v)) if v is not None else scenario.discount_rate
            elif k == "planning_year":
                scenario.planning_years = [int(str(v))] if v is not None else scenario.planning_years

    # ── Year settings → ScenarioProfile ─────────────────────────────
    imported_co2: dict = {}
    if "year_settings" in wb.sheetnames:
        scenario.planning_years = []
        for r in sheet_rows("year_settings"):
            if r.get("year") is None:
                continue
            year = _itn(r, "year")
            scenario.planning_years.append(year)
            imported_co2[year] = {
                "co2_limit": _flt(r, "co2_limit", 1e18),
                "co2_price": _flt(r, "co2_price", 0.0),
            }
        if not scenario.planning_years:
            scenario.planning_years = [2030]

    # ── Carrier costs ────────────────────────────────────────────────
    imported_carrier_costs: dict = {}
    for r in sheet_rows("carrier_costs"):
        carrier = r.get("carrier")
        if carrier:
            imported_carrier_costs[carrier] = {
                "capital_cost":  _flt(r, "capital_cost",  0.0),
                "marginal_cost": _flt(r, "marginal_cost", 0.0),
                "efficiency":    _flt(r, "efficiency",    1.0),
                "co2_intensity": _flt(r, "co2_intensity", 0.0),
                "lifetime":      _itn(r, "lifetime",      25),
            }

    # ── Profiles (old format: name + enabled + profile_rules) ────────
    profiles_map: dict = {}
    for r in sheet_rows("profiles"):
        name = str(r.get("name") or "")
        if name:
            profiles_map[name] = ScenarioProfile(name=name)

    for r in sheet_rows("profile_rules"):
        pname = str(r.get("profile_name") or "")
        if pname not in profiles_map:
            continue
        try:
            profiles_map[pname].rules.append(ComponentOverrideRule(
                component_type=str(r.get("component_type") or ""),
                component_name=str(r.get("component_name") or ""),
                parameter=str(r.get("parameter") or ""),
                year=int(r.get("year") or 2030),
                value=float(r.get("value") or 0.0),
            ))
        except (TypeError, ValueError):
            pass

    # ── Build returned profile list ───────────────────────────────────
    # CO2設定・carrier_costsが存在する場合は専用プロファイルを先頭に追加
    result_profiles = list(profiles_map.values())
    if imported_co2 or imported_carrier_costs:
        default_profile = ScenarioProfile(
            name=f"{scenario.name}（インポート済み設定）",
            description="旧シナリオファイルから自動変換",
            co2_settings=imported_co2,
            carrier_costs=imported_carrier_costs,
        )
        result_profiles.insert(0, default_profile)

    return scenario, result_profiles


# ── Project (network + timeseries + scenarios + profiles) ─────────────

def save_project(network: NetworkData, ts: TimeSeriesData, filepath: str):
    """統合プロジェクトファイルとして保存。save_network_with_timeseries と同等。"""
    save_network_with_timeseries(network, ts, filepath)


def load_project(filepath: str):
    """統合プロジェクトファイルを読み込む。

    Returns:
        tuple[NetworkData, TimeSeriesData]:
            NetworkData.scenarios / NetworkData.scenario_profiles に
            シナリオ・プロファイルが格納されている。
    """
    return load_network_with_timeseries(filepath)


# ══════════════════════════════════════════════════════════════════════
# Time series  (solar_cf / wind_cf / demand_mw)
# ══════════════════════════════════════════════════════════════════════

def save_timeseries(ts: TimeSeriesData, filepath: str):
    """Save 8760-hour time series to Excel (3 sheets)."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _write_timeseries_sheets(wb, ts)
    wb.save(filepath)


def load_timeseries(filepath: str) -> TimeSeriesData:
    """Load 8760-hour time series from Excel (3 sheets)."""
    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
    ts = TimeSeriesData()

    def _load_sheet(sheet_name) -> dict:
        if sheet_name not in wb.sheetnames:
            return {}
        ws     = wb[sheet_name]
        rows   = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if not header:
            return {}
        buses = [str(b) for b in header if b is not None]
        data  = {b: [] for b in buses}
        for row in rows:
            for i, b in enumerate(buses):
                val = row[i] if i < len(row) else None
                try:
                    data[b].append(float(val) if val is not None else 0.0)
                except (TypeError, ValueError):
                    data[b].append(0.0)
        # Pad / trim
        for b in buses:
            d = data[b]
            if len(d) < N_HOURS:
                d.extend([0.0] * (N_HOURS - len(d)))
            data[b] = d[:N_HOURS]
        return data

    ts.solar_cf         = _load_sheet("solar_cf")
    ts.wind_cf          = _load_sheet("wind_cf")
    ts.hydro_cf         = _load_sheet("hydro_cf")
    ts.biomass_cf       = _load_sheet("biomass_cf")
    ts.gen_cf           = _load_sheet("gen_cf")
    ts.demand_mw        = _load_sheet("demand_mw")

    # ── ts_mode (CF/MW per generator) ──────────────────────────────
    if "ts_mode" in wb.sheetnames:
        ws_m = wb["ts_mode"]
        for row in ws_m.iter_rows(min_row=2, values_only=True):
            if row[0] is not None and row[1] is not None:
                ts.ts_mode[str(row[0])] = str(row[1])

    # ── fixed_output (forced dispatch per generator) ────────────────
    if "ts_fixed_output" in wb.sheetnames:
        ws_f = wb["ts_fixed_output"]
        for row in ws_f.iter_rows(min_row=2, values_only=True):
            if row[0] is not None and row[1] is not None:
                ts.fixed_output[str(row[0])] = bool(row[1]) if not isinstance(row[1], bool) else row[1]

    wb.close()
    return ts
