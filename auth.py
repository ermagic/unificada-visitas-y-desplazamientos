# Fichero: auth.py
import bcrypt
import pandas as pd
from database import get_data

def verificar_usuario(username, password):
    """Verifica el usuario y la contraseña contra los datos de Google Sheets."""
    
    # 1. Obtene# Fichero: auth.py (VERSIÓN DE PRUEBA PARA IGNORAR CONTRASEÑA)
import bcrypt
import pandas as pd
from database import get_data

def verificar_usuario(username, password):
    """Verifica el usuario ignorando la contraseña para una prueba."""
    
    users_df = get_data("usuarios")
    
    if users_df.empty:
        return None

    user_data_row = users_df[users_df['username'] == username]

    if user_data_row.empty:
        return None

    # --- INICIO DE LA MODIFICACIÓN DE PRUEBA ---
    # Si hemos encontrado al usuario, devolvemos sus datos directamente
    # sin comprobar la contraseña.
    user_data = user_data_row.iloc[0]
    return user_data.to_dict()
    # --- FIN DE LA MODIFICACIÓN DE PRUEBA ---

    """
    # --- CÓDIGO ORIGINAL (DESACTIVADO TEMPORALMENTE) ---
    # user_data = user_data_row.iloc[0]
    # password_hash_from_db = user_data['password_hash']
    # 
    # if isinstance(password_hash_from_db, str) and bcrypt.checkpw(password.encode('utf-8'), password_hash_from_db.encode('utf-8')):
    #     return user_data.to_dict()
    # 
    # return None
    """mos TODOS los usuarios de la hoja de cálculo
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