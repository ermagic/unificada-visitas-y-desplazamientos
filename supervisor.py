# Fichero: supervisor.py (Versión con Algoritmo de Optimización Mejorado)
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime, time
import googlemaps
import itertools
import smtplib
from email.mime.text import MIMEText
from database import supabase

# --- CONSTANTES ---
# Punto de inicio y fin de jornada para Martín en el centro de Barcelona.
PUNTO_INICIO_MARTIN = "Plaça de Catalunya, Barcelona, España"
DURACION_VISITA_SEGUNDOS = 45 * 60  # 45 minutos

# --- FUNCIONES AUXILIARES ---

def send_email(recipients, subject, body):
    """Envía un correo electrónico a una lista de destinatarios."""
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
        st.success("✅ Correo de notificación enviado con éxito.")
        return True
    except Exception as e:
        st.error(f"Error al enviar correo: {e}")
        return False

def get_daily_time_budget(weekday):
    """Devuelve el tiempo de trabajo efectivo en segundos según el día de la semana."""
    if weekday == 4:  # Viernes (de 8:00 a 15:00)
        return 7 * 3600  # 7 horas
    else:  # Lunes a Jueves (de 8:00 a 17:00 con 1h para comer)
        return 8 * 3600  # 8 horas

# --- LÓGICA DEL ALGORITMO DE OPTIMIZACIÓN (EL "CEREBRO") ---

