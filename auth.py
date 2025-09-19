# Fichero: auth.py (VERSIÓN DE PRUEBA FINAL - SIN BCRYPT)
import pandas as pd
from database import get_data

def verificar_usuario(username, password):
    """
    Verifica el usuario comparando texto plano con texto plano.
    ESTO ES SOLO PARA DEPURACIÓN Y NO ES SEGURO.
    """
    users_df = get_data("usuarios")
    
    if users_df.empty:
        return None

    user_data_row = users_df[users_df['username'] == username]

    if user_data_row.empty:
        return None

    user_data = user_data_row.iloc[0]
    
    # Leemos la contraseña en texto plano de la hoja
    password_from_sheet = str(user_data['password_hash'])

    # Comparamos directamente la contraseña del formulario con la de la hoja
    if password == password_from_sheet:
        return user_data.to_dict()
        
    return None