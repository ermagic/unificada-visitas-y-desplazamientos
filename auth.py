# Fichero: auth.py (Versión Supabase)
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
        # Supabase se encarga de la seguridad, el hashing y la verificación.
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        user = response.user
        
        if user:
            # Si el login es exitoso, obtenemos su perfil de la tabla 'usuarios'
            profile_response = supabase.table('usuarios').select('*').eq('id', user.id).single().execute()
            user_data = profile_response.data
            return user_data # Devuelve el perfil completo (id, nombre_completo, rol)

    except Exception as e:
        # Supabase devuelve un error si las credenciales son incorrectas
        # Lo capturamos para no mostrar mensajes de error técnicos al usuario.
        return None
    
    return None