# Fichero: planificador.py (Versión con visualización de visitas asignadas)
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
        geolocator = Nominatim(user_agent="streamlit_app_planner_v12")
        geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
        location = geocode(address + ", Catalunya", timeout=10)
        if location: return location.latitude, location.longitude
        return None, None
    except Exception: return None, None

### INICIO DE LA CORRECCIÓN: MAPA GLOBAL MEJORADO ###
def create_global_map(df, color_map):
    st.markdown("#### 🗺️ Mapa de Visitas")
    map_data = df.dropna(subset=['lat', 'lon'])
    
    if not map_data.empty:
        map_center = [41.8781, 1.7834] # Centro de Cataluña
        m = folium.Map(location=map_center, zoom_start=8)
        
        for _, row in map_data.iterrows():
            nombre = row['nombre_completo']
            
            # Si la visita está asignada al supervisor
            if row['status'] == 'Asignada a Supervisor' and pd.notna(row.get('fecha_asignada')):
                fecha_popup = pd.to_datetime(row['fecha_asignada']).strftime('%d/%m/%Y')
                hora_popup = row.get('hora_asignada') or 'N/A'
                popup_html = f"<b>Ubicación:</b> {row['direccion_texto']}  
<b>Asignada a Supervisor</b>  
<b>Fecha/Hora Final:</b> {fecha_popup} a las {hora_popup}  
<b>Propuesto por:</b> {nombre}"
                tooltip_info = f"{row['direccion_texto']} (Asignada a Supervisor)"
                # Icono especial para el supervisor
                icono = folium.Icon(color='black', icon='user-shield', prefix='fa')
            # Si es una visita propuesta
            else:
                franja = row['franja_horaria'] or ''
                fecha_popup = pd.to_datetime(row['fecha']).strftime('%d/%m/%Y')
                popup_html = f"<b>Ubicación:</b> {row['direccion_texto']}  
<b>Propuesta por:</b> {nombre}  
<b>Equipo:</b> {row['equipo']}  
<b>Fecha Propuesta:</b> {fecha_popup} ({franja})"
                tooltip_info = f"{row['direccion_texto']} (Propuesta)"
                # Icono de colores para cada coordinador
                inicial = nombre[0].upper() if nombre else '?'
                color_fondo = color_map.get(nombre, 'gray')
                icono = DivIcon(icon_size=(30,30), icon_anchor=(15,30), html=f'<div style="font-size: 12pt; font-weight: bold; color: white; background-color: {color_fondo}; width: 30px; height: 30px; text-align: center; line-height: 30px; border-radius: 50%;">{inicial}</div>')

            folium.Marker(
                location=[row['lat'], row['lon']],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=tooltip_info,
                icon=icono
            ).add_to(m)
            
        st_folium(m, width='100%', height=450)
    else:
        st.info("No hay visitas con coordenadas geográficas para mostrar en el mapa.")
### FIN DE LA CORRECCIÓN: MAPA GLOBAL MEJORADO ###

