# Fichero: planificador.py (Versión con flujo de envío para Coordinador)
import streamlit as st
import pandas as pd
from datetime import timedelta, date, datetime
import re
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium
from folium.features import DivIcon
from streamlit_folium import st_folium
from streamlit_calendar import calendar
from database import supabase

# --- CONSTANTES Y FUNCIONES AUXILIARES (sin cambios) ---
HORAS_LUNES_JUEVES = ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "15:00-16:00", "16:00-17:00", "08:00-10:00", "10:00-12:00", "12:00-14:00", "15:00-17:00"]
HORAS_VIERNES = ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "08:00-10:00", "10:00-12:00", "12:00-14:00"]

@st.cache_data(ttl=60*60*24)
def geocode_address(address: str):
    if not address or pd.isna(address): return None, None
    try:
        geolocator = Nominatim(user_agent="streamlit_app_planner_v11") # User agent actualizado
        geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
        location = geocode(address + ", Catalunya", timeout=10)
        if location: return location.latitude, location.longitude
        return None, None
    except Exception: return None, None

def create_global_map(df, color_map):
    st.markdown("#### 🗺️ Mapa de Visitas")
    map_data = df.dropna(subset=['lat', 'lon'])
    
    if not map_data.empty:
        map_center = [41.8781, 1.7834]
        m = folium.Map(location=map_center, zoom_start=8)
        
        for _, row in map_data.iterrows():
            nombre = row['nombre_completo']
            franja = row['franja_horaria'] or ''
            
            ### MODIFICADO: Usa la fecha asignada si existe para el tooltip
            if pd.notna(row.get('fecha_asignada')):
                fecha_corta = pd.to_datetime(row['fecha_asignada']).strftime('%d/%m')
                fecha_popup = pd.to_datetime(row['fecha_asignada']).strftime('%d/%m/%Y')
                hora_popup = row.get('hora_asignada') or ''
                popup_html = f"<b>Ubicación:</b> {row['direccion_texto']}<br><b>Fecha Asignada:</b> {fecha_popup} <b>({hora_popup})</b><br><b>Asignado a:</b> Martín<br><b>Propuesto por:</b> {nombre}"
                tooltip_info = f"{row['direccion_texto']} ({fecha_corta} - Asignada)"
            else:
                fecha_corta = row['fecha'].strftime('%d/%m')
                fecha_popup = row['fecha'].strftime('%d/%m/%Y')
                popup_html = f"<b>Ubicación:</b> {row['direccion_texto']}<br><b>Fecha Propuesta:</b> {fecha_popup} <b>({franja})</b><br><b>Equipo:</b> {row['equipo']}<br><b>Usuario:</b> {nombre}"
                tooltip_info = f"{row['direccion_texto']} ({fecha_corta} - {franja})"

            if row['status'] == 'Asignada a Supervisor':
                icono = folium.Icon(color='black', icon='user-shield', prefix='fa')
            else:
                inicial = nombre[0].upper() if nombre else '?'
                color_fondo = color_map.get(nombre, 'gray')
                icono = DivIcon(icon_size=(30,30), icon_anchor=(15,30), html=f'<div style="font-size: 12pt; font-weight: bold; color: white; background-color: {color_fondo}; width: 30px; height: 30px; text-align: center; line-height: 30px; border-radius: 50%;">{inicial}</div>')

            folium.Marker(location=[row['lat'], row['lon']], popup=folium.Popup(popup_html, max_width=300), tooltip=tooltip_info, icon=icono).add_to(m)
            
        st_folium(m, width='100%', height=450)
    else:
        st.info("No hay visitas con coordenadas geográficas para mostrar en el mapa.")

