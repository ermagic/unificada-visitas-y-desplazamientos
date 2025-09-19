# Fichero: auth.py (Versión final y segura para Google Sheets)
import bcrypt
import pandas as pd
from database import get_data

def verificar_usuario(username, password):
    """Verifica el usuario y la contraseña contra los datos de Google Sheets."""
    users_df = get_data("usuarios")
    
    if users_df.empty:
        return None

    # Busca la fila donde el username coincide
    user_data_row = users_df[users_df['username'] == username]

    # Si no se encuentra ninguna fila, el usuario no existe
    if user_data_row.empty:
        return None

    # Extrae los datos de la primera (y única) fila encontrada
    user_data = user_data_row.iloc[0]
    password_hash_from_db = user_data['password_hash']
    
    # Comprueba si el hash es una cadena de texto (string) antes de comparar
    if isinstance(password_hash_from_db, str) and bcrypt.checkpw(password.encode('utf-8'), password_hash_from_db.encode('utf-8')):
        # Si la contraseña es correcta, devuelve los datos del usuario
        return user_data.to_dict()
        
    # Si la contraseña es incorrecta o hay algún problema, devuelve None
    return None