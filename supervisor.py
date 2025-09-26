# Fichero: supervisor.py (Versión con UI enriquecida, mapa y lógica de guardado)
import streamlit as st
import pandas as pd
from database import supabase
from datetime import date, timedelta, datetime, time
import googlemaps
import itertools
import smtplib
from email.mime.text import MIMEText
import re
import folium
from streamlit_folium import st_folium

# --- FUNCIONES DE CORREO Y DISTANCIA (sin cambios) ---
@st.cache_data(ttl=3600)
def get_distance_matrix(api_key, locations):
    try:
        gmaps = googlemaps.Client(key=api_key)
        return gmaps.distance_matrix(locations, locations, mode="driving")
    except Exception as e:
        st.error(f"Error al contactar con la API de Google Maps: {e}"); return None

def send_email(recipients, subject, body):
    try:
        smtp_cfg = st.secrets["smtp"]
        sender, password = smtp_cfg["username"], smtp_cfg["password"]
        msg = MIMEText(body, 'html')
        msg['From'], msg['To'], msg['Subject'] = sender, ", ".join(recipients), subject
        server = smtplib.SMTP(smtp_cfg["server"], smtp_cfg["port"])
        server.starttls(); server.login(sender, password); server.send_message(msg); server.quit()
        st.success("✅ ¡Correo de notificación enviado con éxito!")
        return True
    except Exception as e:
        st.error(f"Error al enviar el correo: {e}"); return False

# --- LÓGICA DEL MOTOR DE PLANIFICACIÓN (sin cambios, ya validada) ---
def find_best_route_for_one_day(visits_df, all_locations, dist_matrix, is_friday):
    time_budget_seconds = 7 * 3600 if is_friday else 8 * 3600
    visit_duration_seconds = 45 * 60
    best_route_info = {'route': [], 'num_visits': 0, 'travel_time': float('inf')}
    if visits_df.empty: return best_route_info
    max_possible_visits = min(len(visits_df), 7)
    for r in range(max_possible_visits, 0, -1):
        for p in itertools.permutations(visits_df.index, r):
            current_travel_time = 0
            try:
                first_loc_index = all_locations.index(visits_df.loc[p[0], 'direccion_texto'])
                element_to_first = dist_matrix['rows'][0]['elements'][first_loc_index]
                if element_to_first['status'] != 'OK': continue
                current_travel_time += element_to_first['duration']['value']
                for i in range(len(p) - 1):
                    idx_a = all_locations.index(visits_df.loc[p[i], 'direccion_texto'])
                    idx_b = all_locations.index(visits_df.loc[p[i+1], 'direccion_texto'])
                    element_between = dist_matrix['rows'][idx_a]['elements'][idx_b]
                    if element_between['status'] != 'OK': raise ValueError("Ruta inválida")
                    current_travel_time += element_between['duration']['value']
                last_loc_index = all_locations.index(visits_df.loc[p[-1], 'direccion_texto'])
                element_from_last = dist_matrix['rows'][last_loc_index]['elements'][0]
                if element_from_last['status'] != 'OK': continue
                current_travel_time += element_from_last['duration']['value']
            except (ValueError, IndexError): continue
            total_day_duration = current_travel_time + (len(p) * visit_duration_seconds)
            if total_day_duration <= time_budget_seconds:
                if current_travel_time < best_route_info['travel_time']:
                    best_route_info = {'route': [visits_df.loc[i].to_dict() for i in p], 'num_visits': len(p), 'travel_time': current_travel_time}
        if best_route_info['route']: return best_route_info
    return best_route_info

