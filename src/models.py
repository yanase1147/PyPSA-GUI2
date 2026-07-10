from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional

CARRIERS = [
    "Coal", "Gas", "Oil", "Hydro", "Nuclear", "Solar", "Wind",
    "Biomass", "Waste", "Geothermal", "Wave and Tidal", "Battery",
    "Petcoke", "Cogeneration", "Other",
]

# Carriers that use capacity-factor time series
CF_CARRIERS = {"Solar", "Wind", "Wave and Tidal", "Hydro", "Biomass"}

CARRIER_COLORS = {
    "Nuclear": "#745994",
    "Hydro": "royalblue",
    "Wind": "skyblue",
    "Coal": "dimgray",
    "Gas": "#E77A61",
    "Oil": "#FF0000",
    "Solar": "#EEFF00",
    "Biomass": "#228B22",
    "Other": "#D2691E",
    "Water": "#2C3796",     # 揚水放電・揚水充電
    "Waste": "#006400",
    "Geothermal": "#DC143C",
    "Wave and Tidal": "#00BFFF",
    "Battery": "#9370DB",
    "Petcoke": "#4B0082",
    "Cogeneration": "#FF69B4",
    # セクターカップリングLink（ACバスと非ACバスをつなぐConverter）の相手側バスキャリア
    "heat": "#FF8C00",
    "hydrogen": "#00CED1",
    "gas": "#A0522D",
    "DC": "#4682B4",
}

DEFAULT_CARRIER_COSTS: Dict[str, Dict[str, float]] = {
    "Coal":          {"capital_cost": 1500000, "marginal_cost": 25.0,  "efficiency": 0.37, "co2_intensity": 0.34, "lifetime": 40},
    "Gas":           {"capital_cost": 800000,  "marginal_cost": 55.0,  "efficiency": 0.50, "co2_intensity": 0.20, "lifetime": 30},
    "Oil":           {"capital_cost": 1000000, "marginal_cost": 70.0,  "efficiency": 0.38, "co2_intensity": 0.28, "lifetime": 30},
    "Hydro":         {"capital_cost": 2000000, "marginal_cost": 0.0,   "efficiency": 0.90, "co2_intensity": 0.00, "lifetime": 60},
    "Nuclear":       {"capital_cost": 6000000, "marginal_cost": 5.0,   "efficiency": 0.33, "co2_intensity": 0.00, "lifetime": 50},
    "Solar":         {"capital_cost": 500000,  "marginal_cost": 0.0,   "efficiency": 1.00, "co2_intensity": 0.00, "lifetime": 25},
    "Wind":          {"capital_cost": 1200000, "marginal_cost": 0.0,   "efficiency": 1.00, "co2_intensity": 0.00, "lifetime": 25},
    "Biomass":       {"capital_cost": 2500000, "marginal_cost": 30.0,  "efficiency": 0.35, "co2_intensity": 0.00, "lifetime": 30},
    "Waste":         {"capital_cost": 3000000, "marginal_cost": 10.0,  "efficiency": 0.25, "co2_intensity": 0.10, "lifetime": 30},
    "Geothermal":    {"capital_cost": 4000000, "marginal_cost": 5.0,   "efficiency": 0.15, "co2_intensity": 0.00, "lifetime": 30},
    "Wave and Tidal":{"capital_cost": 5000000, "marginal_cost": 0.0,   "efficiency": 1.00, "co2_intensity": 0.00, "lifetime": 25},
    "Battery":       {"capital_cost": 300000,  "marginal_cost": 0.0,   "efficiency": 0.90, "co2_intensity": 0.00, "lifetime": 15},
    "Petcoke":       {"capital_cost": 1200000, "marginal_cost": 20.0,  "efficiency": 0.38, "co2_intensity": 0.36, "lifetime": 40},
    "Cogeneration":  {"capital_cost": 1100000, "marginal_cost": 30.0,  "efficiency": 0.75, "co2_intensity": 0.20, "lifetime": 30},
    "Other":         {"capital_cost": 1000000, "marginal_cost": 20.0,  "efficiency": 0.40, "co2_intensity": 0.10, "lifetime": 25},
}

AREA_CARRIERS = ["AC", "DC", "gas", "heat", "hydrogen", "other"]

MULTI_CARRIERS = ["AC", "heat", "hydrogen", "gas"]

