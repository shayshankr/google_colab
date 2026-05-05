from hvac_e20_heat_load_tool import Boundary, ZoneInputs, e20_heat_load


def test_multi_boundary_load_runs():
    inputs = ZoneInputs(
        latitude=28.6139,
        city="Delhi",
        usage_type="office",
        occupancy=40,
        floor_area_m2=180.0,
        electronic_load_w=8000.0,
        boundaries=[
            Boundary(name="Wall-1", boundary_type="wall", area_m2=30.0, orientation="W", wall_type="medium"),
            Boundary(name="Wall-2", boundary_type="wall", area_m2=30.0, orientation="E", wall_type="medium"),
            Boundary(name="Wall-3", boundary_type="wall", area_m2=25.0, orientation="N", wall_type="medium"),
            Boundary(name="Wall-4", boundary_type="wall", area_m2=25.0, orientation="S", wall_type="medium"),
            Boundary(name="Window-West", boundary_type="window", area_m2=10.0, orientation="W", glass_type="double_low_e", shading_type="internal_blinds"),
            Boundary(name="Roof", boundary_type="roof", area_m2=180.0, orientation="HORIZONTAL", u_value_w_m2k=1.2),
            Boundary(name="Floor", boundary_type="floor", area_m2=180.0, orientation="HORIZONTAL", u_value_w_m2k=0.9),
        ],
    )

    result = e20_heat_load(inputs)

    assert result["room_sensible_kw"] > 0
    assert result["room_latent_kw"] > 0
    assert result["ahu_total_cooling_kw"] >= result["room_total_kw"]
    assert 0 < result["rshf"] <= 1
    assert 0 < result["gshf"] <= 1


def test_window_without_glass_type_raises():
    inputs = ZoneInputs(
        latitude=19.07,
        city="Mumbai",
        usage_type="office",
        occupancy=10,
        floor_area_m2=60.0,
        electronic_load_w=2000.0,
        boundaries=[Boundary(name="BadWindow", boundary_type="window", area_m2=5.0, orientation="W")],
    )

    try:
        e20_heat_load(inputs)
        assert False, "Expected ValueError for missing glass_type"
    except ValueError as exc:
        assert "glass_type is missing" in str(exc)
