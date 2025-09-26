# Fichero: admin.py (Versión con punto de partida)
import streamlit as st
import pandas as pd
from database import supabase
from supabase import create_client, Client

def get_admin_client() -> Client:
    try:
        url = st.secrets["supabase"]["url"]
        service_key = st.secrets["supabase"]["service_key"]
        return create_client(url, service_key)
    except Exception:
        st.error("Error crítico: No se pudieron cargar las credenciales de administrador.")
        return None

def mostrar_panel_admin():
    st.header("Panel de Administración 👑")
    supabase_admin = get_admin_client()
    if not supabase or not supabase_admin:
        st.error("La conexión con la base de datos no está disponible."); st.stop()

    if 'editing_user_id' not in st.session_state:
        st.session_state.editing_user_id = None

    st.subheader("Gestión de Cuentas de Usuario")
    with st.expander("➕ Añadir Nuevo Usuario"):
        with st.form("create_user_form", clear_on_submit=True):
            st.text_input("Nombre Completo", key="new_name")
            st.text_input("Email", key="new_email")
            st.text_input("Contraseña", key="new_password", type="password")
            st.selectbox("Rol", options=["admin", "supervisor", "coordinador"], key="new_role")
            st.text_input("Punto de Partida", key="new_start_point", placeholder="Ej: Plaça de Catalunya, Barcelona")
            if st.form_submit_button("Crear Usuario", type="primary"):
                try:
                    user_auth = supabase_admin.auth.admin.create_user({"email": st.session_state.new_email, "password": st.session_state.new_password, "email_confirm": True})
                    supabase_admin.table('usuarios').insert({
                        "id": user_auth.user.id,
                        "nombre_completo": st.session_state.new_name,
                        "rol": st.session_state.new_role,
                        "punto_partida": st.session_state.new_start_point
                    }).execute()
                    st.success(f"Usuario '{st.session_state.new_name}' creado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al crear usuario: {e}")

    st.markdown("---")
    st.subheader("Usuarios Registrados")
    try:
        users_response = supabase_admin.table('usuarios').select('*').execute()
        users_df = pd.DataFrame(users_response.data)
        for index, user in users_df.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.markdown(f"**{user['nombre_completo']}** (`{user['rol']}`)")
                    st.caption(f"Punto Partida: {user.get('punto_partida') or 'No definido'}")
                if col2.button("✏️ Editar", key=f"edit_{user['id']}", use_container_width=True):
                    st.session_state.editing_user_id = user['id']; st.rerun()
                if col3.button("🗑️ Eliminar", key=f"delete_{user['id']}", use_container_width=True):
                    supabase_admin.table('usuarios').delete().eq('id', user['id']).execute()
                    supabase_admin.auth.admin.delete_user(user['id'])
                    st.success(f"Usuario '{user['nombre_completo']}' eliminado."); st.rerun()

                if st.session_state.editing_user_id == user['id']:
                    with st.form(f"edit_form_{user['id']}"):
                        st.text_input("Nombre Completo", value=user['nombre_completo'], key=f"name_{user['id']}")
                        st.selectbox("Rol", options=["admin", "supervisor", "coordinador"], index=["admin", "supervisor", "coordinador"].index(user['rol']), key=f"role_{user['id']}")
                        st.text_input("Punto de Partida", value=user.get('punto_partida', ''), key=f"start_point_{user['id']}")
                        st.text_input("Nueva Contraseña (dejar en blanco para no cambiar)", type="password", key=f"pwd_{user['id']}")
                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("Guardar Cambios", type="primary"):
                            update_data = {'nombre_completo': st.session_state[f"name_{user['id']}"], 'rol': st.session_state[f"role_{user['id']}"], 'punto_partida': st.session_state[f"start_point_{user['id']}"]}
                            supabase_admin.table('usuarios').update(update_data).eq('id', user['id']).execute()
                            if st.session_state[f"pwd_{user['id']}"]:
                                supabase_admin.auth.admin.update_user_by_id(user['id'], {"password": st.session_state[f"pwd_{user['id']}"]})
                            st.success("Usuario actualizado."); st.session_state.editing_user_id = None; st.rerun()
                        if c2.form_submit_button("Cancelar"):
                            st.session_state.editing_user_id = None; st.rerun()
    except Exception as e:
        st.error(f"No se pudieron cargar los usuarios: {e}")
