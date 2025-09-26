# Fichero: desplazamientos.py (Versión final con rediseño visual profesional)
import streamlit as st
import pandas as pd
import googlemaps
import datetime as dt
import math
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import supabase

def inicializar_estado_calculadora():
    if 'calc_page' not in st.session_state: st.session_state.calc_page = 'calculator'
    if 'calculation_results' not in st.session_state: st.session_state.calculation_results = {}
    if 'gmaps_results' not in st.session_state: st.session_state.gmaps_results = None

@st.cache_data
def cargar_datos_supabase():
    try:
        response = supabase.table('tiempos').select('*').execute()
        df = pd.DataFrame(response.data)
        if df.empty:
            st.error("Error: La tabla 'tiempos' de Supabase no devolvió datos.")
            return None
        df.rename(columns={
            'Poblacion_WFI': 'poblacion', 'Centro de Trabajo Nuevo': 'centro_trabajo',
            'Provincia Centro de Trabajo': 'provincia_ct', 'Distancia en Kms': 'distancia',
            'Tiempo(Min)': 'minutos_total', 'Tiempo a cargo de empresa(Min)': 'minutos_cargo'
        }, inplace=True)
        required_cols = ['poblacion', 'centro_trabajo', 'provincia_ct', 'distancia', 'minutos_total', 'minutos_cargo']
        if not all(col in df.columns for col in required_cols):
            st.error("Error Crítico: La tabla de Supabase no contiene todas las columnas necesarias.")
            return None
        df_clean = df[required_cols].dropna(subset=['poblacion', 'centro_trabajo', 'provincia_ct'])
        for col in ['poblacion', 'centro_trabajo', 'provincia_ct']:
            df_clean[col] = df_clean[col].str.strip()
        df_clean['distancia'] = df_clean['distancia'].astype(str).str.replace(',', '.', regex=False)
        for col in ['distancia', 'minutos_total', 'minutos_cargo']:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0)
        df_clean['minutos_total'] = df_clean['minutos_total'].astype(int)
        df_clean['minutos_cargo'] = df_clean['minutos_cargo'].astype(int)
        return df_clean
    except Exception as e:
        st.error(f"Error al conectar o procesar datos de Supabase: {e}")
        return None

@st.cache_data
def cargar_datos_empleados():
    try:
        response = supabase.table('empleados').select('*').execute()
        df = pd.DataFrame(response.data)
        if df.empty:
            st.error("Error: La tabla 'empleados' en Supabase está vacía o no se pudo cargar.")
            return None
        required_cols = ['PROVINCIA', 'EQUIPO', 'NOMBRE COMPLETO', 'EMAIL', 'PERSONAL']
        if not all(col in df.columns for col in required_cols):
            st.error(f"❌ Error en la tabla 'empleados': Faltan columnas: {[c for c in required_cols if c not in df.columns]}")
            return None
        return df[df['PERSONAL'].str.lower() == 'activo'].copy()
    except Exception as e: 
        st.error(f"Error al cargar los empleados desde Supabase. Error: {e}"); 
        return None

def calcular_minutos_con_limite(origen, destino, gmaps_client):
    try:
        directions_result = gmaps_client.directions(origen, destino, mode="driving", avoid="tolls")
        if not directions_result or not directions_result[0]['legs']: return None, None, "No se pudo encontrar una ruta."
        steps = directions_result[0]['legs'][0]['steps']
        total_capped_duration_seconds, total_distance_meters = 0, 0
        for step in steps:
            distancia_metros, duracion_google_seg = step['distance']['value'], step['duration']['value']
            total_distance_meters += distancia_metros
            theoretical_duration_90kmh_seg = (distancia_metros / 1000) / (90 / 3600) if distancia_metros > 0 else 0
            capped_duration_seg = max(duracion_google_seg, theoretical_duration_90kmh_seg)
            total_capped_duration_seconds += capped_duration_seg
        total_distancia_km = total_distance_meters / 1000
        total_minutos_final = math.ceil(total_capped_duration_seconds / 60)
        return total_distancia_km, total_minutos_final, None
    except googlemaps.exceptions.ApiError as e: return None, None, f"Error de la API de Google: {e}"
    except Exception as e: return None, None, f"Error inesperado: {e}"

