# Fichero: supervisor.py (Versión completa y funcional para Martín)
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime, time
import googlemaps
import itertools
import smtplib
from email.mime.text import MIMEText
import random
from database import supabase

# --- EMAIL ---
def send_email(recipients, subject, body):
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
        st.success("✅ Correo enviado con éxito.")
        return True
    except Exception as e:
        st.error(f"Error al enviar correo: {e}")
        return False

# --- HORARIOS ---
def get_daily_time_budget(weekday):
    if weekday == 4:  # Viernes
        return 7 * 3600  # 7 horas
    else:
        return 8 * 3600  # 8 horas

# --- ALGORITMO ---
def generar_planificacion_automatica():
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    weekdays = [start_of_next_week + timedelta(days=i) for i in range(5)]

    response = supabase.table('visitas').select('*, usuarios(nombre_completo)').eq('status', 'Pendiente de Asignación').execute()
    visitas = pd.DataFrame(response.data)
    if visitas.empty:
        st.warning("No hay visitas pendientes de asignación.")
        return None, None

    visitas['fecha'] = pd.to_datetime(visitas['fecha']).dt.date
    visitas['nombre_coordinador'] = visitas['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'N/A')

    ubicaciones = list(visitas['direccion_texto'].unique())
    try:
        gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
        matrix = gmaps.distance_matrix(ubicaciones, ubicaciones, mode="driving")
    except Exception as e:
        st.error(f"Error al conectar con Google Maps: {e}")
        return None, None

    random.shuffle(weekdays)
    plan = {}
    usadas = set()

    for day in weekdays[:3]:  # Máximo 3 días
        dia_visitas = visitas[visitas['fecha'] == day].copy()
        dia_visitas = dia_visitas[~dia_visitas['id'].isin(usadas)]
        if dia_visitas.empty:
            continue

        mejor_ruta = []
        mejor_tiempo = 0
        mejor_cantidad = 0

        for cantidad in range(min(8, len(dia_visitas)), 0, -1):
            for combo in itertools.combinations(dia_visitas.index, cantidad):
                for orden in itertools.permutations(combo):
                    tiempo = 0
                    ruta = []
                    valida = True

                    for i, idx in enumerate(orden):
                        visita = dia_visitas.loc[idx]
                        ruta.append(visita.to_dict())

                        if i > 0:
                            origen = dia_visitas.loc[orden[i - 1]]['direccion_texto']
                            destino = visita['direccion_texto']
                            origen_idx = ubicaciones.index(origen)
                            destino_idx = ubicaciones.index(destino)
                            tiempo += matrix['rows'][origen_idx]['elements'][destino_idx]['duration']['value']

                        tiempo += 45 * 60  # Visita

                        if tiempo > get_daily_time_budget(day.weekday()):
                            valida = False
                            break

                    if valida and len(ruta) > mejor_cantidad:
                        mejor_ruta = ruta
                        mejor_cantidad = len(ruta)
                        mejor_tiempo = tiempo

                if mejor_ruta:
                    break

        if mejor_ruta:
            plan[day] = mejor_ruta
            usadas.update([v['id'] for v in mejor_ruta])

        if len(usadas) >= len(visitas):
            break  # ✅ No hace falta más días

    no_asignadas = visitas[~visitas['id'].isin(usadas)].to_dict('records')
    return plan, no_asignadas

# --- INTERFAZ ---
def mostrar_planificador_supervisor():
    st.header("Planificador de Martín (Supervisor) 🤖")

    if st.button("🤖 Generar planificación automática (3 días al azar)"):
        with st.spinner("Generando planificación..."):
            plan, no_asignadas = generar_planificacion_automatica()
            if plan:
                st.session_state.supervisor_plan = plan
                st.session_state.no_asignadas = no_asignadas
                st.success("Planificación generada.")
                st.rerun()

    if "supervisor_plan" in st.session_state:
        plan = st.session_state.supervisor_plan
        st.subheader("📅 Planificación actual")
        for day, visitas in plan.items():
            with st.expander(f"{day.strftime('%A %d/%m')} ({len(visitas)} visitas)"):
                for v in visitas:
                    st.write(f"- {v['direccion_texto']} ({v['nombre_coordinador']})")

        if st.button("✅ Confirmar planificación"):
            for day, visitas in plan.items():
                for i, v in enumerate(visitas):
                    hora = time(8 + i, 0)
                    supabase.table('visitas').update({
                        'status': 'Asignada a Supervisor',
                        'fecha_asignada': str(day),
                        'hora_asignada': hora.strftime('%H:%M')
                    }).eq('id', v['id']).execute()
            st.success("Visitas confirmadas y asignadas.")

        if st.button("📧 Notificar a coordinadores"):
            emails = [u['email'] for u in supabase.table('usuarios').select('email').eq('rol', 'coordinador').execute().data]
            body = "<h3>Visitas asignadas a Martín</h3><ul>"
            for day, visitas in plan.items():
                for v in visitas:
                    body += f"<li>{day.strftime('%d/%m')}: {v['direccion_texto']} ({v['nombre_coordinador']})</li>"
            body += "</ul>"
            send_email(emails, f"Planificación de Martín - Semana del {min(plan.keys()).strftime('%d/%m')}", body)

    # --- PLANIFICACIÓN MANUAL ---
    with st.expander("➕ Añadir visita manual (sin algoritmo)"):
        with st.form("manual_visit"):
            fecha = st.date_input("Fecha")
            hora = st.time_input("Hora")
            direccion = st.text_input("Dirección")
            equipo = st.text_input("Equipo")
            observaciones = st.text_area("Observaciones")
            if st.form_submit_button("Añadir visita"):
                supabase.table('visitas').insert({
                    'usuario_id': st.session_state['usuario_id'],
                    'fecha': str(fecha),
                    'franja_horaria': f"{hora.strftime('%H:%M')}-{((datetime.combine(fecha, hora) + timedelta(minutes=45)).time().strftime('%H:%M'))}",
                    'direccion_texto': direccion,
                    'equipo': equipo,
                    'observaciones': observaciones,
                    'status': 'Asignada a Supervisor',
                    'fecha_asignada': str(fecha),
                    'hora_asignada': hora.strftime('%H:%M')
                }).execute()
                st.success("Visita añadida manualmente.")
                st.rerun()