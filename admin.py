# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import bcrypt
from database import obtener_conexion

def mostrar_panel_admin():
    """Muestra el panel de administración con gestión completa de usuarios."""
    st.header("Panel de Administración 👑")
    
    conn = obtener_conexion()
    cursor = conn.cursor()

    # --- Pestañas de la interfaz ---
    tab_manage, tab_add = st.tabs(["👥 Gestionar Usuarios", "➕ Añadir Nuevo Usuario"])

    # --- PESTAÑA 1: GESTIONAR USUARIOS EXISTENTES ---
    with tab_manage:
        st.subheader("Editar o Eliminar un Usuario")

        # --- 1. SELECCIÓN DE USUARIO ---
        # Obtenemos la lista de usuarios para el selector
        try:
            users_list_df = pd.read_sql_query("SELECT id, username, nombre_completo, rol FROM usuarios", conn)
            # Creamos una lista de tuplas (id, 'username (Nombre Completo)') para el selectbox
            user_options = list(users_list_df.itertuples(index=False, name=None))
        except Exception as e:
            st.error(f"No se pudieron cargar los usuarios: {e}")
            user_options = []

        # Usamos un formato especial para mostrar más info en el selectbox
        selected_user_tuple = st.selectbox(
            "Selecciona un usuario para editarlo o eliminarlo:",
            options=user_options,
            format_func=lambda user: f"{user[1]} ({user[2]})", # Muestra -> username (Nombre Completo)
            index=None,
            placeholder="Elige un usuario..."
        )

        # Si se ha seleccionado un usuario, mostramos el formulario de edición
        if selected_user_tuple:
            # Extraemos los datos del usuario seleccionado
            user_id, current_username, user_full_name, user_role = selected_user_tuple
            
            st.markdown("---")
            st.info(f"Estás editando a **{user_full_name}** (Rol: {user_role})")

            # --- 2. FORMULARIO DE EDICIÓN ---
            with st.form(f"edit_user_{user_id}"):
                st.write("#### 📝 Modificar Datos")
                st.caption("Deja un campo en blanco si no quieres modificarlo.")
                
                # Campo para el nuevo nombre de usuario
                new_username = st.text_input("Nuevo nombre de usuario (login)", value=current_username)
                
                # Campo para la nueva contraseña
                new_password = st.text_input("Nueva contraseña (si se quiere cambiar)", type="password")

                submitted = st.form_submit_button("💾 Guardar Cambios", type="primary")

                if submitted:
                    # --- Lógica de actualización ---
                    update_fields = []
                    params = []

                    # Comprobamos si el nombre de usuario ha cambiado y no está vacío
                    if new_username and new_username != current_username:
                        update_fields.append("username = ?")
                        params.append(new_username)

                    # Hasheamos la nueva contraseña SÓLO si se ha introducido una
                    if new_password:
                        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
                        update_fields.append("password_hash = ?")
                        params.append(hashed_password)

                    # Si hay algo que actualizar, ejecutamos la consulta
                    if update_fields:
                        query = f"UPDATE usuarios SET {', '.join(update_fields)} WHERE id = ?"
                        params.append(user_id)
                        
                        try:
                            cursor.execute(query, tuple(params))
                            conn.commit()
                            st.success(f"¡Usuario '{current_username}' actualizado correctamente!")
                            st.rerun() # Recargamos la app para ver los cambios
                        except Exception as e: # sqlite3.IntegrityError
                            st.error(f"Error al actualizar: El nombre de usuario '{new_username}' ya existe.")
                    else:
                        st.warning("No se ha modificado ningún campo.")

            # --- 3. ZONA DE PELIGRO: ELIMINAR USUARIO ---
            st.markdown("---")
            st.write("#### 🗑️ Eliminar Usuario")
            st.warning(f"**Atención:** Esta acción es irreversible. Se borrará el usuario **{current_username}** permanentemente.")
            
            if st.button(f"Eliminar al usuario {current_username}", type="secondary"):
                try:
                    cursor.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
                    conn.commit()
                    st.success(f"Usuario '{current_username}' eliminado con éxito.")
                    st.rerun() # Recargamos la app
                except Exception as e:
                    st.error(f"Error al eliminar el usuario: {e}")


    # --- PESTAÑA 2: AÑADIR NUEVO USUARIO (Sin cambios) ---
    with tab_add:
        with st.form("add_user_form", clear_on_submit=True):
            st.subheader("Crear un Nuevo Usuario")
            nombre = st.text_input("Nombre Completo del Usuario")
            user = st.text_input("Nombre de Usuario (para login)")
            pwd = st.text_input("Contraseña Temporal", type="password")
            rol = st.selectbox("Rol", ["coordinador", "admin"])
            
            if st.form_submit_button("➕ Crear Usuario"):
                if nombre and user and pwd and rol:
                    hashed_password = bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt())
                    try:
                        cursor.execute("INSERT INTO usuarios (nombre_completo, username, password_hash, rol) VALUES (?, ?, ?, ?)", (nombre, user, hashed_password, rol))
                        conn.commit()
                        st.success(f"Usuario '{user}' creado.")
                    except: # sqlite3.IntegrityError
                        st.error(f"El usuario '{user}' ya existe.")
                else:
                    st.warning("Rellena todos los campos.")
    
    # Cerramos la conexión al final de la función
    conn.close()