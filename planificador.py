# Fichero: planificador.py (Versión con Edición de Visitas)
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import st_folium
from streamlit_calendar import calendar
from database import supabase # Importamos el cliente de Supabase

# --- FUNCIÓN AUXILIAR PARA MAPEAR FRANJAS A HORAS CONCRETAS ---
def map_franja_to_time(fecha, franja):
    fecha_dt = pd.to_datetime(fecha).date()
    
    if franja == "Jornada Mañana (8-14h)":
        start_time, end_time = time(8, 0), time(14, 0)
    elif franja == "Jornada Tarde (15-17h)":
        start_time, end_time = time(15, 0), time(17, 0)
    else: # Default o si hay otros valores
        start_time, end_time = time(9, 0), time(17, 0)
        
    return datetime.combine(fecha_dt, start_time).isoformat(), datetime.combine(fecha_dt, end_time).isoformat()

def mostrar_planificador():
    st.header("Planificador de Visitas 🗓️")
    
    if not supabase:
        st.error("La conexión con la base de datos no está disponible.")
        st.stop()

    # --- LECTURA DE DATOS DESDE SUPABASE ---
    users_response = supabase.table('usuarios').select('id, nombre_completo').execute()
    users_df = pd.DataFrame(users_response.data)
    
    visits_response = supabase.table('visitas').select('*').execute()
    all_visits_df = pd.DataFrame(visits_response.data)

    # Preparamos el DataFrame principal si no está vacío
    if not all_visits_df.empty:
        all_visits_df['fecha'] = pd.to_datetime(all_visits_df['fecha'])
        all_visits_df = pd.merge(
            all_visits_df, users_df,
            left_on='usuario_id', right_on='id',
            how='left'
        ).rename(columns={'id_x': 'id'})

    # --- FORMULARIO PARA AÑADIR VISITA (YA FUNCIONAL CON SUPABASE) ---
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
                            new_visit_data = {
                                'usuario_id': st.session_state['usuario_id'],
                                'direccion_texto': direccion,
                                'lat': location.latitude,
                                'lon': location.longitude,
                                'fecha': fecha_visita.strftime("%Y-%m-%d"),
                                'franja_horaria': franja,
                                'observaciones': observaciones
                            }
                            supabase.table('visitas').insert(new_visit_data).execute()
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
    # Permitir a los admins ver todo, los demás solo ven lo suyo
    if st.session_state['rol'] == 'admin':
        vision_global = st.toggle("Visión Global (ver todos los usuarios)", value=True)
        filtered_visits_df = all_visits_df if vision_global else all_visits_df[all_visits_df['usuario_id'] == st.session_state['usuario_id']]
    else:
        filtered_visits_df = all_visits_df[all_visits_df['usuario_id'] == st.session_state['usuario_id']]

    # Mapeo de colores para usuarios
    if not users_df.empty:
        coordinadores = users_df['nombre_completo'].unique()
        colores_mapa = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue']
        color_map = {coord: colores_mapa[i % len(colores_mapa)] for i, coord in enumerate(coordinadores)}
    else:
        color_map = {}

    # --- PESTAÑAS DE VISUALIZACIÓN ---
    tab_semanal, tab_calendario, tab_gestion = st.tabs(["🗓️ Visión Semanal", "📅 Vista Calendario", "✏️ Gestionar Mis Visitas"])

    # PESTAÑA 1: MAPA SEMANAL (RESTAURADA)
    with tab_semanal:
        st.subheader("Mapa de Visitas")
        selected_date = st.date_input("Selecciona una fecha para centrar la semana", value=datetime.today())
        start_of_week = selected_date - timedelta(days=selected_date.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        st.info(f"Mostrando visitas para la semana del {start_of_week.strftime('%d/%m/%Y')} al {end_of_week.strftime('%d/%m/%Y')}")

        weekly_visits_df = filtered_visits_df[
            (filtered_visits_df['fecha'].dt.date >= start_of_week.date()) & 
            (filtered_visits_df['fecha'].dt.date <= end_of_week.date())
        ]

        if not weekly_visits_df.empty:
            map_data = weekly_visits_df.dropna(subset=['lat', 'lon'])
            if not map_data.empty:
                m = folium.Map(location=[map_data['lat'].mean(), map_data['lon'].mean()], zoom_start=7)
                for _, row in map_data.iterrows():
                    popup_text = f"<b>{row['nombre_completo']}</b><br>{row['direccion_texto']}<br>{row['fecha'].strftime('%d/%m/%Y')}"
                    
                    folium.Marker(
                        location=[row['lat'], row['lon']], 
                        popup=popup_text, 
                        tooltip=row['nombre_completo'], 
                        icon=folium.Icon(color=color_map.get(row['nombre_completo'], 'gray'))
                    ).add_to(m)
                st_folium(m, width=725, height=400)
            else:
                st.warning("No hay visitas con coordenadas geográficas para mostrar en el mapa esta semana.")
        else:
            st.info("No hay visitas planificadas para esta semana.")

    # PESTAÑA 2: CALENDARIO (RESTAURADO)
    with tab_calendario:
        st.subheader("Calendario de Visitas")
        calendar_events = []
        if not filtered_visits_df.empty:
            for _, row in filtered_visits_df.iterrows():
                start_time, end_time = map_franja_to_time(row['fecha'], row['franja_horaria'])
                calendar_events.append({
                    "title": f"{row['nombre_completo']} - {row['direccion_texto']}",
                    "start": start_time,
                    "end": end_time,
                    "color": color_map.get(row['nombre_completo'], 'gray'),
                })
        
        calendar_options = {
            "headerToolbar": {
                "left": "prev,next today",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek,timeGridDay",
            },
            "initialView": "dayGridMonth",
            "locale": "es", # Calendario en español
        }
        
        calendar(events=calendar_events, options=calendar_options)

    # PESTAÑA 3: GESTIÓN DE VISITAS (CÓDIGO ACTUALIZADO CON EDICIÓN)
    with tab_gestion:
        st.subheader("Gestionar Mis Próximas Visitas")
        
        my_id = st.session_state['usuario_id']
        # Usamos el DataFrame ya cargado para no hacer otra llamada a la DB
        my_visits_df = all_visits_df[
            (all_visits_df['usuario_id'] == my_id) & 
            (all_visits_df['fecha'].dt.date >= datetime.today().date())
        ].sort_values(by='fecha')

        if my_visits_df.empty:
            st.info("No tienes ninguna visita futura programada.")
        else:
            for _, visit in my_visits_df.iterrows():
                # Usamos el ID de la visita para asegurar que cada contenedor y sus elementos son únicos
                visit_id = visit['id'] 
                
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1]) # Dividimos en columnas para alinear botones
                    
                    with col1:
                        fecha_formateada = visit['fecha'].strftime('%d/%m/%Y')
                        st.write(f"**{fecha_formateada}** - **{visit['direccion_texto']}**")
                        st.caption(f"Franja: {visit['franja_horaria']}")
                        if visit['observaciones']:
                            st.info(f"Observaciones: {visit['observaciones']}", icon="ℹ️")

                    with col2:
                        # Botón para eliminar, con una clave única
                        if st.button("🗑️ Eliminar", key=f"del_{visit_id}", use_container_width=True):
                            supabase.table('visitas').delete().eq('id', visit_id).execute()
                            st.success(f"Visita a {visit['direccion_texto']} eliminada.")
                            st.rerun()

                    # El formulario de edición estará en un expander
                    with st.expander("✏️ Editar esta visita"):
                        with st.form(key=f"edit_form_{visit_id}", clear_on_submit=False):
                            # Pre-cargamos los valores actuales de la visita
                            franjas_list = ["Jornada Mañana (8-14h)", "Jornada Tarde (15-17h)"]
                            current_franja_index = franjas_list.index(visit['franja_horaria']) if visit['franja_horaria'] in franjas_list else 0

                            new_fecha = st.date_input("Nueva Fecha", value=pd.to_datetime(visit['fecha']), key=f"date_{visit_id}")
                            new_franja = st.selectbox("Nueva Franja", options=franjas_list, index=current_franja_index, key=f"franja_{visit_id}")
                            new_observaciones = st.text_area("Nuevas Observaciones", value=visit['observaciones'], key=f"obs_{visit_id}")

                            if st.form_submit_button("Actualizar Visita", type="primary"):
                                update_data = {
                                    'fecha': new_fecha.strftime("%Y-%m-%d"),
                                    'franja_horaria': new_franja,
                                    'observaciones': new_observaciones
                                }
                                # No actualizamos la dirección para mantener la geolocalización original
                                # Si quisieras cambiarla, habría que volver a geolocalizar
                                
                                supabase.table('visitas').update(update_data).eq('id', visit_id).execute()
                                st.success(f"Visita a {visit['direccion_texto']} actualizada.")
                                st.rerun()