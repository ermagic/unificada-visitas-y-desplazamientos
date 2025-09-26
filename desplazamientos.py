# Fichero: desplazamientos.py (Versión Corregida)
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
        # --- LÍNEA CORREGIDA ---
        # Se ha eliminado .limit() para que cargue todas las filas
        # permitidas por la configuración de Supabase.
        response = supabase.table('tiempos').select('*').execute()
        
        df = pd.DataFrame(response.data)
        
        if df.empty:
            st.warning("La tabla 'tiempos' de Supabase no devolvió datos.")
            return None

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

@st.cache_data
def cargar_datos_coordinadores():
    """Carga los datos de coordinadores desde Supabase."""
    try:
        response = supabase.table('coordinadores').select('*').execute()
        df = pd.DataFrame(response.data)
        return df
    except Exception as e:
        st.error(f"Error al cargar datos de coordinadores: {e}")
        return pd.DataFrame()

def send_email(to_addrs, subject, body):
    """Envía un email usando las credenciales de Streamlit Secrets."""
    try:
        smtp_user = st.secrets["email"]["smtp_user"]
        smtp_pass = st.secrets["email"]["smtp_pass"]
        
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = ", ".join(to_addrs)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_addrs, msg.as_string())
        st.success("✅ Email enviado correctamente.")
    except Exception as e:
        st.error(f"Error al enviar el email: {e}")

# --- PÁGINAS DE LA INTERFAZ ---

def mostrar_calculadora_avanzada():
    """Muestra la interfaz principal de la calculadora."""
    st.header("Calculadora Avanzada de Desplazamientos 🚗")
    inicializar_estado_calculadora()

    df_tiempos = cargar_datos_tiempos()
    
    if df_tiempos is None or df_tiempos.empty:
        st.error("No se pudieron cargar los datos de tiempos. La calculadora no puede funcionar.")
        st.stop()
    
    # --- Formulario de selección ---
    st.subheader("1. Selecciona Origen y Destino")

    col1, col2 = st.columns(2)
    with col1:
        provincias = sorted(df_tiempos['provincia_ct'].unique().tolist())
        provincia_sel = st.selectbox("Provincia del Centro de Trabajo:", options=provincias, index=None, placeholder="Elige una provincia...")

    if provincia_sel:
        df_filtrado_prov = df_tiempos[df_tiempos['provincia_ct'] == provincia_sel]
        
        with col2:
            centros = sorted(df_filtrado_prov['centro_trabajo'].unique().tolist())
            centro_sel = st.selectbox("Selecciona tu Centro de Trabajo (Origen):", options=centros, index=None, placeholder="Elige un centro...")
        
        if centro_sel:
            df_filtrado_centro = df_filtrado_prov[df_filtrado_prov['centro_trabajo'] == centro_sel]
            poblaciones = sorted(df_filtrado_centro['poblacion'].unique().tolist())
            poblacion_sel = st.selectbox("Selecciona la Población de Destino:", options=poblaciones, index=None, placeholder="Elige una población...")
            
            if poblacion_sel:
                st.markdown("---")
                if st.button("Calcular Desplazamiento", type="primary"):
                    resultado = df_filtrado_centro[df_filtrado_centro['poblacion'] == poblacion_sel].iloc[0]
                    
                    res_dict = {
                        "fecha": dt.date.today().strftime('%d/%m/%Y'),
                        "provincia": provincia_sel,
                        "origen": centro_sel,
                        "destino": poblacion_sel,
                        "distancia": resultado['distancia'],
                        "minutos_total": resultado['minutos_total'],
                        "minutos_cargo": resultado['minutos_cargo'],
                        "aviso_dieta": resultado['distancia'] > 40,
                        "aviso_jornada": resultado['minutos_cargo'] > 60,
                        "aviso_pernocta": resultado['minutos_cargo'] > 80
                    }
                    st.session_state.calculation_results = res_dict
    
    # --- Mostrar resultados ---
    if st.session_state.calculation_results:
        res = st.session_state.calculation_results
        st.subheader("2. Resultados del Cálculo")
        
        # Avisos
        if res['aviso_dieta'] or res['aviso_jornada'] or res['aviso_pernocta']:
            st.warning("⚠️ **¡Atención! Se han generado los siguientes avisos:**")
            if res['aviso_dieta']: st.markdown("- **Media Dieta:** La distancia supera los 40 km.")
            if res['aviso_jornada']: st.markdown("- **Jornada Especial:** El tiempo a cargo de la empresa supera los 60 min.")
            if res['aviso_pernocta']: st.markdown("- **Posible Pernocta:** El tiempo a cargo de la empresa supera los 80 min.")

        # Detalles del cálculo
        st.markdown(f"""
        | Concepto | Valor |
        | :--- | :--- |
        | **Fecha** | {res['fecha']} |
        | **Origen** | {res['origen']} |
        | **Destino** | {res['destino']} ({res['provincia']}) |
        | **Distancia** | `{res['distancia']:.2f} km` |
        | **Tiempo Total Viaje** | `{res['minutos_total']} minutos` |
        | **Tiempo a Cargo Empresa** | `{res['minutos_cargo']} minutos` |
        """)
        st.markdown("---")
        
        # --- Opciones de comunicación ---
        st.subheader("3. Comunicar a Coordinación")
        df_coordinadores = cargar_datos_coordinadores()
        
        if df_coordinadores.empty:
            st.warning("No se han encontrado coordinadores a los que notificar.")
        else:
            opciones_email = ["Confirmar Jornada", "Informar de Pernocta"]
            tipo_mail = st.radio("Elige el tipo de email a generar:", options=opciones_email, horizontal=True)
            
            mostrar_formulario_email(res, tipo_mail, df_coordinadores)