def mostrar_horas_de_salida(total_minutos_desplazamiento):
    st.subheader("🕒 Horas de Salida Sugeridas")
    dias_es = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes"}
    meses_es = {"January": "enero", "February": "febrero", "March": "marzo", "April": "abril", "May": "mayo", "June": "junio", "July": "julio", "August": "agosto", "September": "septiembre", "October": "octubre", "November": "noviembre", "December": "diciembre"}
    hoy = dt.date.today()
    fecha_formateada = f"{dias_es.get(hoy.strftime('%A'), '')} {hoy.day} de {meses_es.get(hoy.strftime('%B'), '')}"
    st.session_state.calculation_results['fecha'] = fecha_formateada
    
    horarios_base = {"Habitual Intensivo": dt.time(15, 0), "Normal": dt.time(15, 0)} if hoy.weekday() == 4 else {"Habitual Intensivo": dt.time(16, 0), "Normal": dt.time(17, 0)}
    
    col1, col2 = st.columns(2)
    horas_salida_hoy = {}
    for i, (nombre, hora_habitual) in enumerate(horarios_base.items()):
        salida_dt_hoy = dt.datetime.combine(hoy, hora_habitual) - dt.timedelta(minutes=total_minutos_desplazamiento)
        hora_salida_str = salida_dt_hoy.strftime('%H:%M')
        horas_salida_hoy[nombre] = hora_salida_str
        (col1 if i == 0 else col2).metric(f"Salida Horario {nombre}", hora_salida_str, f"Normal: {hora_habitual.strftime('%H:%M')}")
        
    st.session_state.calculation_results['horas_salida'] = horas_salida_hoy

def send_email(recipients, subject, body):
    try:
        smtp_cfg = st.secrets["smtp"]
        sender, password = smtp_cfg["username"], smtp_cfg["password"]
        msg = MIMEMultipart(); msg['From'], msg['To'], msg['Subject'] = sender, ", ".join(recipients), subject
        msg.attach(MIMEText(body, 'plain')); server = smtplib.SMTP(smtp_cfg["server"], smtp_cfg["port"])
        server.starttls(); server.login(sender, password); server.send_message(msg); server.quit()
        st.success("✅ ¡Correo enviado con éxito!")
        return True
    except Exception as e: 
        st.error(f"Error al enviar el correo: {e}")
        return False

