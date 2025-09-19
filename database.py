# Fichero: database.py (Versión final con gspread)
import streamlit as st
import pandas as pd
from gspread_pandas import Spread, Client

# NOTA: No es necesario cambiar auth.py o admin.py porque mantenemos los mismos nombres de función.

def get_client() -> Client:
    """Crea y devuelve un cliente de gspread_pandas autenticado."""
    # Usa las mismas credenciales JSON que ya tienes en tus secretos.
    creds = st.secrets["gcp_service_account"]
    client = Client(creds)
    return client

def get_spreadsheet(client: Client) -> Spread:
    """Abre la hoja de cálculo de Google Sheets."""
    # El nombre de la hoja de cálculo debe estar en tus secretos.
    sheet_name = st.secrets["gcp_service_account"]["sheet_name"]
    return Spread(sheet_name, client=client)

def get_data(worksheet_name: str) -> pd.DataFrame:
    """Lee todos los datos de una pestaña de Google Sheets."""
    try:
        spread = get_spreadsheet(get_client())
        # Carga la hoja como un DataFrame, interpretando la primera fila como encabezado.
        df = spread.sheet_to_df(sheet=worksheet_name, index=False)
        return df
    except Exception as e:
        # Si la hoja de cálculo no existe o está vacía, puede dar un error.
        st.error(f"Error al leer la hoja '{worksheet_name}': {e}")
        return pd.DataFrame()

def update_data(worksheet_name: str, data: pd.DataFrame):
    """Sobrescribe todos los datos de una pestaña con un nuevo DataFrame."""
    try:
        spread = get_spreadsheet(get_client())
        # Sobrescribe la hoja con el nuevo DataFrame.
        spread.df_to_sheet(df=data, sheet=worksheet_name, index=False, replace=True)
        return True
    except Exception as e:
        st.error(f"No se pudo actualizar la hoja de cálculo: {e}")
        return False