# Fichero: coordinador_planner.py (con optimización mejorada)
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime, time
from database import supabase
from route_optimizer import RouteOptimizer

# --- CONSTANTES ---
DURACION_VISITA_SEGUNDOS = 45 * 60
LIMITE_VISITAS_A_PLANIFICAR = 50  # Ahora podemos manejar muchas más visitas

# --- FUNCIONES AUXILIARES ---
def get_daily_time_budget(weekday):
    """Devuelve la duración de la jornada en segundos (8h L-J, 7h V)."""
    return 7 * 3600 if weekday == 4 else 8 * 3600

# --- INTERFAZ DE STREAMLIT ---
def mostrar_planificador_coordinador():
    st.header("✨ Planificación Óptima de Visitas (Coordinador)")

    # --- 1. CONFIGURACIÓN ---
    st.subheader("1. Configura tu semana")
    
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    
    # Cargar visitas pendientes del coordinador
    try:
        response = supabase.table('visitas').select('*').eq(
            'usuario_id', st.session_state['usuario_id']
        ).eq(
            'status', 'Propuesta'
        ).gte(
            'fecha', start_of_next_week.isoformat()
        ).lte(
            'fecha', (start_of_next_week + timedelta(days=6)).isoformat()
        ).execute()
        visitas_pendientes_raw = response.data
    except Exception as e:
        st.error(f"No se pudieron cargar las visitas pendientes: {e}")
        st.stop()
    
    if not visitas_pendientes_raw:
        st.info("No tienes visitas propuestas para la próxima semana para planificar.")
        st.stop()

    df_visitas = pd.DataFrame(visitas_pendientes_raw)
    df_visitas['display_name'] = df_visitas['direccion_texto'] + " (" + df_visitas['equipo'] + ")"

    # Selección de visitas
    st.info(f"Selecciona las visitas que quieres incluir en la optimización (máximo {LIMITE_VISITAS_A_PLANIFICAR}).")
    visitas_seleccionadas_display = st.multiselect(
        "Visitas pendientes para la próxima semana:",
        options=df_visitas['display_name'].tolist()
    )

    if len(visitas_seleccionadas_display) > LIMITE_VISITAS_A_PLANIFICAR:
        st.error(f"Has seleccionado {len(visitas_seleccionadas_display)} visitas. Por favor, selecciona un máximo de {LIMITE_VISITAS_A_PLANIFICAR}.")
        st.stop()

    visitas_a_planificar_ids = df_visitas[df_visitas['display_name'].isin(visitas_seleccionadas_display)]['id'].tolist()
    visitas_a_planificar = [v for v in visitas_pendientes_raw if v['id'] in visitas_a_planificar_ids]
    
    punto_inicio = st.text_input("📍 Introduce tu punto de partida para la jornada:", placeholder="Ej: Carrer de la Riera, 7, Cornellà de Llobregat")
    num_dias = st.selectbox("🗓️ ¿En cuántos días quieres planificar?", [1, 2])

    dias_semana_siguiente = [start_of_next_week + timedelta(days=i) for i in range(5)]
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
    
    # --- 2. CÁLCULO CON NUEVO OPTIMIZADOR ---
    if st.button("🚀 Calcular Plan Óptimo", type="primary", use_container_width=True):
        if not punto_inicio:
            st.warning("Por favor, introduce un punto de partida.")
            st.stop()
        if not visitas_a_planificar:
            st.warning("Por favor, selecciona al menos una visita para planificar.")
            st.stop()

        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.text("🔍 Preparando visitas...")
        progress_bar.progress(10)

        st.session_state.plan_propuesto = None

        # Crear optimizador
        optimizer = RouteOptimizer()

        # Añadir punto de inicio como primera "visita" temporal
        visitas_con_inicio = [{'direccion_texto': punto_inicio, 'id': 'inicio'}] + visitas_a_planificar

        status_text.text("🧠 Optimizando rutas con algoritmo mejorado...")
        progress_bar.progress(30)

        if num_dias == 1:
            # Optimizar para un solo día
            visitas_ordenadas, tiempo_total = optimizer.optimize_route(
                visitas_con_inicio,
                DURACION_VISITA_SEGUNDOS
            )

            progress_bar.progress(70)
            status_text.text("📊 Verificando capacidad de jornada...")

            # Quitar el punto de inicio
            visitas_ordenadas = [v for v in visitas_ordenadas if v['id'] != 'inicio']

            # Verificar que cabe en la jornada
            budget = get_daily_time_budget(fechas_seleccionadas[0].weekday())
            if tiempo_total <= budget:
                plan_final = {fechas_seleccionadas[0]: {'ruta': visitas_ordenadas, 'tiempo_total': tiempo_total}}
            else:
                # Recortar visitas hasta que quepa
                visitas_que_caben = []
                tiempo_acumulado = 0
                for v in visitas_ordenadas:
                    tiempo_prueba = tiempo_acumulado + DURACION_VISITA_SEGUNDOS
                    if len(visitas_que_caben) > 0:
                        # Añadir tiempo de viaje (estimado)
                        tiempo_prueba += 1800  # 30 min aprox

                    if tiempo_prueba <= budget:
                        visitas_que_caben.append(v)
                        tiempo_acumulado = tiempo_prueba
                    else:
                        break

                plan_final = {fechas_seleccionadas[0]: {'ruta': visitas_que_caben, 'tiempo_total': tiempo_acumulado}}
                visitas_no_asignadas = [v for v in visitas_ordenadas if v not in visitas_que_caben]

        else:
            # Optimizar para múltiples días
            plan_final, visitas_no_asignadas = optimizer.optimize_multiday(
                visitas_a_planificar,
                fechas_seleccionadas,
                DURACION_VISITA_SEGUNDOS,
                get_daily_time_budget
            )

            progress_bar.progress(70)
            status_text.text("⏰ Finalizando plan...")

        progress_bar.progress(100)
        status_text.text("✅ Planificación completada!")

        st.session_state.plan_propuesto = {
            'plan': plan_final,
            'no_asignadas': visitas_no_asignadas if num_dias > 1 or 'visitas_no_asignadas' in locals() else [],
            'punto_inicio': punto_inicio
        }
        st.rerun()

    # --- 3. RESULTADOS ---
    if 'plan_propuesto' in st.session_state and st.session_state.plan_propuesto:
        st.markdown("---")
        st.subheader("✅ Propuesta de Planificación Óptima")
        st.success("Este es un plan sugerido generado con algoritmo inteligente. **Asigna las fechas y horas manualmente en la pestaña 'Planificador de Visitas'**.")

        plan_data = st.session_state.plan_propuesto
        if not plan_data['plan']:
            st.warning("No se ha podido generar un plan que encaje en los días seleccionados.")
        
        optimizer = RouteOptimizer()
        
        for fecha, datos_ruta in sorted(plan_data['plan'].items()):
            if isinstance(fecha, str):
                fecha = date.fromisoformat(fecha)

            # Manejar ambos formatos (dict con 'ruta' y lista simple)
            ruta_visitas = datos_ruta['ruta'] if isinstance(datos_ruta, dict) else datos_ruta

            with st.expander(f"**🗓️ Plan para el {fecha.strftime('%A, %d/%m/%Y')}** ({len(ruta_visitas)} visitas)", expanded=True):
                hora_actual = datetime.combine(fecha, time(8, 0))

                for idx, visita in enumerate(ruta_visitas):
                    if idx > 0:
                        # Calcular tiempo de viaje desde la visita anterior
                        origen = ruta_visitas[idx-1]['direccion_texto']
                        destino = visita['direccion_texto']
                        _, tiempo_viaje = optimizer.get_distance_duration(origen, destino)
                        if tiempo_viaje:
                            hora_actual += timedelta(seconds=tiempo_viaje)
                    else:
                        # Primera visita: calcular desde punto de inicio
                        _, tiempo_viaje = optimizer.get_distance_duration(plan_data['punto_inicio'], visita['direccion_texto'])
                        if tiempo_viaje:
                            hora_actual += timedelta(seconds=tiempo_viaje)

                    st.markdown(f"- **🕣 {hora_actual.strftime('%H:%M')}** - **{visita['direccion_texto']}** (Equipo: *{visita['equipo']}*)")
                    hora_actual += timedelta(seconds=DURACION_VISITA_SEGUNDOS)

                # Calcular tiempo total (manejar ambos formatos)
                tiempo_total_seg = datos_ruta['tiempo_total'] if isinstance(datos_ruta, dict) and 'tiempo_total' in datos_ruta else len(ruta_visitas) * DURACION_VISITA_SEGUNDOS
                tiempo_total_horas = tiempo_total_seg / 3600
                st.info(f"🕣 Tiempo total estimado de jornada: **{tiempo_total_horas:.2f} horas**.")

        if plan_data.get('no_asignadas'):
            st.markdown("---")
            st.warning("Visitas no incluidas en el plan (por falta de tiempo):")
            for v in plan_data['no_asignadas']:
                st.markdown(f"- {v['direccion_texto']} (Equipo: {v['equipo']})")