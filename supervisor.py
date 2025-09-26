# Fichero: supervisor.py (Versión con mapa de rutas y correcciones)
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime, time
import googlemaps
import itertools
import smtplib
from email.mime.text import MIMEText
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from database import supabase

# --- CONSTANTES ---
PUNTO_INICIO_MARTIN = "Plaça de Catalunya, Barcelona, España"
DURACION_VISITA_SEGUNDOS = 45 * 60

# --- FUNCIONES AUXILIARES ---
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

# --- LÓGICA DEL ALGORITMO ---
def generar_planificacion_automatica():
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    end_of_next_week = start_of_next_week + timedelta(days=4)

    response = supabase.table('visitas').select('*, usuarios(nombre_completo)').eq('status', 'Pendiente de Asignación').gte('fecha', start_of_next_week).lte('fecha', end_of_next_week).execute()
    visitas_df = pd.DataFrame(response.data)
    if visitas_df.empty:
        st.warning("No hay visitas pendientes de asignación para la próxima semana.")
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

    for _ in range(3):
        if not visitas_pendientes: break
        mejor_dia_encontrado, mejor_ruta_del_dia, mejor_puntuacion = None, [], (-1, float('inf'))

        for dia_laboral in dias_disponibles:
            presupuesto_tiempo_dia = get_daily_time_budget(dia_laboral.weekday())
            for cantidad in range(len(visitas_pendientes), 0, -1):
                if cantidad < mejor_puntuacion[0]: break
                for combo in itertools.combinations(visitas_pendientes, cantidad):
                    for orden in itertools.permutations(combo):
                        tiempo_total = sum(DURACION_VISITA_SEGUNDOS + get_travel_time(orden[i]['direccion_texto'], orden[i+1]['direccion_texto']) for i in range(len(orden)-1))
                        tiempo_total += DURACION_VISITA_SEGUNDOS + get_travel_time(orden[-1]['direccion_texto'], PUNTO_INICIO_MARTIN)
                        if tiempo_total <= presupuesto_tiempo_dia:
                            puntuacion_actual = (len(orden), tiempo_total)
                            if puntuacion_actual[0] > mejor_puntuacion[0] or (puntuacion_actual[0] == mejor_puntuacion[0] and puntuacion_actual[1] < mejor_puntuacion[1]):
                                mejor_puntuacion, mejor_ruta_del_dia, mejor_dia_encontrado = puntuacion_actual, list(orden), dia_laboral
                if mejor_puntuacion[0] == cantidad: break
        
        if mejor_dia_encontrado:
            plan_final[mejor_dia_encontrado] = mejor_ruta_del_dia
            ids_agregadas = {v['id'] for v in mejor_ruta_del_dia}
            visitas_ya_planificadas_ids.update(ids_agregadas)
            visitas_pendientes = [v for v in visitas_pendientes if v['id'] not in ids_agregadas]
            dias_disponibles.remove(mejor_dia_encontrado)
        else: break
    
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
            st.rerun()

    if "supervisor_plan" in st.session_state and st.session_state.supervisor_plan:
        plan = st.session_state.supervisor_plan
        if 'plan_con_horas' not in st.session_state:
            gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
            plan_con_horas = {}
            for day, visitas in plan.items():
                hora_actual, visitas_con_hora = datetime.combine(day, time(8, 0)), []
                for i, v in enumerate(visitas):
                    if i > 0:
                        origen = visitas[i-1]['direccion_texto']
                        tiempo_viaje = gmaps.distance_matrix(origen, v['direccion_texto'], mode="driving")['rows'][0]['elements'][0]['duration']['value']
                        hora_actual += timedelta(seconds=tiempo_viaje)
                    v_con_hora = v.copy()
                    v_con_hora['hora_asignada'] = hora_actual.time()
                    visitas_con_hora.append(v_con_hora)
                    hora_actual += timedelta(seconds=DURACION_VISITA_SEGUNDOS)
                plan_con_horas[day] = visitas_con_hora
            st.session_state.plan_con_horas = plan_con_horas

        tab_plan, tab_mapa = st.tabs(["📅 Propuesta de Planificación", "🗺️ Vista en Mapa"])
        with tab_plan:
            for day, visitas in st.session_state.plan_con_horas.items():
                nombre_dia = day.strftime('%A, %d de %B').capitalize()
                with st.expander(f"**{nombre_dia}** ({len(visitas)} visitas)", expanded=True):
                    for v in visitas:
                        st.markdown(f"- **{v['hora_asignada'].strftime('%H:%M')}h** - {v['direccion_texto']} | **Equipo**: {v['equipo']} (*Propuesto por: {v['nombre_coordinador']}*)")
        
        with tab_mapa:
            df_visitas = pd.DataFrame([visit for day_visits in plan.values() for visit in day_visits]).dropna(subset=['lat', 'lon'])
            if df_visitas.empty:
                st.warning("No hay visitas con coordenadas para mostrar en el mapa.")
            else:
                map_center = [df_visitas['lat'].mean(), df_visitas['lon'].mean()]
                m = folium.Map(location=map_center, zoom_start=11)
                try:
                    location = Nominatim(user_agent="supervisor_map_v2").geocode(PUNTO_INICIO_MARTIN)
                    if location: folium.Marker([location.latitude, location.longitude], popup="Punto de Salida/Llegada", icon=folium.Icon(color='green', icon='home', prefix='fa')).add_to(m)
                except Exception: pass
                
                day_colors = ['blue', 'red', 'purple']
                for i, (day, visitas) in enumerate(plan.items()):
                    color, points = day_colors[i % len(day_colors)], []
                    for visit in visitas:
                        if pd.notna(visit.get('lat')) and pd.notna(visit.get('lon')):
                            points.append((visit['lat'], visit['lon']))
                            popup_html = f"<b>{day.strftime('%A')}</b>: {visit['equipo']}<br>{visit['direccion_texto']}"
                            folium.Marker([visit['lat'], visit['lon']], popup=popup_html, icon=folium.Icon(color=color, icon='briefcase', prefix='fa')).add_to(m)
                    if len(points) > 1: folium.PolyLine(points, color=color, weight=2.5, opacity=0.8).add_to(m)
                st_folium(m, use_container_width=True, height=500)

        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Confirmar y Asignar", use_container_width=True, type="primary"):
                with st.spinner("Actualizando base de datos..."):
                    for day, visitas in st.session_state.plan_con_horas.items():
                        for v in visitas: supabase.table('visitas').update({'status': 'Asignada a Supervisor', 'fecha_asignada': str(day.date()), 'hora_asignada': v['hora_asignada'].strftime('%H:%M')}).eq('id', v['id']).execute()
                    if st.session_state.no_asignadas:
                        ids = [v['id'] for v in st.session_state.no_asignadas]
                        supabase.table('visitas').update({'status': 'Asignada a Coordinador'}).in_('id', ids).execute()
                st.success("¡Planificación confirmada y asignada en el sistema!")
                for key in ['supervisor_plan', 'no_asignadas', 'plan_con_horas']:
                    if key in st.session_state: del st.session_state[key]
                st.rerun()
        with col2:
            if st.button("📧 Notificar a Coordinadores", use_container_width=True):
                response = supabase.table('usuarios').select('email').eq('rol', 'coordinador').execute()
                emails = [u['email'] for u in response.data if u['email']]
                if emails:
                    body = "<h3>Resumen de la Planificación del Supervisor</h3><p>Hola equipo, a continuación se detallan las visitas que asumirá el supervisor la próxima semana:</p>"
                    for day, visitas in st.session_state.plan_con_horas.items():
                        body += f"<h4>{day.strftime('%A, %d/%m/%Y').capitalize()}</h4><ul>"
                        for v in visitas:
                            body += f"<li><b>{v['hora_asignada'].strftime('%H:%M')}h</b>: {v['direccion_texto']} (Equipo: {v['equipo']}) - <i>Propuesta por {v['nombre_coordinador']}</i></li>"
                        body += "</ul>"
                    body += "<p>El resto de visitas planificadas han sido asignadas a sus coordinadores correspondientes. Por favor, revisad la plataforma.</p>"
                    send_email(emails, f"Planificación del Supervisor - Semana del {min(plan.keys()).strftime('%d/%m')}", body)
                else:
                    st.warning("No se encontraron emails de coordinadores para notificar.")


    if "no_asignadas" in st.session_state and st.session_state.no_asignadas:
        st.warning("Visitas no incluidas en la planificación óptima (serán devueltas a sus coordinadores):")
        for v in st.session_state.no_asignadas:
            st.markdown(f"- {v['direccion_texto']} (Equipo: {v['equipo']}) - *Propuesto por: {v['nombre_coordinador']}*")

    with st.expander("➕ Añadir visita manual (fuera del algoritmo)"):
        with st.form("manual_visit_form"):
            fecha = st.date_input("Fecha")
            hora = st.time_input("Hora")
            direccion = st.text_input("Dirección")
            equipo = st.text_input("Equipo")
            observaciones = st.text_area("Observaciones")
            if st.form_submit_button("Añadir visita manual"):
                hora_fin = (datetime.combine(date.today(), hora) + timedelta(minutes=45)).time()
                supabase.table('visitas').insert({
                    'usuario_id': st.session_state['usuario_id'],
                    'fecha': str(fecha),
                    'franja_horaria': f"{hora.strftime('%H:%M')}-{hora_fin.strftime('%H:%M')}",
                    'direccion_texto': direccion,
                    'equipo': equipo,
                    'observaciones': observaciones,
                    'status': 'Asignada a Supervisor',
                    'fecha_asignada': str(fecha),
                    'hora_asignada': hora.strftime('%H:%M')
                }).execute()
                st.success("Visita manual añadida correctamente.")
                st.rerun()