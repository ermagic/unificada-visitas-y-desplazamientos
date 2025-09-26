# Fichero: coordinador_planner.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime, time
import googlemaps
import itertools
from database import supabase

# --- CONSTANTES ---
DURACION_VISITA_SEGUNDOS = 45 * 60 # 45 minutos por visita

# --- FUNCIONES AUXILIARES ---
def get_daily_time_budget(weekday):
    """Devuelve la duración de la jornada en segundos (8h L-J, 7h V)."""
    return 7 * 3600 if weekday == 4 else 8 * 3600

def calcular_ruta_optima(punto_inicio, visitas_del_dia, gmaps, time_budget):
    """
    Encuentra la mejor permutación de visitas para un día que maximice el número
    de visitas realizadas sin exceder el presupuesto de tiempo.
    """
    mejor_ruta, mejor_puntuacion = [], (-1, float('inf'))

    # Probamos desde hacer todas las visitas hasta solo una
    for cantidad in range(len(visitas_del_dia), 0, -1):
        for combo in itertools.combinations(visitas_del_dia, cantidad):
            for orden in itertools.permutations(combo):
                # Calcular tiempo total para esta permutación
                tiempo_total = 0
                origen_actual = punto_inicio
                
                # Viaje inicial + primera visita
                tiempo_total += gmaps.distance_matrix(origen_actual, orden[0]['direccion_texto'])['rows'][0]['elements'][0]['duration']['value']
                tiempo_total += DURACION_VISITA_SEGUNDOS
                origen_actual = orden[0]['direccion_texto']
                
                # Viajes intermedios + resto de visitas
                for i in range(len(orden) - 1):
                    destino_siguiente = orden[i+1]['direccion_texto']
                    tiempo_total += gmaps.distance_matrix(origen_actual, destino_siguiente)['rows'][0]['elements'][0]['duration']['value']
                    tiempo_total += DURACION_VISITA_SEGUNDOS
                    origen_actual = destino_siguiente
                
                # Si la ruta es válida y mejor que la anterior, la guardamos
                if tiempo_total <= time_budget:
                    puntuacion_actual = (len(orden), tiempo_total)
                    if puntuacion_actual[0] > mejor_puntuacion[0] or \
                       (puntuacion_actual[0] == mejor_puntuacion[0] and puntuacion_actual[1] < mejor_puntuacion[1]):
                        mejor_puntuacion = puntuacion_actual
                        mejor_ruta = list(orden)
        
        # Si ya encontramos una ruta con la máxima cantidad posible, paramos.
        if mejor_ruta:
            return mejor_ruta, mejor_puntuacion[1]
            
    return [], 0


