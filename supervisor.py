# Fichero: supervisor.py (Sistema flexible con optimización mejorada)
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime, time
import googlemaps
import smtplib
from email.mime.text import MIMEText
import folium
from folium.features import DivIcon
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from database import supabase
from route_optimizer import RouteOptimizer

# --- CONSTANTES ---
PUNTO_INICIO_MARTIN = "Plaça de Catalunya, Barcelona, España"
DURACION_VISITA_SEGUNDOS = 45 * 60
CATALONIA_CENTER = [41.8795, 1.7887]

# --- FUNCIONES AUXILIARES ---
def send_email(recipients, subject, body):
    try:
        smtp_cfg = st.secrets["smtp"]
        sender, password = smtp_cfg["username"], smtp_cfg["password"]
        msg = MIMEText(body, 'html')
        msg['From'], msg['To'], msg['Subject'] = sender, ", ".join(recipients), subject
        server = smtplib.SMTP(smtp_cfg["server"], smtp_cfg["port"])
        server.starttls(); server.login(sender, password); server.send_message(msg); server.quit()
        st.success("✅ Correo de notificación enviado con éxito.")
        return True
    except Exception as e:
        st.error(f"Error al enviar correo: {e}")
        return False

def get_daily_time_budget(weekday):
    """Devuelve la duración de la jornada en segundos (9h L-J, 7h V)"""
    return 7 * 3600 if weekday == 4 else 9 * 3600

def calcular_tiempo_total_dia(visitas_dia, optimizer):
    """Calcula el tiempo total de un día usando el optimizador"""
    if not visitas_dia:
        return 0
    
    _, tiempo = optimizer.optimize_route(visitas_dia, DURACION_VISITA_SEGUNDOS)
    return tiempo

# --- ALGORITMO AUTOMÁTICO OPTIMIZADO ---
def generar_planificacion_automatica(dias_seleccionados):
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    end_of_next_week = start_of_next_week + timedelta(days=4)

    response = supabase.table('visitas').select('*, usuarios(nombre_completo)').neq('status', 'Realizada').gte('fecha', start_of_next_week).lte('fecha', end_of_next_week).execute()
    visitas_df = pd.DataFrame(response.data)

    if visitas_df.empty:
        return None, None

    visitas_df['nombre_coordinador'] = visitas_df['usuarios'].apply(lambda x: x.get('nombre_completo') if isinstance(x, dict) else 'N/A')
    todas_las_visitas = visitas_df.to_dict('records')

    visitas_obligatorias = [v for v in todas_las_visitas if v.get('ayuda_solicitada')]
    visitas_opcionales = [v for v in todas_las_visitas if not v.get('ayuda_solicitada') and v.get('status') == 'Propuesta']

    # Usar el nuevo optimizador
    optimizer = RouteOptimizer()
    
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
    for visitas_dia in plan_final.values():
        ids_planificadas.update([v['id'] for v in visitas_dia])
    
    obligatorias_no_planificadas = [v for v in visitas_obligatorias if v['id'] not in ids_planificadas]
    if obligatorias_no_planificadas:
        st.error("¡Atención! Las siguientes visitas con ayuda solicitada no pudieron ser incluidas en el plan por falta de tiempo:")
        for v in obligatorias_no_planificadas:
            st.error(f"- {v['direccion_texto']} (Coordinador: {v['nombre_coordinador']})")

    return plan_final, visitas_no_planificadas

# --- CALCULAR HORAS PARA PLAN ---
def calcular_horas_plan(plan):
    """Calcula las horas de llegada para cada visita del plan"""
    optimizer = RouteOptimizer()
    plan_con_horas = {}
    
    for day_iso, visitas in plan.items():
        day = date.fromisoformat(day_iso)
        hora_actual = datetime.combine(day, time(8, 0))
        visitas_con_hora = []
        
        if visitas:
            v_primera = visitas[0].copy()
            v_primera['hora_asignada'] = hora_actual.strftime('%H:%M')
            visitas_con_hora.append(v_primera)
            
            for i in range(len(visitas) - 1):
                hora_actual += timedelta(seconds=DURACION_VISITA_SEGUNDOS)
                origen, destino = visitas[i]['direccion_texto'], visitas[i+1]['direccion_texto']
                
                _, tiempo_viaje = optimizer.get_distance_duration(origen, destino)
                if tiempo_viaje:
                    hora_actual += timedelta(seconds=tiempo_viaje)
                else:
                    hora_actual += timedelta(minutes=30)  # Fallback
                
                v_siguiente = visitas[i+1].copy()
                v_siguiente['hora_asignada'] = hora_actual.strftime('%H:%M')
                visitas_con_hora.append(v_siguiente)
        
        plan_con_horas[day_iso] = visitas_con_hora
    
    return plan_con_horas

