# Fichero: stats.py (Versión Cuadro de Mando Interactivo)
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from database import supabase
from streamlit_calendar import calendar
import plotly.express as px

# --- Función Principal del Cuadro de Mando ---
def mostrar_stats():
    st.header("📊 Cuadro de Mando de Ayudas del Supervisor")

    # --- OBTENCIÓN Y PREPARACIÓN DE DATOS ---
    try:
        response = supabase.table('visitas').select(
            '*, usuarios:usuario_id(nombre_completo)'
        ).eq(
            'status', 'Asignada a Supervisor'
        ).execute()

        df_base = pd.DataFrame(response.data)

        if df_base.empty:
            st.info("Aún no hay visitas asignadas al supervisor para mostrar.")
            return

        df_base['nombre_coordinador'] = df_base['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'Desconocido')
        df_base['fecha_asignada'] = pd.to_datetime(df_base['fecha_asignada']).dt.date
        df_base.dropna(subset=['nombre_coordinador', 'fecha_asignada'], inplace=True)
        df_base.sort_values('fecha_asignada', inplace=True)

    except Exception as e:
        st.error(f"Error al cargar los datos de las visitas: {e}")
        return

    # --- 1. FILTROS DINÁMICOS ---
    st.markdown("### 🕵️‍♀️ Filtros")
    
    col1, col2 = st.columns(2)
    with col1:
        # Selector de Rango de Fechas
        fecha_min = df_base['fecha_asignada'].min()
        fecha_max = df_base['fecha_asignada'].max()
        
        # Corrección para evitar error si solo hay una fecha
        if fecha_min == fecha_max:
            fecha_max += timedelta(days=1)
            
        selected_dates = st.date_input(
            "Selecciona un rango de fechas",
            value=(fecha_min, fecha_max),
            min_value=fecha_min,
            max_value=fecha_max,
            key="date_range_selector"
        )
        
        # Aseguramos tener un rango válido
        start_date = selected_dates[0]
        end_date = selected_dates[1] if len(selected_dates) > 1 else selected_dates[0]

    with col2:
        # Selector de Coordinadores
        lista_coordinadores = sorted(df_base['nombre_coordinador'].unique())
        selected_coordinadores = st.multiselect(
            "Filtra por coordinador",
            options=lista_coordinadores,
            default=lista_coordinadores
        )

    # Aplicar filtros al DataFrame
    df_filtered = df_base[
        (df_base['fecha_asignada'] >= start_date) &
        (df_base['fecha_asignada'] <= end_date) &
        (df_base['nombre_coordinador'].isin(selected_coordinadores))
    ]

    if df_filtered.empty:
        st.warning("No se encontraron visitas con los filtros seleccionados.")
        return

    st.markdown("---")

    # --- 2. GRÁFICOS DE DISTRIBUCIÓN ---
    st.markdown("### 📊 Gráficos de Distribución")
    
    counts = df_filtered['nombre_coordinador'].value_counts()

    gcol1, gcol2 = st.columns(2)
    with gcol1:
        st.markdown("#### Cantidad de Ayudas")
        # Gráfico de Barras con Plotly para más control
        fig_bar = px.bar(counts, x=counts.index, y=counts.values, labels={'x': 'Coordinador', 'y': 'Nº de Visitas'})
        st.plotly_chart(fig_bar, use_container_width=True)

    with gcol2:
        st.markdown("#### Proporción de Ayudas (%)")
        # Gráfico Circular
        fig_pie = px.pie(counts, names=counts.index, values=counts.values)
        st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("---")

    # --- 3. TABLA DETALLADA DE VISITAS ---
    st.markdown("### 📋 Tabla Detallada de Visitas Transferidas")
    df_display = df_filtered[['fecha_asignada', 'nombre_coordinador', 'direccion_texto', 'equipo', 'observaciones']].rename(columns={
        'fecha_asignada': 'Fecha',
        'nombre_coordinador': 'Coordinador Original',
        'direccion_texto': 'Ubicación',
        'equipo': 'Equipo',
        'observaciones': 'Obs.'
    }).reset_index(drop=True)
    st.dataframe(df_display, use_container_width=True)

    st.markdown("---")
    
    # --- 4. CALENDARIO VISUAL DE AYUDAS ---
    st.markdown("### 🗓️ Calendario Visual de Ayudas")

    # Generar paleta de colores para los coordinadores
    color_palette = px.colors.qualitative.Plotly
    coordinador_colors = {coord: color_palette[i % len(color_palette)] for i, coord in enumerate(lista_coordinadores)}

    events = []
    for _, row in df_filtered.iterrows():
        events.append({
            "title": f"{row['nombre_coordinador']} - {row['equipo']}",
            "start": row['fecha_asignada'].isoformat(),
            "end": row['fecha_asignada'].isoformat(),
            "color": coordinador_colors.get(row['nombre_coordinador'], '#808080'), # Gris si no encuentra color
            "textColor": "white"
        })

    calendar_css = """
    .fc-event-title { font-size: 0.8em !important; line-height: 1.2 !important; white-space: normal !important; padding: 2px !important; }
    """
    
    calendar(
        events=events,
        options={"initialView": "dayGridMonth", "locale": "es"},
        custom_css=calendar_css,
        key=f"cal_{start_date}_{end_date}"
    )