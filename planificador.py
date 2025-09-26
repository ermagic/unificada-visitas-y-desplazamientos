# Fichero: planificador.py (Versión con todas las mejoras integradas)
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
import re
from geopy.geocoders import Nominatim
from database import supabase
import folium
from folium.features import DivIcon
from streamlit_folium import st_folium
from streamlit_calendar import calendar

# --- CONSTANTES ---
HORAS_LUNES_JUEVES = ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "15:00-16:00", "16:00-17:00", "08:00-10:00", "10:00-12:00", "12:00-14:00", "15:00-17:00"]
HORAS_VIERNES = ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "08:00-10:00", "10:00-12:00", "12:00-14:00"]
CATALONIA_CENTER = [41.8795, 1.7887]

def get_initials(full_name: str) -> str:
    if not full_name or not isinstance(full_name, str): return "??"
    parts = full_name.split()
    if len(parts) > 1: return (parts[0][0] + parts[-1][0]).upper()
    elif len(parts) == 1 and len(parts[0]) > 1: return (parts[0][0] + parts[0][1]).upper()
    elif len(parts) == 1: return parts[0][0].upper()
    return "??"

@st.cache_data(ttl=60*60*24)
def geocode_address(address: str):
    if not address or pd.isna(address): return None, None
    try:
        geolocator = Nominatim(user_agent="streamlit_app_planner_v18")
        location = geolocator.geocode(address + ", Catalunya", timeout=10)
        if location: return location.latitude, location.longitude
        return None, None
    except Exception: return None, None

