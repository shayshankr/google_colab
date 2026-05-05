# HVAC Application

This folder contains the HVAC E20 heat load calculator package, web UI, tests, and deployment files.

## Run CLI
```bash
cd Hvac
python -m hvac_e20_heat_load_tool --input-json your_inputs.json
```

## Run Web App
```bash
cd Hvac
pip install -r requirements.txt
python -m hvac_web.app
```
Open: http://localhost:5000

## Run Tests
```bash
cd Hvac
python -m pytest -q
```

## Render Deployment
This folder includes `render.yaml` and `requirements.txt` for Render deployment.
Start command in render config:
- `gunicorn hvac_web.app:app`
