# Fichero: planificador.py (Versión Supabase)
import streamlit as st
import pandas as pd
from datetime import datetime
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import st_folium
from database import supabase # Importamos el cliente

def mostrar_planificador():
    st.header("Planificador de Visitas 🗓️")
    
    if not supabase:
        st.error("La conexión con la base de datos no está disponible.")
        st.stop()

    # --- LECTURA DE DATOS ---
    # Leemos los perfiles de usuario para poder mostrar los nombres
    users_response = supabase.table('usuarios').select('id, nombre_completo').execute()
    users_df = pd.DataFrame(users_response.data)
    
    # Leemos todas las visitas
    visits_response = supabase.table('visitas').select('*').execute()
    all_visits_df = pd.DataFrame(visits_response.data)

    if not all_visits_df.empty:
        all_visits_df['fecha'] = pd.to_datetime(all_visits_df['fecha'])
        # Unimos las visitas con los nombres de usuario
        all_visits_df = pd.merge(
            all_visits_df, users_df,
            left_on='usuario_id', right_on='id',
            how='left'
        ).drop(columns=['id_y']).rename(columns={'id_x': 'id'})

    # --- FORMULARIO PARA AÑADIR VISITA ---
    with st.expander("➕ Añadir Nueva Visita", expanded=False):
        with st.form("visit_form", clear_on_submit=True):
            direccion = st.text_input("Ciudad de la visita")
            fecha_visita = st.date_input("Fecha", value=datetime.today())
            franja = st.selectbox("Franja Horaria", ["Jornada Mañana (8-14h)", "Jornada Tarde (15-17h)"])
            observaciones = st.text_area("Observaciones (opcional)")

            if st.form_submit_button("Guardar Visita", type="primary"):
                if direccion:
                    geolocator = Nominatim(user_agent=f"planificador_visitas_{st.session_state['usuario_id']}")
                    try:
                        location = geolocator.geocode(f"{direccion}, Spain")
                        if location:
                            new_visit_data = {
                                'usuario_id': st.session_state['usuario_id'],
                                'direccion_texto': direccion,
                                'lat': location.latitude,
                                'lon': location.longitude,
                                'fecha': fecha_visita.strftime("%Y-%m-%d"),
                                'franja_horaria': franja,
                                'observaciones': observaciones
                            }
                            # Insertamos los datos en la tabla de Supabase
                            supabase.table('visitas').insert(new_visit_data).execute()
                            st.success(f"Visita a '{direccion}' guardada.")
                            st.rerun()
                        else:
                            st.error(f"No se pudo encontrar la ciudad '{direccion}'.")
                    except Exception as e:
                        st.error(f"Error de geocodificación: {e}")
                else:
                    st.warning("El campo 'Ciudad de la visita' no puede estar vacío.")

    st.markdown("---")
    
    # El resto de la lógica de visualización (mapas, filtros, etc.) puede
    # seguir funcionando con los DataFrames `all_visits_df` y `users_df`
    # ... (código de las pestañas sin cambios) ...

    # --- LÓGICA DE GESTIÓN DE VISITAS ---
    with st.tabs(["🗓️ Visión Semanal", "📅 Vista Calendario", "✏️ Gestionar Mis Visitas"])[2]:
        st.subheader("Gestionar Mis Próximas Visitas")
        
        my_id = st.session_state['usuario_id']
        my_visits_response = supabase.table('visitas').select('*').eq('usuario_id', my_id).gte('fecha', datetime.today().date().isoformat()).order('fecha').execute()
        my_visits_df = pd.DataFrame(my_visits_response.data)

        if my_visits_df.empty:
            st.info("No tienes ninguna visita futura programada.")
        else:
            for _, visit in my_visits_df.iterrows():
                with st.container(border=True):
                    fecha_formateada = pd.to_datetime(visit['fecha']).strftime('%d/%m/%Y')
                    st.write(f"**{fecha_formateada}** - {visit['direccion_texto']}")
                    if st.button("🗑️ Eliminar", key=f"del_{visit['id']}", type="secondary"):
                        # Lógica de eliminación para Supabase
                        supabase.table('visitas').delete().eq('id', visit['id']).execute()
                        st.success("Visita eliminada.")
                        st.rerun()

# (El código de las otras pestañas como el mapa y el calendario se mantiene,
#  ya que leen de los dataframes que ya hemos preparado)