"""
Download Virginia Electric Service Territory data from ArcGIS REST service
and create a styled map matching the original layer symbology.
"""

import requests
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from io import StringIO
import json
import os

# ── Config ────────────────────────────────────────────────────────────────────
SERVICE_URL = (
    "https://services3.arcgis.com/Ww6Zhg5FR2pLMf1C/ArcGIS/rest/services"
    "/VA_Electric_2016/FeatureServer/0"
)
QUERY_URL = SERVICE_URL + "/query"
OUTPUT_GEOJSON = os.path.join(os.path.dirname(__file__), "va_electric_2016.geojson")
OUTPUT_MAP     = os.path.join(os.path.dirname(__file__), "va_electric_2016_map.png")

# ── Color lookup from the renderer (RGBA → matplotlib tuple) ──────────────────
def rgba_to_mpl(r, g, b, a=255):
    return (r / 255, g / 255, b / 255, a / 255)

PROVIDER_STYLES = {
    "APC":                  {"color": rgba_to_mpl(205, 46,  49),  "label": "APCo"},
    "ODPC":                 {"color": rgba_to_mpl(0,   115, 76),  "label": "Kentucky Utilities"},
    "VEPCO":                {"color": rgba_to_mpl(255, 255, 0),   "label": "Dominion Virginia Power"},
    "ANEC":                 {"color": rgba_to_mpl(244, 142, 73),  "label": "A&N"},
    "BARC":                 {"color": rgba_to_mpl(0,   0,   0),   "label": "BARC"},
    "CBEC":                 {"color": rgba_to_mpl(76,  230, 0),   "label": "Craig-Botetourt EC"},
    "CEC":                  {"color": rgba_to_mpl(115, 178, 115), "label": "Community EC"},
    "CVEC":                 {"color": rgba_to_mpl(0,   197, 255), "label": "CVEC"},
    "MEC":                  {"color": rgba_to_mpl(255, 190, 190), "label": "Mecklenburg EC"},
    "NNEC":                 {"color": rgba_to_mpl(255, 234, 190), "label": "Northern Neck EC"},
    "NOVEC":                {"color": rgba_to_mpl(156, 122, 80),  "label": "Northern Virginia EC"},
    "PVEC":                 {"color": rgba_to_mpl(71,  71,  71),  "label": "Powell Valley EC"},
    "PGEC":                 {"color": rgba_to_mpl(102, 153, 205), "label": "Prince George EC"},
    "REC":                  {"color": rgba_to_mpl(0,   0,   0),   "label": "Rappahannock EC"},
    "SSEC":                 {"color": rgba_to_mpl(225, 225, 225), "label": "Southside EC"},
    "SVEC":                 {"color": rgba_to_mpl(255, 127, 127), "label": "Shenandoah Valley EC"},
    "BristolPowerBoard":    {"color": rgba_to_mpl(200, 200, 200, 180), "label": "Bristol Power Board"},
    "CityOfBedford":        {"color": rgba_to_mpl(200, 200, 200, 180), "label": "City of Bedford"},
    "CityOfDanville":       {"color": rgba_to_mpl(200, 200, 200, 180), "label": "City of Danville"},
    "CityOfManassas":       {"color": rgba_to_mpl(200, 200, 200, 180), "label": "City of Manassas"},
    "CityOfMartinsville":   {"color": rgba_to_mpl(200, 200, 200, 180), "label": "City of Martinsville"},
    "CityOfRadford":        {"color": rgba_to_mpl(200, 200, 200, 180), "label": "City of Radford"},
    "CityOfSalem":          {"color": rgba_to_mpl(200, 200, 200, 180), "label": "City of Salem"},
    "Franklin":             {"color": rgba_to_mpl(200, 200, 200, 180), "label": "Franklin"},
    "HarrisonburgElecCom":  {"color": rgba_to_mpl(200, 200, 200, 180), "label": "Harrisonburg Elec Com"},
    "Richlands":            {"color": rgba_to_mpl(255, 255, 255), "label": "Richlands"},
    "TownOfBlackstone":     {"color": rgba_to_mpl(200, 200, 200, 180), "label": "Town of Blackstone"},
    "TownOfCulpeper":       {"color": rgba_to_mpl(255, 255, 255), "label": "Town of Culpeper"},
    "TownOfElkton":         {"color": rgba_to_mpl(200, 200, 200, 180), "label": "Town of Elkton"},
    "TownOfFrontRoyal":     {"color": rgba_to_mpl(255, 255, 255), "label": "Town of Front Royal"},
    "TownofWakefield":      {"color": rgba_to_mpl(255, 255, 255), "label": "Town of Wakefield"},
    "VPI&SU":               {"color": rgba_to_mpl(200, 200, 200, 180), "label": "VPI&SU"},
}
DEFAULT_COLOR = rgba_to_mpl(180, 180, 180)


