import gradio as gr
import pandas as pd
import folium
import plotly.express as px
import unicodedata
import re
import os
import tempfile

def normalizar_texto(s):
    if pd.isna(s):
        return ""
    s = str(s).lower().strip()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return s

def extraer_coordenadas(row):
    n_str = str(row['N']).strip() if pd.notnull(row['N']) and str(row['N']).strip().lower() != 'nan' else ''
    w_str = str(row['W']).strip() if pd.notnull(row['W']) and str(row['W']).strip().lower() != 'nan' else ''
    combined = n_str + " " + w_str
    
    lat_match = re.search(r"(\d+)°\s*(\d+)['′\s]*([\d\.]+)\"?\s*N?", combined)
    lon_match = re.search(r"(10[23])°\s*(\d+)['′\s]*([\d\.]+)\"?\s*W?", combined)
    
    lat, lon = None, None
    if lat_match:
        lat = float(lat_match.group(1)) + float(lat_match.group(2))/60.0 + float(lat_match.group(3))/3600.0
    if lon_match:
        lon = -(float(lon_match.group(1)) + float(lon_match.group(2))/60.0 + float(lon_match.group(3))/3600.0)
        
    return pd.Series({'latitud': lat, 'longitud': lon})

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

def cargar_datos():
    excel_file = "Mortalidad de siniestros viales 2026Ca_4.xlsx"
    if not os.path.exists(excel_file):
        archivos = [f for f in os.listdir('.') if f.endswith('.xlsx')]
        if archivos:
            excel_file = archivos[0]
            
    df_raw = pd.read_excel(excel_file, sheet_name='2026')
    cols_clave = ['Fecha ', 'Domicilio ', 'Municipio ', 'Edad', 'Sexo ', 'Circunstancia que ocurrió el siniestro', 'N']
    cols_existentes = [c for c in cols_clave if c in df_raw.columns]
    df = df_raw[df_raw[cols_existentes].notna().any(axis=1)].copy()
    
    df['Municipio'] = df['Municipio '].fillna('Sin definir').astype(str).str.strip().str.title().replace({
        'El Salto ': 'El Salto',
        'Tonala': 'Tonalá',
        'Tlajomulco De Zúñiga': 'Tlajomulco de Zúñiga',
        'Nan': 'Sin definir',
        'None': 'Sin definir',
        '': 'Sin definir'
    })
    
    df['Fecha_Texto'] = pd.to_datetime(df['Fecha '], errors='coerce').dt.strftime('%Y-%m-%d')
    df['Fecha_Texto'] = df['Fecha_Texto'].fillna(df['Fecha '].fillna('Sin fecha').astype(str))
    df['Domicilio_Original'] = df['Domicilio '].fillna('Sin definir').astype(str).str.strip()
    df['Crucero'] = df['Domicilio '].apply(normalizar_cruce)
    df['Mes_Nombre'] = df['Mes'].fillna('SIN DEFINIR').astype(str).str.strip().str.upper().replace({
        'NAN': 'SIN DEFINIR', 'NONE': 'SIN DEFINIR', '': 'SIN DEFINIR'
    })
    df['Sexo_Clean'] = df['Sexo '].fillna('Sin definir').astype(str).str.strip().map({
        'Masc': 'Masculino', 'Fem': 'Femenino'
    }).fillna('Sin definir')
    df['Rol'] = df['Piloto o acompañante '].fillna('Sin definir').astype(str).str.strip().replace({
        'Piloto ': 'Piloto',
        'Acopañante': 'Acompañante',
        'Acompañante ': 'Acompañante',
        'Nan': 'Sin definir',
        'None': 'Sin definir',
        '': 'Sin definir'
    })
    df['Circunstancia'] = df['Circunstancia que ocurrió el siniestro'].fillna('Sin definir').astype(str).str.strip().str.capitalize().replace({
        'Choque ': 'Choque',
        ' Choque': 'Choque',
        'Prensado por camion y camionata': 'Prensado por camión/camioneta',
        'Nan': 'Sin definir',
        'None': 'Sin definir',
        '': 'Sin definir'
    })
    df['Rango_Edad'] = df['Edad'].apply(categorizar_edad)
    df['Edad_Display'] = df['Edad'].apply(lambda x: str(int(float(x))) if pd.notna(x) and str(x).replace('.','',1).isdigit() else 'Sin definir')
    
    corredores_info = df['Domicilio '].apply(clasificar_corredor)
    df['Corredor'] = [c[0] for c in corredores_info]
    df['Jerarquia_Vial'] = [c[1] for c in corredores_info]
    df['Regimen_Trafico'] = [c[2] for c in corredores_info]
    
    coords = df.apply(extraer_coordenadas, axis=1)
    df['latitud'] = pd.to_numeric(coords['latitud'], errors='coerce')
    df['longitud'] = pd.to_numeric(coords['longitud'], errors='coerce')
    df['Enlace'] = df['LINK '].fillna('').astype(str).str.strip()
    
    return df

