# Fichero: desplazamientos.py (Versión con Diagnóstico Definitivo)
# ... (el resto de imports y funciones iniciales no cambian) ...
import streamlit as st
import pandas as pd
import googlemaps
import datetime as dt
import math
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import supabase

# --- INICIALIZACIÓN DE ESTADO (para este módulo) ---
def inicializar_estado_calculadora():
    """Inicializa las variables de sesión necesarias para la calculadora."""
    if 'calc_page' not in st.session_state: st.session_state.calc_page = 'calculator'
    if 'calculation_results' not in st.session_state: st.session_state.calculation_results = {}
    if 'gmaps_results' not in st.session_state: st.session_state.gmaps_results = None

# --- FUNCIONES DE LÓGICA ---

@st.cache_data
def cargar_datos_tiempos():
    """Carga los datos de tiempos desde la tabla 'tiempos' de Supabase."""
    try:
        response = supabase.table('tiempos').select('*').limit(3000).execute()
        df = pd.DataFrame(response.data)
        
        # --- LÍNEA DE DIAGNÓSTICO IMPORTANTE ---
        st.info(f"🔍 **Diagnóstico:** Se han recibido {len(df.index)} filas de la tabla 'tiempos' desde Supabase.")
        # --- FIN DE LÍNEA DE DIAGNÓSTICO ---
        
        if df.empty:
            st.warning("La tabla 'tiempos' de Supabase no devolvió datos.")
            return None

        # (El resto de la función no cambia)
        required_cols = [
            'Poblacion_WFI', 'Centro de Trabajo Nuevo', 'Provincia Centro de Trabajo', 
            'Distancia en Kms', 'Tiempo(Min)', 'Tiempo a cargo de empresa(Min)'
        ]
        
        if not all(col in df.columns for col in required_cols):
            st.error("Error Crítico: La tabla 'tiempos' en Supabase no contiene todas las columnas necesarias. Revisa los nombres.")
            st.write("Columnas esperadas:", required_cols)
            st.write("Columnas encontradas:", df.columns.tolist())
            return None
        
        column_mapping = {
            'Poblacion_WFI': 'poblacion',
            'Centro de Trabajo Nuevo': 'centro_trabajo',
            'Provincia Centro de Trabajo': 'provincia_ct',
            'Distancia en Kms': 'distancia',
            'Tiempo(Min)': 'minutos_total',
            'Tiempo a cargo de empresa(Min)': 'minutos_cargo'
        }
        df.rename(columns=column_mapping, inplace=True)
        
        df_clean = df.dropna(subset=['poblacion', 'centro_trabajo', 'provincia_ct'])
        for col in ['poblacion', 'centro_trabajo', 'provincia_ct']:
            df_clean[col] = df_clean[col].str.strip()
        for col in ['distancia', 'minutos_total', 'minutos_cargo']:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0)
        
        df_clean['minutos_total'] = df_clean['minutos_total'].astype(int)
        df_clean['minutos_cargo'] = df_clean['minutos_cargo'].astype(int)
        return df_clean
    except Exception as e:
        st.error(f"Error al cargar datos de la tabla 'tiempos': {e}")
        return None

