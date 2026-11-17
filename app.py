import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import unicodedata
import re
import os
import requests

# Configuración inicial de la página
st.set_page_config(
    page_title="Dashboard Mortalidad Vial ZMG 2026",
    page_icon="🚨",
    layout="wide"
)

col_titulo, col_logo = st.columns([3.8, 1.2])
with col_titulo:
    st.title("🚨 Dashboard de Mortalidad por Siniestros Viales en Motocicletas en la ZMG (2026). CEPAJ")
    st.markdown("Análisis geoespacial, estadístico y de corredores estratégicos de siniestros viales en el Área Metropolitana de Guadalajara. BJ")

with col_logo:
    st.markdown("<div style='padding-top: 12px;'></div>", unsafe_allow_html=True)
    logo_candidatos = [
        "Logo cepaj imterior blanco.png",
        "logo_cepaj.png",
        "Logo_CEPAJ.png",
        "logo cepaj.png"
    ]
    logo_path = next((p for p in logo_candidatos if os.path.exists(p)), None)
    if not logo_path:
        imgs = [f for f in os.listdir('.') if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) and 'cepaj' in f.lower()]
        if imgs:
            logo_path = imgs[0]
    if logo_path:
        st.image(logo_path, use_container_width=True)

# Función auxiliar para normalizar texto (quitar acentos y pasar a minúsculas)
def normalizar_texto(s):
    if pd.isna(s):
        return ""
    s = str(s).lower().strip()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return s

# Descarga y caché de los polígonos oficiales de límites municipales de la ZMG (OSM Overpass / Nominatim)
@st.cache_data(ttl=604800, show_spinner=False)
def obtener_limites_municipales_zmg():
    municipios_obj = [
        ("Guadalajara", ["Guadalajara, Jalisco, Mexico"]),
        ("Zapopan", ["Zapopan, Jalisco, Mexico"]),
        ("San Pedro Tlaquepaque", [
            "Municipio de San Pedro Tlaquepaque, Jalisco, Mexico",
            "San Pedro Tlaquepaque, Jalisco, Mexico",
            "Tlaquepaque, Jalisco, Mexico"
        ]),
        ("Tonalá", ["Tonalá, Jalisco, Mexico"]),
        ("Tlajomulco de Zúñiga", ["Tlajomulco de Zúñiga, Jalisco, Mexico"]),
        ("El Salto", ["El Salto, Jalisco, Mexico"]),
        ("Ixtlahuacán de los Membrillos", ["Ixtlahuacán de los Membrillos, Jalisco, Mexico"]),
        ("Juanacatlán", ["Juanacatlán, Jalisco, Mexico"]),
        ("Zapotlanejo", ["Zapotlanejo, Jalisco, Mexico"])
    ]
    headers = {"User-Agent": "DashboardMortalidadZMG/2026 (analisis-vial-zmg)"}
    features_zmg = []

    for nombre_etiqueta, queries in municipios_obj:
        encontrado = False
        for query in queries:
            if encontrado:
                break
            try:
                resp = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": query,
                        "format": "geojson",
                        "polygon_geojson": 1,
                        "limit": 5,
                        "countrycodes": "mx"
                    },
                    headers=headers,
                    timeout=12
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for feat in data.get("features", []):
                        geom = feat.get("geometry", {})
                        props = feat.get("properties", {})
                        if geom.get("type") in ("Polygon", "MultiPolygon") and props.get("category") == "boundary":
                            feat["properties"]["MUNICIPIO_ETIQUETA"] = nombre_etiqueta
                            features_zmg.append(feat)
                            encontrado = True
                            break
                    if not encontrado:
                        for feat in data.get("features", []):
                            geom = feat.get("geometry", {})
                            if geom.get("type") in ("Polygon", "MultiPolygon"):
                                feat["properties"]["MUNICIPIO_ETIQUETA"] = nombre_etiqueta
                                features_zmg.append(feat)
                                encontrado = True
                                break
            except Exception:
                continue

    if features_zmg:
        return {"type": "FeatureCollection", "features": features_zmg}
    return None

# Función mejorada para extraer coordenadas en DMS (Grados, Minutos, Segundos) o Grados Decimales (20.6597, -103.3496)
def extraer_coordenadas(row):
    n_str = str(row['N']).strip() if pd.notnull(row['N']) and str(row['N']).strip().lower() != 'nan' else ''
    w_str = str(row['W']).strip() if pd.notnull(row['W']) and str(row['W']).strip().lower() != 'nan' else ''
    combined = (n_str + " " + w_str).replace(',', '.')
    
    lat, lon = None, None
    
    # 1. Intentar formato Grados, Minutos, Segundos (DMS): ej. 20°40'32.5"N  103°20'15.1"W
    lat_dms = re.search(r"(\d{1,2})\s*[°º]\s*(\d{1,2})\s*['′’]\s*([\d\.]+)\s*[\"″”]?\s*N?", combined, re.IGNORECASE)
    lon_dms = re.search(r"(10[234])\s*[°º]\s*(\d{1,2})\s*['′’]\s*([\d\.]+)\s*[\"″”]?\s*W?", combined, re.IGNORECASE)
    
    if lat_dms:
        lat = float(lat_dms.group(1)) + float(lat_dms.group(2))/60.0 + float(lat_dms.group(3))/3600.0
    if lon_dms:
        lon = -(float(lon_dms.group(1)) + float(lon_dms.group(2))/60.0 + float(lon_dms.group(3))/3600.0)
    
    # 2. Si no viene en DMS, intentar Grados Decimales directos (ej. 20.6754 y -103.3452 o 103.3452)
    if lat is None:
        lat_dec = re.search(r"\b(20\.\d+|21\.\d+)\b", combined)
        if lat_dec:
            lat = float(lat_dec.group(1))
    if lon is None:
        lon_dec = re.search(r"(-?10[234]\.\d+)", combined)
        if lon_dec:
            val = float(lon_dec.group(1))
            lon = val if val < 0 else -val
            
    # Validar que las coordenadas caigan dentro del rango geográfico de Jalisco / ZMG
    if lat is not None and not (19.5 <= lat <= 22.0):
        lat = None
    if lon is not None and not (-105.0 <= lon <= -102.0):
        lon = None
        
    return pd.Series({'latitud': lat, 'longitud': lon})

