from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SALES_SQL = ROOT / "pdd_backend" / "sql" / "sales" / "upsert_sales_daily.sql"


def test_invalid_enriched_split_is_conserved_and_excluded_from_pdvb() -> None:
    sql = SALES_SQL.read_text(encoding="utf-8")

    assert "enriched_units_conserved" in sql
    assert "p.observed_units" in sql
    assert "'ENRICHED_INVALID'" in sql
    assert "'ENRICHED_UNITS_MISMATCH'" in sql
    assert "OR c.promo_adjustment_method = 'ENRICHED_INVALID'" in sql
