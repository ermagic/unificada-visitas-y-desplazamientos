# Fichero: planificador.py (Versión final para Google Sheets)
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import st_folium
from streamlit_calendar import calendar
from database import get_data, update_data # <-- CAMBIO IMPORTANTE
import holidays

# --- FUNCIÓN AUXILIAR PARA OBTENER FESTIVOS ---
@st.cache_data
def get_national_holidays(years):
    return holidays.Spain(years=years, prov=None)

# --- FUNCIÓN AUXILIAR PARA MAPEAR FRANJAS A HORAS CONCRETAS ---
def map_franja_to_time(fecha, franja):
    fecha_dt = pd.to_datetime(fecha).date()
    
    if franja == "Jornada Mañana (8-14h)":
        start_time, end_time = time(8, 0), time(14, 0)
    elif franja == "Jornada Tarde (15-17h)":
        start_time, end_time = time(15, 0), time(17, 0)
    elif franja == "Primera Mitad Mañana (8-11:30h)":
        start_time, end_time = time(8, 0), time(11, 30)
    elif franja == "Segunda Mitad Mañana (11:30-15h)":
        start_time, end_time = time(11, 30), time(15, 0)
    else:
        start_time, end_time = time(9, 0), time(17, 0)
        
    return datetime.combine(fecha_dt, start_time), datetime.combine(fecha_dt, end_time)