DF_GLOBAL = cargar_datos()

def actualizar_dashboard(mun_sel, jer_sel, circ_sel, busqueda):
    df_fil = DF_GLOBAL.copy()
    if mun_sel != 'Todos':
        df_fil = df_fil[df_fil['Municipio'] == mun_sel]
    if jer_sel != 'Todas':
        df_fil = df_fil[df_fil['Jerarquia_Vial'] == jer_sel]
    if circ_sel != 'Todas':
        df_fil = df_fil[df_fil['Circunstancia'] == circ_sel]

    total = len(df_fil)
    con_coords = df_fil.dropna(subset=['latitud', 'longitud'])

    mun_top = df_fil['Municipio'].value_counts().index[0] if total > 0 else "N/A"
    pct_pilotos = f"{(len(df_fil[df_fil['Rol']=='Piloto'])/total*100):.1f}%" if total > 0 else "0%"
    causa_top = df_fil['Circunstancia'].value_counts().index[0] if total > 0 else "N/A"

    kpis_html = f"""
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 10px 0;">
        <div style="background:#1e293b; color:white; padding:16px; border-radius:10px; border-left:5px solid #ef4444;">
            <div style="font-size:13px; color:#94a3b8;">Total Fallecidos / Siniestros</div>
            <div style="font-size:28px; font-weight:bold;">{total}</div>
            <div style="font-size:11px; color:#cbd5e1;">{len(con_coords)} con GPS | {total - len(con_coords)} sin GPS</div>
        </div>
        <div style="background:#1e293b; color:white; padding:16px; border-radius:10px; border-left:5px solid #f97316;">
            <div style="font-size:13px; color:#94a3b8;">Municipio con Más Casos</div>
            <div style="font-size:24px; font-weight:bold;">{mun_top}</div>
        </div>
        <div style="background:#1e293b; color:white; padding:16px; border-radius:10px; border-left:5px solid #eab308;">
            <div style="font-size:13px; color:#94a3b8;">% Pilotos Fallecidos</div>
            <div style="font-size:28px; font-weight:bold;">{pct_pilotos}</div>
        </div>
        <div style="background:#1e293b; color:white; padding:16px; border-radius:10px; border-left:5px solid #3b82f6;">
            <div style="font-size:13px; color:#94a3b8;">Causa Principal</div>
            <div style="font-size:24px; font-weight:bold;">{causa_top}</div>
        </div>
    </div>
    """

    center_lat = float(con_coords['latitud'].mean()) if not con_coords.empty else 20.6597
    center_lon = float(con_coords['longitud'].mean()) if not con_coords.empty else -103.3496
    mapa = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles="OpenStreetMap")

    for (lat_val, lon_val), grupo in con_coords.groupby(['latitud', 'longitud']):
        cant = len(grupo)
        radio = 6 + (cant - 1) * 3.5
        color_punto = "#b30000" if cant > 1 else "#d9534f"
        detalles_html = "".join(
            f"<li><b>{r['Fecha_Texto']}</b>: {r['Circunstancia']} | {r['Rol']} ({r['Sexo_Clean']}, {r['Edad_Display']} años)</li>"
            for _, r in grupo.iterrows()
        )
        popup_txt = f"""
        <div style="font-family: Arial, sans-serif; width: 260px;">
            <b>Cruce:</b> {grupo.iloc[0]['Crucero']}<br>
            <b>Municipio:</b> {grupo.iloc[0]['Municipio']}<br>
            <b>Corredor:</b> {grupo.iloc[0]['Corredor']}<br>
            <b>Total Fallecidos:</b> {cant}
            <hr style="margin:5px 0;"><ul style="padding-left:15px; margin:0;">{detalles_html}</ul>
        </div>
        """
        folium.CircleMarker(
            location=[float(lat_val), float(lon_val)],
            radius=radio,
            popup=folium.Popup(popup_txt, max_width=290),
            tooltip=f"{grupo.iloc[0]['Crucero']} ({grupo.iloc[0]['Municipio']}) - {cant}",
            color=color_punto, fill=True, fill_color=color_punto, fill_opacity=0.85, weight=2
        ).add_to(mapa)

    mapa_html = f'<div style="width:100%; height:460px; border-radius:8px; overflow:hidden;">{mapa._repr_html_()}</div>'

    top_cruces = df_fil.groupby(['Crucero', 'Municipio', 'Corredor']).size().reset_index(name='Fallecidos')
    top_cruces = top_cruces.sort_values(by=['Fallecidos', 'Crucero'], ascending=[False, True]).reset_index(drop=True)
    top_cruces.insert(0, '#', range(1, len(top_cruces) + 1))

    df_mun = df_fil['Municipio'].value_counts().reset_index()
    df_mun.columns = ['Municipio', 'Fallecidos']
    df_mun['Porcentaje (%)'] = ((df_mun['Fallecidos'] / total) * 100).round(1) if total > 0 else 0
    fig_mun = px.bar(df_mun, x='Municipio', y='Fallecidos', text='Fallecidos', color='Fallecidos', color_continuous_scale='Reds', title="Fallecidos por Municipio")
    fig_mun.update_traces(textposition='outside')

    orden_rangos = ['<1 año', '1 a 4 años', '5 a 9 años', '10 a 14', '15 a 19', '20 a 29', '30 a 39', '40 a 49', '50 a 59', '>60', 'Sin definir']
    df_edad = df_fil['Rango_Edad'].value_counts().reindex(orden_rangos, fill_value=0).reset_index()
    df_edad.columns = ['Rango de Edad', 'Fallecidos']
    df_edad['Porcentaje (%)'] = ((df_edad['Fallecidos'] / total) * 100).round(1) if total > 0 else 0
    fig_edad = px.bar(df_edad, x='Rango de Edad', y='Fallecidos', text='Fallecidos', color='Fallecidos', color_continuous_scale='Oranges', title="Distribución por Rango de Edad")
    fig_edad.update_traces(textposition='outside')

    df_sexo = df_fil['Sexo_Clean'].value_counts().reset_index()
    df_sexo.columns = ['Sexo', 'Fallecidos']
    df_sexo['Porcentaje (%)'] = ((df_sexo['Fallecidos'] / total) * 100).round(1) if total > 0 else 0
    fig_sexo = px.pie(df_sexo, names='Sexo', values='Fallecidos', title="Proporción por Sexo", color_discrete_sequence=['#1f77b4', '#e377c2', '#7f7f7f'])
    fig_sexo.update_traces(textinfo='percent+value+label')

    orden_meses = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC']
    conteo_mes = df_fil['Mes_Nombre'].value_counts()
    df_mes = conteo_mes.reindex(orden_meses, fill_value=0).reset_index()
    df_mes.columns = ['Mes', 'Fallecidos']
    df_mes['Porcentaje (%)'] = ((df_mes['Fallecidos'] / total) * 100).round(1) if total > 0 else 0
    fig_mes = px.line(df_mes, x='Mes', y='Fallecidos', markers=True, text='Fallecidos', title="Tendencia Mensual de Mortalidad 2026")
    fig_mes.update_traces(line_color='#d9534f', line_width=3, textposition='top center')

    df_rol = df_fil['Rol'].value_counts().reset_index()
    df_rol.columns = ['Rol del Usuario', 'Fallecidos']
    df_rol['Porcentaje (%)'] = ((df_rol['Fallecidos'] / total) * 100).round(1) if total > 0 else 0
    fig_rol = px.bar(df_rol, x='Rol del Usuario', y='Fallecidos', text='Fallecidos', color='Rol del Usuario', color_discrete_sequence=['#d9534f', '#f0ad4e', '#5bc0de'], title="Pilotos vs Acompañantes")
    fig_rol.update_traces(textposition='outside')

    df_circ = df_fil['Circunstancia'].value_counts().reset_index()
    df_circ.columns = ['Circunstancia de Ocurrencia', 'Fallecidos']
    df_circ['Porcentaje (%)'] = ((df_circ['Fallecidos'] / total) * 100).round(1) if total > 0 else 0
    fig_circ = px.bar(df_circ.sort_values(by='Fallecidos', ascending=True), x='Fallecidos', y='Circunstancia de Ocurrencia', orientation='h', text='Fallecidos', color='Fallecidos', color_continuous_scale='OrRd', title="Siniestros por Circunstancia")
    fig_circ.update_traces(textposition='outside')

    df_corr = df_fil.groupby(['Corredor', 'Jerarquia_Vial', 'Regimen_Trafico']).agg(
        Fallecidos=('Crucero', 'count'),
        Choques=('Circunstancia', lambda x: int(sum('choque' in normalizar_texto(v) for v in x))),
        Derrapes=('Circunstancia', lambda x: int(sum('derrape' in normalizar_texto(v) for v in x))),
        Vehiculo_Pesado=('Circunstancia', lambda x: int(sum(any(k in normalizar_texto(v) for k in ['camion', 'trailer', 'pick up', 'auto', 'prensado']) for v in x)))
    ).reset_index().sort_values(by='Fallecidos', ascending=False)
    df_corr['% del Total'] = ((df_corr['Fallecidos'] / total) * 100).round(1) if total > 0 else 0

    df_corr_prin = df_corr[df_corr['Corredor'] != 'Otras Vialidades / Red Secundaria'].sort_values(by='Fallecidos', ascending=True)
    fig_corr = px.bar(df_corr_prin, x='Fallecidos', y='Corredor', color='Jerarquia_Vial', orientation='h', text='Fallecidos', title="Corredores Metropolitanos y Accesos Críticos")
    fig_corr.update_traces(textposition='outside')
    fig_corr.update_yaxes(categoryorder='total ascending')

    df_jer = df_fil.groupby('Jerarquia_Vial').size().reset_index(name='Fallecidos').sort_values(by='Fallecidos', ascending=False)
    fig_jer = px.pie(df_jer, names='Jerarquia_Vial', values='Fallecidos', hole=0.4, title="Distribución por Jerarquía Vial")
    fig_jer.update_traces(textinfo='percent+value')

    tabla_corr_out = df_corr[['Corredor', 'Jerarquia_Vial', 'Fallecidos', '% del Total', 'Choques', 'Derrapes', 'Vehiculo_Pesado', 'Regimen_Trafico']]

    texto_combinado = df_fil['Circunstancia'].fillna('') + ' ' + df_fil['Enlace'].fillna('')
    es_pesado = texto_combinado.apply(lambda x: any(k in normalizar_texto(x) for k in ['camion', 'trailer', 'remolque', 'vehiculo pesado', 'vehiculo-pesado', 'carga', 'prensado']))
    df_pesado = pd.DataFrame({
        'Tipo de Evento': ['Involucra Transporte Pesado / Camión / Tráiler', 'Otros Choques / Derrapes'],
        'Cantidad': [int(es_pesado.sum()), int((~es_pesado).sum())]
    })
    df_pesado['Porcentaje (%)'] = ((df_pesado['Cantidad'] / total) * 100).round(1) if total > 0 else 0
    fig_pesado = px.pie(df_pesado, names='Tipo de Evento', values='Cantidad', title="Intervención de Transporte Pesado", color_discrete_sequence=['#c9302c', '#31b0d5'])
    fig_pesado.update_traces(textinfo='percent+value+label')

    df_tabla = df_fil.copy()
    if busqueda and busqueda.strip():
        q = normalizar_texto(busqueda)
        mask_q = (
            df_tabla['Domicilio_Original'].apply(lambda x: q in normalizar_texto(x)) |
            df_tabla['Municipio'].apply(lambda x: q in normalizar_texto(x)) |
            df_tabla['Corredor'].apply(lambda x: q in normalizar_texto(x)) |
            df_tabla['Circunstancia'].apply(lambda x: q in normalizar_texto(x))
        )
        df_tabla = df_tabla[mask_q]

    cols_mostrar = ['No.', 'Fecha_Texto', 'Mes_Nombre', 'Domicilio_Original', 'Municipio', 'Corredor', 'Edad_Display', 'Rango_Edad', 'Sexo_Clean', 'Rol', 'Circunstancia', 'Enlace']
    df_display = df_tabla[cols_mostrar].copy()
    df_display.columns = ['No.', 'Fecha', 'Mes', 'Domicilio / Cruce', 'Municipio', 'Corredor Vial', 'Edad', 'Rango de Edad', 'Sexo', 'Rol', 'Circunstancia', 'Link']

    tmp_csv = os.path.join(tempfile.gettempdir(), "siniestros_motos_zmg_2026.csv")
    df_display.to_csv(tmp_csv, index=False, encoding='utf-8-sig')

    return (
        kpis_html, mapa_html, top_cruces,
        df_mun, fig_mun,
        df_edad, fig_edad, df_sexo, fig_sexo,
        df_mes, fig_mes, df_rol, fig_rol,
        df_circ, fig_circ,
        fig_corr, fig_jer, tabla_corr_out,
        df_pesado, fig_pesado,
        df_display, tmp_csv
    )

