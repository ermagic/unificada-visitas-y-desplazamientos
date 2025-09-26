# Fichero: app.py (Versión con diseño original + logo + corrección de texto en calendario)
import streamlit as st
from auth import verificar_usuario_supabase
from desplazamientos import mostrar_calculadora_avanzada
from planificador import mostrar_planificador
from admin import mostrar_panel_admin
from supervisor import mostrar_planificador_supervisor
from database import supabase

st.set_page_config(
    page_title="App Unificada",
    page_icon="assets/logo.png",
    layout="wide"
)

# --- INICIO DE LA CORRECCIÓN ---
# Añadimos CSS para que el texto de los eventos del calendario se ajuste en varias líneas
st.markdown("""
<style>
    .fc-event-title {
        white-space: normal !important; /* Permite que el texto salte de línea */
    }
</style>
""", unsafe_allow_html=True)
# --- FIN DE LA CORRECCIÓN ---


# --- Gestión de Sesión ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- Página de Login ---
if not st.session_state.logged_in:
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.image("assets/logo.png", width=200)
        st.title("Plataforma de Coordinación 🗺️")
        
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Contraseña", type="password")

            if st.form_submit_button("Iniciar Sesión", type="primary"):
                user_profile = verificar_usuario_supabase(email, password)

                if user_profile:
                    st.session_state.logged_in = True
                    st.session_state.email = email
                    st.session_state.nombre_completo = user_profile['nombre_completo']
                    st.session_state.rol = user_profile['rol']
                    st.session_state.usuario_id = user_profile['id']
                    st.rerun()
else:
    # --- Aplicación Principal ---
    with st.sidebar:
        st.image("assets/logo.png", width=100)
        st.header(f"Hola, {st.session_state['nombre_completo']}")
        st.caption(f"Rol: {st.session_state.rol.capitalize()}")
        st.markdown("---")

        opciones = ["Planificador de Visitas", "Calculadora de Desplazamientos"]
        
        if st.session_state.rol in ['admin', 'supervisor']:
            opciones.append("Planificador Automático")
        
        if st.session_state.rol == 'admin':
            opciones.append("Gestión de Usuarios")

        pagina_seleccionada = st.radio("Selecciona una herramienta:", opciones)

        st.markdown("---")
        if st.button("Cerrar Sesión"):
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