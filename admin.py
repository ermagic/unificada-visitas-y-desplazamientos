# Fichero: admin.py (Versión final con rediseño visual profesional)
import streamlit as st
import pandas as pd
from database import supabase
from supabase import create_client, Client

def get_admin_client() -> Client:
    try:
        url, service_key = st.secrets["supabase"]["url"], st.secrets["supabase"]["service_key"]
        return create_client(url, service_key)
    except Exception:
        st.error("Error crítico: No se pudieron cargar las credenciales de administrador de Supabase.")
        return None

def mostrar_panel_admin():
    st.header("👑 Panel de Administración", divider="blue")
    supabase_admin = get_admin_client()
    if not supabase or not supabase_admin:
        st.error("La conexión con la base de datos no está disponible."); st.stop()

    if 'editing_user_id' not in st.session_state:
        st.session_state.editing_user_id = None

    with st.expander("➕ Añadir Nuevo Usuario"):
        with st.form("create_user_form", clear_on_submit=True):
            st.subheader("Formulario de Creación")
            col1, col2 = st.columns(2)
            new_name = col1.text_input("Nombre Completo")
            new_role = col2.selectbox("Rol", options=["admin", "supervisor", "coordinador"])
            new_email = col1.text_input("Email")
            new_password = col2.text_input("Contraseña", type="password")
            
            if st.form_submit_button("Crear Usuario", type="primary", use_container_width=True):
                try:
                    user_auth = supabase_admin.auth.admin.create_user({
                        "email": new_email, "password": new_password, "email_confirm": True
                    })
                    supabase_admin.table('usuarios').insert({
                        "id": user_auth.user.id, "nombre_completo": new_name, "rol": new_role
                    }).execute()
                    st.success(f"Usuario '{new_name}' creado con éxito.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al crear usuario: {e}")

    st.divider()
    st.subheader("Usuarios Registrados")
    try:
        users_df = pd.DataFrame(supabase_admin.table('usuarios').select('*').execute().data)
        if users_df.empty:
            st.info("No hay usuarios registrados.")
        else:
            for index, user in users_df.iterrows():
                with st.container(border=True):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.markdown(f"**{user['nombre_completo']}**")
                        st.caption(f"Rol: `{user['rol']}` | ID: `{user['id']}`")
                    if col2.button("✏️ Editar", key=f"edit_{user['id']}", use_container_width=True):
                        st.session_state.editing_user_id = user['id']; st.rerun()
                    if col3.button("🗑️ Eliminar", key=f"delete_{user['id']}", use_container_width=True, type="secondary"):
                        try:
                            supabase_admin.table('usuarios').delete().eq('id', user['id']).execute()
                            supabase_admin.auth.admin.delete_user(user['id'])
                            st.success(f"Usuario '{user['nombre_completo']}' eliminado."); st.rerun()
                        except Exception as e:
                            st.error(f"Error al eliminar: {e}")

                    if st.session_state.editing_user_id == user['id']:
                        with st.form(f"edit_form_{user['id']}"):
                            st.markdown("##### Editando Usuario")
                            c1, c2 = st.columns(2)
                            name = c1.text_input("Nombre", value=user['nombre_completo'], key=f"name_{user['id']}")
                            role = c2.selectbox("Rol", options=["admin", "supervisor", "coordinador"], index=["admin", "supervisor", "coordinador"].index(user['rol']), key=f"role_{user['id']}")
                            pwd = st.text_input("Nueva Contraseña (dejar en blanco para no cambiar)", type="password", key=f"pwd_{user['id']}")

                            c_save, c_cancel = st.columns(2)
                            if c_save.form_submit_button("Guardar", type="primary"):
                                try:
                                    supabase_admin.table('usuarios').update({'nombre_completo': name, 'rol': role}).eq('id', user['id']).execute()
                                    if pwd:
                                        supabase_admin.auth.admin.update_user_by_id(user['id'], {"password": pwd})
                                    st.success("Usuario actualizado."); st.session_state.editing_user_id = None; st.rerun()
                                except Exception as e: st.error(f"Error al actualizar: {e}")
                            if c_cancel.form_submit_button("Cancelar"):
                                st.session_state.editing_user_id = None; st.rerun()
    except Exception as e:
        st.error(f"No se pudieron cargar los usuarios: {e}")