# (El resto del fichero .py es exactamente igual, por brevedad no se repite aquí pero debes tenerlo completo)
# ...
# (Asegúrate de que el resto de tu fichero desde @st.cache_data def cargar_datos_empleados(): hacia abajo sigue intacto)
# ...
# --- PÁGINA DE LA CALCULADORA ---
def pagina_calculadora():
    st.header("Calculadora de Tiempos y Notificaciones 🚗")
    df_tiempos = cargar_datos_tiempos()

    def _cargo(minutos): return max(0, int(minutos) - 30)

    tab1, tab2 = st.tabs(["Cálculo oficial (desde Base de Datos)", "Cálculo informativo (con Google Maps)"])
    
    with tab1:
        st.subheader("Cálculo de tiempos desde la base de datos")
        if df_tiempos is not None:
            provincias_ct = sorted(df_tiempos['provincia_ct'].unique())
            provincia_seleccionada = st.selectbox("1. Selecciona la provincia del Centro de Trabajo:",provincias_ct, index=None, placeholder="Elige una provincia")
            if provincia_seleccionada:
                df_filtrado = df_tiempos[df_tiempos['provincia_ct'] == provincia_seleccionada]
                lista_poblaciones = sorted(df_filtrado['poblacion'].unique())
                st.markdown("---")
                col1, col2 = st.columns(2)
                with col1:
                    mun_entrada = st.selectbox("2. Destino del comienzo de la jornada:", lista_poblaciones, index=None, placeholder="Selecciona una población")
                    if mun_entrada:
                        info_entrada = df_filtrado[df_filtrado['poblacion'] == mun_entrada].iloc[0]
                        st.info(f"**Centro de Trabajo:** {info_entrada['centro_trabajo']}")
                with col2:
                    mun_salida = st.selectbox("3. Destino del final de la jornada:", lista_poblaciones, index=None, placeholder="Selecciona una población")
                    if mun_salida:
                        info_salida = df_filtrado[df_filtrado['poblacion'] == mun_salida].iloc[0]
                        st.info(f"**Centro de Trabajo:** {info_salida['centro_trabajo']}")
                if mun_entrada and mun_salida:
                    st.markdown("---")
                    datos_entrada = df_filtrado[df_filtrado['poblacion'] == mun_entrada].iloc[0]
                    datos_salida = df_filtrado[df_filtrado['poblacion'] == mun_salida].iloc[0]
                    min_total_entrada, dist_entrada, min_cargo_entrada = int(datos_entrada['minutos_total']), float(datos_entrada['distancia']), int(datos_entrada['minutos_cargo'])
                    min_total_salida, dist_salida, min_cargo_salida = int(datos_salida['minutos_total']), float(datos_salida['distancia']), int(datos_salida['minutos_cargo'])
                    st.session_state.calculation_results.update({
                        'aviso_pernocta': min_total_entrada > 80 or min_total_salida > 80, 'aviso_dieta': dist_entrada > 40 or dist_salida > 40,
                        'aviso_jornada': min_total_entrada > 60 or min_total_salida > 60, 'trayecto_entrada': f"De `{datos_entrada['centro_trabajo']}` a `{mun_entrada}`",
                        'trayecto_salida': f"De `{mun_salida}` a `{datos_salida['centro_trabajo']}`"
                    })
                    if st.session_state.calculation_results['aviso_pernocta']: st.warning("🛌 **Aviso Pernocta:** Uno o ambos trayectos superan los 80 minutos.")
                    if st.session_state.calculation_results['aviso_dieta']: st.warning("⚠️ **Atención Media Dieta:** Uno o ambos trayectos superan los 40km.")
                    if st.session_state.calculation_results['aviso_jornada']: st.warning("⏰ **Aviso Jornada:** Uno o ambos trayectos superan los 60 minutos.")
                    st.markdown("---")
                    col_res1, col_res2 = st.columns(2)
                    with col_res1:
                        st.subheader("Viaje de Ida"); st.markdown(f"**{st.session_state.calculation_results['trayecto_entrada']}**"); st.metric("Distancia", f"{dist_entrada} km"); st.metric("Tiempo de viaje", f"{min_total_entrada} min"); st.metric("A cargo de la empresa", f"{min_cargo_entrada} min")
                    with col_res2:
                        st.subheader("Viaje de Vuelta"); st.markdown(f"**{st.session_state.calculation_results['trayecto_salida']}**"); st.metric("Distancia", f"{dist_salida} km"); st.metric("Tiempo de viaje", f"{min_total_salida} min"); st.metric("A cargo de la empresa", f"{min_cargo_salida} min")
                    st.markdown("---")
                    total_minutos_a_cargo = min_cargo_entrada + min_cargo_salida
                    st.success(f"**Tiempo total a restar de la jornada:** {total_minutos_a_cargo} minutos")
                    mostrar_horas_de_salida(total_minutos_a_cargo)
                    st.session_state.calculation_results['total_minutos'] = total_minutos_a_cargo
                    if st.button("📧 Enviar mail al equipo", key="btn_csv_mail"): st.session_state.calc_page = 'email_form'; st.rerun()
        else:
            st.error("No se pudieron cargar los datos de tiempos desde la base de datos. Comprueba la conexión y la tabla 'tiempos' en Supabase.")

    with tab2:
        st.subheader("Cálculo por distancia (Reglas ponderadas)")
        
        try:
            gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
        except Exception:
            st.error("Error: La clave de API de Google no está disponible en los secretos.")
            st.stop()
        
        centros_map, lista_provincias_ct = {}, ["(Escribir dirección manual)"]
        if df_tiempos is not None:
            centros_df = df_tiempos[['provincia_ct', 'centro_trabajo']].drop_duplicates(subset=['provincia_ct'])
            centros_map = pd.Series(centros_df.centro_trabajo.values, index=centros_df.provincia_ct).to_dict()
            lista_provincias_ct.extend(sorted(centros_map.keys()))

        def update_field_from_select(field_key, select_key):
            provincia = st.session_state[select_key]
            if provincia in centros_map: st.session_state[field_key] = centros_map[provincia]
            st.session_state.gmaps_results = None
        
        if 'origen_ida' not in st.session_state: st.session_state.origen_ida = ""
        if 'destino_vuelta' not in st.session_state: st.session_state.destino_vuelta = ""

        col1_g, col2_g = st.columns(2)
        with col1_g:
            st.selectbox("Ayuda: Seleccionar centro (Origen ida)", lista_provincias_ct, key='origen_ida_select', on_change=update_field_from_select, args=('origen_ida', 'origen_ida_select'))
            origen_ida = st.text_input("Origen (ida)", key="origen_ida", on_change=lambda: st.session_state.update(gmaps_results=None))
            destino_ida = st.text_input("Destino (ida)", key="destino_ida", on_change=lambda: st.session_state.update(gmaps_results=None))
        with col2_g:
            origen_vuelta = st.text_input("Origen (vuelta)", key="origen_vuelta", on_change=lambda: st.session_state.update(gmaps_results=None))
            st.selectbox("Ayuda: Seleccionar centro (Destino vuelta)", lista_provincias_ct, key='destino_vuelta_select', on_change=update_field_from_select, args=('destino_vuelta', 'destino_vuelta_select'))
            destino_vuelta = st.text_input("Destino (vuelta)", key="destino_vuelta", on_change=lambda: st.session_state.update(gmaps_results=None))
        
        if st.button("Calcular Tiempo por Distancia", type="primary"):
            if all([origen_ida, destino_ida, origen_vuelta, destino_vuelta]):
                with st.spinner('Calculando...'):
                    dist_ida, min_ida, err_ida = calcular_minutos_con_limite(origen_ida, destino_ida, gmaps)
                    dist_vuelta, min_vuelta, err_vuelta = calcular_minutos_con_limite(origen_vuelta, destino_vuelta, gmaps)
                    if err_ida or err_vuelta:
                        if err_ida: st.error(f"Error ida: {err_ida}")
                        if err_vuelta: st.error(f"Error vuelta: {err_vuelta}")
                        st.session_state.gmaps_results = None
                    else:
                        st.session_state.gmaps_results = {"dist_ida": dist_ida, "min_ida": min_ida, "dist_vuelta": dist_vuelta, "min_vuelta": min_vuelta}
                        st.session_state.calculation_results.update({
                            'trayecto_entrada': f"De `{origen_ida}` a `{destino_ida}`", 'trayecto_salida': f"De `{origen_vuelta}` a `{destino_vuelta}`"
                        })
            else: st.warning("Por favor, rellene las cuatro direcciones."); st.session_state.gmaps_results = None
        
        if st.session_state.gmaps_results:
            res = st.session_state.gmaps_results
            es_identico = origen_ida.strip().lower() == destino_vuelta.strip().lower() and destino_ida.strip().lower() == origen_vuelta.strip().lower()
            if es_identico:
                dist, mins = (res['dist_ida'], res['min_ida']) if res['min_ida'] >= res['min_vuelta'] else (res['dist_vuelta'], res['min_vuelta'])
                st.session_state.calculation_results.update({'aviso_pernocta': mins > 80, 'aviso_dieta': dist > 40, 'aviso_jornada': mins > 60})
                if st.session_state.calculation_results['aviso_pernocta']: st.warning(f"🛌 **Aviso Pernocta:** El trayecto ({mins} min) supera los 80 minutos.")
                if st.session_state.calculation_results['aviso_dieta']: st.warning(f"⚠️ **Atención Media Dieta:** El trayecto ({dist:.1f} km) supera los 40km.")
                if st.session_state.calculation_results['aviso_jornada']: st.warning(f"⏰ **Aviso Jornada:** El trayecto ({mins} min) supera los 60 minutos.")
                st.metric(f"TRAYECTO MÁS LARGO ({dist:.1f} km)", f"{_cargo(mins)} min a cargo", f"Tiempo total: {mins} min", delta_color="off")
                total_final = _cargo(mins) * 2
            else:
                st.session_state.calculation_results.update({'aviso_pernocta': res['min_ida'] > 80 or res['min_vuelta'] > 80, 'aviso_dieta': res['dist_ida'] > 40 or res['dist_vuelta'] > 40, 'aviso_jornada': res['min_ida'] > 60 or res['min_vuelta'] > 60})
                if st.session_state.calculation_results['aviso_pernocta']: st.warning("🛌 **Aviso Pernocta:** Uno o ambos trayectos superan los 80 minutos.")
                if st.session_state.calculation_results['aviso_dieta']: st.warning("⚠️ **Atención Media Dieta:** Uno o ambos trayectos superan los 40km.")
                if st.session_state.calculation_results['aviso_jornada']: st.warning("⏰ **Aviso Jornada:** Uno o ambos trayectos superan los 60 minutos.")
                st.metric(f"IDA: {res['dist_ida']:.1f} km", f"{_cargo(res['min_ida'])} min a cargo", f"Tiempo total: {res['min_ida']} min", delta_color="off")
                st.metric(f"VUELTA: {res['dist_vuelta']:.1f} km", f"{_cargo(res['min_vuelta'])} min a cargo", f"Tiempo total: {res['min_vuelta']} min", delta_color="off")
                total_final = _cargo(res['min_ida']) + _cargo(res['min_vuelta'])
            st.markdown("---")
            st.success(f"**Tiempo total a restar de la jornada:** {total_final} minutos")
            mostrar_horas_de_salida(total_final)
            st.session_state.calculation_results['total_minutos'] = total_final
            if st.button("📧 Enviar mail al equipo", key="btn_gmaps_mail"): st.session_state.calc_page = 'email_form'; st.rerun()


