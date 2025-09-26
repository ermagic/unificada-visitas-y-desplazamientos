# Fichero: app.py (Versión Final)
import streamlit as st
from auth import verificar_usuario_supabase # <--- CAMBIO IMPORTANTE
from desplazamientos import mostrar_calculadora_avanzada
from planificador import mostrar_planificador
from admin import mostrar_panel_admin
from database import supabase # Importamos para gestionar el logout

st.set_page_config(page_title="App Unificada", layout="wide")

# --- Gestión de Sesión ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- Página de Login ---
if not st.session_state.logged_in:
    st.title("Plataforma de Coordinación 🗺️")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Contraseña", type="password")
        
        if st.form_submit_button("Iniciar Sesión", type="primary"):
            # Llamamos a la nueva función de autenticación de Supabase
            user_profile = verificar_usuario_supabase(email, password)
            
            if user_profile:
                st.session_state.logged_in = True
                # Guardamos los datos del perfil obtenidos de la tabla 'usuarios'
                st.session_state.email = user_profile['email'] # Asumiendo que tienes un campo email
                st.session_state.nombre_completo = user_profile['nombre_completo']
                st.session_state.rol = user_profile['rol']
                st.session_state.usuario_id = user_profile['id'] # Este es el UUID
                st.rerun()
            # La función verificar_usuario_supabase ya muestra el st.error()
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
            supabase.auth.sign_out() # Cerramos sesión en Supabase
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