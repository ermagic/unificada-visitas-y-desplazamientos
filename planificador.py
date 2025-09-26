# Fichero: planificador.py (Versión con eliminación de visitas e iconos personalizados)
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
import re
from geopy.geocoders import Nominatim
from database import supabase
import folium
from folium.features import DivIcon # Importar DivIcon
from streamlit_folium import st_folium
from streamlit_calendar import calendar

# --- CONSTANTES ---
HORAS_LUNES_JUEVES = ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "15:00-16:00", "16:00-17:00", "08:00-10:00", "10:00-12:00", "12:00-14:00", "15:00-17:00"]
HORAS_VIERNES = ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "08:00-10:00", "10:00-12:00", "12:00-14:00"]

# --- INICIO CORRECCIÓN: Función para obtener iniciales ---
def get_initials(full_name: str) -> str:
    """Extrae las iniciales de un nombre completo."""
    if not full_name or not isinstance(full_name, str):
        return "??"
    parts = full_name.split()
    if len(parts) > 1:
        return (parts[0][0] + parts[-1][0]).upper()
    elif len(parts) == 1 and len(parts[0]) > 1:
        return (parts[0][0] + parts[0][1]).upper()
    elif len(parts) == 1:
        return parts[0][0].upper()
    return "??"
# --- FIN CORRECCIÓN ---

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
    if not supabase: st.error("Sin conexión a base de datos."); st.stop()

    rol_usuario = st.session_state.get('rol', 'coordinador')
    planificar_tab_title = "✍️ Gestionar Visitas" if rol_usuario in ['supervisor', 'admin'] else "✍️ Planificar Mis Visitas"

    tab_global, tab_planificar = st.tabs(["🌍 Vista Global", planificar_tab_title])

    with tab_global:
        st.subheader("Panel de Control de Visitas de la Semana")
        
        today = date.today()
        start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
        cal_date = st.date_input("Ver semana", value=start_of_next_week, format="DD/MM/YYYY", key="cal_date")
        
        start_cal, end_cal = cal_date - timedelta(days=cal_date.weekday()), cal_date + timedelta(days=6-cal_date.weekday())

        response = supabase.table('visitas').select('*, usuario:usuario_id(nombre_completo)').gte('fecha', start_cal).lte('fecha', end_cal).execute()
        df_all = pd.DataFrame(response.data)
        
        if df_all.empty:
            st.info("Sin visitas programadas para esta semana.")
        else:
            df_all['Coordinador'] = df_all['usuario'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'Desconocido')
            df_all.rename(columns={'equipo': 'Equipo', 'direccion_texto': 'Ubicación', 'observaciones': 'Observaciones'}, inplace=True)
            
            def get_assignee(row):
                if row['status'] == 'Asignada a Supervisor':
                    return f"Martín / {row['Coordinador']}"
                return row['Coordinador']
            df_all['Asignado a'] = df_all.apply(get_assignee, axis=1)

            st.markdown("#### Tabla de Visitas")
            df_all['Fecha Visita'] = pd.to_datetime(df_all['fecha_asignada'].fillna(df_all['fecha'])).dt.strftime('%d/%m/%Y')
            df_all['Hora Visita'] = df_all['hora_asignada'].fillna(df_all['franja_horaria'])

            df_display = df_all[['Asignado a', 'Equipo', 'Ubicación', 'Fecha Visita', 'Hora Visita', 'Observaciones']]
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("🗺️ Mapa y 🗓️ Calendario de la Semana")
            df_mapa = df_all.dropna(subset=['lat', 'lon']).copy()
            
            if not df_mapa.empty:
                m = folium.Map()
                coords_counter = {}
                for _, row in df_mapa.iterrows():
                    original_coords = (row['lat'], row['lon'])
                    offset_count = coords_counter.get(original_coords, 0)
                    lat, lon = row['lat'] + 0.0001 * offset_count, row['lon'] + 0.0001 * offset_count
                    coords_counter[original_coords] = offset_count + 1

                    popup_html = f"<b>Asignado a:</b> {row['Asignado a']}<br><b>Equipo:</b> {row['Equipo']}<br><b>Ubicación:</b> {row['Ubicación']}"
                    
                    # --- INICIO CORRECCIÓN: Lógica de iconos dinámicos ---
                    if row['status'] == 'Asignada a Supervisor':
                        # Icono de detective para el supervisor
                        icon = folium.Icon(color='darkpurple', icon='user-secret', prefix='fa')
                    else:
                        # Icono con iniciales para el coordinador
                        initials = get_initials(row['Coordinador'])
                        icon_html = f'<div style="font-family: Arial, sans-serif; font-size: 12px; font-weight: bold; color: white; background-color: #0078A8; border-radius: 50%; width: 25px; height: 25px; text-align: center; line-height: 25px; border: 1px solid white;">{initials}</div>'
                        icon = DivIcon(html=icon_html)
                    
                    folium.Marker(
                        [lat, lon], 
                        popup=folium.Popup(popup_html, max_width=300), 
                        icon=icon
                    ).add_to(m)
                    # --- FIN CORRECCIÓN ---
                
                sw, ne = df_mapa[['lat', 'lon']].min().values.tolist(), df_mapa[['lat', 'lon']].max().values.tolist()
                m.fit_bounds([sw, ne])
                st_folium(m, use_container_width=True, height=500)
            else: 
                st.info("No hay visitas con coordenadas para mostrar en el mapa.")
            
            events = []
            for _, r in df_all.iterrows():
                titulo = f"{r['Asignado a']} - {r['Equipo']}"
                color = 'darkpurple' if r['status'] == 'Asignada a Supervisor' else 'lightblue'
                start, end = None, None
                if pd.notna(r.get('fecha_asignada')) and pd.notna(r.get('hora_asignada')) and r['status'] == 'Asignada a Supervisor':
                    hora_match = re.search(r'^(\d{2}:\d{2})', str(r['hora_asignada']))
                    if hora_match:
                        try:
                            start = datetime.combine(pd.to_datetime(r['fecha_asignada']).date(), datetime.strptime(hora_match.group(1), '%H:%M').time())
                            end = start + timedelta(minutes=45)
                        except (ValueError, TypeError): continue
                else:
                    horas = re.findall(r'(\d{2}:\d{2})', r['franja_horaria'] or '')
                    if len(horas) == 2:
                        try:
                            fecha_evento = pd.to_datetime(r['fecha']).date()
                            start = datetime.combine(fecha_evento, datetime.strptime(horas[0], '%H:%M').time())
                            end = datetime.combine(fecha_evento, datetime.strptime(horas[1], '%H:%M').time())
                        except ValueError: continue
                if start and end:
                    events.append({"title": titulo, "start": start.isoformat(), "end": end.isoformat(), "color": color, "textColor": "white"})
            
            calendar(events=events, options={"headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek"}, "initialView": "timeGridWeek", "locale": "es", "initialDate": start_cal.isoformat(), "slotMinTime": "08:00:00", "slotMaxTime": "18:00:00"}, key=f"cal_{start_cal}")

    with tab_planificar:
        st.subheader("Añade o Edita Tus Visitas")
        
        today_plan = date.today()
        start_of_next_week_plan = today_plan + timedelta(days=-today_plan.weekday(), weeks=1)
        selected_date = st.date_input("Selecciona una semana para planificar", value=start_of_next_week_plan, format="DD/MM/YYYY", key="date_plan")
        start, end = selected_date - timedelta(days=selected_date.weekday()), selected_date + timedelta(days=6-selected_date.weekday())
        
        if rol_usuario in ['supervisor', 'admin']:
            assigned_res = supabase.table('visitas').select('*').eq('status', 'Asignada a Supervisor').gte('fecha_asignada', start).lte('fecha_asignada', end).execute()
            own_res = supabase.table('visitas').select('*').eq('usuario_id', st.session_state['usuario_id']).gte('fecha', start).lte('fecha', end).execute()
            df_assigned = pd.DataFrame(assigned_res.data)
            df_own = pd.DataFrame(own_res.data)
            df = pd.concat([df_assigned, df_own]).drop_duplicates(subset=['id'], keep='first').reset_index(drop=True)
        else:
            response = supabase.table('visitas').select('*').eq('usuario_id', st.session_state['usuario_id']).gte('fecha', start).lte('fecha', end).execute()
            df = pd.DataFrame(response.data)
        
        if not df.empty:
            for col in ['fecha', 'fecha_asignada']:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

        if rol_usuario in ['supervisor', 'admin']:
            column_config = {
                "id": None, "usuario_id": None, "lat": None, "lon": None, "created_at": None, "id_visita_original": None,
                "fecha": st.column_config.DateColumn("Fecha Propuesta", format="DD/MM/YYYY"),
                "franja_horaria": st.column_config.SelectboxColumn("Franja Propuesta", options=sorted(set(HORAS_LUNES_JUEVES + HORAS_VIERNES))),
                "direccion_texto": st.column_config.TextColumn("Ubicación", required=True, width="medium"),
                "equipo": st.column_config.TextColumn("Equipo", required=True),
                "observaciones": st.column_config.TextColumn("Observaciones"),
                "status": st.column_config.SelectboxColumn("Estado", options=['Propuesta', 'Asignada a Supervisor'], required=True),
                "fecha_asignada": st.column_config.DateColumn("Fecha Asignada", format="DD/MM/YYYY"),
                "hora_asignada": st.column_config.TextColumn("Hora Asignada (HH:MM)"),
            }
        else:
            column_config = {
                "id": None, "usuario_id": None, "lat": None, "lon": None, "created_at": None, "status": None,
                "id_visita_original": None, "fecha_asignada": None, "hora_asignada": None,
                "fecha": st.column_config.DateColumn("Fecha", min_value=start, max_value=end, required=True, format="DD/MM/YYYY"),
                "franja_horaria": st.column_config.SelectboxColumn("Franja", options=sorted(set(HORAS_LUNES_JUEVES + HORAS_VIERNES)), required=True),
                "direccion_texto": st.column_config.TextColumn("Ubicación", required=True),
                "equipo": st.column_config.TextColumn("Equipo", required=True),
                "observaciones": st.column_config.TextColumn("Observaciones")
            }
        
        edited_df = st.data_editor(
            df, column_config=column_config, num_rows="dynamic", use_container_width=True, key=f"editor_{start}"
        )

        if st.button("💾 Guardar Cambios", type="primary", use_container_width=True):
            with st.spinner("Guardando..."):
                
                # --- INICIO CORRECCIÓN: Lógica para detectar y ejecutar eliminaciones ---
                original_ids = set(df['id'].dropna())
                edited_ids = set(edited_df['id'].dropna())
                ids_to_delete = original_ids - edited_ids

                for visit_id in ids_to_delete:
                    try:
                        supabase.table('visitas').delete().eq('id', int(visit_id)).execute()
                        st.toast(f"Visita {visit_id} eliminada.")
                    except Exception as e:
                        st.error(f"Error eliminando visita {visit_id}: {e}")
                # --- FIN CORRECCIÓN ---

                for _, row in edited_df.iterrows():
                    if pd.isna(row.get('direccion_texto')) or pd.isna(row.get('equipo')): continue
                    
                    lat, lon = geocode_address(row['direccion_texto'])
                    
                    data_to_upsert = {
                        'direccion_texto': row['direccion_texto'], 'equipo': row['equipo'],
                        'observaciones': str(row.get('observaciones') or ''), 'lat': lat, 'lon': lon,
                    }

                    if rol_usuario in ['supervisor', 'admin']:
                        data_to_upsert['status'] = row.get('status', 'Propuesta')
                        data_to_upsert['fecha_asignada'] = str(row['fecha_asignada']) if pd.notna(row.get('fecha_asignada')) else None
                        data_to_upsert['hora_asignada'] = row['hora_asignada'] if pd.notna(row.get('hora_asignada')) else None
                        data_to_upsert['fecha'] = str(row['fecha']) if pd.notna(row.get('fecha')) else None
                        data_to_upsert['franja_horaria'] = row['franja_horaria'] if pd.notna(row.get('franja_horaria')) else None
                    else:
                        data_to_upsert['status'] = 'Propuesta'
                        data_to_upsert['fecha'] = str(row['fecha']) if pd.notna(row.get('fecha')) else None
                        data_to_upsert['franja_horaria'] = row['franja_horaria'] if pd.notna(row.get('franja_horaria')) else None

                    if pd.isna(row.get('id')) or row['id'] == '':
                        data_to_upsert['usuario_id'] = st.session_state['usuario_id']

                    if pd.notna(row.get('id')) and row['id'] != '':
                        supabase.table('visitas').update(data_to_upsert).eq('id', int(row['id'])).execute()
                    else:
                        supabase.table('visitas').insert(data_to_upsert).execute()

            st.success("¡Cambios guardados correctamente!")
            st.rerun()