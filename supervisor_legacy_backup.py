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

def analizar_plan_y_sugerir(plan_manual, optimizer):
    """Analiza el plan manual y genera sugerencias de mejora"""
    problemas = []
    sugerencias = []

    if not plan_manual:
        return problemas, sugerencias

    # Analizar cada día
    dias_info = {}
    for dia_iso in sorted(plan_manual.keys()):
        dia = date.fromisoformat(dia_iso)
        datos_dia = plan_manual[dia_iso]
        visitas = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia

        tiempo_total = calcular_tiempo_total_dia(visitas, optimizer)
        limite = get_daily_time_budget(dia.weekday())
        capacidad_usada = (tiempo_total / limite) * 100 if limite > 0 else 0

        dias_info[dia_iso] = {
            'dia': dia,
            'visitas': visitas,
            'tiempo_total': tiempo_total,
            'limite': limite,
            'capacidad_usada': capacidad_usada,
            'num_visitas': len(visitas)
        }

    # Detectar problemas
    for dia_iso, info in dias_info.items():
        if info['capacidad_usada'] > 100:
            exceso_mins = (info['tiempo_total'] - info['limite']) / 60
            problemas.append({
                'tipo': 'sobrecarga',
                'dia': info['dia'].strftime('%A %d/%m'),
                'mensaje': f"Sobrecargado ({info['capacidad_usada']:.0f}% - excede {exceso_mins:.0f} min)"
            })
        elif info['capacidad_usada'] < 50 and info['num_visitas'] > 0:
            problemas.append({
                'tipo': 'subcapacidad',
                'dia': info['dia'].strftime('%A %d/%m'),
                'mensaje': f"Baja ocupación ({info['capacidad_usada']:.0f}% - solo {info['num_visitas']} visitas)"
            })

    # Generar sugerencias
    dias_list = list(dias_info.items())

    # Sugerencia: Mover visitas de día sobrecargado a día con capacidad
    for i, (dia_iso_origen, info_origen) in enumerate(dias_list):
        if info_origen['capacidad_usada'] > 100:
            for j, (dia_iso_destino, info_destino) in enumerate(dias_list):
                if i != j and info_destino['capacidad_usada'] < 90:
                    # Buscar visita movible
                    for visita in info_origen['visitas']:
                        tiempo_sin_visita = calcular_tiempo_total_dia(
                            [v for v in info_origen['visitas'] if v['id'] != visita['id']],
                            optimizer
                        )
                        tiempo_con_visita = calcular_tiempo_total_dia(
                            info_destino['visitas'] + [visita],
                            optimizer
                        )

                        if tiempo_sin_visita <= info_origen['limite'] and tiempo_con_visita <= info_destino['limite']:
                            sugerencias.append({
                                'tipo': 'mover',
                                'mensaje': f"Mover '{visita['direccion_texto'][:40]}...' de {info_origen['dia'].strftime('%A')} a {info_destino['dia'].strftime('%A')}",
                                'origen': dia_iso_origen,
                                'destino': dia_iso_destino,
                                'visita_id': visita['id'],
                                'beneficio': f"Balancea carga (-{(info_origen['tiempo_total']-tiempo_sin_visita)/60:.0f}min origen, +{(tiempo_con_visita-info_destino['tiempo_total'])/60:.0f}min destino)"
                            })
                            break

    # Sugerencia: Optimizar días que no están optimizados
    for dia_iso, info in dias_info.items():
        if info['num_visitas'] > 3:
            # Simular optimización
            visitas_originales = info['visitas']
            visitas_optimizadas, tiempo_opt = optimizer.optimize_route(visitas_originales, DURACION_VISITA_SEGUNDOS)

            # Ver si el orden es diferente
            orden_diferente = [v['id'] for v in visitas_originales] != [v['id'] for v in visitas_optimizadas]

            if orden_diferente and abs(tiempo_opt - info['tiempo_total']) > 300:  # Diferencia > 5 min
                ahorro = (info['tiempo_total'] - tiempo_opt) / 60
                if ahorro > 0:
                    sugerencias.append({
                        'tipo': 'optimizar',
                        'mensaje': f"Reordenar visitas del {info['dia'].strftime('%A')} por proximidad",
                        'dia': dia_iso,
                        'beneficio': f"Ahorras ~{ahorro:.0f} minutos"
                    })

    return problemas, sugerencias[:3]  # Limitar a 3 sugerencias

