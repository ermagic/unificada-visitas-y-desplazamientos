# Fichero: supervisor.py (Versión corregida con algoritmo funcional y horarios de viernes)
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
import math

# --- FUNCIÓN PARA ENVIAR EMAILS ---
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

# --- LÓGICA DEL MOTOR DE PLANIFICACIÓN CORREGIDA ---
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

def calculate_day_time_budget(day_date):
    """Calcula el tiempo disponible según el día (7h viernes, 8h otros días)."""
    if day_date.weekday() == 4:  # Viernes
        return 7 * 3600  # 7 horas en segundos
    else:
        return 8 * 3600  # 8 horas en segundos

def optimize_single_day(visits_for_day, home_base, dist_matrix, all_locations):
    """Encuentra la mejor ruta para un día específico usando algoritmo TSP simplificado."""
    if not visits_for_day:
        return [], 0, 0
    
    day_date = visits_for_day.iloc[0]['fecha'] if hasattr(visits_for_day.iloc[0]['fecha'], 'weekday') else pd.to_datetime(visits_for_day.iloc[0]['fecha']).date()
    time_budget = calculate_day_time_budget(day_date)
    visit_duration = 45 * 60  # 45 minutos en segundos
    
    best_route = []
    best_visit_count = 0
    best_total_time = 0
    
    # Probar diferentes órdenes de visita
    for num_visits in range(min(len(visits_for_day), 8), 0, -1):  # Máximo 8 visitas por día
        for visit_combination in itertools.combinations(visits_for_day.index, num_visits):
            for visit_order in itertools.permutations(visit_combination):
                current_time = 0
                current_route = []
                last_location = home_base
                valid_route = True
                
                # Tiempo desde base hasta primera visita
                first_visit = visits_for_day.loc[visit_order[0]]
                first_loc_idx = all_locations.index(first_visit['direccion_texto'])
                base_to_first = dist_matrix['rows'][0]['elements'][first_loc_idx]
                
                if base_to_first['status'] != 'OK':
                    continue
                
                current_time += base_to_first['duration']['value']
                
                for i, visit_idx in enumerate(visit_order):
                    visit = visits_for_day.loc[visit_idx]
                    
                    # Tiempo de visita
                    current_time += visit_duration
                    
                    # Verificar si aún tenemos tiempo
                    if current_time > time_budget:
                        valid_route = False
                        break
                    
                    current_route.append(visit.to_dict())
                    
                    # Tiempo hasta siguiente visita (excepto para la última)
                    if i < len(visit_order) - 1:
                        next_visit = visits_for_day.loc[visit_order[i + 1]]
                        current_loc_idx = all_locations.index(visit['direccion_texto'])
                        next_loc_idx = all_locations.index(next_visit['direccion_texto'])
                        travel_time = dist_matrix['rows'][current_loc_idx]['elements'][next_loc_idx]
                        
                        if travel_time['status'] != 'OK':
                            valid_route = False
                            break
                        
                        current_time += travel_time['duration']['value']
                
                # Tiempo de regreso a base para la última visita
                if valid_route and current_route:
                    last_visit = current_route[-1]
                    last_loc_idx = all_locations.index(last_visit['direccion_texto'])
                    return_to_base = dist_matrix['rows'][last_loc_idx]['elements'][0]
                    
                    if return_to_base['status'] != 'OK':
                        continue
                    
                    total_time_with_return = current_time + return_to_base['duration']['value']
                    
                    if total_time_with_return <= time_budget:
                        if len(current_route) > best_visit_count or (
                            len(current_route) == best_visit_count and total_time_with_return < best_total_time):
                            best_route = current_route
                            best_visit_count = len(current_route)
                            best_total_time = total_time_with_return
        
        # Si encontramos una ruta con este número de visitas, es probablemente la mejor
        if best_route:
            break
    
    return best_route, best_visit_count, best_total_time