# Función para categorizar rangos de edad según el requerimiento exacto
def categorizar_edad(edad):
    if pd.isna(edad) or str(edad).strip().lower() in ['sin datos', 'sin definir', 'nan', '', 'none', 'null']:
        return 'Sin definir'
    try:
        e = float(edad)
        if e < 1:
            return '<1 año'
        elif 1 <= e <= 4:
            return '1 a 4 años'
        elif 5 <= e <= 9:
            return '5 a 9 años'
        elif 10 <= e <= 14:
            return '10 a 14'
        elif 15 <= e <= 19:
            return '15 a 19'
        elif 20 <= e <= 29:
            return '20 a 29'
        elif 30 <= e <= 39:
            return '30 a 39'
        elif 40 <= e <= 49:
            return '40 a 49'
        elif 50 <= e <= 59:
            return '50 a 59'
        elif e >= 60:
            return '>60'
    except:
        return 'Sin definir'
    return 'Sin definir'

# Estandarización de cruceros recurrentes con distinta ortografía
def normalizar_cruce(dom):
    if pd.isna(dom) or str(dom).strip().lower() in ['nan', 'none', '']:
        return 'Sin definir'
    texto = re.sub(r'\s+', ' ', str(dom).strip()).replace('/', ' / ')
    texto = re.sub(r'\s+', ' ', texto).strip()
    norm = normalizar_texto(texto)
    
    if ('periferico' in norm or 'pefiferico' in norm) and 'colon' in norm:
        return 'Periférico Sur / Av. Colón'
    if 'periferico nuevo' in norm and 'zapotlanejo' in norm:
        return 'Periférico Nuevo / Carretera a Zapotlanejo'
    if 'periferico nuevo' in norm and 'el salto' in norm:
        return 'Periférico Nuevo / Carretera a El Salto'
    if 'juan pablo ii' in norm and 'quemada' in norm:
        return 'Av. Juan Pablo II / Hacienda de la Quemada'
    if 'colimilla' in norm:
        return 'Camino a Colimilla (La Barranca)'
    return texto

# Clasificación de corredores estratégicos, arterias principales y vías de ingreso/salida
def clasificar_corredor(dom):
    d = normalizar_texto(dom)
    if 'periferico' in d or 'pefiferico' in d:
        if 'nuevo' in d or 'oriente' in d:
            return 'Anillo Periférico (Nuevo Periférico / Oriente)', 'Anillo Metropolitano', 'Mixto (Tráfico Pesado + Alta Velocidad)'
        elif 'norte' in d:
            return 'Anillo Periférico (Periférico Norte)', 'Anillo Metropolitano', 'Mixto (Congestión + Flujo Rápido)'
        else:
            return 'Anillo Periférico (Periférico Sur / Poniente)', 'Anillo Metropolitano', 'Hora Pico (Filtrado / Transporte Pesado)'
    if 'chapala' in d:
        return 'Carretera a Chapala', 'Vía de Ingreso / Salida', 'Mixto (Cuellos de Botella + Alta Velocidad)'
    if 'adolf horn' in d or 'camino real a colima' in d or 'michel gonzalez' in d or 'circuito metropolitano' in d:
        return 'Corredor Sur (Adolf Horn / Camino Real / Michel Glez. / VFG)', 'Vía de Ingreso / Salida', 'Hora Pico (Congestión Severa / Filtrado)'
    if 'vallarta' in d or 'nogales' in d or 'venta' in d:
        return 'Eje Poniente (Av. Vallarta – Ctra. a Nogales)', 'Vía de Ingreso / Salida', 'Hora Pico (Congestión / Cruces Semaforizados)'
    if 'zapotlanejo' in d or 'los altos' in d:
        return 'Autopista / Libre a Zapotlanejo – Los Altos', 'Vía de Ingreso / Salida', 'Flujo Rápido / Transporte de Carga'
    if 'juan gil preciado' in d or 'tesistan' in d or 'aviacion' in d or 'base aerea' in d:
        return 'Corredor Norponiente (Juan Gil Preciado / Tesistán / Aviación)', 'Vía de Ingreso / Salida', 'Hora Pico (Congestión / Transporte Pesado)'
    if 'lopez mateos' in d or 'americas' in d:
        return 'Corredor López Mateos – Av. Américas', 'Arteria Principal / Acceso', 'Hora Valle / Nocturno (Túneles y Alta Velocidad)'
    if 'colon' in d and 'glorieta' not in d:
        return 'Av. Cristóbal Colón', 'Arteria Principal Intraurbana', 'Hora Pico (Cruces Urbanos)'
    if 'el salto' in d or 'san martin el verde' in d:
        return 'Carretera a El Salto / Corredor Industrial', 'Vía de Ingreso / Salida', 'Mixto (Zona Industrial / Carga)'
    if 'independencia' in d or 'belisario' in d or 'juan pablo ii' in d:
        return 'Eje Norte-Oriente (Calz. Independencia / Belisario / Juan Pablo II)', 'Arteria Principal Intraurbana', 'Mixto (Carril Confinado / Cruces)'
    if 'tonaltecas' in d or 'revolucion' in d:
        return 'Eje Oriente (Av. Tonaltecas / Calz. Revolución)', 'Arteria Principal Intraurbana', 'Hora Pico (Cruces Urbanos)'
    if 'patria' in d or 'guadalupe' in d or 'mariano otero' in d or '8 de julio' in d:
        return 'Arterias Troncales (Patria / Guadalupe / M. Otero / 8 de Julio)', 'Arteria Principal Intraurbana', 'Hora Pico (Cruces Urbanos)'
    if 'saltillo' in d:
        return 'Carretera a Saltillo', 'Vía de Ingreso / Salida', 'Flujo Rápido / Carretero'
    if 'colima' in d:
        return 'Autopista / Carretera a Colima', 'Vía de Ingreso / Salida', 'Flujo Rápido / Carretero'
    return 'Otras Vialidades / Red Secundaria', 'Red Secundaria / Local', 'Cruces Locales / Falta de Visibilidad'

