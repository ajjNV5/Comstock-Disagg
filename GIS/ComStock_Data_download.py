"""
ComStock Data Download Script
Downloads all CSV files from the OEDI S3 bucket for Virginia ComStock 2025 data
and combines them into a single CSV file.

Source:
  Bucket : oedi-data-lake  (public, no AWS credentials required)
  Prefix : nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/
           2025/comstock_amy2018_release_3/metadata_and_annual_results_aggregates/
           by_state_and_county/basic/csv/state=VA/

Methods supported:
  1. boto3 with UNSIGNED config  (default, recommended)
  2. AWS CLI  (set METHOD = "cli")
  3. requests + S3 REST API  (set METHOD = "requests")
"""

import os
import io
import pathlib
import pandas as pd

# ── Configuration ─────────────────────────────────────────────────────────────
BUCKET   = "oedi-data-lake"
PREFIX   = (
    "nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/"
    "2025/comstock_amy2018_release_3/metadata_and_annual_results_aggregates/"
    "by_state_and_county/basic/csv/state=VA/"
)
OUT_DIR  = pathlib.Path(__file__).parent / "comstock_va_csvs"   # temp download folder
OUT_FILE = pathlib.Path(__file__).parent / "comstock_va_combined.csv"

UPGRADE_FILTER = "upgrade0"   # Only download baseline (upgrade0); set to None for all
METHOD   = "boto3"   # "boto3" | "cli" | "requests"
# ──────────────────────────────────────────────────────────────────────────────


# ── Method 1: boto3 (recommended) ─────────────────────────────────────────────
def list_keys_boto3(s3_client) -> list[str]:
    """Return all object keys under PREFIX using paginated list_objects_v2."""
    keys = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if (key.endswith(".csv.gz") or key.endswith(".csv")) and (
                UPGRADE_FILTER is None or UPGRADE_FILTER in key
            ):
                keys.append(key)
    return keys


def download_boto3() -> list[pathlib.Path]:
    """Download all CSVs using boto3 with anonymous (unsigned) access."""
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    keys = list_keys_boto3(s3)
    print(f"Found {len(keys)} CSV files via boto3.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    local_paths = []
    for i, key in enumerate(keys, 1):
        # Flatten county=XXXXX/filename.csv.gz -> county_XXXXX_filename.csv.gz
        parts = key.replace(PREFIX, "").strip("/").split("/")
        filename = "_".join(parts) if len(parts) > 1 else parts[0]
        local_path = OUT_DIR / filename
        if not local_path.exists():
            print(f"  [{i}/{len(keys)}] Downloading {filename} ...")
            s3.download_file(BUCKET, key, str(local_path))
        else:
            print(f"  [{i}/{len(keys)}] Already exists, skipping {filename}")
        local_paths.append(local_path)
    return local_paths


# ── Method 2: AWS CLI ──────────────────────────────────────────────────────────
def download_cli() -> list[pathlib.Path]:
    """Download all CSVs using the AWS CLI (must be installed)."""
    import subprocess

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    s3_uri = f"s3://{BUCKET}/{PREFIX}"
    cmd = [
        "aws", "s3", "sync", s3_uri, str(OUT_DIR),
        "--no-sign-request",
        "--exclude", "*",
        "--include", "*.csv",
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"AWS CLI failed:\n{result.stderr}")
    print(result.stdout)
    return list(OUT_DIR.glob("*.csv"))


# ── Method 3: requests + S3 REST XML API ──────────────────────────────────────
def list_keys_requests() -> list[str]:
    """List S3 objects via the REST ListObjectsV2 XML endpoint with pagination."""
    import requests
    from xml.etree import ElementTree as ET

    base_url = f"https://{BUCKET}.s3.amazonaws.com/"
    ns = "http://s3.amazonaws.com/doc/2006-03-01/"
    keys = []
    continuation_token = None

    while True:
        params = {"list-type": "2", "prefix": PREFIX, "max-keys": "1000"}
        if continuation_token:
            params["continuation-token"] = continuation_token

        resp = requests.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)

        for content in root.findall(f"{{{ns}}}Contents"):
            key = content.find(f"{{{ns}}}Key").text
            if (key.endswith(".csv.gz") or key.endswith(".csv")) and (
                UPGRADE_FILTER is None or UPGRADE_FILTER in key
            ):
                keys.append(key)

        is_truncated = root.findtext(f"{{{ns}}}IsTruncated", "false").lower()
        if is_truncated == "true":
            continuation_token = root.findtext(f"{{{ns}}}NextContinuationToken")
        else:
            break

    return keys


def download_requests() -> list[pathlib.Path]:
    """Download all CSVs using the requests library."""
    import requests

    keys = list_keys_requests()
    print(f"Found {len(keys)} CSV files via requests.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    local_paths = []
    for i, key in enumerate(keys, 1):
        filename = pathlib.Path(key).name
        local_path = OUT_DIR / filename
        if not local_path.exists():
            url = f"https://{BUCKET}.s3.amazonaws.com/{key}"
            print(f"  [{i}/{len(keys)}] Downloading {filename} ...")
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            local_path.write_bytes(resp.content)
        else:
            print(f"  [{i}/{len(keys)}] Already exists, skipping {filename}")
        local_paths.append(local_path)
    return local_paths


# ── Combine CSVs ───────────────────────────────────────────────────────────────
def combine_csvs(local_paths: list[pathlib.Path]) -> None:
    """Read all downloaded CSVs and write a single combined CSV."""
    print(f"\nCombining {len(local_paths)} CSV files ...")
    if not local_paths:
        raise RuntimeError("No files to combine. Check that downloads succeeded.")
    dfs = []
    for path in sorted(local_paths):
        try:
            df = pd.read_csv(path)  # pandas handles .gz automatically
            df["source_file"] = path.name
            dfs.append(df)
        except Exception as e:
            print(f"  WARNING: Could not read {path.name}: {e}")

    if not dfs:
        raise RuntimeError("All files failed to read. Check file integrity.")
    combined = pd.concat(dfs, ignore_index=True)
    
    # Remove all columns ending with agg_basic.csv
    cols_to_drop = [col for col in combined.columns if col.endswith("agg_basic.csv")]
    if cols_to_drop:
        combined = combined.drop(columns=cols_to_drop)
        print(f"  Removed {len(cols_to_drop)} column(s) ending with 'agg_basic.csv'")
    
    # Remove completely blank rows (all NaN)
    before_drop = len(combined)
    combined = combined.dropna(how="all")
    after_drop = len(combined)
    if before_drop > after_drop:
        print(f"  Removed {before_drop - after_drop:,} completely blank rows")
    
    # Remove rows where only source_file has a value
    before_drop = len(combined)
    cols_except_source = [col for col in combined.columns if col != "source_file"]
    combined = combined[~combined[cols_except_source].isna().all(axis=1)]
    after_drop = len(combined)
    if before_drop > after_drop:
        print(f"  Removed {before_drop - after_drop:,} rows with only source_file populated")
    
    combined.to_csv(OUT_FILE, index=False)
    print(f"Combined CSV written to: {OUT_FILE}")
    print(f"  Total rows : {len(combined):,}")
    print(f"  Columns    : {list(combined.columns)}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    if METHOD == "boto3":
        local_paths = download_boto3()
    elif METHOD == "cli":
        local_paths = download_cli()
    elif METHOD == "requests":
        local_paths = download_requests()
    else:
        raise ValueError(f"Unknown METHOD: {METHOD!r}. Choose 'boto3', 'cli', or 'requests'.")

    combine_csvs(local_paths)


if __name__ == "__main__":
    main()