def generate_optimal_plan():
    """Función principal que orquesta la creación del plan para Martín."""
    with st.spinner("Analizando visitas y calculando rutas óptimas... Este proceso puede tardar unos minutos."):
        today = date.today()
        start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
        end_of_next_week = start_of_next_week + timedelta(days=6)
        
        st.info(f"Buscando visitas para la semana del {start_of_next_week.strftime('%d/%m/%Y')} al {end_of_next_week.strftime('%d/%m/%Y')}")

        # Obtener visitas pendientes de asignación
        response = supabase.table('visitas').select('*, usuarios(nombre_completo)').eq(
            'status', 'Pendiente de Asignación'
        ).gte('fecha', start_of_next_week).lte('fecha', end_of_next_week).execute()

        candidate_visits = response.data
        if not candidate_visits:
            st.warning("No hay visitas 'Pendientes de Asignación' para la semana que viene.")
            return None, None

        df_visits = pd.DataFrame(candidate_visits)
        df_visits['nombre_coordinador'] = df_visits['usuarios'].apply(
            lambda x: x['nombre_completo'] if isinstance(x, dict) and x else 'N/A'
        )
        df_visits['fecha'] = pd.to_datetime(df_visits['fecha']).dt.date

        home_base = "Plaza Catalunya, Barcelona, Spain"
        unique_locations = list(df_visits['direccion_texto'].unique())
        all_locations = [home_base] + unique_locations
        
        st.info(f"Analizando {len(df_visits)} visitas en {len(unique_locations)} ubicaciones diferentes")
        
        dist_matrix = get_distance_matrix(all_locations)
        if not dist_matrix:
            st.error("Error al calcular distancias. Verifica las direcciones.")
            return None, None

        # Planificar por días de la semana
        days_plan = {}
        available_visits_df = df_visits.copy()
        
        # Ordenar días por potencial (más visitas disponibles primero)
        days_priority = []
        for day_offset in range(5):  # Lunes a Viernes
            day_date = start_of_next_week + timedelta(days=day_offset)
            visits_for_day = available_visits_df[available_visits_df['fecha'] == day_date]
            days_priority.append((day_date, len(visits_for_day)))
        
        # Ordenar días por número de visitas disponibles (descendente)
        days_priority.sort(key=lambda x: x[1], reverse=True)
        
        # Planificar los 3 mejores días
        final_plan = {}
        for i in range(min(3, len(days_priority))):
            day_date, visit_count = days_priority[i]
            visits_for_day = available_visits_df[available_visits_df['fecha'] == day_date]
            
            if not visits_for_day.empty:
                day_route, visit_count, total_time = optimize_single_day(
                    visits_for_day, home_base, dist_matrix, all_locations
                )
                
                if day_route:
                    final_plan[day_date] = day_route
                    # Remover visitas asignadas de las disponibles
                    used_ids = [visit['id'] for visit in day_route]
                    available_visits_df = available_visits_df[~available_visits_df['id'].isin(used_ids)]
                    
                    hours = total_time / 3600
                    st.success(f"Día {i+1}: {day_date.strftime('%A %d/%m')} - {visit_count} visitas ({hours:.1f}h)")

        unassigned_visits = available_visits_df.to_dict('records')
        
        if final_plan:
            st.success(f"¡Planificación generada! {sum(len(visits) for visits in final_plan.values())} visitas asignadas en {len(final_plan)} días.")
        else:
            st.warning("No se pudo generar ninguna planificación automática.")
            
        return final_plan, unassigned_visits

def move_visit(visit_id, current_day, new_day):
    """Mueve una visita entre días en la planificación."""
    visit_to_move = None
    
    if current_day in st.session_state.supervisor_plan:
        for i, visit in enumerate(st.session_state.supervisor_plan[current_day]):
            if visit['id'] == visit_id:
                visit_to_move = st.session_state.supervisor_plan[current_day].pop(i)
                break
    
    if visit_to_move:
        if new_day not in st.session_state.supervisor_plan:
            st.session_state.supervisor_plan[new_day] = []
        st.session_state.supervisor_plan[new_day].append(visit_to_move)