def mostrar_formulario_email(res, tipo_mail, coordinadores_df):
    """Muestra el formulario para redactar y enviar el email."""
    
    destinatarios_df = coordinadores_df[coordinadores_df['PROVINCIA'] == res['provincia']]
    if destinatarios_df.empty:
        st.warning(f"No hay coordinadores asignados a la provincia de **{res['provincia']}**.")
        return

    st.info(f"Este email se enviará a: **{', '.join(destinatarios_df['NOMBRE'].tolist())}**")

    # Contenido predefinido según la plantilla
    saludo = "Buenos días,"
    asunto_pred = ""
    cuerpo_pred = ""

    if tipo_mail == "Confirmar Jornada":
        asunto_pred = f"Confirmación de jornada - {res.get('fecha', 'día de hoy')}"
        cuerpo_pred = f"""{saludo}

Respecto a los desplazamientos del día de hoy ({res.get('fecha', '')}), por favor, confirma el tipo de jornada a aplicar.

Recuerda que los avisos generados han sido:
- Media Dieta (>40km): **{'Sí' if res.get('aviso_dieta') else 'No'}**
- Jornada Especial (>60min): **{'Sí' if res.get('aviso_jornada') else 'No'}**

Quedo a la espera de tu confirmación.

Saludos,
{st.session_state['nombre_completo']}"""
    elif tipo_mail == "Informar de Pernocta":
        asunto_pred = f"Aviso de posible pernocta - {res.get('fecha', 'día de hoy')}"
        cuerpo_pred = f"""{saludo}

El cálculo de desplazamiento para hoy, {res.get('fecha', '')}, ha generado un aviso por superar los 80 minutos, lo que podría implicar una pernocta.

Por favor, revisa la planificación y gestiona la reserva de hotel si es necesario.

Saludos,
{st.session_state['nombre_completo']}"""
    
    asunto = st.text_input("Asunto:", asunto_pred)
    cuerpo = st.text_area("Cuerpo del Mensaje:", cuerpo_pred, height=300)
    st.markdown("---")
    
    if st.button("🚀 Enviar Email", type="primary"):
        send_email(destinatarios_df['EMAIL'].tolist(), asunto, cuerpo)