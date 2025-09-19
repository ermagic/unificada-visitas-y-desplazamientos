# Fichero: admin.py (Versión final para Google Sheets)
import streamlit as st
import pandas as pd
import bcrypt
from database import get_data, update_data # <-- CAMBIO IMPORTANTE

def mostrar_panel_admin():
    """Muestra el panel de administración con gestión completa de usuarios desde Google Sheets."""
    st.header("Panel de Administración 👑")
    
    # --- Cargar datos ---
    users_df = get_data("usuarios")
    # Asegurarse de que la columna 'id' sea numérica para poder calcular el máximo
    if not users_df.empty:
        users_df['id'] = pd.to_numeric(users_df['id'])

    tab_manage, tab_add = st.tabs(["👥 Gestionar Usuarios", "➕ Añadir Nuevo Usuario"])

    # --- PESTAÑA 1: GESTIONAR USUARIOS ---
    with tab_manage:
        st.subheader("Editar o Eliminar un Usuario")

        if users_df.empty:
            st.warning("No hay usuarios para gestionar.")
        else:
            user_options = users_df['username'].tolist()
            selected_username = st.selectbox(
                "Selecciona un usuario:",
                options=user_options,
                index=None,
                placeholder="Elige un usuario..."
            )

            if selected_username:
                user_data = users_df[users_df['username'] == selected_username].iloc[0]
                
                with st.form(f"edit_user_{user_data['id']}"):
                    st.write(f"#### Editando a *{user_data['nombre_completo']}*")
                    new_username = st.text_input("Nuevo nombre de usuario", value=user_data['username'])
                    new_password = st.text_input("Nueva contraseña (dejar en blanco para no cambiar)", type="password")

                    if st.form_submit_button("💾 Guardar Cambios"):
                        changes_made = False
                        user_index = user_data.name
                        
                        if new_username and new_username != user_data['username']:
                            users_df.loc[user_index, 'username'] = new_username
                            changes_made = True

                        if new_password:
                            hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                            users_df.loc[user_index, 'password_hash'] = hashed_pw
                            changes_made = True

                        if changes_made:
                            if update_data("usuarios", users_df):
                                st.success("Usuario actualizado.")
                                st.rerun()
                        else:
                            st.warning("No se ha modificado ningún campo.")

                st.markdown("---")
                if st.button(f"🗑️ Eliminar usuario {user_data['username']}", type="secondary"):
                    users_df.drop(index=user_data.name, inplace=True)
                    if update_data("usuarios", users_df):
                        st.success(f"Usuario '{user_data['username']}' eliminado.")
                        st.rerun()

    # --- PESTAÑA 2: AÑADIR NUEVO USUARIO ---
    with tab_add:
        with st.form("add_user_form", clear_on_submit=True):
            nombre = st.text_input("Nombre Completo")
            user = st.text_input("Nombre de Usuario (login)")
            pwd = st.text_input("Contraseña", type="password")
            rol = st.selectbox("Rol", ["coordinador", "admin"])
            
            if st.form_submit_button("➕ Crear Usuario"):
                if not (nombre and user and pwd and rol):
                    st.warning("Rellena todos los campos.")
                elif not users_df[users_df['username'] == user].empty:
                    st.error(f"El usuario '{user}' ya existe.")
                else:
                    hashed_pw = bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    new_id = (users_df['id'].max() + 1) if not users_df.empty else 1
                    
                    new_user_df = pd.DataFrame([{
                        'id': new_id,
                        'nombre_completo': nombre,
                        'username': user,
                        'password_hash': hashed_pw,
                        'rol': rol
                    }])
                    
                    updated_df = pd.concat([users_df, new_user_df], ignore_index=True)
                    
                    if update_data("usuarios", updated_df):
                        st.success(f"Usuario '{user}' creado.")
                        st.rerun()