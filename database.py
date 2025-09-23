# Fichero: database.py (Versión de diagnóstico final)
import streamlit as st
import pandas as pd
from gspread_pandas import Spread, Client
import json

def get_client() -> Client:
    """Crea y devuelve un cliente de gspread_pandas autenticado."""
    try:
        creds_str = st.secrets["gcp_creds"]["json_credentials"]
        
        # --- LÍNEA DE DIAGNÓSTICO ---
        # Esta línea mostrará el contenido exacto del secret en un cuadro amarillo en la app
        st.warning(f"CONTENIDO SECRETO A DEPURAR:\n\n{creds_str}")
        # ---------------------------

        creds_dict = json.loads(creds_str)
        client = Client(credentials=creds_dict)
        return client
    except Exception as e:
        st.error(f"Error al configurar el cliente de Google: {e}")
        return None

def get_spreadsheet(client: Client) -> Spread:
    """Abre la hoja de cálculo de Google Sheets."""
    try:
        sheet_name = st.secrets["gcp_creds"]["sheet_name"]
        return Spread(sheet_name, client=client)
    except Exception as e:
        st.error(f"Error al abrir el fichero de Google Sheets llamado '{st.secrets['gcp_creds']['sheet_name']}': {e}")
        return None

def get_data(worksheet_name: str) -> pd.DataFrame:
    """Lee todos los datos de una pestaña de Google Sheets."""
    try:
        client = get_client()
        if client:
            spread = get_spreadsheet(client)
            if spread:
                df = spread.sheet_to_df(sheet=worksheet_name, index=False)
                return df
    except Exception as e:
        st.error(f"Error DETALLADO al leer la pestaña '{worksheet_name}': {e}")
    
    return pd.DataFrame()

def update_data(worksheet_name: str, data: pd.DataFrame):
    """Sobrescribe todos los datos de una pestaña con un nuevo DataFrame."""
    try:
        client = get_client()
        if client:
            spread = get_spreadsheet(client)
            if spread:
                spread.df_to_sheet(df=data, sheet=worksheet_name, index=False, replace=True)
                return True
    except Exception as e:
        st.error(f"No se pudo actualizar la hoja de cálculo '{worksheet_name}': {e}")
    
    return False