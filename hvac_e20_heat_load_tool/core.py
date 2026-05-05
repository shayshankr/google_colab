"""HVAC cooling load calculator using an E20-style worksheet structure.

This module estimates:
- Room sensible heat (RSH)
- Room latent heat (RLH)
- Room total heat (RTH)
- Sensible heat factor (RSHF)
- Fresh air flow based on occupancy/usage
- Fresh air sensible + latent load
- Effective sensible heat factor (ESHF)
- Grand sensible heat factor (GSHF)
- Supply/dehumidified air quantity
- AHU total cooling load

The formulas are simplified and intended for preliminary sizing.
For detailed design, validate with project standards and local codes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Literal
import argparse
import json

UsageType = Literal["office", "retail", "classroom", "residential", "conference"]
GlassType = Literal["single_clear", "double_clear", "double_low_e", "reflective"]
ShadingType = Literal["none", "internal_blinds", "external_shading", "film"]
WallType = Literal["light", "medium", "heavy", "insulated"]
Orientation = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW", "HORIZONTAL"]
BoundaryType = Literal["wall", "window", "roof", "floor", "partition"]

CITY_OUTDOOR_CONDITIONS: Dict[str, Dict[str, float]] = {
    # DBT (°C), WBT (°C) approximations for peak summer design
    "mumbai": {"dbt": 35.0, "wbt": 28.0},
    "delhi": {"dbt": 43.0, "wbt": 27.0},
    "chennai": {"dbt": 37.0, "wbt": 28.0},
    "bengaluru": {"dbt": 34.0, "wbt": 24.0},
    "hyderabad": {"dbt": 39.0, "wbt": 24.0},
    "kolkata": {"dbt": 37.0, "wbt": 28.0},
    "default": {"dbt": 38.0, "wbt": 26.0},
}

GLASS_SHGF_W_M2 = {
    "single_clear": 520.0,
    "double_clear": 420.0,
    "double_low_e": 300.0,
    "reflective": 260.0,
}

SHADING_MULTIPLIER = {
    "none": 1.00,
    "internal_blinds": 0.80,
    "external_shading": 0.60,
    "film": 0.70,
}

WALL_U_VALUE_W_M2K = {
    "light": 2.2,
    "medium": 1.6,
    "heavy": 1.2,
    "insulated": 0.7,
}

DEFAULT_U_BY_BOUNDARY = {"roof": 1.2, "floor": 0.9, "partition": 1.8}

USAGE_FRESH_AIR_LPS_PER_PERSON = {
    "office": 10.0,
    "retail": 8.0,
    "classroom": 7.5,
    "residential": 6.0,
    "conference": 12.5,
}

USAGE_LIGHTING_W_M2 = {
    "office": 12.0,
    "retail": 18.0,
    "classroom": 14.0,
    "residential": 8.0,
    "conference": 15.0,
}

ORIENTATION_SOLAR_FACTOR = {
    "N": 0.70,
    "NE": 0.85,
    "E": 1.00,
    "SE": 1.05,
    "S": 0.95,
    "SW": 1.10,
    "W": 1.15,
    "NW": 0.90,
    "HORIZONTAL": 1.20,
}


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


def humidity_ratio_from_tdb_twb(dbt_c: float, wbt_c: float, p_kpa: float = 101.325) -> float:
    """Approximate humidity ratio (kg/kg dry air) from DBT & WBT."""
    pws_wbt = 0.61078 * 2.71828 ** ((17.2694 * wbt_c) / (wbt_c + 237.29))
    a = 0.00066 * (1 + 0.00115 * wbt_c) * p_kpa
    pw = pws_wbt - a * (dbt_c - wbt_c)
    pw = max(0.05, min(pw, p_kpa * 0.99))
    return 0.62198 * pw / (p_kpa - pw)


def humidity_ratio_from_tdb_rh(dbt_c: float, rh_percent: float, p_kpa: float = 101.325) -> float:
    pws = 0.61078 * 2.71828 ** ((17.2694 * dbt_c) / (dbt_c + 237.29))
    pw = (rh_percent / 100.0) * pws
    return 0.62198 * pw / (p_kpa - pw)


def _boundary_sensible_w(boundary: Boundary, delta_t: float) -> float:
    if not boundary.outdoor_exposed:
        return 0.0
    if boundary.boundary_type == "window":
        if not boundary.glass_type:
            raise ValueError(f"Boundary '{boundary.name}' is window but glass_type is missing")
        shgf = GLASS_SHGF_W_M2[boundary.glass_type]
        shade = SHADING_MULTIPLIER[boundary.shading_type]
        of = ORIENTATION_SOLAR_FACTOR[boundary.orientation]
        solar = boundary.area_m2 * shgf * shade * of
        u_value = boundary.u_value_w_m2k if boundary.u_value_w_m2k is not None else 5.8
        conduction = boundary.area_m2 * u_value * delta_t
        return solar + conduction

    if boundary.u_value_w_m2k is not None:
        u_value = boundary.u_value_w_m2k
    elif boundary.wall_type:
        u_value = WALL_U_VALUE_W_M2K[boundary.wall_type]
    else:
        u_value = DEFAULT_U_BY_BOUNDARY.get(boundary.boundary_type, WALL_U_VALUE_W_M2K["medium"])
    of = ORIENTATION_SOLAR_FACTOR.get(boundary.orientation, 1.0)
    return boundary.area_m2 * u_value * delta_t * of


def e20_heat_load(inputs: ZoneInputs) -> Dict[str, float]:
    city_data = CITY_OUTDOOR_CONDITIONS.get(inputs.city.lower(), CITY_OUTDOOR_CONDITIONS["default"])
    out_dbt, out_wbt = city_data["dbt"], city_data["wbt"]
    delta_t = max(0.0, out_dbt - inputs.indoor_dbt_c)

    envelope_sensible_w = sum(_boundary_sensible_w(b, delta_t) for b in inputs.boundaries)
    occupant_sensible_w = inputs.occupancy * 75.0
    occupant_latent_w = inputs.occupancy * 55.0
    lighting_w = inputs.floor_area_m2 * USAGE_LIGHTING_W_M2[inputs.usage_type]

    room_sensible_w = envelope_sensible_w + occupant_sensible_w + lighting_w + inputs.electronic_load_w
    room_latent_w = occupant_latent_w
    room_total_w = room_sensible_w + room_latent_w
    rshf = room_sensible_w / room_total_w if room_total_w else 0.0

    fa_lps = inputs.occupancy * USAGE_FRESH_AIR_LPS_PER_PERSON[inputs.usage_type]
    fa_m3s = fa_lps / 1000.0

    # Fresh air sensible heat: 1.2 kJ/(m3.K) -> kW formula ~ 1.2*V*ΔT
    fa_sensible_kw = 1.2 * fa_m3s * delta_t

    w_out = humidity_ratio_from_tdb_twb(out_dbt, out_wbt)
    w_in = humidity_ratio_from_tdb_rh(inputs.indoor_dbt_c, inputs.indoor_rh)
    delta_w = max(0.0, w_out - w_in)

    # Fresh air latent: m_dot_da * h_fg * delta_w
    # Approx m_dot_da = 1.2 * V (kg/s), h_fg=2501 kJ/kg
    fa_latent_kw = 1.2 * fa_m3s * 2501.0 * delta_w

    fa_total_kw = fa_sensible_kw + fa_latent_kw

    grand_sensible_w = room_sensible_w + fa_sensible_kw * 1000.0
    grand_latent_w = room_latent_w + fa_latent_kw * 1000.0
    grand_total_w = grand_sensible_w + grand_latent_w

    eshf = room_sensible_w / (room_sensible_w + room_latent_w + fa_latent_kw * 1000.0) if room_total_w else 0.0
    gshf = grand_sensible_w / grand_total_w if grand_total_w else 0.0

    # Supply/dehumidified airflow from sensible equation
    # Qs(kW)=1.2*V*(Tr-Ts)
    tr_minus_ts = max(1.0, inputs.indoor_dbt_c - inputs.supply_air_temp_c)
    supply_air_m3s = (grand_sensible_w / 1000.0) / (1.2 * tr_minus_ts)
    supply_air_cmh = supply_air_m3s * 3600.0

    ahu_total_kw = grand_total_w / 1000.0

    return {
        "outdoor_dbt_c": out_dbt,
        "outdoor_wbt_c": out_wbt,
        "envelope_sensible_kw": envelope_sensible_w / 1000.0,
        "room_sensible_kw": room_sensible_w / 1000.0,
        "room_latent_kw": room_latent_w / 1000.0,
        "room_total_kw": room_total_w / 1000.0,
        "rshf": rshf,
        "fresh_air_lps": fa_lps,
        "fresh_air_sensible_kw": fa_sensible_kw,
        "fresh_air_latent_kw": fa_latent_kw,
        "fresh_air_total_kw": fa_total_kw,
        "eshf": eshf,
        "gshf": gshf,
        "grand_sensible_kw": grand_sensible_w / 1000.0,
        "grand_total_kw": grand_total_w / 1000.0,
        "dehumidified_supply_air_cmh": supply_air_cmh,
        "ahu_total_cooling_kw": ahu_total_kw,
    }


def _demo() -> None:
    """CLI entrypoint that takes user-provided values instead of fixed defaults."""
    parser = argparse.ArgumentParser(description="E20-style HVAC heat load calculator")
    parser.add_argument("--input-json", help="Path to JSON file with ZoneInputs fields")
    parser.add_argument("--print-template", action="store_true", help="Print JSON template and exit")
    args = parser.parse_args()

    template = {
        "latitude": 28.6139,
        "city": "Delhi",
        "usage_type": "office",
        "occupancy": 40,
        "floor_area_m2": 180.0,
        "electronic_load_w": 8000.0,
        "indoor_dbt_c": 24.0,
        "indoor_rh": 50.0,
        "supply_air_temp_c": 14.0,
        "boundaries": [
            {"name": "Wall-1", "boundary_type": "wall", "area_m2": 30.0, "orientation": "W", "wall_type": "medium"},
            {"name": "Wall-2", "boundary_type": "wall", "area_m2": 30.0, "orientation": "E", "wall_type": "medium"},
            {"name": "Wall-3", "boundary_type": "wall", "area_m2": 25.0, "orientation": "N", "wall_type": "medium"},
            {"name": "Wall-4", "boundary_type": "wall", "area_m2": 25.0, "orientation": "S", "wall_type": "medium"},
            {"name": "Window-West", "boundary_type": "window", "area_m2": 10.0, "orientation": "W", "glass_type": "double_low_e", "shading_type": "internal_blinds"},
            {"name": "Roof", "boundary_type": "roof", "area_m2": 180.0, "orientation": "HORIZONTAL", "u_value_w_m2k": 1.2},
            {"name": "Floor", "boundary_type": "floor", "area_m2": 180.0, "orientation": "HORIZONTAL", "u_value_w_m2k": 0.9}
        ]
    }

    if args.print_template:
        print(json.dumps(template, indent=2))
        return

    if not args.input_json:
        raise SystemExit(
            "Provide user values using --input-json <file>. Use --print-template to generate the expected format."
        )

    with open(args.input_json, "r", encoding="utf-8") as f:
        payload = json.load(f)
    payload["boundaries"] = [Boundary(**b) for b in payload.get("boundaries", [])]

    inputs = ZoneInputs(**payload)
    result = e20_heat_load(inputs)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _demo()