CONVERTER_PRESETS = {
    "CHP":          {"carrier_in": "gas",      "carrier_out": "AC",       "carrier_out2": "heat"},
    "電解槽":        {"carrier_in": "AC",       "carrier_out": "hydrogen", "carrier_out2": ""},
    "燃料電池":      {"carrier_in": "hydrogen", "carrier_out": "AC",       "carrier_out2": ""},
    "ヒートポンプ":   {"carrier_in": "AC",       "carrier_out": "heat",     "carrier_out2": ""},
    "ガスボイラー":   {"carrier_in": "gas",      "carrier_out": "heat",     "carrier_out2": ""},
}


@dataclass
class Area:
    name: str
    lat: float
    lon: float
    country: str = ""


@dataclass
class Generator:
    name: str
    area: str
    carrier: str
    bus_carrier: str = "AC"
    p_nom: float = 0.0
    p_nom_extendable: bool = False
    p_nom_max: float = 0.0
    marginal_cost: float = 0.0
    capital_cost: float = 0.0
    efficiency: float = 1.0
    build_year: int = 2020
    p_max_pu: float = 1.0
    p_min_pu: float = 0.0
    committable: bool = False
    min_up_time: int = 0
    ramp_limit_up: float = 1.0
    ramp_limit_down: float = 1.0
    lifetime: int = 0  # 0 = キャリアのデフォルト値を使用


@dataclass
class Interconnection:
    name: str
    area0: str
    area1: str
    carrier: str = ""
    efficiency: float = 1.0
    p_nom: float = 0.0
    p_nom_reverse: float = 0.0   # reverse-direction capacity [MW]; 0 = unidirectional
    p_nom_extendable: bool = False
    capital_cost: float = 0.0
    marginal_cost: float = 0.0
    build_year: int = 2020
    lifetime: int = 0


@dataclass
class Load:
    name: str
    area: str
    p_set: float = 0.0
    bus_carrier: str = "AC"


@dataclass
class Store:
    name: str
    area: str
    e_nom: float = 0.0
    carrier: str = ""
    e_nom_extendable: bool = False
    capital_cost: float = 0.0
    lifetime: int = 0


@dataclass
class PumpedHydro:
    name: str
    ac_area: str
    p_nom_turbine: float = 0.0
    efficiency_turbine: float = 0.9
    p_nom_pump: float = 0.0
    efficiency_pump: float = 0.85
    e_nom: float = 0.0
    p_nom_extendable: bool = False
    capital_cost: float = 0.0
    marginal_cost: float = 0.0
    build_year: int = 2020
    lifetime: int = 0


@dataclass
class Converter:
    name: str
    area: str
    carrier_in: str
    carrier_out: str
    carrier_out2: str = ""
    efficiency: float = 0.9
    efficiency2: float = 0.0
    p_nom: float = 0.0
    p_nom_extendable: bool = False
    p_nom_max: float = 0.0
    marginal_cost: float = 0.0
    capital_cost: float = 0.0
    build_year: int = 2020
    lifetime: int = 0


# ── Custom compound components ─────────────────────────────────────────

AVAILABLE_EXPOSED_PARAMS: Dict[str, List[str]] = {
    "Bus": [],
    "Store": [
        "e_nom", "e_nom_extendable", "e_nom_max", "e_min_pu", "e_max_pu",
        "e_initial", "standing_loss", "cyclic_state_of_charge",
        "capital_cost", "marginal_cost",
    ],
    "Generator": [
        "p_nom", "p_nom_extendable", "p_nom_max", "marginal_cost",
        "capital_cost", "efficiency", "p_max_pu", "p_min_pu", "build_year",
    ],
    "Link": [
        "p_nom", "p_nom_extendable", "p_nom_max", "efficiency", "efficiency2",
        "marginal_cost", "capital_cost", "build_year",
    ],
}

PARAM_DEFAULTS: Dict[str, Any] = {
    "e_nom": 100.0, "e_nom_max": 0.0, "e_min_pu": 0.0, "e_max_pu": 1.0,
    "e_initial": 0.0, "standing_loss": 0.0,
    "e_nom_extendable": False, "cyclic_state_of_charge": True,
    "p_nom": 100.0, "p_nom_max": 0.0, "p_nom_extendable": False,
    "marginal_cost": 0.0, "capital_cost": 0.0,
    "efficiency": 0.9, "efficiency2": 0.0,
    "p_max_pu": 1.0, "p_min_pu": 0.0, "build_year": 2020,
}

def get_param_suffix(cur: str = "CURRENCY") -> Dict[str, str]:
    return {
        "e_nom": " MWh", "e_nom_max": " MWh",
        "p_nom": " MW",  "p_nom_max": " MW",
        "capital_cost": f" {cur}/MW", "marginal_cost": f" {cur}/MWh",
    }


