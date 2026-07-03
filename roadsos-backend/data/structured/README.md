# RoadSoS Structured Dataset

This folder contains normalized exports generated from the raw RoadSoS data files.

Run from `roadsos-backend`:

```powershell
python tools\structure_dataset.py
```

Generated collections:

- `manifest.json`: dataset version, counts, source paths, and shared schema.
- `knowledge_base.json`: structured safety-rule sections and emergency guides.
- `emergency_services.json`: hospitals, police stations, and towing services in one common service schema.
- `police_stations.json`: police-only records using the common emergency-service schema.
- `road_alerts.json`: active road-alert records with source metadata.
- `danger_zones.json`: geofenced danger-zone records with source metadata.

The backend still reads the original files under `data/`; this folder is the clean export for training, analysis, QA, and future UI features.