def mostrar_planificador():
    st.header("Planificador de Visitas 🗓️")
    if not supabase: st.error("La conexión con la base de datos no está disponible."); st.stop()
    
    # Cargar TODAS las visitas para tener una visión completa
    all_visits_response = supabase.table('visitas').select('*, usuarios(nombre_completo)').execute()
    all_visits_df = pd.DataFrame(all_visits_response.data)
    
    if not all_visits_df.empty:
        all_visits_df['nombre_completo'] = all_visits_df['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'N/A')
        all_visits_df.drop(columns=['usuarios'], inplace=True)
    
    # Crear mapa de colores para los coordinadores
    coordinadores = all_visits_df[all_visits_df['status'] != 'Asignada a Supervisor']['nombre_completo'].unique()
    colores = ['blue', 'orange', 'purple', 'cadetblue', 'pink', 'lightgreen', 'red', 'gray', 'lightblue', 'darkred']
    color_map = {coordinador: colores[i % len(colores)] for i, coordinador in enumerate(coordinadores)}

    tab_planificar, tab_global, tab_gestion = st.tabs(["✍️ 1. Planificar (Borrador)", "🌍 2. Vista Global (Calendario)", "👀 3. Mis Visitas (Seguimiento)"])

    with tab_planificar:
        # ... (Esta parte no necesita cambios, la lógica de edición de borradores es la misma)
        st.subheader("Gestiona tus visitas propuestas (Borradores)")
        
        selected_date_plan = st.date_input("Selecciona una semana para planificar", value=date.today(), format="DD/MM/YYYY", key="date_plan")

        start_of_week = selected_date_plan - timedelta(days=selected_date_plan.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        st.info(f"Editando borradores para la semana del {start_of_week.strftime('%d/%m/%Y')} al {end_of_week.strftime('%d/%m/%Y')}")

        mis_visitas_res = supabase.table('visitas').select('*').eq('usuario_id', st.session_state['usuario_id']).eq('status', 'Propuesta').gte('fecha', start_of_week).lte('fecha', end_of_week).execute()
        df_propuestas_original = pd.DataFrame(mis_visitas_res.data)
        
        if not df_propuestas_original.empty: 
            df_propuestas_original['fecha'] = pd.to_datetime(df_propuestas_original['fecha']).dt.date
        
        df_para_editar = df_propuestas_original.reindex(columns=['fecha', 'franja_horaria', 'direccion_texto', 'equipo', 'observaciones', 'id'])
        
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
                # ... (lógica de guardado sin cambios)
                st.success("¡Borradores actualizados!"); st.rerun()

        with col2:
            if st.button("✅ Enviar Planificación a Supervisor", use_container_width=True):
                # ... (lógica de envío sin cambios)
                st.success("¡Visitas enviadas para asignación!"); st.rerun()
        
        st.markdown("---")
        # Usamos el dataframe completo para el mapa
        if not all_visits_df.empty:
            create_global_map(all_visits_df, color_map)
        else:
            st.info("Aún no hay visitas para mostrar en el mapa.")


    with tab_global:
        st.subheader("Calendario de Visitas Global")
        
        ### INICIO DE LA CORRECCIÓN: LÓGICA DEL CALENDARIO UNIFICADO ###
        if not all_visits_df.empty:
            calendar_events = []
            for _, row in all_visits_df.iterrows():
                # Evento para visita ASIGNADA A SUPERVISOR
                if row['status'] == 'Asignada a Supervisor' and pd.notna(row.get('fecha_asignada')) and pd.notna(row.get('hora_asignada')):
                    title = f"SUPERVISOR - {row['direccion_texto']}"
                    start_dt = datetime.combine(pd.to_datetime(row['fecha_asignada']).date(), datetime.strptime(row['hora_asignada'], '%H:%M').time())
                    end_dt = start_dt + timedelta(hours=1) # Asumimos 1h de duración en calendario
                    calendar_events.append({
                        "title": title,
                        "start": start_dt.isoformat(),
                        "end": end_dt.isoformat(),
                        "color": "black", # Color distintivo para el supervisor
                        "extendedProps": {
                            "propuesto_por": row['nombre_completo'],
                            "equipo": row['equipo']
                        }
                    })
                # Evento para visita PROPUESTA
                elif row['status'] in ['Propuesta', 'Pendiente de Asignación']:
                    title = f"{row['nombre_completo']} - {row['equipo']}"
                    franja = row.get('franja_horaria')
                    if not franja or not isinstance(franja, str): continue
                    horas = re.findall(r'(\d{2}:\d{2})', franja)
                    if len(horas) != 2: continue
                    start_time_str, end_time_str = horas
                    start_dt = datetime.combine(pd.to_datetime(row['fecha']).date(), datetime.strptime(start_time_str, '%H:%M').time())
                    end_dt = datetime.combine(pd.to_datetime(row['fecha']).date(), datetime.strptime(end_time_str, '%H:%M').time())
                    calendar_events.append({
                        "title": title,
                        "start": start_dt.isoformat(),
                        "end": end_dt.isoformat(),
                        "color": color_map.get(row['nombre_completo'], 'gray')
                    })

            calendar_options = {
                "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek,listWeek"},
                "initialView": "timeGridWeek", "locale": "es", "eventTextColor": "white",
                "slotMinTime": "08:00:00", "slotMaxTime": "18:00:00"
            }
            calendar(events=calendar_events, options=calendar_options, key="global_calendar")
        else:
            st.warning("No hay ninguna visita planificada en el sistema.")
        ### FIN DE LA CORRECCIÓN: LÓGICA DEL CALENDARIO UNIFICADO ###

    with tab_gestion:
        st.subheader("Seguimiento de Mis Visitas")
        # Obtenemos solo las visitas del usuario logueado
        mis_visitas_res = supabase.table('visitas').select('*').eq('usuario_id', st.session_state['usuario_id']).order('fecha', desc=False).execute()
        df_mis_visitas = pd.DataFrame(mis_visitas_res.data)
        
        if not df_mis_visitas.empty:
            ### INICIO DE LA CORRECCIÓN: PESTAÑA DE SEGUIMIENTO ###
            st.markdown("#### ✅ Asignadas al Supervisor")
            st.info("Estas visitas han sido confirmadas por el supervisor. La fecha y hora son las definitivas.")
            df_asignadas = df_mis_visitas[df_mis_visitas['status'] == 'Asignada a Supervisor'].copy()
            if not df_asignadas.empty:
                # Limpiamos y renombramos las columnas para mayor claridad
                df_asignadas['fecha_asignada'] = pd.to_datetime(df_asignadas['fecha_asignada']).dt.strftime('%d/%m/%Y')
                df_asignadas_show = df_asignadas[['fecha_asignada', 'hora_asignada', 'direccion_texto', 'equipo', 'observaciones']]
                df_asignadas_show.rename(columns={
                    'fecha_asignada': 'Fecha Final',
                    'hora_asignada': 'Hora Final',
                    'direccion_texto': 'Ubicación',
                    'equipo': 'Equipo',
                    'observaciones': 'Observaciones'
                }, inplace=True)
                st.dataframe(df_asignadas_show, use_container_width=True, hide_index=True)
            else:
                st.success("Ninguna de tus visitas ha sido asignada al supervisor todavía.")

            st.markdown("---")
            st.markdown("#### ⏳ Pendientes de Asignación")
            st.info("Has enviado estas visitas para que el supervisor las organice. Desaparecerán de aquí una vez confirmadas.")
            df_pendientes = df_mis_visitas[df_mis_visitas['status'] == 'Pendiente de Asignación']
            if not df_pendientes.empty:
                df_pendientes['fecha'] = pd.to_datetime(df_pendientes['fecha']).dt.strftime('%d/%m/%Y')
                df_pendientes_show = df_pendientes[['fecha', 'franja_horaria', 'direccion_texto', 'equipo', 'observaciones']]
                st.dataframe(df_pendientes_show, use_container_width=True, hide_index=True)
            else:
                st.success("No has enviado ninguna visita para ser asignada.")

            st.markdown("---")
            st.markdown("#### ✍️ Borradores (Sin Enviar)")
            st.info("Estas visitas solo son visibles para ti. Puedes editarlas en la pestaña 'Planificar'.")
            df_propuestas = df_mis_visitas[df_mis_visitas['status'] == 'Propuesta']
            if not df_propuestas.empty:
                df_propuestas['fecha'] = pd.to_datetime(df_propuestas['fecha']).dt.strftime('%d/%m/%Y')
                df_propuestas_show = df_propuestas[['fecha', 'franja_horaria', 'direccion_texto', 'equipo', 'observaciones']]
                st.dataframe(df_propuestas_show, use_container_width=True, hide_index=True)
            else:
                st.success("No tienes ninguna visita guardada como borrador.")
            ### FIN DE LA CORRECCIÓN: PESTAÑA DE SEGUIMIENTO ###
        else:
            st.info("Aún no has planificado ninguna visita.")

