"""
Planificador de Martín (Supervisor) - REFACTORIZADO
Arquitectura modular con separación de responsabilidades
"""
import streamlit as st
import pandas as pd
from datetime import date, timedelta
import smtplib
from email.mime.text import MIMEText

# Nuevos imports modulares
from balancing_service import BalancingService
from scoring_service import ScoringService
from plan_manager import PlanManager
from ui_components import UIComponents
from route_optimizer import RouteOptimizer
from config import (
    get_daily_time_budget, DURACION_VISITA_SEGUNDOS,
    PUNTO_INICIO_MARTIN, MIN_VISITAS_AUTO_ASIGNAR
)
from database import supabase


# ==================== SERVICIOS SINGLETON ====================

@st.cache_resource
def get_services():
    """Inicializa y cachea todos los servicios"""
    optimizer = RouteOptimizer()
    return {
        'optimizer': optimizer,
        'balancer': BalancingService(optimizer),
        'scorer': ScoringService(optimizer),
        'manager': PlanManager(optimizer),
        'ui': UIComponents()
    }


# ==================== UTILIDADES DE EMAIL ====================

def send_email(recipients, subject, body):
    """Envía email de notificación"""
    try:
        smtp_cfg = st.secrets["smtp"]
        sender, password = smtp_cfg["username"], smtp_cfg["password"]
        msg = MIMEText(body, 'html')
        msg['From'], msg['To'], msg['Subject'] = sender, ", ".join(recipients), subject
        server = smtplib.SMTP(smtp_cfg["server"], smtp_cfg["port"])
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        st.success("✅ Correo de notificación enviado con éxito.")
        return True
    except Exception as e:
        st.error(f"Error al enviar correo: {e}")
        return False


# ==================== CARGA DE DATOS ====================

def load_weekly_visits():
    """Carga visitas de la próxima semana"""
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    end_of_next_week = start_of_next_week + timedelta(days=4)

    response = supabase.table('visitas').select('*, usuarios(nombre_completo)').neq(
        'status', 'Realizada'
    ).gte('fecha', start_of_next_week).lte('fecha', end_of_next_week).execute()

    visitas_df = pd.DataFrame(response.data)

    if visitas_df.empty:
        return None, None

    visitas_df['nombre_coordinador'] = visitas_df['usuarios'].apply(
        lambda x: x.get('nombre_completo') if isinstance(x, dict) else 'N/A'
    )

    todas_visitas = visitas_df.to_dict('records')
    visitas_obligatorias = [v for v in todas_visitas if v.get('ayuda_solicitada')]
    visitas_opcionales = [v for v in todas_visitas if not v.get('ayuda_solicitada') and v.get('status') == 'Propuesta']

    return visitas_obligatorias, visitas_opcionales


# ==================== ALGORITMO AUTOMÁTICO ====================

def generar_planificacion_automatica(dias_seleccionados):
    """
    Genera planificación automática optimizada

    Args:
        dias_seleccionados: Lista de fechas (date objects)

    Returns:
        Tupla (plan_final, visitas_no_planificadas)
    """
    services = get_services()
    optimizer = services['optimizer']

    visitas_obligatorias, visitas_opcionales = load_weekly_visits()

    if not visitas_obligatorias and not visitas_opcionales:
        return None, None

    # Priorizar obligatorias primero
    todas_visitas = visitas_obligatorias + visitas_opcionales

    # Optimizar multidía
    plan_final, visitas_no_planificadas = optimizer.optimize_multiday(
        todas_visitas,
        dias_seleccionados,
        DURACION_VISITA_SEGUNDOS,
        get_daily_time_budget
    )

    # Verificar que todas las obligatorias están incluidas
    ids_planificadas = set()
    for datos_dia in plan_final.values():
        ids_planificadas.update([v['id'] for v in datos_dia['ruta']])

    obligatorias_no_planificadas = [v for v in visitas_obligatorias if v['id'] not in ids_planificadas]
    if obligatorias_no_planificadas:
        st.error("¡Atención! Las siguientes visitas con ayuda solicitada no pudieron ser incluidas:")
        for v in obligatorias_no_planificadas:
            st.error(f"- {v['direccion_texto']} (Coordinador: {v['nombre_coordinador']})")

    return plan_final, visitas_no_planificadas


