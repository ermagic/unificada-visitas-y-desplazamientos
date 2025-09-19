# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import st_folium
from streamlit_calendar import calendar
from database import obtener_conexion
import holidays

# --- FUNCIÓN AUXILIAR PARA OBTENER FESTIVOS ---
@st.cache_data
def get_national_holidays(years):
    """
    Obtiene únicamente los festivos nacionales de España.
    """
    return holidays.Spain(years=years, prov=None)

# --- FUNCIÓN AUXILIAR PARA MAPEAR FRANJAS A HORAS CONCRETAS ---
def map_franja_to_time(fecha, franja):
    """Convierte una fecha y una franja horaria de texto en objetos datetime de inicio y fin."""
    fecha_dt = pd.to_datetime(fecha).date()
    
    if franja == "Jornada Mañana (8-14h)":
        start_time = time(8, 0)
        end_time = time(14, 0)
    elif franja == "Jornada Tarde (15-17h)":
        start_time = time(15, 0)
        end_time = time(17, 0)
    elif franja == "Primera Mitad Mañana (8-11:30h)":
        start_time = time(8, 0)
        end_time = time(11, 30)
    elif franja == "Segunda Mitad Mañana (11:30-15h)":
        start_time = time(11, 30)
        end_time = time(15, 0)
    else: # Fallback
        start_time = time(9, 0)
        end_time = time(17, 0)
        
    start_datetime = datetime.combine(fecha_dt, start_time)
    end_datetime = datetime.combine(fecha_dt, end_time)
    
    return start_datetime, end_datetime


