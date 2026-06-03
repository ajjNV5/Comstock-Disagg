"""
Determine which Virginia ComStock counties intersect with
Dominion Virginia Power and/or Appalachian Power (APCo) service territories,
and what percentage of each county's area falls within each territory.

ComStock county GISJOIN format: G5100010, G5100030, etc. (G510 + 4-digit county ID)

Outputs:
  - comstock_county_utility_map.csv  — full results table (both utilities)
  - in_comstock_county_dominion.txt  — County IDs intersecting Dominion
  - in_comstock_county_apco.txt      — County IDs intersecting APCo
"""

import geopandas as gpd
import pandas as pd
import os
from datetime import datetime
import urllib.request
import zipfile
import tempfile

BASE_DIR            = os.path.dirname(os.path.abspath(__file__))
DOMINION_SHP        = os.path.join(BASE_DIR, "Dominion_Virginia_Power.shp")
APCO_SHP            = os.path.join(BASE_DIR, "APCo.shp")
OUT_CSV             = os.path.join(BASE_DIR, "comstock_county_utility_map.csv")
OUT_DOMINION_TXT    = os.path.join(BASE_DIR, "in_comstock_county_dominion.txt")
OUT_APCO_TXT        = os.path.join(BASE_DIR, "in_comstock_county_apco.txt")

# ── Download Virginia County Shapefile from Census TIGER ──────────────────────
def download_county_shapefile():
    """Download 2025 Virginia county shapefile if not present."""
    county_dir = os.path.join(BASE_DIR, "tl_2025_51_county")
    county_shp = os.path.join(county_dir, "tl_2025_51_county.shp")
    
    if os.path.exists(county_shp):
        print(f"County shapefile exists: {county_shp}")
        return county_shp
    
    print("Downloading 2025 Virginia county shapefile from Census TIGER...")
    url = "https://www2.census.gov/geo/tiger/TIGER2025/COUNTY/tl_2025_us_county.zip"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "county.zip")
        urllib.request.urlretrieve(url, zip_path)
        print(f"  Downloaded to {zip_path}, extracting...")
        
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(tmpdir)
        
        # Find the shapefile
        for fname in os.listdir(tmpdir):
            if fname.endswith(".shp"):
                county_shp_tmp = os.path.join(tmpdir, fname)
                break
        else:
            raise FileNotFoundError("No .shp file found in county zipfile")
        
        # Filter to Virginia (STATEFP=51) and save to permanent location
        gdf = gpd.read_file(county_shp_tmp)
        gdf_va = gdf[gdf["STATEFP"] == "51"].copy()
        
        os.makedirs(county_dir, exist_ok=True)
        # Copy all related files (.shp, .shx, .dbf, .prj, etc.)
        base_tmp = county_shp_tmp.replace(".shp", "")
        base_dst = os.path.join(county_dir, "tl_2025_51_county")
        for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
            src = base_tmp + ext
            dst = base_dst + ext
            if os.path.exists(src):
                import shutil
                shutil.copy(src, dst)
        
        print(f"  Extracted Virginia counties to {county_dir}")
        return county_shp


# ── Load layers ───────────────────────────────────────────────────────────────
print("Loading shapefiles...")
TARGET_CRS = "EPSG:3968"  # NAD83 / Virginia South (meters)

county_shp = download_county_shapefile()
county = gpd.read_file(county_shp).to_crs(TARGET_CRS)
dominion = gpd.read_file(DOMINION_SHP).to_crs(TARGET_CRS)
apco = gpd.read_file(APCO_SHP).to_crs(TARGET_CRS)

# Filter county to Virginia only
county = county[county["STATEFP"] == "51"].copy()

print(f"  County features  : {len(county)}, CRS: {county.crs}")
print(f"  Dominion features : {len(dominion)}, CRS: {dominion.crs}")
print(f"  APCo features     : {len(apco)}, CRS: {apco.crs}")

dominion_union = dominion.union_all()
apco_union = apco.union_all()


# ── Helper: compute % of each county inside a utility polygon ────────────────
def compute_pct_overlap(county_gdf, utility_union):
    """Returns dict mapping COUNTYFP -> (in_utility: bool, pct: float)."""
    results = {}
    for _, row in county_gdf.iterrows():
        area = row.geometry.area
        if not row.geometry.intersects(utility_union):
            results[row["COUNTYFP"]] = (False, 0.0)
        else:
            isect_area = row.geometry.intersection(utility_union).area
            pct = round((isect_area / area) * 100, 2) if area > 0 else 0.0
            results[row["COUNTYFP"]] = (pct > 0, pct)
    return results


# ── Compute original county areas and run both overlaps ─────────────────────
county = county.copy()
county["county_area_m2"] = county.geometry.area

print("Computing intersections...")
dominion_overlap = compute_pct_overlap(county, dominion_union)
apco_overlap = compute_pct_overlap(county, apco_union)

n_dom = sum(1 for v in dominion_overlap.values() if v[0])
n_apco = sum(1 for v in apco_overlap.values() if v[0])
print(f"  Counties intersecting Dominion : {n_dom}")
print(f"  Counties intersecting APCo     : {n_apco}")

# ── Build combined DataFrame ──────────────────────────────────────────────────
records = []
for _, row in county.iterrows():
    countyfp = row["COUNTYFP"]
    # ComStock county code format uses COUNTYFP with trailing zero (e.g., 001 -> 0010)
    county_id = f"{countyfp}0"
    comstock_gisjoin = f"G510{county_id}"
    
    in_dom, pct_dom = dominion_overlap[countyfp]
    in_apco, pct_apco = apco_overlap[countyfp]
    
    records.append({
        "County_ID": county_id,
        "Comstock_GISJOIN": comstock_gisjoin,
        "County_Name": row.get("NAME", ""),
        "In_Dominion": in_dom,
        "Pct_In_Dominion": pct_dom,
        "In_APCo": in_apco,
        "Pct_In_APCo": pct_apco,
    })

df = pd.DataFrame(records).sort_values("County_ID").reset_index(drop=True)

# ── Save CSV ──────────────────────────────────────────────────────────────────
try:
    df.to_csv(OUT_CSV, index=False)
    actual_out_csv = OUT_CSV
except PermissionError:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    actual_out_csv = os.path.join(BASE_DIR, f"comstock_county_utility_map_{ts}.csv")
    df.to_csv(actual_out_csv, index=False)
    print(f"\nPrimary output file is locked. Wrote fallback CSV -> {actual_out_csv}")

print(f"\nCSV saved -> {actual_out_csv}")
print(df.to_string(index=False))

# ── Save in_comstock_county_dominion.txt ───────────────────────────────────────
in_dominion = df[df["In_Dominion"]]["County_ID"].tolist()
with open(OUT_DOMINION_TXT, "w") as f:
    for cid in in_dominion:
        f.write(f"{cid}\n")
print(f"\nin_comstock_county_dominion.txt saved -> {OUT_DOMINION_TXT}  ({len(in_dominion)} IDs)")

# ── Save in_comstock_county_apco.txt ───────────────────────────────────────────
in_apco_ids = df[df["In_APCo"]]["County_ID"].tolist()
with open(OUT_APCO_TXT, "w") as f:
    for cid in in_apco_ids:
        f.write(f"{cid}\n")
print(f"in_comstock_county_apco.txt saved -> {OUT_APCO_TXT}  ({len(in_apco_ids)} IDs)")
