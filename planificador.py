# Fichero: planificador.py (Versión final con edición/eliminación para coordinadores)
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
import re
import googlemaps
from database import supabase
import folium
from folium.features import DivIcon
from streamlit_folium import st_folium
from streamlit_calendar import calendar

# --- CONSTANTES ---
HORAS_LUNES_JUEVES = ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "15:00-16:00", "16:00-17:00", "08:00-10:00", "10:00-12:00", "12:00-14:00", "15:00-17:00"]
HORAS_VIERNES = ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "08:00-10:00", "10:00-12:00", "12:00-14:00"]
CATALONIA_CENTER = [41.8795, 1.7887]
CATALONIA_BOUNDS = {
    "northeast": {"lat": 42.86, "lng": 3.32},
    "southwest": {"lat": 40.52, "lng": 0.18},
}

def get_initials(full_name: str) -> str:
    if not full_name or not isinstance(full_name, str): return "??"
    parts = full_name.split()
    if len(parts) > 1: return (parts[0][0] + parts[-1][0]).upper()
    elif len(parts) == 1 and len(parts[0]) > 1: return (parts[0][0] + parts[0][1]).upper()
    elif len(parts) == 1: return parts[0][0].upper()
    return "??"

@st.cache_data(ttl=60*60*24)
def geocode_address(address: str):
    if not address or pd.isna(address): 
        return None, None, "La población no puede estar vacía."
    try:
        gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
        geocode_result = gmaps.geocode(address, region='ES', bounds=CATALONIA_BOUNDS)
        if geocode_result:
            lat = geocode_result[0]['geometry']['location']['lat']
            lon = geocode_result[0]['geometry']['location']['lng']
            return lat, lon, None
        else:
            return None, None, f"Google Maps no pudo encontrar la población '{address}'."
    except Exception as e:
        return None, None, f"Ha ocurrido un error con la API de Google Maps: {e}"