@st.cache_data
def cargar_datos(filepath):
    df_raw = pd.read_excel(filepath, sheet_name='2026')
    
    # Conservar TODAS las filas que contengan al menos un dato real del siniestro (evitando filas vacías al final)
    cols_clave = ['Fecha ', 'Domicilio ', 'Municipio ', 'Edad', 'Sexo ', 'Circunstancia que ocurrió el siniestro', 'N']
    cols_existentes = [c for c in cols_clave if c in df_raw.columns]
    df = df_raw[df_raw[cols_existentes].notna().any(axis=1)].copy()
    
    # Estandarización segura de Municipio (incluyendo registros sin municipio como 'Sin definir')
    df['Municipio'] = df['Municipio '].fillna('Sin definir').astype(str).str.strip().str.title()
    df['Municipio'] = df['Municipio'].replace({
        'El Salto ': 'El Salto',
        'Tonala': 'Tonalá',
        'Tlajomulco De Zúñiga': 'Tlajomulco de Zúñiga',
        'Nan': 'Sin definir',
        'None': 'Sin definir',
        '': 'Sin definir'
    })
    
    # Fecha legible
    df['Fecha_Texto'] = pd.to_datetime(df['Fecha '], errors='coerce').dt.strftime('%Y-%m-%d')
    df['Fecha_Texto'] = df['Fecha_Texto'].fillna(df['Fecha '].fillna('Sin fecha').astype(str))
    
    # Crucero normalizado y domicilio original
    df['Domicilio_Original'] = df['Domicilio '].fillna('Sin definir').astype(str).str.strip()
    df['Crucero'] = df['Domicilio '].apply(normalizar_cruce)
    
    # Mes estandarizado
    df['Mes_Nombre'] = df['Mes'].fillna('SIN DEFINIR').astype(str).str.strip().str.upper()
    df['Mes_Nombre'] = df['Mes_Nombre'].replace({'NAN': 'SIN DEFINIR', 'NONE': 'SIN DEFINIR', '': 'SIN DEFINIR'})
    
    # Sexo
    df['Sexo_Clean'] = df['Sexo '].fillna('Sin definir').astype(str).str.strip().map({
        'Masc': 'Masculino', 'Fem': 'Femenino'
    }).fillna('Sin definir')
    
    # Rol (Piloto o Acompañante)
    df['Rol'] = df['Piloto o acompañante '].fillna('Sin definir').astype(str).str.strip().replace({
        'Piloto ': 'Piloto',
        'Acopañante': 'Acompañante',
        'Acompañante ': 'Acompañante',
        'Nan': 'Sin definir',
        'None': 'Sin definir',
        '': 'Sin definir'
    })
    
    # Circunstancia
    df['Circunstancia'] = df['Circunstancia que ocurrió el siniestro'].fillna('Sin definir').astype(str).str.strip().str.capitalize()
    df['Circunstancia'] = df['Circunstancia'].replace({
        'Choque ': 'Choque',
        ' Choque': 'Choque',
        'Prensado por camion y camionata': 'Prensado por camión/camioneta',
        'Nan': 'Sin definir',
        'None': 'Sin definir',
        '': 'Sin definir'
    })
    
    # Categorizar Edad
    df['Rango_Edad'] = df['Edad'].apply(categorizar_edad)
    df['Edad_Display'] = df['Edad'].apply(lambda x: str(int(float(x))) if pd.notna(x) and str(x).replace('.','',1).isdigit() else 'Sin definir')
    
    # Clasificar Corredor y Jerarquía Vial
    corredores_info = df['Domicilio '].apply(clasificar_corredor)
    df['Corredor'] = [c[0] for c in corredores_info]
    df['Jerarquia_Vial'] = [c[1] for c in corredores_info]
    df['Regimen_Trafico'] = [c[2] for c in corredores_info]
    
    # Extraer coordenadas numéricas
    coords = df.apply(extraer_coordenadas, axis=1)
    df['latitud'] = pd.to_numeric(coords['latitud'], errors='coerce')
    df['longitud'] = pd.to_numeric(coords['longitud'], errors='coerce')
    
    # Enlace
    df['Enlace'] = df['LINK '].fillna('').astype(str).str.strip()
    
    return df