PARAM_SUFFIX: Dict[str, str] = get_param_suffix()


@dataclass
class SubComponentDef:
    """One PyPSA primitive inside a ComponentTemplate."""
    sub_id: str
    component_type: str          # "Bus" | "Store" | "Link" | "Generator"
    name_template: str           # e.g. "{name}-h2-store"
    fixed_params: Dict[str, Any] = field(default_factory=dict)
    exposed_params: List[str]    = field(default_factory=list)
    bus_connections: Dict[str, str] = field(default_factory=dict)
    pos_x: float = 0.0
    pos_y: float = 0.0


@dataclass
class ComponentTemplate:
    name: str
    description: str = ""
    sub_components: List[SubComponentDef] = field(default_factory=list)


@dataclass
class CustomComponentInstance:
    name: str
    area: str
    template_name: str
    # Keys: "{sub_id}.{param_name}"
    param_values: Dict[str, Any] = field(default_factory=dict)
    lifetime: int = 0  # サブコンポーネントの capital_cost 年間換算に使用（0 = デフォルト 25 年）


@dataclass
class AreaRES:
    """Reference Energy System for one area: bundles all supply, demand, and storage."""
    area: Area
    generators:      List[Generator]              = field(default_factory=list)
    loads:           List[Load]                   = field(default_factory=list)
    stores:          List[Store]                  = field(default_factory=list)
    pumped_hydros:   List[PumpedHydro]            = field(default_factory=list)
    converters:      List[Converter]              = field(default_factory=list)
    custom_instances: List[CustomComponentInstance] = field(default_factory=list)


# ── Scenario Profile ───────────────────────────────────────────────────

@dataclass
class ComponentOverrideRule:
    """年ごとのコンポーネントパラメータ上書きルール（1レコード = 1年分）。"""
    component_type: str   # "Generator" | "Store" | "PumpedHydro" | "Converter" | "Interconnection" | "CustomComponentInstance"
    component_name: str
    parameter: str        # 例: "capital_cost", "efficiency"
    year: int
    value: float


@dataclass
class ScenarioProfile:
    """シナリオプロファイル: CO2制約・キャリアコスト・コンポーネントオーバーライドの名前付きセット。

    複数プロファイルを適用する場合はリスト順に上書き（後が優先）。
    """
    name: str
    description: str = ""
    # 年別CO2設定 {year: {"co2_limit": float, "co2_price": float}}
    co2_settings: Dict[int, Dict[str, float]] = field(default_factory=dict)
    # キャリア別コスト（全年共通） {carrier: {param: value}}
    carrier_costs: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # コンポーネント別・年別パラメータオーバーライド
    rules: List[ComponentOverrideRule] = field(default_factory=list)

    def get_co2_limit(self, year: int) -> float:
        return self.co2_settings.get(year, {}).get("co2_limit", 1e18)

    def get_co2_price(self, year: int) -> float:
        return self.co2_settings.get(year, {}).get("co2_price", 0.0)

    def resolve_rule_value(
        self,
        component_type: str,
        component_name: str,
        parameter: str,
        year: int,
    ) -> Optional[float]:
        """指定コンポーネント・パラメータの適用値を返す。

        未定義年は直前の定義年の値を継続（carry-forward）。
        対象ルールが一切なければ None を返す。
        """
        candidates = [
            r for r in self.rules
            if r.component_type == component_type
            and r.component_name == component_name
            and r.parameter == parameter
            and r.year <= year
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.year).value


# 旧名エイリアス（後方互換）
TechnologyProfile = ScenarioProfile


def resolve_profiles(
    profiles: List[ScenarioProfile],
    component_type: str,
    component_name: str,
    parameter: str,
    year: int,
) -> Optional[float]:
    """複数プロファイルを順番に適用し、最後に定義された値を返す（後が優先）。

    どのプロファイルにも定義がなければ None を返す。
    """
    result: Optional[float] = None
    for profile in profiles:
        val = profile.resolve_rule_value(component_type, component_name, parameter, year)
        if val is not None:
            result = val
    return result


def resolve_co2_settings(profiles: List[ScenarioProfile], year: int) -> Dict[str, float]:
    """複数プロファイルからCO2設定をマージして返す（後が優先）。"""
    result: Dict[str, float] = {"co2_limit": 1e18, "co2_price": 0.0}
    for profile in profiles:
        if year in profile.co2_settings:
            result.update(profile.co2_settings[year])
    return result