# ==================== MODO AUTOMÁTICO ====================

def modo_automatico():
    """Modo automático con optimización inteligente"""
    services = get_services()
    manager = services['manager']
    ui = services['ui']

    st.subheader("🤖 Modo Automático")
    st.info("El algoritmo optimizado generará la mejor planificación priorizando visitas con ayuda solicitada.")

    # Configuración de días
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    dias_semana_siguiente = [start_of_next_week + timedelta(days=i) for i in range(5)]
    dias_es = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
               "Thursday": "Jueves", "Friday": "Viernes"}

    num_dias = st.slider("¿Cuántos días quieres planificar?", min_value=1, max_value=5, value=3)

    dias_seleccionados = st.multiselect(
        f"Elige {num_dias} días de la próxima semana:",
        options=dias_semana_siguiente,
        format_func=lambda d: f"{dias_es.get(d.strftime('%A'))}, {d.strftime('%d/%m')}",
        max_selections=num_dias
    )

    if st.button("🤖 Generar Planificación Automática", type="primary", use_container_width=True):
        if len(dias_seleccionados) != num_dias:
            st.warning(f"Por favor, selecciona exactamente {num_dias} días.")
        else:
            # Progress bar
            progress_bar = st.progress(0)
            status_text = st.empty()

            status_text.text("🔍 Cargando visitas disponibles...")
            progress_bar.progress(20)

            dias_seleccionados.sort()

            status_text.text("🧠 Optimizando rutas con algoritmo mejorado...")
            progress_bar.progress(40)

            plan, no_asignadas = generar_planificacion_automatica(dias_seleccionados)

            status_text.text("⏰ Calculando horarios...")
            progress_bar.progress(70)

            if plan:
                manager.set_plan_propuesto(plan)
                plan_con_horas = manager.calculate_plan_with_hours(plan)
                manager.set_plan_con_horas(plan_con_horas)
                st.session_state.visitas_no_asignadas = no_asignadas

                status_text.text("✅ Planificación completada!")
                progress_bar.progress(100)

                st.success("✅ Planificación generada con algoritmo optimizado!")

                # Botones de transición
                col1, col2, col3 = st.columns(3)

                with col1:
                    if st.button("✅ Aceptar plan", use_container_width=True):
                        st.info("👉 Ve a la pestaña 'Revisar Plan' para confirmar")

                with col2:
                    if st.button("✏️ Editar manualmente", key="auto_to_manual", use_container_width=True):
                        # Convertir plan automático a manual editable
                        plan_manual = manager.convert_auto_to_manual(plan)
                        manager.set_plan_manual(plan_manual)
                        manager.clear_plan_propuesto()
                        st.success("✅ Plan cargado en modo manual. Ve a la pestaña 'Manual'.")

                with col3:
                    if st.button("🔄 Regenerar", use_container_width=True):
                        manager.clear_plan_propuesto()
                        st.rerun()

                st.rerun()


# ==================== MODO MANUAL ====================

