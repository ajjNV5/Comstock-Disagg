"""
Visual check: two-panel map showing 2010 PUMAs clipped to
(left)  Dominion Virginia Power territory
(right) Appalachian Power (APCo) territory

Output: puma_dominion_check.png
"""

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import os

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DOMINION_SHP = os.path.join(BASE_DIR, "Dominion_Virginia_Power.shp")
APCO_SHP     = os.path.join(BASE_DIR, "APCo.shp")
PUMA_SHP     = os.path.join(BASE_DIR, "tl_2020_51_puma10", "tl_2020_51_puma10.shp")
OUT_PNG      = os.path.join(BASE_DIR, "puma_dominion_check.png")

PLOT_CRS = "EPSG:3968"   # NAD83 / Virginia South

# ── Colors (matching original ArcGIS symbology) ───────────────────────────────
# Dominion: yellow fill  rgba(255,255,0)  -> use a muted version for readability
DOM_FILL     = "#fffaaa"
DOM_EDGE     = "#004a99"
DOM_PUMA     = "#ffd700"
DOM_PUMA_EDG = "#7a6000"

# APCo: red  rgba(205,46,49)
APCO_FILL     = "#f4b8b9"
APCO_EDGE     = "#cd2e31"
APCO_PUMA     = "#cd2e31"
APCO_PUMA_EDG = "#7a0000"

# ── Load & reproject ──────────────────────────────────────────────────────────
print("Loading shapefiles...")
dominion = gpd.read_file(DOMINION_SHP).to_crs(PLOT_CRS)
apco     = gpd.read_file(APCO_SHP).to_crs(PLOT_CRS)
puma     = gpd.read_file(PUMA_SHP).to_crs(PLOT_CRS)

dominion_union = dominion.union_all()
apco_union     = apco.union_all()

puma_in_dom  = puma[puma.geometry.intersects(dominion_union)].copy()
puma_in_apco = puma[puma.geometry.intersects(apco_union)].copy()
puma_out_dom  = puma[~puma.geometry.intersects(dominion_union)].copy()
puma_out_apco = puma[~puma.geometry.intersects(apco_union)].copy()

puma_clipped_dom  = gpd.clip(puma_in_dom,  dominion)
puma_clipped_apco = gpd.clip(puma_in_apco, apco)

print(f"  PUMAs intersecting Dominion : {len(puma_in_dom)}")
print(f"  PUMAs intersecting APCo     : {len(puma_in_apco)}")

# ── Helper: draw one panel ────────────────────────────────────────────────────
def draw_panel(ax, utility_gdf, puma_all, puma_in, puma_clipped,
               util_fill, util_edge, puma_fill, puma_edge, title):
    # All VA PUMAs as grey background context
    puma_all.plot(ax=ax, color="#e8e8e8", edgecolor="#aaaaaa",
                  linewidth=0.3, zorder=1)

    # Utility territory fill
    utility_gdf.plot(ax=ax, color=util_fill, edgecolor=util_edge,
                     linewidth=1.5, zorder=2)

    # Clipped PUMA fill
    puma_clipped.plot(ax=ax, color=puma_fill, alpha=0.55,
                      edgecolor=puma_edge, linewidth=0.8, zorder=3)

    # Full PUMA outlines (dashed) for intersecting PUMAs
    puma_in.plot(ax=ax, color="none", edgecolor=puma_edge,
                 linewidth=0.5, linestyle="--", zorder=4)

    # Utility boundary on top
    utility_gdf.boundary.plot(ax=ax, color=util_edge, linewidth=1.8, zorder=5)

    # PUMA labels
    for _, row in puma_in.iterrows():
        centroid = row.geometry.centroid
        ax.annotate(row["PUMACE10"], xy=(centroid.x, centroid.y),
                    fontsize=5, ha="center", va="center",
                    color="#1a1a1a", zorder=6)

    ax.set_title(title, fontsize=11, fontweight="bold", pad=8)
    ax.set_axis_off()

# ── Plot ──────────────────────────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(22, 10))

draw_panel(
    ax1, dominion, puma, puma_in_dom, puma_clipped_dom,
    DOM_FILL, DOM_EDGE, DOM_PUMA, DOM_PUMA_EDG,
    f"Dominion Virginia Power\n({len(puma_in_dom)} PUMAs intersect)",
)
draw_panel(
    ax2, apco, puma, puma_in_apco, puma_clipped_apco,
    APCO_FILL, APCO_EDGE, APCO_PUMA, APCO_PUMA_EDG,
    f"Appalachian Power (APCo)\n({len(puma_in_apco)} PUMAs intersect)",
)

# ── Shared legend ─────────────────────────────────────────────────────────────
legend_handles = [
    mpatches.Patch(facecolor=DOM_FILL,  edgecolor=DOM_EDGE,
                   label="Dominion territory"),
    mpatches.Patch(facecolor=DOM_PUMA,  alpha=0.6, edgecolor=DOM_PUMA_EDG,
                   label="PUMA clipped to Dominion"),
    mpatches.Patch(facecolor=APCO_FILL, edgecolor=APCO_EDGE,
                   label="APCo territory"),
    mpatches.Patch(facecolor=APCO_PUMA, alpha=0.6, edgecolor=APCO_PUMA_EDG,
                   label="PUMA clipped to APCo"),
    mpatches.Patch(facecolor="#e8e8e8", edgecolor="#aaaaaa",
                   label="All VA 2010 PUMAs (background)"),
    mpatches.Patch(facecolor="none", edgecolor="#555555", linestyle="--",
                   label="Full PUMA boundary (before clip)"),
]
fig.legend(handles=legend_handles, loc="lower center", ncol=3,
           fontsize=9, framealpha=0.9, bbox_to_anchor=(0.5, 0.01))

fig.suptitle(
    "Virginia 2010 PUMAs Clipped to Electric Utility Service Territories\n"
    "(tl_2020_51_puma10  x  Dominion_Virginia_Power.shp / APCo.shp)",
    fontsize=13, fontweight="bold", y=1.01,
)

plt.tight_layout(rect=[0, 0.07, 1, 1])
plt.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
print(f"Map saved -> {OUT_PNG}")
plt.close()
plt.close()
