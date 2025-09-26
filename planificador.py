# Fichero: planificador.py (Versión con Franja Horaria)
import streamlit as st
import pandas as pd
from datetime import timedelta, date, datetime
import re
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium
from streamlit_folium import st_folium
from streamlit_calendar import calendar
from database import supabase

# --- CONSTANTES Y FUNCIONES AUXILIARES ---

# Definimos las franjas horarias disponibles
HORAS_LUNES_JUEVES = [
    "08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00",
    "12:00-13:00", "13:00-14:00", "14:00-15:00", "15:00-16:00", "16:00-17:00",
    "08:00-10:00", "10:00-12:00", "12:00-14:00", "15:00-17:00"
]
HORAS_VIERNES = [
    "08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00",
    "12:00-13:00", "13:00-14:00", "14:00-15:00",
    "08:00-10:00", "10:00-12:00", "12:00-14:00"
]

@st.cache_data(ttl=60*60*24)
def geocode_address(address: str):
    """Convierte una dirección de texto a coordenadas (lat, lon)."""
    if not address or pd.isna(address):
        return None, None
    try:
        geolocator = Nominatim(user_agent="streamlit_app_planner_v8")
        geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
        location = geocode(address + ", Catalunya", timeout=10)
        if location:
            return location.latitude, location.longitude
        return None, None
    except Exception:
        return None, None

def create_global_map(df, color_map):
    """Crea y muestra un mapa de Folium con las visitas."""
    st.markdown("#### 🗺️ Mapa de Visitas")
    map_data = df.dropna(subset=['lat', 'lon'])
    
    if not map_data.empty:
        map_center = [41.8781, 1.7834]
        m = folium.Map(location=map_center, zoom_start=8)
        for _, row in map_data.iterrows():
            nombre = row['nombre_completo']
            franja = row['franja_horaria'] or ''
            if nombre == 'Martín':
                color_icono, icono_fa = 'black', 'user-shield'
            else:
                color_icono, icono_fa = color_map.get(nombre, 'gray'), 'user'
            popup_html = f"<b>Ubicación:</b> {row['direccion_texto']}<br><b>Fecha:</b> {row['fecha'].strftime('%d/%m/%Y')} {franja}<br><b>Equipo:</b> {row['equipo']}<br><b>Usuario:</b> {nombre}"
            folium.Marker(location=[row['lat'], row['lon']], popup=folium.Popup(popup_html, max_width=300), tooltip=f"{row['direccion_texto']} ({nombre})", icon=folium.Icon(color=color_icono, icon=icono_fa, prefix='fa')).add_to(m)
        st_folium(m, width='100%', height=450)
    else:
        st.info("No hay visitas con coordenadas geográficas para mostrar en el mapa.")

