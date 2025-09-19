# Fichero: auth.py
import bcrypt
import pandas as pd
from database import get_data

def verificar_usuario(username, password):
    """Verifica el usuario y la contraseña contra los datos de Google Sheets."""
    
    # 1. Obtenemos TODOS los usuarios de la hoja de cálculo
    users_df = get_data("usuarios")
    
    # Si el DataFrame está vacío o hubo un error, no podemos verificar
    if users_df.empty:
        return None

    # 2. Buscamos al usuario por su 'username'
    # .squeeze() convierte el resultado en una fila (Series) si solo hay una coincidencia
    user_data = users_df[users_df['username'] == username].squeeze()

    # Si no se encuentra al usuario (user_data estará vacío) o si se encuentran múltiples
    if user_data.empty or not isinstance(user_data, pd.Series):
        return None

    # 3. Verificamos la contraseña
    password_hash_from_db = user_data['password_hash']
    
    # Comprobamos si la contraseña introducida coincide con el hash guardado
    if bcrypt.checkpw(password.encode('utf-8'), password_hash_from_db.encode('utf-8')):
        # Si es correcta, devolvemos los datos del usuario como un diccionario
        return user_data.to_dict()
        
    # Si la contraseña es incorrecta, devolvemos None
    return None