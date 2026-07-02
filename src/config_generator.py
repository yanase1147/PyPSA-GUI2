"""Build a pypsa.Network object from GUI data (NetworkData + ScenarioData + TimeSeriesData)."""
from __future__ import annotations

import copy
from collections import defaultdict, Counter

import pypsa
import pandas as pd
import numpy as np

# Prevent pandas 3.0 ArrowStringArray from breaking xarray in PyPSA's optimizer
try:
    pd.options.future.infer_string = False
except (AttributeError, TypeError):
    pass

from typing import List

from .models import (
    NetworkData, ScenarioData, TimeSeriesData, CF_CARRIERS,
    ScenarioProfile, resolve_co2_settings, resolve_carrier_costs,
)

N_HOURS = 8760


def _bus_name(area: str, carrier: str) -> str:
    """キャリアに対応するバス名を返す。AC または空文字はエリア名そのまま。"""
    return area if carrier in ("AC", "", None) else f"{area}-{carrier}"


def _collect_needed_carriers(net: NetworkData) -> dict:
    """エリアごとに必要な非ACキャリアの集合を返す。"""
    needed = {a.name: set() for a in net.areas}
    for gen in net.all_generators:
        if gen.bus_carrier != "AC" and gen.area in needed:
            needed[gen.area].add(gen.bus_carrier)
    for conv in net.all_converters:
        for c in (conv.carrier_in, conv.carrier_out, conv.carrier_out2):
            if c and c != "AC" and conv.area in needed:
                needed[conv.area].add(c)
    for ld in net.all_loads:
        if ld.bus_carrier != "AC" and ld.area in needed:
            needed[ld.area].add(ld.bus_carrier)
    for st in net.all_stores:
        if st.carrier and st.carrier != "AC" and st.area in needed:
            needed[st.area].add(st.carrier)
    for ic in net.interconnections:
        if ic.carrier and ic.carrier != "AC":
            for area_name in (ic.area0, ic.area1):
                if area_name in needed:
                    needed[area_name].add(ic.carrier)
    # custom instances: collect area:X refs
    for ci in net.all_custom_instances:
        tmpl = net.get_template(ci.template_name)
        if not tmpl or ci.area not in needed:
            continue
        for sub in tmpl.sub_components:
            for ref in sub.bus_connections.values():
                if ref.startswith("area:"):
                    carrier = ref[5:]
                    if carrier not in ("AC", ""):
                        needed[ci.area].add(carrier)
    return needed


def _resolve_bus_ref(ref: str, area: str, instance_name: str,
                     tmpl, sub_name_map: dict | None = None) -> str:
    """bus_connections の参照文字列を実際の PyPSA バス名に変換。"""
    if ref.startswith("area:"):
        return _bus_name(area, ref[5:])
    if ref.startswith("internal:"):
        sub_id = ref[9:]
        if sub_name_map and sub_id in sub_name_map:
            return sub_name_map[sub_id]
        sub = next((s for s in tmpl.sub_components if s.sub_id == sub_id), None)
        if sub:
            return sub.name_template.replace("{name}", instance_name)
    return ref


_COMPONENT_INDEX_ATTR = {
    "Bus": "buses",
    "Generator": "generators",
    "Link": "links",
    "Load": "loads",
    "Store": "stores",
    "Carrier": "carriers",
    "GlobalConstraint": "global_constraints",
}


def _unique_component_name(n: pypsa.Network, component_type: str,
                           base_name: str, scope_hint: str = "") -> str:
    """Return a unique component name in the current network.

    PyPSA skips duplicate names with a warning. We avoid silent drops by
    creating deterministic unique names when needed.
    """
    idx_attr = _COMPONENT_INDEX_ATTR.get(component_type)
    if not idx_attr:
        return base_name
    existing = getattr(n, idx_attr).index
    if base_name not in existing:
        return base_name

    hint = scope_hint.replace(" ", "_") if scope_hint else "dup"
    stem = f"{base_name}__{hint}"
    candidate = stem
    suffix = 2
    while candidate in existing:
        candidate = f"{stem}_{suffix}"
        suffix += 1
    return candidate