def pagina_calculadora():
    st.header("🚗 Calculadora de Desplazamientos", divider="blue")
    df_tiempos = cargar_datos_supabase()
    def _cargo(minutos): return max(0, int(minutos) - 30)

    tab1, tab2 = st.tabs(["Cálculo Oficial (Base de Datos)", "Cálculo Estimado (Google Maps)"])
    
    with tab1:
        if df_tiempos is not None:
            with st.container(border=True):
                st.subheader("1. Selecciona los Trayectos")
                provincias_ct = sorted(df_tiempos['provincia_ct'].unique())
                provincia_seleccionada = st.selectbox("Provincia del Centro de Trabajo:",provincias_ct, index=None, placeholder="Elige una provincia")
                if provincia_seleccionada:
                    df_filtrado = df_tiempos[df_tiempos['provincia_ct'] == provincia_seleccionada]
                    lista_poblaciones = sorted(df_filtrado['poblacion'].unique())
                    col1, col2 = st.columns(2)
                    mun_entrada = col1.selectbox("Destino al inicio de jornada:", lista_poblaciones, index=None, placeholder="Selecciona población de ida")
                    mun_salida = col2.selectbox("Origen al final de jornada:", lista_poblaciones, index=None, placeholder="Selecciona población de vuelta")
                    if mun_entrada and mun_salida:
                        st.session_state.db_calc_ready = True
                        st.session_state.db_data = {'df_filtrado': df_filtrado, 'mun_entrada': mun_entrada, 'mun_salida': mun_salida}
            
            if st.session_state.get('db_calc_ready'):
                with st.container(border=True):
                    st.subheader("2. Resultados del Cálculo Oficial")
                    data = st.session_state.db_data
                    datos_entrada = data['df_filtrado'][data['df_filtrado']['poblacion'] == data['mun_entrada']].iloc[0]
                    datos_salida = data['df_filtrado'][data['df_filtrado']['poblacion'] == data['mun_salida']].iloc[0]
                    st.session_state.calculation_results.update({
                        'aviso_pernocta': int(datos_entrada['minutos_total']) > 80 or int(datos_salida['minutos_total']) > 80, 
                        'aviso_dieta': float(datos_entrada['distancia']) > 40 or float(datos_salida['distancia']) > 40,
                        'aviso_jornada': int(datos_entrada['minutos_total']) > 60 or int(datos_salida['minutos_total']) > 60, 
                        'trayecto_entrada': f"De `{datos_entrada['centro_trabajo']}` a `{data['mun_entrada']}`",
                        'trayecto_salida': f"De `{data['mun_salida']}` a `{datos_salida['centro_trabajo']}`"
                    })
                    if st.session_state.calculation_results['aviso_pernocta']: st.warning("🛌 **Aviso Pernocta:** Uno de los trayectos supera los 80 min.")
                    if st.session_state.calculation_results['aviso_dieta']: st.warning("⚠️ **Atención Media Dieta:** Uno de los trayectos supera los 40km.")
                    if st.session_state.calculation_results['aviso_jornada']: st.warning("⏰ **Aviso Jornada:** Uno de los trayectos supera los 60 min.")
                    
                    st.divider()
                    col_res1, col_res2 = st.columns(2)
                    with col_res1:
                        st.markdown(f"**Viaje de Ida:** {st.session_state.calculation_results['trayecto_entrada']}")
                        st.metric("Tiempo de viaje", f"{int(datos_entrada['minutos_total'])} min")
                        st.metric("A cargo de empresa", f"{int(datos_entrada['minutos_cargo'])} min")
                    with col_res2:
                        st.markdown(f"**Viaje de Vuelta:** {st.session_state.calculation_results['trayecto_salida']}")
                        st.metric("Tiempo de viaje", f"{int(datos_salida['minutos_total'])} min")
                        st.metric("A cargo de empresa", f"{int(datos_salida['minutos_cargo'])} min")
                    
                    st.divider()
                    total_minutos_a_cargo = int(datos_entrada['minutos_cargo']) + int(datos_salida['minutos_cargo'])
                    st.success(f"**Tiempo total a compensar en la jornada: `{total_minutos_a_cargo}` minutos**")
                    mostrar_horas_de_salida(total_minutos_a_cargo)
                    st.session_state.calculation_results['total_minutos'] = total_minutos_a_cargo
                    if st.button("📧 Notificar al Equipo", key="btn_csv_mail", use_container_width=True):
                        st.session_state.calc_page = 'email_form'; st.rerun()

    with tab2:
        try: gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
        except Exception: st.error("Error: La clave de API de Google no está disponible."); st.stop()
        
        with st.container(border=True):
            st.subheader("1. Introduce las Direcciones")
            col1_g, col2_g = st.columns(2)
            origen_ida = col1_g.text_input("📍 Origen (ida)", key="origen_ida")
            destino_ida = col1_g.text_input("🏁 Destino (ida)", key="destino_ida")
            origen_vuelta = col2_g.text_input("📍 Origen (vuelta)", key="origen_vuelta")
            destino_vuelta = col2_g.text_input("🏁 Destino (vuelta)", key="destino_vuelta")
        
            if st.button("Calcular Tiempo por Distancia", type="primary", use_container_width=True):
                if all([origen_ida, destino_ida, origen_vuelta, destino_vuelta]):
                    with st.spinner('Calculando rutas con Google Maps...'):
                        dist_ida, min_ida, err_ida = calcular_minutos_con_limite(origen_ida, destino_ida, gmaps)
                        dist_vuelta, min_vuelta, err_vuelta = calcular_minutos_con_limite(origen_vuelta, destino_vuelta, gmaps)
                        if err_ida or err_vuelta:
                            if err_ida: st.error(f"Error en ruta de ida: {err_ida}")
                            if err_vuelta: st.error(f"Error en ruta de vuelta: {err_vuelta}")
                            st.session_state.gmaps_results = None
                        else:
                            st.session_state.gmaps_results = {"dist_ida": dist_ida, "min_ida": min_ida, "dist_vuelta": dist_vuelta, "min_vuelta": min_vuelta}
                            st.session_state.calculation_results.update({'trayecto_entrada': f"De `{origen_ida}` a `{destino_ida}`", 'trayecto_salida': f"De `{origen_vuelta}` a `{destino_vuelta}`"})
                else: st.warning("Por favor, rellena las cuatro direcciones."); st.session_state.gmaps_results = None
        
        if st.session_state.gmaps_results:
            with st.container(border=True):
                st.subheader("2. Resultados Estimados")
                res = st.session_state.gmaps_results
                st.session_state.calculation_results.update({
                    'aviso_pernocta': res['min_ida'] > 80 or res['min_vuelta'] > 80,
                    'aviso_dieta': res['dist_ida'] > 40 or res['dist_vuelta'] > 40,
                    'aviso_jornada': res['min_ida'] > 60 or res['min_vuelta'] > 60
                })
                if st.session_state.calculation_results['aviso_pernocta']: st.warning("🛌 **Aviso Pernocta:** Uno de los trayectos supera los 80 min.")
                if st.session_state.calculation_results['aviso_dieta']: st.warning("⚠️ **Atención Media Dieta:** Uno de los trayectos supera los 40km.")
                if st.session_state.calculation_results['aviso_jornada']: st.warning("⏰ **Aviso Jornada:** Uno de los trayectos supera los 60 min.")
                
                st.divider()
                col1, col2 = st.columns(2)
                col1.metric(f"IDA: {res['dist_ida']:.1f} km", f"{_cargo(res['min_ida'])} min a cargo", f"Tiempo total: {res['min_ida']} min")
                col2.metric(f"VUELTA: {res['dist_vuelta']:.1f} km", f"{_cargo(res['min_vuelta'])} min a cargo", f"Tiempo total: {res['min_vuelta']} min")
                
                st.divider()
                total_final = _cargo(res['min_ida']) + _cargo(res['min_vuelta'])
                st.success(f"**Tiempo total a compensar en la jornada: `{total_final}` minutos**")
                mostrar_horas_de_salida(total_final)
                st.session_state.calculation_results['total_minutos'] = total_final
                if st.button("📧 Notificar al Equipo", key="btn_gmaps_mail", use_container_width=True): 
                    st.session_state.calc_page = 'email_form'; st.rerun()

