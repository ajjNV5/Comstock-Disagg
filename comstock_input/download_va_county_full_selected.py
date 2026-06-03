"""Download and combine Virginia ComStock county full CSV files.

Source prefix:
  s3://oedi-data-lake/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/
  2025/comstock_amy2018_release_3/metadata_and_annual_results_aggregates/
  by_state_and_county/full/csv/state=VA/

This script:
1) Lists only upgrade0 CSV/CSV.GZ objects under the prefix
2) Streams every file and keeps only the required columns
3) Writes one combined CSV into comstock_input/
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import pathlib
import sys
import tarfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BUCKET = "oedi-data-lake"
PREFIX = (
    "nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/"
    "2025/comstock_amy2018_release_3/metadata_and_annual_results_aggregates/"
    "by_state_and_county/full/csv/state=VA/"
)
BASE_URL = f"https://{BUCKET}.s3.amazonaws.com/"
UPGRADE_KEY_FILTER = "_upgrade0_"

OUTPUT_FILE = pathlib.Path(__file__).parent / "comstock_va_full_county_selected.csv"
PROGRESS_FILE = pathlib.Path(__file__).parent / "comstock_va_full_county_selected.progress.json"

# Exact output columns requested by user.
KEEP_COLUMNS = [
    "bldg_id",
    "upgrade",
    "weight",
    "in.sqft..ft2",
    "calc.weighted.sqft..ft2",
    "in.upgrade_name",
    "in.census_division_name",
    "in.census_region_name",
    "in.iso_rto_region",
    "in.nhgis_county_gisjoin",
    "in.nhgis_state_gisjoin",
    "in.reeds_balancing_area",
    "in.state",
    "in.building_subtype",
    "in.comstock_building_type",
    "in.comstock_building_type_group",
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


def _tag_name(tag: str) -> str:
    """Return XML tag name without namespace."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def list_s3_keys(prefix: str) -> list[str]:
    """List all upgrade0 CSV/CSV.GZ keys under prefix using S3 ListObjectsV2."""
    keys: list[str] = []
    continuation_token: str | None = None

    while True:
        params = {
            "list-type": "2",
            "prefix": prefix,
            "max-keys": "1000",
        }
        if continuation_token:
            params["continuation-token"] = continuation_token

        url = BASE_URL + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url) as resp:
            payload = resp.read()

        root = ET.fromstring(payload)

        for child in root:
            if _tag_name(child.tag) != "Contents":
                continue
            key = None
            for content_node in child:
                if _tag_name(content_node.tag) == "Key":
                    key = content_node.text
                    break
            if (
                key
                and UPGRADE_KEY_FILTER in key
                and (key.endswith(".csv") or key.endswith(".csv.gz"))
            ):
                keys.append(key)

        is_truncated = "false"
        next_token = None
        for child in root:
            if _tag_name(child.tag) == "IsTruncated" and child.text:
                is_truncated = child.text.lower()
            elif _tag_name(child.tag) == "NextContinuationToken":
                next_token = child.text

        if is_truncated != "true":
            break
        continuation_token = next_token

    return sorted(keys)


def open_csv_stream_from_key(key: str):
    """Open key as text stream suitable for csv.DictReader.

    Some objects are true CSV.GZ files. Others are TAR.GZ archives with one CSV.
    This function handles both layouts.
    """
    object_url = BASE_URL + urllib.parse.quote(key, safe="/")
    response = urllib.request.urlopen(object_url)

    if key.endswith(".gz"):
        payload = response.read()
        response.close()

        # Try TAR.GZ first; if not a tar archive, fall back to plain GZIP CSV.
        try:
            tar_buffer = io.BytesIO(payload)
            with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
                members = [m for m in tar.getmembers() if m.isfile()]
                if members:
                    extracted = tar.extractfile(members[0])
                    if extracted is None:
                        raise OSError(f"Could not extract CSV from tar member in {key}")
                    csv_bytes = extracted.read()
                    return io.TextIOWrapper(io.BytesIO(csv_bytes), encoding="utf-8", newline="")
        except tarfile.ReadError:
            pass

        gz = gzip.GzipFile(fileobj=io.BytesIO(payload))
        return io.TextIOWrapper(gz, encoding="utf-8", newline="")

    return io.TextIOWrapper(response, encoding="utf-8", newline="")