def mostrar_planificador():
    st.header("Planificador de Visitas 🗓️")
    
    conn = obtener_conexion()
    try:
        cursor = conn.cursor()

        # --- FORMULARIO PARA AÑADIR VISITA ---
        with st.expander("➕ Añadir Nueva Visita", expanded=False):
            with st.form("visit_form", clear_on_submit=True):
                col1, col2, col3 = st.columns(3)
                with col1:
                    direccion = st.text_input("Ciudad de la visita")
                with col2:
                    fecha_visita = st.date_input("Fecha", value=datetime.today())
                with col3:
                    if fecha_visita.weekday() < 4:
                        franja = st.selectbox("Franja Horaria", ["Jornada Mañana (8-14h)", "Jornada Tarde (15-17h)"])
                    else:
                        franja = st.selectbox("Franja Horaria", ["Primera Mitad Mañana (8-11:30h)", "Segunda Mitad Mañana (11:30-15h)"])
                observaciones = st.text_area("Observaciones (opcional)")
                if st.form_submit_button("Guardar Visita", use_container_width=True, type="primary"):
                    if direccion:
                        geolocator = Nominatim(user_agent=f"planificador_visitas_{st.session_state.get('usuario_id', 'default')}")
                        try:
                            location = geolocator.geocode(f"{direccion}, Spain")
                            if location:
                                cursor.execute(
                                    "INSERT INTO visitas (usuario_id, direccion_texto, lat, lon, fecha, franja_horaria, observaciones) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                    (st.session_state['usuario_id'], direccion, location.latitude, location.longitude, fecha_visita.strftime("%Y-%m-%d"), franja, observaciones)
                                )
                                conn.commit()
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
        col_filtros, col_toggle = st.columns([3, 1])
        with col_filtros:
            selected_date = st.date_input("Selecciona una fecha para centrar la vista semanal", value=datetime.today(), label_visibility="collapsed")
        with col_toggle:
            vision_global = st.toggle("Visión Global (ver todos)", help="Activa para ver las visitas de todos los coordinadores.")

        coordinadores_df = pd.read_sql_query("SELECT nombre_completo FROM usuarios", conn)
        coordinadores = coordinadores_df['nombre_completo'].unique()
        colores_mapa = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue']
        color_map = {coord: colores_mapa[i % len(colores_mapa)] for i, coord in enumerate(coordinadores)}

        query_base = "SELECT v.id, v.fecha, v.franja_horaria, v.direccion_texto, v.observaciones, v.lat, v.lon, u.nombre_completo, u.id as id_usuario FROM visitas v JOIN usuarios u ON v.usuario_id = u.id ORDER BY v.fecha"
        all_visits_df = pd.read_sql_query(query_base, conn)
        if not all_visits_df.empty:
            all_visits_df['fecha'] = pd.to_datetime(all_visits_df['fecha'])

        filtered_visits_df = all_visits_df if vision_global else all_visits_df[all_visits_df['id_usuario'] == st.session_state['usuario_id']]

        # --- PESTAÑAS DE VISUALIZACIÓN ---
        tab_semanal, tab_calendario, tab_gestion = st.tabs(["🗓️ Visión Semanal", "📅 Vista Calendario", "✏️ Gestionar Mis Visitas"])

        with tab_semanal:
            start_of_week = selected_date - timedelta(days=selected_date.weekday())
            end_of_week = start_of_week + timedelta(days=6)
            st.caption(f"Mostrando semana del **{start_of_week.strftime('%d/%m/%Y')}** al **{end_of_week.strftime('%d/%m/%Y')}**")
            weekly_visits_df = filtered_visits_df[(filtered_visits_df['fecha'].dt.date >= start_of_week) & (filtered_visits_df['fecha'].dt.date <= end_of_week)]
            if not weekly_visits_df.empty:
                display_cols = ['fecha', 'franja_horaria', 'direccion_texto', 'nombre_completo', 'observaciones']
                df_display = weekly_visits_df[display_cols].copy()
                df_display['fecha'] = df_display['fecha'].dt.strftime('%d/%m/%Y')
                st.dataframe(df_display, use_container_width=True, hide_index=True)
                map_data = weekly_visits_df.dropna(subset=['lat', 'lon'])
                if not map_data.empty:
                    st.subheader("Mapa de Visitas de la Semana")
                    map_center = [map_data['lat'].mean(), map_data['lon'].mean()]
                    m = folium.Map(location=map_center, zoom_start=8)
                    for _, row in map_data.iterrows():
                        popup_text = f"<b>{row['nombre_completo']}</b><br>{row['direccion_texto']}<br>{row['fecha'].strftime('%d/%m/%Y')}"
                        
                        # --- INICIO DE LA LÓGICA PARA ICONO PERSONALIZADO ---
                        # Comprobamos si el nombre del coordinador contiene 'martin' (ignorando mayúsculas)
                        if 'martin' in row['nombre_completo'].lower():
                            # Si es Martín, usamos un icono especial de escudo
                            marker_icon = folium.Icon(color='darkblue', icon='shield', prefix='fa')
                        else:
                            # Para el resto de usuarios, usamos el icono por defecto
                            marker_icon = folium.Icon(color=color_map.get(row['nombre_completo'], 'gray'), icon='briefcase')
                        # --- FIN DE LA LÓGICA ---
                        
                        # Usamos la variable 'marker_icon' que acabamos de definir
                        folium.Marker(
                            location=[row['lat'], row['lon']], 
                            popup=folium.Popup(popup_text, max_width=300), 
                            tooltip=row['direccion_texto'], 
                            icon=marker_icon
                        ).add_to(m)
                        
                    st_folium(m, width=725, height=400)
            else:
                st.info("No hay visitas planificadas para esta semana.")

        with tab_calendario:
            today = datetime.today()
            festivos = get_national_holidays(years=today.year)
            festivos.update(get_national_holidays(years=today.year + 1))
            
            calendar_events = []

            for date, name in festivos.items():
                calendar_events.append({"title": f"🎉 {name}", "start": str(date), "end": str(date), "allDay": True, "color": "#808080", "display": "background"})

            if not filtered_visits_df.empty:
                for _, row in filtered_visits_df.iterrows():
                    start_dt, end_dt = map_franja_to_time(row['fecha'], row['franja_horaria'])
                    event_title = f"{row['nombre_completo']}\n📍 {row['direccion_texto']}\n🕒 {row['franja_horaria']}"
                    calendar_events.append({
                        "title": event_title,
                        "color": color_map.get(row['nombre_completo'], 'gray'),
                        "start": start_dt.isoformat(),
                        "end": end_dt.isoformat(),
                    })
            
            calendar_options = {
                "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek,timeGridDay"},
                "initialView": "timeGridWeek",
                "locale": "es",
                "slotMinTime": "07:00:00",
                "slotMaxTime": "19:00:00",
                "allDaySlot": False,
                "firstDay": 1, 
                "hiddenDays": [0],
            }
            
            custom_css = """
                .fc-event-main-frame {
                    white-space: pre-wrap;
                }
                .fc-view-harness {
                    min-height: 600px;
                }
            """
            
            st.caption("📝 Las visitas se muestran como bloques de tiempo. Los días festivos aparecen con un fondo gris.")
            calendar(events=calendar_events, options=calendar_options, custom_css=custom_css, key="calendar")

        with tab_gestion:
            st.subheader("Gestionar Mis Próximas Visitas")
            my_visits_df = all_visits_df[(all_visits_df['id_usuario'] == st.session_state['usuario_id']) & (all_visits_df['fecha'].dt.date >= datetime.today().date())].sort_values(by='fecha')
            if my_visits_df.empty:
                st.info("No tienes ninguna visita futura programada.")
            else:
                for _, visit in my_visits_df.iterrows():
                    with st.container(border=True):
                        col1_gest, col2_gest = st.columns([4, 1])
                        with col1_gest:
                            st.write(f"**{visit['fecha'].strftime('%d/%m/%Y')}** - {visit['direccion_texto']}")
                            st.caption(f"Franja: {visit['franja_horaria']}")
                        with col2_gest:
                            if st.button("🗑️", key=f"del_{visit['id']}", help="Eliminar visita"):
                                cursor.execute("DELETE FROM visitas WHERE id = ?", (visit['id'],))
                                conn.commit()
                                st.rerun()
    finally:
        if conn:
            conn.close()