# --- RENDERIZAR MAPA ---
def renderizar_mapa_plan(plan_con_horas):
    m = folium.Map(location=CATALONIA_CENTER, zoom_start=8)
    try:
        location = Nominatim(user_agent="supervisor_map_v11").geocode(PUNTO_INICIO_MARTIN)
        if location: 
            folium.Marker([location.latitude, location.longitude], popup="Punto de Salida de Martín", icon=folium.Icon(color='green', icon='home', prefix='fa')).add_to(m)
    except: 
        pass

    dias_es = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes"}
    day_colors = ['blue', 'red', 'purple', 'orange', 'darkgreen', 'cadetblue', 'lightred']
    all_points = []
    
    for i, (day_iso, visitas) in enumerate(plan_con_horas.items()):
        day = date.fromisoformat(day_iso)
        color = day_colors[i % len(day_colors)]
        points_of_day = []
        
        for visit_idx, visit in enumerate(visitas):
            if pd.notna(visit.get('lat')) and pd.notna(visit.get('lon')):
                coords = (visit['lat'], visit['lon'])
                points_of_day.append(coords)
                all_points.append(coords)
                popup_html = f"<b>{dias_es.get(day.strftime('%A'))} - Visita {visit_idx + 1}</b><br><b>Hora:</b> {visit['hora_asignada']}h<br><b>Equipo:</b> {visit['equipo']}<br><b>Dirección:</b> {visit['direccion_texto']}"
                DivIcon_html = f'<div style="font-family: sans-serif; color: {color}; font-size: 18px; font-weight: bold; text-shadow: -1px 0 white, 0 1px white, 1px 0 white, 0 -1px white;">{visit_idx + 1}</div>'
                folium.Marker(coords, popup=folium.Popup(popup_html, max_width=300), icon=DivIcon(icon_size=(150, 36), icon_anchor=(7, 20), html=DivIcon_html)).add_to(m)
        
        if len(points_of_day) > 1:
            folium.PolyLine(points_of_day, color=color, weight=2.5, opacity=0.8).add_to(m)
    
    if all_points:
        df_points = pd.DataFrame(all_points, columns=['lat', 'lon'])
        sw = df_points[['lat', 'lon']].min().values.tolist()
        ne = df_points[['lat', 'lon']].max().values.tolist()
        m.fit_bounds([sw, ne])
    
    return m

# --- MODO AUTOMÁTICO ---
def modo_automatico():
    st.subheader("🤖 Modo Automático")
    st.info("El algoritmo optimizado generará la mejor planificación priorizando visitas con ayuda solicitada.")
    
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    dias_semana_siguiente = [start_of_next_week + timedelta(days=i) for i in range(5)]
    dias_es = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes"}
    
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
            with st.spinner("🧠 Optimizando rutas con algoritmo mejorado..."):
                dias_seleccionados.sort()
                plan, no_asignadas = generar_planificacion_automatica(dias_seleccionados)
                
                if plan:
                    st.session_state.plan_propuesto = plan
                    st.session_state.plan_con_horas = calcular_horas_plan(plan)
                    st.session_state.visitas_no_asignadas = no_asignadas
                    st.success("✅ Planificación generada con algoritmo optimizado!")
                    st.rerun()