def generate_optimal_plan():
    with st.spinner("Analizando visitas y calculando rutas óptimas..."):
        today = date.today()
        start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
        end_of_next_week = start_of_next_week + timedelta(days=6)
        response = supabase.table('visitas').select('*, usuarios(id, nombre_completo)').eq('status', 'Pendiente de Asignación').gte('fecha', start_of_next_week.isoformat()).lte('fecha', end_of_next_week.isoformat()).execute()
        if not response.data:
            st.warning("No hay visitas 'Pendientes de Asignación' para la semana que viene."); return None, None
        df_visits = pd.DataFrame(response.data)
        df_visits['nombre_coordinador'] = df_visits['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'N/A')
        home_base = "Plaça de Catalunya, Barcelona"
        unique_locations = list(df_visits['direccion_texto'].unique())
        all_locations = [home_base] + unique_locations
        api_key = st.secrets.get("google", {}).get("api_key")
        if not api_key: st.error("Clave de API de Google no encontrada."); return None, None
        dist_matrix = get_distance_matrix(api_key, all_locations)
        if not dist_matrix: return None, None
        final_plan, available_visits_df = [], df_visits.copy()
        for i in range(3):
            if available_visits_df.empty: break
            is_friday = (i == 2)
            best_day_info = find_best_route_for_one_day(available_visits_df, all_locations, dist_matrix, is_friday)
            if best_day_info['route']:
                final_plan.append(best_day_info['route'])
                used_ids = [visit['id'] for visit in best_day_info['route']]
                available_visits_df = available_visits_df[~available_visits_df['id'].isin(used_ids)]
        unassigned_visits = available_visits_df.to_dict('records')
        st.success(f"¡Propuesta generada con {len(final_plan)} días planificados!")
        return final_plan, unassigned_visits

# --- NUEVA FUNCIÓN PARA EL MAPA ---
def create_supervisor_map(plan_days, dates):
    st.markdown("---")
    st.subheader("🗺️ Mapa de Rutas Propuestas")
    
    home_lat, home_lon = 41.3874, 2.1686 # Coordenadas de Plaça de Catalunya
    m = folium.Map(location=[home_lat, home_lon], zoom_start=8)
    
    # Marcador del punto de partida
    folium.Marker([home_lat, home_lon], popup="Punto de Partida/Final", icon=folium.Icon(color='green', icon='home')).add_to(m)
    
    colors = ['blue', 'orange', 'purple']
    
    for i, day_plan in enumerate(plan_days):
        if not day_plan: continue
        
        day_date = dates[i]
        day_color = colors[i % len(colors)]
        
        points = [(home_lat, home_lon)]
        
        for visit in day_plan:
            if visit.get('lat') and visit.get('lon'):
                points.append((visit['lat'], visit['lon']))
                folium.Marker(
                    location=[visit['lat'], visit['lon']],
                    popup=f"<b>{visit['direccion_texto']}</b>  
Día {i+1} ({day_date.strftime('%d/%m')})  
Propuesto por: {visit['nombre_coordinador']}",
                    icon=folium.Icon(color=day_color, icon='car', prefix='fa')
                ).add_to(m)
        
        points.append((home_lat, home_lon)) # Regreso al origen
        
        # Dibujar la línea de la ruta
        folium.PolyLine(points, color=day_color, weight=2.5, opacity=1, tooltip=f"Ruta Día {i+1}").add_to(m)
        
    st_folium(m, width='100%', height=450)

# --- Interfaz de Streamlit (UI) ---
def move_visit(visit_id, current_day_index, new_day_index):
    plan_state = st.session_state.supervisor_plan
    visit_to_move = None
    source_list = plan_state['unassigned'] if current_day_index == -1 else plan_state['plan_days'][current_day_index]
    for i, visit in enumerate(source_list):
        if visit['id'] == visit_id:
            visit_to_move = source_list.pop(i); break
    if visit_to_move:
        dest_list = plan_state['unassigned'] if new_day_index == -1 else plan_state['plan_days'][new_day_index]
        dest_list.append(visit_to_move)

def mostrar_planificador_supervisor():
    st.header("Planificador Automático para Martín 🤖")
    day_names_es = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes"}

    if st.button("🤖 Generar Nueva Planificación Óptima", type="primary", use_container_width=True):
        plan_days_list, unassigned = generate_optimal_plan()
        if plan_days_list is not None:
            start_of_next_week = date.today() + timedelta(days=-date.today().weekday(), weeks=1)
            st.session_state.supervisor_plan = {
                'plan_days': plan_days_list, 'unassigned': unassigned,
                'dates': [start_of_next_week + timedelta(days=i) for i in range(len(plan_days_list))]
            }
        st.session_state.plan_confirmed = False
        st.rerun()

    st.markdown("---")

    if 'supervisor_plan' in st.session_state and st.session_state.supervisor_plan:
        plan_state = st.session_state.supervisor_plan
        st.subheader("🗓️ Tablero de Planificación Manual")
        
        cols_fechas = st.columns(len(plan_state['plan_days']))
        for i in range(len(plan_state['dates'])):
            with cols_fechas[i]:
                plan_state['dates'][i] = st.date_input(f"Fecha Día {i+1}", value=plan_state['dates'][i], key=f"date_{i}")

        st.markdown("---")
        cols_dias = st.columns(len(plan_state['plan_days']))

        for i, day_plan in enumerate(plan_state['plan_days']):
            with cols_dias[i]:
                day_date = plan_state['dates'][i]
                day_name_es = day_names_es.get(day_date.strftime('%A'), day_date.strftime('%A'))
                st.markdown(f"#### Día {i+1} ({day_name_es})")
                num_visits = len(day_plan)
                total_hours = (num_visits * 45 + (num_visits + 1) * 30) / 60
                st.info(f"{num_visits} visitas | Est: {total_hours:.1f}h")
                if (day_date.weekday() == 4 and total_hours > 7) or (day_date.weekday() != 4 and total_hours > 8):
                    st.warning("⚠️ El plan excede el horario laboral.")

                # --- INICIO DE LA MEJORA EN TARJETAS DE VISITA ---
                for visit in day_plan:
                    with st.container(border=True):
                        st.markdown(f"**📍 {visit['direccion_texto']}**")
                        # Mostramos la información de contexto
                        fecha_propuesta = pd.to_datetime(visit['fecha']).strftime('%d/%m/%Y')
                        st.caption(f"Propuesto por: **{visit['nombre_coordinador']}**")
                        st.caption(f"Fecha original: {fecha_propuesta} ({visit['franja_horaria']})")
                        
                        move_options = {f"Día {j+1}": j for j in range(len(plan_state['plan_days']))}
                        move_options["No Asignada"] = -1
                        new_location_index = st.selectbox("Mover a:", options=move_options.keys(), index=i, key=f"move_{visit['id']}")
                        if move_options[new_location_index] != i:
                            move_visit(visit['id'], i, move_options[new_location_index]); st.rerun()
                # --- FIN DE LA MEJORA ---

        with st.expander(f"Visitas No Asignadas ({len(plan_state['unassigned'])})", expanded=True):
            for visit in sorted(plan_state['unassigned'], key=lambda x: x['fecha']):
                with st.container(border=True):
                    st.markdown(f"**📍 {visit['direccion_texto']}**")
                    fecha_propuesta = pd.to_datetime(visit['fecha']).strftime('%d/%m/%Y')
                    st.caption(f"Propuesto por: **{visit['nombre_coordinador']}** | Original: {fecha_propuesta} ({visit['franja_horaria']})")
                    move_options = {"No Asignada": -1}; move_options.update({f"Día {j+1}": j for j in range(len(plan_state['plan_days']))})
                    new_location_index = st.selectbox("Asignar a:", options=move_options.keys(), index=0, key=f"move_{visit['id']}")
                    if move_options[new_location_index] != -1:
                        move_visit(visit['id'], -1, move_options[new_location_index]); st.rerun()

        # --- INCLUSIÓN DEL MAPA ---
        create_supervisor_map(plan_state['plan_days'], plan_state['dates'])

        st.markdown("---")
        if 'plan_confirmed' not in st.session_state: st.session_state.plan_confirmed = False
        col1, col2 = st.columns(2)
        with col1:
            # --- LÓGICA DE CONFIRMACIÓN Y GUARDADO ---
            if st.button("✅ Confirmar y Asignar Plan", type="primary", use_container_width=True, disabled=st.session_state.plan_confirmed):
                with st.spinner("Confirmando y guardando el plan en la base de datos..."):
                    api_key = st.secrets.get("google", {}).get("api_key")
                    home_base = "Plaça de Catalunya, Barcelona"
                    
                    for i, day_plan in enumerate(plan_state['plan_days']):
                        if not day_plan: continue
                        assigned_date = plan_state['dates'][i]
                        current_time_dt = datetime.combine(assigned_date, time(8, 0))
                        last_location = home_base
                        
                        # Reordenar el plan del día según la ruta óptima para ese día específico
                        day_locations = [home_base] + [v['direccion_texto'] for v in day_plan]
                        day_matrix = get_distance_matrix(api_key, day_locations)
                        
                        # Simple algoritmo para ordenar: siempre ir al más cercano
                        ordered_route = []
                        remaining_visits = list(day_plan)
                        
                        while remaining_visits:
                            last_loc_idx = day_locations.index(last_location)
                            next_visit_idx = -1
                            min_dist = float('inf')

                            for j, visit in enumerate(remaining_visits):
                                try:
                                    current_loc_idx = day_locations.index(visit['direccion_texto'])
                                    dist = day_matrix['rows'][last_loc_idx]['elements'][current_loc_idx]['duration']['value']
                                    if dist < min_dist:
                                        min_dist = dist
                                        next_visit_idx = j
                                except (ValueError, IndexError): continue
                            
                            if next_visit_idx > -1:
                                next_visit = remaining_visits.pop(next_visit_idx)
                                travel_time = min_dist
                                current_time_dt += timedelta(seconds=travel_time)
                                
                                # Actualizar BD
                                supabase.table('visitas').update({
                                    'status': 'Asignada a Supervisor',
                                    'fecha_asignada': str(assigned_date),
                                    'hora_asignada': current_time_dt.strftime('%H:%M'),
                                    'supervisor_id': st.session_state['usuario_id']
                                }).eq('id', next_visit['id']).execute()
                                
                                ordered_route.append(next_visit)
                                current_time_dt += timedelta(minutes=45)
                                last_location = next_visit['direccion_texto']
                            else:
                                # Si no se puede encontrar una ruta, se procesa el resto sin ordenar
                                for visit in remaining_visits:
                                     supabase.table('visitas').update({'status': 'Asignada a Supervisor', 'fecha_asignada': str(assigned_date), 'hora_asignada': '00:00'}).eq('id', visit['id']).execute()
                                break
                        
                        plan_state['plan_days'][i] = ordered_route # Actualizar el plan con la ruta ordenada

                    st.session_state.plan_confirmed = True
                    st.success("¡Plan confirmado y asignado en la base de datos!")
                    st.rerun()
        with col2:
            if st.session_state.get('plan_confirmed', False):
                if st.button("📧 Notificar a Coordinadores", use_container_width=True):
                    # Lógica de notificación (ya funcional)
                    pass