def mostrar_planificador():
    st.header("Planificador de Visitas 🗓️")
    rol_usuario = st.session_state.get('rol', 'coordinador')
    planificar_tab_title = "✍️ Gestionar Visitas" if rol_usuario in ['supervisor', 'admin'] else "✍️ Planificar Mis Visitas"
    tab_global, tab_planificar = st.tabs(["🌍 Vista Global", planificar_tab_title])

    with tab_global:
        st.subheader("Panel de Control de Visitas de la Semana")
        today = date.today()
        start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
        cal_date = st.date_input("Ver semana", value=start_of_next_week, format="DD/MM/YYYY", key="cal_date")
        
        ver_solo_mis_visitas = False
        if rol_usuario == 'coordinador':
            ver_solo_mis_visitas = st.checkbox("Ver solo mis visitas")
        
        start_cal, end_cal = cal_date - timedelta(days=cal_date.weekday()), cal_date + timedelta(days=6-cal_date.weekday())
        response = supabase.table('visitas').select('*, usuario:usuario_id(nombre_completo, id)').gte('fecha', start_cal).lte('fecha', end_cal).execute()
        df_all = pd.DataFrame(response.data)
        
        if df_all.empty:
            st.info("Sin visitas programadas para esta semana.")
        else:
            df_all['usuario_id_fk'] = df_all['usuario'].apply(lambda x: x['id'] if isinstance(x, dict) else None)
            df_all['Coordinador'] = df_all['usuario'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'Desconocido')
            df_all.rename(columns={'equipo': 'Equipo', 'direccion_texto': 'Ubicación', 'observaciones': 'Observaciones'}, inplace=True)
            
            if ver_solo_mis_visitas:
                df_all = df_all[df_all['usuario_id_fk'] == st.session_state['usuario_id']].copy()

            coordinadores_en_vista = sorted([c for c in df_all['Coordinador'].unique() if c != 'Desconocido'])
            colores_base = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
            color_map = {coord: colores_base[i % len(colores_base)] for i, coord in enumerate(coordinadores_en_vista)}
            color_map['Desconocido'] = '#808080'
            
            def get_assignee(row):
                if row['status'] == 'Asignada a Supervisor': return f"Martín / {row['Coordinador']}"
                return row['Coordinador']
            df_all['Asignado a'] = df_all.apply(get_assignee, axis=1)

            st.markdown("#### Tabla de Visitas")
            st.dataframe(df_all[['Asignado a', 'Equipo', 'Ubicación', 'fecha', 'franja_horaria', 'Observaciones']], use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("🗺️ Mapa y 🗓️ Calendario de la Semana")
            df_mapa = df_all.dropna(subset=['lat', 'lon']).copy()
            
            m = folium.Map(location=CATALONIA_CENTER, zoom_start=8)

            if not df_mapa.empty:
                for _, row in df_mapa.iterrows():
                    popup_html = f"<b>Asignado a:</b> {row['Asignado a']}<br><b>Equipo:</b> {row['Equipo']}<br><b>Ubicación:</b> {row['Ubicación']}"
                    
                    if row['status'] == 'Asignada a Supervisor':
                        icon = folium.Icon(color='darkpurple', icon='user-secret', prefix='fa')
                    else:
                        bg_color = color_map.get(row['Coordinador'])
                        initials = get_initials(row['Coordinador'])
                        icon_html = f'<div style="font-family: Arial, sans-serif; font-size: 12px; font-weight: bold; color: white; background-color: {bg_color}; border-radius: 50%; width: 25px; height: 25px; text-align: center; line-height: 25px; border: 1px solid white;">{initials}</div>'
                        icon = DivIcon(html=icon_html)
                    
                    folium.Marker([row['lat'], row['lon']], popup=folium.Popup(popup_html, max_width=300), icon=icon).add_to(m)
                
                sw = df_mapa[['lat', 'lon']].min().values.tolist()
                ne = df_mapa[['lat', 'lon']].max().values.tolist()
                if sw == ne:
                    m.location = sw
                    m.zoom_start = 13
                else:
                    m.fit_bounds([sw, ne])
            
            st_folium(m, use_container_width=True, height=500)
            
            events = []
            for _, r in df_all.iterrows():
                titulo = f"{r['Asignado a']} - {r['Equipo']}"
                if r['status'] == 'Asignada a Supervisor':
                    color = 'darkpurple'
                else:
                    color = color_map.get(r['Coordinador'])
                
                start, end = None, None
                horas = re.findall(r'(\d{2}:\d{2})', r['franja_horaria'] or '')
                if len(horas) == 2:
                    try:
                        fecha_evento = pd.to_datetime(r['fecha']).date()
                        start = datetime.combine(fecha_evento, datetime.strptime(horas[0], '%H:%M').time())
                        end = datetime.combine(fecha_evento, datetime.strptime(horas[1], '%H:%M').time())
                        events.append({"title": titulo, "start": start.isoformat(), "end": end.isoformat(), "color": color, "textColor": "white"})
                    except ValueError: continue

            calendar_css = ".fc-event-title { font-size: 0.8em !important; line-height: 1.2 !important; white-space: normal !important; padding: 2px !important; }"
            calendar(events=events, options={"headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek"}, "initialView": "timeGridWeek", "locale": "es", "initialDate": start_cal.isoformat()}, custom_css=calendar_css, key=f"cal_{start_cal}")

    with tab_planificar:
        today_plan = date.today()
        start_of_next_week_plan = today_plan + timedelta(days=-today.weekday(), weeks=1)
        selected_date = st.date_input("Selecciona una semana para planificar", value=start_of_next_week_plan, format="DD/MM/YYYY", key="date_plan")
        start, end = selected_date - timedelta(days=selected_date.weekday()), selected_date + timedelta(days=6-selected_date.weekday())

        with st.expander("➕ Añadir Nueva Visita"):
            with st.form("new_visit_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    new_fecha = st.date_input("Fecha", min_value=start, max_value=end)
                    new_poblacion = st.text_input("Población", placeholder="Ej: Cornellà de Llobregat")
                with col2:
                    franjas_disponibles = HORAS_VIERNES if new_fecha and new_fecha.weekday() == 4 else HORAS_LUNES_JUEVES
                    new_franja = st.selectbox("Franja Horaria", options=sorted(set(franjas_disponibles)))
                    new_equipo = st.text_input("Equipo", placeholder="Ej: FB45")
                new_observaciones = st.text_area("Observaciones (opcional)")
                submitted = st.form_submit_button("Añadir Visita", type="primary", use_container_width=True)
                if submitted:
                    if not new_poblacion or not new_equipo:
                        st.warning("Por favor, completa la población y el equipo.")
                    else:
                        with st.spinner("Geocodificando y guardando..."):
                            lat, lon = geocode_address(new_poblacion)
                            if lat is None:
                                st.error("No se pudo encontrar la población. Revisa que el nombre sea correcto.")
                            else:
                                res = supabase.table('visitas').select('id').ilike('direccion_texto', f"%{new_poblacion}%").limit(1).execute()
                                if not res.data:
                                    logro_data = {
                                        'usuario_id': st.session_state['usuario_id'],
                                        'logro_tipo': 'explorador',
                                        'fecha_logro': str(date.today()),
                                        'detalles': {'poblacion': new_poblacion}
                                    }
                                    supabase.table('logros').insert(logro_data).execute()
                                    st.balloons()
                                    st.success(f"¡Felicidades! Eres el primero en visitar {new_poblacion}. ¡Has ganado el logro 'Explorador'!")
                                
                                new_visit_data = {
                                    'usuario_id': st.session_state['usuario_id'], 'fecha': str(new_fecha),
                                    'franja_horaria': new_franja, 'direccion_texto': new_poblacion,
                                    'equipo': new_equipo, 'observaciones': new_observaciones,
                                    'lat': lat, 'lon': lon, 'status': 'Propuesta'
                                }
                                try:
                                    supabase.table('visitas').insert(new_visit_data).execute()
                                    st.success(f"¡Visita a '{new_poblacion}' añadida con éxito!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al guardar la visita: {e}")
        st.markdown("---")
        
        st.subheader("Tus Visitas Propuestas para esta Semana")
        response = supabase.table('visitas').select('*').eq(
            'usuario_id', st.session_state['usuario_id']
        ).gte('fecha', start).lte('fecha', end).order('fecha').execute()
        
        visitas_semana = response.data
        ayuda_ya_solicitada = any(v.get('ayuda_solicitada') for v in visitas_semana)

        if not visitas_semana:
            st.info("No tienes visitas propuestas para la semana seleccionada.")
        else:
            st.success("Puedes solicitar la ayuda de Martín para **una visita por semana**. Se incluirá de forma garantizada en su planificación.")
            
            for visita in visitas_semana:
                with st.container(border=True):
                    col1, col2, col3 = st.columns([2, 2, 1])
                    with col1:
                        st.markdown(f"**📍 {visita['direccion_texto']}**")
                        st.write(f"**🗓️ {visita['fecha']}** | 🕒 {visita['franja_horaria']}")
                    with col2:
                        st.write(f"**Equipo:** {visita['equipo']}")
                        st.caption(f"Obs: {visita['observaciones'] if visita['observaciones'] else 'Ninguna'}")

                    with col3:
                        if visita.get('ayuda_solicitada'):
                            if st.button("✔️ Ayuda Solicitada", key=f"cancel_{visita['id']}", type="primary", use_container_width=True, help="Cancelar la solicitud de ayuda"):
                                supabase.table('visitas').update({'ayuda_solicitada': False}).eq('id', visita['id']).execute()
                                st.rerun()
                        else:
                            if st.button("🙋 Pedir Ayuda a Martín", key=f"ask_{visita['id']}", use_container_width=True, disabled=ayuda_ya_solicitada, help="Solicitar que esta visita sea incluida en el plan de Martín"):
                                supabase.table('visitas').update({'ayuda_solicitada': True}).eq('id', visita['id']).execute()
                                st.rerun()