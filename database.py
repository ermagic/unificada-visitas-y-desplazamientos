# Fichero: database.py (Versión final y robusta)
import streamlit as st
import pandas as pd
from gspread_pandas import Spread, Client
import json

def get_client() -> Client:
    """Crea y devuelve un cliente de gspread_pandas autenticado."""
    # Lee las credenciales como una única cadena de texto desde los secretos
    creds_str = st.secrets["gcp_creds"]["json_credentials"]
    # Convierte la cadena de texto a un diccionario que gspread puede entender
    creds_dict = json.loads(creds_str)
    # Autentica y devuelve el cliente
    client = Client(credentials=creds_dict)
    return client

def get_spreadsheet(client: Client) -> Spread:
    """Abre la hoja de cálculo de Google Sheets."""
    sheet_name = st.secrets["gcp_creds"]["sheet_name"]
    return Spread(sheet_name, client=client)

def get_data(worksheet_name: str) -> pd.DataFrame:
    """Lee todos los datos de una pestaña de Google Sheets."""
    try:
        spread = get_spreadsheet(get_client())
        df = spread.sheet_to_df(sheet=worksheet_name, index=False)
        return df
    except Exception as e:
        return pd.DataFrame()

def update_data(worksheet_name: str, data: pd.DataFrame):
    """Sobrescribe todos los datos de una pestaña con un nuevo DataFrame."""
    try:
        spread = get_spreadsheet(get_client())
        spread.df_to_sheet(df=data, sheet=worksheet_name, index=False, replace=True)
        return True
    except Exception as e:
        st.error(f"No se pudo actualizar la hoja de cálculo: {e}")
        return False