# ── Step 1: Download all features (paginated) ─────────────────────────────────
def download_all_features(query_url, page_size=1000):
    all_features = []
    offset = 0
    crs = None

    print("Downloading features from ArcGIS REST service...")
    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        }
        resp = requests.get(query_url, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        print(f"  Fetched {len(features)} features (offset {offset})")
        all_features.extend(features)

        if crs is None:
            crs = data.get("crs")

        # Stop when we get fewer records than requested (last page)
        if len(features) < page_size:
            break
        offset += page_size

    print(f"Total features downloaded: {len(all_features)}")

    geojson = {
        "type": "FeatureCollection",
        "features": all_features,
    }
    if crs:
        geojson["crs"] = crs
    return geojson


# ── Step 2: Save GeoJSON ──────────────────────────────────────────────────────
def save_geojson(geojson, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson, f)
    print(f"GeoJSON saved → {path}")


# ── Step 3: Create the map ────────────────────────────────────────────────────
def create_map(gdf, output_path):
    # Expects gdf already in WGS84 (EPSG:4326)

    fig, ax = plt.subplots(1, 1, figsize=(18, 10))
    ax.set_aspect("equal")

    legend_handles = []
    seen = set()

    for provider, style in PROVIDER_STYLES.items():
        subset = gdf[gdf["Provider"] == provider]
        if subset.empty:
            continue
        color = style["color"]
        label = style["label"]

        # Hatched fill for PGEC and SVEC (BackwardDiagonal in original)
        hatch = "//" if provider in ("PGEC", "SVEC") else None

        subset.plot(
            ax=ax,
            color=color,
            edgecolor="black",
            linewidth=0.3,
            hatch=hatch,
        )

        if provider not in seen:
            patch = mpatches.Patch(facecolor=color, edgecolor="black",
                                   linewidth=0.5, hatch=hatch, label=label)
            legend_handles.append(patch)
            seen.add(provider)

    # Plot any providers not in our lookup with a default color
    unknown = gdf[~gdf["Provider"].isin(PROVIDER_STYLES)]
    if not unknown.empty:
        unknown.plot(ax=ax, color=DEFAULT_COLOR, edgecolor="black", linewidth=0.3)

    ax.set_title("Virginia Electric Service Territories (2016)", fontsize=16, pad=12)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(
        handles=legend_handles,
        loc="lower left",
        fontsize=7,
        title="Provider",
        title_fontsize=8,
        framealpha=0.9,
        ncol=2,
    )
    ax.set_facecolor("#d0e8f5")  # light blue background (water/outside)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Map saved → {output_path}")
    plt.show()


# ── Step 4: Export individual provider files ──────────────────────────────────
def export_provider(gdf, provider_code, label, out_dir):
    subset = gdf[gdf["Provider"] == provider_code].copy()
    if subset.empty:
        print(f"  No features found for provider '{provider_code}', skipping.")
        return

    safe_label = label.replace(" ", "_").replace("&", "and")
    geojson_path = os.path.join(out_dir, f"{safe_label}.geojson")
    shp_path     = os.path.join(out_dir, f"{safe_label}.shp")

    subset.to_file(geojson_path, driver="GeoJSON")
    print(f"  GeoJSON -> {geojson_path}  ({len(subset)} features)")

    subset.to_file(shp_path, driver="ESRI Shapefile")
    print(f"  Shapefile -> {shp_path}  ({len(subset)} features)")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Download (or reuse cached GeoJSON)
    if not os.path.exists(OUTPUT_GEOJSON):
        geojson = download_all_features(QUERY_URL)
        save_geojson(geojson, OUTPUT_GEOJSON)
    else:
        print(f"Using cached GeoJSON: {OUTPUT_GEOJSON}")

    # Load into GeoDataFrame
    gdf = gpd.read_file(OUTPUT_GEOJSON)
    print(f"Loaded {len(gdf)} features. CRS: {gdf.crs}")
    print("Provider values:", gdf["Provider"].unique())

    # Assign CRS if missing, then reproject to WGS84
    if gdf.crs is None:
        gdf = gdf.set_crs(
            "+proj=lcc +lat_1=37 +lat_2=39.5 +lat_0=36 +lon_0=-79.5"
            " +x_0=0 +y_0=0 +ellps=GRS80 +units=m +no_defs"
        )
    gdf = gdf.to_crs(epsg=4326)

    # Export individual providers
    OUT_DIR = os.path.dirname(OUTPUT_GEOJSON)
    EXPORTS = [
        ("APC",   "APCo"),
        ("VEPCO", "Dominion_Virginia_Power"),
    ]
    print("\nExporting individual provider files...")
    for code, label in EXPORTS:
        export_provider(gdf, code, label, OUT_DIR)

    # Create and save map
    create_map(gdf, OUTPUT_MAP)