EXCEL_FILE = "Mortalidad de siniestros viales 2026Ca_4.xlsx"

if not os.path.exists(EXCEL_FILE):
    archivos = [f for f in os.listdir('.') if f.endswith('.xlsx')]
    if archivos:
        EXCEL_FILE = archivos[0]

try:
    df = cargar_datos(EXCEL_FILE)

    # --- FILTROS EN BARRA LATERAL ---
    st.sidebar.header("🔍 Filtros Dinámicos")
    municipios_lista = sorted([str(m) for m in df['Municipio'].unique() if pd.notna(m)])
    municipios = ['Todos'] + municipios_lista
    mun_sel = st.sidebar.selectbox("Selecciona Municipio:", municipios)

    jerarquias_lista = sorted([str(j) for j in df['Jerarquia_Vial'].unique() if pd.notna(j)])
    jerarquias = ['Todas'] + jerarquias_lista
    jer_sel = st.sidebar.selectbox("Tipo de Corredor / Jerarquía Vial:", jerarquias)

    circ_lista = sorted([str(c) for c in df['Circunstancia'].unique() if pd.notna(c)])
    circ_sel = st.sidebar.selectbox("Circunstancia del Siniestro:", ['Todas'] + circ_lista)

    st.sidebar.markdown("---")
    st.sidebar.subheader("🗺️ Opciones del Mapa")
    estilo_mapa = st.sidebar.selectbox(
        "Mapa Base / Cartografía:",
        [
            "Google Maps (Calles y Colonias)",
            "Google Híbrido (Satélite + Calles)",
            "Esri Satélite (Vista Aérea HD)",
            "OpenStreetMap (Detallado)",
            "CartoDB Positron (Claro)"
        ]
    )
    mostrar_limites = st.sidebar.checkbox("Mostrar división política municipal", value=True)

    df_fil = df.copy()
    if mun_sel != 'Todos':
        df_fil = df_fil[df_fil['Municipio'] == mun_sel]
    if jer_sel != 'Todas':
        df_fil = df_fil[df_fil['Jerarquia_Vial'] == jer_sel]
    if circ_sel != 'Todas':
        df_fil = df_fil[df_fil['Circunstancia'] == circ_sel]

    total_registros = len(df_fil)
    con_coords = df_fil.dropna(subset=['latitud', 'longitud'])

    st.sidebar.markdown("---")
    st.sidebar.info(
        f"📌 **Total registros activos:** {total_registros}\n\n"
        f"🗺️ **Georreferenciados en mapa:** {len(con_coords)}\n\n"
        f"⚠️ **Sin coordenadas GPS:** {total_registros - len(con_coords)}"
    )

    # KPIs
    st.markdown("### 📊 Indicadores Clave de Mortalidad")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Fallecidos / Siniestros", total_registros)
    c2.metric("Municipio con Más Casos", df_fil['Municipio'].value_counts().index[0] if total_registros > 0 else "N/A")
    c3.metric("% Pilotos Fallecidos", f"{(len(df_fil[df_fil['Rol']=='Piloto'])/total_registros*100):.1f}%" if total_registros > 0 else "0%")
    c4.metric("Causa Principal", df_fil['Circunstancia'].value_counts().index[0] if total_registros > 0 else "N/A")

    st.markdown("---")

    # --- 1. MAPA Y TABLA DETALLADA DE CRUCES ---
    st.subheader("📍 1. Mapa de Puntos Críticos y Tabla Detallada de Cruces")
    col_map, col_tabla_cruces = st.columns([1.6, 1.4])

    # Agrupar cruceros con municipio y corredor, ordenados estrictamente de mayor a menor
    top_cruces = df_fil.groupby(['Crucero', 'Municipio', 'Corredor']).size().reset_index(name='Fallecidos')
    top_cruces = top_cruces.sort_values(by=['Fallecidos', 'Crucero'], ascending=[False, True]).reset_index(drop=True)
    top_cruces.index = top_cruces.index + 1
    top_cruces.index.name = '#'

    with col_map:
        st.markdown(f"**Geolocalización de Siniestros Mortales ({len(con_coords)} puntos con GPS)**")
        center_lat = float(con_coords['latitud'].mean()) if not con_coords.empty else 20.6597
        center_lon = float(con_coords['longitud'].mean()) if not con_coords.empty else -103.3496
        
        mapa = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles=None)

        # Selección de mapa base de alta precisión (Google Maps / Satélite / OSM / CartoDB)
        if estilo_mapa == "Google Maps (Calles y Colonias)":
            folium.TileLayer(
                tiles="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
                attr="Google Maps",
                name="Google Maps",
                max_zoom=21
            ).add_to(mapa)
        elif estilo_mapa == "Google Híbrido (Satélite + Calles)":
            folium.TileLayer(
                tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                attr="Google Hybrid",
                name="Google Híbrido",
                max_zoom=21
            ).add_to(mapa)
        elif estilo_mapa == "Esri Satélite (Vista Aérea HD)":
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri World Imagery",
                name="Esri Satélite",
                max_zoom=19
            ).add_to(mapa)
        elif estilo_mapa == "CartoDB Positron (Claro)":
            folium.TileLayer("CartoDB positron", name="CartoDB Positron", max_zoom=20).add_to(mapa)
        else:
            folium.TileLayer("OpenStreetMap", name="OpenStreetMap", max_zoom=19).add_to(mapa)

        # Capa de límites políticos municipales de la ZMG
        geojson_zmg = obtener_limites_municipales_zmg() if mostrar_limites else None
        if mostrar_limites and not geojson_zmg:
            st.warning("No se pudieron descargar los polígonos municipales en este momento. Intenta recargar la página.")

        if geojson_zmg:
            paleta_muns = {
                "guadalajara": "#1d4ed8",
                "zapopan": "#6d28d9",
                "san pedro tlaquepaque": "#047857",
                "tlaquepaque": "#047857",
                "tonala": "#b45309",
                "tlajomulco de zuniga": "#b91c1c",
                "el salto": "#0e7490",
                "ixtlahuacan de los membrillos": "#4338ca",
                "juanacatlan": "#4d7c0f",
                "zapotlanejo": "#7e22ce"
            }

            def estilo_municipio(feature):
                nom = normalizar_texto(feature["properties"].get("MUNICIPIO_ETIQUETA", ""))
                color_borde = "#1e3a8a"
                for k, v in paleta_muns.items():
                    if k in nom:
                        color_borde = v
                        break
                es_seleccionado = (mun_sel != 'Todos' and (normalizar_texto(mun_sel) in nom or ('tlaquepaque' in normalizar_texto(mun_sel) and 'tlaquepaque' in nom)))
                return {
                    "fillColor": color_borde,
                    "color": color_borde,
                    "weight": 4.5 if es_seleccionado else 3.0,
                    "dashArray": None if es_seleccionado else "8, 5",
                    "fillOpacity": 0.14 if es_seleccionado else 0.03
                }

            folium.GeoJson(
                geojson_zmg,
                name="División Política Municipal (ZMG)",
                style_function=estilo_municipio,
                highlight_function=lambda x: {"weight": 5, "fillOpacity": 0.20},
                tooltip=folium.GeoJsonTooltip(
                    fields=["MUNICIPIO_ETIQUETA"],
                    aliases=["Municipio:"],
                    style="font-family: Arial, sans-serif; font-size: 13px; font-weight: bold;"
                )
            ).add_to(mapa)

        # Capa de puntos críticos de siniestros con enlace directo a Google Maps Street View / Ubicación exacta
        capa_puntos = folium.FeatureGroup(name="Puntos de Siniestros Mortales")
        for (lat_val, lon_val), grupo in con_coords.groupby(['latitud', 'longitud']):
            cant = len(grupo)
            radio = 6.5 + (cant - 1) * 3.5
            color_punto = "#b30000" if cant > 1 else "#e11d48"
            
            detalles_html = ""
            for _, r in grupo.iterrows():
                detalles_html += f"<li style='margin-bottom:4px;'><b>{r['Fecha_Texto']}</b>: {r['Circunstancia']} | {r['Rol']} ({r['Sexo_Clean']}, {r['Edad_Display']} años)</li>"
            
            gmaps_url = f"https://www.google.com/maps/search/?api=1&query={lat_val:.6f},{lon_val:.6f}"
            
            popup_txt = f"""
            <div style="font-family: Arial, sans-serif; width: 280px;">
                <b>Cruce:</b> {grupo.iloc[0]['Crucero']}<br>
                <b>Municipio:</b> {grupo.iloc[0]['Municipio']}<br>
                <b>Corredor:</b> {grupo.iloc[0]['Corredor']}<br>
                <b>Coordenadas:</b> {lat_val:.6f}, {lon_val:.6f}<br>
                <b>Total Fallecidos en este punto:</b> {cant}<br>
                <a href="{gmaps_url}" target="_blank" style="display:inline-block; margin-top:5px; padding:4px 8px; background:#1a73e8; color:white; text-decoration:none; border-radius:4px; font-size:12px;">
                    📍 Abrir punto exacto en Google Maps
                </a>
                <hr style="margin:6px 0;">
                <ul style="padding-left:16px; margin:0;">{detalles_html}</ul>
            </div>
            """
            folium.CircleMarker(
                location=[float(lat_val), float(lon_val)],
                radius=radio,
                popup=folium.Popup(popup_txt, max_width=310),
                tooltip=f"{grupo.iloc[0]['Crucero']} ({grupo.iloc[0]['Municipio']}) - {cant} fallecido(s)",
                color="#ffffff",
                fill=True,
                fill_color=color_punto,
                fill_opacity=0.9,
                weight=1.5
            ).add_to(capa_puntos)

        capa_puntos.add_to(mapa)

        st_folium(mapa, width="100%", height=460, returned_objects=[])

    with col_tabla_cruces:
        st.markdown(f"**Ranking Completo de Intersecciones ({len(top_cruces)} cruces / {total_registros} siniestros)**")
        st.dataframe(top_cruces, use_container_width=True, height=460)

    st.markdown("---")

    # --- 2. MUNICIPIOS ---
    st.subheader("🏙️ 2. Cantidad de Siniestros por Municipio")
    col_mun_tab, col_mun_fig = st.columns([1.1, 1.9])

    df_mun = df_fil['Municipio'].value_counts().reset_index()
    df_mun.columns = ['Municipio', 'Fallecidos']
    df_mun['Porcentaje (%)'] = ((df_mun['Fallecidos'] / total_registros) * 100).round(1) if total_registros > 0 else 0

    with col_mun_tab:
        st.markdown(f"**Tabla por Municipio (Total: {df_mun['Fallecidos'].sum()})**")
        st.dataframe(df_mun, hide_index=True, use_container_width=True, height=360)

    with col_mun_fig:
        st.markdown("**Comparativa Visual por Municipio**")
        fig_mun = px.bar(
            df_mun, x='Municipio', y='Fallecidos', text='Fallecidos',
            color='Fallecidos', color_continuous_scale='Reds'
        )
        fig_mun.update_traces(textposition='outside')
        fig_mun.update_layout(xaxis_title="Municipio", yaxis_title="Cantidad de Fallecidos", height=360)
        st.plotly_chart(fig_mun, use_container_width=True)

    st.markdown("---")

    # --- 3. RANGO DE EDAD Y DISTRIBUCIÓN POR SEXO ---
    st.subheader("👥 3. Perfil Demográfico: Rango de Edad y Sexo")
    col_edad, col_sexo = st.columns(2)

    with col_edad:
        orden_rangos = ['<1 año', '1 a 4 años', '5 a 9 años', '10 a 14', '15 a 19', '20 a 29', '30 a 39', '40 a 49', '50 a 59', '>60', 'Sin definir']
        df_edad = df_fil['Rango_Edad'].value_counts().reindex(orden_rangos, fill_value=0).reset_index()
        df_edad.columns = ['Rango de Edad', 'Fallecidos']
        df_edad['Porcentaje (%)'] = ((df_edad['Fallecidos'] / total_registros) * 100).round(1) if total_registros > 0 else 0
        
        st.markdown(f"**Fallecidos por Rango de Edad (Total: {df_edad['Fallecidos'].sum()})**")
        st.dataframe(df_edad, hide_index=True, use_container_width=True, height=425)
        
        fig_edad = px.bar(
            df_edad, x='Rango de Edad', y='Fallecidos', text='Fallecidos',
            color='Fallecidos', color_continuous_scale='Oranges', title="Distribución por Rango de Edad (Todos los Grupos)"
        )
        fig_edad.update_traces(textposition='outside')
        st.plotly_chart(fig_edad, use_container_width=True)

    with col_sexo:
        df_sexo = df_fil['Sexo_Clean'].value_counts().reset_index()
        df_sexo.columns = ['Sexo', 'Fallecidos']
        df_sexo['Porcentaje (%)'] = ((df_sexo['Fallecidos'] / total_registros) * 100).round(1) if total_registros > 0 else 0
        
        st.markdown(f"**Distribución por Sexo (Total: {df_sexo['Fallecidos'].sum()})**")
        st.dataframe(df_sexo, hide_index=True, use_container_width=True)
        
        fig_sexo = px.pie(
            df_sexo, names='Sexo', values='Fallecidos',
            title="Proporción por Sexo", color_discrete_sequence=['#1f77b4', '#e377c2', '#7f7f7f']
        )
        fig_sexo.update_traces(textinfo='percent+value+label')
        st.plotly_chart(fig_sexo, use_container_width=True)

    st.markdown("---")

    # --- 4. EVOLUCIÓN MENSUAL Y ROL DE LA VÍCTIMA ---
    st.subheader("📅 4. Evolución Mensual y Rol de las Víctimas (Piloto vs Pasajero/Acompañante)")
    col_mes, col_rol = st.columns(2)

    with col_mes:
        orden_meses = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC']
        conteo_mes = df_fil['Mes_Nombre'].value_counts()
        df_mes = conteo_mes.reindex(orden_meses, fill_value=0).reset_index()
        df_mes.columns = ['Mes', 'Fallecidos']
        sin_mes = int(conteo_mes.get('SIN DEFINIR', 0))
        if sin_mes > 0:
            df_mes = pd.concat([df_mes, pd.DataFrame([{'Mes': 'SIN DEFINIR', 'Fallecidos': sin_mes}])], ignore_index=True)
        df_mes['Porcentaje (%)'] = ((df_mes['Fallecidos'] / total_registros) * 100).round(1) if total_registros > 0 else 0
        
        st.markdown(f"**Víctimas / Siniestros por Mes (Total: {df_mes['Fallecidos'].sum()})**")
        st.dataframe(df_mes, hide_index=True, use_container_width=True, height=460)
        
        fig_mes = px.line(
            df_mes[df_mes['Mes'].isin(orden_meses)], x='Mes', y='Fallecidos', markers=True, text='Fallecidos',
            title="Tendencia Mensual de Mortalidad 2026 (Enero - Diciembre)", line_shape='linear'
        )
        fig_mes.update_traces(line_color='#d9534f', line_width=3, textposition='top center')
        st.plotly_chart(fig_mes, use_container_width=True)

    with col_rol:
        df_rol = df_fil['Rol'].value_counts().reset_index()
        df_rol.columns = ['Rol del Usuario', 'Fallecidos']
        df_rol['Porcentaje (%)'] = ((df_rol['Fallecidos'] / total_registros) * 100).round(1) if total_registros > 0 else 0
        
        st.markdown(f"**Pilotos vs Pasajeros / Acompañantes (Total: {df_rol['Fallecidos'].sum()})**")
        st.dataframe(df_rol, hide_index=True, use_container_width=True)
        
        fig_rol = px.bar(
            df_rol, x='Rol del Usuario', y='Fallecidos', text='Fallecidos',
            color='Rol del Usuario', color_discrete_sequence=['#d9534f', '#f0ad4e', '#5bc0de'],
            title="Distribución por Rol de la Víctima"
        )
        fig_rol.update_traces(textposition='outside')
        st.plotly_chart(fig_rol, use_container_width=True)

    st.markdown("---")

    # --- 5. CIRCUNSTANCIA DEL SINIESTRO ---
    st.subheader("⚠️ 5. Circunstancia por la que Ocurrió el Siniestro")
    col_circ_tab, col_circ_fig = st.columns([1.1, 1.9])

    df_circ = df_fil['Circunstancia'].value_counts().reset_index()
    df_circ.columns = ['Circunstancia de Ocurrencia', 'Fallecidos']
    df_circ['Porcentaje (%)'] = ((df_circ['Fallecidos'] / total_registros) * 100).round(1) if total_registros > 0 else 0

    with col_circ_tab:
        st.markdown(f"**Tabla por Circunstancia (Total: {df_circ['Fallecidos'].sum()})**")
        st.dataframe(df_circ, hide_index=True, use_container_width=True, height=340)

    with col_circ_fig:
        st.markdown("**Comparativa Visual por Circunstancia**")
        fig_circ = px.bar(
            df_circ.sort_values(by='Fallecidos', ascending=True),
            x='Fallecidos', y='Circunstancia de Ocurrencia', orientation='h', text='Fallecidos',
            color='Fallecidos', color_continuous_scale='OrRd'
        )
        fig_circ.update_traces(textposition='outside')
        fig_circ.update_layout(xaxis_title="Cantidad de Fallecidos", yaxis_title="", height=340)
        st.plotly_chart(fig_circ, use_container_width=True)

    st.markdown("---")

    # --- 6. CORREDORES ESTRATÉGICOS Y VÍAS DE INGRESO/SALIDA (DINÁMICA VIAL ZMG) ---
    st.subheader("🛣️ 6. Corredores Estratégicos, Arterias Principales y Vías de Ingreso/Salida")
    st.markdown("""
    Análisis de corredores críticos cruzando **jerarquía vial**, **puntos de ingreso/salida de la ZMG** y **regímenes de tráfico**:
    * **Hora Pico (Congestión Severa / Filtrado):** Cuellos de botella en accesos metropolitanos donde predominan choques por alcance y puntos ciegos de transporte pesado.
    * **Hora Valle / Nocturno (Flujo Libre / Alta Velocidad):** Tramos rápidos, curvas y túneles donde predomina la pérdida de control (derrape).
    """)

    df_corr = df_fil.groupby(['Corredor', 'Jerarquia_Vial', 'Regimen_Trafico']).agg(
        Fallecidos=('Crucero', 'count'),
        Choques=('Circunstancia', lambda x: int(sum('choque' in normalizar_texto(v) for v in x))),
        Derrapes=('Circunstancia', lambda x: int(sum('derrape' in normalizar_texto(v) for v in x))),
        Vehiculo_Pesado=('Circunstancia', lambda x: int(sum(any(k in normalizar_texto(v) for k in ['camion', 'trailer', 'pick up', 'auto', 'prensado']) for v in x)))
    ).reset_index().sort_values(by='Fallecidos', ascending=False)

    df_corr['% del Total'] = ((df_corr['Fallecidos'] / total_registros) * 100).round(1) if total_registros > 0 else 0

    col_corr_fig, col_jer_fig = st.columns([1.65, 1.35])

    with col_corr_fig:
        st.markdown("**Ranking de Corredores Metropolitanos y Accesos (Ordenado de Mayor a Menor)**")
        df_corr_principales = df_corr[df_corr['Corredor'] != 'Otras Vialidades / Red Secundaria'].sort_values(by='Fallecidos', ascending=True)
        if not df_corr_principales.empty:
            fig_corr = px.bar(
                df_corr_principales,
                x='Fallecidos',
                y='Corredor',
                color='Jerarquia_Vial',
                orientation='h',
                text='Fallecidos',
                color_discrete_sequence=px.colors.qualitative.Set1
            )
            fig_corr.update_traces(textposition='outside')
            fig_corr.update_yaxes(categoryorder='total ascending')
            fig_corr.update_layout(
                xaxis_title="Fallecidos",
                yaxis_title="",
                legend_title="Jerarquía Vial",
                height=480,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_corr, use_container_width=True)
        else:
            st.info("No hay registros en corredores principales para el filtro seleccionado.")

    with col_jer_fig:
        st.markdown(f"**Distribución por Jerarquía Vial (Total: {total_registros})**")
        df_jer = df_fil.groupby('Jerarquia_Vial').size().reset_index(name='Fallecidos').sort_values(by='Fallecidos', ascending=False)
        df_jer['%'] = ((df_jer['Fallecidos'] / total_registros) * 100).round(1) if total_registros > 0 else 0
        
        fig_jer = px.pie(
            df_jer, names='Jerarquia_Vial', values='Fallecidos',
            hole=0.4, color_discrete_sequence=px.colors.qualitative.Bold
        )
        fig_jer.update_traces(textinfo='percent+value')
        fig_jer.update_layout(height=480)
        st.plotly_chart(fig_jer, use_container_width=True)

    st.markdown(f"**Tabla Analítica Completa de Corredores (Total: {df_corr['Fallecidos'].sum()} fallecidos)**")
    st.dataframe(
        df_corr[['Corredor', 'Jerarquia_Vial', 'Fallecidos', '% del Total', 'Choques', 'Derrapes', 'Vehiculo_Pesado', 'Regimen_Trafico']],
        hide_index=True,
        use_container_width=True
    )

    st.markdown("---")

    # --- 7. PROPUESTA ADICIONAL: INTERVENCIÓN DE VEHÍCULOS PESADOS ---
    st.subheader("🚛 7. Análisis de Letalidad por Intervención de Vehículos Pesados / Carga")
    st.markdown("""
    Identificación de siniestros con intervención directa de transporte de carga, camiones o vehículos pesados (combinando la columna *Circunstancia* y el reporte de *LINK*).
    """)

    texto_combinado = df_fil['Circunstancia'].fillna('') + ' ' + df_fil['Enlace'].fillna('')
    es_pesado = texto_combinado.apply(
        lambda x: any(k in normalizar_texto(x) for k in ['camion', 'trailer', 'remolque', 'vehiculo pesado', 'vehiculo-pesado', 'carga', 'prensado'])
    )
    df_pesado = pd.DataFrame({
        'Tipo de Evento': ['Involucra Transporte Pesado / Camión / Tráiler', 'Otros Choques / Derrapes'],
        'Cantidad': [int(es_pesado.sum()), int((~es_pesado).sum())]
    })

    col_pes_tab, col_pes_fig = st.columns([1.1, 1.9])
    with col_pes_tab:
        df_pesado['Porcentaje (%)'] = ((df_pesado['Cantidad'] / total_registros) * 100).round(1) if total_registros > 0 else 0
        st.dataframe(df_pesado, hide_index=True, use_container_width=True)
    with col_pes_fig:
        fig_propuesta = px.pie(
            df_pesado, names='Tipo de Evento', values='Cantidad',
            title="Proporción de Siniestros Fatales con Intervención de Transporte Pesado",
            color_discrete_sequence=['#c9302c', '#31b0d5']
        )
        fig_propuesta.update_traces(textinfo='percent+value+label')
        st.plotly_chart(fig_propuesta, use_container_width=True)

    st.markdown("---")

    # --- 8. BASE DE DATOS COMPLETA AUDITABLE ---
    st.subheader(f"📋 8. Base Completa de Siniestros Registrados ({total_registros} registros)")
    st.markdown("Consulta individual de todos los registros incluidos en los análisis anteriores:")

    busqueda = st.text_input("🔎 Buscar por calle, colonia, municipio o circunstancia:", "")
    df_tabla_final = df_fil.copy()
    if busqueda.strip():
        q = normalizar_texto(busqueda)
        mask_q = (
            df_tabla_final['Domicilio_Original'].apply(lambda x: q in normalizar_texto(x)) |
            df_tabla_final['Municipio'].apply(lambda x: q in normalizar_texto(x)) |
            df_tabla_final['Corredor'].apply(lambda x: q in normalizar_texto(x)) |
            df_tabla_final['Circunstancia'].apply(lambda x: q in normalizar_texto(x))
        )
        df_tabla_final = df_tabla_final[mask_q]

    cols_mostrar = ['No.', 'Fecha_Texto', 'Mes_Nombre', 'Domicilio_Original', 'Municipio', 'Corredor', 'Edad_Display', 'Rango_Edad', 'Sexo_Clean', 'Rol', 'Circunstancia', 'Enlace']
    df_display = df_tabla_final[cols_mostrar].copy()
    df_display.columns = ['No.', 'Fecha', 'Mes', 'Domicilio / Cruce', 'Municipio', 'Corredor Vial', 'Edad', 'Rango de Edad', 'Sexo', 'Rol', 'Circunstancia', 'Link']

    st.dataframe(df_display, hide_index=True, use_container_width=True, height=450)

    csv_export = df_display.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="⬇️ Descargar Base Filtrada en CSV (Excel)",
        data=csv_export,
        file_name="siniestros_motos_zmg_2026_completo.csv",
        mime="text/csv"
    )

except Exception as e:
    st.error(f"Error procesando la base de datos: {e}")
