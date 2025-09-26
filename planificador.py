# Fichero: planificador.py (Versión completa y estable para coordinadores)
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
import re
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium
from folium.features import DivIcon
from streamlit_folium import st_folium
from streamlit_calendar import calendar
from database import supabase

# --- CONSTANTES ---
HORAS_LUNES_JUEVES = ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "15:00-16:00", "16:00-17:00", "08:00-10:00", "10:00-12:00", "12:00-14:00", "15:00-17:00"]
HORAS_VIERNES = ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "08:00-10:00", "10:00-12:00", "12:00-14:00"]

@st.cache_data(ttl=60*60*24)
def geocode_address(address: str):
    if not address or pd.isna(address): return None, None
    try:
        geolocator = Nominatim(user_agent="streamlit_app_planner_v12")
        geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
        location = geocode(address + ", Catalunya", timeout=10)
        if location: return location.latitude, location.longitude
        return None, None
    except Exception: return None, None

def mostrar_planificador():
    st.header("Planificador de Visitas 🗓️")
    if not supabase: st.error("Sin conexión a base de datos."); st.stop()

    tab_mis_visitas, tab_planificar, tab_global = st.tabs(["✅ Mis Tareas", "✍️ Planificar", "🌍 Vista Global"])

    with tab_mis_visitas:
        st.subheader("Resumen de tus Visitas")

        response = supabase.table('visitas').select('*').eq('usuario_id', st.session_state['usuario_id']).order('fecha').execute()
        df_mis = pd.DataFrame(response.data)
        if df_mis.empty:
            st.info("No tienes visitas de ningún tipo.")
        else:
            df_mis['fecha_fmt'] = pd.to_datetime(df_mis['fecha']).dt.strftime('%d/%m/%Y')
            df_mis['fecha_asignada_fmt'] = pd.to_datetime(df_mis['fecha_asignada']).dt.strftime('%d/%m/%Y')
            
            # --- NUEVA SECCIÓN: Tareas asignadas al coordinador ---
            propias_asignadas = df_mis[df_mis['status'] == 'Asignada a Coordinador']
            if not propias_asignadas.empty:
                st.markdown("#### 📋 Mis Visitas Asignadas (Confirmadas)")
                st.dataframe(propias_asignadas[['fecha_fmt', 'franja_horaria', 'direccion_texto', 'equipo', 'observaciones']].rename(columns={
                    'fecha_fmt': 'Fecha', 'franja_horaria': 'Franja', 'direccion_texto': 'Ubicación', 'equipo': 'Equipo', 'observaciones': 'Obs.'
                }), use_container_width=True, hide_index=True)
            else:
                st.info("Aún no tienes visitas confirmadas asignadas a ti.")

            # --- Visitas asignadas al supervisor ---
            asignadas_supervisor = df_mis[df_mis['status'] == 'Asignada a Supervisor']
            if not asignadas_supervisor.empty:
                st.markdown("####  superviseur ✅ Asignadas a Martín (Supervisor)")
                st.dataframe(asignadas_supervisor[['fecha_asignada_fmt', 'hora_asignada', 'direccion_texto', 'equipo']].rename(columns={
                    'fecha_asignada_fmt': 'Fecha Final', 'hora_asignada': 'Hora Final', 'direccion_texto': 'Ubicación', 'equipo': 'Equipo'
                }), use_container_width=True, hide_index=True)
            
            # --- Visitas pendientes y borradores ---
            pendientes = df_mis[df_mis['status'] == 'Pendiente de Asignación']
            if not pendientes.empty:
                st.markdown("#### ⏳ Pendientes de asignar por el supervisor")
                st.dataframe(pendientes[['fecha_fmt', 'franja_horaria', 'direccion_texto', 'equipo']], use_container_width=True, hide_index=True)

            borradores = df_mis[df_mis['status'] == 'Propuesta']
            if not borradores.empty:
                st.markdown("#### ✍️ Tus borradores (no enviados)")
                st.dataframe(borradores[['fecha_fmt', 'franja_horaria', 'direccion_texto', 'equipo']], use_container_width=True, hide_index=True)


    with tab_planificar:
        st.subheader("Gestiona tus visitas propuestas (Borradores)")
        selected_date = st.date_input("Selecciona una semana", value=date.today(), format="DD/MM/YYYY", key="date_plan")
        start = selected_date - timedelta(days=selected_date.weekday())
        end = start + timedelta(days=6)

        response = supabase.table('visitas').select('*').eq('usuario_id', st.session_state['usuario_id']).eq('status', 'Propuesta').gte('fecha', start).lte('fecha', end).execute()
        df = pd.DataFrame(response.data)

        df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce').dt.date
        df['id'] = pd.to_numeric(df['id'], errors='coerce')

        edited = st.data_editor(
            df,
            num_rows="dynamic",
            column_config={
                "id": None,
                "fecha": st.column_config.DateColumn("Fecha", min_value=start, max_value=end, required=True),
                "franja_horaria": st.column_config.SelectboxColumn("Franja", options=sorted(set(HORAS_LUNES_JUEVES + HORAS_VIERNES))),
                "direccion_texto": st.column_config.TextColumn("Ubicación", required=True),
                "equipo": st.column_config.TextColumn("Equipo", required=True),
                "observaciones": st.column_config.TextColumn("Observaciones")
            },
            key=f"editor_{start}"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Guardar cambios", type="primary", disabled=edited.empty):
                for _, row in edited.iterrows():
                    if pd.isna(row['fecha']) or pd.isna(row['franja_horaria']) or pd.isna(row['direccion_texto']): continue
                    if row['fecha'].weekday() == 4 and row['franja_horaria'] not in HORAS_VIERNES: continue
                    lat, lon = geocode_address(row['direccion_texto'])
                    data = {
                        'usuario_id': st.session_state['usuario_id'], 'fecha': str(row['fecha']), 'franja_horaria': row['franja_horaria'],
                        'direccion_texto': row['direccion_texto'], 'equipo': row['equipo'], 'observaciones': row['observaciones'],
                        'status': 'Propuesta', 'lat': lat, 'lon': lon
                    }
                    if pd.notna(row['id']):
                        supabase.table('visitas').update(data).eq('id', int(row['id'])).execute()
                    else:
                        supabase.table('visitas').insert(data).execute()
                st.success("Borradores actualizados."); st.rerun()

        with col2:
            if st.button("✅ Enviar a supervisor", disabled=edited.empty):
                ids = edited['id'].dropna().tolist()
                if ids:
                    supabase.table('visitas').update({'status': 'Pendiente de Asignación'}).in_('id', ids).execute()
                    st.success("Visitas enviadas."); st.rerun()

    with tab_global:
        st.subheader("Calendario Global")
        cal_date = st.date_input("Ver semana", value=date.today(), format="DD/MM/YYYY", key="cal_date")
        start_cal = cal_date - timedelta(days=cal_date.weekday())
        end_cal = start_cal + timedelta(days=6)

        response = supabase.table('visitas').select('*, usuarios(nombre_completo)').gte('fecha', start_cal).lte('fecha', end_cal).execute()
        df_all = pd.DataFrame(response.data)
        if df_all.empty:
            st.info("Sin visitas esta semana.")
        else:
            df_all['fecha'] = pd.to_datetime(df_all['fecha']).dt.date
            df_all['nombre_completo'] = df_all['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'N/A')

            events = []
            for _, r in df_all.iterrows():
                titulo = f"{r['nombre_completo']} - {r['equipo']}"
                # --- LÓGICA DE COLORES MEJORADA ---
                status_colors = {
                    'Asignada a Supervisor': 'black',
                    'Asignada a Coordinador': 'blue',
                    'Pendiente de Asignación': 'orange',
                    'Propuesta': 'gray'
                }
                color = status_colors.get(r['status'], 'gray')

                if pd.notna(r.get('fecha_asignada')) and pd.notna(r.get('hora_asignada')):
                    start = datetime.combine(pd.to_datetime(r['fecha_asignada']).date(), datetime.strptime(r['hora_asignada'], '%H:%M').time())
                    end = start + timedelta(minutes=45)
                else:
                    horas = re.findall(r'(\d{2}:\d{2})', r['franja_horaria'] or '')
                    if len(horas) != 2: continue
                    start = datetime.combine(r['fecha'], datetime.strptime(horas[0], '%H:%M').time())
                    end = datetime.combine(r['fecha'], datetime.strptime(horas[1], '%H:%M').time())
                
                events.append({"title": titulo, "start": start.isoformat(), "end": end.isoformat(), "color": color, "extendedProps": {"status": r['status']}})

            calendar(events=events, options={
                "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek"},
                "initialView": "timeGridWeek", "locale": "es", "initialDate": start_cal.isoformat(),
                "slotMinTime": "08:00:00", "slotMaxTime": "18:00:00"
            }, key=f"cal_{start_cal}")
