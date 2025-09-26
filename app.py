# Fichero: app.py (Versión con rediseño visual profesional)
import streamlit as st
from auth import verificar_usuario_supabase
from desplazamientos import mostrar_calculadora_avanzada
from planificador import mostrar_planificador
from admin import mostrar_panel_admin
from supervisor import mostrar_planificador_supervisor
from database import supabase

# --- CONFIGURACIÓN DE LA PÁGINA Y ESTILOS ---
st.set_page_config(
    page_title="Plataforma Coordinadores",
    page_icon="🌐", # Icono de fibra/mundo
    layout="wide"
)

# --- ESTILOS CSS PERSONALIZADOS ---
# Paleta de colores: Azul corporativo, acento cian, grises neutros.
# Se usan contenedores con bordes redondeados y sombras para un efecto "tarjeta".
st.markdown("""
<style>
    /* Estilo general del cuerpo */
    .stApp {
        background-color: #F0F2F6;
    }
    /* Estilo de los botones principales */
    .stButton > button {
        border-radius: 8px;
        border: 1px solid #0072C6;
        color: #FFFFFF;
        background-color: #0072C6;
    }
    .stButton > button:hover {
        border: 1px solid #005A9E;
        background-color: #005A9E;
        color: #FFFFFF;
    }
    /* Contenedores con borde para efecto tarjeta */
    .st-emotion-cache-1jicfl2 {
        border-radius: 10px;
        border: 1px solid #E0E0E0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    /* Títulos y cabeceras */
    h1, h2, h3 {
        color: #1E293B; /* Un gris oscuro en lugar de negro puro */
    }
</style>
""", unsafe_allow_html=True)


# --- Gestión de Sesión ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- Página de Login ---
if not st.session_state.logged_in:
    # --- Centrar el formulario de login ---
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.image("https://i.imgur.com/8y03Etc.png", width=200) # Reemplaza con la URL de tu logo
        st.title("Plataforma de Coordinación")
        st.text("Gestión de visitas y desplazamientos.")

        with st.form("login_form"):
            email = st.text_input("📧 Email")
            password = st.text_input("🔑 Contraseña", type="password")

            if st.form_submit_button("Iniciar Sesión", type="primary", use_container_width=True):
                user_profile = verificar_usuario_supabase(email, password)

                if user_profile:
                    st.session_state.logged_in = True
                    st.session_state.email = email
                    st.session_state.nombre_completo = user_profile['nombre_completo']
                    st.session_state.rol = user_profile['rol']
                    st.session_state.usuario_id = user_profile['id']
                    st.rerun()
else:
    # --- Aplicación Principal (si el usuario ha iniciado sesión) ---
    with st.sidebar:
        st.image("https://i.imgur.com/8y03Etc.png", width=100) # Logo en la barra lateral
        st.header(f"Hola, {st.session_state['nombre_completo'].split()[0]}")
        st.caption(f"Rol: {st.session_state.rol.capitalize()}")
        st.divider()

        # --- NAVEGACIÓN BASADA EN ROLES CON ICONOS ---
        opciones = {
            "Planificador de Visitas": "🗓️",
            "Calculadora de Desplazamientos": "🚗",
        }
        
        if st.session_state.rol in ['admin', 'supervisor']:
            opciones["Planificador Automático"] = "🤖"
        
        if st.session_state.rol == 'admin':
            opciones["Gestión de Usuarios"] = "👑"

        # Crear etiquetas con iconos para el radio
        opciones_con_iconos = [f"{icon} {name}" for name, icon in opciones.items()]
        
        pagina_seleccionada_con_icono = st.radio(
            "Menú de Herramientas:",
            opciones_con_iconos,
            label_visibility="collapsed"
        )
        
        # Extraer el nombre de la página sin el icono
        pagina_seleccionada = pagina_seleccionada_con_icono.split(" ", 1)[1]

        st.divider()
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            supabase.auth.sign_out()
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # --- Contenido Principal ---
    if pagina_seleccionada == "Planificador de Visitas":
        mostrar_planificador()
    elif pagina_seleccionada == "Calculadora de Desplazamientos":
        mostrar_calculadora_avanzada()
    elif pagina_seleccionada == "Planificador Automático":
        if st.session_state.rol in ['admin', 'supervisor']:
            mostrar_planificador_supervisor()
        else:
            st.error("No tienes permisos para acceder a esta sección.")
    elif pagina_seleccionada == "Gestión de Usuarios":
        if st.session_state.rol == 'admin':
            mostrar_panel_admin()
        else:
            st.error("No tienes permisos para acceder a esta sección.")