def normalize_upgrade(value: str) -> str:
    """Normalize upgrade labels like '1.0' to '1' for key matching."""
    text = str(value).strip()
    try:
        return str(int(float(text)))
    except ValueError:
        return text


def load_progress(path: pathlib.Path) -> dict | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_progress(path: pathlib.Path, progress: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2)


def find_key_index_for_pair(keys: list[str], county: str, upgrade: str) -> int:
    """Find key index from county GISJOIN and upgrade number."""
    normalized_upgrade = normalize_upgrade(upgrade)
    county_marker = f"/county={county}/"
    for i, key in enumerate(keys):
        if county_marker not in key:
            continue
        if f"_upgrade{normalized_upgrade}_agg.csv" in key:
            return i
    return -1


def bootstrap_progress_from_partial_output(keys: list[str], out_file: pathlib.Path) -> tuple[int, int]:
    """Bootstrap resume state from existing CSV by dropping tail block and resuming at that key.

    We conservatively drop the final contiguous (county, upgrade) block so the next run
    can safely reprocess that key in case interruption happened mid-file.
    """
    tmp_file = out_file.with_suffix(out_file.suffix + ".tmp")

    with out_file.open("r", encoding="utf-8", newline="") as f_in:
        reader = csv.DictReader(f_in)
        if reader.fieldnames != KEEP_COLUMNS:
            raise RuntimeError(
                "Existing output header does not match expected selected columns. "
                "Delete output/progress files or rerun without --resume."
            )

        with tmp_file.open("w", encoding="utf-8", newline="") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=KEEP_COLUMNS, extrasaction="ignore")
            writer.writeheader()

            current_pair: tuple[str, str] | None = None
            current_block: list[dict] = []
            kept_rows = 0

            for row in reader:
                pair = (
                    row.get("in.nhgis_county_gisjoin", "").strip(),
                    normalize_upgrade(row.get("upgrade", "")),
                )
                if current_pair is None:
                    current_pair = pair

                if pair != current_pair:
                    for block_row in current_block:
                        writer.writerow(block_row)
                    kept_rows += len(current_block)
                    current_block = [row]
                    current_pair = pair
                else:
                    current_block.append(row)

            # Intentionally do not write the final block.
            dropped_pair = current_pair

    tmp_file.replace(out_file)

    if dropped_pair is None:
        return 0, 0

    county, upgrade = dropped_pair
    key_index = find_key_index_for_pair(keys, county, upgrade)
    if key_index < 0:
        raise RuntimeError(
            f"Could not map partial output tail (county={county}, upgrade={upgrade}) to an S3 key."
        )
    return key_index, kept_rows


