# Fichero: planificador.py (Versión con corrección de error en data_editor y centrado de mapa)
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
import re
from geopy.geocoders import Nominatim
from database import supabase
import folium
from streamlit_folium import st_folium
from streamlit_calendar import calendar

# --- CONSTANTES ---
HORAS_LUNES_JUEVES = ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "15:00-16:00", "16:00-17:00", "08:00-10:00", "10:00-12:00", "12:00-14:00", "15:00-17:00"]
HORAS_VIERNES = ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "08:00-10:00", "10:00-12:00", "12:00-14:00"]
STATUS_COLORS = {'Asignada a Supervisor': 'green', 'Propuesta': 'gray'}

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

    tab_global, tab_planificar = st.tabs(["🌍 Vista Global", "✍️ Planificar Mis Visitas"])

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
                # <-- CAMBIO: Lógica de centrado y zoom automático del mapa
                m = folium.Map()

                coords_counter = {}
                for _, row in df_mapa.iterrows():
                    original_coords = (row['lat'], row['lon'])
                    offset_count = coords_counter.get(original_coords, 0)
                    lat, lon = row['lat'] + 0.0001 * offset_count, row['lon'] + 0.0001 * offset_count
                    coords_counter[original_coords] = offset_count + 1

                    color = 'green' if row['status'] == 'Asignada a Supervisor' else 'blue'
                    popup_html = f"<b>Asignado a:</b> {row['Asignado a']}<br><b>Equipo:</b> {row['Equipo']}<br><b>Ubicación:</b> {row['Ubicación']}"
                    folium.Marker([lat, lon], popup=folium.Popup(popup_html, max_width=300), icon=folium.Icon(color=color, icon='briefcase', prefix='fa')).add_to(m)
                
                # Le decimos al mapa que se ajuste para mostrar todos los puntos
                sw = df_mapa[['lat', 'lon']].min().values.tolist()
                ne = df_mapa[['lat', 'lon']].max().values.tolist()
                m.fit_bounds([sw, ne])

                st_folium(m, use_container_width=True, height=500)
            else: 
                st.info("No hay visitas con coordenadas para mostrar en el mapa.")
            
            events = []
            for _, r in df_all.iterrows():
                titulo = f"{r['Asignado a']} - {r['Equipo']}"
                color = 'green' if r['status'] == 'Asignada a Supervisor' else 'blue'
                
                if pd.notna(r.get('fecha_asignada')) and pd.notna(r.get('hora_asignada')) and r['status'] == 'Asignada a Supervisor':
                    start = datetime.combine(pd.to_datetime(r['fecha_asignada']).date(), datetime.strptime(r['hora_asignada'], '%H:%M').time())
                    end = start + timedelta(minutes=45)
                else:
                    fecha_evento = pd.to_datetime(r['fecha']).date()
                    horas = re.findall(r'(\d{2}:\d{2})', r['franja_horaria'] or '')
                    if len(horas) != 2: continue
                    start = datetime.combine(fecha_evento, datetime.strptime(horas[0], '%H:%M').time())
                    end = datetime.combine(fecha_evento, datetime.strptime(horas[1], '%H:%M').time())
                events.append({"title": titulo, "start": start.isoformat(), "end": end.isoformat(), "color": color})
                
            calendar(events=events, options={"headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek"}, "initialView": "timeGridWeek", "locale": "es", "initialDate": start_cal.isoformat(), "slotMinTime": "08:00:00", "slotMaxTime": "18:00:00"}, key=f"cal_{start_cal}")

    with tab_planificar:
        st.subheader("Añade o Edita Tus Visitas")
        
        today_plan = date.today()
        start_of_next_week_plan = today_plan + timedelta(days=-today_plan.weekday(), weeks=1)
        selected_date = st.date_input("Selecciona una semana para planificar", value=start_of_next_week_plan, format="DD/MM/YYYY", key="date_plan")
        
        start, end = selected_date - timedelta(days=selected_date.weekday()), selected_date + timedelta(days=6-selected_date.weekday())
        
        response = supabase.table('visitas').select('*').eq('usuario_id', st.session_state['usuario_id']).gte('fecha', start).lte('fecha', end).execute()
        df = pd.DataFrame(response.data)

        # <-- CAMBIO: Convertimos la columna 'fecha' al tipo de dato correcto ANTES de pasarla al editor
        if not df.empty:
            df['fecha'] = pd.to_datetime(df['fecha']).dt.date

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
                for _, row in edited_df.iterrows():
                    if pd.isna(row['fecha']) or pd.isna(row['direccion_texto']) or pd.isna(row['equipo']): continue
                    
                    lat, lon = geocode_address(row['direccion_texto'])
                    
                    data_to_upsert = {
                        'fecha': str(row['fecha']), 'franja_horaria': row['franja_horaria'],
                        'direccion_texto': row['direccion_texto'], 'equipo': row['equipo'],
                        'observaciones': str(row.get('observaciones') or ''), 'lat': lat, 'lon': lon,
                        'usuario_id': st.session_state['usuario_id'], 'status': 'Propuesta'
                    }
                    
                    if pd.notna(row['id']) and row['id'] != '':
                        supabase.table('visitas').update(data_to_upsert).eq('id', int(row['id'])).execute()
                    else:
                        supabase.table('visitas').insert(data_to_upsert).execute()

            st.success("¡Visitas guardadas correctamente!")
            st.rerun()