def modo_manual():
    """Modo manual con asistencia inteligente"""
    services = get_services()
    manager = services['manager']
    balancer = services['balancer']
    scorer = services['scorer']
    optimizer = services['optimizer']
    ui = services['ui']

    st.subheader("✋ Modo Manual")
    st.info("Asigna manualmente las visitas a los días que prefieras.")

    # Inicializar plan manual
    manager.initialize_plan_manual()

    # Cargar datos
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    end_of_next_week = start_of_next_week + timedelta(days=4)

    response = supabase.table('visitas').select('*, usuarios(nombre_completo)').neq(
        'status', 'Realizada'
    ).gte('fecha', start_of_next_week).lte('fecha', end_of_next_week).execute()

    visitas_df = pd.DataFrame(response.data)

    if visitas_df.empty:
        st.warning("No hay visitas disponibles para planificar.")
        return

    visitas_df['nombre_coordinador'] = visitas_df['usuarios'].apply(
        lambda x: x.get('nombre_completo') if isinstance(x, dict) else 'N/A'
    )
    todas_visitas = visitas_df.to_dict('records')

    # Filtrar visitas ya asignadas
    plan_manual = manager.get_plan_manual() or {}
    ids_asignadas = set()
    for dia_iso, datos_dia in plan_manual.items():
        visitas_dia = manager.extract_visits_from_day(datos_dia)
        ids_asignadas.update([v['id'] for v in visitas_dia])

    visitas_disponibles = [v for v in todas_visitas if v['id'] not in ids_asignadas and v.get('status') == 'Propuesta']

    # Tabs
    tab_lista, tab_mapa = st.tabs(["📋 Vista Lista", "🗺️ Vista Mapa"])

    with tab_mapa:
        ui.render_map(plan_manual, visitas_disponibles)
        ui.render_map_legend()

    with tab_lista:
        col1, col2 = st.columns([3, 2])

        with col1:
            st.markdown("##### Visitas Disponibles")

            # Botón para asignar restantes automáticamente
            if visitas_disponibles and len(visitas_disponibles) > MIN_VISITAS_AUTO_ASIGNAR:
                if st.button(f"🤖 Asignar {len(visitas_disponibles)} visitas restantes automáticamente",
                           use_container_width=True):
                    dias_disponibles = [start_of_next_week + timedelta(days=i) for i in range(5)]

                    plan_restantes, no_asignadas = optimizer.optimize_multiday(
                        visitas_disponibles,
                        dias_disponibles,
                        DURACION_VISITA_SEGUNDOS,
                        get_daily_time_budget
                    )

                    # Fusionar con plan existente
                    plan_fusionado = manager.merge_plans(plan_manual, plan_restantes)
                    manager.set_plan_manual(plan_fusionado)

                    st.success(f"✅ {len(visitas_disponibles) - len(no_asignadas)} visitas asignadas automáticamente!")
                    if no_asignadas:
                        st.warning(f"⚠️ {len(no_asignadas)} visitas no pudieron ser asignadas por falta de capacidad")
                    st.rerun()

                st.markdown("---")

            # Lista de visitas disponibles
            if visitas_disponibles:
                for visita in visitas_disponibles:
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])

                        with c1:
                            ayuda = " 🆘" if visita.get('ayuda_solicitada') else ""
                            st.markdown(f"**📍 {visita['direccion_texto']}**{ayuda}")
                            st.caption(f"Equipo: {visita['equipo']} | Coord: {visita['nombre_coordinador']}")

                        with c2:
                            # Selector con scores
                            dias_semana = [start_of_next_week + timedelta(days=i) for i in range(5)]
                            scores_dias = scorer.calculate_scores_for_all_days(visita, dias_semana, plan_manual)
                            dias_ordenados = scorer.sort_days_by_score(visita, dias_semana, plan_manual)

                            def format_dia_con_score(d):
                                if d is None:
                                    return "Elegir día..."
                                score_info = scores_dias[d.isoformat()]
                                return f"{d.strftime('%a %d/%m')} {score_info.estrellas} ({score_info.capacidad_pct:.0f}%)"

                            dia_seleccionado = st.selectbox(
                                "Asignar a:",
                                options=[None] + dias_ordenados,
                                format_func=format_dia_con_score,
                                key=f"asignar_{visita['id']}",
                                help="Días ordenados por idoneidad (capacidad + proximidad)"
                            )

                            if dia_seleccionado:
                                dia_iso = dia_seleccionado.isoformat()

                                # Verificar límite de jornada
                                visitas_del_dia = manager.extract_visits_from_day(plan_manual.get(dia_iso, []))
                                tiempo_actual = manager.calculate_day_time(visitas_del_dia)
                                tiempo_con_nueva = manager.calculate_day_time(visitas_del_dia + [visita])
                                limite_dia = get_daily_time_budget(dia_seleccionado.weekday())

                                if tiempo_con_nueva > limite_dia:
                                    st.error(f"⚠️ Excede jornada ({tiempo_con_nueva/3600:.1f}h)")
                                else:
                                    plan_manual = manager.add_visit_to_day(plan_manual, dia_iso, visita)
                                    manager.set_plan_manual(plan_manual)
                                    st.rerun()
            else:
                st.success("✅ Todas las visitas están asignadas")

        with col2:
            st.markdown("##### Plan Actual")

            if plan_manual:
                for dia_iso in sorted(plan_manual.keys()):
                    dia = date.fromisoformat(dia_iso)
                    visitas = manager.extract_visits_from_day(plan_manual[dia_iso])
                    tiempo_total = manager.calculate_day_time(visitas)
                    limite = get_daily_time_budget(dia.weekday())

                    with st.expander(f"**{dia.strftime('%A %d/%m')}** ({len(visitas)} visitas - {tiempo_total/3600:.1f}h)",
                                   expanded=True):
                        # Botón de optimización
                        if len(visitas) > 2:
                            if st.button(f"✨ Optimizar orden del {dia.strftime('%A')}",
                                       key=f"opt_{dia_iso}", use_container_width=True):
                                plan_manual = manager.optimize_day(plan_manual, dia_iso)
                                manager.set_plan_manual(plan_manual)
                                st.success(f"✅ Orden optimizado!")
                                st.rerun()

                        # Lista de visitas
                        for idx, v in enumerate(visitas):
                            col_v1, col_v2 = st.columns([4, 1])
                            with col_v1:
                                st.markdown(f"{idx+1}. {v['direccion_texto']}")
                            with col_v2:
                                if st.button("❌", key=f"remove_{v['id']}_{dia_iso}"):
                                    plan_manual = manager.remove_visit_from_day(plan_manual, dia_iso, v['id'])
                                    manager.set_plan_manual(plan_manual)
                                    st.rerun()

                        if tiempo_total > limite:
                            st.error(f"⚠️ Excede límite: {tiempo_total/3600:.1f}h / {limite/3600:.1f}h")
            else:
                st.info("El plan está vacío")

    # Asistente de balanceo
    st.markdown("---")

    if plan_manual:
        with st.expander("🧠 **Asistente de Balanceo** - Ver análisis y sugerencias", expanded=False):
            with st.spinner("Analizando plan..."):
                analysis = balancer.analyze_plan(plan_manual)

            ui.render_problems(analysis.problemas)

            if analysis.sugerencias:
                ui.render_suggestions(
                    analysis.sugerencias,
                    on_apply=lambda sug: apply_suggestion_and_refresh(sug, plan_manual, balancer, manager)
                )

            if analysis.plan_esta_balanceado:
                st.success("✅ El plan está bien balanceado. ¡Buen trabajo!")

    # Confirmar
    if st.button("✅ Confirmar Planificación Manual", type="primary", use_container_width=True):
        if plan_manual:
            manager.set_plan_propuesto(plan_manual)
            plan_con_horas = manager.calculate_plan_with_hours(plan_manual)
            manager.set_plan_con_horas(plan_con_horas)
            st.success("✅ Plan manual confirmado. Ve a la pestaña 'Revisar Plan' para asignar.")
        else:
            st.warning("El plan está vacío.")


