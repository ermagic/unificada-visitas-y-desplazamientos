# Fichero: auth.py (Sin cambios)
import streamlit as st
from database import supabase

def verificar_usuario_supabase(email, password):
    if not supabase:
        st.error("La conexión con la base de datos no está disponible.")
        return None
        
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        user = response.user
        
        if user:
            profile_response = supabase.table('usuarios').select('*').eq('id', user.id).single().execute()
            user_profile = profile_response.data
            
            if user_profile:
                return user_profile
            else:
                st.error("Login correcto, pero no se encontró un perfil de usuario asociado.")
                supabase.auth.sign_out()
                return None
    except Exception as e:
        st.error("Email o contraseña incorrectos.")
        return None
    
    return None