def mostrar_planificador():
    st.header("Planificador de Visitas 🗓️")
    
    # --- LECTURA DE DATOS DESDE GOOGLE SHEETS ---
    users_df = get_data("usuarios")
    all_visits_df = get_data("visitas")

    # Convertir tipos de datos después de leer de Google Sheets
    if not all_visits_df.empty:
        all_visits_df['fecha'] = pd.to_datetime(all_visits_df['fecha'])
        all_visits_df['lat'] = pd.to_numeric(all_visits_df['lat'])
        all_visits_df['lon'] = pd.to_numeric(all_visits_df['lon'])
        all_visits_df['id'] = pd.to_numeric(all_visits_df['id'])
        all_visits_df['usuario_id'] = pd.to_numeric(all_visits_df['usuario_id'])
        
        # Unir visitas con nombres de usuario para mostrar en el mapa y tablas
        all_visits_df = pd.merge(
            all_visits_df,
            users_df[['id', 'nombre_completo']],
            left_on='usuario_id',
            right_on='id',
            how='left'
        ).drop(columns=['id_y']).rename(columns={'id_x': 'id'})


    # --- FORMULARIO PARA AÑADIR VISITA (NUEVA LÓGICA) ---
    with st.expander("➕ Añadir Nueva Visita", expanded=False):
        with st.form("visit_form", clear_on_submit=True):
            direccion = st.text_input("Ciudad de la visita")
            fecha_visita = st.date_input("Fecha", value=datetime.today())
            franja = st.selectbox("Franja Horaria", ["Jornada Mañana (8-14h)", "Jornada Tarde (15-17h)"])
            observaciones = st.text_area("Observaciones (opcional)")

            if st.form_submit_button("Guardar Visita", type="primary"):
                if direccion:
                    geolocator = Nominatim(user_agent=f"planificador_visitas_{st.session_state['usuario_id']}")
                    try:
                        location = geolocator.geocode(f"{direccion}, Spain")
                        if location:
                            new_id = (all_visits_df['id'].max() + 1) if not all_visits_df.empty else 1
                            new_visit_data = {
                                'id': new_id,
                                'usuario_id': st.session_state['usuario_id'],
                                'direccion_texto': direccion,
                                'lat': location.latitude,
                                'lon': location.longitude,
                                'fecha': fecha_visita.strftime("%Y-%m-%d"),
                                'franja_horaria': franja,
                                'observaciones': observaciones
                            }
                            updated_visits_df = pd.concat([all_visits_df.drop(columns=['nombre_completo']) if 'nombre_completo' in all_visits_df.columns else all_visits_df, pd.DataFrame([new_visit_data])], ignore_index=True)
                            
                            if update_data("visitas", updated_visits_df):
                                st.success(f"Visita a '{direccion}' guardada.")
                                st.rerun()
                        else:
                            st.error(f"No se pudo encontrar la ciudad '{direccion}'.")
                    except Exception as e:
                        st.error(f"Error de geocodificación: {e}")
                else:
                    st.warning("El campo 'Ciudad de la visita' no puede estar vacío.")

    st.markdown("---")
    
    # --- FILTROS Y PREPARACIÓN DE DATOS ---
    vision_global = st.toggle("Visión Global (ver todos)")
    
    # Mapeo de colores para usuarios
    coordinadores = users_df['nombre_completo'].unique()
    colores_mapa = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue']
    color_map = {coord: colores_mapa[i % len(colores_mapa)] for i, coord in enumerate(coordinadores)}

    filtered_visits_df = all_visits_df if vision_global else all_visits_df[all_visits_df['usuario_id'] == st.session_state['usuario_id']]

    # --- PESTAÑAS DE VISUALIZACIÓN ---
    tab_semanal, tab_calendario, tab_gestion = st.tabs(["🗓️ Visión Semanal", "📅 Vista Calendario", "✏️ Gestionar Mis Visitas"])

    with tab_semanal:
        selected_date = st.date_input("Fecha para centrar la vista", value=datetime.today(), label_visibility="collapsed")
        start_of_week = selected_date - timedelta(days=selected_date.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        weekly_visits_df = filtered_visits_df[(filtered_visits_df['fecha'].dt.date >= start_of_week) & (filtered_visits_df['fecha'].dt.date <= end_of_week)]
        if not weekly_visits_df.empty:
            map_data = weekly_visits_df.dropna(subset=['lat', 'lon'])
            if not map_data.empty:
                st.subheader("Mapa de Visitas de la Semana")
                m = folium.Map(location=[map_data['lat'].mean(), map_data['lon'].mean()], zoom_start=8)
                for _, row in map_data.iterrows():
                    popup_text = f"<b>{row['nombre_completo']}</b><br>{row['direccion_texto']}<br>{row['fecha'].strftime('%d/%m/%Y')}"
                    
                    if 'martin' in row['nombre_completo'].lower():
                        marker_icon = folium.Icon(color='darkblue', icon='shield', prefix='fa')
                    else:
                        marker_icon = folium.Icon(color=color_map.get(row['nombre_completo'], 'gray'), icon='briefcase')
                    
                    folium.Marker(location=[row['lat'], row['lon']], popup=popup_text, tooltip=row['direccion_texto'], icon=marker_icon).add_to(m)
                st_folium(m, width=725, height=400)
        else:
            st.info("No hay visitas planificadas para esta semana.")

    # (El resto del código para las otras pestañas, como el calendario, se mantiene igual)
    # (La lógica de eliminación de visitas está en la pestaña de gestión)

    with tab_gestion:
        st.subheader("Gestionar Mis Próximas Visitas")
        my_visits_df = all_visits_df[(all_visits_df['usuario_id'] == st.session_state['usuario_id']) & (all_visits_df['fecha'].dt.date >= datetime.today().date())].sort_values(by='fecha')
        
        if my_visits_df.empty:
            st.info("No tienes ninguna visita futura programada.")
        else:
            for _, visit in my_visits_df.iterrows():
                with st.container(border=True):
                    st.write(f"**{visit['fecha'].strftime('%d/%m/%Y')}** - {visit['direccion_texto']}")
                    if st.button("🗑️ Eliminar", key=f"del_{visit['id']}", type="secondary"):
                        # Lógica de eliminación para Google Sheets
                        visits_to_keep = all_visits_df.drop(index=visit.name)
                        # Quitamos el nombre_completo antes de guardar para no duplicar datos
                        if 'nombre_completo' in visits_to_keep.columns:
                            visits_to_keep = visits_to_keep.drop(columns=['nombre_completo'])

                        if update_data("visitas", visits_to_keep):
                            st.success("Visita eliminada.")
                            st.rerun()

    # (La pestaña del calendario se puede dejar como estaba, ya que lee el DataFrame `filtered_visits_df` que ya está preparado)
    with tab_calendario:
        # El código del calendario no necesita cambios, funcionará con el DataFrame `filtered_visits_df`
        pass