def apply_suggestion_and_refresh(suggestion, plan, balancer, manager):
    """Aplica una sugerencia y actualiza el estado"""
    plan_actualizado = balancer.apply_suggestion(plan, suggestion)
    manager.set_plan_manual(plan_actualizado)
    st.success("✅ Sugerencia aplicada!")
    st.rerun()


# ==================== MODO HÍBRIDO ====================

def modo_hibrido():
    """Modo híbrido: genera automático + edita manual"""
    services = get_services()
    manager = services['manager']
    optimizer = services['optimizer']

    st.subheader("🔄 Modo Híbrido")
    st.info("Genera una propuesta automática optimizada y edítala antes de confirmar.")

    if 'plan_hibrido' not in st.session_state:
        # Paso 1: Generar propuesta
        today = date.today()
        start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
        dias_semana_siguiente = [start_of_next_week + timedelta(days=i) for i in range(5)]
        dias_es = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
                   "Thursday": "Jueves", "Friday": "Viernes"}

        num_dias = st.slider("¿Cuántos días quieres planificar?", min_value=1, max_value=5, value=3, key="hibrido_dias")

        dias_seleccionados = st.multiselect(
            f"Elige {num_dias} días:",
            options=dias_semana_siguiente,
            format_func=lambda d: f"{dias_es.get(d.strftime('%A'))}, {d.strftime('%d/%m')}",
            max_selections=num_dias,
            key="hibrido_select"
        )

        if st.button("🤖 Generar Propuesta Inicial Optimizada", type="primary", use_container_width=True):
            if len(dias_seleccionados) != num_dias:
                st.warning(f"Por favor, selecciona exactamente {num_dias} días.")
            else:
                with st.spinner("🧠 Generando propuesta optimizada..."):
                    dias_seleccionados.sort()
                    plan, no_asignadas = generar_planificacion_automatica(dias_seleccionados)

                    if plan:
                        st.session_state.plan_hibrido = plan
                        st.success("✅ Propuesta optimizada generada. Ahora puedes editarla.")
                        st.rerun()
    else:
        # Paso 2: Editar propuesta
        st.success("📝 Edita la propuesta a continuación:")

        # Cargar visitas disponibles
        today = date.today()
        start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
        end_of_next_week = start_of_next_week + timedelta(days=4)

        response = supabase.table('visitas').select('*, usuarios(nombre_completo)').neq(
            'status', 'Realizada'
        ).gte('fecha', start_of_next_week).lte('fecha', end_of_next_week).execute()

        visitas_df = pd.DataFrame(response.data)
        visitas_df['nombre_coordinador'] = visitas_df['usuarios'].apply(
            lambda x: x.get('nombre_completo') if isinstance(x, dict) else 'N/A'
        )
        todas_visitas = visitas_df.to_dict('records')

        ids_en_plan = set()
        for datos_dia in st.session_state.plan_hibrido.values():
            visitas = manager.extract_visits_from_day(datos_dia)
            ids_en_plan.update([v['id'] for v in visitas])

        visitas_fuera_plan = [v for v in todas_visitas if v['id'] not in ids_en_plan and v.get('status') == 'Propuesta']

        # Editar días
        for dia_iso in sorted(st.session_state.plan_hibrido.keys()):
            dia = date.fromisoformat(dia_iso)
            with st.expander(f"**{dia.strftime('%A %d/%m')}**", expanded=True):
                visitas_dia = manager.extract_visits_from_day(st.session_state.plan_hibrido[dia_iso])

                # Mostrar visitas con opciones
                for idx, v in enumerate(visitas_dia):
                    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                    with col1:
                        st.markdown(f"{idx+1}. **{v['direccion_texto']}** ({v['equipo']})")
                    with col2:
                        if idx > 0 and st.button("⬆️", key=f"up_{v['id']}_{dia_iso}"):
                            visitas_dia[idx], visitas_dia[idx-1] = visitas_dia[idx-1], visitas_dia[idx]
                            st.session_state.plan_hibrido[dia_iso] = visitas_dia
                            st.rerun()
                    with col3:
                        if idx < len(visitas_dia)-1 and st.button("⬇️", key=f"down_{v['id']}_{dia_iso}"):
                            visitas_dia[idx], visitas_dia[idx+1] = visitas_dia[idx+1], visitas_dia[idx]
                            st.session_state.plan_hibrido[dia_iso] = visitas_dia
                            st.rerun()
                    with col4:
                        if st.button("🗑️", key=f"del_{v['id']}_{dia_iso}"):
                            visitas_dia.remove(v)
                            st.session_state.plan_hibrido[dia_iso] = visitas_dia
                            if not st.session_state.plan_hibrido[dia_iso]:
                                del st.session_state.plan_hibrido[dia_iso]
                            st.rerun()

                # Añadir visita
                if visitas_fuera_plan:
                    nueva_visita = st.selectbox(
                        "➕ Añadir visita a este día:",
                        options=[None] + visitas_fuera_plan,
                        format_func=lambda v: "Seleccionar..." if v is None else f"{v['direccion_texto']} ({v['equipo']})",
                        key=f"add_{dia_iso}"
                    )

                    if nueva_visita:
                        tiempo_actual = manager.calculate_day_time(visitas_dia)
                        tiempo_con_nueva = manager.calculate_day_time(visitas_dia + [nueva_visita])
                        limite = get_daily_time_budget(dia.weekday())

                        if tiempo_con_nueva > limite:
                            st.error(f"⚠️ Excedería la jornada ({tiempo_con_nueva/3600:.1f}h > {limite/3600:.1f}h)")
                        else:
                            visitas_dia.append(nueva_visita)
                            st.session_state.plan_hibrido[dia_iso] = visitas_dia
                            st.rerun()

                # Tiempo total
                tiempo_total = manager.calculate_day_time(visitas_dia)
                limite = get_daily_time_budget(dia.weekday())
                st.caption(f"⏱️ Tiempo total: {tiempo_total/3600:.1f}h / {limite/3600:.1f}h")

        # Botones finales
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("❌ Descartar y empezar de nuevo", use_container_width=True):
                del st.session_state.plan_hibrido
                st.rerun()

        with col2:
            if st.button("✨ Re-optimizar cada día", use_container_width=True):
                plan_optimizado = manager.optimize_all_days(st.session_state.plan_hibrido)
                st.session_state.plan_hibrido = plan_optimizado
                st.success("✅ Todos los días re-optimizados!")
                st.rerun()

        with col3:
            if st.button("✅ Confirmar Plan Editado", type="primary", use_container_width=True):
                manager.set_plan_propuesto(st.session_state.plan_hibrido)
                plan_con_horas = manager.calculate_plan_with_hours(st.session_state.plan_hibrido)
                manager.set_plan_con_horas(plan_con_horas)
                del st.session_state.plan_hibrido
                st.success("✅ Plan híbrido confirmado. Ve a 'Revisar Plan'.")