# --- PÁGINA DE EMAIL ---
def pagina_email():
    st.header("📧 Redactar y Enviar Notificación")
    if st.button("⬅️ Volver a la calculadora"): 
        st.session_state.calc_page = 'calculator'
        st.rerun()
    st.markdown("---")
    employees_df = cargar_datos_empleados()
    if employees_df is None: 
        st.error("No se pudieron cargar los datos de empleados. No se puede continuar.")
        return
    
    st.subheader("1. Filtrar y Seleccionar Destinatarios")
    col1, col2 = st.columns(2)
    with col1: provincia_sel = st.selectbox("Filtrar por Provincia:", employees_df['PROVINCIA'].unique())
    with col2:
        equipos_en_provincia = employees_df[employees_df['PROVINCIA'] == provincia_sel]['EQUIPO'].unique()
        equipo_sel = st.selectbox("Filtrar por Equipo:", equipos_en_provincia)
    personas_en_provincia = employees_df[employees_df['PROVINCIA'] == provincia_sel]
    personas_en_equipo = personas_en_provincia[personas_en_provincia['EQUIPO'] == equipo_sel]
    nombres_seleccionados = st.multiselect("Destinatarios:", options=personas_en_provincia['NOMBRE COMPLETO'].tolist(), default=personas_en_equipo['NOMBRE COMPLETO'].tolist())
    if not nombres_seleccionados: st.info("Selecciona al menos un destinatario."); st.stop()
    destinatarios_df = employees_df[employees_df['NOMBRE COMPLETO'].isin(nombres_seleccionados)]
    def crear_saludo(nombres):
        if not nombres: return "Hola,"
        nombres_cortos = [name.split()[0] for name in nombres]
        return f"Hola {nombres_cortos[0]}," if len(nombres_cortos) == 1 else f"Hola {', '.join(nombres_cortos[:-1])} y {nombres_cortos[-1]},"
    saludo = crear_saludo(nombres_seleccionados)
    with st.expander("Confirmar destinatarios y correos", expanded=True):
        if not destinatarios_df.empty: st.markdown("\n".join([f"- **{row['NOMBRE COMPLETO']}** ({row['EMAIL']})" for _, row in destinatarios_df.iterrows()]))
        else: st.write("No hay destinatarios.")
    
    tipo_mail = st.radio("Tipo de notificación:", ["Comunicar Horario de Salida", "Notificar Tipo de Jornada", "Informar de Pernocta"], horizontal=True)
    st.subheader("2. Revisa y Edita el Correo")
    res = st.session_state.calculation_results
    asunto_pred, cuerpo_pred = "", ""
    if tipo_mail == "Comunicar Horario de Salida":
        asunto_pred = f"Horario de salida para el {res.get('fecha', 'día de hoy')}"
        cuerpo_pred = f"{saludo}\n\nTe informo del horario de salida calculado para hoy, {res.get('fecha', '')}, será **{res.get('total_minutos', 0)} minutos** antes:\n\n- Salida en horario de Verano: **{res.get('horas_salida', {}).get('Verano', 'N/A')}**\n- Salida en horario Intensivo: **{res.get('horas_salida', {}).get('Habitual Intensivo', 'N/A')}**\n- Salida en horario Normal: **{res.get('horas_salida', {}).get('Normal', 'N/A')}**\n\nTrayectos considerados:\n- Ida: {res.get('trayecto_entrada', 'No especificado')}\n- Vuelta: {res.get('trayecto_salida', 'No especificado')}\n\nSaludos,\n{st.session_state['nombre_completo']}"
    elif tipo_mail == "Notificar Tipo de Jornada":
        asunto_pred = f"Confirmación de jornada para el {res.get('fecha', 'día de hoy')}"
        cuerpo_pred = f"{saludo}\n\nDebido a los desplazamientos del día de hoy ({res.get('fecha', '')}), por favor, confirma el tipo de jornada a aplicar.\n\nRecuerda que los avisos generados han sido:\n- Media Dieta (>40km): **{'Sí' if res.get('aviso_dieta') else 'No'}**\n- Jornada Especial (>60min): **{'Sí' if res.get('aviso_jornada') else 'No'}**\n\nQuedo a la espera de tu confirmación.\n\nSaludos,\n{st.session_state['nombre_completo']}"
    elif tipo_mail == "Informar de Pernocta":
        asunto_pred = f"Aviso de posible pernocta - {res.get('fecha', 'día de hoy')}"
        cuerpo_pred = f"{saludo}\n\nEl cálculo de desplazamiento para hoy, {res.get('fecha', '')}, ha generado un aviso por superar los 80 minutos, lo que podría implicar una pernocta.\n\nPor favor, revisa la planificación y gestiona la reserva de hotel si es necesario.\n\nSaludos,\n{st.session_state['nombre_completo']}"
    
    asunto = st.text_input("Asunto:", asunto_pred)
    cuerpo = st.text_area("Cuerpo del Mensaje:", cuerpo_pred, height=300)
    st.markdown("---")
    
    if st.button("🚀 Enviar Email", type="primary"):
        send_email(destinatarios_df['EMAIL'].tolist(), asunto, cuerpo)

# --- FUNCIÓN PRINCIPAL DEL MÓDULO ---
def mostrar_calculadora_avanzada():
    """Esta es la función que se llamará desde la app principal."""
    inicializar_estado_calculadora()
    
    if st.session_state.calc_page == 'calculator':
        pagina_calculadora()
    elif st.session_state.calc_page == 'email_form':
        pagina_email()