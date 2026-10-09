"""
GIS Dashboard (Streamlit version)

Run locally:  streamlit run streamlit_app.py
Add layers:   drop .geojson / .shp / .gpkg files into the data/ folder.
"""
import io
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

DATA_DIR = Path(__file__).parent / "data"
PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2"]
VECTOR_EXTS = {".geojson", ".json", ".shp", ".gpkg"}

st.set_page_config(page_title="GIS Dashboard", layout="wide")


def to_wgs84(gdf):
    # Web maps expect WGS84 (EPSG:4326)
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf


@st.cache_data
def load_layer(path):
    return to_wgs84(gpd.read_file(path))


DATA_DIR.mkdir(exist_ok=True)
layers = {
    p.name: load_layer(str(p))
    for p in sorted(DATA_DIR.iterdir())
    if p.suffix.lower() in VECTOR_EXTS
}

# ---------------- Sidebar ----------------
st.sidebar.title("GIS Dashboard")

upload = st.sidebar.file_uploader(
    "Upload a GeoJSON (kept for this visit only)", type=["geojson", "json"]
)
if upload is not None:
    try:
        layers[upload.name] = to_wgs84(gpd.read_file(io.BytesIO(upload.getvalue())))
    except Exception as exc:
        st.sidebar.error(f"Could not read {upload.name}: {exc}")

if not layers:
    st.info("No layers yet. Put .geojson files in the data folder, or upload one in the sidebar.")
    st.stop()

chosen = st.sidebar.multiselect("Layers on the map", list(layers), default=list(layers))
shown = {name: layers[name] for name in chosen}

st.sidebar.subheader("Filter")
target = st.sidebar.selectbox("Layer to filter", chosen) if chosen else None
if target:
    gdf = layers[target]
    columns = [c for c in gdf.columns if c != "geometry"]
    column = st.sidebar.selectbox("Column", ["(no filter)"] + columns)
    if column != "(no filter)":
        s = gdf[column]
        numeric = (
            pd.api.types.is_numeric_dtype(s)
            and not pd.api.types.is_bool_dtype(s)
            and s.notna().any()
        )
        if numeric:
            lo, hi = float(s.min()), float(s.max())
            if lo < hi:
                low, high = st.sidebar.slider(f"{column} between", lo, hi, (lo, hi))
                gdf = gdf[s.between(low, high)]
            else:
                st.sidebar.caption(f"Every value of {column} is {lo}.")
        else:
            options = sorted(s.dropna().astype(str).unique())
            picked = st.sidebar.multiselect(f"Show only these {column} values", options)
            if picked:
                gdf = gdf[s.astype(str).isin(picked)]
    shown[target] = gdf

# ---------------- Map ----------------
m = folium.Map(location=[17.6868, 83.2185], zoom_start=10)
extent = []
for i, (name, g) in enumerate(shown.items()):
    if g.empty:
        continue
    color = PALETTE[i % len(PALETTE)]
    fields = [c for c in g.columns if c != "geometry"]
    folium.GeoJson(
        g.to_json(),
        name=name,
        style_function=lambda feature, c=color: {"color": c, "weight": 2, "fillOpacity": 0.3},
        marker=folium.CircleMarker(radius=6),
        popup=folium.GeoJsonPopup(fields=fields) if fields else None,
    ).add_to(m)
    minx, miny, maxx, maxy = g.total_bounds
    extent += [[miny, minx], [maxy, maxx]]
if extent:
    m.fit_bounds(extent)

try:
    st_folium(m, height=650, use_container_width=True, returned_objects=[])
except TypeError:
    st_folium(m, height=650, returned_objects=[])

st.caption(", ".join(f"{n}: {len(g)} of {len(layers[n])} features" for n, g in shown.items()))
if target:
    with st.expander(f"Table for {target}"):
        st.dataframe(pd.DataFrame(shown[target].drop(columns="geometry")))
