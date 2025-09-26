# Fichero: logros.py
import streamlit as st
import pandas as pd
from database import supabase
from datetime import date, timedelta

def mostrar_logros():
    """
    Muestra la página de logros y clasificaciones del equipo.
    """
    st.header("🏆 Logros y Clasificaciones del Equipo")

    try:
        # Cargar todos los logros y los nombres de los usuarios en una sola consulta
        logros_res = supabase.table('logros').select('*, usuarios:usuario_id(nombre_completo)').execute()
        df_logros = pd.DataFrame(logros_res.data)
        if not df_logros.empty:
            df_logros['nombre_coordinador'] = df_logros['usuarios'].apply(lambda x: x['nombre_completo'] if isinstance(x, dict) else 'Desconocido')
    except Exception as e:
        st.error(f"No se pudieron cargar los logros: {e}")
        return

    # --- 1. REY DE LA RUTA ---
    st.subheader("👑 Rey de la Ruta")
    st.info("Este logro se otorga al coordinador que consiga la planificación semanal más eficiente, minimizando el tiempo de viaje frente al tiempo en visitas.")

    if not df_logros.empty:
        df_reyes = df_logros[df_logros['logro_tipo'] == 'rey_de_la_ruta'].copy()
        if not df_reyes.empty:
            df_reyes['eficiencia'] = df_reyes['detalles'].apply(lambda x: x.get('eficiencia', 0))
            
            # Encontrar el rey de la ruta con la máxima eficiencia de todos los tiempos
            rey_actual = df_reyes.loc[df_reyes['eficiencia'].idxmax()]

            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    label=f"Campeón Actual: {rey_actual['nombre_coordinador']}",
                    value=f"{rey_actual['eficiencia']:.2f}% de Eficiencia",
                    help="Porcentaje del tiempo de jornada dedicado a visitas vs. desplazamientos."
                )
            with col2:
                fecha_logro = pd.to_datetime(rey_actual['fecha_logro']).strftime('%d/%m/%Y')
                st.metric(
                    label="Fecha del Récord",
                    value=fecha_logro
                )
        else:
            st.write("Aún no se ha coronado al primer Rey de la Ruta. ¡Sé el primero en generar un plan óptimo!")
    else:
        st.write("No hay datos de logros todavía.")

    st.markdown("---")

    # --- 2. EXPLORADOR ---
    st.subheader("🗺️ Explorador")
    st.info("Este logro se otorga a los coordinadores que realizan la primera visita registrada en una nueva población, expandiendo el alcance del equipo.")

    if not df_logros.empty:
        df_exploradores = df_logros[df_logros['logro_tipo'] == 'explorador'].copy()
        if not df_exploradores.empty:
            df_exploradores['poblacion'] = df_exploradores['detalles'].apply(lambda x: x.get('poblacion', 'N/A'))
            df_exploradores['fecha_descubrimiento'] = pd.to_datetime(df_exploradores['fecha_logro']).dt.strftime('%d/%m/%Y')
            
            st.write("**Poblaciones Descubiertas:**")
            
            # Mostrar una lista de los descubrimientos
            df_display = df_exploradores[['fecha_descubrimiento', 'poblacion', 'nombre_coordinador']].rename(columns={
                'fecha_descubrimiento': 'Fecha',
                'poblacion': 'Población',
                'nombre_coordinador': 'Descubierto por'
            }).sort_values(by='Fecha', ascending=False).reset_index(drop=True)
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.write("Aún no se han registrado nuevas poblaciones.")
    else:
        st.write("No hay datos de logros todavía.")
