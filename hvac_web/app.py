from flask import Flask, render_template, request
from hvac_e20_heat_load_tool.core import Boundary, ZoneInputs, e20_heat_load, validate_zone_inputs

app = Flask(__name__)


def _to_zone_inputs(form):
    boundaries = []
    for i in range(len(form.getlist('b_name'))):
        name = form.getlist('b_name')[i].strip()
        if not name:
            continue
        boundaries.append(Boundary(
            name=name,
            boundary_type=form.getlist('b_type')[i],
            area_m2=float(form.getlist('b_area')[i]),
            orientation=form.getlist('b_orientation')[i],
            wall_type=(form.getlist('b_wall_type')[i] or None),
            glass_type=(form.getlist('b_glass_type')[i] or None),
            shading_type=(form.getlist('b_shading')[i] or 'none'),
            u_value_w_m2k=(float(form.getlist('b_u_value')[i]) if form.getlist('b_u_value')[i] else None),
        ))

    return ZoneInputs(
        latitude=float(form['latitude']),
        city=form['city'],
        usage_type=form['usage_type'],
        occupancy=int(form['occupancy']),
        floor_area_m2=float(form['floor_area_m2']),
        electronic_load_w=float(form['electronic_load_w']),
        indoor_dbt_c=float(form['indoor_dbt_c']),
        indoor_rh=float(form['indoor_rh']),
        supply_air_temp_c=float(form['supply_air_temp_c']),
        boundaries=boundaries,
    )


@app.route('/', methods=['GET', 'POST'])
def index():
    result = None
    errors = []
    if request.method == 'POST':
        try:
            inputs = _to_zone_inputs(request.form)
            errors = validate_zone_inputs(inputs)
            if not errors:
                result = e20_heat_load(inputs)
        except Exception as exc:
            errors = [str(exc)]
    return render_template('index.html', result=result, errors=errors)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
