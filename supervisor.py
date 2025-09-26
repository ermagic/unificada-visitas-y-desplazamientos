# Fichero: supervisor.py (Versión con ALGORITMO Y MAPA CORREGIDOS)
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime, time
import googlemaps
import itertools
import smtplib
from email.mime.text import MIMEText
import folium
from folium.features import DivIcon
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from database import supabase

# --- CONSTANTES ---
PUNTO_INICIO_MARTIN = "Plaça de Catalunya, Barcelona, España"
DURACION_VISITA_SEGUNDOS = 45 * 60

# --- FUNCIONES AUXILIARES (sin cambios) ---
def send_email(recipients, subject, body):
    try:
        smtp_cfg = st.secrets["smtp"]
        sender, password = smtp_cfg["username"], smtp_cfg["password"]
        msg = MIMEText(body, 'html')
        msg['From'], msg['To'], msg['Subject'] = sender, ", ".join(recipients), subject
        server = smtplib.SMTP(smtp_cfg["server"], smtp_cfg["port"])
        server.starttls(); server.login(sender, password); server.send_message(msg); server.quit()
        st.success("✅ Correo de notificación enviado con éxito.")
        return True
    except Exception as e: st.error(f"Error al enviar correo: {e}"); return False

def get_daily_time_budget(weekday):
    return 7 * 3600 if weekday == 4 else 8 * 3600