# --- MODO MANUAL ---
def modo_manual():
    st.subheader("✋ Modo Manual")
    st.info("Asigna manualmente las visitas a los días que prefieras.")
    
    # Inicializar plan manual si no existe
    if 'plan_manual' not in st.session_state:
        st.session_state.plan_manual = {}
    
    today = date.today()
    start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
    end_of_next_week = start_of_next_week + timedelta(days=4)
    
    # Cargar visitas disponibles
    response = supabase.table('visitas').select('*, usuarios(nombre_completo)').neq('status', 'Realizada').gte('fecha', start_of_next_week).lte('fecha', end_of_next_week).execute()
    visitas_df = pd.DataFrame(response.data)
    
    if visitas_df.empty:
        st.warning("No hay visitas disponibles para planificar.")
        return
    
    visitas_df['nombre_coordinador'] = visitas_df['usuarios'].apply(lambda x: x.get('nombre_completo') if isinstance(x, dict) else 'N/A')
    todas_las_visitas = visitas_df.to_dict('records')
    
    # IDs ya asignadas
    ids_asignadas = set()
    for visitas_dia in st.session_state.plan_manual.values():
        ids_asignadas.update([v['id'] for v in visitas_dia])
    
    visitas_disponibles = [v for v in todas_las_visitas if v['id'] not in ids_asignadas and v.get('status') == 'Propuesta']
    
    col1, col2 = st.columns([3, 2])
    optimizer = RouteOptimizer()
    
    with col1:
        st.markdown("##### Visitas Disponibles")
        if visitas_disponibles:
            for visita in visitas_disponibles:
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        ayuda = " 🆘" if visita.get('ayuda_solicitada') else ""
                        st.markdown(f"**📍 {visita['direccion_texto']}**{ayuda}")
                        st.caption(f"Equipo: {visita['equipo']} | Coord: {visita['nombre_coordinador']}")
                    with c2:
                        # Selector de día
                        dias_semana = [start_of_next_week + timedelta(days=i) for i in range(5)]
                        dia_seleccionado = st.selectbox(
                            "Asignar a:", 
                            options=[None] + dias_semana,
                            format_func=lambda d: "Elegir día" if d is None else d.strftime("%a %d/%m"),
                            key=f"asignar_{visita['id']}"
                        )
                        
                        if dia_seleccionado:
                            dia_iso = dia_seleccionado.isoformat()
                            
                            # Verificar límite de jornada
                            visitas_del_dia = st.session_state.plan_manual.get(dia_iso, [])
                            tiempo_actual = calcular_tiempo_total_dia(visitas_del_dia, optimizer)
                            tiempo_con_nueva = calcular_tiempo_total_dia(visitas_del_dia + [visita], optimizer)
                            limite_dia = get_daily_time_budget(dia_seleccionado.weekday())
                            
                            if tiempo_con_nueva > limite_dia:
                                st.error(f"⚠️ Excede jornada ({tiempo_con_nueva/3600:.1f}h)")
                            else:
                                if dia_iso not in st.session_state.plan_manual:
                                    st.session_state.plan_manual[dia_iso] = []
                                st.session_state.plan_manual[dia_iso].append(visita)
                                st.rerun()
        else:
            st.success("✅ Todas las visitas están asignadas")
    
    with col2:
        st.markdown("##### Plan Actual")
        if st.session_state.plan_manual:
            for dia_iso in sorted(st.session_state.plan_manual.keys()):
                dia = date.fromisoformat(dia_iso)
                visitas = st.session_state.plan_manual[dia_iso]
                tiempo_total = calcular_tiempo_total_dia(visitas, optimizer)
                limite = get_daily_time_budget(dia.weekday())
                
                with st.expander(f"**{dia.strftime('%A %d/%m')}** ({len(visitas)} visitas - {tiempo_total/3600:.1f}h)", expanded=True):
                    for idx, v in enumerate(visitas):
                        col_v1, col_v2 = st.columns([4, 1])
                        with col_v1:
                            st.markdown(f"{idx+1}. {v['direccion_texto']}")
                        with col_v2:
                            if st.button("❌", key=f"remove_{v['id']}_{dia_iso}"):
                                st.session_state.plan_manual[dia_iso].remove(v)
                                if not st.session_state.plan_manual[dia_iso]:
                                    del st.session_state.plan_manual[dia_iso]
                                st.rerun()
                    
                    if tiempo_total > limite:
                        st.error(f"⚠️ Excede límite: {tiempo_total/3600:.1f}h / {limite/3600:.1f}h")
        else:
            st.info("El plan está vacío")
    
    st.markdown("---")
    
    if st.button("✅ Confirmar Planificación Manual", type="primary", use_container_width=True):
        if st.session_state.plan_manual:
            st.session_state.plan_propuesto = st.session_state.plan_manual
            st.session_state.plan_con_horas = calcular_horas_plan(st.session_state.plan_manual)
            st.success("✅ Plan manual confirmado. Ve a la pestaña 'Revisar Plan' para asignar.")
        else:
            st.warning("El plan está vacío.")

