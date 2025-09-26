# Fichero: auth.py (Versión de DIAGNÓSTICO)
import streamlit as st
from database import supabase # Importamos el cliente ya inicializado

def verificar_usuario(email, password):
    """
    Verifica las credenciales del usuario contra la autenticación de Supabase.
    Devuelve los datos del usuario y su perfil si es exitoso.
    """
    if not supabase:
        st.error("La conexión con la base de datos no está disponible.")
        return None
        
    try:
        # Intenta iniciar sesión en Supabase
        st.info("Intentando iniciar sesión...")
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        user = response.user
        
        if user:
            # Si el login tiene éxito, intenta buscar el perfil
            st.info("Login correcto. Buscando perfil del usuario...")
            profile_response = supabase.table('usuarios').select('*').eq('id', user.id).single().execute()
            user_data = profile_response.data
            
            # Si no encuentra el perfil, user_data estará vacío
            if not user_data:
                st.error("Error Crítico: El login fue correcto, pero no se encontró un perfil para este usuario en la tabla 'usuarios'. Verifica que el UID coincide.")
                return None

            st.success("¡Perfil encontrado! Deberías poder entrar.")
            return user_data

    except Exception as e:
        # ¡ESTA LÍNEA ES LA MÁS IMPORTANTE!
        # Muestra el error técnico real en la pantalla.
        st.error("Ha ocurrido un error durante la autenticación:")
        st.exception(e) # Esto mostrará el error completo y detallado
        return None
    
    return None