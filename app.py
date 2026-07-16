import streamlit as st
import pandas as pd
import json
import plotly.graph_objects as go

# Set page configuration
st.set_page_config(layout="wide", page_title="Earthquake Monitoring Dashboard")

# -----------------------------------------------------------------------------
# 1. FAST DATA LOADING (Vectorized)
# -----------------------------------------------------------------------------
# @st.cache_data
# def load_data(filepath="data.geojson"):
#     try:
#         with open(filepath, "r", encoding="utf-8") as f:
#             geo_data = json.load(f)
#     except Exception as e:
#         st.error(f"Error loading file: {e}")
#         return pd.DataFrame()

#     table_rows = []
    
#     # Helper to clean numeric values quickly
#     def clean_num(val):
#         if val == '-' or val is None: return 0
#         try: return int(float(val))
#         except: return 0

#     for feature in geo_data.get('features', []):
#         props = feature.get('properties', {})
#         coords = feature.get('geometry', {}).get('coordinates', [0, 0, 0])
        
#         table_rows.append({
#             'Magnitude': props.get('mag'),
#             'Place': props.get('place'),
#             'Depth (km)': coords[2],
#             'time_str': props.get('time'),  # Keep as string for fast vectorized parsing
#             'Latitude': coords[1],
#             'Longitude': coords[0],
#             'Country': props.get('country'),
#             'tsunami': props.get('tsunami'),
#             'mmi': props.get('mmi'),
#             'mmi_level': props.get('mmi_level'),
#             'dead': clean_num(props.get('dead')),
#             'injured': clean_num(props.get('injured')),
#             'impact': props.get('impact')
#         })
        
#     df = pd.DataFrame(table_rows)
    
#     if not df.empty:
#         # Fast vectorized date conversion
#         df['Date'] = pd.to_datetime(df['time_str'], format='ISO8601', errors='coerce').dt.date
#         df = df.drop(columns=['time_str'])
        
#     return df

@st.cache_data
def load_data(geojson_path="data.geojson", csv_path="victims.csv"):
    # 1. Load GeoJSON
    try:
        with open(geojson_path, "r", encoding="utf-8") as f:
            geo_data = json.load(f)
        
        # Convert features to a DataFrame
        features = geo_data.get('features', [])
        data_list = []
        for f in features:
            props = f.get('properties', {})
            # Extract coordinates for lat/lon
            coords = f.get('geometry', {}).get('coordinates', [0, 0, 0])
            props['Latitude'] = coords[1]
            props['Longitude'] = coords[0]
            props['Depth (km)'] = coords[2]
            data_list.append(props)
        
        df_geojson = pd.DataFrame(data_list)
    except Exception as e:
        st.error(f"Error loading GeoJSON: {e}")
        return pd.DataFrame()

    # 2. Load CSV
    try:
        df_victims = pd.read_csv(csv_path)
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        return pd.DataFrame()

    # 3. Prepare for Merge
    # Columns to merge on
    merge_cols = ['date', 'month', 'year', 'country', 'km', 'mag']
    
    # Ensure types match across both DataFrames for the merge columns
    for col in merge_cols:
        df_geojson[col] = df_geojson[col].astype(str)
        df_victims[col] = df_victims[col].astype(str)
        
    # 4. Merge
    df = pd.merge(df_geojson, df_victims, on=merge_cols, how='left')
    df = df.rename(columns={'mag':'Magnitude', 'place':'Place', 'time':'Time', 'mmi':'MMI', 'tsunami':'Tsunami', 'type':'Type', 
                       'title':'Title', 'country':'Country', 'impact':'Impact', 'dead':'Dead', 'injured':'Injured', 'mmi_level':'MMI_Level'})
    
    # --- TYPE CONVERSION FIX ---
    # Ensure numeric columns are actually numeric
    df['Magnitude'] = pd.to_numeric(df['Magnitude'], errors='coerce')
    df['Depth (km)'] = pd.to_numeric(df['Depth (km)'], errors='coerce')
    df['Dead'] = pd.to_numeric(df['Dead'], errors='coerce').fillna(0)
    df['Injured'] = pd.to_numeric(df['Injured'], errors='coerce').fillna(0)
    # ---------------------------
    
    # Clean up impact columns (replace NaN with placeholders)
    fill_cols = ['Impact', 'MMI_Level']
    for col in fill_cols:
        if col in df.columns:
            df[col] = df[col].fillna("-")
            
    # 5. Format Date
    df['Date'] = pd.to_datetime(df['Time'], format='ISO8601', errors='coerce').dt.date
    
    return df
        
    # # 4. Merge
    # df = pd.merge(df_geojson, df_victims, on=merge_cols, how='left')
    
    # # Clean up impact columns (replace NaN with placeholders if needed)
    # fill_cols = ['dead', 'injured', 'impact', 'mmi_level']
    # for col in fill_cols:
    #     if col in df.columns:
    #         df[col] = df[col].fillna("-")
            
    # # 5. Format Date
    # # 'time' is available from GeoJSON; ensure Date column exists
    # df['Date'] = pd.to_datetime(df['time'], format='ISO8601', errors='coerce').dt.date
    
    # return df