def mostrar_planificador():
    st.header("Planificador de Visitas 🗓️")
    rol_usuario = st.session_state.get('rol', 'coordinador')
    
    if 'editing_visit_id' not in st.session_state:
        st.session_state.editing_visit_id = None

    planificar_tab_title = "✍️ Gestionar Visitas" if rol_usuario in ['supervisor', 'admin'] else "✍️ Planificar Mis Visitas"
    tab_global, tab_planificar = st.tabs(["🌍 Vista Global", planificar_tab_title])

    with tab_global:
        # ... (código sin cambios)
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
            st.success("👍 No hay aún visitas planificadas para la semana seleccionada.")
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
                if sw != ne: m.fit_bounds([sw, ne])
            st_folium(m, use_container_width=True, height=500)
            events = []
            for _, r in df_all.iterrows():
                titulo = f"{r['Asignado a']} - {r['Equipo']}"
                color = 'darkpurple' if r['status'] == 'Asignada a Supervisor' else color_map.get(r['Coordinador'])
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
                # ... (código del formulario sin cambios)
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
                    if not new_poblacion or not new_equipo: st.warning("Por favor, completa la población y el equipo.")
                    else:
                        with st.spinner("Geocodificando y guardando..."):
                            lat, lon, error_msg = geocode_address(new_poblacion)
                            if error_msg:
                                st.error(error_msg)
                            else:
                                if not supabase.table('visitas').select('id').ilike('direccion_texto', f"%{new_poblacion}%").limit(1).execute().data:
                                    supabase.table('logros').insert({'usuario_id': st.session_state['usuario_id'], 'logro_tipo': 'explorador', 'fecha_logro': str(date.today()), 'detalles': {'poblacion': new_poblacion}}).execute()
                                    st.balloons(); st.success(f"¡Felicidades! Eres el primero en visitar {new_poblacion}. ¡Has ganado el logro 'Explorador'!")
                                supabase.table('visitas').insert({'usuario_id': st.session_state['usuario_id'], 'fecha': str(new_fecha), 'franja_horaria': new_franja, 'direccion_texto': new_poblacion, 'equipo': new_equipo, 'observaciones': new_observaciones, 'lat': lat, 'lon': lon, 'status': 'Propuesta'}).execute()
                                st.success(f"¡Visita a '{new_poblacion}' añadida con éxito!"); st.rerun()

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
            for visita in visitas_semana:
                # --- INICIO DE LA LÓGICA DE EDICIÓN PARA COORDINADOR ---
                if st.session_state.editing_visit_id == visita['id']:
                    with st.form(key=f"edit_coord_form_{visita['id']}"):
                        st.markdown(f"**Editando visita a: {visita['direccion_texto']}**")
                        
                        current_date = datetime.strptime(visita['fecha'], '%Y-%m-%d').date()
                        franjas = HORAS_VIERNES if current_date.weekday() == 4 else HORAS_LUNES_JUEVES
                        try:
                            current_franja_index = franjas.index(visita['franja_horaria'])
                        except ValueError:
                            current_franja_index = 0

                        new_fecha = st.date_input("Fecha", value=current_date, min_value=start, max_value=end)
                        new_franja = st.selectbox("Franja Horaria", options=franjas, index=current_franja_index)
                        new_equipo = st.text_input("Equipo", value=visita['equipo'])
                        new_obs = st.text_area("Observaciones", value=visita['observaciones'])

                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("💾 Guardar", use_container_width=True, type="primary"):
                            update_data = {
                                'fecha': str(new_fecha), 'franja_horaria': new_franja,
                                'equipo': new_equipo, 'observaciones': new_obs
                            }
                            supabase.table('visitas').update(update_data).eq('id', visita['id']).execute()
                            st.success("Visita actualizada.")
                            st.session_state.editing_visit_id = None
                            st.rerun()
                        if c2.form_submit_button("✖️ Cancelar", use_container_width=True):
                            st.session_state.editing_visit_id = None
                            st.rerun()
                else:
                    with st.container(border=True):
                        col1, col2, cols_botones = st.columns([2, 2, 2])
                        with col1:
                            st.markdown(f"**📍 {visita['direccion_texto']}**")
                            st.write(f"**🗓️ {visita['fecha']}** | 🕒 {visita['franja_horaria']}")
                        with col2:
                            st.write(f"**Equipo:** {visita['equipo']}")
                            st.caption(f"Obs: {visita['observaciones'] or 'Ninguna'}")
                        
                        with cols_botones:
                            # Contenedor para los 4 botones
                            b1, b2, b3, b4 = st.columns(4)
                            with b1:
                                if st.button("🙋", key=f"ask_{visita['id']}", help="Pedir Ayuda a Martín", disabled=ayuda_ya_solicitada, use_container_width=True):
                                    supabase.table('visitas').update({'ayuda_solicitada': True}).eq('id', visita['id']).execute(); st.rerun()
                            with b2:
                                if st.button("🤝", key=f"offer_{visita['id']}", help="Ofrecer al Mercado", use_container_width=True):
                                    supabase.table('visitas').update({'en_mercado': True}).eq('id', visita['id']).execute(); st.rerun()
                            with b3:
                                if st.button("✏️", key=f"edit_coord_{visita['id']}", help="Editar Visita", use_container_width=True):
                                    st.session_state.editing_visit_id = visita['id']
                                    st.rerun()
                            with b4:
                                if st.button("🗑️", key=f"del_coord_{visita['id']}", help="Eliminar Visita", use_container_width=True):
                                    supabase.table('visitas').delete().eq('id', visita['id']).execute()
                                    st.success("Visita eliminada.")
                                    st.rerun()

                            # Mostrar insignias si la visita está en el mercado o con ayuda solicitada
                            if visita.get('ayuda_solicitada'):
                                st.success("✔️ Ayuda Solicitada", icon="🙋")
                            if visita.get('en_mercado'):
                                st.info("✔️ En Mercado", icon="🤝")
                # --- FIN DE LA LÓGICA DE EDICIÓN ---

        if st.session_state.get('rol') in ['supervisor', 'admin']:
            st.markdown("---")
            st.subheader("📋 Mis Visitas Asignadas")
            # ... (código sin cambios)
            try:
                assigned_res = supabase.table('visitas').select('*, coordinador:usuario_id(nombre_completo)').eq('status', 'Asignada a Supervisor').order('fecha_asignada').execute()
                assigned_visits = assigned_res.data
                if not assigned_visits:
                    st.info("Actualmente no tienes ninguna visita asignada.")
                else:
                    for visita in assigned_visits:
                        if st.session_state.editing_visit_id == visita['id']:
                            edit_form = st.form(key=f"edit_form_{visita['id']}")
                            with edit_form:
                                st.markdown(f"**Editando visita a: {visita['direccion_texto']}**")
                                current_date = datetime.strptime(visita['fecha_asignada'], '%Y-%m-%d').date()
                                current_time = datetime.strptime(visita['hora_asignada'], '%H:%M:%S').time()
                                new_date = st.date_input("Nueva fecha", value=current_date)
                                new_time = st.time_input("Nueva hora", value=current_time)
                                col_save, col_cancel = st.columns(2)
                                submitted_save = col_save.form_submit_button("💾 Guardar Cambios", use_container_width=True, type="primary")
                                submitted_cancel = col_cancel.form_submit_button("✖️ Cancelar", use_container_width=True)
                            
                            if submitted_save:
                                update_data = {'fecha_asignada': new_date.strftime('%Y-%m-%d'), 'hora_asignada': new_time.strftime('%H:%M')}
                                supabase.table('visitas').update(update_data).eq('id', visita['id']).execute()
                                st.success("Visita actualizada con éxito.")
                                st.session_state.editing_visit_id = None
                                st.rerun()
                            if submitted_cancel:
                                st.session_state.editing_visit_id = None
                                st.rerun()
                        else:
                            with st.container(border=True):
                                coordinador_info = visita.get('coordinador', {})
                                coordinador_nombre = coordinador_info.get('nombre_completo', 'Desconocido') if isinstance(coordinador_info, dict) else 'Desconocido'
                                col1, col2, col3 = st.columns([3, 1, 1])
                                with col1:
                                    st.markdown(f"**📍 {visita['direccion_texto']}** (Equipo: *{visita['equipo']}*)")
                                    st.caption(f"Asignada para el **{visita['fecha_asignada']}** a las **{visita['hora_asignada']}h**. Proviene de: **{coordinador_nombre}**.")
                                with col2:
                                    if st.button("✏️ Editar", key=f"edit_{visita['id']}", use_container_width=True):
                                        st.session_state.editing_visit_id = visita['id']
                                        st.rerun()
                                with col3:
                                    if st.button("↩️ Devolver", key=f"devolver_{visita['id']}", use_container_width=True, help="Devolver la visita a su coordinador original"):
                                        update_data = {'status': 'Propuesta', 'fecha_asignada': None, 'hora_asignada': None}
                                        supabase.table('visitas').update(update_data).eq('id', visita['id']).execute()
                                        st.success(f"La visita a {visita['direccion_texto']} ha sido devuelta a {coordinador_nombre}.")
                                        st.rerun()
            except Exception as e:
                st.error(f"Error al cargar las visitas asignadas: {e}")