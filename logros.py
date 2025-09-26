# Fichero: logros.py (Versión final con Compañero del Mes)
import streamlit as st
import pandas as pd
from database import supabase
from datetime import date
from dateutil.relativedelta import relativedelta

def mostrar_logros():
    st.header("🏆 Logros y Clasificaciones del Equipo")

    try:
        logros_res = supabase.table('logros').select('*, usuarios:usuario_id(nombre_completo)').execute()
        df_logros = pd.DataFrame(logros_res.data)
        if not df_logros.empty:
            df_logros['nombre_coordinador'] = df_logros['usuarios'].apply(lambda x: x.get('nombre_completo') if isinstance(x, dict) else 'Desconocido')
    except Exception as e:
        st.error(f"No se pudieron cargar los logros: {e}")
        return

    # --- 1. COMPAÑERO DEL MES ---
    st.subheader("🥇 Compañero del Mes")
    st.info("Este logro se otorga al coordinador que más visitas reclama del mercado, ayudando a sus compañeros.")
    
    try:
        today = date.today()
        first_day_of_month = today.replace(day=1)
        
        # Cargar ayudas del mes actual
        ayudas_res = supabase.table('ayudas_registradas').select(
            '*, reclamador:reclamador_id(nombre_completo)'
        ).gte(
            'fecha_ayuda', first_day_of_month
        ).execute()
        
        df_ayudas = pd.DataFrame(ayudas_res.data)

        if not df_ayudas.empty:
            df_ayudas['nombre_reclamador'] = df_ayudas['reclamador'].apply(lambda x: x.get('nombre_completo') if isinstance(x, dict) else 'Desconocido')
            
            # Ranking del mes actual
            ranking_mes = df_ayudas['nombre_reclamador'].value_counts().reset_index()
            ranking_mes.columns = ['Coordinador', 'Ayudas Realizadas']
            
            ganador_actual = ranking_mes.iloc[0]

            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    label=f"Líder de {today.strftime('%B')}: {ganador_actual['Coordinador']}",
                    value=f"{ganador_actual['Ayudas Realizadas']} Ayudas"
                )
            with col2:
                st.write("**Ranking del Mes Actual:**")
                st.dataframe(ranking_mes, use_container_width=True, hide_index=True)

        else:
            st.write("Aún no se han registrado ayudas este mes. ¡Anímate a ser el primero!")

    except Exception as e:
        st.error(f"No se pudo cargar el ranking de ayudas: {e}")
    st.markdown("---")

    # --- 2. REY DE LA RUTA ---
    st.subheader("👑 Rey de la Ruta")
    st.info("Este logro se otorga al coordinador con la planificación semanal más eficiente.")
    if not df_logros.empty:
        df_reyes = df_logros[df_logros['logro_tipo'] == 'rey_de_la_ruta'].copy()
        if not df_reyes.empty:
            df_reyes['eficiencia'] = df_reyes['detalles'].apply(lambda x: x.get('eficiencia', 0))
            rey_actual = df_reyes.loc[df_reyes['eficiencia'].idxmax()]
            col1, col2 = st.columns(2)
            with col1:
                st.metric(label=f"Campeón Actual: {rey_actual['nombre_coordinador']}", value=f"{rey_actual['eficiencia']:.2f}% Eficiencia")
            with col2:
                st.metric(label="Fecha del Récord", value=pd.to_datetime(rey_actual['fecha_logro']).strftime('%d/%m/%Y'))
        else:
            st.write("Aún no se ha coronado al primer Rey de la Ruta.")
    else:
        st.write("No hay datos de logros todavía.")

    st.markdown("---")

    # --- 3. EXPLORADOR ---
    st.subheader("🗺️ Explorador")
    st.info("Otorgado por ser el primero en registrar una visita en una nueva población.")
    if not df_logros.empty:
        df_exploradores = df_logros[df_logros['logro_tipo'] == 'explorador'].copy()
        if not df_exploradores.empty:
            df_exploradores['poblacion'] = df_exploradores['detalles'].apply(lambda x: x.get('poblacion', 'N/A'))
            df_exploradores['fecha_descubrimiento'] = pd.to_datetime(df_exploradores['fecha_logro']).dt.strftime('%d/%m/%Y')
            st.write("**Poblaciones Descubiertas:**")
            df_display = df_exploradores[['fecha_descubrimiento', 'poblacion', 'nombre_coordinador']].rename(columns={'fecha_descubrimiento': 'Fecha', 'poblacion': 'Población', 'nombre_coordinador': 'Descubierto por'}).sort_values(by='Fecha', ascending=False).reset_index(drop=True)
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.write("Aún no se han registrado nuevas poblaciones.")
    else:
        st.write("No hay datos de logros todavía.")