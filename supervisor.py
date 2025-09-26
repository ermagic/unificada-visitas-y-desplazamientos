# Fichero: supervisor.py (Versión con lógica de tiempo corregida y mejoras visuales)
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
    # Devuelve 9 horas (L-J) o 7 horas (V) en segundos
    # Jornada de 8 a 17h = 9h / Jornada de 8 a 15h = 7h
    return 7 * 3600 if weekday == 4 else 9 * 3600

# --- LÓGICA DEL ALGORITMO ---
def generar_planificacion_automatica(dias_seleccionados):
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    end_of_next_week = start_of_next_week + timedelta(days=4)

    st.info(f"Buscando todas las visitas propuestas para la semana del {start_of_next_week.strftime('%d/%m/%Y')}.")
    
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

    visitas_obligatorias = [v for v in todas_las_visitas if v.get('ayuda_solicitada')]
    visitas_opcionales = [v for v in todas_las_visitas if not v.get('ayuda_solicitada') and v.get('status') == 'Propuesta']
    
    if visitas_obligatorias:
        st.success(f"Se han encontrado {len(visitas_obligatorias)} visitas con ayuda solicitada. Se incluirán de forma garantizada en el plan.")

    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
    plan_final = {}
    visitas_ya_planificadas_ids = set()
    
    for dia_laboral in dias_seleccionados:
        presupuesto_tiempo_dia = get_daily_time_budget(dia_laboral.weekday())
        
        obligatorias_restantes = [v for v in visitas_obligatorias if v['id'] not in visitas_ya_planificadas_ids]
        opcionales_restantes = [v for v in visitas_opcionales if v['id'] not in visitas_ya_planificadas_ids]
        visitas_disponibles_hoy = obligatorias_restantes + opcionales_restantes
        
        if not visitas_disponibles_hoy: continue

        mejor_ruta_del_dia = []
        mejor_puntuacion = (-1, -1, float('-inf'))
        
        for cantidad in range(len(visitas_disponibles_hoy), 0, -1):
            for combo in itertools.combinations(visitas_disponibles_hoy, cantidad):
                for orden in itertools.permutations(combo):
                    tiempo_de_trabajo = len(orden) * DURACION_VISITA_SEGUNDOS
                    
                    if len(orden) > 1:
                        direcciones_ruta = [v['direccion_texto'] for v in orden]
                        matrix = gmaps.distance_matrix(direcciones_ruta, direcciones_ruta, mode="driving")
                        for i in range(len(orden) - 1):
                            tiempo_de_trabajo += matrix['rows'][i]['elements'][i+1]['duration']['value']

                    if tiempo_de_trabajo <= presupuesto_tiempo_dia:
                        num_obligatorias = sum(1 for v in combo if v.get('ayuda_solicitada'))
                        puntuacion_actual = (num_obligatorias, len(combo), -tiempo_de_trabajo)
                        
                        if puntuacion_actual > mejor_puntuacion:
                            mejor_puntuacion = puntuacion_actual
                            mejor_ruta_del_dia = list(orden)
            
            if mejor_ruta_del_dia: break

        if mejor_ruta_del_dia:
            plan_final[dia_laboral.isoformat()] = mejor_ruta_del_dia
            visitas_ya_planificadas_ids.update({v['id'] for v in mejor_ruta_del_dia})

    visitas_no_planificadas = [v for v in todas_las_visitas if v['id'] not in visitas_ya_planificadas_ids and v.get('status') == 'Propuesta']
    
    obligatorias_no_planificadas = [v for v in visitas_obligatorias if v['id'] not in visitas_ya_planificadas_ids]
    if obligatorias_no_planificadas:
        st.error("¡Atención! Las siguientes visitas con ayuda solicitada no pudieron ser incluidas en el plan por falta de tiempo:")
        for v in obligatorias_no_planificadas:
            st.error(f"- {v['direccion_texto']} (Coordinador: {v['nombre_coordinador']})")

    return plan_final, visitas_no_planificadas