def combine_selected_columns(
    keys: list[str],
    out_file: pathlib.Path,
    progress_file: pathlib.Path,
    resume: bool,
    stop_after: int | None,
) -> tuple[int, int]:
    """Combine selected columns from all keys into one CSV, with resume checkpoints."""
    out_file.parent.mkdir(parents=True, exist_ok=True)

    progress = load_progress(progress_file) if resume else None
    if progress and progress.get("prefix") != PREFIX:
        raise RuntimeError("Progress file prefix does not match script prefix.")

    if resume and progress is None and out_file.exists() and out_file.stat().st_size > 0:
        print("No progress manifest found. Bootstrapping resume state from existing partial CSV...")
        start_index, rows_written = bootstrap_progress_from_partial_output(keys, out_file)
        progress = {
            "bucket": BUCKET,
            "prefix": PREFIX,
            "output_file": str(out_file),
            "keys_total": len(keys),
            "processed_keys": keys[:start_index],
            "skipped_keys": [],
            "rows_written": rows_written,
        }
        save_progress(progress_file, progress)
        print(f"Bootstrap complete. Will resume from key index {start_index + 1}/{len(keys)}.")

    if resume and progress is not None:
        processed_keys = set(progress.get("processed_keys", []))
        skipped_keys = list(progress.get("skipped_keys", []))
        total_rows = int(progress.get("rows_written", 0))

        file_exists = out_file.exists() and out_file.stat().st_size > 0
        if not file_exists:
            # If output vanished, start a fresh file but keep clean progress state.
            processed_keys = set()
            skipped_keys = []
            total_rows = 0

        mode = "a" if file_exists else "w"
        with out_file.open(mode, encoding="utf-8", newline="") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=KEEP_COLUMNS, extrasaction="ignore")
            if mode == "w":
                writer.writeheader()

            files_processed_this_run = 0
            for index, key in enumerate(keys, start=1):
                if key in processed_keys:
                    continue
                if stop_after is not None and files_processed_this_run >= stop_after:
                    break

                print(f"[{index}/{len(keys)}] Reading {key}")
                text_stream = None
                try:
                    text_stream = open_csv_stream_from_key(key)
                    reader = csv.DictReader(text_stream)
                    missing = [col for col in KEEP_COLUMNS if col not in (reader.fieldnames or [])]
                    if missing:
                        print(f"    -> skipped: missing required column(s): {', '.join(missing)}")
                        skipped_keys.append(key)
                    else:
                        file_rows = 0
                        for row in reader:
                            writer.writerow({col: row.get(col, "") for col in KEEP_COLUMNS})
                            file_rows += 1
                        total_rows += file_rows
                        processed_keys.add(key)
                        files_processed_this_run += 1
                        print(f"    -> wrote {file_rows:,} rows")

                except Exception as exc:
                    print(f"    -> skipped due to read error: {exc}")
                    skipped_keys.append(key)

                finally:
                    if text_stream is not None:
                        text_stream.close()

                progress = {
                    "bucket": BUCKET,
                    "prefix": PREFIX,
                    "output_file": str(out_file),
                    "keys_total": len(keys),
                    "processed_keys": sorted(processed_keys),
                    "skipped_keys": skipped_keys,
                    "rows_written": total_rows,
                }
                save_progress(progress_file, progress)

        return len(processed_keys), total_rows

    # Fresh run (no resume): overwrite output and progress.
    with out_file.open("w", encoding="utf-8", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=KEEP_COLUMNS, extrasaction="ignore")
        writer.writeheader()

        total_rows = 0
        processed_keys: list[str] = []
        skipped_keys: list[str] = []
        files_processed_this_run = 0

        for index, key in enumerate(keys, start=1):
            if stop_after is not None and files_processed_this_run >= stop_after:
                break

            print(f"[{index}/{len(keys)}] Reading {key}")
            text_stream = None
            try:
                text_stream = open_csv_stream_from_key(key)
                reader = csv.DictReader(text_stream)
                missing = [col for col in KEEP_COLUMNS if col not in (reader.fieldnames or [])]
                if missing:
                    print(f"    -> skipped: missing required column(s): {', '.join(missing)}")
                    skipped_keys.append(key)
                    continue

                file_rows = 0
                for row in reader:
                    writer.writerow({col: row.get(col, "") for col in KEEP_COLUMNS})
                    file_rows += 1

                processed_keys.append(key)
                files_processed_this_run += 1
                total_rows += file_rows
                print(f"    -> wrote {file_rows:,} rows")

            except Exception as exc:
                print(f"    -> skipped due to read error: {exc}")
                skipped_keys.append(key)

            finally:
                if text_stream is not None:
                    text_stream.close()

            progress = {
                "bucket": BUCKET,
                "prefix": PREFIX,
                "output_file": str(out_file),
                "keys_total": len(keys),
                "processed_keys": processed_keys,
                "skipped_keys": skipped_keys,
                "rows_written": total_rows,
            }
            save_progress(progress_file, progress)

    return len(processed_keys), total_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and combine VA ComStock county full CSVs with selected columns."
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing output/progress files instead of overwriting.",
    )
    parser.add_argument(
        "--stop-after",
        type=int,
        default=None,
        help="Process only this many files in the current run (checkpoint test mode).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("Listing Virginia county full CSV files from S3...")
    keys = list_s3_keys(PREFIX)
    if not keys:
        print("No CSV files found under prefix. Check BUCKET/PREFIX.")
        return 1

    print(f"Found {len(keys)} file(s).")
    processed, rows = combine_selected_columns(
        keys=keys,
        out_file=OUTPUT_FILE,
        progress_file=PROGRESS_FILE,
        resume=args.resume,
        stop_after=args.stop_after,
    )

    print("\nDone.")
    print(f"Files processed: {processed}")
    print(f"Total rows    : {rows:,}")
    print(f"Output        : {OUTPUT_FILE}")
    print(f"Progress file : {PROGRESS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
