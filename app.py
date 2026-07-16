import streamlit as st
import pandas as pd
import folium
import json
from folium.plugins import HeatMap
from streamlit_folium import st_folium

# Set page configuration
st.set_page_config(layout="wide", page_title="Earthquake Monitoring Dashboard")

# -----------------------------------------------------------------------------
# 1. DATA LOADING FUNCTION
# -----------------------------------------------------------------------------
@st.cache_data
def load_data(filepath="data.geojson"):
    # Load data from the local GeoJSON file
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            geo_data = json.load(f)
    except Exception as e:
        st.error(f"Error loading file: {e}")
        return pd.DataFrame()

    table_rows = []
    # Parse the standard GeoJSON FeatureCollection structure
    for feature in geo_data.get('features', []):
        props = feature.get('properties', {})
        coords = feature.get('geometry', {}).get('coordinates', [0, 0, 0])
        
        # GeoJSON coordinates are formatted as: [longitude, latitude, depth]
        lon, lat, depth = coords[0], coords[1], coords[2]
        
        # Helper function to convert victims data into clean integers
        def clean_num(val):
            try:
                if val == '-' or val is None:
                    return 0
                return int(float(val))
            except:
                return 0
        
        table_rows.append({
            'Magnitude': props.get('mag'),
            'Place': props.get('place'),
            'Depth (km)': depth,
            # The GeoJSON time is an ISO string, so we let pandas infer the datetime format
            'Date': pd.to_datetime(props.get('time')).date(),
            'Latitude': lat,
            'Longitude': lon,
            'Country': props.get('country'),
            'tsunami': props.get('tsunami'),
            'mmi': props.get('mmi'),
            'mmi_level': props.get('mmi_level'),
            'dead': clean_num(props.get('dead')),
            'injured': clean_num(props.get('injured')),
            'impact': props.get('impact')
        })
        
    return pd.DataFrame(table_rows)

df_raw = load_data()

if df_raw.empty:
    st.warning("No data found or failed to parse.")
    st.stop()

# -----------------------------------------------------------------------------
# 2. SIDEBAR FILTERS
# -----------------------------------------------------------------------------
st.sidebar.title("Filters")

# --- Filter 1: Magnitude ---
min_mag = float(df_raw['Magnitude'].min())
max_mag = float(df_raw['Magnitude'].max())
mag_range = st.sidebar.slider(
    "Select Magnitude Range", 
    min_value=min_mag, 
    max_value=max_mag, 
    value=(min_mag, max_mag), 
    step=0.1
)

