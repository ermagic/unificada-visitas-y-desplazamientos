# Fichero: stats.py (Versión con Kilometraje)
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from database import supabase
import plotly.express as px
import googlemaps

@st.cache_data(ttl=3600)
def calcular_kilometraje_equipo(_start_date, _end_date):
    """
    Calcula el kilometraje total y por coordinador para un rango de fechas.
    """
    try:
        # Obtener todas las visitas y usuarios
        visitas_res = supabase.table('visitas').select('*, coordinador:usuario_id(*)').gte('fecha', _start_date).lte('fecha', _end_date).execute()
        df_visitas = pd.DataFrame(visitas_res.data)

        if df_visitas.empty:
            return 0, pd.DataFrame()

        # Limpiar datos
        df_visitas['nombre_coordinador'] = df_visitas['coordinador'].apply(lambda x: x.get('nombre_completo') if isinstance(x, dict) else 'Supervisor')
        df_visitas['punto_partida'] = df_visitas['coordinador'].apply(lambda x: x.get('punto_partida') if isinstance(x, dict) else 'Plaça de Catalunya, Barcelona')
        df_visitas['fecha'] = pd.to_datetime(df_visitas['fecha'])

        # Filtrar visitas sin punto de partida válido
        df_visitas.dropna(subset=['punto_partida', 'direccion_texto'], inplace=True)
        if df_visitas.empty:
            return 0, pd.DataFrame()

        gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
        km_por_coordinador = {}

        # Agrupar por coordinador y por día
        for (coordinador, fecha), group in df_visitas.groupby(['nombre_coordinador', pd.Grouper(key='fecha', freq='D')]):
            punto_partida = group['punto_partida'].iloc[0]
            direcciones = [punto_partida] + group['direccion_texto'].tolist()
            
            total_km_dia = 0
            # Calcular distancia entre puntos consecutivos de la ruta
            for i in range(len(direcciones) - 1):
                origen = direcciones[i]
                destino = direcciones[i+1]
                if origen != destino:
                    dist_matrix = gmaps.distance_matrix(origen, destino, mode="driving")
                    km_tramo = dist_matrix['rows'][0]['elements'][0].get('distance', {}).get('value', 0) / 1000
                    total_km_dia += km_tramo
            
            km_por_coordinador[coordinador] = km_por_coordinador.get(coordinador, 0) + total_km_dia

        df_km = pd.DataFrame(list(km_por_coordinador.items()), columns=['Coordinador', 'Kilómetros']).sort_values('Kilómetros', ascending=False)
        total_km = df_km['Kilómetros'].sum()

        return total_km, df_km

    except Exception:
        return 0, pd.DataFrame()

def mostrar_stats():
    st.header("📊 Cuadro de Mando de Ayudas del Supervisor")
    # ... (código del Cuadro de Mando de Ayudas sin cambios) ...

    st.markdown("---")
    # --- INICIO NUEVA SECCIÓN: KILOMETRAJE ---
    st.subheader("🚗 Kilometraje Estimado del Equipo")
    
    # Reutilizar los filtros de fecha de la sección anterior
    if 'date_range_selector' in st.session_state and len(st.session_state.date_range_selector) == 2:
        start_date, end_date = st.session_state.date_range_selector
        
        with st.spinner("Calculando kilometraje del equipo..."):
            total_km, df_km = calcular_kilometraje_equipo(start_date, end_date)

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Kilometraje Total del Equipo", f"{total_km:.1f} km")
        
        if not df_km.empty:
            with col2:
                st.write("**Desglose por Coordinador:**")
                st.dataframe(df_km, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos de kilometraje para el periodo seleccionado.")
    else:
        st.info("Selecciona un rango de fechas para calcular el kilometraje.")
    # --- FIN NUEVA SECCIÓN ---
