# Fichero: auth.py (Versión final corregida)
import pandas as pd
import bcrypt
from database import get_data

def verificar_usuario(username, password):
    """
    Verifica las credenciales del usuario contra los datos de Google Sheets.
    Usa bcrypt para comparar la contraseña de forma segura.
    """
    users_df = get_data("usuarios")
    
    # Si el DataFrame está vacío o hay un error, no se puede verificar.
    if users_df.empty:
        st.error("No se pudo cargar la información de usuarios desde la base de datos.")
        return None

    user_data_row = users_df[users_df['username'] == username]

    # Si no se encuentra el usuario por su 'username', no existe.
    if user_data_row.empty:
        return None

    user_data = user_data_row.iloc[0]
    
    # Extraemos el hash de la contraseña guardado en Google Sheets.
    password_hash_from_sheet = user_data['password_hash']

    # Usamos bcrypt.checkpw para comparar la contraseña introducida (en bytes)
    # con el hash guardado (también en bytes).
    if bcrypt.checkpw(password.encode('utf-8'), password_hash_from_sheet.encode('utf-8')):
        # Si la contraseña es correcta, devolvemos los datos del usuario.
        return user_data.to_dict()
    
    # Si la contraseña no coincide, devolvemos None.
    return None