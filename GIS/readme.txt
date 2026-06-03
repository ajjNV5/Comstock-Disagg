================================================================================
  GIS_VA — Virginia Electric Service Territory & PUMA Mapping
================================================================================

PURPOSE
-------
This project maps Virginia electric utility service territories (2016) against
U.S. Census Public Use Microdata Areas (PUMAs) to determine which PUMA regions
fall within Dominion Virginia Power's service territory, and what percentage of
each PUMA's area is covered. This supports use with ResStock, which uses 2010
PUMA definitions as geographic identifiers for building stock modeling.


--------------------------------------------------------------------------------
DATA SOURCES & DOWNLOAD LOCATIONS
--------------------------------------------------------------------------------

1. Virginia Electric Service Territory (2016)
   Source:  ArcGIS REST FeatureServer (publicly hosted)
   URL:     https://services3.arcgis.com/Ww6Zhg5FR2pLMf1C/ArcGIS/rest/services/VA_Electric_2016/FeatureServer/0
   Layer:   Export_Output_6_Project (ID: 0)
   Format:  Downloaded as GeoJSON via the /query endpoint (f=geojson, where=1=1)
   Files:   va_electric_2016.geojson          — full dataset (all 34 providers)
            Dominion_Virginia_Power.geojson    — Dominion (VEPCO) territory only
            Dominion_Virginia_Power.shp/.dbf/.prj/.shx/.cpg
            APCo.geojson                       — Appalachian Power territory only
            APCo.shp/.dbf/.prj/.shx/.cpg
   Note:    Data was last edited 8/16/2016 per the service metadata.
            Provider field code for Dominion is "VEPCO".

2. Virginia 2010 Census PUMA Boundaries (used by ResStock)
   Source:  U.S. Census Bureau TIGER/Line Shapefiles
   URL:     https://www2.census.gov/geo/tiger/TIGER2020/PUMA/tl_2020_51_puma10.zip
   Vintage: 2010 PUMA definitions (required to match ResStock input geography)
   Files:   tl_2020_51_puma10/tl_2020_51_puma10.shp (and sidecar files)
            tl_2020_51_puma10.zip
   Key columns:
     PUMACE10  — 5-digit PUMA code (e.g. "51206")
     GEOID10   — 7-digit GEOID (state FIPS + PUMA code, e.g. "5151206")
     NAMELSAD10 — Human-readable PUMA name

3. Virginia 2020 Census PUMA Boundaries (reference only, NOT used for ResStock)
   Source:  U.S. Census Bureau TIGER/Line Shapefiles
   URL:     https://www2.census.gov/geo/tiger/TIGER2025/PUMA/ (tl_2025_51_puma20)
   Files:   tl_2025_51_puma20/ (folder with shapefile and sidecar files)
   Note:    These are 2020-vintage boundaries. ResStock does NOT use this vintage.
            Kept for reference only.

4. ResStock PUMA ID Reference (in.puma.txt — pre-existing)
   Source:  NREL ResStock documentation / input file
   URL:     https://resstock.nrel.gov  (see ResStock documentation for geography inputs)
   File:    tl_2025_51_puma20/in.puma.txt
   Format:  NHGIS GISJOIN identifiers, e.g. "G51051206"
            Structure: G + state_FIPS(2) + county_pad(1,always 0) + PUMACE10(5)
            Example:   G51051206 -> state=51 (VA), PUMACE10=51206


--------------------------------------------------------------------------------
FILE INVENTORY
--------------------------------------------------------------------------------

Scripts:
  download_and_map_va_electric.py
    — Downloads all features from the ArcGIS REST service, saves as GeoJSON,
      exports per-provider shapefiles/GeoJSONs, and renders a styled map image.

  puma_dominion_overlap.py
    — Loads the Dominion shapefile and the 2010 PUMA shapefile, computes the
      intersection of each PUMA with Dominion's territory, and outputs the
      percentage of each PUMA's area that falls within Dominion's boundary.

Outputs:
  va_electric_2016.geojson       — All 34 utility service territories (WGS84)
  va_electric_2016_map.png       — Rendered map with original ArcGIS symbology
  Dominion_Virginia_Power.*      — Dominion territory only (GeoJSON + shapefile)
  APCo.*                         — Appalachian Power territory only
  puma_dominion_overlap.csv      — 3-column result table (see format below)
  in.puma.txt                    — List of PUMACE10 codes intersecting Dominion


--------------------------------------------------------------------------------
PUMA ID MAPPING — KEY CONCEPT
--------------------------------------------------------------------------------