# --- LÓGICA DEL ALGORITMO (con cálculo de tiempo corregido) ---
def generar_planificacion_automatica():
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    end_of_next_week = start_of_next_week + timedelta(days=4)
    
    st.info(f"Buscando visitas disponibles para la semana del {start_of_next_week.strftime('%d/%m/%Y')}.")
    response = supabase.table('visitas').select('*, usuarios(nombre_completo)').neq('status', 'Asignada a Supervisor').gte('fecha', start_of_next_week).lte('fecha', end_of_next_week).execute()
    visitas_df = pd.DataFrame(response.data)
    
    st.info(f"Se encontraron {len(visitas_df)} visitas disponibles para planificar.")
    if visitas_df.empty:
        st.warning("No hay visitas de coordinadores disponibles para planificar la próxima semana.")
        return None, None

    visitas_df['nombre_coordinador'] = visitas_df['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'N/A')
    visitas_pendientes = visitas_df.to_dict('records')

    locations = [PUNTO_INICIO_MARTIN] + list(visitas_df['direccion_texto'].unique())
    try:
        gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
        matrix = gmaps.distance_matrix(locations, locations, mode="driving")
    except Exception as e: st.error(f"Error al conectar con Google Maps API: {e}"); return None, None

    def get_travel_time(origen, destino):
        try:
            origen_idx, destino_idx = locations.index(origen), locations.index(destino)
            return matrix['rows'][origen_idx]['elements'][destino_idx]['duration']['value']
        except (ValueError, KeyError): return 3600

    plan_final = {}; visitas_ya_planificadas_ids = set()
    dias_disponibles = [start_of_next_week + timedelta(days=i) for i in range(5)]

    for dia_laboral in dias_disponibles:
        presupuesto_tiempo_dia = get_daily_time_budget(dia_laboral.weekday())
        visitas_disponibles_hoy = [v for v in visitas_pendientes if v['id'] not in visitas_ya_planificadas_ids]
        if not visitas_disponibles_hoy: break
        
        mejor_ruta_del_dia, mejor_puntuacion = [], (-1, float('inf'))
        for cantidad in range(len(visitas_disponibles_hoy), 0, -1):
            for combo in itertools.combinations(visitas_disponibles_hoy, cantidad):
                for orden in itertools.permutations(combo):
                    # <-- CAMBIO FUNDAMENTAL: Lógica de cálculo de tiempo corregida
                    
                    # Empezamos con el viaje a la primera visita
                    tiempo_total = get_travel_time(PUNTO_INICIO_MARTIN, orden[0]['direccion_texto'])
                    
                    # Sumamos la duración de TODAS las visitas
                    tiempo_total += len(orden) * DURACION_VISITA_SEGUNDOS
                    
                    # Sumamos los viajes INTERNOS entre visitas
                    for i in range(len(orden) - 1):
                        tiempo_total += get_travel_time(orden[i]['direccion_texto'], orden[i+1]['direccion_texto'])
                    
                    # NO sumamos el viaje de vuelta a Barcelona, la jornada termina en la última visita.
                    
                    if tiempo_total <= presupuesto_tiempo_dia:
                        puntuacion_actual = (len(orden), tiempo_total)
                        if puntuacion_actual[0] > mejor_puntuacion[0] or (puntuacion_actual[0] == mejor_puntuacion[0] and puntuacion_actual[1] < mejor_puntuacion[1]):
                            mejor_puntuacion, mejor_ruta_del_dia = puntuacion_actual, list(orden)
            if mejor_ruta_del_dia: break
        
        if mejor_ruta_del_dia:
            plan_final[dia_laboral.isoformat()] = mejor_ruta_del_dia
            ids_agregadas = {v['id'] for v in mejor_ruta_del_dia}
            visitas_ya_planificadas_ids.update(ids_agregadas)
            
    no_asignadas = visitas_df[~visitas_df['id'].isin(visitas_ya_planificadas_ids)].to_dict('records')
    return plan_final, no_asignadas

# --- INTERFAZ DE STREAMLIT ---
def mostrar_planificador_supervisor():
    st.header("Planificador de Martín (Supervisor) 🤖")

    if st.button("🤖 Generar planificación óptima", type="primary", use_container_width=True):
        with st.spinner("🧠 Analizando todas las visitas y calculando las mejores rutas..."):
            st.session_state.supervisor_plan, st.session_state.no_asignadas = generar_planificacion_automatica()
            if 'plan_con_horas' in st.session_state: del st.session_state.plan_con_horas
            if st.session_state.supervisor_plan: st.success("¡Planificación óptima generada!")
    
    if "supervisor_plan" in st.session_state and st.session_state.supervisor_plan:
        plan = st.session_state.supervisor_plan
        if 'plan_con_horas' not in st.session_state:
            gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
            plan_con_horas = {}
            for day_iso, visitas in plan.items():
                day = date.fromisoformat(day_iso)
                hora_actual, visitas_con_hora = datetime.combine(day, time(8, 0)), []
                origen = PUNTO_INICIO_MARTIN
                for i, v in enumerate(visitas):
                    tiempo_viaje = gmaps.distance_matrix(origen, v['direccion_texto'], mode="driving")['rows'][0]['elements'][0]['duration']['value']
                    hora_actual += timedelta(seconds=tiempo_viaje)
                    v_con_hora = v.copy(); v_con_hora['hora_asignada'] = hora_actual.strftime('%H:%M')
                    visitas_con_hora.append(v_con_hora)
                    hora_actual += timedelta(seconds=DURACION_VISITA_SEGUNDOS)
                    origen = v['direccion_texto']
                plan_con_horas[day_iso] = visitas_con_hora
            st.session_state.plan_con_horas = plan_con_horas

        tab_plan, tab_mapa = st.tabs(["📅 Propuesta de Planificación", "🗺️ Vista en Mapa"])
        with tab_plan:
            for day_iso, visitas in st.session_state.plan_con_horas.items():
                day = date.fromisoformat(day_iso)
                nombre_dia = day.strftime('%A, %d de %B').capitalize()
                with st.expander(f"**{nombre_dia}** ({len(visitas)} visitas)", expanded=True):
                    for v in visitas:
                        st.markdown(f"- **{v['hora_asignada']}h** - {v['direccion_texto']} | **Equipo**: {v['equipo']} (*Propuesto por: {v['nombre_coordinador']}*)")
        
        with tab_mapa:
            df_visitas = pd.DataFrame([visit for day_visits in plan.values() for visit in day_visits]).dropna(subset=['lat', 'lon'])
            if df_visitas.empty:
                st.warning("No hay visitas con coordenadas para mostrar en el mapa.")
            else:
                # <-- CAMBIO: Lógica de mapa restaurada a la original y funcional
                map_center = [df_visitas['lat'].mean(), df_visitas['lon'].mean()]
                m = folium.Map(location=map_center, zoom_start=11)

                try:
                    location = Nominatim(user_agent="supervisor_map_v8").geocode(PUNTO_INICIO_MARTIN)
                    if location: folium.Marker([location.latitude, location.longitude], popup="Punto de Salida", icon=folium.Icon(color='green', icon='home', prefix='fa')).add_to(m)
                except Exception: pass
                
                day_colors = ['blue', 'red', 'purple', 'orange', 'darkgreen']
                for i, (day_iso, visitas) in enumerate(st.session_state.plan_con_horas.items()):
                    day = date.fromisoformat(day_iso)
                    color = day_colors[i % len(day_colors)]
                    points = []
                    for visit_idx, visit in enumerate(visitas):
                        if pd.notna(visit.get('lat')) and pd.notna(visit.get('lon')):
                            points.append((visit['lat'], visit['lon']))
                            popup_html = f"<b>{day.strftime('%A')} - Visita {visit_idx + 1}</b><br><b>Hora:</b> {visit['hora_asignada']}h<br><b>Equipo:</b> {visit['equipo']}<br><b>Dirección:</b> {visit['direccion_texto']}"
                            DivIcon_html=f'<div style="font-family: sans-serif; color: {color}; font-size: 18px; font-weight: bold; text-shadow: -1px 0 white, 0 1px white, 1px 0 white, 0 -1px white;">{visit_idx + 1}</div>'
                            folium.Marker([visit['lat'], visit['lon']], popup=folium.Popup(popup_html, max_width=300), icon=DivIcon(icon_size=(150,36), icon_anchor=(7,20), html=DivIcon_html)).add_to(m)
                    
                    if len(points) > 1:
                        folium.PolyLine(points, color=color, weight=2.5, opacity=0.8).add_to(m)

                # Usamos fit_bounds para el zoom automático, que es más robusto
                if not df_visitas.empty:
                    sw = df_visitas[['lat', 'lon']].min().values.tolist()
                    ne = df_visitas[['lat', 'lon']].max().values.tolist()
                    m.fit_bounds([sw, ne])
                
                st_folium(m, use_container_width=True, height=500)

        # ... (Resto del fichero sin cambios)
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Confirmar y Asignar", use_container_width=True, type="primary"):
                # ...
        with col2:
            if st.button("📧 Notificar a Coordinadores", use_container_width=True):
                # ...

    if "no_asignadas" in st.session_state and st.session_state.no_asignadas:
        # ...

    with st.expander("➕ Añadir/Crear visita manual para Martín"):
        # ...