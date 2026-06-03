"""
Determine which Virginia PUMAs (tl_2020_51_puma10) intersect with
Dominion Virginia Power and/or Appalachian Power (APCo) service territories,
and what percentage of each PUMA's area falls within each territory.

Outputs:
  - puma_dominion_overlap.csv  — full results table (both utilities)
  - in.puma.txt                — PUMA IDs intersecting Dominion
  - in_apco.puma.txt           — PUMA IDs intersecting APCo
"""

import geopandas as gpd
import pandas as pd
import os

BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
DOMINION_SHP     = os.path.join(BASE_DIR, "Dominion_Virginia_Power.shp")
APCO_SHP         = os.path.join(BASE_DIR, "APCo.shp")
PUMA_SHP         = os.path.join(BASE_DIR, "tl_2020_51_puma10", "tl_2020_51_puma10.shp")
OUT_CSV          = os.path.join(BASE_DIR, "puma_dominion_overlap.csv")
OUT_DOMINION_TXT = os.path.join(BASE_DIR, "in.puma.txt")
OUT_APCO_TXT     = os.path.join(BASE_DIR, "in_apco.puma.txt")

# ── Load layers ───────────────────────────────────────────────────────────────
print("Loading shapefiles...")
TARGET_CRS = "EPSG:3968"  # NAD83 / Virginia South (meters)

dominion = gpd.read_file(DOMINION_SHP).to_crs(TARGET_CRS)
apco     = gpd.read_file(APCO_SHP).to_crs(TARGET_CRS)
puma     = gpd.read_file(PUMA_SHP).to_crs(TARGET_CRS)

print(f"  Dominion features : {len(dominion)}, CRS: {dominion.crs}")
print(f"  APCo features     : {len(apco)}, CRS: {apco.crs}")
print(f"  PUMA features     : {len(puma)}, CRS: {puma.crs}")

dominion_union = dominion.union_all()
apco_union     = apco.union_all()

# ── Helper: compute % of each PUMA inside a utility polygon ──────────────────
def compute_pct_overlap(puma_gdf, utility_union):
    """Returns dict mapping GEOID10 -> (in_utility: bool, pct: float)."""
    results = {}
    for _, row in puma_gdf.iterrows():
        area = row.geometry.area
        if not row.geometry.intersects(utility_union):
            results[row["GEOID10"]] = (False, 0.0)
        else:
            isect_area = row.geometry.intersection(utility_union).area
            pct = round((isect_area / area) * 100, 2) if area > 0 else 0.0
            results[row["GEOID10"]] = (pct > 0, pct)
    return results

# ── Compute original PUMA areas and run both overlaps ────────────────────────
puma = puma.copy()
puma["puma_area_m2"] = puma.geometry.area

print("Computing intersections...")
dominion_overlap = compute_pct_overlap(puma, dominion_union)
apco_overlap     = compute_pct_overlap(puma, apco_union)

n_dom  = sum(1 for v in dominion_overlap.values() if v[0])
n_apco = sum(1 for v in apco_overlap.values()     if v[0])
print(f"  PUMAs intersecting Dominion : {n_dom}")
print(f"  PUMAs intersecting APCo     : {n_apco}")

# ── Build combined DataFrame ──────────────────────────────────────────────────
records = []
for _, row in puma.iterrows():
    geoid   = row["GEOID10"]
    puma_id = row["PUMACE10"]
    in_dom,  pct_dom  = dominion_overlap[geoid]
    in_apco, pct_apco = apco_overlap[geoid]
    records.append({
        "PUMA_ID":          puma_id,
        "ResStock_GISJOIN": f"G510{puma_id}",
        "In_Dominion":      in_dom,
        "Pct_In_Dominion":  pct_dom,
        "In_APCo":          in_apco,
        "Pct_In_APCo":      pct_apco,
    })

df = pd.DataFrame(records).sort_values("PUMA_ID").reset_index(drop=True)

# ── Save CSV ──────────────────────────────────────────────────────────────────
df.to_csv(OUT_CSV, index=False)
print(f"\nCSV saved -> {OUT_CSV}")
print(df.to_string(index=False))

# ── Save in.puma.txt (Dominion) ───────────────────────────────────────────────
in_dominion = df[df["In_Dominion"]]["PUMA_ID"].tolist()
with open(OUT_DOMINION_TXT, "w") as f:
    for pid in in_dominion:
        f.write(f"{pid}\n")
print(f"\nin.puma.txt saved -> {OUT_DOMINION_TXT}  ({len(in_dominion)} IDs)")

# ── Save in_apco.puma.txt (APCo) ─────────────────────────────────────────────
in_apco_ids = df[df["In_APCo"]]["PUMA_ID"].tolist()
with open(OUT_APCO_TXT, "w") as f:
    for pid in in_apco_ids:
        f.write(f"{pid}\n")
print(f"in_apco.puma.txt saved -> {OUT_APCO_TXT}  ({len(in_apco_ids)} IDs)")
