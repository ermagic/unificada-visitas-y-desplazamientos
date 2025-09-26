# Fichero: admin.py (Versión Supabase)
import streamlit as st
import pandas as pd
from database import supabase # Importamos el cliente anon
from supabase import create_client, Client # Necesario para el cliente admin

def get_admin_client() -> Client:
    """Crea un cliente con permisos de administrador."""
    try:
        url = st.secrets["supabase"]["url"]
        service_key = st.secrets["supabase"]["service_key"]
        return create_client(url, service_key)
    except Exception:
        return None

def mostrar_panel_admin():
    st.header("Panel de Administración 👑")

    supabase_admin = get_admin_client()
    if not supabase or not supabase_admin:
        st.error("La conexión con la base de datos no está disponible.")
        st.stop()

    # --- Cargar datos ---
    users_response = supabase.table('usuarios').select('id, nombre_completo, rol').execute()
    users_df = pd.DataFrame(users_response.data)

    tab_manage, tab_add = st.tabs(["👥 Gestionar Usuarios", "➕ Añadir Nuevo Usuario"])

    # --- PESTAÑA 1: GESTIONAR USUARIOS ---
    with tab_manage:
        st.subheader("Ver o Eliminar un Usuario")
        if users_df.empty:
            st.warning("No hay usuarios para gestionar.")
        else:
            st.dataframe(users_df.rename(columns={
                'id': 'ID de Usuario',
                'nombre_completo': 'Nombre Completo',
                'rol': 'Rol'
            }))
            
            st.markdown("---")
            st.subheader("Eliminar un usuario")
            user_to_delete_id = st.selectbox(
                "Selecciona un usuario para eliminar (por su ID):",
                options=[user_id for user_id in users_df['id'] if user_id != st.session_state['usuario_id']],
                format_func=lambda x: users_df.loc[users_df['id'] == x, 'nombre_completo'].iloc[0]
            )

            if st.button(f"🗑️ Eliminar usuario seleccionado", type="secondary"):
                try:
                    # Usamos el cliente admin para borrar el usuario de auth
                    supabase_admin.auth.admin.delete_user(user_to_delete_id)
                    # La tabla 'usuarios' se actualiza en cascada gracias al FOREIGN KEY
                    st.success(f"Usuario eliminado correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al eliminar usuario: {e}")

    # --- PESTAÑA 2: AÑADIR NUEVO USUARIO ---
    with tab_add:
        with st.form("add_user_form", clear_on_submit=True):
            nombre = st.text_input("Nombre Completo")
            email = st.text_input("Email del Usuario (para login)")
            pwd = st.text_input("Contraseña", type="password")
            rol = st.selectbox("Rol", ["coordinador", "admin"])
            
            if st.form_submit_button("➕ Crear Usuario"):
                if not all([nombre, email, pwd, rol]):
                    st.warning("Rellena todos los campos.")
                else:
                    try:
                        # 1. Crear el usuario en el sistema de autenticación de Supabase
                        user_response = supabase.auth.sign_up({
                            "email": email,
                            "password": pwd
                        })
                        new_user = user_response.user
                        
                        if new_user:
                            # 2. Insertar el perfil en la tabla 'usuarios'
                            supabase.table('usuarios').insert({
                                'id': new_user.id,
                                'nombre_completo': nombre,
                                'rol': rol
                            }).execute()
                            st.success(f"Usuario '{email}' creado.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error al crear el usuario: {e}")