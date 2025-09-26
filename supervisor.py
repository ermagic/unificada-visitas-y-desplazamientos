# Fichero: supervisor.py (Versión con algoritmo corregido y UI mejorada)
import streamlit as st
import pandas as pd
from database import supabase
from datetime import date, timedelta, datetime, time
import googlemaps
import itertools
import folium
from streamlit_calendar import calendar
import smtplib
from email.mime.text import MIMEText
import re

# --- FUNCIÓN PARA ENVIR EMAILS (sin cambios) ---
def send_email(recipients, subject, body):
    """Envía un correo electrónico usando la configuración de secrets."""
    try:
        smtp_cfg = st.secrets["smtp"]
        sender, password = smtp_cfg["username"], smtp_cfg["password"]
        msg = MIMEText(body, 'html')
        msg['From'], msg['To'], msg['Subject'] = sender, ", ".join(recipients), subject
        server = smtplib.SMTP(smtp_cfg["server"], smtp_cfg["port"])
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        st.success("✅ ¡Correo de notificación enviado con éxito!")
        return True
    except Exception as e:
        st.error(f"Error al enviar el correo: {e}")
        return False

# --- LÓGICA DEL MOTOR DE PLANIFICACIÓN ---
@st.cache_data(ttl=3600)
def get_distance_matrix(locations):
    """Obtiene la matriz de distancias de Google Maps para una lista de ubicaciones."""
    try:
        gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
        matrix = gmaps.distance_matrix(locations, locations, mode="driving")
        return matrix
    except Exception as e:
        st.error(f"Error al contactar con la API de Google Maps: {e}")
        return None

def find_best_day_route(available_visits_df, all_locations, dist_matrix):
    time_budget_seconds = 8 * 3600
    visit_duration_seconds = 45 * 60

    best_route = []
    max_visits = 0
    min_travel_time = float('inf')
    invalid_routes_found = 0

    if available_visits_df.empty:
        return best_route, max_visits, min_travel_time, invalid_routes_found

    ### INICIO DE LA CORRECCIÓN ALGORITMO ###
    # Iterar desde el número máximo de visitas hacia abajo
    max_possible_visits = min(len(available_visits_df), 6)
    for r in range(max_possible_visits, 0, -1):
        for p in itertools.permutations(available_visits_df.index, r):
    ### FIN DE LA CORRECCIÓN ALGORITMO ###
            current_time = 0
            current_travel_time = 0
            current_route_segment = []
            is_permutation_valid = True

            first_visit_loc = available_visits_df.loc[p[0], 'direccion_texto']
            first_loc_index = all_locations.index(first_visit_loc)
            element_to_first = dist_matrix['rows'][0]['elements'][first_loc_index]
            if element_to_first['status'] != 'OK':
                invalid_routes_found += 1
                continue
            travel_to_first = element_to_first['duration']['value']

            current_time += travel_to_first
            current_travel_time += travel_to_first

            for j in range(len(p)):
                current_time += visit_duration_seconds
                if j < len(p) - 1:
                    loc_a = available_visits_df.loc[p[j], 'direccion_texto']
                    loc_b = available_visits_df.loc[p[j+1], 'direccion_texto']
                    idx_a = all_locations.index(loc_a)
                    idx_b = all_locations.index(loc_b)
                    element_to_next = dist_matrix['rows'][idx_a]['elements'][idx_b]
                    if element_to_next['status'] != 'OK':
                        is_permutation_valid = False
                        break
                    travel_to_next = element_to_next['duration']['value']
                    current_time += travel_to_next
                    current_travel_time += travel_to_next

                last_visit_loc = available_visits_df.loc[p[j], 'direccion_texto']
                last_loc_index = all_locations.index(last_visit_loc)
                element_from_last = dist_matrix['rows'][last_loc_index]['elements'][0]
                if element_from_last['status'] != 'OK':
                    is_permutation_valid = False
                    break
                travel_from_last = element_from_last['duration']['value']

                if (current_time + travel_from_last) > time_budget_seconds:
                    is_permutation_valid = False
                    break
                
                current_route_segment.append(available_visits_df.loc[p[j]].to_dict())
            
            if not is_permutation_valid:
                invalid_routes_found += 1
                continue

            num_current_visits = len(current_route_segment)
            final_travel_time = current_travel_time + travel_from_last

            if num_current_visits > max_visits:
                max_visits = num_current_visits
                min_travel_time = final_travel_time
                best_route = current_route_segment
            elif num_current_visits == max_visits and final_travel_time < min_travel_time:
                min_travel_time = final_travel_time
                best_route = current_route_segment
        
        # Si ya encontramos una ruta, no necesitamos buscar rutas más cortas
        if best_route:
            break

    return best_route, max_visits, min_travel_time, invalid_routes_found