def resolve_carrier_costs(profiles: List[ScenarioProfile]) -> Dict[str, Dict[str, float]]:
    """複数プロファイルからcarrier_costsをマージして返す（後が優先）。"""
    result: Dict[str, Dict[str, float]] = {}
    for profile in profiles:
        for carrier, costs in profile.carrier_costs.items():
            if carrier not in result:
                result[carrier] = {}
            result[carrier].update(costs)
    return result


# ── Scenario ───────────────────────────────────────────────────────────

# 旧フォーマット読み込み時の後方互換クラス
@dataclass
class YearSettings:
    co2_limit: float = 1e18
    co2_price: float = 0.0


@dataclass
class ScenarioData:
    name: str = "Scenario1"
    base_year: int = 2020
    planning_years: List[int] = field(default_factory=lambda: [2030])
    discount_rate: float = 0.05
    profile_names: List[str] = field(default_factory=list)
    multi_period: bool = False

    @property
    def planning_year(self) -> int:
        return self.planning_years[0] if self.planning_years else 2030


# ── Network ────────────────────────────────────────────────────────────

@dataclass
class NetworkData:
    areas:               List[Area]              = field(default_factory=list)
    area_res_list:       List[AreaRES]           = field(default_factory=list)
    interconnections:    List[Interconnection]   = field(default_factory=list)
    component_templates: List[ComponentTemplate] = field(default_factory=list)
    user_carriers:       List[str]               = field(default_factory=list)
    currency:            str                     = "CURRENCY"
    # シナリオプロファイル（ネットワークファイルに保存）
    scenario_profiles:   List[ScenarioProfile]   = field(default_factory=list)
    # シナリオ一覧（統合ファイル形式）
    scenarios:           List[ScenarioData]      = field(default_factory=list)

    # ── helpers ──────────────────────────────────────────────────────
    def get_area_res(self, area_name: str) -> Optional['AreaRES']:
        return next((r for r in self.area_res_list if r.area.name == area_name), None)

    def get_or_create_area_res(self, area: Area) -> 'AreaRES':
        res = self.get_area_res(area.name)
        if res is None:
            res = AreaRES(area=area)
            self.area_res_list.append(res)
        return res

    def get_template(self, name: str) -> Optional['ComponentTemplate']:
        return next((t for t in self.component_templates if t.name == name), None)

    def get_profile(self, name: str) -> Optional['ScenarioProfile']:
        return next((p for p in self.scenario_profiles if p.name == name), None)

    def get_scenario(self, name: str) -> Optional['ScenarioData']:
        return next((s for s in self.scenarios if s.name == name), None)

    def area_carriers(self) -> List[str]:
        base = list(AREA_CARRIERS)
        for c in self.user_carriers:
            if c and c not in base:
                base.append(c)
        return base

    def multi_carriers(self) -> List[str]:
        excluded = {"DC", "other", ""}
        return [c for c in self.area_carriers() if c not in excluded]

    def add_user_carrier(self, carrier: str) -> bool:
        c = carrier.strip()
        if not c:
            return False
        if c in AREA_CARRIERS or c in self.user_carriers:
            return False
        self.user_carriers.append(c)
        return True

    def remove_user_carrier(self, carrier: str) -> bool:
        if carrier in self.user_carriers:
            self.user_carriers.remove(carrier)
            return True
        return False

    @property
    def all_generators(self) -> List[Generator]:
        return [g for res in self.area_res_list for g in res.generators]

    @property
    def all_loads(self) -> List[Load]:
        return [ld for res in self.area_res_list for ld in res.loads]

    @property
    def all_stores(self) -> List[Store]:
        return [st for res in self.area_res_list for st in res.stores]

    @property
    def all_pumped_hydros(self) -> List[PumpedHydro]:
        return [ph for res in self.area_res_list for ph in res.pumped_hydros]

    @property
    def all_converters(self) -> List[Converter]:
        return [c for res in self.area_res_list for c in res.converters]

    @property
    def all_custom_instances(self) -> List[CustomComponentInstance]:
        return [ci for res in self.area_res_list for ci in res.custom_instances]


# ── Time series ────────────────────────────────────────────────────────