# --- Filter 2: Date Range ---
min_date = df_raw['Date'].min()
max_date = df_raw['Date'].max()
date_range = st.sidebar.date_input(
    "Select Date Range", 
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# --- Filter 3: Search Location ---
search_location = st.sidebar.text_input("Search Location / Country Name", "").strip()

# --- Filter 3b: Country Filter (Multiple Selections) ---
unique_countries = sorted(df_raw['Country'].dropna().unique())
selected_countries = st.sidebar.multiselect("Select Countries", options=unique_countries, default=[])

# --- Filter 4: Show M6.0+ Scatter Points ---
show_m6_scatter = st.sidebar.checkbox("Show M ≥ 6.0 Earthquake Points", value=True)

# --- Filter 5: Show Tectonic Plates ---
show_plates = st.sidebar.checkbox("Show Tectonic Plates", value=False)

# -----------------------------------------------------------------------------
# 3. APPLY FILTERS TO DATAFRAME
# -----------------------------------------------------------------------------
# Apply Magnitude filter
df_filtered = df_raw[
    (df_raw['Magnitude'] >= mag_range[0]) & 
    (df_raw['Magnitude'] <= mag_range[1])
]

# Apply Date filter (handles case where user selects a single date vs a range)
if isinstance(date_range, tuple) and len(date_range) == 2:
    df_filtered = df_filtered[
        (df_filtered['Date'] >= date_range[0]) & 
        (df_filtered['Date'] <= date_range[1])
    ]
elif isinstance(date_range, tuple) and len(date_range) == 1:
    df_filtered = df_filtered[df_filtered['Date'] == date_range[0]]

# Apply Location filter
if search_location:
    df_filtered = df_filtered[df_filtered['Place'].str.contains(search_location, case=False, na=False)]

# Apply Country filter
if selected_countries:
    df_filtered = df_filtered[df_filtered['Country'].isin(selected_countries)]

# -----------------------------------------------------------------------------
# 4. MAIN LAYOUT & RENDERING
# -----------------------------------------------------------------------------
st.title("Earthquake Hazard Density Analysis")

# High-level metrics row
col1, col2, col3 = st.columns(3)
col1.metric("Total Events Displayed", len(df_filtered))
if not df_filtered.empty:
    col2.metric("Max Magnitude", f"{df_filtered['Magnitude'].max():.1f}")
    col3.metric("Avg Depth", f"{df_filtered['Depth (km)'].mean():.1f} km")
else:
    col2.metric("Max Magnitude", "N/A")
    col3.metric("Avg Depth", "N/A")

st.markdown("---")

if not df_filtered.empty:
    st.subheader("Global Seismic Density Map")
    
    # 1. Initialize Folium Map
    m = folium.Map(location=[0, 120], zoom_start=2, tiles='CartoDB positron')
    
    # 2. Extract [latitude, longitude] pairs and add the HeatMap layer
    heat_data = df_filtered[['Latitude', 'Longitude']].values.tolist()
    
    transparent_gradient = {
        0.2: 'rgba(0, 0, 255, 0.4)',
        0.4: 'rgba(0, 255, 255, 0.5)',
        0.6: 'rgba(0, 255, 0, 0.6)',
        0.8: 'rgba(255, 255, 0, 0.7)',
        1.0: 'rgba(255, 0, 0, 0.8)'
    }
    
    HeatMap(
        heat_data, 
        radius=15, 
        blur=10, 
        max_zoom=1,
        min_opacity=0.1,
        gradient=transparent_gradient
    ).add_to(m)

    # 3. SPATIAL AGGREGATION FOR HOVER TOOLTIPS
    df_agg = df_filtered.copy()
    df_agg['Lat_Bin'] = df_agg['Latitude'].round(0)
    df_agg['Lon_Bin'] = df_agg['Longitude'].round(0)
    
    df_agg = df_agg.sort_values('Magnitude', ascending=False)
    
    grouped = df_agg.groupby(['Lat_Bin', 'Lon_Bin']).agg(
        Num_Earthquakes=('Magnitude', 'count'),
        Max_Mag=('Magnitude', 'first'),
        Max_Mag_Date=('Date', 'first'),
        Area_Details=('Place', 'first'), 
        Lat_Center=('Latitude', 'mean'), 
        Lon_Center=('Longitude', 'mean'),
        Total_Dead=('dead', 'sum'),
        Total_Injured=('injured', 'sum')
    ).reset_index()

    # 4. Overlay invisible interactive markers for general area hover info
    for _, row in grouped.iterrows():
        tooltip_html = f"""
        <div style="font-family: sans-serif; font-size: 14px; min-width: 200px;">
            <b>Area:</b> {row['Area_Details']}<br>
            <b>Earthquakes in Area:</b> {row['Num_Earthquakes']}<br>
            <b>Highest Magnitude:</b> M {row['Max_Mag']} (on {row['Max_Mag_Date']})<br>
            <b>Total Dead (Area):</b> {row['Total_Dead']}<br>
            <b>Total Injured (Area):</b> {row['Total_Injured']}
        </div>
        """
        
        folium.CircleMarker(
            location=[row['Lat_Center'], row['Lon_Center']],
            radius=18,                  
            color='rgba(0,0,0,0)',      
            fill=True,
            fill_color='rgba(0,0,0,0)', 
            tooltip=tooltip_html
        ).add_to(m)

    # 5. Overlay specific scatter points for M >= 6.0 earthquakes if checked
    if show_m6_scatter:
        df_m6_plus = df_filtered[df_filtered['Magnitude'] >= 6.0]
        
        if not df_m6_plus.empty:
            max_m6_mag = df_m6_plus['Magnitude'].max()
            
            for _, row in df_m6_plus.iterrows():
                mag = row['Magnitude']
                
                # Calculate color dynamically: Yellow (6.0) to Red (Max Magnitude)
                if max_m6_mag > 6.0:
                    ratio = (mag - 6.0) / (max_m6_mag - 6.0)
                else:
                    ratio = 1.0  # Default to red if all points are exactly 6.0
                
                # Green channel scales from 255 (Yellow) to 0 (Red)
                g_val = int(255 * (1 - ratio))
                color_hex = f'#ff{g_val:02x}00'
                
                m6_tooltip_html = f"""
                <div style="font-family: sans-serif; font-size: 14px; min-width: 220px; color: #333;">
                    <h4 style="margin-top: 0; color: {color_hex}; text-shadow: 1px 1px 1px #000;">⚠️ Major Earthquake</h4>
                    <b>Magnitude:</b> {mag}<br>
                    <b>Location:</b> {row['Place']}<br>
                    <b>Date:</b> {row['Date']}<br>
                    <b>Depth:</b> {row['Depth (km)']} km<br>
                    <b>Coords:</b> {row['Latitude']:.4f}, {row['Longitude']:.4f}<br>
                    <b>Dead:</b> {row['dead']}<br>
                    <b>Injured:</b> {row['injured']}
                </div>
                """
                
                folium.CircleMarker(
                    location=[row['Latitude'], row['Longitude']],
                    radius=2,
                    color='black',
                    weight=1,
                    fill=True,
                    fill_color=color_hex,
                    fill_opacity=0.9,
                    tooltip=m6_tooltip_html
                ).add_to(m)

    # 6. Overlay Tectonic Plates if checked
    if show_plates:
        try:
            with open("plates.geojson", "r", encoding="utf-8") as f:
                plates_data = json.load(f)
            
            folium.GeoJson(
                plates_data,
                name="Tectonic Plates",
                style_function=lambda feature: {
                    'color': '#2C3E50',
                    'weight': 2.5,
                    'opacity': 0.8,
                    'dashArray': '5, 5'
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=['plate1', 'plate2', 'type', 'feature', 'length'],
                    aliases=['Plate 1:', 'Plate 2:', 'Boundary Type:', 'Feature Name:', 'Length:'],
                    localize=True,
                    style=("background-color: white; color: #333333; font-family: arial; font-size: 13px; padding: 10px;")
                )
            ).add_to(m)
        except Exception as e:
            st.error(f"Error loading plates.geojson: {e}")
    
    # 7. Render map back into Streamlit canvas
    st_folium(m, width=1400, height=500, returned_objects=[])
    
    st.markdown("---")
    
    st.subheader("Data Details")
    st.dataframe(
        df_filtered[['Magnitude', 'Place', 'Depth (km)', 'Date', 'tsunami', 'mmi', 'mmi_level', 'dead', 'injured', 'impact']], 
        use_container_width=True, 
        hide_index=True
    )
else:
    st.info("No earthquake records match the selected sidebar filters. Try expanding your search bounds.")