# Fichero: database.py
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# Creamos la conexión usando los secretos que ya configuraste
# Esto asume que en tu secrets.toml tienes [connections.gcs]
conn = st.connection("gcs", type=GSheetsConnection)

def get_data(worksheet_name: str) -> pd.DataFrame:
    """Función genérica para leer datos de cualquier pestaña."""
    try:
        data = conn.read(worksheet=worksheet_name, usecols=lambda x: x not in [None, ''])
        # Asegurarnos que las columnas vacías no se lean como 'Unnamed'
        data = data.loc[:, ~data.columns.str.contains('^Unnamed')]
        return data
    except Exception as e:
        st.error(f"No se pudo leer la hoja de cálculo '{worksheet_name}': {e}")
        return pd.DataFrame()

def update_data(worksheet_name: str, data: pd.DataFrame):
    """Función para sobreescribir todos los datos en una pestaña."""
    try:
        conn.update(worksheet=worksheet_name, data=data)
        st.success("Datos actualizados correctamente.")
    except Exception as e:
        st.error(f"No se pudo actualizar la hoja de cálculo: {e}")

def add_row(worksheet_name: str, new_row_df: pd.DataFrame):
    """Función para añadir una nueva fila a una pestaña."""
    try:
        # Leemos los datos existentes para no borrarlos
        existing_data = get_data(worksheet_name)
        updated_df = pd.concat([existing_data, new_row_df], ignore_index=True)
        conn.update(worksheet=worksheet_name, data=updated_df)
    except Exception as e:
        st.error(f"No se pudo añadir la fila: {e}")