# --- INTERFAZ DE STREAMLIT ---
def mostrar_planificador_coordinador():
    st.header("✨ Planificación Óptima de Visitas (Coordinador)")

    # --- 1. CONFIGURACIÓN ---
    st.subheader("1. Configura tu semana")
    
    # Próxima semana
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    dias_semana_siguiente = [start_of_next_week + timedelta(days=i) for i in range(5)]

    punto_inicio = st.text_input("📍 Introduce tu punto de partida para la jornada:", placeholder="Ej: Carrer de la Riera, 7, Cornellà de Llobregat")
    num_dias = st.selectbox("🗓️ ¿En cuántos días quieres planificar?", [1, 2])

    fechas_seleccionadas = []
    if num_dias == 1:
        fecha_1 = st.date_input("Elige el día de trabajo", value=dias_semana_siguiente[0], min_value=dias_semana_siguiente[0], max_value=dias_semana_siguiente[4])
        fechas_seleccionadas.append(fecha_1)
    else:
        col1, col2 = st.columns(2)
        with col1:
            fecha_1 = st.date_input("Elige el primer día", value=dias_semana_siguiente[0], min_value=dias_semana_siguiente[0], max_value=dias_semana_siguiente[4])
        with col2:
            fecha_2 = st.date_input("Elige el segundo día", value=dias_semana_siguiente[1], min_value=dias_semana_siguiente[0], max_value=dias_semana_siguiente[4])
        if fecha_1 == fecha_2:
            st.error("Por favor, selecciona dos días diferentes.")
            st.stop()
        fechas_seleccionadas.extend([fecha_1, fecha_2])
    
    # --- 2. CÁLCULO ---
    if st.button("🚀 Calcular Plan Óptimo", type="primary", use_container_width=True):
        if not punto_inicio:
            st.warning("Por favor, introduce un punto de partida."); st.stop()

        with st.spinner("Buscando tus visitas y calculando las mejores rutas..."):
            # Cargar visitas del coordinador para la próxima semana
            response = supabase.table('visitas').select('*').eq(
                'usuario_id', st.session_state['usuario_id']
            ).eq(
                'status', 'Propuesta' # Solo las no asignadas
            ).gte(
                'fecha', start_of_next_week.isoformat()
            ).lte(
                'fecha', (start_of_next_week + timedelta(days=6)).isoformat()
            ).execute()
            
            visitas_pendientes = response.data
            if not visitas_pendientes:
                st.info("No tienes visitas propuestas para la próxima semana para planificar."); st.stop()
            
            st.session_state.plan_propuesto = None
            gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
            plan_final = {}
            visitas_asignadas_ids = set()

            if num_dias == 1:
                time_budget = get_daily_time_budget(fechas_seleccionadas[0].weekday())
                ruta, tiempo = calcular_ruta_optima(punto_inicio, visitas_pendientes, gmaps, time_budget)
                if ruta:
                    plan_final[fechas_seleccionadas[0]] = {'ruta': ruta, 'tiempo_total': tiempo}
                    visitas_asignadas_ids.update([v['id'] for v in ruta])
            
            else: # Lógica para 2 días
                mejor_combinacion = {}
                max_visitas_logradas = -1
                
                # Iteramos sobre todas las formas de dividir las visitas en 2 grupos
                for i in range(1, len(visitas_pendientes) // 2 + 1):
                    for combo_dia1 in itertools.combinations(visitas_pendientes, i):
                        visitas_dia1 = list(combo_dia1)
                        visitas_dia2 = [v for v in visitas_pendientes if v not in visitas_dia1]
                        
                        # Probamos la asignación en ambos sentidos (combo a dia 1 / combo a dia 2)
                        for d1, d2 in [(fechas_seleccionadas[0], fechas_seleccionadas[1]), (fechas_seleccionadas[1], fechas_seleccionadas[0])]:
                            budget1 = get_daily_time_budget(d1.weekday())
                            budget2 = get_daily_time_budget(d2.weekday())

                            ruta1, _ = calcular_ruta_optima(punto_inicio, visitas_dia1, gmaps, budget1)
                            ruta2, _ = calcular_ruta_optima(punto_inicio, visitas_dia2, gmaps, budget2)

                            if len(ruta1) + len(ruta2) > max_visitas_logradas:
                                max_visitas_logradas = len(ruta1) + len(ruta2)
                                mejor_combinacion = {d1: ruta1, d2: ruta2}

                # Guardamos la mejor combinación encontrada
                for fecha, ruta in mejor_combinacion.items():
                    if ruta:
                         # Recalculamos el tiempo solo para la ruta final para mostrarlo
                        _, tiempo_final = calcular_ruta_optima(punto_inicio, ruta, gmaps, get_daily_time_budget(fecha.weekday()))
                        plan_final[fecha] = {'ruta': ruta, 'tiempo_total': tiempo_final}
                        visitas_asignadas_ids.update([v['id'] for v in ruta])
            
            visitas_no_asignadas = [v for v in visitas_pendientes if v['id'] not in visitas_asignadas_ids]
            st.session_state.plan_propuesto = {'plan': plan_final, 'no_asignadas': visitas_no_asignadas, 'punto_inicio': punto_inicio}
            st.rerun()

    # --- 3. RESULTADOS ---
    if 'plan_propuesto' in st.session_state and st.session_state.plan_propuesto:
        st.markdown("---")
        st.subheader("✅ Propuesta de Planificación Óptima")
        st.success("Este es un plan sugerido. Para confirmarlo, **asigna las fechas y horas manualmente en la pestaña 'Gestionar Visitas'**.")

        plan_data = st.session_state.plan_propuesto
        if not plan_data['plan']:
            st.warning("No se ha podido generar un plan que encaje en los días seleccionados con las visitas disponibles.")
        
        for fecha, datos_ruta in sorted(plan_data['plan'].items()):
            with st.expander(f"**🗓️ Plan para el {fecha.strftime('%A, %d/%m/%Y')}** ({len(datos_ruta['ruta'])} visitas)", expanded=True):
                hora_actual = datetime.combine(fecha, time(8, 0))
                origen = plan_data['punto_inicio']
                
                for visita in datos_ruta['ruta']:
                    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
                    tiempo_viaje_seg = gmaps.distance_matrix(origen, visita['direccion_texto'])['rows'][0]['elements'][0]['duration']['value']
                    hora_actual += timedelta(seconds=tiempo_viaje_seg)
                    
                    st.markdown(f"- **🕣 {hora_actual.strftime('%H:%M')}** - **{visita['direccion_texto']}** (Equipo: *{visita['equipo']}*)")
                    
                    hora_actual += timedelta(seconds=DURACION_VISITA_SEGUNDOS)
                    origen = visita['direccion_texto']
                
                tiempo_total_horas = plan_data['plan'][fecha]['tiempo_total'] / 3600
                st.info(f"🕣 Tiempo total estimado de jornada: **{tiempo_total_horas:.2f} horas**.")

        if plan_data['no_asignadas']:
            st.markdown("---")
            st.warning("Visitas no incluidas en el plan (por falta de tiempo):")
            for v in plan_data['no_asignadas']:
                st.markdown(f"- {v['direccion_texto']} (Equipo: {v['equipo']})")