# ==================== REVISAR PLAN ====================

def revisar_plan():
    """Pestaña para revisar y confirmar el plan final"""
    services = get_services()
    manager = services['manager']
    ui = services['ui']

    st.subheader("📋 Revisar y Confirmar Planificación")

    plan_con_horas = manager.get_plan_con_horas()

    if plan_con_horas:
        dias_es = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
                   "Thursday": "Jueves", "Friday": "Viernes"}

        tab_plan, tab_mapa = st.tabs(["📅 Propuesta Detallada", "🗺️ Vista en Mapa"])

        with tab_plan:
            for day_iso, visitas in plan_con_horas.items():
                day = date.fromisoformat(day_iso)
                nombre_dia_es = dias_es.get(day.strftime('%A'), day.strftime('%A'))
                nombre_dia_completo = day.strftime(f'{nombre_dia_es}, %d de %B').capitalize()

                with st.expander(f"**{nombre_dia_completo}** ({len(visitas)} visitas)", expanded=True):
                    for v in visitas:
                        ayuda_texto = " <span style='color:red;'>(ayuda pedida)</span>" if v.get('ayuda_solicitada') else ""
                        st.markdown(f"- **{v['hora_asignada']}h** - {v['direccion_texto']} | **Equipo**: {v['equipo']} (*Propuesto por: {v.get('nombre_coordinador', 'N/A')}{ayuda_texto}*)", unsafe_allow_html=True)

        with tab_mapa:
            ui.render_map(plan_con_horas)

        st.markdown("---")

        if st.button("✅ Confirmar y Asignar en el Sistema", use_container_width=True, type="primary"):
            with st.spinner("Actualizando base de datos..."):
                for day_iso, visitas in plan_con_horas.items():
                    for v in visitas:
                        update_data = {
                            'status': 'Asignada a Supervisor',
                            'fecha_asignada': day_iso,
                            'hora_asignada': v['hora_asignada']
                        }
                        supabase.table('visitas').update(update_data).eq('id', v['id']).execute()

                st.success("¡Planificación confirmada y asignada!")

                # Limpiar sesión
                manager.clear_all_plans()
                st.rerun()
    else:
        ui.render_empty_state(
            "No hay plan para revisar",
            "Ve a una de las pestañas anteriores para crear un plan.",
            "📋"
        )


# ==================== INTERFAZ PRINCIPAL ====================

def mostrar_planificador_supervisor():
    """Función principal - punto de entrada"""
    st.header("Planificador de Martín (Supervisor) 🤖")

    # Tabs principales
    tab_auto, tab_manual, tab_hibrido, tab_revisar = st.tabs([
        "🤖 Automático",
        "✋ Manual",
        "🔄 Híbrido",
        "📋 Revisar Plan"
    ])

    with tab_auto:
        modo_automatico()

    with tab_manual:
        modo_manual()

    with tab_hibrido:
        modo_hibrido()

    with tab_revisar:
        revisar_plan()