@dataclass
class TimeSeriesData:
    """8760-hour time series.

    solar_cf[gen_name]   : capacity factor 0-1 OR raw MW output (Solar generators)
    wind_cf[gen_name]    : capacity factor 0-1 OR raw MW output (Wind / Wave&Tidal generators)
    hydro_cf[gen_name]   : capacity factor 0-1 OR raw MW output (Hydro generators)
    biomass_cf[gen_name] : capacity factor 0-1 OR raw MW output (Biomass generators)
    gen_cf[gen_name]     : capacity factor 0-1 for any other generator carrier
    demand_mw[area|load_name] : demand in MW (Load components); keyed by area
        so that loads with the same name in different areas stay independent.
    ts_mode[gen_name]    : "cf" (default) or "mw" — input mode per generator
    fixed_output[gen_name]: True → p_min_pu = p_max_pu (forced dispatch)
    """
    solar_cf:     Dict[str, List[float]] = field(default_factory=dict)
    wind_cf:      Dict[str, List[float]] = field(default_factory=dict)
    hydro_cf:     Dict[str, List[float]] = field(default_factory=dict)
    biomass_cf:   Dict[str, List[float]] = field(default_factory=dict)
    gen_cf:       Dict[str, List[float]] = field(default_factory=dict)
    demand_mw:    Dict[str, List[float]] = field(default_factory=dict)
    ts_mode:      Dict[str, str]         = field(default_factory=dict)
    fixed_output: Dict[str, bool]        = field(default_factory=dict)

    def cf_for_carrier(self, carrier: str) -> Dict[str, List[float]]:
        if carrier == "Solar":
            return self.solar_cf
        if carrier in ("Wind", "Wave and Tidal"):
            return self.wind_cf
        if carrier == "Hydro":
            return self.hydro_cf
        if carrier == "Biomass":
            return self.biomass_cf
        return self.gen_cf

    def get_gen_cf(self, gen_name: str, carrier: str) -> List[float]:
        """Return the CF timeseries for a generator (empty list if not set)."""
        return self.cf_for_carrier(carrier).get(gen_name, [])

    def set_gen_cf(self, gen_name: str, carrier: str, values: List[float]) -> None:
        """Write CF timeseries for a generator into the appropriate dict."""
        self.cf_for_carrier(carrier)[gen_name] = values

    @staticmethod
    def make_load_key(area_name: str, load_name: str) -> str:
        return f"{area_name}|{load_name}"

    def get_demand_for_load(self, area_name: str, load_name: str) -> List[float]:
        """Return the demand timeseries for a load (empty list if not set)."""
        return self.demand_mw.get(self.make_load_key(area_name, load_name), [])

    def set_demand_for_load(self, area_name: str, load_name: str, values: List[float]) -> None:
        """Write demand timeseries for a load."""
        self.demand_mw[self.make_load_key(area_name, load_name)] = values

    def ensure_load_demand(self, area_name: str, load_name: str, n_hours: int = 8760) -> None:
        key = self.make_load_key(area_name, load_name)
        if key not in self.demand_mw:
            self.demand_mw[key] = [0.0] * n_hours

    def ensure_generator(self, gen_name: str, carrier: str, n_hours: int = 8760) -> None:
        cf_dict = self.cf_for_carrier(carrier)
        if gen_name not in cf_dict:
            cf_dict[gen_name] = [0.0] * n_hours


# ── Optimization results ───────────────────────────────────────────────

@dataclass
class YearResult:
    year: int
    status: str = "unknown"           # "ok" | "infeasible" | "error"
    snapshot_step: int = 1            # hours per snapshot (1=hourly, 24=daily, ...)
    objective: float = 0.0            # total system cost (Currency)
    co2_emissions: float = 0.0        # tCO₂
    # capacity by carrier {carrier: MW}
    capacity_by_carrier: Dict[str, float] = field(default_factory=dict)
    # annual generation by carrier {carrier: MWh}
    generation_by_carrier: Dict[str, float] = field(default_factory=dict)
    # capital cost by carrier {carrier: Currency}
    capex_by_carrier: Dict[str, float] = field(default_factory=dict)
    # operational cost by carrier {carrier: Currency}
    opex_by_carrier: Dict[str, float] = field(default_factory=dict)
    # Hourly time-series (pd.DataFrame / pd.Series, None if not extracted)
    dispatch_df: Any = None     # DataFrame[hours × carrier]: generator dispatch [MW]
    link_gen_df: Any = None     # DataFrame[hours × area_carrier]: Link generation to AC area [MW]
    link_charge_df: Any = None  # DataFrame[hours × area_carrier]: Link consumption from AC area [MW]
    link_flow_df: Any = None    # DataFrame[hours × link_name]: AC carrier Link p0 [MW]
    curtailment_df: Any = None  # DataFrame[hours × carrier]: curtailed renewable generation [MW]
    demand_ts: Any = None       # Series[hours]: total demand [MW]


@dataclass
class OptimizationResults:
    scenario_name: str = ""
    year_results: List[YearResult] = field(default_factory=list)
    log: str = ""

    def get_year(self, year: int) -> Optional[YearResult]:
        return next((r for r in self.year_results if r.year == year), None)
