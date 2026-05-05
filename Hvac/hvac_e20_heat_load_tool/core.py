"""HVAC cooling load calculator using an E20-style worksheet structure."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal

UsageType = Literal["office", "retail", "classroom", "residential", "conference"]
GlassType = Literal["single_clear", "double_clear", "double_low_e", "reflective"]
ShadingType = Literal["none", "internal_blinds", "external_shading", "film"]
WallType = Literal["light", "medium", "heavy", "insulated"]
Orientation = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW", "HORIZONTAL"]
BoundaryType = Literal["wall", "window", "roof", "floor", "partition"]

CITY_OUTDOOR_CONDITIONS: Dict[str, Dict[str, float]] = {
    "mumbai": {"dbt": 35.0, "wbt": 28.0}, "delhi": {"dbt": 43.0, "wbt": 27.0}, "chennai": {"dbt": 37.0, "wbt": 28.0},
    "bengaluru": {"dbt": 34.0, "wbt": 24.0}, "hyderabad": {"dbt": 39.0, "wbt": 24.0}, "kolkata": {"dbt": 37.0, "wbt": 28.0},
    "default": {"dbt": 38.0, "wbt": 26.0},
}
GLASS_SHGF_W_M2 = {"single_clear": 520.0, "double_clear": 420.0, "double_low_e": 300.0, "reflective": 260.0}
SHADING_MULTIPLIER = {"none": 1.00, "internal_blinds": 0.80, "external_shading": 0.60, "film": 0.70}
WALL_U_VALUE_W_M2K = {"light": 2.2, "medium": 1.6, "heavy": 1.2, "insulated": 0.7}
DEFAULT_U_BY_BOUNDARY = {"roof": 1.2, "floor": 0.9, "partition": 1.8}
USAGE_FRESH_AIR_LPS_PER_PERSON = {"office": 10.0, "retail": 8.0, "classroom": 7.5, "residential": 6.0, "conference": 12.5}
USAGE_LIGHTING_W_M2 = {"office": 12.0, "retail": 18.0, "classroom": 14.0, "residential": 8.0, "conference": 15.0}
ORIENTATION_SOLAR_FACTOR = {"N": 0.70, "NE": 0.85, "E": 1.00, "SE": 1.05, "S": 0.95, "SW": 1.10, "W": 1.15, "NW": 0.90, "HORIZONTAL": 1.20}


@dataclass
class Boundary:
    name: str
    boundary_type: BoundaryType
    area_m2: float
    orientation: Orientation = "N"
    u_value_w_m2k: float | None = None
    wall_type: WallType | None = None
    glass_type: GlassType | None = None
    shading_type: ShadingType = "none"
    outdoor_exposed: bool = True


@dataclass
class ZoneInputs:
    latitude: float
    city: str
    usage_type: UsageType
    occupancy: int
    floor_area_m2: float
    electronic_load_w: float
    boundaries: List[Boundary] = field(default_factory=list)
    indoor_dbt_c: float = 24.0
    indoor_rh: float = 50.0
    supply_air_temp_c: float = 14.0


def validate_zone_inputs(inputs: ZoneInputs) -> List[str]:
    errors: List[str] = []
    if inputs.occupancy < 0:
        errors.append("Occupancy cannot be negative.")
    if inputs.floor_area_m2 <= 0:
        errors.append("Floor area must be greater than 0.")
    if not (0 <= inputs.indoor_rh <= 100):
        errors.append("Indoor RH must be between 0 and 100.")

    walls = [b for b in inputs.boundaries if b.boundary_type == "wall"]
    windows = [b for b in inputs.boundaries if b.boundary_type == "window"]
    if len(walls) < 4:
        errors.append(f"Please provide data for {4 - len(walls)} more wall(s).")
    if len(windows) == 0:
        errors.append("Please provide at least one window boundary.")

    for b in inputs.boundaries:
        if b.area_m2 <= 0:
            errors.append(f"Boundary '{b.name}' area must be greater than 0.")
        if b.boundary_type == "window" and not b.glass_type:
            errors.append(f"Boundary '{b.name}' is window but glass_type is missing.")
    return errors


def humidity_ratio_from_tdb_twb(dbt_c: float, wbt_c: float, p_kpa: float = 101.325) -> float:
    pws_wbt = 0.61078 * 2.71828 ** ((17.2694 * wbt_c) / (wbt_c + 237.29))
    a = 0.00066 * (1 + 0.00115 * wbt_c) * p_kpa
    pw = max(0.05, min(pws_wbt - a * (dbt_c - wbt_c), p_kpa * 0.99))
    return 0.62198 * pw / (p_kpa - pw)


def humidity_ratio_from_tdb_rh(dbt_c: float, rh_percent: float, p_kpa: float = 101.325) -> float:
    pws = 0.61078 * 2.71828 ** ((17.2694 * dbt_c) / (dbt_c + 237.29))
    pw = (rh_percent / 100.0) * pws
    return 0.62198 * pw / (p_kpa - pw)


def _boundary_sensible_w(boundary: Boundary, delta_t: float) -> float:
    if not boundary.outdoor_exposed:
        return 0.0
    if boundary.boundary_type == "window":
        shgf = GLASS_SHGF_W_M2[boundary.glass_type]  # validated upfront
        shade = SHADING_MULTIPLIER[boundary.shading_type]
        of = ORIENTATION_SOLAR_FACTOR[boundary.orientation]
        solar = boundary.area_m2 * shgf * shade * of
        u_value = boundary.u_value_w_m2k if boundary.u_value_w_m2k is not None else 5.8
        return solar + (boundary.area_m2 * u_value * delta_t)

    u_value = boundary.u_value_w_m2k if boundary.u_value_w_m2k is not None else (
        WALL_U_VALUE_W_M2K[boundary.wall_type] if boundary.wall_type else DEFAULT_U_BY_BOUNDARY.get(boundary.boundary_type, WALL_U_VALUE_W_M2K["medium"])
    )
    return boundary.area_m2 * u_value * delta_t * ORIENTATION_SOLAR_FACTOR.get(boundary.orientation, 1.0)


def e20_heat_load(inputs: ZoneInputs) -> Dict[str, float]:
    errors = validate_zone_inputs(inputs)
    if errors:
        raise ValueError("; ".join(errors))

    city_data = CITY_OUTDOOR_CONDITIONS.get(inputs.city.lower(), CITY_OUTDOOR_CONDITIONS["default"])
    out_dbt, out_wbt = city_data["dbt"], city_data["wbt"]
    delta_t = max(0.0, out_dbt - inputs.indoor_dbt_c)

    envelope_sensible_w = sum(_boundary_sensible_w(b, delta_t) for b in inputs.boundaries)
    room_sensible_w = envelope_sensible_w + (inputs.occupancy * 75.0) + (inputs.floor_area_m2 * USAGE_LIGHTING_W_M2[inputs.usage_type]) + inputs.electronic_load_w
    room_latent_w = inputs.occupancy * 55.0
    room_total_w = room_sensible_w + room_latent_w

    fa_lps = inputs.occupancy * USAGE_FRESH_AIR_LPS_PER_PERSON[inputs.usage_type]
    fa_m3s = fa_lps / 1000.0
    fa_sensible_kw = 1.2 * fa_m3s * delta_t
    fa_latent_kw = 1.2 * fa_m3s * 2501.0 * max(0.0, humidity_ratio_from_tdb_twb(out_dbt, out_wbt) - humidity_ratio_from_tdb_rh(inputs.indoor_dbt_c, inputs.indoor_rh))

    grand_sensible_w = room_sensible_w + fa_sensible_kw * 1000.0
    grand_total_w = grand_sensible_w + room_latent_w + fa_latent_kw * 1000.0
    tr_minus_ts = max(1.0, inputs.indoor_dbt_c - inputs.supply_air_temp_c)

    return {
        "outdoor_dbt_c": out_dbt,
        "outdoor_wbt_c": out_wbt,
        "envelope_sensible_kw": envelope_sensible_w / 1000.0,
        "room_sensible_kw": room_sensible_w / 1000.0,
        "room_latent_kw": room_latent_w / 1000.0,
        "room_total_kw": room_total_w / 1000.0,
        "rshf": room_sensible_w / room_total_w if room_total_w else 0.0,
        "fresh_air_lps": fa_lps,
        "fresh_air_sensible_kw": fa_sensible_kw,
        "fresh_air_latent_kw": fa_latent_kw,
        "fresh_air_total_kw": fa_sensible_kw + fa_latent_kw,
        "eshf": room_sensible_w / (room_sensible_w + room_latent_w + fa_latent_kw * 1000.0) if room_total_w else 0.0,
        "gshf": grand_sensible_w / grand_total_w if grand_total_w else 0.0,
        "grand_sensible_kw": grand_sensible_w / 1000.0,
        "grand_total_kw": grand_total_w / 1000.0,
        "dehumidified_supply_air_cmh": ((grand_sensible_w / 1000.0) / (1.2 * tr_minus_ts)) * 3600.0,
        "ahu_total_cooling_kw": grand_total_w / 1000.0,
    }


def cli() -> None:
    import argparse, json
    parser = argparse.ArgumentParser(description="E20 HVAC heat load calculator")
    parser.add_argument("--input-json", required=True)
    args = parser.parse_args()
    payload = json.load(open(args.input_json, "r", encoding="utf-8"))
    payload["boundaries"] = [Boundary(**b) for b in payload.get("boundaries", [])]
    result = e20_heat_load(ZoneInputs(**payload))
    print(json.dumps(result, indent=2))
