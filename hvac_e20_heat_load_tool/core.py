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

from dataclasses import dataclass
from typing import Dict, Literal

UsageType = Literal["office", "retail", "classroom", "residential", "conference"]
GlassType = Literal["single_clear", "double_clear", "double_low_e", "reflective"]
ShadingType = Literal["none", "internal_blinds", "external_shading", "film"]
WallType = Literal["light", "medium", "heavy", "insulated"]


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


@dataclass
class ZoneInputs:
    latitude: float
    city: str
    usage_type: UsageType
    occupancy: int
    floor_area_m2: float

    # Window + solar
    glass_type: GlassType
    shading_type: ShadingType
    window_area_m2: float
    window_orientation: Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

    # Wall + envelope
    wall_type: WallType
    wall_area_m2: float
    wall_orientation: Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

    # Internal gains
    electronic_load_w: float

    # Design conditions
    indoor_dbt_c: float = 24.0
    indoor_rh: float = 50.0
    supply_air_temp_c: float = 14.0


ORIENTATION_SOLAR_FACTOR = {
    "N": 0.70,
    "NE": 0.85,
    "E": 1.00,
    "SE": 1.05,
    "S": 0.95,
    "SW": 1.10,
    "W": 1.15,
    "NW": 0.90,
}


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


def e20_heat_load(inputs: ZoneInputs) -> Dict[str, float]:
    city_data = CITY_OUTDOOR_CONDITIONS.get(inputs.city.lower(), CITY_OUTDOOR_CONDITIONS["default"])
    out_dbt = city_data["dbt"]
    out_wbt = city_data["wbt"]

    # Envelope sensible gains
    shgf = GLASS_SHGF_W_M2[inputs.glass_type]
    shade_mult = SHADING_MULTIPLIER[inputs.shading_type]
    win_orient_factor = ORIENTATION_SOLAR_FACTOR[inputs.window_orientation]
    solar_window_w = inputs.window_area_m2 * shgf * shade_mult * win_orient_factor

    wall_u = WALL_U_VALUE_W_M2K[inputs.wall_type]
    wall_orient_factor = ORIENTATION_SOLAR_FACTOR[inputs.wall_orientation]
    delta_t = max(0.0, out_dbt - inputs.indoor_dbt_c)
    wall_transmission_w = inputs.wall_area_m2 * wall_u * delta_t * wall_orient_factor

    # Internal sensible and latent gains
    occupant_sensible_w = inputs.occupancy * 75.0
    occupant_latent_w = inputs.occupancy * 55.0
    lighting_w = inputs.floor_area_m2 * USAGE_LIGHTING_W_M2[inputs.usage_type]

    room_sensible_w = solar_window_w + wall_transmission_w + occupant_sensible_w + lighting_w + inputs.electronic_load_w
    room_latent_w = occupant_latent_w
    room_total_w = room_sensible_w + room_latent_w

    rshf = room_sensible_w / room_total_w if room_total_w else 0.0

    # Fresh air (ventilation) by occupancy + usage type
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
    example = ZoneInputs(
        latitude=19.07,
        city="Mumbai",
        usage_type="office",
        occupancy=25,
        floor_area_m2=120.0,
        glass_type="double_low_e",
        shading_type="internal_blinds",
        window_area_m2=24.0,
        window_orientation="W",
        wall_type="medium",
        wall_area_m2=95.0,
        wall_orientation="W",
        electronic_load_w=5500.0,
    )

    result = e20_heat_load(example)
    print("=== E20 Cooling Load Summary ===")
    for k, v in result.items():
        if "factor" in k or k in {"rshf", "eshf", "gshf"}:
            print(f"{k:30s}: {v:.3f}")
        elif "air" in k and "lps" not in k:
            print(f"{k:30s}: {v:.1f}")
        else:
            print(f"{k:30s}: {v:.2f}")


if __name__ == "__main__":
    _demo()