def pagina_email():
    st.header("📧 Redactar y Enviar Notificación", divider="blue")
    if st.button("⬅️ Volver a la calculadora"): 
        st.session_state.calc_page = 'calculator'; st.rerun()
    
    employees_df = cargar_datos_empleados()
    if employees_df is None: st.warning("No se pudieron cargar datos de empleados."); return
    
    with st.container(border=True):    
        st.subheader("1. Seleccionar Destinatarios")
        col1, col2 = st.columns(2)
        prov_options = employees_df['PROVINCIA'].unique()
        provincia_sel = col1.selectbox("Filtrar por Provincia:", prov_options)
        
        equipos_en_provincia = employees_df[employees_df['PROVINCIA'] == provincia_sel]['EQUIPO'].unique()
        equipo_sel = col2.selectbox("Filtrar por Equipo:", equipos_en_provincia)
        
        personas_en_equipo = employees_df[(employees_df['PROVINCIA'] == provincia_sel) & (employees_df['EQUIPO'] == equipo_sel)]
        nombres_seleccionados = st.multiselect("Destinatarios:", options=personas_en_equipo['NOMBRE COMPLETO'].tolist(), default=personas_en_equipo['NOMBRE COMPLETO'].tolist())
        
        if not nombres_seleccionados: st.info("Selecciona al menos un destinatario."); st.stop()
        destinatarios_df = employees_df[employees_df['NOMBRE COMPLETO'].isin(nombres_seleccionados)]

    with st.container(border=True):
        st.subheader("2. Redactar el Correo")
        def crear_saludo(nombres):
            nombres_cortos = [name.split()[0] for name in nombres]
            if len(nombres_cortos) == 1: return f"Hola {nombres_cortos[0]},"
            return f"Hola {', '.join(nombres_cortos[:-1])} y {nombres_cortos[-1]},"

        res = st.session_state.calculation_results
        asunto_pred, cuerpo_pred = "", ""
        tipo_mail = st.radio("Tipo de notificación:", ["Comunicar Horario", "Notificar Jornada", "Informar Pernocta"], horizontal=True)
        
        if tipo_mail == "Comunicar Horario":
            asunto_pred = f"Horario de salida para el {res.get('fecha', 'día de hoy')}"
            cuerpo_pred = f"{crear_saludo(nombres_seleccionados)}\n\nTe informo del horario de salida calculado para hoy, {res.get('fecha', '')}, será **{res.get('total_minutos', 0)} minutos** antes:\n\n- Salida en horario Intensivo: **{res.get('horas_salida', {}).get('Habitual Intensivo', 'N/A')}**\n- Salida en horario Normal: **{res.get('horas_salida', {}).get('Normal', 'N/A')}**\n\nTrayectos considerados:\n- Ida: {res.get('trayecto_entrada', 'No especificado')}\n- Vuelta: {res.get('trayecto_salida', 'No especificado')}\n\nSaludos,\n{st.session_state['nombre_completo']}"
        elif tipo_mail == "Notificar Jornada":
            asunto_pred = f"Confirmación de jornada para el {res.get('fecha', 'día de hoy')}"
            cuerpo_pred = f"{crear_saludo(nombres_seleccionados)}\n\nDebido a los desplazamientos del día de hoy ({res.get('fecha', '')}), por favor, confirma el tipo de jornada a aplicar.\n\nRecuerda que los avisos generados han sido:\n- Media Dieta (>40km): **{'Sí' if res.get('aviso_dieta') else 'No'}**\n- Jornada Especial (>60min): **{'Sí' if res.get('aviso_jornada') else 'No'}**\n\nQuedo a la espera de tu confirmación.\n\nSaludos,\n{st.session_state['nombre_completo']}"
        elif tipo_mail == "Informar Pernocta":
            asunto_pred = f"Aviso de posible pernocta - {res.get('fecha', 'día de hoy')}"
            cuerpo_pred = f"{crear_saludo(nombres_seleccionados)}\n\nEl cálculo de desplazamiento para hoy, {res.get('fecha', '')}, ha generado un aviso por superar los 80 minutos, lo que podría implicar una pernocta.\n\nPor favor, revisa la planificación y gestiona la reserva de hotel si es necesario.\n\nSaludos,\n{st.session_state['nombre_completo']}"
        
        asunto = st.text_input("Asunto:", asunto_pred)
        cuerpo = st.text_area("Cuerpo del Mensaje:", cuerpo_pred, height=250)
        
        if st.button("🚀 Enviar Email", type="primary", use_container_width=True):
            send_email(destinatarios_df['EMAIL'].tolist(), asunto, cuerpo)

def mostrar_calculadora_avanzada():
    inicializar_estado_calculadora()
    if st.session_state.calc_page == 'calculator':
        pagina_calculadora()
    elif st.session_state.calc_page == 'email_form':
        pagina_email()