def calcular_score_idoneidad(visita, dia_iso, plan_manual, optimizer):
    """Calcula qué tan idónea es una visita para un día específico"""
    dia = date.fromisoformat(dia_iso)
    datos_dia = plan_manual.get(dia_iso, [])
    visitas_dia = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia

    # Factor 1: Capacidad disponible (0-1)
    limite = get_daily_time_budget(dia.weekday())
    tiempo_actual = calcular_tiempo_total_dia(visitas_dia, optimizer) if visitas_dia else 0
    capacidad_disponible = max(0, (limite - tiempo_actual) / limite)

    # Factor 2: Proximidad geográfica (0-1)
    if visitas_dia:
        # Calcular distancia promedio a las visitas del día
        distancias = []
        for v_existente in visitas_dia:
            dist, _ = optimizer.get_distance_duration(
                visita['direccion_texto'],
                v_existente['direccion_texto']
            )
            if dist:
                distancias.append(dist)

        if distancias:
            dist_promedio = sum(distancias) / len(distancias)
            # Normalizar: 0-20km = 1.0, >50km = 0
            proximidad = max(0, 1 - (dist_promedio / 50000))
        else:
            proximidad = 0.5
    else:
        proximidad = 0.7  # Bonus por ser el primero del día

    # Score combinado
    score = (capacidad_disponible * 0.6) + (proximidad * 0.4)

    # Metadata
    estrellas = "⭐" * int(score * 5 + 0.5)
    capacidad_pct = (tiempo_actual / limite * 100) if limite > 0 else 0

    return {
        'score': score,
        'estrellas': estrellas,
        'capacidad_pct': capacidad_pct,
        'proximidad': proximidad
    }

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
    for datos_dia in plan_final.values():
        ids_planificadas.update([v['id'] for v in datos_dia['ruta']])

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

    for day_iso, datos_dia in plan.items():
        day = date.fromisoformat(day_iso)
        hora_actual = datetime.combine(day, time(8, 0))
        visitas_con_hora = []

        # Extraer las visitas del nuevo formato
        visitas = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia

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
                st.session_state.plan_propuesto = plan
                st.session_state.plan_con_horas = calcular_horas_plan(plan)
                st.session_state.visitas_no_asignadas = no_asignadas

                status_text.text("✅ Planificación completada!")
                progress_bar.progress(100)

                st.success("✅ Planificación generada con algoritmo optimizado!")

                # Opciones de siguiente paso
                col_next1, col_next2, col_next3 = st.columns(3)
                with col_next1:
                    if st.button("✅ Aceptar plan", use_container_width=True):
                        # El plan ya está en session_state, solo hace falta ir a revisar
                        st.info("👉 Ve a la pestaña 'Revisar Plan' para confirmar")
                with col_next2:
                    if st.button("✏️ Editar manualmente", key="auto_to_manual", use_container_width=True):
                        # Convertir plan automático a manual editable
                        st.session_state.plan_manual = {}
                        for dia_iso, datos in plan.items():
                            visitas = datos['ruta'] if isinstance(datos, dict) else datos
                            st.session_state.plan_manual[dia_iso] = visitas
                        # Limpiar plan propuesto
                        del st.session_state.plan_propuesto
                        del st.session_state.plan_con_horas
                        st.success("✅ Plan cargado en modo manual. Ve a la pestaña 'Manual' para editarlo.")
                with col_next3:
                    if st.button("🔄 Regenerar", use_container_width=True):
                        st.session_state.plan_propuesto = None
                        st.session_state.plan_con_horas = None
                        st.rerun()

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
    for datos_dia in st.session_state.plan_manual.values():
        visitas_dia = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia
        ids_asignadas.update([v['id'] for v in visitas_dia])
    
    visitas_disponibles = [v for v in todas_las_visitas if v['id'] not in ids_asignadas and v.get('status') == 'Propuesta']

    optimizer = RouteOptimizer()

    # Tabs para vista lista vs vista mapa
    tab_lista, tab_mapa = st.tabs(["📋 Vista Lista", "🗺️ Vista Mapa"])

    with tab_mapa:
        # Crear mapa interactivo
        m = folium.Map(location=CATALONIA_CENTER, zoom_start=8)

        # Colores por día
        day_colors = {
            0: 'blue',    # Lunes
            1: 'red',     # Martes
            2: 'purple',  # Miércoles
            3: 'orange',  # Jueves
            4: 'green'    # Viernes
        }

        # Añadir visitas ya asignadas con color por día
        for dia_iso in sorted(st.session_state.plan_manual.keys()):
            dia = date.fromisoformat(dia_iso)
            datos_dia = st.session_state.plan_manual[dia_iso]
            visitas = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia

            color = day_colors.get(dia.weekday(), 'gray')
            dia_nombre = dia.strftime('%A %d/%m')

            for idx, v in enumerate(visitas):
                if pd.notna(v.get('lat')) and pd.notna(v.get('lon')):
                    popup_html = f"<b>{dia_nombre}</b><br>Orden: {idx+1}<br><b>{v['direccion_texto']}</b><br>Equipo: {v['equipo']}"
                    folium.CircleMarker(
                        location=[v['lat'], v['lon']],
                        radius=8,
                        popup=folium.Popup(popup_html, max_width=250),
                        color=color,
                        fill=True,
                        fillColor=color,
                        fillOpacity=0.7
                    ).add_to(m)

        # Añadir visitas sin asignar en gris
        for v in visitas_disponibles:
            if pd.notna(v.get('lat')) and pd.notna(v.get('lon')):
                popup_html = f"<b>SIN ASIGNAR</b><br><b>{v['direccion_texto']}</b><br>Equipo: {v['equipo']}<br>Coord: {v['nombre_coordinador']}"
                folium.CircleMarker(
                    location=[v['lat'], v['lon']],
                    radius=6,
                    popup=folium.Popup(popup_html, max_width=250),
                    color='gray',
                    fill=True,
                    fillColor='lightgray',
                    fillOpacity=0.5
                ).add_to(m)

        # Leyenda
        st.markdown("""
        **Leyenda:**
        🔵 Lunes | 🔴 Martes | 🟣 Miércoles | 🟠 Jueves | 🟢 Viernes | ⚪ Sin asignar
        """)

        st_folium(m, use_container_width=True, height=500)

    with tab_lista:
        col1, col2 = st.columns([3, 2])
    
    with col1:
        st.markdown("##### Visitas Disponibles")

        # Botón para asignar restantes automáticamente
        if visitas_disponibles and len(visitas_disponibles) > 3:
            if st.button(f"🤖 Asignar {len(visitas_disponibles)} visitas restantes automáticamente", use_container_width=True):
                today = date.today()
                start_of_next_week = today + timedelta(days=-today.weekday(), weeks=1)
                dias_disponibles = [start_of_next_week + timedelta(days=i) for i in range(5)]

                # Optimizar visitas restantes en días disponibles
                plan_restantes, no_asignadas = optimizer.optimize_multiday(
                    visitas_disponibles,
                    dias_disponibles,
                    DURACION_VISITA_SEGUNDOS,
                    get_daily_time_budget
                )

                # Fusionar con plan manual existente
                for dia_iso, datos in plan_restantes.items():
                    visitas_nuevas = datos['ruta'] if isinstance(datos, dict) else datos

                    if dia_iso in st.session_state.plan_manual:
                        # Añadir a día existente
                        datos_existentes = st.session_state.plan_manual[dia_iso]
                        visitas_existentes = datos_existentes['ruta'] if isinstance(datos_existentes, dict) else datos_existentes
                        st.session_state.plan_manual[dia_iso] = visitas_existentes + visitas_nuevas
                    else:
                        # Crear nuevo día
                        st.session_state.plan_manual[dia_iso] = visitas_nuevas

                st.success(f"✅ {len(visitas_disponibles) - len(no_asignadas)} visitas asignadas automáticamente!")
                if no_asignadas:
                    st.warning(f"⚠️ {len(no_asignadas)} visitas no pudieron ser asignadas por falta de capacidad")
                st.rerun()

            st.markdown("---")

        if visitas_disponibles:
            for visita in visitas_disponibles:
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        ayuda = " 🆘" if visita.get('ayuda_solicitada') else ""
                        st.markdown(f"**📍 {visita['direccion_texto']}**{ayuda}")
                        st.caption(f"Equipo: {visita['equipo']} | Coord: {visita['nombre_coordinador']}")
                    with c2:
                        # Selector de día con recomendaciones
                        dias_semana = [start_of_next_week + timedelta(days=i) for i in range(5)]

                        # Calcular scores para todos los días
                        scores_dias = {}
                        for dia_opcion in dias_semana:
                            scores_dias[dia_opcion.isoformat()] = calcular_score_idoneidad(
                                visita, dia_opcion.isoformat(), st.session_state.plan_manual, optimizer
                            )

                        # Ordenar días por score
                        dias_ordenados = sorted(
                            dias_semana,
                            key=lambda d: scores_dias[d.isoformat()]['score'],
                            reverse=True
                        )

                        def format_dia_con_score(d):
                            if d is None:
                                return "Elegir día..."
                            score_info = scores_dias[d.isoformat()]
                            return f"{d.strftime('%a %d/%m')} {score_info['estrellas']} ({score_info['capacidad_pct']:.0f}%)"

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
                            datos_dia_actual = st.session_state.plan_manual.get(dia_iso, [])
                            visitas_del_dia = datos_dia_actual['ruta'] if isinstance(datos_dia_actual, dict) else datos_dia_actual
                            tiempo_actual = calcular_tiempo_total_dia(visitas_del_dia, optimizer)
                            tiempo_con_nueva = calcular_tiempo_total_dia(visitas_del_dia + [visita], optimizer)
                            limite_dia = get_daily_time_budget(dia_seleccionado.weekday())

                            if tiempo_con_nueva > limite_dia:
                                st.error(f"⚠️ Excede jornada ({tiempo_con_nueva/3600:.1f}h)")
                            else:
                                if dia_iso not in st.session_state.plan_manual:
                                    st.session_state.plan_manual[dia_iso] = []
                                # Asegurar formato lista simple para compatibilidad
                                if isinstance(st.session_state.plan_manual[dia_iso], dict):
                                    st.session_state.plan_manual[dia_iso] = st.session_state.plan_manual[dia_iso]['ruta']
                                st.session_state.plan_manual[dia_iso].append(visita)
                                st.rerun()
        else:
            st.success("✅ Todas las visitas están asignadas")
    
    with col2:
        st.markdown("##### Plan Actual")
        if st.session_state.plan_manual:
            for dia_iso in sorted(st.session_state.plan_manual.keys()):
                dia = date.fromisoformat(dia_iso)
                datos_dia = st.session_state.plan_manual[dia_iso]
                visitas = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia
                tiempo_total = calcular_tiempo_total_dia(visitas, optimizer)
                limite = get_daily_time_budget(dia.weekday())
                
                with st.expander(f"**{dia.strftime('%A %d/%m')}** ({len(visitas)} visitas - {tiempo_total/3600:.1f}h)", expanded=True):
                    # Botón de optimización por día
                    if len(visitas) > 2:
                        if st.button(f"✨ Optimizar orden del {dia.strftime('%A')}", key=f"opt_{dia_iso}", use_container_width=True):
                            # Asegurar formato lista
                            if isinstance(st.session_state.plan_manual[dia_iso], dict):
                                visitas_a_optimizar = st.session_state.plan_manual[dia_iso]['ruta']
                            else:
                                visitas_a_optimizar = st.session_state.plan_manual[dia_iso]

                            # Optimizar
                            visitas_optimizadas, tiempo_opt = optimizer.optimize_route(visitas_a_optimizar, DURACION_VISITA_SEGUNDOS)
                            st.session_state.plan_manual[dia_iso] = visitas_optimizadas
                            st.success(f"✅ Orden optimizado! Tiempo estimado: {tiempo_opt/3600:.1f}h")
                            st.rerun()

                    for idx, v in enumerate(visitas):
                        col_v1, col_v2 = st.columns([4, 1])
                        with col_v1:
                            st.markdown(f"{idx+1}. {v['direccion_texto']}")
                        with col_v2:
                            if st.button("❌", key=f"remove_{v['id']}_{dia_iso}"):
                                # Asegurar formato lista para poder eliminar
                                if isinstance(st.session_state.plan_manual[dia_iso], dict):
                                    st.session_state.plan_manual[dia_iso] = st.session_state.plan_manual[dia_iso]['ruta']
                                st.session_state.plan_manual[dia_iso].remove(v)
                                if not st.session_state.plan_manual[dia_iso]:
                                    del st.session_state.plan_manual[dia_iso]
                                st.rerun()

                    if tiempo_total > limite:
                        st.error(f"⚠️ Excede límite: {tiempo_total/3600:.1f}h / {limite/3600:.1f}h")
        else:
            st.info("El plan está vacío")

    # ASISTENTE DE BALANCEO (fuera de las tabs)
    st.markdown("---")

    if st.session_state.plan_manual:
        with st.expander("🧠 **Asistente de Balanceo** - Ver análisis y sugerencias", expanded=False):
            with st.spinner("Analizando plan..."):
                problemas, sugerencias = analizar_plan_y_sugerir(st.session_state.plan_manual, optimizer)

            if problemas:
                st.warning("**⚠️ Problemas detectados:**")
                for p in problemas:
                    if p['tipo'] == 'sobrecarga':
                        st.error(f"🔴 {p['dia']}: {p['mensaje']}")
                    else:
                        st.info(f"🔵 {p['dia']}: {p['mensaje']}")

            if sugerencias:
                st.success("**💡 Sugerencias de mejora:**")
                for idx, sug in enumerate(sugerencias):
                    col_sug1, col_sug2 = st.columns([3, 1])
                    with col_sug1:
                        st.markdown(f"**{idx+1}.** {sug['mensaje']}")
                        st.caption(f"📊 {sug['beneficio']}")
                    with col_sug2:
                        if sug['tipo'] == 'mover':
                            if st.button("Aplicar", key=f"apply_sug_{idx}"):
                                # Mover visita
                                origen_datos = st.session_state.plan_manual[sug['origen']]
                                origen_visitas = origen_datos['ruta'] if isinstance(origen_datos, dict) else origen_datos

                                visita_a_mover = next((v for v in origen_visitas if v['id'] == sug['visita_id']), None)

                                if visita_a_mover:
                                    # Remover del origen
                                    if isinstance(st.session_state.plan_manual[sug['origen']], dict):
                                        st.session_state.plan_manual[sug['origen']]['ruta'].remove(visita_a_mover)
                                    else:
                                        st.session_state.plan_manual[sug['origen']].remove(visita_a_mover)

                                    # Añadir al destino
                                    if sug['destino'] not in st.session_state.plan_manual:
                                        st.session_state.plan_manual[sug['destino']] = []

                                    if isinstance(st.session_state.plan_manual[sug['destino']], dict):
                                        st.session_state.plan_manual[sug['destino']]['ruta'].append(visita_a_mover)
                                    else:
                                        st.session_state.plan_manual[sug['destino']].append(visita_a_mover)

                                    st.success("✅ Visita movida!")
                                    st.rerun()
                        elif sug['tipo'] == 'optimizar':
                            if st.button("Aplicar", key=f"apply_sug_{idx}"):
                                # Optimizar día
                                datos_dia = st.session_state.plan_manual[sug['dia']]
                                visitas = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia
                                visitas_opt, _ = optimizer.optimize_route(visitas, DURACION_VISITA_SEGUNDOS)
                                st.session_state.plan_manual[sug['dia']] = visitas_opt
                                st.success("✅ Día optimizado!")
                                st.rerun()

            if not problemas and not sugerencias:
                st.success("✅ El plan está bien balanceado. ¡Buen trabajo!")

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
        for datos_dia in st.session_state.plan_hibrido.values():
            visitas = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia
            ids_en_plan.update([v['id'] for v in visitas])
        
        visitas_fuera_plan = [v for v in todas_visitas if v['id'] not in ids_en_plan and v.get('status') == 'Propuesta']
        
        optimizer = RouteOptimizer()
        
        for dia_iso in sorted(st.session_state.plan_hibrido.keys()):
            dia = date.fromisoformat(dia_iso)
            with st.expander(f"**{dia.strftime('%A %d/%m')}**", expanded=True):
                datos_dia = st.session_state.plan_hibrido[dia_iso]
                visitas_dia = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia
                
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
                            # Asegurar formato lista
                            if isinstance(st.session_state.plan_hibrido[dia_iso], dict):
                                st.session_state.plan_hibrido[dia_iso] = st.session_state.plan_hibrido[dia_iso]['ruta']
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
                            # Asegurar formato lista
                            if isinstance(st.session_state.plan_hibrido[dia_iso], dict):
                                st.session_state.plan_hibrido[dia_iso] = st.session_state.plan_hibrido[dia_iso]['ruta']
                            st.session_state.plan_hibrido[dia_iso].append(nueva_visita)
                            st.rerun()
                
                # Mostrar tiempo total
                tiempo_total = calcular_tiempo_total_dia(visitas_dia, optimizer)
                limite = get_daily_time_budget(dia.weekday())
                st.caption(f"⏱️ Tiempo total: {tiempo_total/3600:.1f}h / {limite/3600:.1f}h")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("❌ Descartar y empezar de nuevo", use_container_width=True):
                del st.session_state.plan_hibrido
                st.rerun()
        with col2:
            if st.button("✨ Re-optimizar cada día", use_container_width=True):
                # Re-optimizar cada día manteniendo las visitas asignadas
                for dia_iso in list(st.session_state.plan_hibrido.keys()):
                    datos_dia = st.session_state.plan_hibrido[dia_iso]
                    visitas = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia

                    if len(visitas) > 2:
                        visitas_opt, tiempo_opt = optimizer.optimize_route(visitas, DURACION_VISITA_SEGUNDOS)
                        st.session_state.plan_hibrido[dia_iso] = visitas_opt

                st.success("✅ Todos los días re-optimizados!")
                st.rerun()
        with col3:
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