def mostrar_planificador():
    st.header("Planificador de Visitas 🗓️")
    if not supabase:
        st.error("La conexión con la base de datos no está disponible."); st.stop()
    
    all_visits_response = supabase.table('visitas').select('*, usuarios(nombre_completo)').execute()
    all_visits_df = pd.DataFrame(all_visits_response.data)
    
    if not all_visits_df.empty:
        all_visits_df['nombre_completo'] = all_visits_df['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'N/A')
        all_visits_df.drop(columns=['usuarios'], inplace=True)
        all_visits_df['fecha'] = pd.to_datetime(all_visits_df['fecha'])
    
    coordinadores = all_visits_df[all_visits_df['nombre_completo'] != 'Martín']['nombre_completo'].unique()
    colores = ['blue', 'orange', 'purple', 'cadetblue', 'pink', 'lightgreen', 'red', 'gray', 'lightblue', 'darkred']
    color_map = {coordinador: colores[i % len(colores)] for i, coordinador in enumerate(coordinadores)}

    tab_planificar, tab_global, tab_gestion = st.tabs(["✍️ Planificar Mi Semana", "🌍 Vista Global (Calendario)", "👀 Mis Próximas Visitas"])

    with tab_planificar:
        st.subheader("Gestiona tus visitas propuestas")
        st.info("Puedes editar directamente en la tabla. Las filas en blanco se ignorarán. Haz clic en el '+' para añadir nuevas visitas.")
        
        mis_visitas_propuestas_res = supabase.table('visitas').select('*').eq('usuario_id', st.session_state['usuario_id']).eq('status', 'Propuesta').execute()
        df_propuestas_original = pd.DataFrame(mis_visitas_propuestas_res.data)
        
        if not df_propuestas_original.empty:
            df_propuestas_original['fecha'] = pd.to_datetime(df_propuestas_original['fecha']).dt.date
        
        df_para_editar = df_propuestas_original if not df_propuestas_original.empty else pd.DataFrame()
        column_order = ['fecha', 'franja_horaria', 'direccion_texto', 'equipo', 'observaciones', 'id']
        df_para_editar = df_para_editar.reindex(columns=column_order)

        edited_df = st.data_editor(
            df_para_editar,
            num_rows="dynamic",
            column_order=['fecha', 'franja_horaria', 'direccion_texto', 'equipo', 'observaciones'],
            column_config={
                "id": None, 
                "fecha": st.column_config.DateColumn("Fecha", required=True),
                "franja_horaria": st.column_config.SelectboxColumn("Franja Horaria", options=HORAS_LUNES_JUEVES + HORAS_VIERNES, required=True),
                "direccion_texto": st.column_config.TextColumn("Ubicación", required=True),
                "equipo": st.column_config.TextColumn("Equipo", required=True),
                "observaciones": st.column_config.TextColumn("Observaciones")
            },
            key="editor_visitas"
        )

        if st.button("💾 Guardar Cambios", type="primary", use_container_width=True):
            with st.spinner("Guardando..."):
                original_ids = set(df_propuestas_original['id'].dropna().tolist())
                current_ids = set(edited_df['id'].dropna().tolist())
                ids_to_delete = original_ids - current_ids
                if ids_to_delete:
                    for visit_id in ids_to_delete: supabase.table('visitas').delete().eq('id', int(visit_id)).execute()
                
                for _, row in edited_df.iterrows():
                    if pd.isna(row['fecha']) or pd.isna(row['franja_horaria']) or pd.isna(row['direccion_texto']): continue
                    
                    # Validar que la franja horaria es correcta para el día de la semana
                    dia_semana = row['fecha'].weekday()
                    if dia_semana == 4 and row['franja_horaria'] not in HORAS_VIERNES:
                        st.error(f"La franja '{row['franja_horaria']}' no es válida para un viernes. Fila ignorada.")
                        continue
                    
                    lat, lon = geocode_address(row['direccion_texto'])
                    visita_data = {'usuario_id': st.session_state['usuario_id'], 'fecha': str(row['fecha']), 'franja_horaria': row['franja_horaria'], 'direccion_texto': row['direccion_texto'], 'equipo': row['equipo'], 'observaciones': row['observaciones'], 'status': 'Propuesta', 'lat': lat, 'lon': lon}
                    
                    if pd.notna(row['id']) and row['id'] in original_ids:
                        supabase.table('visitas').update(visita_data).eq('id', int(row['id'])).execute()
                    else:
                        supabase.table('visitas').insert(visita_data).execute()
                
                st.success("¡Planificación actualizada!")
                st.rerun()
        
        st.markdown("---")
        if not all_visits_df.empty: create_global_map(all_visits_df, color_map)
        else: st.info("Aún no hay visitas para mostrar en el mapa.")

    with tab_global:
        st.subheader("Calendario de Visitas Global")
        selected_date = st.date_input("Selecciona una fecha para ver su semana", value=date.today(), format="DD/MM/YYYY")

        if selected_date and not all_visits_df.empty:
            start_of_week = selected_date - timedelta(days=selected_date.weekday())
            end_of_week = start_of_week + timedelta(days=6)
            st.info(f"Mostrando visitas para la semana del {start_of_week.strftime('%d/%m/%Y')} al {end_of_week.strftime('%d/%m/%Y')}")
            df_semana_filtrada = all_visits_df[(all_visits_df['fecha'].dt.date >= start_of_week) & (all_visits_df['fecha'].dt.date <= end_of_week)]

            if not df_semana_filtrada.empty:
                calendar_events = []
                for _, row in df_semana_filtrada.iterrows():
                    franja = row.get('franja_horaria')
                    if not franja or not isinstance(franja, str): continue
                    
                    horas = re.findall(r'(\d{2}:\d{2})', franja)
                    if len(horas) == 2:
                        start_time_str, end_time_str = horas
                        fecha_evento = row['fecha'].date()
                        start_datetime = datetime.combine(fecha_evento, datetime.strptime(start_time_str, '%H:%M').time())
                        end_datetime = datetime.combine(fecha_evento, datetime.strptime(end_time_str, '%H:%M').time())
                        
                        color_evento = "black" if row['nombre_completo'] == 'Martín' else color_map.get(row['nombre_completo'], 'gray')
                        title = f"{row['nombre_completo']} - {row['equipo']}"
                        
                        calendar_events.append({"title": title, "start": start_datetime.isoformat(), "end": end_datetime.isoformat(), "color": color_evento})
                
                calendar_options = {"headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek,listWeek"}, "initialView": "timeGridWeek", "locale": "es", "eventTextColor": "white", "initialDate": start_of_week.isoformat(), "slotMinTime": "08:00:00", "slotMaxTime": "18:00:00"}
                calendar(events=calendar_events, options=calendar_options, key=f"cal_{start_of_week}")
            else:
                st.warning("No hay visitas planificadas para la semana seleccionada.")
        else:
            st.warning("No hay ninguna visita planificada en el sistema.")
    
    with tab_gestion:
        st.subheader("Resumen de Mis Próximas Visitas")
        mis_visitas_res = supabase.table('visitas').select('*').eq('usuario_id', st.session_state['usuario_id']).order('fecha, franja_horaria', desc=False).execute()
        df_mis_visitas = pd.DataFrame(mis_visitas_res.data)
        if not df_mis_visitas.empty:
            df_mis_visitas['fecha'] = pd.to_datetime(df_mis_visitas['fecha']).dt.strftime('%d/%m/%Y')
            df_mis_visitas_show = df_mis_visitas[['fecha', 'franja_horaria', 'direccion_texto', 'equipo', 'status', 'observaciones']]
            st.dataframe(df_mis_visitas_show, use_container_width=True)
        else:
            st.info("Aún no has planificado ninguna visita.")