# --- MODO HÍBRIDO ---
def modo_hibrido():
    st.subheader("🔄 Modo Híbrido")
    st.info("Genera una propuesta automática optimizada y edítala antes de confirmar.")
    
    if 'plan_hibrido' not in st.session_state:
        # Paso 1: Generar propuesta automática
        today = date.today()
        start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
        dias_semana_siguiente = [start_of_next_week + timedelta(days=i) for i in range(5)]
        dias_es = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes"}
        
        num_dias = st.slider("¿Cuántos días quieres planificar?", min_value=1, max_value=5, value=3, key="hibrido_dias")
        
        dias_seleccionados = st.multiselect(
            f"Elige {num_dias} días de la próxima semana:",
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
        
        # Cargar todas las visitas disponibles para poder añadir
        today = date.today()
        start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
        end_of_next_week = start_of_next_week + timedelta(days=4)
        
        response = supabase.table('visitas').select('*, usuarios(nombre_completo)').neq('status', 'Realizada').gte('fecha', start_of_next_week).lte('fecha', end_of_next_week).execute()
        visitas_df = pd.DataFrame(response.data)
        visitas_df['nombre_coordinador'] = visitas_df['usuarios'].apply(lambda x: x.get('nombre_completo') if isinstance(x, dict) else 'N/A')
        todas_visitas = visitas_df.to_dict('records')
        
        ids_en_plan = set()
        for visitas in st.session_state.plan_hibrido.values():
            ids_en_plan.update([v['id'] for v in visitas])
        
        visitas_fuera_plan = [v for v in todas_visitas if v['id'] not in ids_en_plan and v.get('status') == 'Propuesta']
        
        optimizer = RouteOptimizer()
        
        for dia_iso in sorted(st.session_state.plan_hibrido.keys()):
            dia = date.fromisoformat(dia_iso)
            with st.expander(f"**{dia.strftime('%A %d/%m')}**", expanded=True):
                visitas_dia = st.session_state.plan_hibrido[dia_iso]
                
                # Mostrar visitas con opciones de eliminar y reordenar
                for idx, v in enumerate(visitas_dia):
                    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                    with col1:
                        st.markdown(f"{idx+1}. **{v['direccion_texto']}** ({v['equipo']})")
                    with col2:
                        if idx > 0 and st.button("⬆️", key=f"up_{v['id']}_{dia_iso}"):
                            visitas_dia[idx], visitas_dia[idx-1] = visitas_dia[idx-1], visitas_dia[idx]
                            st.rerun()
                    with col3:
                        if idx < len(visitas_dia)-1 and st.button("⬇️", key=f"down_{v['id']}_{dia_iso}"):
                            visitas_dia[idx], visitas_dia[idx+1] = visitas_dia[idx+1], visitas_dia[idx]
                            st.rerun()
                    with col4:
                        if st.button("🗑️", key=f"del_{v['id']}_{dia_iso}"):
                            st.session_state.plan_hibrido[dia_iso].remove(v)
                            if not st.session_state.plan_hibrido[dia_iso]:
                                del st.session_state.plan_hibrido[dia_iso]
                            st.rerun()
                
                # Opción de añadir visita
                if visitas_fuera_plan:
                    nueva_visita = st.selectbox(
                        "➕ Añadir visita a este día:",
                        options=[None] + visitas_fuera_plan,
                        format_func=lambda v: "Seleccionar..." if v is None else f"{v['direccion_texto']} ({v['equipo']})",
                        key=f"add_{dia_iso}"
                    )
                    
                    if nueva_visita:
                        tiempo_actual = calcular_tiempo_total_dia(visitas_dia, optimizer)
                        tiempo_con_nueva = calcular_tiempo_total_dia(visitas_dia + [nueva_visita], optimizer)
                        limite = get_daily_time_budget(dia.weekday())
                        
                        if tiempo_con_nueva > limite:
                            st.error(f"⚠️ Añadir esta visita excedería la jornada ({tiempo_con_nueva/3600:.1f}h > {limite/3600:.1f}h)")
                        else:
                            st.session_state.plan_hibrido[dia_iso].append(nueva_visita)
                            st.rerun()
                
                # Mostrar tiempo total
                tiempo_total = calcular_tiempo_total_dia(visitas_dia, optimizer)
                limite = get_daily_time_budget(dia.weekday())
                st.caption(f"⏱️ Tiempo total: {tiempo_total/3600:.1f}h / {limite/3600:.1f}h")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("❌ Descartar y empezar de nuevo", use_container_width=True):
                del st.session_state.plan_hibrido
                st.rerun()
        with col2:
            if st.button("✅ Confirmar Plan Editado", type="primary", use_container_width=True):
                st.session_state.plan_propuesto = st.session_state.plan_hibrido
                st.session_state.plan_con_horas = calcular_horas_plan(st.session_state.plan_hibrido)
                del st.session_state.plan_hibrido
                st.success("✅ Plan híbrido confirmado. Ve a 'Revisar Plan'.")

# --- INTERFAZ PRINCIPAL ---
def mostrar_planificador_supervisor():
    st.header("Planificador de Martín (Supervisor) 🤖")
    
    # Tabs para los diferentes modos
    tab_auto, tab_manual, tab_hibrido, tab_revisar = st.tabs(["🤖 Automático", "✋ Manual", "🔄 Híbrido", "📋 Revisar Plan"])
    
    with tab_auto:
        modo_automatico()
    
    with tab_manual:
        modo_manual()
    
    with tab_hibrido:
        modo_hibrido()
    
    with tab_revisar:
        st.subheader("📋 Revisar y Confirmar Planificación")
        
        if 'plan_con_horas' in st.session_state and st.session_state.plan_con_horas:
            dias_es = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes"}
            
            tab_plan, tab_mapa = st.tabs(["📅 Propuesta Detallada", "🗺️ Vista en Mapa"])
            
            with tab_plan:
                for day_iso, visitas in st.session_state.plan_con_horas.items():
                    day = date.fromisoformat(day_iso)
                    nombre_dia_es = dias_es.get(day.strftime('%A'), day.strftime('%A'))
                    nombre_dia_completo = day.strftime(f'{nombre_dia_es}, %d de %B').capitalize()
                    
                    with st.expander(f"**{nombre_dia_completo}** ({len(visitas)} visitas)", expanded=True):
                        for v in visitas:
                            ayuda_texto = " <span style='color:red;'>(ayuda pedida)</span>" if v.get('ayuda_solicitada') else ""
                            st.markdown(f"- **{v['hora_asignada']}h** - {v['direccion_texto']} | **Equipo**: {v['equipo']} (*Propuesto por: {v['nombre_coordinador']}{ayuda_texto}*)", unsafe_allow_html=True)
            
            with tab_mapa:
                m = renderizar_mapa_plan(st.session_state.plan_con_horas)
                st_folium(m, use_container_width=True, height=500)
            
            st.markdown("---")
            
            if st.button("✅ Confirmar y Asignar en el Sistema", use_container_width=True, type="primary"):
                with st.spinner("Actualizando base de datos..."):
                    for day_iso, visitas in st.session_state.plan_con_horas.items():
                        for v in visitas:
                            update_data = {
                                'status': 'Asignada a Supervisor',
                                'fecha_asignada': day_iso,
                                'hora_asignada': v['hora_asignada']
                            }
                            supabase.table('visitas').update(update_data).eq('id', v['id']).execute()
                    
                    st.success("¡Planificación confirmada y asignada!")
                    
                    # Limpiar sesión
                    for key in ['plan_propuesto', 'plan_con_horas', 'plan_manual', 'plan_hibrido', 'visitas_no_asignadas']:
                        if key in st.session_state:
                            del st.session_state[key]
                    
                    st.rerun()
        else:
            st.info("No hay ningún plan generado. Ve a una de las pestañas anteriores para crear un plan.")