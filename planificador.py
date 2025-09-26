# Fichero: planificador.py (Versión con Iconos Personalizados y Calendario Visible)
import streamlit as st
import pandas as pd
from datetime import timedelta, date
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium
from streamlit_folium import st_folium
from streamlit_calendar import calendar
from database import supabase

# --- FUNCIÓN DE GEOCODIFICACIÓN (se mantiene igual) ---
@st.cache_data(ttl=60*60*24)
def geocode_address(address: str):
    """Convierte una dirección de texto a coordenadas (lat, lon)."""
    if not address or pd.isna(address):
        return None, None
    try:
        geolocator = Nominatim(user_agent="streamlit_app_planner_v3")
        geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
        location = geocode(address + ", Catalunya", timeout=10)
        if location:
            return location.latitude, location.longitude
        return None, None
    except Exception:
        return None, None

def mostrar_planificador():
    st.header("Planificador de Visitas 🗓️")

    if not supabase:
        st.error("La conexión con la base de datos no está disponible.")
        st.stop()
    
    # --- PESTAÑAS DE VISUALIZACIÓN ---
    tab_planificar, tab_global, tab_gestion = st.tabs(["✍️ Planificar Mi Semana", "🌍 Vista Global (Mapa y Calendario)", "👀 Mis Próximas Visitas"])

    # --- PESTAÑA 1: PLANIFICAR MI SEMANA (sin cambios en esta versión) ---
    with tab_planificar:
        st.subheader("Gestiona tus visitas propuestas")
        st.info("Puedes editar directamente en la tabla. Las filas en blanco se ignorarán. Haz clic en el '+' para añadir nuevas visitas.")
        
        # Cargar las visitas existentes que están en estado "Propuesta"
        mis_visitas_propuestas_res = supabase.table('visitas').select('*').eq(
            'usuario_id', st.session_state['usuario_id']
        ).eq('status', 'Propuesta').execute()
        
        df_propuestas_original = pd.DataFrame(mis_visitas_propuestas_res.data)
        
        if 'original_df_ids' not in st.session_state:
            st.session_state.original_df_ids = set(df_propuestas_original['id'].tolist()) if not df_propuestas_original.empty else set()

        df_para_editar = df_propuestas_original[['id', 'fecha', 'direccion_texto', 'equipo', 'observaciones']] if not df_propuestas_original.empty else pd.DataFrame(columns=['id', 'fecha', 'direccion_texto', 'equipo', 'observaciones'])

        edited_df = st.data_editor(
            df_para_editar,
            num_rows="dynamic",
            column_config={
                "id": None, 
                "fecha": st.column_config.DateColumn("Fecha", required=True),
                "direccion_texto": st.column_config.TextColumn("Ciudad / Ubicación", required=True),
                "equipo": st.column_config.TextColumn("Equipo", required=True),
                "observaciones": st.column_config.TextColumn("Observaciones")
            },
            key="editor_visitas"
        )

        if st.button("💾 Guardar Cambios", type="primary", use_container_width=True):
            with st.spinner("Guardando y geocodificando direcciones..."):
                current_ids = set(edited_df['id'].dropna().tolist())
                original_ids = st.session_state.original_df_ids
                ids_to_delete = original_ids - current_ids
                
                if ids_to_delete:
                    for visit_id in ids_to_delete:
                        supabase.table('visitas').delete().eq('id', int(visit_id)).execute()

                for _, row in edited_df.iterrows():
                    if pd.isna(row['direccion_texto']) or pd.isna(row['fecha']) or pd.isna(row['equipo']):
                        continue
                    
                    lat, lon = geocode_address(row['direccion_texto'])
                    visita_data = {
                        'usuario_id': st.session_state['usuario_id'],
                        'fecha': str(row['fecha']),
                        'direccion_texto': row['direccion_texto'],
                        'equipo': row['equipo'],
                        'observaciones': row['observaciones'],
                        'status': 'Propuesta',
                        'lat': lat, 'lon': lon
                    }

                    if pd.notna(row['id']) and row['id'] in original_ids:
                        supabase.table('visitas').update(visita_data).eq('id', int(row['id'])).execute()
                    else:
                        supabase.table('visitas').insert(visita_data).execute()
                
                st.success("¡Planificación actualizada correctamente!")
                st.session_state.original_df_ids = None
                st.rerun()

    # --- PESTAÑA 2: VISTA GLOBAL (CON ICONOS PERSONALIZADOS) ---
    with tab_global:
        st.subheader("Mapa y Calendario de Visitas Global")
        all_visits_response = supabase.table('visitas').select('*, usuarios(nombre_completo)').execute()
        all_visits_df = pd.DataFrame(all_visits_response.data)

        if not all_visits_df.empty:
            all_visits_df['nombre_completo'] = all_visits_df['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'N/A')
            all_visits_df.drop(columns=['usuarios'], inplace=True)
            all_visits_df['fecha'] = pd.to_datetime(all_visits_df['fecha'])

            # --- MAPA GLOBAL CON ICONOS PERSONALIZADOS ---
            st.markdown("#### 🗺️ Mapa de Visitas")
            map_data = all_visits_df.dropna(subset=['lat', 'lon'])
            
            if not map_data.empty:
                map_center = [41.8781, 1.7834] # Cataluña
                m = folium.Map(location=map_center, zoom_start=8)

                # --- Lógica de colores para coordinadores ---
                coordinadores = map_data[map_data['nombre_completo'] != 'Martín']['nombre_completo'].unique()
                colores = ['blue', 'orange', 'purple', 'cadetblue', 'pink', 'lightgreen', 'red', 'gray', 'lightblue', 'darkred']
                color_map = {coordinador: colores[i % len(colores)] for i, coordinador in enumerate(coordinadores)}

                for _, row in map_data.iterrows():
                    nombre = row['nombre_completo']
                    
                    # Asignar icono y color
                    if nombre == 'Martín':
                        color_icono = 'black'
                        icono_fa = 'user-shield' # Icono de escudo
                    else:
                        color_icono = color_map.get(nombre, 'gray') # Color asignado
                        icono_fa = 'user' # Icono estándar de usuario
                    
                    popup_html = f"""
                    <b>Ubicación:</b> {row['direccion_texto']}<br>
                    <b>Fecha:</b> {row['fecha'].strftime('%d/%m/%Y')}<br>
                    <b>Equipo:</b> {row['equipo']}<br>
                    <b>Usuario:</b> {nombre}
                    """
                    
                    folium.Marker(
                        location=[row['lat'], row['lon']],
                        popup=folium.Popup(popup_html, max_width=300),
                        tooltip=f"{row['direccion_texto']} ({nombre})",
                        icon=folium.Icon(color=color_icono, icon=icono_fa, prefix='fa')
                    ).add_to(m)

                st_folium(m, width='100%', height=450)
            else:
                st.info("No hay visitas con coordenadas geográficas para mostrar en el mapa.")

            # --- CALENDARIO GLOBAL (LÓGICA REVISADA PARA MÁXIMA VISIBILIDAD) ---
            st.markdown("#### 🗓️ Calendario Semanal")
            calendar_events = []
            for _, row in all_visits_df.iterrows():
                # Asignar color según el usuario
                if row['nombre_completo'] == 'Martín':
                    color_evento = "black"
                else:
                    color_evento = color_map.get(row['nombre_completo'], 'gray')

                title = f"{row['nombre_completo']} - {row['equipo']} en {row['direccion_texto']}"
                
                calendar_events.append({
                    "title": title,
                    "start": row['fecha'].isoformat(),
                    "end": (row['fecha'] + timedelta(hours=1)).isoformat(),
                    "color": color_evento,
                })

            calendar_options = {
                "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek,listWeek"},
                "initialView": "timeGridWeek",
                "locale": "es",
                "eventTextColor": "white"
            }
            calendar(events=calendar_events, options=calendar_options)
        else:
            st.warning("No hay visitas para mostrar en la vista global.")

    # --- PESTAÑA 3: MIS PRÓXIMAS VISITAS (se mantiene igual) ---
    with tab_gestion:
        st.subheader("Resumen de Mis Próximas Visitas")
        mis_visitas_res = supabase.table('visitas').select('*').eq(
            'usuario_id', st.session_state['usuario_id']
        ).order('fecha', desc=False).execute()

        df_mis_visitas = pd.DataFrame(mis_visitas_res.data)

        if not df_mis_visitas.empty:
            df_mis_visitas_show = df_mis_visitas[['fecha', 'direccion_texto', 'equipo', 'status', 'observaciones']]
            st.dataframe(df_mis_visitas_show, use_container_width=True)
        else:
            st.info("Aún no has planificado ninguna visita.")