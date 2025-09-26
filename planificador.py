# Fichero: planificador.py (Versión 3.0 - Funcionalidad completa)
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import st_folium
from streamlit_calendar import calendar
from database import supabase # Importamos el cliente de Supabase

def mostrar_planificador():
    st.header("Planificador de Visitas 🗓️")
    
    if not supabase:
        st.error("La conexión con la base de datos no está disponible.")
        st.stop()

    # --- LÓGICA DE PLANIFICACIÓN SEMANAL ---
    hoy = date.today()
    proxima_semana_fecha = hoy + timedelta(days=7)
    año_siguiente, semana_siguiente, _ = proxima_semana_fecha.isocalendar()

    planificacion_response = supabase.table('planificaciones_semanales').select('*').eq(
        'usuario_id', st.session_state['usuario_id']
    ).eq('numero_semana', semana_siguiente).eq('año', año_siguiente).execute()
    
    planificacion_finalizada = bool(planificacion_response.data and planificacion_response.data[0]['status_planificacion'] == 'Finalizada')

    # --- PESTAÑAS DE VISUALIZACIÓN ---
    tab_planificar, tab_global, tab_gestion = st.tabs(["✍️ Planificar Mi Semana", "🌍 Vista Global (Mapa y Calendario)", "👀 Mis Próximas Visitas"])

    # --- PESTAÑA 1: PLANIFICAR MI SEMANA ---
    with tab_planificar:
        st.subheader(f"Planificación para la Semana {semana_siguiente}")

        if planificacion_finalizada:
            st.success("✅ Tu planificación para esta semana ya está finalizada.")
        else:
            st.info("Puedes editar directamente en la tabla. Las filas en blanco se ignorarán. Haz clic en el '+' para añadir nuevas visitas.")
            mis_visitas_propuestas_res = supabase.table('visitas').select('*').eq(
                'usuario_id', st.session_state['usuario_id']
            ).eq('status', 'Propuesta').execute()
            
            df_propuestas = pd.DataFrame(mis_visitas_propuestas_res.data)

            if not df_propuestas.empty:
                df_propuestas['fecha'] = pd.to_datetime(df_propuestas['fecha']).dt.date

            df_para_editar = df_propuestas[['fecha', 'direccion_texto', 'equipo', 'observaciones']] if not df_propuestas.empty else pd.DataFrame(columns=['fecha', 'direccion_texto', 'equipo', 'observaciones'])

            edited_df = st.data_editor(
                df_para_editar,
                num_rows="dynamic",
                column_config={
                    "fecha": st.column_config.DateColumn("Fecha", required=True),
                    "direccion_texto": st.column_config.TextColumn("Ciudad / Ubicación", required=True),
                    "equipo": st.column_config.TextColumn("Equipo", required=True), # <-- CAMPO AÑADIDO
                    "observaciones": st.column_config.TextColumn("Observaciones")
                },
                key="editor_visitas"
            )

            if st.button("💾 Guardar y Finalizar Planificación", type="primary", use_container_width=True):
                with st.spinner("Guardando..."):
                    supabase.table('visitas').delete().eq('usuario_id', st.session_state['usuario_id']).eq('status', 'Propuesta').execute()
                    
                    nuevas_visitas = []
                    for index, row in edited_df.iterrows():
                        if pd.notna(row['direccion_texto']) and pd.notna(row['fecha']) and pd.notna(row['equipo']):
                             nuevas_visitas.append({
                                'usuario_id': st.session_state['usuario_id'],
                                'fecha': str(row['fecha']),
                                'direccion_texto': row['direccion_texto'],
                                'equipo': row['equipo'], # <-- CAMPO AÑADIDO
                                'observaciones': row['observaciones'],
                                'status': 'Propuesta'
                            })
                    
                    if nuevas_visitas:
                        supabase.table('visitas').insert(nuevas_visitas).execute()

                    supabase.table('planificaciones_semanales').upsert({
                        'usuario_id': st.session_state['usuario_id'],
                        'numero_semana': semana_siguiente,
                        'año': año_siguiente,
                        'status_planificacion': 'Finalizada'
                    }).execute()
                    
                    st.success("¡Planificación guardada y finalizada!")
                    st.rerun()

    # --- PESTAÑA 2: VISTA GLOBAL (MAPA Y CALENDARIO) ---
    with tab_global:
        st.subheader("Mapa y Calendario de Visitas Global")
        all_visits_response = supabase.table('visitas').select('*, usuarios(nombre_completo)').execute()
        all_visits_df = pd.DataFrame(all_visits_response.data)

        if not all_visits_df.empty:
            all_visits_df['nombre_completo'] = all_visits_df['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'N/A')
            all_visits_df.drop(columns=['usuarios'], inplace=True)
            all_visits_df['fecha'] = pd.to_datetime(all_visits_df['fecha'])

            # --- MAPA GLOBAL ---
            st.markdown("#### Mapa de Visitas")
            map_data = all_visits_df.dropna(subset=['lat', 'lon'])
            if not map_data.empty:
                # ... (El código del mapa se puede añadir aquí si se geocodifican las direcciones al guardar)
                st.info("El mapa global se mostrará aquí cuando las visitas tengan coordenadas.")
            
            # --- CALENDARIO GLOBAL ---
            st.markdown("#### Calendario Semanal")
            calendar_events = []
            for _, row in all_visits_df.iterrows():
                color = "blue" if row['status'] == 'Propuesta' else "green"
                title = f"{row['nombre_completo']} - {row['equipo']} en {row['direccion_texto']}"
                if row['nombre_completo'] == "Martín": 
                    title = f"👮 {title}"

                calendar_events.append({
                    "title": title,
                    "start": row['fecha'].isoformat(),
                    "end": (row['fecha'] + timedelta(hours=1)).isoformat(), # Muestra un bloque de 1h
                    "color": color,
                })
            
            calendar_options = {
                "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek,listWeek"},
                "initialView": "timeGridWeek", # <-- VISTA SEMANAL POR DEFECTO
                "locale": "es",
            }
            calendar(events=calendar_events, options=calendar_options)
        else:
            st.warning("No hay visitas para mostrar en la vista global.")

    # --- PESTAÑA 3: MIS PRÓXIMAS VISITAS ---
    with tab_gestion:
        st.subheader("Resumen de Mis Próximas Visitas")
        # ... (Esta parte del código no necesita cambios y se mantiene igual)