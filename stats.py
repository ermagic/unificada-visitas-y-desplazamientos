# Fichero: stats.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from database import supabase

def mostrar_stats():
    """
    Muestra una página de estadísticas con el número de visitas que el supervisor
    ha realizado a los coordinadores.
    """
    st.header("📊 Estadísticas de Visitas del Supervisor")

    # --- OBTENCIÓN Y FILTRADO DE DATOS ---
    try:
        # La fecha de inicio fija para el acumulativo
        start_date_cumulative = date(2025, 9, 29)

        # Obtenemos todas las visitas del supervisor desde la fecha de inicio
        response = supabase.table('visitas').select(
            '*, usuarios:usuario_id(nombre_completo)' # Hacemos un JOIN para obtener el nombre del coordinador
        ).eq(
            'status', 'Asignada a Supervisor'
        ).gte(
            'fecha_asignada', start_date_cumulative.isoformat()
        ).execute()

        df = pd.DataFrame(response.data)

        if df.empty:
            st.info("No hay datos de visitas asignadas al supervisor para mostrar.")
            return

        # Limpiamos y preparamos los datos
        df['nombre_coordinador'] = df['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'Desconocido')
        df['fecha_asignada'] = pd.to_datetime(df['fecha_asignada']).dt.date
        df.dropna(subset=['nombre_coordinador'], inplace=True)

    except Exception as e:
        st.error(f"Error al cargar los datos de las visitas: {e}")
        return


    # --- 1. GRÁFICO ACUMULATIVO ---
    st.subheader(f"Visitas acumuladas por coordinador (desde {start_date_cumulative.strftime('%d/%m/%Y')})")

    # Contamos las visitas por cada coordinador
    cumulative_counts = df['nombre_coordinador'].value_counts().sort_values(ascending=True)

    if not cumulative_counts.empty:
        st.bar_chart(cumulative_counts)
    else:
        st.info("No hay visitas acumuladas para mostrar en este periodo.")


    # --- 2. GRÁFICO DE LA SEMANA PLANIFICADA (PRÓXIMA SEMANA) ---
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    end_of_next_week = start_of_next_week + timedelta(days=6)

    st.subheader(f"Visitas planificadas por coordinador para la próxima semana ({start_of_next_week.strftime('%d/%m')} - {end_of_next_week.strftime('%d/%m')})")

    # Filtramos el DataFrame para obtener solo las visitas de la próxima semana
    df_next_week = df[
        (df['fecha_asignada'] >= start_of_next_week) &
        (df['fecha_asignada'] <= end_of_next_week)
    ]

    if not df_next_week.empty:
        # Contamos las visitas por coordinador para esa semana
        next_week_counts = df_next_week['nombre_coordinador'].value_counts().sort_values(ascending=True)
        if not next_week_counts.empty:
            st.bar_chart(next_week_counts)
        else:
            st.info("No hay visitas planificadas para la próxima semana.")
    else:
        st.info("No hay visitas planificadas para la próxima semana.")