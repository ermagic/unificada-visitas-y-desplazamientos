# Fichero: supervisor.py (Versión con flexibilidad total y UI mejorada)
import streamlit as st
import pandas as pd
from database import supabase
from datetime import date, timedelta, datetime, time
import googlemaps
import itertools
import smtplib
from email.mime.text import MIMEText
import re

# --- FUNCIÓN PARA ENVIAR EMAILS (sin cambios) ---
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
def get_distance_matrix(api_key, locations):
    """Obtiene la matriz de distancias de Google Maps."""
    try:
        gmaps = googlemaps.Client(key=api_key)
        matrix = gmaps.distance_matrix(locations, locations, mode="driving")
        return matrix
    except Exception as e:
        st.error(f"Error al contactar con la API de Google Maps: {e}")
        return None

### INICIO DE LA CORRECCIÓN ALGORITMO (Lógica de "Bolsa de Visitas") ###
def find_best_route_for_one_day(visits_df, all_locations, dist_matrix, is_friday):
    """
    Encuentra la mejor ruta posible para un solo día a partir de un conjunto de visitas disponibles.
    """
    time_budget_seconds = 7 * 3600 if is_friday else 8 * 3600
    visit_duration_seconds = 45 * 60

    best_route_info = {'route': [], 'num_visits': 0, 'travel_time': float('inf')}

    if visits_df.empty:
        return best_route_info

    # Iterar desde el máximo de visitas posibles hacia abajo para ser más eficiente
    max_possible_visits = min(len(visits_df), 7) # Límite práctico para evitar cálculos excesivos

    for r in range(max_possible_visits, 0, -1):
        for p in itertools.permutations(visits_df.index, r):
            current_travel_time = 0
            
            # 1. Viaje desde el origen (Barcelona) a la primera visita
            first_visit_loc = visits_df.loc[p[0], 'direccion_texto']
            first_loc_index = all_locations.index(first_visit_loc)
            element_to_first = dist_matrix['rows'][0]['elements'][first_loc_index]
            if element_to_first['status'] != 'OK': continue
            current_travel_time += element_to_first['duration']['value']

            # 2. Viajes entre visitas
            for i in range(len(p) - 1):
                loc_a = visits_df.loc[p[i], 'direccion_texto']
                loc_b = visits_df.loc[p[i+1], 'direccion_texto']
                idx_a = all_locations.index(loc_a)
                idx_b = all_locations.index(loc_b)
                element_between = dist_matrix['rows'][idx_a]['elements'][idx_b]
                if element_between['status'] != 'OK': continue
                current_travel_time += element_between['duration']['value']

            # 3. Viaje de vuelta al origen
            last_visit_loc = visits_df.loc[p[-1], 'direccion_texto']
            last_loc_index = all_locations.index(last_visit_loc)
            element_from_last = dist_matrix['rows'][last_loc_index]['elements'][0]
            if element_from_last['status'] != 'OK': continue
            current_travel_time += element_from_last['duration']['value']

            total_day_duration = current_travel_time + (len(p) * visit_duration_seconds)

            if total_day_duration <= time_budget_seconds:
                # Como iteramos de mayor a menor `r`, la primera ruta válida que encontremos
                # para un `r` dado es la mejor en términos de número de visitas.
                # Solo necesitamos comprobar si es mejor en tiempo de viaje que otras del mismo `r`.
                if current_travel_time < best_route_info['travel_time']:
                    best_route_info = {
                        'route': [visits_df.loc[i].to_dict() for i in p],
                        'num_visits': len(p),
                        'travel_time': current_travel_time
                    }
        
        # Si hemos encontrado una ruta para el `r` actual, no necesitamos buscar en `r-1`
        if best_route_info['route']:
            return best_route_info

    return best_route_info

