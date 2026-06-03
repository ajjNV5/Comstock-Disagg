"""Aggregate utility-specific ComStock outputs by building type.

Creates pivot-style CSV summaries for Dominion and APCo by summing the
requested calc columns, weight, sqft, and weighted sqft, grouped by:
  - in.comstock_building_type
  - in.census_division_name
  - in.state
  - utility

Also adds sample_n as the row count contributing to each grouped total.
Also emits a second set of exports grouped by in.comstock_building_type_group.
"""

from __future__ import annotations

import pathlib

import pandas as pd

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT_DIR / "comstock_input"
OUTPUT_DIR = pathlib.Path(__file__).resolve().parent

INPUTS = {
    "Dominion": INPUT_DIR / "comstock_va_full_county_dominion.csv",
    "APCo": INPUT_DIR / "comstock_va_full_county_apco.csv",
}

OUTPUTS = {
    "Dominion": OUTPUT_DIR / "comstock_va_full_county_dominion_pivot.csv",
    "APCo": OUTPUT_DIR / "comstock_va_full_county_apco_pivot.csv",
}

GROUP_OUTPUTS = {
    "Dominion": (
        OUTPUT_DIR / "comstock_va_full_county_dominion_group_pivot.csv"
    ),
    "APCo": OUTPUT_DIR / "comstock_va_full_county_apco_group_pivot.csv",
}

COMBINED_OUTPUT = OUTPUT_DIR / "comstock_va_full_county_utility_pivot.csv"
COMBINED_GROUP_OUTPUT = (
    OUTPUT_DIR / "comstock_va_full_county_utility_group_pivot.csv"
)
TOTAL_ENERGY_COLUMN = (
    "calc.weighted.electricity.total.energy_consumption..tbtu"
)

SUM_COLUMNS = [
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
    "weight",
    "in.sqft..ft2",
    "calc.weighted.sqft..ft2",
]

PERCENT_COLUMNS = [
    f"percent.{column}"
    for column in SUM_COLUMNS
    if column.startswith("calc.weighted.electricity.")
]

BASE_GROUP_COLUMNS = [
    "in.census_division_name",
    "in.state",
    "utility",
]

PRIMARY_GROUP_COLUMN = "in.comstock_building_type"
SECONDARY_GROUP_COLUMN = "in.comstock_building_type_group"


def validate_columns(
    df: pd.DataFrame,
    required: list[str],
    source_name: str,
) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(
            f"Missing required column(s) in {source_name}: {missing}"
        )


def add_percent_columns(df: pd.DataFrame) -> pd.DataFrame:
    total = df[TOTAL_ENERGY_COLUMN].replace(0, pd.NA)
    for column in SUM_COLUMNS:
        if not column.startswith("calc.weighted.electricity."):
            continue
        percent_column = f"percent.{column}"
        df[percent_column] = (df[column] / total).fillna(0.0)
    return df


def build_pivot(
    input_file: pathlib.Path,
    utility: str,
    group_column: str,
) -> pd.DataFrame:
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    print(f"Reading {utility} input: {input_file}")
    df = pd.read_csv(input_file)
    group_columns = [group_column, *BASE_GROUP_COLUMNS]
    validate_columns(df, group_columns[:-1] + SUM_COLUMNS, utility)

    df["utility"] = utility

    for column in SUM_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

    pivot_df = (
        df.groupby(group_columns, dropna=False, as_index=False)
        .agg({**{column: "sum" for column in SUM_COLUMNS}, "utility": "first"})
    )

    sample_n = (
        df.groupby(group_columns, dropna=False)
        .size()
        .rename("sample_n")
        .reset_index()
    )

    pivot_df = sample_n.merge(pivot_df, on=group_columns, how="left")
    pivot_df = add_percent_columns(pivot_df)
    pivot_df = pivot_df[
        [
            group_column,
            "in.census_division_name",
            "in.state",
            "utility",
            "sample_n",
            *SUM_COLUMNS,
            *PERCENT_COLUMNS,
        ]
    ]
    pivot_df = pivot_df.sort_values(
        [
            "utility",
            "in.state",
            "in.census_division_name",
            group_column,
        ]
    ).reset_index(drop=True)
    return pivot_df


def write_output_set(
    group_column: str,
    outputs: dict[str, pathlib.Path],
    combined_output: pathlib.Path,
    label: str,
) -> None:
    pivot_frames: list[pd.DataFrame] = []
    for utility, input_file in INPUTS.items():
        pivot_df = build_pivot(input_file, utility, group_column)
        pivot_df.to_csv(outputs[utility], index=False)
        pivot_frames.append(pivot_df)
        print(
            f"Wrote {utility} {label} pivot: {outputs[utility]} "
            f"({len(pivot_df):,} rows)"
        )

    combined_df = pd.concat(pivot_frames, ignore_index=True)
    combined_df.to_csv(combined_output, index=False)
    print(
        f"Wrote combined {label} pivot: {combined_output} "
        f"({len(combined_df):,} rows)"
    )


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    write_output_set(
        group_column=PRIMARY_GROUP_COLUMN,
        outputs=OUTPUTS,
        combined_output=COMBINED_OUTPUT,
        label="building-type",
    )
    write_output_set(
        group_column=SECONDARY_GROUP_COLUMN,
        outputs=GROUP_OUTPUTS,
        combined_output=COMBINED_GROUP_OUTPUT,
        label="building-type-group",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
