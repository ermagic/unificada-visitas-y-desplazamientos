"""
Componentes UI reutilizables para Streamlit
"""
import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
from datetime import date
from typing import Dict, List, Optional, Callable

from models import Problem, Suggestion, ScoreInfo
from config import CATALONIA_CENTER, DAY_COLORS, get_dia_nombre_espanol


class UIComponents:
    """Clase con componentes UI reutilizables"""

    @staticmethod
    def render_progress_bar(steps: List[tuple]):
        """
        Renderiza una barra de progreso con pasos

        Args:
            steps: Lista de tuplas (porcentaje, mensaje)
                   Ej: [(20, "Cargando..."), (50, "Procesando...")]
        """
        progress_bar = st.progress(0)
        status_text = st.empty()

        for pct, msg in steps:
            status_text.text(msg)
            progress_bar.progress(pct)

        return progress_bar, status_text

    @staticmethod
    def render_problems(problemas: List[Problem]):
        """
        Renderiza lista de problemas detectados

        Args:
            problemas: Lista de Problem objects
        """
        if not problemas:
            return

        st.warning("**⚠️ Problemas detectados:**")
        for p in problemas:
            if p.tipo == 'sobrecarga':
                st.error(f"🔴 {p.dia}: {p.mensaje}")
            else:
                st.info(f"🔵 {p.dia}: {p.mensaje}")

    @staticmethod
    def render_suggestions(
        sugerencias: List[Suggestion],
        on_apply: Optional[Callable] = None
    ):
        """
        Renderiza lista de sugerencias con botones de aplicar

        Args:
            sugerencias: Lista de Suggestion objects
            on_apply: Callback function(suggestion) cuando se aplica una sugerencia
        """
        if not sugerencias:
            return

        st.success("**💡 Sugerencias de mejora:**")

        for idx, sug in enumerate(sugerencias):
            col1, col2 = st.columns([3, 1])

            with col1:
                st.markdown(f"**{idx+1}.** {sug.mensaje}")
                st.caption(f"📊 {sug.beneficio}")

            with col2:
                if on_apply and st.button("Aplicar", key=f"apply_sug_{idx}"):
                    on_apply(sug)

    @staticmethod
    def render_score_selector(
        label: str,
        options: List[any],
        scores: Dict[str, ScoreInfo],
        format_func: Callable,
        key: str,
        help_text: Optional[str] = None
    ):
        """
        Renderiza un selector con scores visuales

        Args:
            label: Etiqueta del selector
            options: Lista de opciones
            scores: Dict con scores de cada opción
            format_func: Función para formatear cada opción con su score
            key: Key única para el widget
            help_text: Texto de ayuda opcional

        Returns:
            Opción seleccionada
        """
        # Ordenar opciones por score
        sorted_options = sorted(
            options,
            key=lambda opt: scores.get(str(opt), ScoreInfo(0, 0, 0, 0)).score,
            reverse=True
        )

        return st.selectbox(
            label,
            options=[None] + sorted_options,
            format_func=format_func,
            key=key,
            help=help_text or "Días ordenados por idoneidad (capacidad + proximidad)"
        )

    @staticmethod
    def render_map(
        plan: Dict[str, dict],
        visitas_sin_asignar: Optional[List[dict]] = None,
        punto_inicio: Optional[tuple] = None,
        height: int = 500
    ):
        """
        Renderiza mapa interactivo con el plan

        Args:
            plan: Plan a visualizar {fecha_iso: {ruta: [...]}}
            visitas_sin_asignar: Visitas no asignadas (opcional)
            punto_inicio: Tupla (lat, lon) del punto de inicio (opcional)
            height: Altura del mapa en pixels

        Returns:
            Objeto de mapa de Folium
        """
        m = folium.Map(location=CATALONIA_CENTER, zoom_start=8)

        # Añadir punto de inicio si existe
        if punto_inicio:
            folium.Marker(
                punto_inicio,
                popup="Punto de Inicio",
                icon=folium.Icon(color='green', icon='home', prefix='fa')
            ).add_to(m)

        # Añadir visitas del plan
        all_points = []

        for i, (dia_iso, datos_dia) in enumerate(sorted(plan.items())):
            dia = date.fromisoformat(dia_iso)
            color = DAY_COLORS.get(dia.weekday(), 'gray')
            dia_nombre = get_dia_nombre_espanol(dia.strftime('%A'))

            # Extraer visitas
            visitas = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia
            points_of_day = []

            for idx, visita in enumerate(visitas):
                if pd.notna(visita.get('lat')) and pd.notna(visita.get('lon')):
                    coords = (visita['lat'], visita['lon'])
                    points_of_day.append(coords)
                    all_points.append(coords)

                    popup_html = f"""
                    <b>{dia_nombre} {dia.strftime('%d/%m')}</b><br>
                    Orden: {idx+1}<br>
                    <b>{visita['direccion_texto']}</b><br>
                    Equipo: {visita.get('equipo', 'N/A')}
                    """

                    folium.CircleMarker(
                        location=coords,
                        radius=8,
                        popup=folium.Popup(popup_html, max_width=250),
                        color=color,
                        fill=True,
                        fillColor=color,
                        fillOpacity=0.7
                    ).add_to(m)

            # Añadir líneas de ruta
            if len(points_of_day) > 1:
                folium.PolyLine(
                    points_of_day,
                    color=color,
                    weight=2.5,
                    opacity=0.8
                ).add_to(m)

        # Añadir visitas sin asignar
        if visitas_sin_asignar:
            for visita in visitas_sin_asignar:
                if pd.notna(visita.get('lat')) and pd.notna(visita.get('lon')):
                    coords = (visita['lat'], visita['lon'])
                    all_points.append(coords)

                    popup_html = f"""
                    <b>SIN ASIGNAR</b><br>
                    <b>{visita['direccion_texto']}</b><br>
                    Equipo: {visita.get('equipo', 'N/A')}
                    """

                    folium.CircleMarker(
                        location=coords,
                        radius=6,
                        popup=folium.Popup(popup_html, max_width=250),
                        color='gray',
                        fill=True,
                        fillColor='lightgray',
                        fillOpacity=0.5
                    ).add_to(m)

        # Ajustar bounds del mapa
        if all_points:
            df_points = pd.DataFrame(all_points, columns=['lat', 'lon'])
            sw = df_points[['lat', 'lon']].min().values.tolist()
            ne = df_points[['lat', 'lon']].max().values.tolist()
            m.fit_bounds([sw, ne])

        # Renderizar
        st_folium(m, use_container_width=True, height=height)

        return m

    @staticmethod
    def render_map_legend():
        """Renderiza la leyenda del mapa"""
        st.markdown("""
        **Leyenda:**
        🔵 Lunes | 🔴 Martes | 🟣 Miércoles | 🟠 Jueves | 🟢 Viernes | ⚪ Sin asignar
        """)

    @staticmethod
    def render_day_summary(dia_nombre: str, num_visitas: int, tiempo_horas: float, limite_horas: float):
        """
        Renderiza resumen de un día

        Args:
            dia_nombre: Nombre del día
            num_visitas: Número de visitas
            tiempo_horas: Tiempo estimado en horas
            limite_horas: Límite de jornada en horas
        """
        capacidad_pct = (tiempo_horas / limite_horas * 100) if limite_horas > 0 else 0

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Visitas", num_visitas)

        with col2:
            st.metric("Tiempo", f"{tiempo_horas:.1f}h")

        with col3:
            delta_color = "inverse" if capacidad_pct > 100 else "normal"
            st.metric(
                "Capacidad",
                f"{capacidad_pct:.0f}%",
                delta=f"{capacidad_pct - 100:.0f}%" if capacidad_pct != 100 else None
            )

    @staticmethod
    def render_transition_buttons(
        on_accept: Optional[Callable] = None,
        on_edit: Optional[Callable] = None,
        on_regenerate: Optional[Callable] = None
    ):
        """
        Renderiza botones de transición entre modos

        Args:
            on_accept: Callback para aceptar plan
            on_edit: Callback para editar manualmente
            on_regenerate: Callback para regenerar
        """
        col1, col2, col3 = st.columns(3)

        with col1:
            if on_accept and st.button("✅ Aceptar plan", use_container_width=True):
                on_accept()

        with col2:
            if on_edit and st.button("✏️ Editar manualmente", key="transition_edit", use_container_width=True):
                on_edit()

        with col3:
            if on_regenerate and st.button("🔄 Regenerar", use_container_width=True):
                on_regenerate()

    @staticmethod
    def render_optimization_button(dia_iso: str, num_visitas: int, on_click: Callable):
        """
        Renderiza botón de optimización por día

        Args:
            dia_iso: Fecha ISO del día
            num_visitas: Número de visitas en el día
            on_click: Callback function() cuando se hace click
        """
        if num_visitas > 2:
            dia = date.fromisoformat(dia_iso)
            dia_nombre = get_dia_nombre_espanol(dia.strftime('%A'))

            if st.button(
                f"✨ Optimizar orden del {dia_nombre}",
                key=f"opt_{dia_iso}",
                use_container_width=True
            ):
                on_click()

    @staticmethod
    def render_empty_state(titulo: str, mensaje: str, icon: str = "ℹ️"):
        """
        Renderiza un estado vacío

        Args:
            titulo: Título del estado vacío
            mensaje: Mensaje descriptivo
            icon: Icono a mostrar
        """
        st.markdown(f"""
        <div style='text-align: center; padding: 40px;'>
            <h2>{icon}</h2>
            <h3>{titulo}</h3>
            <p style='color: gray;'>{mensaje}</p>
        </div>
        """, unsafe_allow_html=True)
