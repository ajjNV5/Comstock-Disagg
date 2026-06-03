"""Split VA ComStock county data into Dominion and APCo utility files.

Join key:
- comstock_county_utility_map.csv: Comstock_GISJOIN
- comstock_va_full_county_selected.csv: in.nhgis_county_gisjoin

For each utility file, selected calc columns are scaled by:
- Pct_In_Dominion / 100
- Pct_In_APCo / 100
"""

from __future__ import annotations

import pathlib
import pandas as pd

BASE_DIR = pathlib.Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent

INPUT_COMSTOCK = BASE_DIR / "comstock_va_full_county_selected.csv"
INPUT_MAP = ROOT_DIR / "GIS" / "comstock_county_utility_map.csv"

OUTPUT_DOMINION = BASE_DIR / "comstock_va_full_county_dominion.csv"
OUTPUT_APCO = BASE_DIR / "comstock_va_full_county_apco.csv"

CALC_COLUMNS = [
    "calc.weighted.electricity.cooling.energy_consumption..tbtu",
    "calc.weighted.electricity.exterior_lighting.energy_consumption..tbtu",
    "calc.weighted.electricity.fans.energy_consumption..tbtu",
    "calc.weighted.electricity.heat_recovery.energy_consumption..tbtu",
    "calc.weighted.electricity.heat_rejection.energy_consumption..tbtu",
    "calc.weighted.electricity.heating.energy_consumption..tbtu",
    "calc.weighted.electricity.interior_equipment.energy_consumption..tbtu",
    "calc.weighted.electricity.interior_lighting.energy_consumption..tbtu",
    "calc.weighted.electricity.net.energy_consumption..tbtu",
    "calc.weighted.electricity.pumps.energy_consumption..tbtu",
    "calc.weighted.electricity.purchased.energy_consumption..tbtu",
    "calc.weighted.electricity.pv.energy_consumption..tbtu",
    "calc.weighted.electricity.refrigeration.energy_consumption..tbtu",
    "calc.weighted.electricity.total.energy_consumption..tbtu",
    "calc.weighted.electricity.water_systems.energy_consumption..tbtu",
]


def validate_columns(df: pd.DataFrame, required: list[str], source_name: str) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(f"Missing required column(s) in {source_name}: {missing}")


def scale_for_utility(
    merged_df: pd.DataFrame,
    pct_col: str,
    output_file: pathlib.Path,
) -> tuple[int, int]:
    out = merged_df.copy()
    out[pct_col] = pd.to_numeric(out[pct_col], errors="coerce").fillna(0.0)

    # Only keep rows that have non-zero overlap with the target utility.
    out = out[out[pct_col] > 0].copy()

    factor = out[pct_col] / 100.0
    for col in CALC_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
        out[col] = out[col] * factor

    out.to_csv(output_file, index=False)
    return len(out), out["in.nhgis_county_gisjoin"].nunique()


def main() -> int:
    if not INPUT_COMSTOCK.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_COMSTOCK}")
    if not INPUT_MAP.exists():
        raise FileNotFoundError(f"Mapping file not found: {INPUT_MAP}")

    print(f"Reading ComStock data: {INPUT_COMSTOCK}")
    comstock_df = pd.read_csv(INPUT_COMSTOCK)

    print(f"Reading county utility map: {INPUT_MAP}")
    map_df = pd.read_csv(INPUT_MAP)

    validate_columns(comstock_df, ["in.nhgis_county_gisjoin", *CALC_COLUMNS], "comstock")
    validate_columns(
        map_df,
        ["Comstock_GISJOIN", "Pct_In_Dominion", "Pct_In_APCo"],
        "county map",
    )

    merged = comstock_df.merge(
        map_df,
        how="left",
        left_on="in.nhgis_county_gisjoin",
        right_on="Comstock_GISJOIN",
    )

    missing_map_rows = int(merged["Comstock_GISJOIN"].isna().sum())
    if missing_map_rows > 0:
        print(
            f"WARNING: {missing_map_rows} row(s) in ComStock data did not find county map matches."
        )

    dom_rows, dom_counties = scale_for_utility(
        merged,
        pct_col="Pct_In_Dominion",
        output_file=OUTPUT_DOMINION,
    )
    apco_rows, apco_counties = scale_for_utility(
        merged,
        pct_col="Pct_In_APCo",
        output_file=OUTPUT_APCO,
    )

    print("\nDone.")
    print(f"Dominion output: {OUTPUT_DOMINION}")
    print(f"  Rows: {dom_rows:,}")
    print(f"  Counties: {dom_counties}")
    print(f"APCo output: {OUTPUT_APCO}")
    print(f"  Rows: {apco_rows:,}")
    print(f"  Counties: {apco_counties}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