df_raw = load_data()
print(df_raw.columns)

if df_raw.empty:
    st.warning("No data found or failed to parse.")
    st.stop()

# -----------------------------------------------------------------------------
# 2. SIDEBAR FILTERS
# -----------------------------------------------------------------------------
st.sidebar.title("Filters")

# Magnitude Filter
min_mag, max_mag = float(df_raw['Magnitude'].min()), float(df_raw['Magnitude'].max())
mag_range = st.sidebar.slider("Select Magnitude Range", min_mag, max_mag, (min_mag, max_mag), 0.1)

# Date Filter
min_date, max_date = df_raw['Date'].min(), df_raw['Date'].max()
date_range = st.sidebar.date_input("Select Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)

# Location Filter
search_location = st.sidebar.text_input("Search Location / Country Name", "").strip()

# Country Filter
unique_countries = sorted(df_raw['Country'].dropna().unique())
selected_countries = st.sidebar.multiselect("Select Countries", options=unique_countries, default=[])

# Layer Toggles
show_m7_scatter = st.sidebar.checkbox("Show M ≥ 7.0 Earthquake Points", value=True)
show_plates = st.sidebar.checkbox("Show Tectonic Plates", value=False)

# -----------------------------------------------------------------------------
# 3. APPLY FILTERS
# -----------------------------------------------------------------------------
df_filtered = df_raw[(df_raw['Magnitude'] >= mag_range[0]) & (df_raw['Magnitude'] <= mag_range[1])]

if isinstance(date_range, tuple):
    if len(date_range) == 2:
        df_filtered = df_filtered[(df_filtered['Date'] >= date_range[0]) & (df_filtered['Date'] <= date_range[1])]
    elif len(date_range) == 1:
        df_filtered = df_filtered[df_filtered['Date'] == date_range[0]]

if search_location:
    df_filtered = df_filtered[df_filtered['Place'].str.contains(search_location, case=False, na=False)]

if selected_countries:
    df_filtered = df_filtered[df_filtered['Country'].isin(selected_countries)]

# -----------------------------------------------------------------------------
# 4. DASHBOARD LAYOUT & METRICS
# -----------------------------------------------------------------------------
st.title("Earthquake Hazard Density Analysis")

# Calculate totals for the metrics
total_events = len(df_filtered)
total_tsunami = int(pd.to_numeric(df_filtered['Tsunami'], errors='coerce').fillna(0).sum())
total_dead = int(df_filtered['Dead'].sum())
total_injured = int(df_filtered['Injured'].sum())

# Display metrics in two rows
row1 = st.columns(6)
row1[0].metric("Total Events", total_events)
row1[1].metric("Max Magnitude", f"{df_filtered['Magnitude'].max():.1f}" if not df_filtered.empty else "N/A")
row1[2].metric("Avg Depth", f"{df_filtered['Depth (km)'].mean():.1f} km" if not df_filtered.empty else "N/A")
row1[3].metric("Total Tsunami Occurrences", total_tsunami)
row1[4].metric("Total Deaths", total_dead)
row1[5].metric("Total Injured", total_injured)

st.markdown("---")

# -----------------------------------------------------------------------------
# 5. PLOTLY MAP RENDERING
# -----------------------------------------------------------------------------
if not df_filtered.empty:
    st.subheader("Global Seismic Density Map")
    
    fig = go.Figure()

    # --- Layer 1: Density / Heatmap ---
    # Plotly's Densitymapbox uses a Z value to weight the heatmap. 
    # We pass 1s to replicate a pure density map, or use magnitude for weighted intensity.
    fig.add_trace(go.Densitymapbox(
        lat=df_filtered['Latitude'],
        lon=df_filtered['Longitude'],
        z=[1] * len(df_filtered), 
        radius=10,
        colorscale=[[0, 'rgba(0,0,255,0)'], [0.5, 'blue'], [0.6, 'cyan'], [0.7, 'green'], [0.8, 'yellow'], [0.9, 'orange'], [1.0, 'red']],
        opacity=0.2,
        showscale=False,
        hoverinfo='skip',
        name='Density'
    ))

    # --- Layer 2: Aggregated Area Hover (Invisible Markers) ---
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
        Total_Dead=('Dead', 'sum'),
        Total_Injured=('Injured', 'sum')
    ).reset_index()

    hover_texts = [
        f"<b>Area:</b> {row['Area_Details']}<br>"
        f"<b>Earthquakes in Area:</b> {row['Num_Earthquakes']}<br>"
        f"<b>Highest Magnitude:</b> M {row['Max_Mag']} (on {row['Max_Mag_Date']})<br>"
        f"<b>Total Dead:</b> {row['Total_Dead']}<br>"
        f"<b>Total Injured:</b> {row['Total_Injured']}"
        for _, row in grouped.iterrows()
    ]

    fig.add_trace(go.Scattermapbox(
        lat=grouped['Lat_Center'],
        lon=grouped['Lon_Center'],
        mode='markers',
        marker=dict(size=20, opacity=0), # Invisible trigger area
        text=hover_texts,
        hoverinfo='text',
        name='Area Summary'
    ))

    # --- Layer 3: m7.0+ Scatter Points ---
    if show_m7_scatter:
        df_m7 = df_filtered[df_filtered['Magnitude'] >= 7.0]
        if not df_m7.empty:
            m7_hover_texts = [
                f"<b>⚠️ Major Earthquake</b><br>"
                f"<b>Magnitude:</b> {row['Magnitude']}<br>"
                f"<b>Location:</b> {row['Place']}<br>"
                f"<b>Date:</b> {row['Date']}<br>"
                f"<b>Depth:</b> {row['Depth (km)']} km<br>"
                f"<b>Coords:</b> {row['Latitude']:.4f}, {row['Longitude']:.4f}<br>"
                f"<b>Dead:</b> {row['Dead']}<br>"
                f"<b>Injured:</b> {row['Injured']}"
                for _, row in df_m7.iterrows()
            ]

            fig.add_trace(go.Scattermapbox(
                lat=df_m7['Latitude'],
                lon=df_m7['Longitude'],
                mode='markers',
                marker=dict(
                    size=8,
                    color=df_m7['Magnitude'],
                    colorscale=[[0, "#ff7b00"], [1, "#aa0000"]], # Yellow to Red
                    cmin=7.0,
                    cmax=df_filtered['Magnitude'].max() if df_filtered['Magnitude'].max() > 7.0 else 7.1,
                    showscale=True,
                    colorbar=dict(title="Mag ≥ 7.0", x=0.95)
                ),
                text=m7_hover_texts,
                hoverinfo='text',
                name='M ≥ 7.0'
            ))

    # --- Layer 4: Tectonic Plates ---
    # Plotly requires extracting LineString coordinates to map them seamlessly with hoverdata
    if show_plates:
        try:
            with open("plates.geojson", "r", encoding="utf-8") as f:
                plates_data = json.load(f)
            
            p_lats, p_lons, p_texts = [], [], []
            
            for feature in plates_data.get('features', []):
                geom_type = feature['geometry']['type']
                coords = feature['geometry']['coordinates']
                props = feature['properties']
                
                hover_str = (
                    f"<b>Plate 1:</b> {props.get('plate1', 'N/A')}<br>"
                    f"<b>Plate 2:</b> {props.get('plate2', 'N/A')}<br>"
                    f"<b>Boundary Type:</b> {props.get('type', 'N/A')}<br>"
                    f"<b>Feature Name:</b> {props.get('feature', 'N/A')}<br>"
                    f"<b>Length:</b> {props.get('length', 'N/A')}"
                )
                
                # Flatten the coordinates and insert Nones to break lines
                if geom_type == 'LineString':
                    for lon, lat in coords:
                        p_lons.append(lon); p_lats.append(lat); p_texts.append(hover_str)
                    p_lons.append(None); p_lats.append(None); p_texts.append(None)
                elif geom_type == 'MultiLineString':
                    for line in coords:
                        for lon, lat in line:
                            p_lons.append(lon); p_lats.append(lat); p_texts.append(hover_str)
                        p_lons.append(None); p_lats.append(None); p_texts.append(None)
            
            fig.add_trace(go.Scattermapbox(
                lat=p_lats,
                lon=p_lons,
                mode='lines',
                line=dict(width=1, color="#5D4B3B"),
                opacity=0.5,
                text=p_texts,
                hoverinfo='text',
                name='Tectonic Plates'
            ))
        except Exception as e:
            st.error(f"Error loading plates.geojson: {e}")

    # --- Configure Map Layout ---
    fig.update_layout(
        autosize=True,
        mapbox=dict(
            style='carto-positron',
            center=dict(lat=0, lon=120),
            zoom=1.5
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        height=650,
        showlegend=False
    )

    # Render Plotly Chart in Streamlit
    #st.plotly_chart(fig, use_container_width=True)
    st.plotly_chart(fig, width='stretch', config={'scrollZoom': True})
    
    st.markdown("---")
    
    st.subheader("Data Details")
    
    # 1. Create a copy of the specific columns you want to display
    df_display = df_filtered[['Magnitude', 'Place', 'Depth (km)', 'Date', 'Tsunami', 'MMI', 'Dead', 'Injured', 'Impact']].copy()\
        #.rename(columns={'tsunami':'Tsunami', 'mmi':'MMI', 'mmi_level':'Level', 'dead':'Dead', 'injured':'Injured', 'impact':'Impact'})
    
    st.dataframe(
        df_display, 
        width='stretch', 
        hide_index=True
    )
    
else:
    st.info("No earthquake records match the selected sidebar filters. Try expanding your search bounds.")