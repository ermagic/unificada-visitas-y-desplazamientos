# Fichero: supervisor.py (Versión con Planificación Prioritaria)
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
    except Exception as e:
        st.error(f"Error al enviar correo: {e}")
        return False

def get_daily_time_budget(weekday):
    return 7 * 3600 if weekday == 4 else 8 * 3600

# --- LÓGICA DEL ALGORITMO ---
def generar_planificacion_automatica():
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    end_of_next_week = start_of_next_week + timedelta(days=4)

    st.info(f"Buscando visitas para la semana del {start_of_next_week.strftime('%d/%m/%Y')}.")
    
    response = supabase.table('visitas').select('*, usuarios(nombre_completo)').neq(
        'status', 'Realizada'
    ).gte(
        'fecha', start_of_next_week
    ).lte(
        'fecha', end_of_next_week
    ).execute()
    
    visitas_df = pd.DataFrame(response.data)

    if visitas_df.empty:
        st.warning("No hay visitas disponibles para planificar."); return None, None

    visitas_df['nombre_coordinador'] = visitas_df['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'N/A')
    todas_las_visitas = visitas_df.to_dict('records')

    # Separar visitas prioritarias (ayuda solicitada) de las regulares
    visitas_prioritarias = [v for v in todas_las_visitas if v.get('ayuda_solicitada')]
    visitas_regulares = [v for v in todas_las_visitas if not v.get('ayuda_solicitada') and v.get('status') == 'Propuesta']
    
    if visitas_prioritarias:
        st.success(f"Se han encontrado {len(visitas_prioritarias)} visitas prioritarias. Se planificarán primero.")

    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
    plan_final = {}
    visitas_ya_planificadas_ids = set()
    dias_disponibles = [start_of_next_week + timedelta(days=i) for i in range(5)]

    for dia_laboral in dias_disponibles:
        presupuesto_tiempo_dia = get_daily_time_budget(dia_laboral.weekday())
        
        candidatas_prioritarias = [v for v in visitas_prioritarias if v['id'] not in visitas_ya_planificadas_ids]
        candidatas_regulares = [v for v in visitas_regulares if v['id'] not in visitas_ya_planificadas_ids]
        visitas_disponibles_hoy = candidatas_prioritarias + candidatas_regulares
        
        if not visitas_disponibles_hoy: continue

        mejor_ruta_del_dia, mejor_puntuacion = [], (-1, float('inf'))
        
        for cantidad in range(len(visitas_disponibles_hoy), 0, -1):
            for combo in itertools.combinations(visitas_disponibles_hoy, cantidad):
                if candidatas_prioritarias and not all(p in combo for p in candidatas_prioritarias):
                    continue

                for orden in itertools.permutations(combo):
                    locations = [PUNTO_INICIO_MARTIN] + [v['direccion_texto'] for v in orden]
                    matrix = gmaps.distance_matrix(locations, locations, mode="driving")
                    
                    tiempo_total = matrix['rows'][0]['elements'][1]['duration']['value']
                    for i in range(len(orden) - 1):
                        tiempo_total += matrix['rows'][i+1]['elements'][i+2]['duration']['value']
                    tiempo_total += len(orden) * DURACION_VISITA_SEGUNDOS

                    if tiempo_total <= presupuesto_tiempo_dia:
                        puntuacion_actual = (len(orden), tiempo_total)
                        if puntuacion_actual[0] > mejor_puntuacion[0] or (puntuacion_actual[0] == mejor_puntuacion[0] and puntuacion_actual[1] < mejor_puntuacion[1]):
                            mejor_puntuacion, mejor_ruta_del_dia = puntuacion_actual, list(orden)
            
            if mejor_ruta_del_dia: break

        if mejor_ruta_del_dia:
            plan_final[dia_laboral.isoformat()] = mejor_ruta_del_dia
            visitas_ya_planificadas_ids.update({v['id'] for v in mejor_ruta_del_dia})

    no_asignadas = [v for v in todas_las_visitas if v['id'] not in visitas_ya_planificadas_ids and v.get('status') == 'Propuesta']
    return plan_final, no_asignadas

# --- INTERFAZ DE STREAMLIT ---
def mostrar_planificador_supervisor():
    st.header("Planificador de Martín (Supervisor) 🤖")

    if st.button("🤖 Generar planificación óptima", type="primary", use_container_width=True):
        with st.spinner("🧠 Analizando todas las visitas y calculando las mejores rutas..."):
            st.session_state.supervisor_plan, st.session_state.no_asignadas = generar_planificacion_automatica()
            if 'plan_con_horas' in st.session_state:
                del st.session_state.plan_con_horas
            if st.session_state.supervisor_plan:
                st.success("¡Planificación óptima generada!")

    if "supervisor_plan" in st.session_state and st.session_state.supervisor_plan:
        plan = st.session_state.supervisor_plan
        if 'plan_con_horas' not in st.session_state:
            gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
            plan_con_horas = {}
            for day_iso, visitas in plan.items():
                day = date.fromisoformat(day_iso)
                hora_actual, visitas_con_hora = datetime.combine(day, time(8, 0)), []
                origen = PUNTO_INICIO_MARTIN
                for v in visitas:
                    tiempo_viaje = gmaps.distance_matrix(origen, v['direccion_texto'], mode="driving")['rows'][0]['elements'][0]['duration']['value']
                    hora_actual += timedelta(seconds=tiempo_viaje)
                    v_con_hora = v.copy()
                    v_con_hora['hora_asignada'] = hora_actual.strftime('%H:%M')
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
            # ... (código del mapa sin cambios) ...
            pass
        
        st.markdown("---")
        if st.button("✅ Confirmar y Asignar", use_container_width=True, type="primary"):
            with st.spinner("Actualizando base de datos..."):
                for day_iso, visitas in st.session_state.plan_con_horas.items():
                    for v in visitas:
                        update_data = {
                            'status': 'Asignada a Supervisor', 'fecha_asignada': day_iso, 'hora_asignada': v['hora_asignada']
                        }
                        supabase.table('visitas').update(update_data).eq('id', v['id']).execute()
                st.success("¡Planificación confirmada y asignada en el sistema!")
                for key in ['supervisor_plan', 'no_asignadas', 'plan_con_horas']:
                    if key in st.session_state: del st.session_state[key]
                st.rerun()

    if "no_asignadas" in st.session_state and st.session_state.no_asignadas:
        st.warning("Visitas que no se incluyeron en el plan (siguen a cargo de sus coordinadores):")
        for v in st.session_state.no_asignadas:
            st.markdown(f"- {v['direccion_texto']} (Equipo: {v['equipo']}) - *Propuesto por: {v['nombre_coordinador']}*")
