# Fichero: mercado.py
import streamlit as st
import pandas as pd
from database import supabase
from datetime import date, timedelta

def mostrar_mercado():
    """
    Muestra la página del Mercado de Visitas, donde los coordinadores
    pueden intercambiar visitas.
    """
    st.header("🔄 Mercado de Visitas")
    st.info("Aquí puedes ver las visitas que tus compañeros han ofrecido. Si una te encaja en la ruta, ¡reclámala!")

    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    end_of_next_week = start_of_next_week + timedelta(days=6)

    try:
        # Cargar las visitas que están en el mercado para la próxima semana
        response = supabase.table('visitas').select(
            '*, ofertante:usuario_id(nombre_completo, id)'
        ).eq(
            'en_mercado', True
        ).gte(
            'fecha', start_of_next_week.isoformat()
        ).lte(
            'fecha', end_of_next_week.isoformat()
        ).execute()

        visitas_en_mercado = response.data
    except Exception as e:
        st.error(f"No se pudo cargar el mercado de visitas: {e}")
        return

    if not visitas_en_mercado:
        st.success("¡Buen trabajo en equipo! No hay visitas pendientes en el mercado.")
        return

    st.markdown("---")
    st.subheader("Visitas Disponibles para Intercambio")

    for visita in visitas_en_mercado:
        # No mostrar las visitas ofrecidas por uno mismo
        if visita['usuario_id'] == st.session_state['usuario_id']:
            continue

        ofertante_info = visita.get('ofertante', {})
        ofertante_nombre = ofertante_info.get('nombre_completo', 'Desconocido')
        ofertante_id = ofertante_info.get('id')

        with st.container(border=True):
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                st.markdown(f"**📍 {visita['direccion_texto']}**")
                st.write(f"**🗓️ {visita['fecha']}** | 🕒 {visita['franja_horaria']}")
            with col2:
                st.write(f"**Equipo:** {visita['equipo']}")
                st.caption(f"Ofrecida por: {ofertante_nombre}")
            with col3:
                if st.button("🙋‍♂️ Reclamar Visita", key=f"reclamar_{visita['id']}", use_container_width=True):
                    if not ofertante_id:
                        st.error("No se pudo identificar al ofertante. No se puede reclamar.")
                        continue
                    try:
                        # 1. Reasignar la visita
                        update_data = {'usuario_id': st.session_state['usuario_id'], 'en_mercado': False}
                        supabase.table('visitas').update(update_data).eq('id', visita['id']).execute()
                        
                        # 2. Registrar la ayuda en la nueva tabla
                        ayuda_data = {
                            'reclamador_id': st.session_state['usuario_id'],
                            'ofertante_id': ofertante_id,
                            'visita_id': visita['id'],
                            'fecha_ayuda': str(date.today())
                        }
                        supabase.table('ayudas_registradas').insert(ayuda_data).execute()

                        st.balloons()
                        st.success(f"¡Has reclamado la visita a {visita['direccion_texto']}! Gracias por ayudar.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo reclamar la visita: {e}")