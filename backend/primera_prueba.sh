cd /srv/PDD/backend
source /srv/FORECAST/venv/bin/activate
export PDD_ENV_PATH=/srv/PDD/backend/.env

python - <<'PY'
from pdd_backend.config import Settings
from pdd_backend.db import build_engine
from pdd_backend.freshness import read_source_freshness

settings = Settings.from_env()
engine = build_engine(settings)

try:
    f = read_source_freshness(engine)
    source_dates = [
        f.raw_sales_date,
        f.enriched_sales_date,
        f.stock_source_date,
    ]

    common = min(source_dates) if all(source_dates) else None

    print("raw_sales_date         =", f.raw_sales_date)
    print("enriched_sales_date    =", f.enriched_sales_date)
    print("stock_source_date      =", f.stock_source_date)
    print("canonical_stock_date   =", f.canonical_stock_date)
    print("common_source_closed   =", common)
    print(
        "recommended_business_date =",
        common.replace() + __import__("datetime").timedelta(days=1)
        if common else None
    )
finally:
    engine.dispose()
PY