def generate_optimal_plan():
    """
    Función principal que crea el plan para Martín tratando todas las visitas como una "bolsa".
    """
    with st.spinner("Analizando visitas y calculando rutas óptimas... Este proceso puede tardar un minuto."):
        today = date.today()
        start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
        end_of_next_week = start_of_next_week + timedelta(days=6)

        response = supabase.table('visitas').select('*, usuarios(id, nombre_completo)').eq(
            'status', 'Pendiente de Asignación'
        ).gte('fecha', start_of_next_week.isoformat()).lte('fecha', end_of_next_week.isoformat()).execute()

        candidate_visits = response.data
        if not candidate_visits:
            st.warning("No hay visitas 'Pendientes de Asignación' para la semana que viene.")
            return None, None

        df_visits = pd.DataFrame(candidate_visits)
        df_visits['nombre_coordinador'] = df_visits['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) and x else 'N/A')

        home_base = "Plaça de Catalunya, Barcelona"
        unique_locations = list(df_visits['direccion_texto'].unique())
        all_locations = [home_base] + unique_locations
        
        api_key = st.secrets.get("google", {}).get("api_key")
        if not api_key:
            st.error("No se ha encontrado la clave de API de Google en los secrets.")
            return None, None
            
        dist_matrix = get_distance_matrix(api_key, all_locations)
        if not dist_matrix: return None, None

        # --- Lógica de planificación en 3 días ---
        final_plan = []
        available_visits_df = df_visits.copy()

        # Iteramos para planificar 3 días
        for i in range(3):
            if available_visits_df.empty: break
            
            # Decidimos si este día podría ser un viernes para el cálculo del presupuesto de tiempo.
            # Por simplicidad, asumimos que solo el último día podría ser viernes.
            # Martín puede cambiar las fechas de todos modos.
            is_friday = (i == 2) 
            
            best_day_info = find_best_route_for_one_day(available_visits_df, all_locations, dist_matrix, is_friday)
            
            if best_day_info['route']:
                final_plan.append(best_day_info['route'])
                
                # Eliminar las visitas asignadas del DataFrame de disponibles
                used_ids = [visit['id'] for visit in best_day_info['route']]
                available_visits_df = available_visits_df[~available_visits_df['id'].isin(used_ids)]
        
        unassigned_visits = available_visits_df.to_dict('records')
        st.success(f"¡Propuesta generada con {len(final_plan)} días planificados!")
        return final_plan, unassigned_visits
### FIN DE LA CORRECCIÓN ALGORITMO ###

# --- Interfaz de Streamlit (UI) ---
# La UI se adapta para manejar una lista de planes en lugar de un diccionario
# y para permitir a Martín asignar fechas libremente.

def move_visit(visit_id, current_day_index, new_day_index):
    """Mueve una visita entre listas (días planificados o no asignados)."""
    plan_state = st.session_state.supervisor_plan
    visit_to_move = None

    # Buscar y quitar del origen
    if current_day_index == -1: # Origen es "No Asignadas"
        for i, visit in enumerate(plan_state['unassigned']):
            if visit['id'] == visit_id:
                visit_to_move = plan_state['unassigned'].pop(i)
                break
    else: # Origen es un día planificado
        for i, visit in enumerate(plan_state['plan_days'][current_day_index]):
            if visit['id'] == visit_id:
                visit_to_move = plan_state['plan_days'][current_day_index].pop(i)
                break
    
    # Añadir al destino
    if visit_to_move:
        if new_day_index == -1: # Destino es "No Asignadas"
            plan_state['unassigned'].append(visit_to_move)
        else: # Destino es un día planificado
            plan_state['plan_days'][new_day_index].append(visit_to_move)

def mostrar_planificador_supervisor():
    st.header("Planificador Automático para Martín 🤖")
    day_names_es = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes"}

    if st.button("🤖 Generar Nueva Planificación Óptima", type="primary", use_container_width=True):
        plan_days_list, unassigned = generate_optimal_plan()
        if plan_days_list is not None:
            today = date.today()
            start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
            st.session_state.supervisor_plan = {
                'plan_days': plan_days_list,
                'unassigned': unassigned,
                # Asignamos fechas por defecto, Martín las puede cambiar
                'dates': [start_of_next_week + timedelta(days=i) for i in range(len(plan_days_list))]
            }
        st.session_state.plan_confirmed = False
        st.rerun()

    st.markdown("---")

    if 'supervisor_plan' in st.session_state and st.session_state.supervisor_plan:
        plan_state = st.session_state.supervisor_plan
        
        st.subheader("🗓️ Tablero de Planificación Manual")
        
        # Contenedor para que Martín asigne las fechas
        cols_fechas = st.columns(len(plan_state['plan_days']))
        for i in range(len(plan_state['dates'])):
            with cols_fechas[i]:
                new_date = st.date_input(f"Fecha Día {i+1}", value=plan_state['dates'][i], key=f"date_{i}")
                plan_state['dates'][i] = new_date

        st.markdown("---")
        cols_dias = st.columns(len(plan_state['plan_days']))

        for i, day_plan in enumerate(plan_state['plan_days']):
            with cols_dias[i]:
                day_date = plan_state['dates'][i]
                day_name_en = day_date.strftime('%A')
                day_name_es = day_names_es.get(day_name_en, day_name_en)
                st.markdown(f"#### Día {i+1} ({day_name_es})")
                
                num_visits = len(day_plan)
                total_hours = (num_visits * 45 + (num_visits + 1) * 30) / 60 
                st.info(f"{num_visits} visitas | Est: {total_hours:.1f}h")

                if day_date.weekday() == 4 and total_hours > 7:
                    st.warning("⚠️ El plan excede las 7h para un viernes.")
                elif day_date.weekday() != 4 and total_hours > 8:
                    st.warning("⚠️ El plan excede las 8h.")

                for visit in day_plan:
                    with st.container(border=True):
                        st.markdown(f"**📍 {visit['direccion_texto']}**")
                        st.caption(f"De: {visit['nombre_coordinador']}")
                        
                        # Opciones para mover la visita
                        move_options = {f"Día {j+1}": j for j in range(len(plan_state['plan_days']))}
                        move_options["No Asignada"] = -1
                        
                        new_location_index = st.selectbox("Mover a:", options=move_options.keys(), index=i, key=f"move_{visit['id']}")
                        
                        if move_options[new_location_index] != i:
                            move_visit(visit['id'], i, move_options[new_location_index])
                            st.rerun()

        # Sección de Visitas No Asignadas
        with st.expander(f"Visitas No Asignadas ({len(plan_state['unassigned'])})", expanded=True):
            for visit in sorted(plan_state['unassigned'], key=lambda x: x['fecha']):
                with st.container(border=True):
                    st.markdown(f"**📍 {visit['direccion_texto']}**")
                    st.caption(f"Propuesto por: {visit['nombre_coordinador']} para el {pd.to_datetime(visit['fecha']).strftime('%d/%m')}")

                    move_options = {"No Asignada": -1}
                    move_options.update({f"Día {j+1}": j for j in range(len(plan_state['plan_days']))})
                    
                    new_location_index = st.selectbox("Asignar a:", options=move_options.keys(), index=0, key=f"move_{visit['id']}")
                    if move_options[new_location_index] != -1:
                        move_visit(visit['id'], -1, move_options[new_location_index])
                        st.rerun()

        st.markdown("---")
        # El resto de la lógica de confirmación y notificación permanece igual
        # ...