def generate_optimal_plan():
    """Función principal que orquesta la creación del plan para Martín."""
    with st.spinner("Analizando visitas y calculando rutas óptimas... Este proceso puede tardar un minuto."):
        today = date.today()
        start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
        end_of_next_week = start_of_next_week + timedelta(days=6)

        response = supabase.table('visitas').select('*, usuarios(id, nombre_completo)').eq(
            'status', 'Pendiente de Asignación'
        ).gte('fecha', start_of_next_week).lte('fecha', end_of_next_week).execute()

        candidate_visits = response.data
        if not candidate_visits:
            st.warning("No hay visitas 'Pendientes de Asignación' para la semana que viene.")
            return None, None

        df_visits = pd.DataFrame(candidate_visits)
        df_visits['nombre_coordinador'] = df_visits['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) and x else 'N/A')

        home_base = "Centro de Barcelona, Barcelona"
        unique_locations = list(df_visits['direccion_texto'].unique())
        all_locations = [home_base] + unique_locations
        dist_matrix = get_distance_matrix(all_locations)
        if not dist_matrix: return None, None

        final_plan = []
        available_visits_df = df_visits.copy()
        total_invalid_routes = 0

        for _ in range(3):
            if available_visits_df.empty: break
            
            day_route, _, _, invalid_count = find_best_day_route(available_visits_df, all_locations, dist_matrix)
            total_invalid_routes += invalid_count
            
            if day_route:
                final_plan.append(day_route)
                used_ids = [visit['id'] for visit in day_route]
                available_visits_df = available_visits_df[~available_visits_df['id'].isin(used_ids)]
        
        if total_invalid_routes > 0:
            st.warning(f"ℹ️ Se han descartado algunas rutas porque una o más direcciones podrían ser incorrectas o inaccesibles.")

        unassigned_visits = available_visits_df.to_dict('records')
        st.success(f"¡Propuesta generada con {len(final_plan)} días planificados!")
        return final_plan, unassigned_visits

def move_visit(visit_id, current_day, new_day):
    visit_to_move = None
    for i, visit in enumerate(st.session_state.supervisor_plan[current_day]):
        if visit['id'] == visit_id:
            visit_to_move = st.session_state.supervisor_plan[current_day].pop(i)
            break
    
    if visit_to_move:
        st.session_state.supervisor_plan[new_day].append(visit_to_move)

# --- INTERFAZ DE STREAMLIT ---
def mostrar_planificador_supervisor():
    st.header("Planificador Automático para Martín 🤖")

    # ### NUEVO: Diccionario para traducir días de la semana ###
    day_names_es = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"}

    if st.button("🤖 Generar Nueva Planificación Óptima", type="primary", use_container_width=True):
        plan, unassigned = generate_optimal_plan()
        if plan is not None:
            today = date.today()
            start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
            
            st.session_state.supervisor_plan = {
                'day_1': plan[0] if len(plan) > 0 else [],
                'day_2': plan[1] if len(plan) > 1 else [],
                'day_3': plan[2] if len(plan) > 2 else [],
                'unassigned': unassigned,
                'day_1_date': start_of_next_week,
                'day_2_date': start_of_next_week + timedelta(days=1),
                'day_3_date': start_of_next_week + timedelta(days=2),
            }
        st.session_state.plan_confirmed = False
        st.rerun()

    st.markdown("---")

    if 'supervisor_plan' in st.session_state and st.session_state.supervisor_plan:
        plan_state = st.session_state.supervisor_plan
        
        st.subheader("🗓️ Tablero de Planificación Manual")
        
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            with c1: plan_state['day_1_date'] = st.date_input("Fecha para Día 1", value=plan_state['day_1_date'], key="date1")
            with c2: plan_state['day_2_date'] = st.date_input("Fecha para Día 2", value=plan_state['day_2_date'], key="date2")
            with c3: plan_state['day_3_date'] = st.date_input("Fecha para Día 3", value=plan_state['day_3_date'], key="date3")

        st.markdown("---")
        day_keys = ['day_1', 'day_2', 'day_3']
        cols = st.columns(len(day_keys))

        for i, day_key in enumerate(day_keys):
            with cols[i]:
                day_date = plan_state[f'{day_key}_date']
                day_name_en = day_date.strftime('%A')
                day_name_es = day_names_es.get(day_name_en, day_name_en) # Usar traductor
                st.markdown(f"#### Día {i+1} ({day_name_es})")
                
                total_seconds = len(plan_state[day_key]) * 45 * 60 + (len(plan_state[day_key]) + 1) * 30 * 60
                total_hours = total_seconds / 3600
                st.info(f"{len(plan_state[day_key])} visitas | Est: {total_hours:.1f}h")

                if day_date.weekday() == 4 and total_hours > 7:
                    st.warning("⚠️ El plan excede las 7h para un viernes.")

                for visit in plan_state[day_key]:
                    with st.container(border=True):
                        st.markdown(f"**📍 {visit['direccion_texto']}**")
                        st.caption(f"De: {visit['nombre_coordinador']}")
                        
                        new_location_key = st.selectbox("Mover a:", options=['day_1', 'day_2', 'day_3', 'unassigned'], format_func=lambda x: {'day_1':'Día 1', 'day_2':'Día 2', 'day_3':'Día 3', 'unassigned':'No Asignada'}.get(x), index=i, key=f"move_{visit['id']}")
                        if new_location_key != day_key:
                            move_visit(visit['id'], day_key, new_location_key)
                            st.rerun()

        # ### INICIO DE LA NUEVA SECCIÓN DE VISITAS NO ASIGNADAS ###
        with st.expander(f"Visitas No Asignadas ({len(plan_state['unassigned'])})", expanded=True):
            st.markdown("##### Vista de Calendario de Propuestas")
            
            calendar_events = []
            if plan_state['unassigned']:
                for visit in plan_state['unassigned']:
                    franja = visit.get('franja_horaria')
                    if not franja or not isinstance(franja, str): continue
                    horas = re.findall(r'(\d{2}:\d{2})', franja)
                    if len(horas) == 2:
                        start_time_str, end_time_str = horas
                        start_dt = datetime.combine(pd.to_datetime(visit['fecha']).date(), datetime.strptime(start_time_str, '%H:%M').time())
                        end_dt = datetime.combine(pd.to_datetime(visit['fecha']).date(), datetime.strptime(end_time_str, '%H:%M').time())
                        title = f"{visit['direccion_texto']} ({visit['nombre_coordinador']})"
                        calendar_events.append({"title": title, "start": start_dt.isoformat(), "end": end_dt.isoformat()})
                
                cal_start_date = pd.to_datetime(plan_state['unassigned'][0]['fecha']).date() if plan_state['unassigned'] else date.today()
                calendar(events=calendar_events, options={"initialView": "timeGridWeek", "initialDate": cal_start_date.isoformat()}, key='unassigned_cal')
            else:
                st.info("No hay visitas sin asignar.")
            
            st.markdown("---")
            st.markdown("##### Acciones de Asignación")
            for visit in sorted(plan_state['unassigned'], key=lambda x: x['fecha']):
                with st.container(border=True):
                    # Mostrar toda la información
                    fecha_propuesta = pd.to_datetime(visit['fecha']).strftime('%d/%m/%Y')
                    st.markdown(f"**📍 {visit['direccion_texto']}**")
                    st.caption(f"**Propuesto por:** {visit['nombre_coordinador']} | **Equipo:** {visit['equipo']} | **Fecha Prop.:** {fecha_propuesta} ({visit['franja_horaria']})")

                    new_location_key = st.selectbox("Mover a:", options=['unassigned', 'day_1', 'day_2', 'day_3'], format_func=lambda x: {'day_1':'Día 1', 'day_2':'Día 2', 'day_3':'Día 3', 'unassigned':'No Asignada'}.get(x), index=0, key=f"move_{visit['id']}")
                    if new_location_key != 'unassigned':
                        move_visit(visit['id'], 'unassigned', new_location_key)
                        st.rerun()
        # ### FIN DE LA NUEVA SECCIÓN ###

        st.markdown("---")

        if 'plan_confirmed' not in st.session_state: st.session_state.plan_confirmed = False

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Confirmar y Asignar Plan", type="primary", use_container_width=True, disabled=st.session_state.plan_confirmed):
                with st.spinner("Confirmando y actualizando la base de datos..."):
                    all_final_visits = plan_state['day_1'] + plan_state['day_2'] + plan_state['day_3']
                    if all_final_visits:
                        final_locations = [ "Centro de Barcelona, Barcelona" ] + list(pd.DataFrame(all_final_visits)['direccion_texto'].unique())
                        final_dist_matrix = get_distance_matrix(final_locations)
                    else: final_dist_matrix = None

                    for i, day_key in enumerate(day_keys):
                        assigned_date = plan_state[f'{day_key}_date']
                        current_time_dt = datetime.combine(assigned_date, time(8, 0))
                        last_location = "Centro de Barcelona, Barcelona"

                        for visit in sorted(plan_state[day_key], key=lambda v: v['id']): # Sort for consistency
                            if final_dist_matrix:
                                current_loc_idx = final_locations.index(visit['direccion_texto'])
                                last_loc_idx = final_locations.index(last_location)
                                travel_element = final_dist_matrix['rows'][last_loc_idx]['elements'][current_loc_idx]
                                if travel_element['status'] == 'OK':
                                    current_time_dt += timedelta(seconds=travel_element['duration']['value'])
                            
                            supabase.table('visitas').update({'status': 'Asignada a Supervisor', 'fecha_asignada': str(assigned_date), 'hora_asignada': current_time_dt.strftime('%H:%M')}).eq('id', visit['id']).execute()
                            
                            current_time_dt += timedelta(minutes=45)
                            last_location = visit['direccion_texto']

                    st.session_state.plan_confirmed = True
                    st.success("¡Plan confirmado y asignado en la base de datos!")
                    st.rerun()

        with col2:
            if st.session_state.plan_confirmed:
                if st.button("📧 Notificar a Coordinadores", use_container_width=True):
                    res_users = supabase.table('usuarios').select('email').in_('rol', ['coordinador', 'supervisor']).execute()
                    all_emails = [user['email'] for user in res_users.data if user['email']]
                    
                    if not all_emails:
                        st.error("No se encontraron correos de coordinadores para notificar.")
                    else:
                        body = "<h3>Resumen de visitas asignadas a Martín</h3><p>¡Hola equipo! Martín se encargará de las siguientes visitas:</p>"
                        for i, day_key in enumerate(day_keys):
                             day_date = plan_state[f'{day_key}_date']
                             day_str_en = day_date.strftime('%A')
                             day_str_es = day_names_es.get(day_str_en, day_str_en)
                             day_str_full = f"{day_str_es}, {day_date.strftime('%d/%m/%Y')}"

                             if plan_state[day_key]:
                                 body += f"<h4>{day_str_full}:</h4><ul>"
                                 for visit in plan_state[day_key]:
                                     body += f"<li>{visit['direccion_texto']} (propuesto por {visit['nombre_coordinador']})</li>"
                                 body += "</ul>"
                        body += "<p>Saludos,<br>Sistema de Planificación</p>"

                        send_email(all_emails, f"Planificación de Martín - Semana del {plan_state['day_1_date'].strftime('%d/%m')}", body)