def _crf(discount_rate: float, lifetime: int) -> float:
    """資本回収係数（Capital Recovery Factor）を計算する。
    年間換算コスト = 初期投資コスト × CRF(r, n)
    """
    if lifetime <= 0:
        return 1.0
    if discount_rate <= 0:
        return 1.0 / lifetime
    r, n = discount_rate, lifetime
    return r * (1 + r)**n / ((1 + r)**n - 1)


def _annualize(overnight_cost: float, discount_rate: float, lifetime: int) -> float:
    """初期投資コスト（overnight cost）を年間換算コストに変換する。"""
    if overnight_cost <= 0 or lifetime <= 0:
        return 0.0
    return overnight_cost * _crf(discount_rate, lifetime)


def _get_lifetime(component_lifetime: int, carrier_costs: dict) -> int:
    """コンポーネント固有の設備寿命を返す。0 の場合はキャリアコストのデフォルト値を使用。"""
    if component_lifetime > 0:
        return component_lifetime
    return int(carrier_costs.get("lifetime", 25))


def _compute_overrides(active_profiles: List[ScenarioProfile], planning_year: int) -> dict:
    """アクティブなプロファイルからplanning_yearの実効オーバーライド値を計算する。

    戻り値: {(component_type, component_name): {parameter: value}}
    複数プロファイルが競合した場合、リスト後方のプロファイルが優先される。
    年のキャリーフォワード: planning_year以下の最近傍年の値を使用。
    """
    merged: dict = {}

    for profile in active_profiles:
        groups: dict = defaultdict(dict)
        for rule in profile.rules:
            groups[(rule.component_type, rule.component_name, rule.parameter)][rule.year] = rule.value
        for (ctype, cname, param), year_vals in groups.items():
            valid = [y for y in year_vals if y <= planning_year]
            if not valid:
                continue
            merged[(ctype, cname, param)] = year_vals[max(valid)]

    result: dict = defaultdict(dict)
    for (ctype, cname, param), value in merged.items():
        result[(ctype, cname)][param] = value
    return dict(result)


def _apply_overrides(component, component_type: str, overrides: dict):
    """コンポーネントにオーバーライドを適用した shallow copy を返す。"""
    params = overrides.get((component_type, component.name), {})
    if not params:
        return component
    comp = copy.copy(component)
    for param, value in params.items():
        if not hasattr(comp, param):
            continue
        current = getattr(comp, param)
        if isinstance(current, bool):
            setattr(comp, param, bool(int(value)))
        elif isinstance(current, int):
            setattr(comp, param, int(value))
        else:
            setattr(comp, param, float(value))
    return comp


def _downsample_timeseries(values, step: int, *, mode: str = "mean") -> list[float]:
    """Downsample an hourly series by aggregating each step-sized block.

    Using slicing (values[::step]) can pick only midnight points for 24h steps,
    which makes solar CF appear as all zeros. Aggregate blocks instead.
    """
    arr = np.asarray(values, dtype=float)
    if step <= 1:
        return arr.tolist()
    block = np.arange(len(arr)) // step
    s = pd.Series(arr)
    if mode == "first":
        return s.groupby(block).first().to_numpy().tolist()
    return s.groupby(block).mean().to_numpy().tolist()


