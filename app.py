# Fichero: app.py (Versión Supabase)
import streamlit as st
from auth import verificar_usuario
from desplazamientos import mostrar_calculadora_avanzada
from planificador import mostrar_planificador
from admin import mostrar_panel_admin

st.set_page_config(page_title="App Unificada", layout="wide")

# --- Gestión de Sesión ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- Página de Login ---
if not st.session_state.logged_in:
    st.title("Plataforma de Coordinación 🗺️")
    with st.form("login_form"):
        # CAMBIO: Usamos email en lugar de username
        email = st.text_input("Email") 
        password = st.text_input("Contraseña", type="password")
        
        if st.form_submit_button("Iniciar Sesión"):
            user_data = verificar_usuario(email, password)
            if user_data:
                st.session_state.logged_in = True
                # Guardamos los datos del perfil obtenidos de la tabla 'usuarios'
                st.session_state.email = email
                st.session_state.nombre_completo = user_data['nombre_completo']
                st.session_state.rol = user_data['rol']
                st.session_state.usuario_id = user_data['id'] # Este es el UUID
                st.rerun()
            else:
                st.error("Email o contraseña incorrectos")
else:
    # --- Aplicación Principal (si el usuario ha iniciado sesión) ---
    with st.sidebar:
        st.header(f"Hola, {st.session_state['nombre_completo']}")
        st.caption(f"Rol: {st.session_state.rol.capitalize()}")
        st.markdown("---")

        opciones = ["Planificador de Visitas", "Calculadora de Desplazamientos"]
        if st.session_state.rol == 'admin':
            opciones.append("Administración")
        
        pagina_seleccionada = st.radio("Selecciona una herramienta:", opciones)
        
        st.markdown("---")
        if st.button("Cerrar Sesión"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # --- Contenido Principal ---
    if pagina_seleccionada == "Planificador de Visitas":
        mostrar_planificador()
    elif pagina_seleccionada == "Calculadora de Desplazamientos":
        mostrar_calculadora_avanzada()
    elif pagina_seleccionada == "Administración":
        if st.session_state.rol == 'admin':
            mostrar_panel_admin()
        else:
            st.error("No tienes permisos para acceder a esta sección.")