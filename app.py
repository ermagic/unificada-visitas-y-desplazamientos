# Fichero: app.py (Versión con Mercado de Visitas y Logros)
import streamlit as st
from auth import verificar_usuario_supabase
from desplazamientos import mostrar_calculadora_avanzada
from planificador import mostrar_planificador
from admin import mostrar_panel_admin
from supervisor import mostrar_planificador_supervisor
from stats import mostrar_stats
from coordinador_planner import mostrar_planificador_coordinador
from logros import mostrar_logros
from mercado import mostrar_mercado
from database import supabase

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
        st.header(f"Hola, {st.session_state['nombre_completo']}")
        st.caption(f"Rol: {st.session_state.rol.capitalize()}")
        st.markdown("---")

        # --- PANEL DE ANUNCIOS ---
        st.subheader("📢 Anuncios")
        try:
            response = supabase.table('anuncios').select('*').eq('activo', True).order('created_at', desc=True).execute()
            anuncios = response.data
            if anuncios:
                for anuncio in anuncios:
                    st.info(anuncio['mensaje'])
            else:
                st.info("No hay anuncios activos.")
        except Exception as e:
            st.error("No se pudieron cargar los anuncios.")

        if st.session_state.rol in ['admin', 'supervisor']:
            with st.expander("Gestionar Anuncios"):
                with st.form("new_anuncio_form", clear_on_submit=True):
                    nuevo_mensaje = st.text_area("Nuevo anuncio:")
                    if st.form_submit_button("Publicar Anuncio"):
                        if nuevo_mensaje:
                            supabase.table('anuncios').insert({'mensaje': nuevo_mensaje, 'activo': True}).execute()
                            st.rerun()
                
                st.markdown("---")
                st.write("**Anuncios Activos:**")
                if anuncios:
                    for anuncio in anuncios:
                        c1, c2 = st.columns([4, 1])
                        c1.write(anuncio['mensaje'])
                        if c2.button("X", key=f"del_{anuncio['id']}", help="Desactivar anuncio"):
                            supabase.table('anuncios').update({'activo': False}).eq('id', anuncio['id']).execute()
                            st.rerun()
        st.markdown("---")

        # --- Lógica de Navegación ---
        opciones = ["Planificador de Visitas", "Calculadora de Desplazamientos", "Mercado de Visitas", "Logros"]
        
        if st.session_state.rol in ['admin', 'supervisor']:
            opciones.append("Planificador Automático")
            opciones.append("Stats")
        if st.session_state.rol == 'coordinador':
            opciones.append("Planificación Óptima de Visitas")
        if st.session_state.rol == 'admin':
            opciones.append("Gestión de Usuarios")

        pagina_seleccionada = st.radio("Selecciona una herramienta:", opciones)
        
        st.markdown("---")
        if st.button("Cerrar Sesión"):
            supabase.auth.sign_out()
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    # --- Contenido Principal ---
    if pagina_seleccionada == "Planificador de Visitas": mostrar_planificador()
    elif pagina_seleccionada == "Calculadora de Desplazamientos": mostrar_calculadora_avanzada()
    elif pagina_seleccionada == "Mercado de Visitas": mostrar_mercado()
    elif pagina_seleccionada == "Logros": mostrar_logros()
    elif pagina_seleccionada == "Planificador Automático":
        if st.session_state.rol in ['admin', 'supervisor']: mostrar_planificador_supervisor()
        else: st.error("No tienes permisos para acceder a esta sección.")
    elif pagina_seleccionada == "Stats":
        if st.session_state.rol in ['admin', 'supervisor']: mostrar_stats()
        else: st.error("No tienes permisos para acceder a esta sección.")
    elif pagina_seleccionada == "Planificación Óptima de Visitas":
        if st.session_state.rol == 'coordinador': mostrar_planificador_coordinador()
        else: st.error("No tienes permisos para acceder a esta sección.")
    elif pagina_seleccionada == "Gestión de Usuarios":
        if st.session_state.rol == 'admin': mostrar_panel_admin()
        else: st.error("No tienes permisos para acceder a esta sección.")