# --- INTERFAZ DE STREAMLIT ---
def mostrar_planificador_supervisor():
    st.header("Planificador de Martín (Supervisor) 🤖")

    st.subheader("1. Selecciona los días para planificar")
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    dias_semana_siguiente = [start_of_next_week + timedelta(days=i) for i in range(5)]

    dias_es = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes"}
    
    dias_seleccionados = st.multiselect(
        "Elige 3 días de la próxima semana:",
        options=dias_semana_siguiente,
        format_func=lambda d: f"{dias_es.get(d.strftime('%A'))}, {d.strftime('%d/%m')}",
        max_selections=3
    )
    st.markdown("---")

    if st.button("🤖 Generar planificación para los 3 días seleccionados", type="primary", use_container_width=True):
        if len(dias_seleccionados) != 3:
            st.warning("Por favor, selecciona exactamente 3 días.")
        else:
            with st.spinner("🧠 Analizando todas las visitas y calculando las mejores rutas..."):
                dias_seleccionados.sort()
                st.session_state.supervisor_plan, st.session_state.no_asignadas = generar_planificacion_automatica(dias_seleccionados)
                if 'plan_con_horas' in st.session_state:
                    del st.session_state.plan_con_horas
                if st.session_state.supervisor_plan is not None:
                    st.success("¡Planificación óptima generada!")

    if "supervisor_plan" in st.session_state and st.session_state.supervisor_plan is not None:
        st.subheader("2. Propuesta de Planificación")
        if not st.session_state.supervisor_plan and not st.session_state.no_asignadas:
             st.info("No hay visitas para mostrar.")
        else:
            plan = st.session_state.supervisor_plan
            if 'plan_con_horas' not in st.session_state and plan:
                gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
                plan_con_horas = {}
                for day_iso, visitas in plan.items():
                    day = date.fromisoformat(day_iso)
                    hora_actual = datetime.combine(day, time(8, 0))
                    visitas_con_hora = []

                    if visitas:
                        v_primera = visitas[0].copy()
                        v_primera['hora_asignada'] = hora_actual.strftime('%H:%M')
                        visitas_con_hora.append(v_primera)
                        
                        for i in range(len(visitas) - 1):
                            hora_actual += timedelta(seconds=DURACION_VISITA_SEGUNDOS)
                            origen = visitas[i]['direccion_texto']
                            destino = visitas[i+1]['direccion_texto']
                            tiempo_viaje = gmaps.distance_matrix(origen, destino, mode="driving")['rows'][0]['elements'][0]['duration']['value']
                            hora_actual += timedelta(seconds=tiempo_viaje)
                            
                            v_siguiente = visitas[i+1].copy()
                            v_siguiente['hora_asignada'] = hora_actual.strftime('%H:%M')
                            visitas_con_hora.append(v_siguiente)
                    plan_con_horas[day_iso] = visitas_con_hora
                st.session_state.plan_con_horas = plan_con_horas

            if 'plan_con_horas' in st.session_state and st.session_state.plan_con_horas:
                for day_iso, visitas in st.session_state.plan_con_horas.items():
                    day = date.fromisoformat(day_iso)
                    nombre_dia_es = dias_es.get(day.strftime('%A'))
                    nombre_dia_completo = day.strftime(f'{nombre_dia_es}, %d de %B').capitalize()
                    with st.expander(f"**{nombre_dia_completo}** ({len(visitas)} visitas)", expanded=True):
                        for v in visitas:
                            ayuda_texto = " <span style='color:red;'>(ayuda pedida)</span>" if v.get('ayuda_solicitada') else ""
                            st.markdown(
                                f"- **{v['hora_asignada']}h** - {v['direccion_texto']} | **Equipo**: {v['equipo']} "
                                f"(*Propuesto por: {v['nombre_coordinador']}{ayuda_texto}*)",
                                unsafe_allow_html=True
                            )
            
            st.markdown("---")
            st.subheader("3. Confirmación")
            if st.button("✅ Confirmar y Asignar", use_container_width=True, type="primary"):
                with st.spinner("Actualizando base de datos..."):
                    if 'plan_con_horas' in st.session_state and st.session_state.plan_con_horas:
                        for day_iso, visitas in st.session_state.plan_con_horas.items():
                            for v in visitas:
                                update_data = {'status': 'Asignada a Supervisor', 'fecha_asignada': day_iso, 'hora_asignada': v['hora_asignada']}
                                supabase.table('visitas').update(update_data).eq('id', v['id']).execute()
                    st.success("¡Planificación confirmada y asignada en el sistema!")
                    for key in ['supervisor_plan', 'no_asignadas', 'plan_con_horas']:
                        if key in st.session_state: del st.session_state[key]
                    st.rerun()

    if "no_asignadas" in st.session_state and st.session_state.no_asignadas:
        st.warning("Visitas que no se incluyeron en el plan (siguen a cargo de sus coordinadores):")
        for v in st.session_state.no_asignadas:
            st.markdown(f"- {v['direccion_texto']} (Equipo: {v['equipo']}) - *Propuesto por: {v['nombre_coordinador']}*")