# Fichero: stats.py (Versión corregida que une el Cuadro de Mando y el Kilometraje)
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from database import supabase
import plotly.express as px
import googlemaps
from streamlit_calendar import calendar

@st.cache_data(ttl=3600)
def calcular_kilometraje_equipo(_start_date, _end_date):
    """
    Calcula el kilometraje total y por coordinador para un rango de fechas.
    Utiliza la API Directions con waypoints para optimizar las llamadas.
    """
    try:
        visitas_res = supabase.table('visitas').select('*, coordinador:usuario_id(*)').gte('fecha_asignada', _start_date).lte('fecha_asignada', _end_date).execute()
        df_visitas = pd.DataFrame(visitas_res.data)

        if df_visitas.empty:
            return 0, pd.DataFrame()

        df_visitas['nombre_coordinador'] = df_visitas['coordinador'].apply(lambda x: x.get('nombre_completo') if isinstance(x, dict) else 'Supervisor')
        df_visitas['punto_partida'] = df_visitas['coordinador'].apply(lambda x: x.get('punto_partida') if isinstance(x, dict) else 'Plaça de Catalunya, Barcelona')
        df_visitas['fecha_asignada'] = pd.to_datetime(df_visitas['fecha_asignada']).dt.date

        df_visitas.dropna(subset=['punto_partida', 'direccion_texto'], inplace=True)
        if df_visitas.empty:
            return 0, pd.DataFrame()

        gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
        km_por_coordinador = {}

        for (coordinador, fecha), group in df_visitas.groupby(['nombre_coordinador', 'fecha_asignada']):
            if group.empty:
                continue

            punto_partida = group['punto_partida'].iloc[0]
            group['hora_asignada'] = pd.to_datetime(group['hora_asignada'], format='%H:%M', errors='coerce').dt.time
            group.sort_values('hora_asignada', inplace=True)
            
            direcciones = group['direccion_texto'].tolist()
            
            # Si solo hay una visita, es un viaje de ida y vuelta (A->B)
            if len(direcciones) == 1:
                origen = punto_partida
                destino = direcciones[0]
                try:
                    dist_matrix = gmaps.distance_matrix(origen, destino, mode="driving")
                    km_dia = dist_matrix['rows'][0]['elements'][0].get('distance', {}).get('value', 0) / 1000
                    km_por_coordinador[coordinador] = km_por_coordinador.get(coordinador, 0) + km_dia
                except Exception:
                    continue # Ignorar si hay un error con esta ruta
            
            # Si hay más de una visita, usamos la API Directions con waypoints (A->B->C->...)
            else:
                origen = punto_partida
                destino = direcciones[-1]
                waypoints = direcciones[:-1]

                try:
                    directions_result = gmaps.directions(origen, destino, waypoints=waypoints, mode="driving")
                    if not directions_result:
                        continue
                    
                    total_km_dia = 0
                    for leg in directions_result[0]['legs']:
                        total_km_dia += leg['distance']['value']
                    
                    km_por_coordinador[coordinador] = km_por_coordinador.get(coordinador, 0) + (total_km_dia / 1000)
                except Exception:
                    continue # Ignorar si hay un error con esta ruta

        if not km_por_coordinador:
            return 0, pd.DataFrame()

        df_km = pd.DataFrame(list(km_por_coordinador.items()), columns=['Coordinador', 'Kilómetros']).sort_values('Kilómetros', ascending=False)
        total_km = df_km['Kilómetros'].sum()

        return total_km, df_km

    except Exception as e:
        st.error(f"Error calculando el kilometraje: {e}")
        return 0, pd.DataFrame()

def mostrar_stats():
    st.header("📊 Estadísticas y Métricas del Equipo")

    # --- 1. CUADRO DE MANDO DE AYUDAS DEL SUPERVISOR (CÓDIGO RESTAURADO) ---
    st.subheader("Cuadro de Mando de Ayudas del Supervisor")
    try:
        response = supabase.table('visitas').select(
            '*, usuarios:usuario_id(nombre_completo)'
        ).eq('status', 'Asignada a Supervisor').execute()
        df_base = pd.DataFrame(response.data)
        if df_base.empty:
            st.info("Aún no hay visitas asignadas al supervisor para mostrar en el cuadro de mando.")
        else:
            df_base['nombre_coordinador'] = df_base['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'Desconocido')
            df_base['fecha_asignada'] = pd.to_datetime(df_base['fecha_asignada']).dt.date
            df_base.dropna(subset=['nombre_coordinador', 'fecha_asignada'], inplace=True)
            df_base.sort_values('fecha_asignada', inplace=True)

            col1, col2 = st.columns(2)
            with col1:
                fecha_min = df_base['fecha_asignada'].min()
                fecha_max = df_base['fecha_asignada'].max()
                if fecha_min == fecha_max: fecha_max += timedelta(days=1)
                selected_dates = st.date_input(
                    "Selecciona un rango para ver las ayudas",
                    value=(fecha_min, fecha_max), min_value=fecha_min, max_value=fecha_max,
                    key="ayudas_date_range"
                )
                start_date, end_date = selected_dates[0], selected_dates[1] if len(selected_dates) > 1 else selected_dates[0]
            with col2:
                lista_coordinadores = sorted(df_base['nombre_coordinador'].unique())
                selected_coordinadores = st.multiselect("Filtra por coordinador", options=lista_coordinadores, default=lista_coordinadores)

            df_filtered = df_base[(df_base['fecha_asignada'] >= start_date) & (df_base['fecha_asignada'] <= end_date) & (df_base['nombre_coordinador'].isin(selected_coordinadores))]

            if not df_filtered.empty:
                counts = df_filtered['nombre_coordinador'].value_counts()
                gcol1, gcol2 = st.columns(2)
                with gcol1:
                    fig_bar = px.bar(counts, x=counts.index, y=counts.values, labels={'x': 'Coordinador', 'y': 'Nº de Visitas'})
                    st.plotly_chart(fig_bar, use_container_width=True)
                with gcol2:
                    fig_pie = px.pie(counts, names=counts.index, values=counts.values, title="Proporción de Ayudas (%)")
                    st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.warning("No se encontraron ayudas con los filtros seleccionados.")

    except Exception as e:
        st.error(f"Error al cargar el cuadro de mando de ayudas: {e}")

    st.markdown("---")

    # --- 2. KILOMETRAJE ESTIMADO DEL EQUIPO (CÓDIGO CORREGIDO) ---
    st.subheader("🚗 Kilometraje Estimado del Equipo")
    
    # Selector de fechas INDEPENDIENTE para el kilometraje
    today = date.today()
    km_start_date = st.date_input("Fecha de inicio", value=today - timedelta(days=30), key="km_start_date")
    km_end_date = st.date_input("Fecha de fin", value=today, key="km_end_date")

    if km_start_date and km_end_date:
        if km_start_date > km_end_date:
            st.error("La fecha de inicio no puede ser posterior a la fecha de fin.")
        else:
            with st.spinner("Calculando kilometraje del equipo..."):
                total_km, df_km = calcular_kilometraje_equipo(km_start_date, km_end_date)

            st.metric("Kilometraje Total del Equipo en el Periodo", f"{total_km:.1f} km")
            
            if not df_km.empty:
                st.write("**Desglose por Coordinador:**")
                st.dataframe(df_km, use_container_width=True, hide_index=True)
            else:
                st.info("No hay datos de kilometraje para el periodo seleccionado.")