def mostrar_planificador():
    st.header("Planificador de Visitas 🗓️")
    if not supabase: st.error("La conexión con la base de datos no está disponible."); st.stop()
    
    all_visits_response = supabase.table('visitas').select('*, usuarios(nombre_completo)').execute()
    all_visits_df = pd.DataFrame(all_visits_response.data)
    
    if not all_visits_df.empty:
        all_visits_df['nombre_completo'] = all_visits_df['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'N/A')
        all_visits_df.drop(columns=['usuarios'], inplace=True)
        all_visits_df['fecha'] = pd.to_datetime(all_visits_df['fecha'])
    
    coordinadores = all_visits_df[all_visits_df['status'] != 'Asignada a Supervisor']['nombre_completo'].unique()
    colores = ['blue', 'orange', 'purple', 'cadetblue', 'pink', 'lightgreen', 'red', 'gray', 'lightblue', 'darkred']
    color_map = {coordinador: colores[i % len(colores)] for i, coordinador in enumerate(coordinadores)}

    ### MODIFICADO ### Ligeramente cambiados los títulos de las pestañas
    tab_planificar, tab_global, tab_gestion = st.tabs(["✍️ 1. Planificar (Borrador)", "🌍 2. Vista Global (Calendario)", "👀 3. Mis Visitas (Seguimiento)"])

    with tab_planificar:
        st.subheader("Gestiona tus visitas propuestas (Borradores)")
        
        selected_date_plan = st.date_input("Selecciona una semana para planificar", value=date.today(), format="DD/MM/YYYY", key="date_plan")

        start_of_week = selected_date_plan - timedelta(days=selected_date_plan.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        st.info(f"Editando borradores para la semana del {start_of_week.strftime('%d/%m/%Y')} al {end_of_week.strftime('%d/%m/%Y')}")

        mis_visitas_res = supabase.table('visitas').select('*').eq('usuario_id', st.session_state['usuario_id']).eq('status', 'Propuesta').gte('fecha', start_of_week).lte('fecha', end_of_week).execute()
        df_propuestas_original = pd.DataFrame(mis_visitas_res.data)
        
        ### MODIFICADO: Corrección del bug de StreamlitAPIException ###
        if not df_propuestas_original.empty: 
            df_propuestas_original['fecha'] = pd.to_datetime(df_propuestas_original['fecha']).dt.date
        
        df_para_editar = df_propuestas_original.reindex(columns=['fecha', 'franja_horaria', 'direccion_texto', 'equipo', 'observaciones', 'id'])
        
        # Se asegura de que la columna 'fecha' tenga el tipo correcto incluso si el df está vacío
        df_para_editar['fecha'] = pd.to_datetime(df_para_editar['fecha']).dt.date

        st.markdown("Puedes añadir, editar o eliminar filas. **No olvides guardar los cambios.**")
        edited_df = st.data_editor(df_para_editar, num_rows="dynamic", column_order=['fecha', 'franja_horaria', 'direccion_texto', 'equipo', 'observaciones'],
            column_config={
                "id": None, "fecha": st.column_config.DateColumn("Fecha", min_value=start_of_week, max_value=end_of_week, required=True),
                "franja_horaria": st.column_config.SelectboxColumn("Franja Horaria", options=sorted(list(set(HORAS_LUNES_JUEVES + HORAS_VIERNES)))),
                "direccion_texto": st.column_config.TextColumn("Ubicación", required=True), "equipo": st.column_config.TextColumn("Equipo", required=True),
                "observaciones": st.column_config.TextColumn("Observaciones")}, key=f"editor_{start_of_week}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Guardar Cambios en Borradores", type="primary", use_container_width=True):
                with st.spinner("Guardando..."):
                    original_ids = set(df_propuestas_original['id'].dropna().tolist())
                    current_ids = set(edited_df['id'].dropna().tolist())
                    ids_to_delete = original_ids - current_ids
                    if ids_to_delete:
                        for visit_id in ids_to_delete: supabase.table('visitas').delete().eq('id', int(visit_id)).execute()
                    
                    for _, row in edited_df.iterrows():
                        if pd.isna(row['fecha']) or pd.isna(row['franja_horaria']) or pd.isna(row['direccion_texto']): continue
                        if row['fecha'].weekday() == 4 and row['franja_horaria'] not in HORAS_VIERNES: st.error(f"La franja '{row['franja_horaria']}' no es válida para un viernes. Fila ignorada."); continue
                        
                        lat, lon = geocode_address(row['direccion_texto'])
                        visita_data = {'usuario_id': st.session_state['usuario_id'], 'fecha': str(row['fecha']), 'franja_horaria': row['franja_horaria'], 'direccion_texto': row['direccion_texto'], 'equipo': row['equipo'], 'observaciones': row['observaciones'], 'status': 'Propuesta', 'lat': lat, 'lon': lon}
                        
                        if pd.notna(row['id']) and row['id'] in original_ids: supabase.table('visitas').update(visita_data).eq('id', int(row['id'])).execute()
                        else: supabase.table('visitas').insert(visita_data).execute()
                    
                    st.success("¡Borradores actualizados!"); st.rerun()

        ### NUEVO: Botón para finalizar y enviar planificación ###
        with col2:
            if st.button("✅ Enviar Planificación a Supervisor", use_container_width=True):
                with st.spinner("Enviando visitas para asignación..."):
                    # Buscamos todas las visitas en estado "Propuesta" para el usuario y la semana seleccionada
                    visitas_a_enviar_res = supabase.table('visitas').select('id').eq('usuario_id', st.session_state['usuario_id']).eq('status', 'Propuesta').gte('fecha', start_of_week).lte('fecha', end_of_week).execute()
                    visitas_a_enviar_df = pd.DataFrame(visitas_a_enviar_res.data)

                    if not visitas_a_enviar_df.empty:
                        ids_a_actualizar = visitas_a_enviar_df['id'].tolist()
                        # Actualizamos el estado de todas estas visitas
                        supabase.table('visitas').update({'status': 'Pendiente de Asignación'}).in_('id', ids_a_actualizar).execute()
                        st.success(f"¡Éxito! {len(ids_a_actualizar)} visitas han sido enviadas para su asignación.")
                        st.rerun()
                    else:
                        st.warning("No hay visitas en estado 'Borrador' para enviar en esta semana. Guarda los cambios primero.")
        
        st.markdown("---")
        if not all_visits_df.empty: create_global_map(all_visits_df, color_map)
        else: st.info("Aún no hay visitas para mostrar en el mapa.")

    with tab_global:
        st.subheader("Calendario de Visitas Global")
        selected_date_cal = st.date_input("Selecciona una fecha para ver su semana", value=date.today(), format="DD/MM/YYYY", key="date_cal")

        if selected_date_cal and not all_visits_df.empty:
            start_of_week_cal = selected_date_cal - timedelta(days=selected_date_cal.weekday())
            end_of_week_cal = start_of_week_cal + timedelta(days=6)
            st.info(f"Mostrando visitas para la semana del {start_of_week_cal.strftime('%d/%m/%Y')} al {end_of_week_cal.strftime('%d/%m/%Y')}")
            df_semana_filtrada = all_visits_df[(all_visits_df['fecha'].dt.date >= start_of_week_cal) & (all_visits_df['fecha'].dt.date <= end_of_week_cal)]

            if not df_semana_filtrada.empty:
                calendar_events = []
                for _, row in df_semana_filtrada.iterrows():
                    color = "black" if row['status'] == 'Asignada a Supervisor' else color_map.get(row['nombre_completo'], 'gray')
                    title = f"{row['nombre_completo']} - {row['equipo']}"
                    
                    if pd.notna(row.get('fecha_asignada')) and pd.notna(row.get('hora_asignada')):
                        start_dt = datetime.combine(pd.to_datetime(row['fecha_asignada']).date(), datetime.strptime(row['hora_asignada'], '%H:%M').time())
                        # Asumimos 1h de duración para visitas asignadas en el calendario
                        end_dt = start_dt + timedelta(hours=1) 
                    else:
                        franja = row.get('franja_horaria')
                        if not franja or not isinstance(franja, str): continue
                        horas = re.findall(r'(\d{2}:\d{2})', franja)
                        if len(horas) != 2: continue
                        start_time_str, end_time_str = horas
                        start_dt = datetime.combine(row['fecha'].date(), datetime.strptime(start_time_str, '%H:%M').time())
                        end_dt = datetime.combine(row['fecha'].date(), datetime.strptime(end_time_str, '%H:%M').time())
                    
                    calendar_events.append({"title": title, "start": start_dt.isoformat(), "end": end_dt.isoformat(), "color": color})
                
                calendar_options = {"headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek,listWeek"}, "initialView": "timeGridWeek", "locale": "es", "eventTextColor": "white", "initialDate": start_of_week_cal.isoformat(), "slotMinTime": "08:00:00", "slotMaxTime": "18:00:00"}
                calendar(events=calendar_events, options=calendar_options, key=f"cal_{start_of_week_cal}")
            else: st.warning("No hay visitas planificadas para la semana seleccionada.")
        else: st.warning("No hay ninguna visita planificada en el sistema.")
    
    ### MODIFICADO: Pestaña de gestión con seguimiento por estado ###
    with tab_gestion:
        st.subheader("Seguimiento de Mis Visitas")
        mis_visitas_res = supabase.table('visitas').select('*').eq('usuario_id', st.session_state['usuario_id']).order('fecha, franja_horaria', desc=False).execute()
        df_mis_visitas = pd.DataFrame(mis_visitas_res.data)
        
        if not df_mis_visitas.empty:
            df_mis_visitas['fecha'] = pd.to_datetime(df_mis_visitas['fecha']).dt.strftime('%d/%m/%Y')

            st.markdown("#### ✅ Asignadas al Supervisor")
            df_asignadas = df_mis_visitas[df_mis_visitas['status'] == 'Asignada a Supervisor']
            if not df_asignadas.empty:
                df_asignadas_show = df_asignadas[['fecha_asignada', 'hora_asignada', 'direccion_texto', 'equipo', 'observaciones']]
                df_asignadas_show.rename(columns={'fecha_asignada': 'Fecha Final', 'hora_asignada': 'Hora Final'}, inplace=True)
                st.dataframe(df_asignadas_show, use_container_width=True, hide_index=True)
            else:
                st.info("Ninguna de tus visitas ha sido asignada al supervisor todavía.")

            st.markdown("#### ⏳ Pendientes de Asignación")
            df_pendientes = df_mis_visitas[df_mis_visitas['status'] == 'Pendiente de Asignación']
            if not df_pendientes.empty:
                df_pendientes_show = df_pendientes[['fecha', 'franja_horaria', 'direccion_texto', 'equipo', 'observaciones']]
                st.dataframe(df_pendientes_show, use_container_width=True, hide_index=True)
            else:
                st.info("No has enviado ninguna visita para ser asignada.")

            st.markdown("#### ✍️ Borradores (Sin Enviar)")
            df_propuestas = df_mis_visitas[df_mis_visitas['status'] == 'Propuesta']
            if not df_propuestas.empty:
                df_propuestas_show = df_propuestas[['fecha', 'franja_horaria', 'direccion_texto', 'equipo', 'observaciones']]
                st.dataframe(df_propuestas_show, use_container_width=True, hide_index=True)
            else:
                st.info("No tienes ninguna visita guardada como borrador.")
        else:
            st.info("Aún no has planificado ninguna visita.")