"""
Visual check: two-panel map showing 2025 Virginia counties clipped to
(left)  Dominion Virginia Power territory
(right) Appalachian Power (APCo) territory

Output: comstock_county_utility_check.png
"""

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import os

BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
DOMINION_SHP     = os.path.join(BASE_DIR, "Dominion_Virginia_Power.shp")
APCO_SHP         = os.path.join(BASE_DIR, "APCo.shp")
COUNTY_SHP       = os.path.join(BASE_DIR, "tl_2025_51_county", "tl_2025_51_county.shp")
OUT_PNG          = os.path.join(BASE_DIR, "comstock_county_utility_check.png")

PLOT_CRS = "EPSG:3968"   # NAD83 / Virginia South

# ── Colors (matching original ArcGIS symbology) ───────────────────────────────
# Dominion: yellow fill  rgba(255,255,0)  -> use a muted version for readability
DOM_FILL     = "#fffaaa"
DOM_EDGE     = "#004a99"
DOM_COUNTY   = "#ffd700"
DOM_COUNTY_EDG = "#7a6000"

# APCo: red  rgba(205,46,49)
APCO_FILL       = "#f4b8b9"
APCO_EDGE       = "#cd2e31"
APCO_COUNTY     = "#cd2e31"
APCO_COUNTY_EDG = "#7a0000"

# ── Load & reproject ──────────────────────────────────────────────────────────
print("Loading shapefiles...")
dominion = gpd.read_file(DOMINION_SHP).to_crs(PLOT_CRS)
apco     = gpd.read_file(APCO_SHP).to_crs(PLOT_CRS)
county   = gpd.read_file(COUNTY_SHP).to_crs(PLOT_CRS)

# Filter to Virginia (STATEFP=51)
county = county[county["STATEFP"] == "51"].copy()

dominion_union = dominion.union_all()
apco_union     = apco.union_all()

county_in_dom  = county[county.geometry.intersects(dominion_union)].copy()
county_in_apco = county[county.geometry.intersects(apco_union)].copy()
county_out_dom  = county[~county.geometry.intersects(dominion_union)].copy()
county_out_apco = county[~county.geometry.intersects(apco_union)].copy()

county_clipped_dom  = gpd.clip(county_in_dom,  dominion)
county_clipped_apco = gpd.clip(county_in_apco, apco)

print(f"  Counties intersecting Dominion : {len(county_in_dom)}")
print(f"  Counties intersecting APCo     : {len(county_in_apco)}")

# ── Helper: draw one panel ────────────────────────────────────────────────────
def draw_panel(ax, utility_gdf, county_all, county_in, county_clipped,
               util_fill, util_edge, county_fill, county_edge, title):
    # All VA counties as grey background context
    county_all.plot(ax=ax, color="#e8e8e8", edgecolor="#aaaaaa",
                    linewidth=0.3, zorder=1)

    # Utility territory fill
    utility_gdf.plot(ax=ax, color=util_fill, edgecolor=util_edge,
                     linewidth=1.5, zorder=2)

    # Clipped county fill
    county_clipped.plot(ax=ax, color=county_fill, alpha=0.55,
                        edgecolor=county_edge, linewidth=0.8, zorder=3)

    # Full county outlines (dashed) for intersecting counties
    county_in.plot(ax=ax, color="none", edgecolor=county_edge,
                   linewidth=0.5, linestyle="--", zorder=4)

    # Utility boundary on top
    utility_gdf.boundary.plot(ax=ax, color=util_edge, linewidth=1.8, zorder=5)

    # County labels (abbreviate long names)
    for _, row in county_in.iterrows():
        centroid = row.geometry.centroid
        # Use county name, truncate if too long
        label = row.get("NAME", row["COUNTYFP"])
        if len(label) > 15:
            label = label[:12] + "."
        ax.annotate(label, xy=(centroid.x, centroid.y),
                    fontsize=5, ha="center", va="center",
                    color="#1a1a1a", zorder=6)

    ax.set_title(title, fontsize=11, fontweight="bold", pad=8)
    ax.set_axis_off()

# ── Plot ──────────────────────────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(22, 10))

draw_panel(
    ax1, dominion, county, county_in_dom, county_clipped_dom,
    DOM_FILL, DOM_EDGE, DOM_COUNTY, DOM_COUNTY_EDG,
    f"Dominion Virginia Power\n({len(county_in_dom)} Counties intersect)",
)
draw_panel(
    ax2, apco, county, county_in_apco, county_clipped_apco,
    APCO_FILL, APCO_EDGE, APCO_COUNTY, APCO_COUNTY_EDG,
    f"Appalachian Power (APCo)\n({len(county_in_apco)} Counties intersect)",
)

# ── Shared legend ─────────────────────────────────────────────────────────────
legend_handles = [
    mpatches.Patch(facecolor=DOM_FILL,  edgecolor=DOM_EDGE,
                   label="Dominion territory"),
    mpatches.Patch(facecolor=DOM_COUNTY,  alpha=0.6, edgecolor=DOM_COUNTY_EDG,
                   label="County clipped to Dominion"),
    mpatches.Patch(facecolor=APCO_FILL, edgecolor=APCO_EDGE,
                   label="APCo territory"),
    mpatches.Patch(facecolor=APCO_COUNTY, alpha=0.6, edgecolor=APCO_COUNTY_EDG,
                   label="County clipped to APCo"),
    mpatches.Patch(facecolor="#e8e8e8", edgecolor="#aaaaaa",
                   label="All VA 2025 Counties (background)"),
    mpatches.Patch(facecolor="none", edgecolor="#555555", linestyle="--",
                   label="Full County boundary (before clip)"),
]
fig.legend(handles=legend_handles, loc="lower center", ncol=3,
           fontsize=9, framealpha=0.9, bbox_to_anchor=(0.5, 0.01))

fig.suptitle(
    "Virginia 2025 Counties Clipped to Electric Utility Service Territories\n"
    "(tl_2025_51_county  x  Dominion_Virginia_Power.shp / APCo.shp)",
    fontsize=13, fontweight="bold", y=1.01,
)

plt.tight_layout(rect=[0, 0.07, 1, 1])
plt.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
print(f"Map saved -> {OUT_PNG}")
plt.close()
plt.close()