# --- INTERFAZ DE STREAMLIT MEJORADA ---
def mostrar_planificador_supervisor():
    st.header("Planificador Automático para Martín 🤖")
    
    # Diccionario para traducir días de la semana
    day_names_es = {
        "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", 
        "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
    }

    # Botón para generar nueva planificación
    if st.button("🤖 Generar Nueva Planificación Óptima", type="primary", use_container_width=True):
        plan, unassigned = generate_optimal_plan()
        
        if plan is not None:
            # Convertir el plan a la estructura esperada por la interfaz
            day_keys = []
            supervisor_plan = {'unassigned': unassigned}
            
            for i, (day_date, visits) in enumerate(plan.items()):
                day_key = f'day_{i+1}'
                day_keys.append(day_key)
                supervisor_plan[day_key] = visits
                supervisor_plan[f'{day_key}_date'] = day_date
            
            # Completar con días vacíos si es necesario
            for i in range(len(day_keys), 3):
                day_key = f'day_{i+1}'
                empty_date = date.today() + timedelta(days=(7 - date.today().weekday() + i))
                supervisor_plan[day_key] = []
                supervisor_plan[f'{day_key}_date'] = empty_date
            
            st.session_state.supervisor_plan = supervisor_plan
            st.session_state.plan_confirmed = False
            st.rerun()

    st.markdown("---")

    # Mostrar planificación actual si existe
    if 'supervisor_plan' in st.session_state and st.session_state.supervisor_plan:
        plan_state = st.session_state.supervisor_plan
        
        st.subheader("🗓️ Tablero de Planificación Manual")
        
        # Selector de fechas para los 3 días
        with st.container(border=True):
            cols = st.columns(3)
            day_keys = ['day_1', 'day_2', 'day_3']
            
            for i, day_key in enumerate(day_keys):
                with cols[i]:
                    current_date = plan_state.get(f'{day_key}_date', date.today() + timedelta(days=i))
                    plan_state[f'{day_key}_date'] = st.date_input(
                        f"Fecha para Día {i+1}", 
                        value=current_date, 
                        key=f"date_{i+1}"
                    )

        st.markdown("---")
        
        # Mostrar los 3 días de planificación
        cols = st.columns(3)
        for i, day_key in enumerate(day_keys):
            with cols[i]:
                day_date = plan_state[f'{day_key}_date']
                day_name_en = day_date.strftime('%A')
                day_name_es = day_names_es.get(day_name_en, day_name_en)
                
                st.markdown(f"#### Día {i+1} ({day_name_es})")
                
                # Calcular tiempo total del día
                visits_count = len(plan_state.get(day_key, []))
                time_budget = calculate_day_time_budget(day_date)
                total_hours = time_budget / 3600
                
                st.info(f"{visits_count} visitas | Máximo: {total_hours}h")
                
                # Advertencia si se excede el horario de viernes
                if day_date.weekday() == 4 and visits_count > 0:
                    estimated_time = visits_count * 0.75  # 45 minutos por visita
                    if estimated_time > 7:
                        st.warning("⚠️ El plan podría exceder las 7h de un viernes")

                # Mostrar visitas asignadas a este día
                for visit in plan_state.get(day_key, []):
                    with st.container(border=True):
                        st.markdown(f"**📍 {visit['direccion_texto']}**")
                        st.caption(f"De: {visit['nombre_coordinador']}")
                        st.caption(f"Equipo: {visit.get('equipo', 'N/A')}")
                        
                        # Selector para mover visita
                        new_location = st.selectbox(
                            "Mover a:",
                            options=day_keys + ['unassigned'],
                            format_func=lambda x: {
                                'day_1': 'Día 1', 'day_2': 'Día 2', 'day_3': 'Día 3', 
                                'unassigned': 'No Asignada'
                            }.get(x),
                            index=i if day_key in day_keys else 3,
                            key=f"move_{visit['id']}_{day_key}"
                        )
                        
                        if new_location != day_key:
                            move_visit(visit['id'], day_key, new_location)
                            st.rerun()

        # Sección de visitas no asignadas
        with st.expander(f"📋 Visitas No Asignadas ({len(plan_state.get('unassigned', []))})", expanded=True):
            if plan_state.get('unassigned'):
                st.markdown("##### Visitas disponibles para asignar:")
                
                for visit in plan_state['unassigned']:
                    with st.container(border=True):
                        fecha_propuesta = visit['fecha'] if isinstance(visit['fecha'], str) else visit['fecha'].strftime('%d/%m/%Y')
                        st.markdown(f"**📍 {visit['direccion_texto']}**")
                        st.caption(f"**Propuesto por:** {visit['nombre_coordinador']} | **Fecha:** {fecha_propuesta}")
                        st.caption(f"**Franja:** {visit.get('franja_horaria', 'N/A')} | **Equipo:** {visit.get('equipo', 'N/A')}")
                        
                        new_location = st.selectbox(
                            "Asignar a:",
                            options=['unassigned'] + day_keys,
                            format_func=lambda x: {
                                'day_1': 'Día 1', 'day_2': 'Día 2', 'day_3': 'Día 3', 
                                'unassigned': 'No Asignada'
                            }.get(x),
                            key=f"assign_{visit['id']}"
                        )
                        
                        if new_location != 'unassigned':
                            move_visit(visit['id'], 'unassigned', new_location)
                            st.rerun()
            else:
                st.info("No hay visitas sin asignar.")

        st.markdown("---")

        # Botones de confirmación y notificación
        if 'plan_confirmed' not in st.session_state:
            st.session_state.plan_confirmed = False

        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✅ Confirmar y Asignar Plan", type="primary", use_container_width=True, disabled=st.session_state.plan_confirmed):
                with st.spinner("Confirmando planificación en la base de datos..."):
                    try:
                        # Actualizar cada visita asignada
                        for day_key in day_keys:
                            day_date = plan_state[f'{day_key}_date']
                            visits = plan_state.get(day_key, [])
                            
                            # Ordenar visitas por proximidad (simulación)
                            for i, visit in enumerate(visits):
                                # Asignar horas aproximadas (empezando a las 8:00)
                                start_time = datetime.combine(day_date, time(8, 0)) + timedelta(minutes=i * 60)
                                
                                supabase.table('visitas').update({
                                    'status': 'Asignada a Supervisor',
                                    'fecha_asignada': str(day_date),
                                    'hora_asignada': start_time.strftime('%H:%M')
                                }).eq('id', visit['id']).execute()

                        st.session_state.plan_confirmed = True
                        st.success("¡Planificación confirmada y asignada en la base de datos!")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Error al actualizar la base de datos: {e}")

        with col2:
            if st.session_state.plan_confirmed:
                if st.button("📧 Notificar a Coordinadores", use_container_width=True):
                    # Obtener emails de coordinadores
                    res_users = supabase.table('usuarios').select('email, nombre_completo').in_('rol', ['coordinador', 'supervisor']).execute()
                    all_emails = [user['email'] for user in res_users.data if user['email']]
                    
                    if not all_emails:
                        st.error("No se encontraron correos para notificar.")
                    else:
                        # Crear cuerpo del email
                        body = f"""
                        <h3>📅 Planificación de Visitas - {date.today().strftime('%d/%m/%Y')}</h3>
                        <p>¡Hola equipo!</p>
                        <p>Martín ha confirmado su planificación para la próxima semana:</p>
                        """
                        
                        for day_key in day_keys:
                            day_date = plan_state[f'{day_key}_date']
                            visits = plan_state.get(day_key, [])
                            
                            if visits:
                                day_name_es = day_names_es.get(day_date.strftime('%A'), day_date.strftime('%A'))
                                body += f"<h4>🗓️ {day_name_es} {day_date.strftime('%d/%m')}:</h4><ul>"
                                
                                for visit in visits:
                                    body += f"<li><strong>{visit['direccion_texto']}</strong> (propuesto por {visit['nombre_coordinador']})</li>"
                                
                                body += "</ul>"
                        
                        body += f"""
                        <p>Total de visitas asignadas a Martín: <strong>{sum(len(plan_state.get(day_key, [])) for day_key in day_keys)}</strong></p>
                        <p>Saludos,<br>Sistema de Planificación Automática</p>
                        """
                        
                        if send_email(all_emails, f"Planificación de Martín - Semana del {plan_state['day_1_date'].strftime('%d/%m')}", body):
                            st.success("Notificación enviada correctamente.")

    else:
        st.info("👆 Usa el botón 'Generar Nueva Planificación Óptima' para comenzar. El sistema analizará todas las visitas pendientes y creará una planificación optimizada para Martín.")
        
        # Mostrar estadísticas de visitas pendientes
        today = date.today()
        start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
        
        response = supabase.table('visitas').select('*').eq('status', 'Pendiente de Asignación').gte('fecha', start_of_next_week).execute()
        pending_visits = response.data if response.data else []
        
        if pending_visits:
            st.metric("Visitas pendientes de asignación", len(pending_visits))
        else:
            st.warning("No hay visitas pendientes de asignación para la próxima semana.")