ResStock identifies geographies using NHGIS GISJOIN codes, formatted as:

    G + [2-digit state FIPS] + [1 zero pad] + [5-digit PUMACE10]

    Example:  G51051206
              G   = GISJOIN prefix
              51  = Virginia state FIPS code
              0   = padding zero
              51206 = PUMACE10 code in the 2010 Census PUMA shapefile

To map a ResStock PUMA ID to the Census shapefile:
    1. Strip the leading "G", the 2-digit state code, and the padding "0"
       (i.e., take characters 4 onward)
    2. The remaining 5 digits are the PUMACE10 value in tl_2020_51_puma10.shp

    Python example:
        gisjoin = "G51051206"
        pumace10 = gisjoin[4:]   # -> "51206"

WHY TWO PUMA SHAPEFILES?
  ResStock was built using 2010 Census PUMA boundaries (tl_2020_51_puma10).
  The Census Bureau released new 2020 PUMA boundaries (tl_2025_51_puma20) which
  have different codes and different geographic extents. Using the wrong vintage
  will result in ~82% of codes failing to match (46 of 56 unmatched in testing).
  Always use the 2010-vintage shapefile when working with ResStock data.


--------------------------------------------------------------------------------
OUTPUT FORMAT: puma_dominion_overlap.csv
--------------------------------------------------------------------------------

  Column            Description
  --------          -----------------------------------------------------------
  PUMA_ID           5-digit PUMACE10 code (matches tl_2020_51_puma10 shapefile)
  ResStock_GISJOIN  NHGIS GISJOIN identifier used by ResStock (e.g. G51051206)
  In_Dominion       True if any portion of the PUMA intersects Dominion territory
  Pct_In_Dominion   Percentage (0-100) of PUMA area within Dominion's boundary
  In_APCo           True if any portion of the PUMA intersects APCo territory
  Pct_In_APCo       Percentage (0-100) of PUMA area within APCo's boundary

  Notes:
  - Area calculations use EPSG:3968 (NAD83 / Virginia South, meters) for accuracy
  - A PUMA can appear True for both utilities if it straddles the service boundary
  - PUMAs where Pct_In_Dominion + Pct_In_APCo < 100 are also served by other
    co-op or municipal utilities not analyzed here


--------------------------------------------------------------------------------
KEY FINDINGS
--------------------------------------------------------------------------------

Dominion Virginia Power (VEPCO):
  - 52 of 56 Virginia 2010 PUMAs intersect Dominion's service territory
  - 4 PUMAs have zero Dominion overlap: 51010, 51020, 51040, 51044
    (far southwest/western VA — these are exclusively APCo territory)
  - Several PUMAs are nearly fully within Dominion (>=99%):
    01301, 01302, 04101, 04102, 51165, 51224, 51225, 51235, 51255,
    55001, 55002, 59301–59307, 59308
  - List of intersecting PUMA IDs: in.puma.txt (52 entries)

Appalachian Power (APCo):
  - 10 of 56 Virginia 2010 PUMAs intersect APCo's service territory
  - APCo coverage is concentrated in far southwest/western Virginia
  - 4 PUMAs are predominantly APCo (>73%): 51010, 51020, 51040, 51044
  - 6 PUMAs are split between APCo and other utilities:
      51045  — 49.4% APCo, 14.5% Dominion
      51089  — 15.9% APCo, 21.6% Dominion
      51095  — 48.9% APCo,  4.8% Dominion
      51096  — 39.0% APCo, 13.4% Dominion
      51097  — 50.0% APCo,  5.6% Dominion
      51105  —  0.0% APCo, 28.9% Dominion  (trace APCo overlap)
  - List of intersecting PUMA IDs: in_apco.puma.txt (10 entries)

Coverage overlap between the two utilities:
  - No PUMA is majority-served by both Dominion and APCo simultaneously
  - The boundary between Dominion and APCo runs through the southwestern
    Virginia PUMAs (51xxx series), creating several split-service PUMAs


--------------------------------------------------------------------------------
HOW TO REPRODUCE
--------------------------------------------------------------------------------

Requirements:
    pip install geopandas requests matplotlib

Step 1 — Download electric territory data and export provider shapefiles:
    python download_and_map_va_electric.py
    Outputs: va_electric_2016.geojson, Dominion_Virginia_Power.*, APCo.*,
             va_electric_2016_map.png

Step 2 — Run PUMA overlap analysis:
    python puma_dominion_overlap.py
    Outputs: puma_dominion_overlap.csv, in.puma.txt, in_apco.puma.txt

    Note: Requires tl_2020_51_puma10/ folder (2010 PUMA shapefile).
    If not present, download from:
    https://www2.census.gov/geo/tiger/TIGER2020/PUMA/tl_2020_51_puma10.zip
    and unzip into a folder named tl_2020_51_puma10/

================================================================================
