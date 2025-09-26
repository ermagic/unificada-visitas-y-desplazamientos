# Fichero: admin.py (Versión Simplificada - Solo Gestión de Usuarios)
import streamlit as st
import pandas as pd
from database import supabase
from supabase import create_client, Client

# --- CLIENTE ADMIN ---
def get_admin_client() -> Client:
    """Crea un cliente de Supabase con privilegios de administrador (service_key)."""
    try:
        url = st.secrets["supabase"]["url"]
        service_key = st.secrets["supabase"]["service_key"]
        return create_client(url, service_key)
    except Exception:
        st.error("Error crítico: No se pudieron cargar las credenciales de administrador de Supabase.")
        return None

# --- INTERFAZ DE STREAMLIT ---
def mostrar_panel_admin():
    """Muestra la interfaz de gestión de usuarios para administradores."""
    st.header("Panel de Administración 👑")
    supabase_admin = get_admin_client()
    if not supabase or not supabase_admin:
        st.error("La conexión con la base de datos no está disponible."); st.stop()

    # Inicializar estado de sesión para edición
    if 'editing_user_id' not in st.session_state:
        st.session_state.editing_user_id = None

    st.subheader("Gestión de Cuentas de Usuario")

    # --- Crear Nuevo Usuario ---
    with st.expander("➕ Añadir Nuevo Usuario", expanded=False):
        with st.form("create_user_form", clear_on_submit=True):
            st.text_input("Nombre Completo", key="new_name")
            st.text_input("Email", key="new_email")
            st.text_input("Contraseña", key="new_password", type="password")
            st.selectbox("Rol", options=["admin", "supervisor", "coordinador"], key="new_role")

            if st.form_submit_button("Crear Usuario", type="primary"):
                try:
                    # 1. Crear usuario en Supabase Auth
                    user_auth = supabase_admin.auth.admin.create_user({
                        "email": st.session_state.new_email,
                        "password": st.session_state.new_password,
                        "email_confirm": True # Pre-verifica el email
                    })

                    # 2. Insertar perfil en la tabla 'usuarios'
                    supabase_admin.table('usuarios').insert({
                        "id": user_auth.user.id,
                        "nombre_completo": st.session_state.new_name,
                        "rol": st.session_state.new_role
                    }).execute()

                    st.success(f"Usuario '{st.session_state.new_name}' creado con éxito.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al crear usuario: {e}")

    st.markdown("---")

    # --- Listar y Gestionar Usuarios Existentes ---
    st.subheader("Usuarios Registrados")
    try:
        users_response = supabase_admin.table('usuarios').select('*').execute()
        users_df = pd.DataFrame(users_response.data)

        if users_df.empty:
            st.info("No hay usuarios registrados.")
        else:
            for index, user in users_df.iterrows():
                with st.container(border=True):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.markdown(f"**{user['nombre_completo']}**")
                        st.caption(f"Rol: `{user['rol']}` | ID: `{user['id']}`")

                    with col2:
                        if st.button("✏️ Editar", key=f"edit_{user['id']}", use_container_width=True):
                            st.session_state.editing_user_id = user['id']
                            st.rerun()

                    with col3:
                        if st.button("🗑️ Eliminar", key=f"delete_{user['id']}", use_container_width=True):
                            try:
                                # Borrar de la tabla de perfiles y de Auth
                                supabase_admin.table('usuarios').delete().eq('id', user['id']).execute()
                                supabase_admin.auth.admin.delete_user(user['id'])
                                st.success(f"Usuario '{user['nombre_completo']}' eliminado.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al eliminar: {e}")

                    # --- Formulario de Edición (aparece si se ha pulsado 'Editar') ---
                    if st.session_state.editing_user_id == user['id']:
                        with st.form(f"edit_form_{user['id']}"):
                            st.text_input("Nombre Completo", value=user['nombre_completo'], key=f"name_{user['id']}")
                            st.selectbox("Rol", options=["admin", "supervisor", "coordinador"], index=["admin", "supervisor", "coordinador"].index(user['rol']), key=f"role_{user['id']}")
                            st.text_input("Nueva Contraseña (dejar en blanco para no cambiar)", type="password", key=f"pwd_{user['id']}")

                            col_save, col_cancel = st.columns(2)
                            with col_save:
                                if st.form_submit_button("Guardar Cambios", type="primary"):
                                    try:
                                        # Actualizar perfil
                                        update_data = {
                                            'nombre_completo': st.session_state[f"name_{user['id']}"],
                                            'rol': st.session_state[f"role_{user['id']}"]
                                        }
                                        supabase_admin.table('usuarios').update(update_data).eq('id', user['id']).execute()

                                        # Actualizar contraseña si se ha proporcionado una nueva
                                        new_password = st.session_state[f"pwd_{user['id']}"]
                                        if new_password:
                                            supabase_admin.auth.admin.update_user_by_id(user['id'], {"password": new_password})

                                        st.success("Usuario actualizado.")
                                        st.session_state.editing_user_id = None
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error al actualizar: {e}")
                            with col_cancel:
                                if st.form_submit_button("Cancelar", type="secondary"):
                                    st.session_state.editing_user_id = None
                                    st.rerun()
    except Exception as e:
        st.error(f"No se pudieron cargar los usuarios: {e}")