municipios_opts = ['Todos'] + sorted([str(m) for m in DF_GLOBAL['Municipio'].unique() if pd.notna(m)])
jerarquias_opts = ['Todas'] + sorted([str(j) for j in DF_GLOBAL['Jerarquia_Vial'].unique() if pd.notna(j)])
circ_opts = ['Todas'] + sorted([str(c) for c in DF_GLOBAL['Circunstancia'].unique() if pd.notna(c)])

with gr.Blocks(title="Dashboard Mortalidad Vial ZMG 2026") as demo:
    gr.Markdown("# 🚨 Dashboard de Mortalidad por Siniestros Viales en la ZMG (2026)")
    gr.Markdown("Análisis geoespacial, estadístico y de corredores estratégicos de siniestros viales en el Área Metropolitana de Guadalajara.")

    with gr.Row():
        in_mun = gr.Dropdown(choices=municipios_opts, value='Todos', label="📍 Filtrar por Municipio")
        in_jer = gr.Dropdown(choices=jerarquias_opts, value='Todas', label="🛣️ Jerarquía Vial / Tipo de Corredor")
        in_circ = gr.Dropdown(choices=circ_opts, value='Todas', label="⚠️ Circunstancia del Siniestro")

    out_kpis = gr.HTML()

    gr.Markdown("## 📍 1. Mapa de Puntos Críticos y Tabla Detallada de Cruces")
    with gr.Row():
        out_mapa = gr.HTML(label="Mapa ZMG")
        out_cruces = gr.Dataframe(label="Ranking Completo de Intersecciones", interactive=False)

    gr.Markdown("## 🏙️ 2. Cantidad de Siniestros por Municipio")
    with gr.Row():
        out_mun_tab = gr.Dataframe(label="Tabla por Municipio", interactive=False)
        out_mun_fig = gr.Plot(label="Comparativa Visual por Municipio")

    gr.Markdown("## 👥 3. Perfil Demográfico: Rango de Edad y Sexo")
    with gr.Row():
        out_edad_tab = gr.Dataframe(label="Fallecidos por Rango de Edad", interactive=False)
        out_edad_fig = gr.Plot(label="Gráfico Rango de Edad")
    with gr.Row():
        out_sexo_tab = gr.Dataframe(label="Distribución por Sexo", interactive=False)
        out_sexo_fig = gr.Plot(label="Proporción por Sexo")

    gr.Markdown("## 📅 4. Evolución Mensual y Rol de las Víctimas")
    with gr.Row():
        out_mes_tab = gr.Dataframe(label="Víctimas por Mes", interactive=False)
        out_mes_fig = gr.Plot(label="Tendencia Mensual 2026")
    with gr.Row():
        out_rol_tab = gr.Dataframe(label="Pilotos vs Acompañantes", interactive=False)
        out_rol_fig = gr.Plot(label="Gráfico por Rol")

    gr.Markdown("## ⚠️ 5. Circunstancia por la que Ocurrió el Siniestro")
    with gr.Row():
        out_circ_tab = gr.Dataframe(label="Tabla por Circunstancia", interactive=False)
        out_circ_fig = gr.Plot(label="Comparativa por Circunstancia")

    gr.Markdown("## 🛣️ 6. Corredores Estratégicos, Arterias Principales y Vías de Ingreso/Salida")
    with gr.Row():
        out_corr_fig = gr.Plot(label="Corredores Metropolitanos y Accesos")
        out_jer_fig = gr.Plot(label="Distribución por Jerarquía Vial")
    out_corr_tab = gr.Dataframe(label="Tabla Analítica de Corredores y Dinámica de Tráfico", interactive=False)

    gr.Markdown("## 🚛 7. Análisis de Letalidad por Intervención de Vehículos Pesados")
    with gr.Row():
        out_pes_tab = gr.Dataframe(label="Tabla Transporte Pesado", interactive=False)
        out_pes_fig = gr.Plot(label="Gráfico Transporte Pesado")

    gr.Markdown("## 📋 8. Base Completa de Siniestros Registrados")
    in_busqueda = gr.Textbox(label="🔎 Buscar por calle, municipio, corredor o circunstancia:", placeholder="Escribe aquí para filtrar la tabla...")
    out_base = gr.Dataframe(label="Registros Detallados", interactive=False)
    out_csv = gr.File(label="⬇️ Descargar Base Filtrada (CSV)")

    inputs = [in_mun, in_jer, in_circ, in_busqueda]
    outputs = [
        out_kpis, out_mapa, out_cruces,
        out_mun_tab, out_mun_fig,
        out_edad_tab, out_edad_fig, out_sexo_tab, out_sexo_fig,
        out_mes_tab, out_mes_fig, out_rol_tab, out_rol_fig,
        out_circ_tab, out_circ_fig,
        out_corr_fig, out_jer_fig, out_corr_tab,
        out_pes_tab, out_pes_fig,
        out_base, out_csv
    ]

    for inp in inputs:
        inp.change(fn=actualizar_dashboard, inputs=inputs, outputs=outputs)

    demo.load(fn=actualizar_dashboard, inputs=inputs, outputs=outputs)

if __name__ == "__main__":
    demo.launch()