def build_network(
    net: NetworkData,
    scenario: ScenarioData,
    ts: TimeSeriesData,
    planning_year: int,
    *,
    active_profiles: List[ScenarioProfile] = None,
    solver_name: str = "highs",
    snapshot_step: int = 1,
) -> pypsa.Network:
    """Return a pypsa.Network ready to be optimized for a single planning year."""
    if active_profiles is None:
        active_profiles = []
    if snapshot_step < 1:
        snapshot_step = 1

    n = pypsa.Network()
    all_snapshots = pd.date_range("2019-01-01", periods=N_HOURS, freq="h")
    n.set_snapshots(all_snapshots[::snapshot_step])
    if snapshot_step > 1:
        n.snapshot_weightings = n.snapshot_weightings * snapshot_step

    co2_cfg    = resolve_co2_settings(active_profiles, planning_year)
    co2_limit  = co2_cfg["co2_limit"]
    co2_price  = co2_cfg["co2_price"]

    carrier_costs = resolve_carrier_costs(active_profiles)

    overrides = _compute_overrides(active_profiles, planning_year)

    # ── Areas → PyPSA Buses (AC, 380 kV) ─────────────────────────────
    for area in net.areas:
        n.add("Bus", area.name, v_nom=380.0, x=area.lon, y=area.lat,
              carrier="AC", country=area.country)

    # ── 非AC キャリアバスの自動生成 ───────────────────────────────────
    needed_carriers = _collect_needed_carriers(net)
    for area_name, carriers in needed_carriers.items():
        for carrier in carriers:
            n.add("Bus", f"{area_name}-{carrier}", carrier=carrier)

    # ── Carriers & CO₂ costs ──────────────────────────────────────────
    for carrier, costs in carrier_costs.items():
        co2_int = costs.get("co2_intensity", 0.0)
        # co2_emissions in PyPSA is tCO2/MWh_thermal; we store tCO2/MWh_el
        n.add("Carrier", carrier, co2_emissions=co2_int,
              color=_carrier_color(carrier))

    # 既定の多キャリアに加え、実際に使用されるキャリアも登録
    used_carriers = set(net.multi_carriers())
    used_carriers.update(g.bus_carrier for g in net.all_generators if g.bus_carrier)
    used_carriers.update(ld.bus_carrier for ld in net.all_loads if ld.bus_carrier)
    used_carriers.update(st.carrier for st in net.all_stores if st.carrier)
    for carrier in used_carriers:
        if carrier and carrier not in n.carriers.index:
            n.add("Carrier", carrier)

    # ── Generators ────────────────────────────────────────────────────
    area_names = [a.name for a in net.areas]
    # Validate: each area can have unique names independently
    for area in net.areas:
        gen_names_in_area = [g.name for g in net.all_generators if g.area == area.name]
        dup_names = [name for name, cnt in Counter(gen_names_in_area).items() if cnt > 1]
        if dup_names:
            raise ValueError(
                f"エリア '{area.name}' で発電機名が重複しています。\n"
                "重複: " + ", ".join(dup_names)
            )
    for gen in net.all_generators:
        if gen.area not in area_names:
            continue
        gen = _apply_overrides(gen, "Generator", overrides)
        costs       = carrier_costs.get(gen.carrier, {})
        cap_cost_raw = gen.capital_cost  if gen.capital_cost  else costs.get("capital_cost",  0.0)
        lt           = _get_lifetime(gen.lifetime, costs)
        cap_cost     = _annualize(cap_cost_raw, scenario.discount_rate, lt)
        marg_cost    = gen.marginal_cost if gen.marginal_cost else costs.get("marginal_cost", 0.0)
        efficiency   = gen.efficiency    if gen.efficiency    else costs.get("efficiency",    1.0)

        kwargs: dict = dict(
            bus=_bus_name(gen.area, gen.bus_carrier),
            carrier=gen.carrier,
            p_nom=gen.p_nom,
            p_nom_extendable=gen.p_nom_extendable,
            p_nom_max=gen.p_nom_max if gen.p_nom_extendable else np.inf,
            marginal_cost=marg_cost,
            capital_cost=cap_cost,
            efficiency=efficiency,
            build_year=gen.build_year,
            p_max_pu=gen.p_max_pu,
            p_min_pu=gen.p_min_pu,
            committable=gen.committable,
            min_up_time=gen.min_up_time,
            ramp_limit_up=gen.ramp_limit_up,
            ramp_limit_down=gen.ramp_limit_down,
        )

        if gen.carrier in CF_CARRIERS:
            cf_dict = ts.cf_for_carrier(gen.carrier)
            cf_vals = cf_dict.get(gen.name, [])
            if cf_vals and any(v != 0.0 for v in cf_vals):
                if ts.ts_mode.get(gen.name, "cf") == "mw" and gen.p_nom > 0:
                    cf_vals = [v / gen.p_nom for v in cf_vals]
                # Aggregate hourly CF to coarse snapshots instead of midnight-only sampling.
                kwargs["p_max_pu"] = _downsample_timeseries(cf_vals, snapshot_step, mode="mean")
        else:
            # Non-CF_CARRIERS generators can also have a custom p_max_pu timeseries via gen_cf
            cf_vals = ts.gen_cf.get(gen.name, [])
            if cf_vals and any(v != 0.0 for v in cf_vals):
                if ts.ts_mode.get(gen.name, "cf") == "mw" and gen.p_nom > 0:
                    cf_vals = [v / gen.p_nom for v in cf_vals]
                kwargs["p_max_pu"] = _downsample_timeseries(cf_vals, snapshot_step, mode="mean")
        # Apply fixed_output regardless of whether a CF timeseries exists
        if ts.fixed_output.get(gen.name, False):
            kwargs["p_min_pu"] = kwargs["p_max_pu"]

        # Generate unique name if needed (allows same names in different areas)
        gen_name_unique = _unique_component_name(n, "Generator", gen.name, scope_hint=gen.area)
        n.add("Generator", gen_name_unique, **kwargs)

    # ── Converters → PyPSA Links ──────────────────────────────────────
    for conv in net.all_converters:
        if conv.area not in area_names:
            continue
        conv = _apply_overrides(conv, "Converter", overrides)
        conv_costs = carrier_costs.get(conv.carrier_in, {})
        conv_lt = _get_lifetime(conv.lifetime, conv_costs)
        kwargs = dict(
            bus0=_bus_name(conv.area, conv.carrier_in),
            bus1=_bus_name(conv.area, conv.carrier_out),
            efficiency=conv.efficiency,
            p_nom=conv.p_nom,
            p_nom_extendable=conv.p_nom_extendable,
            p_nom_max=conv.p_nom_max if conv.p_nom_extendable else np.inf,
            marginal_cost=conv.marginal_cost,
            capital_cost=_annualize(conv.capital_cost, scenario.discount_rate, conv_lt),
            build_year=conv.build_year,
        )
        if conv.carrier_out2:
            kwargs["bus2"] = _bus_name(conv.area, conv.carrier_out2)
            kwargs["efficiency2"] = conv.efficiency2
        # Generate unique name if needed (allows same names in different areas)
        # Use deterministic naming based on area to handle duplicates
        conv_name_unique = _unique_component_name(
            n, "Link", conv.name, scope_hint=conv.area
        )
        n.add("Link", conv_name_unique, **kwargs)

    # ── Interconnections → PyPSA Links ────────────────────────────────
    for ic in net.interconnections:
        if ic.area0 not in area_names:
            continue
        if ic.area1 not in area_names:
            continue
        ic = _apply_overrides(ic, "Interconnection", overrides)
        ic_carrier = ic.carrier if ic.carrier else "AC"
        ic_costs = carrier_costs.get(ic.carrier, {"lifetime": 40}) if ic.carrier else {"lifetime": 40}
        ic_lt = _get_lifetime(ic.lifetime, ic_costs)
        p_min_pu = (-ic.p_nom_reverse / ic.p_nom
                    if ic.p_nom_reverse > 0 and ic.p_nom > 0 else 0.0)
        kwargs = dict(
            bus0=_bus_name(ic.area0, ic_carrier),
            bus1=_bus_name(ic.area1, ic_carrier),
            efficiency=ic.efficiency,
            p_nom=ic.p_nom,
            p_min_pu=p_min_pu,
            p_nom_extendable=ic.p_nom_extendable,
            capital_cost=_annualize(ic.capital_cost, scenario.discount_rate, ic_lt),
            marginal_cost=ic.marginal_cost,
            build_year=ic.build_year,
        )
        if ic.carrier:
            kwargs["carrier"] = ic.carrier
        # Generate unique name if needed (allows same names in different areas)
        ic_name_unique = _unique_component_name(n, "Link", ic.name, scope_hint=f"{ic.area0}_{ic.area1}")
        n.add("Link", ic_name_unique, **kwargs)

    # ── Loads ─────────────────────────────────────────────────────────
    # Validate: each area can have unique names independently
    for area in net.areas:
        load_names_in_area = [ld.name for ld in net.all_loads if ld.area == area.name]
        dup_names = [name for name, cnt in Counter(load_names_in_area).items() if cnt > 1]
        if dup_names:
            raise ValueError(
                f"エリア '{area.name}' で需要名が重複しています。\n"
                "重複: " + ", ".join(dup_names)
            )
    for load in net.all_loads:
        if load.area not in area_names:
            continue
        bus = _bus_name(load.area, load.bus_carrier)
        demand_raw = ts.get_demand(load.area, load.bus_carrier) or [load.p_set] * N_HOURS
        # Generate unique name if needed (allows same names in different areas)
        load_name_unique = _unique_component_name(n, "Load", load.name, scope_hint=load.area)
        n.add("Load", load_name_unique, bus=bus,
              p_set=_downsample_timeseries(demand_raw, snapshot_step, mode="mean"))

    # ── Stores ───────────────────────────────────────────────────────
    # Validate: each area can have unique names independently
    for area in net.areas:
        store_names_in_area = [st.name for st in net.all_stores if st.area == area.name]
        dup_names = [name for name, cnt in Counter(store_names_in_area).items() if cnt > 1]
        if dup_names:
            raise ValueError(
                f"エリア '{area.name}' で蓄電池名が重複しています。\n"
                "重複: " + ", ".join(dup_names)
            )
    for st in net.all_stores:
        if st.area not in area_names:
            continue
        st = _apply_overrides(st, "Store", overrides)
        bus = _bus_name(st.area, st.carrier)
        st_costs = carrier_costs.get(st.carrier, {})
        st_lt = _get_lifetime(st.lifetime, st_costs)
        cap_cost = _annualize(st.capital_cost, scenario.discount_rate, st_lt)
        # Generate unique name if needed (allows same names in different areas)
        store_name_unique = _unique_component_name(n, "Store", st.name, scope_hint=st.area)
        n.add("Store", store_name_unique,
              bus=bus,
              e_nom=st.e_nom,
              e_nom_extendable=st.e_nom_extendable,
              capital_cost=cap_cost,
              carrier=st.carrier if st.carrier else "other")

    # ── Pumped hydro (Water bus + Store + turbine Link + pump Link) ───
    # Validate: each area can have unique names independently
    for area in net.areas:
        ph_names_in_area = [ph.name for ph in net.all_pumped_hydros if ph.ac_area == area.name]
        dup_names = [name for name, cnt in Counter(ph_names_in_area).items() if cnt > 1]
        if dup_names:
            raise ValueError(
                f"エリア '{area.name}' で揚水発電名が重複しています。\n"
                "重複: " + ", ".join(dup_names)
            )
    for ph in net.all_pumped_hydros:
        if ph.ac_area not in area_names:
            continue
        ph = _apply_overrides(ph, "PumpedHydro", overrides)
        # Generate unique names for water bus, store, turbine, pump (allows same names in different areas)
        ph_name_unique = _unique_component_name(n, "Bus", ph.name, scope_hint=ph.ac_area)
        water_bus = f"{ph_name_unique}-water"
        costs = carrier_costs.get("Hydro", {})
        cap_cost_raw = ph.capital_cost  if ph.capital_cost  else costs.get("capital_cost",  0.0)
        ph_lt = _get_lifetime(ph.lifetime, costs)
        cap_cost  = _annualize(cap_cost_raw, scenario.discount_rate, ph_lt)
        marg_cost = ph.marginal_cost if ph.marginal_cost else costs.get("marginal_cost", 0.0)
        n.add("Bus", water_bus, carrier="Water")
        n.add("Store", f"{ph_name_unique}-store",
              bus=water_bus,
              e_nom=ph.e_nom,
              e_nom_extendable=False,
              carrier="Water")
        n.add("Link", f"{ph_name_unique}-turbine",
              bus0=water_bus, bus1=ph.ac_area,
              efficiency=ph.efficiency_turbine,
              p_nom=ph.p_nom_turbine,
              p_nom_extendable=ph.p_nom_extendable,
              p_nom_max=np.inf if ph.p_nom_extendable else ph.p_nom_turbine,
              capital_cost=cap_cost,
              marginal_cost=marg_cost,
              build_year=ph.build_year)
        n.add("Link", f"{ph_name_unique}-pump",
              bus0=ph.ac_area, bus1=water_bus,
              efficiency=ph.efficiency_pump,
              p_nom=ph.p_nom_pump,
              p_nom_extendable=ph.p_nom_extendable,
              p_nom_max=np.inf if ph.p_nom_extendable else ph.p_nom_pump,
              build_year=ph.build_year)

    # ── Custom compound components ────────────────────────────────────
    for ci in net.all_custom_instances:
        if ci.area not in area_names:
            continue
        ci_params = overrides.get(("CustomComponentInstance", ci.name), {})
        if ci_params:
            ci = copy.copy(ci)
            ci.param_values = {**ci.param_values, **ci_params}
        tmpl = net.get_template(ci.template_name)
        if not tmpl:
            continue
        ci_lt = ci.lifetime if ci.lifetime > 0 else 25

        sub_name_map: dict[str, str] = {}
        for sub in tmpl.sub_components:
            base_name = sub.name_template.replace("{name}", ci.name)
            sub_name_map[sub.sub_id] = _unique_component_name(
                n,
                sub.component_type,
                base_name,
                scope_hint=f"{ci.area}_{ci.name}",
            )

        for sub in tmpl.sub_components:
            actual_name = sub_name_map.get(
                sub.sub_id,
                sub.name_template.replace("{name}", ci.name),
            )
            params: dict = dict(sub.fixed_params)
            for p_name in sub.exposed_params:
                key = f"{sub.sub_id}.{p_name}"
                if key in ci.param_values:
                    params[p_name] = ci.param_values[key]

            # Annualize capital_cost using instance lifetime
            if params.get("capital_cost"):
                params["capital_cost"] = _annualize(
                    float(params["capital_cost"]), scenario.discount_rate, ci_lt)

            ct = sub.component_type
            if ct == "Bus":
                n.add("Bus", actual_name, **params)
            elif ct == "Store":
                bus_ref = sub.bus_connections.get("bus", "")
                if bus_ref:
                    params["bus"] = _resolve_bus_ref(
                        bus_ref,
                        ci.area,
                        ci.name,
                        tmpl,
                        sub_name_map,
                    )
                n.add("Store", actual_name, **params)
            elif ct == "Generator":
                bus_ref = sub.bus_connections.get("bus", "")
                if bus_ref:
                    params["bus"] = _resolve_bus_ref(
                        bus_ref,
                        ci.area,
                        ci.name,
                        tmpl,
                        sub_name_map,
                    )
                n.add("Generator", actual_name, **params)
            elif ct == "Link":
                for slot in ("bus0", "bus1", "bus2"):
                    ref = sub.bus_connections.get(slot)
                    if ref:
                        params[slot] = _resolve_bus_ref(
                            ref,
                            ci.area,
                            ci.name,
                            tmpl,
                            sub_name_map,
                        )
                n.add("Link", actual_name, **params)

    # ── CO₂ constraint ────────────────────────────────────────────────
    if co2_limit < 1e18:
        n.add("GlobalConstraint", "co2_limit",
              sense="<=",
              constant=co2_limit,
              carrier_attribute="co2_emissions",
              investment_period=None)

    # ── CO₂ price (marginal cost on global constraint) ────────────────
    # Applied via global_constraints attribute in newer PyPSA
    if co2_price > 0:
        for carrier_name, costs in carrier_costs.items():
            co2_int = costs.get("co2_intensity", 0.0)
            if co2_int > 0:
                for gen in n.generators[n.generators.carrier == carrier_name].index:
                    n.generators.loc[gen, "marginal_cost"] += co2_price * co2_int

    return n


def _carrier_color(carrier: str) -> str:
    from .models import CARRIER_COLORS
    return CARRIER_COLORS.get(carrier, "#808080")
