# Fichero: planificador.py (Versión con todas las mejoras de rol y UX)
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
STATUS_COLORS = {'Asignada a Supervisor': 'black', 'Asignada a Coordinador': 'blue', 'Pendiente de Asignación': 'orange', 'Propuesta': 'gray'}

@st.cache_data(ttl=60*60*24)
def geocode_address(address: str):
    if not address or pd.isna(address): return None, None
    try:
        geolocator = Nominatim(user_agent="streamlit_app_planner_v15")
        location = geolocator.geocode(address + ", Catalunya", timeout=10)
        if location: return location.latitude, location.longitude
        return None, None
    except Exception: return None, None

def mostrar_planificador():
    st.header("Planificador de Visitas 🗓️")
    if not supabase: st.error("Sin conexión a base de datos."); st.stop()

    if st.session_state['rol'] == 'coordinador':
        tab_planificar, tab_mis_visitas, tab_global = st.tabs(["✍️ Planificar", "✅ Mis Tareas", "🌍 Vista Global"])
    else: # Supervisor o Admin
        tab_global, tab_mis_visitas, tab_planificar = st.tabs(["🌍 Vista Global de Equipo", "✅ Mis Tareas Propuestas", "✍️ Planificar (Borradores)"])

    with tab_mis_visitas:
        st.subheader("Resumen de Visitas que Has Propuesto")
        response = supabase.table('visitas').select('*').eq('usuario_id', st.session_state['usuario_id']).order('fecha').execute()
        df_mis = pd.DataFrame(response.data)
        if df_mis.empty:
            st.info("No has propuesto ninguna visita.")
        else:
            df_mis['fecha_fmt'] = pd.to_datetime(df_mis['fecha']).dt.strftime('%d/%m/%Y')
            df_mis['fecha_asignada_fmt'] = pd.to_datetime(df_mis['fecha_asignada'], errors='coerce').dt.strftime('%d/%m/%Y')
            
            st.markdown("#### ⏳ Pendientes de Asignar por el Supervisor")
            pendientes = df_mis[df_mis['status'] == 'Pendiente de Asignación']
            if not pendientes.empty:
                for index, row in pendientes.iterrows():
                    cols = st.columns([4, 1])
                    with cols[0]:
                        st.info(f"**{row['fecha_fmt']}** | {row['direccion_texto']} | **Equipo:** {row['equipo']}")
                    with cols[1]:
                        if st.button("↩️ Retirar", key=f"retirar_{row['id']}", help="Devolver esta visita a borradores", use_container_width=True):
                            supabase.table('visitas').update({'status': 'Propuesta'}).eq('id', row['id']).execute()
                            st.success(f"Visita a {row['direccion_texto']} devuelta a borradores.")
                            st.rerun()
            else:
                st.write("No tienes visitas pendientes de asignación.")

            st.markdown("---")
            propias_asignadas = df_mis[df_mis['status'] == 'Asignada a Coordinador']
            if not propias_asignadas.empty:
                st.markdown("#### 📋 Mis Visitas Asignadas (Confirmadas para ti)")
                st.dataframe(propias_asignadas[['fecha_fmt', 'franja_horaria', 'direccion_texto', 'equipo']].rename(columns={'fecha_fmt': 'Fecha', 'franja_horaria': 'Franja', 'direccion_texto': 'Ubicación', 'equipo': 'Equipo'}), use_container_width=True, hide_index=True)

            asignadas_supervisor = df_mis[df_mis['status'] == 'Asignada a Supervisor']
            if not asignadas_supervisor.empty:
                st.markdown("#### ✅ Visitas Asignadas a Martín")
                st.dataframe(asignadas_supervisor[['fecha_asignada_fmt', 'hora_asignada', 'direccion_texto', 'equipo']].rename(columns={'fecha_asignada_fmt': 'Fecha Final', 'hora_asignada': 'Hora Final', 'direccion_texto': 'Ubicación', 'equipo': 'Equipo'}), use_container_width=True, hide_index=True)

    with tab_planificar:
        st.subheader("Gestiona tus visitas propuestas (Borradores)")
        if st.session_state['rol'] != 'coordinador':
            st.info("Esta sección es para que los coordinadores gestionen sus borradores de visitas.")
        
        selected_date = st.date_input("Selecciona una semana", value=date.today(), format="DD/MM/YYYY", key="date_plan")
        start, end = selected_date - timedelta(days=selected_date.weekday()), selected_date + timedelta(days=6-selected_date.weekday())
        response = supabase.table('visitas').select('*').eq('usuario_id', st.session_state['usuario_id']).eq('status', 'Propuesta').gte('fecha', start).lte('fecha', end).execute()
        df = pd.DataFrame(response.data)

        if df.empty:
            df = pd.DataFrame(columns=['id', 'fecha', 'franja_horaria', 'direccion_texto', 'equipo', 'observaciones'])
        else:
            df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce').dt.date
            df['id'] = pd.to_numeric(df['id'], errors='coerce')

        edited = st.data_editor(df, num_rows="dynamic", column_config={"id": None, "fecha": st.column_config.DateColumn("Fecha", min_value=start, max_value=end, required=True), "franja_horaria": st.column_config.SelectboxColumn("Franja", options=sorted(set(HORAS_LUNES_JUEVES + HORAS_VIERNES))), "direccion_texto": st.column_config.TextColumn("Ubicación", required=True), "equipo": st.column_config.TextColumn("Equipo", required=True), "observaciones": st.column_config.TextColumn("Observaciones")}, key=f"editor_{start}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Guardar cambios", type="primary", disabled=(edited.empty), use_container_width=True):
                for _, row in edited.iterrows():
                    if pd.isna(row['fecha']) or pd.isna(row['franja_horaria']) or pd.isna(row['direccion_texto']): continue
                    lat, lon = geocode_address(row['direccion_texto'])
                    data = {'usuario_id': st.session_state['usuario_id'], 'fecha': str(row['fecha']), 'franja_horaria': row['franja_horaria'], 'direccion_texto': row['direccion_texto'], 'equipo': row['equipo'], 'observaciones': str(row.get('observaciones') or ''), 'status': 'Propuesta', 'lat': lat, 'lon': lon }
                    if pd.notna(row['id']): supabase.table('visitas').update(data).eq('id', int(row['id'])).execute()
                    else: supabase.table('visitas').insert(data).execute()
                st.success("Borradores actualizados."); st.rerun()

        with col2:
            if st.button("✅ Enviar a supervisor", disabled=(edited.empty), use_container_width=True):
                ids = edited['id'].dropna().astype(int).tolist()
                if ids: supabase.table('visitas').update({'status': 'Pendiente de Asignación'}).in_('id', ids).execute(); st.success("Visitas enviadas."); st.rerun()

    with tab_global:
        st.subheader("Panel de Control de Visitas")
        cal_date = st.date_input("Ver semana", value=date.today(), format="DD/MM/YYYY", key="cal_date")
        start_cal, end_cal = cal_date - timedelta(days=cal_date.weekday()), cal_date + timedelta(days=6-cal_date.weekday())

        response = supabase.table('visitas').select('*, usuario:usuario_id(nombre_completo)').gte('fecha', start_cal).lte('fecha', end_cal).execute()
        df_all = pd.DataFrame(response.data)
        
        if df_all.empty:
            st.info("Sin visitas programadas para esta semana.")
        else:
            df_all['Coordinador'] = df_all['usuario'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'Desconocido')
            df_all.rename(columns={'status': 'Estado', 'equipo': 'Equipo', 'direccion_texto': 'Ubicación'}, inplace=True)
            
            df_filtered = df_all.copy()
            if st.session_state['rol'] != 'coordinador':
                st.markdown("#### Filtros")
                colf1, colf2 = st.columns(2)
                with colf1:
                    coordinadores = ['Todos'] + sorted(df_filtered['Coordinador'].unique().tolist())
                    selected_coord = st.selectbox('Filtrar por Coordinador:', coordinadores)
                    if selected_coord != 'Todos': df_filtered = df_filtered[df_filtered['Coordinador'] == selected_coord]
                with colf2:
                    status_list = ['Todos'] + sorted(df_filtered['Estado'].unique().tolist())
                    selected_status = st.selectbox('Filtrar por Estado:', status_list)
                    if selected_status != 'Todos': df_filtered = df_filtered[df_filtered['Estado'] == selected_status]
            
            st.markdown("#### Tabla de Visitas")
            st.dataframe(df_filtered[['Coordinador', 'Estado', 'Equipo', 'Ubicación', 'fecha', 'franja_horaria', 'fecha_asignada', 'hora_asignada']], use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("🗺️ Mapa y 🗓️ Calendario de la Semana")
            df_mapa = df_filtered.dropna(subset=['lat', 'lon']).copy()
            if not df_mapa.empty:
                map_center = [df_mapa['lat'].mean(), df_mapa['lon'].mean()]
                m = folium.Map(location=map_center, zoom_start=10)
                for _, row in df_mapa.iterrows():
                    color = STATUS_COLORS.get(row['Estado'], 'gray')
                    popup_html = f"<b>Coordinador:</b> {row['Coordinador']}<br><b>Equipo:</b> {row['Equipo']}<br><b>Estado:</b> {row['Estado']}"
                    folium.Marker([row['lat'], row['lon']], popup=folium.Popup(popup_html, max_width=300), icon=folium.Icon(color=color, icon='briefcase', prefix='fa')).add_to(m)
                st_folium(m, use_container_width=True, height=500)
            else: st.info("No hay visitas con coordenadas para mostrar en el mapa.")
            
            events = []
            for _, r in df_filtered.iterrows():
                titulo = f"{r['Coordinador']} - {r['Equipo']}"
                color = STATUS_COLORS.get(r['Estado'], 'gray')
                if pd.notna(r.get('fecha_asignada')) and pd.notna(r.get('hora_asignada')):
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