# GeoSync Hydro Unified System v2

Бойова, інтегрована система моніторингу трейдингових/гідрологічних ризиків:
- GNN → LSTM + Transformer + Attention
- Фізично-обґрунтований штраф у тренуванні
- GB/T 22482-2008 (гідрологія) & GB 3838-2002 (якість води) — валідація
- Імпутація, Z-score аномалії, алерти
- Чекпоїнти, логи, CLI і HTTP API
- CI-подібний пайплайн (GitHub Actions)

## Quick start
```bash
pip install -r requirements.txt
python geosync_unified.py pipeline --config configs/geosync_unified.yaml
# API
python geosync_unified.py serve --config configs/geosync_unified.yaml
# CLI infer (NPZ):
python geosync_unified.py infer --config configs/geosync_unified.yaml --npz data/val_yangtze.npz
# CLI infer (JSON window):
python geosync_unified.py infer --config configs/geosync_unified.yaml --window_json '[ [[1,2,3,4,5], ...], ... ]'
```

**Масштабування до реальних даних**: заміни `load_npz_dataset` власним адаптером (CSV/Parquet/DB/стріми), дотримуючись форми `X: (N,T,S,F)` і таргетів.