def generar_planificacion_automatica():
    """
    Analiza TODAS las visitas pendientes de la próxima semana y genera la mejor
    combinación de rutas para 1, 2 o 3 días, maximizando las visitas por día.
    """
    # 1. Recopilar todas las visitas 'Pendiente de Asignación' para la semana siguiente.
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    end_of_next_week = start_of_next_week + timedelta(days=4)

    response = supabase.table('visitas').select('*, usuarios(nombre_completo)') \
        .eq('status', 'Pendiente de Asignación') \
        .gte('fecha', start_of_next_week) \
        .lte('fecha', end_of_next_week) \
        .execute()

    visitas_df = pd.DataFrame(response.data)
    if visitas_df.empty:
        st.warning("No hay visitas pendientes de asignación para la próxima semana.")
        return None, None

    # Limpieza y preparación de datos
    visitas_df['nombre_coordinador'] = visitas_df['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'N/A')
    visitas_pendientes = visitas_df.to_dict('records')

    # 2. Calcular la matriz de tiempos de viaje con Google Maps API.
    locations = [PUNTO_INICIO_MARTIN] + list(visitas_df['direccion_texto'].unique())
    try:
        gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
        matrix = gmaps.distance_matrix(locations, locations, mode="driving")
    except Exception as e:
        st.error(f"Error al conectar con Google Maps API: {e}")
        return None, None

    def get_travel_time(origen, destino):
        """Obtiene el tiempo de viaje en segundos desde la matriz pre-calculada."""
        try:
            origen_idx = locations.index(origen)
            destino_idx = locations.index(destino)
            return matrix['rows'][origen_idx]['elements'][destino_idx]['duration']['value']
        except (ValueError, KeyError):
            return 3600

    # 3. Proceso iterativo para encontrar los mejores días de trabajo.
    plan_final = {}
    visitas_ya_planificadas_ids = set()
    dias_disponibles = [start_of_next_week + timedelta(days=i) for i in range(5)]

    for _ in range(3):
        if not visitas_pendientes:
            break

        mejor_dia_encontrado = None
        mejor_ruta_del_dia = []
        mejor_puntuacion = (-1, float('inf')) # (num_visitas, tiempo_total) -> maximizar visitas, minimizar tiempo

        for dia_laboral in dias_disponibles:
            presupuesto_tiempo_dia = get_daily_time_budget(dia_laboral.weekday())
            for cantidad in range(len(visitas_pendientes), 0, -1):
                if cantidad < mejor_puntuacion[0]:
                    break

                for combo in itertools.combinations(visitas_pendientes, cantidad):
                    for orden in itertools.permutations(combo):
                        tiempo_total = 0
                        # --- CAMBIO IMPORTANTE: NO se cuenta el viaje a la primera visita ---
                        # El tiempo de trabajo empieza en la primera visita.

                        for i in range(len(orden)):
                            tiempo_total += DURACION_VISITA_SEGUNDOS
                            if i < len(orden) - 1:
                                tiempo_total += get_travel_time(orden[i]['direccion_texto'], orden[i+1]['direccion_texto'])

                        # Se cuenta el trayecto de la última visita de vuelta al punto de origen.
                        tiempo_total += get_travel_time(orden[-1]['direccion_texto'], PUNTO_INICIO_MARTIN)

                        if tiempo_total <= presupuesto_tiempo_dia:
                            puntuacion_actual = (len(orden), tiempo_total)
                            if puntuacion_actual[0] > mejor_puntuacion[0] or (puntuacion_actual[0] == mejor_puntuacion[0] and puntuacion_actual[1] < mejor_puntuacion[1]):
                                mejor_puntuacion = puntuacion_actual
                                mejor_ruta_del_dia = list(orden)
                                mejor_dia_encontrado = dia_laboral
                
                if mejor_puntuacion[0] == cantidad:
                    break

        if mejor_dia_encontrado:
            plan_final[mejor_dia_encontrado] = mejor_ruta_del_dia
            ids_agregadas = {v['id'] for v in mejor_ruta_del_dia}
            visitas_ya_planificadas_ids.update(ids_agregadas)
            visitas_pendientes = [v for v in visitas_pendientes if v['id'] not in visitas_ya_planificadas_ids]
            dias_disponibles.remove(mejor_dia_encontrado)
        else:
            break

    no_asignadas = visitas_df[~visitas_df['id'].isin(visitas_ya_planificadas_ids)].to_dict('records')
    return plan_final, no_asignadas

# --- INTERFAZ DE STREAMLIT PARA EL SUPERVISOR ---

def mostrar_planificador_supervisor():
    st.header("Planificador de Martín (Supervisor) 🤖")

    if st.button("🤖 Generar planificación óptima", type="primary", use_container_width=True):
        with st.spinner("🧠 Analizando todas las visitas y calculando las mejores rutas..."):
            plan, no_asignadas = generar_planificacion_automatica()
            st.session_state.supervisor_plan = plan
            st.session_state.no_asignadas = no_asignadas
            if plan:
                st.success("¡Planificación óptima generada!")
            st.rerun()

    if "supervisor_plan" in st.session_state and st.session_state.supervisor_plan:
        plan = st.session_state.supervisor_plan
        st.subheader("📅 Propuesta de Planificación Optimizada")
        
        plan_con_horas = {}
        gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
        for day, visitas in plan.items():
            hora_actual = datetime.combine(day, time(8, 0))
            visitas_con_hora = []
            
            for i, v in enumerate(visitas):
                if i > 0:
                    tiempo_viaje = gmaps.distance_matrix(visitas[i-1]['direccion_texto'], v['direccion_texto'], mode="driving")['rows'][0]['elements'][0]['duration']['value']
                    hora_actual += timedelta(seconds=tiempo_viaje)
                
                v_con_hora = v.copy()
                v_con_hora['hora_asignada'] = hora_actual.time()
                visitas_con_hora.append(v_con_hora)
                hora_actual += timedelta(seconds=DURACION_VISITA_SEGUNDOS)
            
            plan_con_horas[day] = visitas_con_hora
        st.session_state.plan_con_horas = plan_con_horas

        for day, visitas in plan_con_horas.items():
            nombre_dia = day.strftime('%A, %d de %B').capitalize()
            with st.expander(f"**{nombre_dia}** ({len(visitas)} visitas)", expanded=True):
                for v in visitas:
                    st.markdown(f"- **{v['hora_asignada'].strftime('%H:%M')}h** - {v['direccion_texto']} | **Equipo**: {v['equipo']} (Propuesto por: *{v['nombre_coordinador']}*)")

        st.markdown("---")
        
        col_accion1, col_accion2 = st.columns(2)
        with col_accion1:
            if st.button("✅ Confirmar y Asignar Planificación", use_container_width=True):
                with st.spinner("Actualizando la base de datos..."):
                    # 1. Asignar visitas al supervisor
                    for day, visitas in st.session_state.plan_con_horas.items():
                        for v in visitas:
                            supabase.table('visitas').update({
                                'status': 'Asignada a Supervisor',
                                'fecha_asignada': str(day.date()),
                                'hora_asignada': v['hora_asignada'].strftime('%H:%M')
                            }).eq('id', v['id']).execute()
                    
                    # 2. Asignar las visitas no seleccionadas de vuelta a los coordinadores
                    if "no_asignadas" in st.session_state and st.session_state.no_asignadas:
                        ids_no_asignadas = [v['id'] for v in st.session_state.no_asignadas]
                        supabase.table('visitas').update({'status': 'Asignada a Coordinador'}).in_('id', ids_no_asignadas).execute()
                        st.info(f"{len(ids_no_asignadas)} visita(s) ha(n) sido asignada(s) a sus coordinadores originales.")

                st.success("✅ ¡Planificación confirmada! El sistema ha sido actualizado.")
                del st.session_state.supervisor_plan
                del st.session_state.plan_con_horas
                if 'no_asignadas' in st.session_state: del st.session_state.no_asignadas
                st.rerun()

        with col_accion2:
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
        st.warning("Visitas que no entraron en la planificación óptima de Martín (serán asignadas a sus coordinadores si se confirma):")
        for v in st.session_state.no_asignadas:
            st.markdown(f"- {v['direccion_texto']} (Equipo: {v['equipo']}) - Propuesto por: *{v['nombre_coordinador']}*")

    st.markdown("---")

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

