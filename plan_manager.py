"""
Manager para gestión de planes y estado de sesión
"""
from typing import Dict, List, Optional
from datetime import date, datetime, time, timedelta
import streamlit as st

from models import Visit, DayPlan, WeekPlan
from config import get_daily_time_budget, HORA_INICIO_DIA, DURACION_VISITA_SEGUNDOS
from route_optimizer import RouteOptimizer


class PlanManager:
    """Manager para gestionar planes en session_state"""

    def __init__(self, optimizer: RouteOptimizer = None):
        self.optimizer = optimizer or RouteOptimizer()

    # ==================== GETTERS ====================

    def get_plan_manual(self) -> Optional[Dict]:
        """Obtiene el plan manual de session_state"""
        return st.session_state.get('plan_manual')

    def get_plan_propuesto(self) -> Optional[Dict]:
        """Obtiene el plan propuesto de session_state"""
        return st.session_state.get('plan_propuesto')

    def get_plan_hibrido(self) -> Optional[Dict]:
        """Obtiene el plan híbrido de session_state"""
        return st.session_state.get('plan_hibrido')

    def get_plan_con_horas(self) -> Optional[Dict]:
        """Obtiene el plan con horas calculadas"""
        return st.session_state.get('plan_con_horas')

    # ==================== SETTERS ====================

    def set_plan_manual(self, plan: Dict):
        """Establece el plan manual"""
        st.session_state.plan_manual = plan

    def set_plan_propuesto(self, plan: Dict):
        """Establece el plan propuesto"""
        st.session_state.plan_propuesto = plan

    def set_plan_hibrido(self, plan: Dict):
        """Establece el plan híbrido"""
        st.session_state.plan_hibrido = plan

    def set_plan_con_horas(self, plan: Dict):
        """Establece el plan con horas"""
        st.session_state.plan_con_horas = plan

    # ==================== OPERATIONS ====================

    def clear_all_plans(self):
        """Limpia todos los planes de session_state"""
        for key in ['plan_manual', 'plan_propuesto', 'plan_hibrido', 'plan_con_horas', 'visitas_no_asignadas']:
            if key in st.session_state:
                del st.session_state[key]

    def clear_plan_manual(self):
        """Limpia solo el plan manual"""
        if 'plan_manual' in st.session_state:
            del st.session_state.plan_manual

    def clear_plan_propuesto(self):
        """Limpia el plan propuesto y sus horas"""
        if 'plan_propuesto' in st.session_state:
            del st.session_state.plan_propuesto
        if 'plan_con_horas' in st.session_state:
            del st.session_state.plan_con_horas

    def initialize_plan_manual(self):
        """Inicializa el plan manual si no existe"""
        if 'plan_manual' not in st.session_state:
            st.session_state.plan_manual = {}

    # ==================== CONVERSIONS ====================

    def extract_visits_from_day(self, day_data: any) -> List[dict]:
        """
        Extrae visitas de un día, manejando ambos formatos

        Args:
            day_data: Puede ser lista de visitas o dict con 'ruta'

        Returns:
            Lista de visitas
        """
        if isinstance(day_data, dict) and 'ruta' in day_data:
            return day_data['ruta']
        return day_data if day_data else []

    def ensure_list_format(self, day_data: any) -> List[dict]:
        """
        Asegura que day_data esté en formato lista simple

        Args:
            day_data: Dato del día

        Returns:
            Lista de visitas
        """
        return self.extract_visits_from_day(day_data)

    def convert_to_dict_format(self, visits: List[dict], tiempo_total: int = None) -> dict:
        """
        Convierte lista de visitas a formato dict

        Args:
            visits: Lista de visitas
            tiempo_total: Tiempo total (opcional, se calcula si no se proporciona)

        Returns:
            Dict con formato {'ruta': [...], 'tiempo_total': int}
        """
        if tiempo_total is None:
            _, tiempo_total = self.optimizer.optimize_route(visits, DURACION_VISITA_SEGUNDOS)

        return {
            'ruta': visits,
            'tiempo_total': tiempo_total
        }

    # ==================== CALCULATIONS ====================

    def calculate_plan_with_hours(self, plan: Dict) -> Dict:
        """
        Calcula las horas de llegada para cada visita del plan

        Args:
            plan: Plan en formato legacy

        Returns:
            Plan con horas calculadas
        """
        plan_con_horas = {}

        for day_iso, datos_dia in plan.items():
            day = date.fromisoformat(day_iso)
            hora_actual = datetime.combine(day, HORA_INICIO_DIA)
            visitas_con_hora = []

            # Extraer visitas
            visitas = self.extract_visits_from_day(datos_dia)

            if visitas:
                # Primera visita
                v_primera = visitas[0].copy()
                v_primera['hora_asignada'] = hora_actual.strftime('%H:%M')
                visitas_con_hora.append(v_primera)

                # Resto de visitas
                for i in range(len(visitas) - 1):
                    hora_actual += timedelta(seconds=DURACION_VISITA_SEGUNDOS)
                    origen = visitas[i]['direccion_texto']
                    destino = visitas[i+1]['direccion_texto']

                    _, tiempo_viaje = self.optimizer.get_distance_duration(origen, destino)
                    if tiempo_viaje:
                        hora_actual += timedelta(seconds=tiempo_viaje)
                    else:
                        hora_actual += timedelta(minutes=30)  # Fallback

                    v_siguiente = visitas[i+1].copy()
                    v_siguiente['hora_asignada'] = hora_actual.strftime('%H:%M')
                    visitas_con_hora.append(v_siguiente)

            plan_con_horas[day_iso] = visitas_con_hora

        return plan_con_horas

    def calculate_day_time(self, visits: List[dict]) -> int:
        """
        Calcula el tiempo total de un día

        Args:
            visits: Lista de visitas

        Returns:
            Tiempo total en segundos
        """
        if not visits:
            return 0

        _, tiempo = self.optimizer.optimize_route(visits, DURACION_VISITA_SEGUNDOS)
        return tiempo

    # ==================== PLAN OPERATIONS ====================

    def add_visit_to_day(self, plan: Dict, dia_iso: str, visita: dict) -> Dict:
        """
        Añade una visita a un día del plan

        Args:
            plan: Plan actual
            dia_iso: Fecha en formato ISO
            visita: Visita a añadir

        Returns:
            Plan actualizado
        """
        if dia_iso not in plan:
            plan[dia_iso] = []

        # Asegurar formato lista
        if isinstance(plan[dia_iso], dict):
            plan[dia_iso] = plan[dia_iso]['ruta']

        plan[dia_iso].append(visita)
        return plan

    def remove_visit_from_day(self, plan: Dict, dia_iso: str, visita_id: str) -> Dict:
        """
        Elimina una visita de un día

        Args:
            plan: Plan actual
            dia_iso: Fecha en formato ISO
            visita_id: ID de la visita a eliminar

        Returns:
            Plan actualizado
        """
        if dia_iso not in plan:
            return plan

        # Asegurar formato lista
        if isinstance(plan[dia_iso], dict):
            plan[dia_iso] = plan[dia_iso]['ruta']

        plan[dia_iso] = [v for v in plan[dia_iso] if v['id'] != visita_id]

        # Eliminar día si queda vacío
        if not plan[dia_iso]:
            del plan[dia_iso]

        return plan

    def move_visit_between_days(
        self,
        plan: Dict,
        origen_iso: str,
        destino_iso: str,
        visita_id: str
    ) -> Dict:
        """
        Mueve una visita entre días

        Args:
            plan: Plan actual
            origen_iso: Día origen
            destino_iso: Día destino
            visita_id: ID de la visita

        Returns:
            Plan actualizado
        """
        # Obtener visita
        origen_visitas = self.extract_visits_from_day(plan.get(origen_iso, []))
        visita_a_mover = next((v for v in origen_visitas if v['id'] == visita_id), None)

        if not visita_a_mover:
            return plan

        # Remover del origen
        plan = self.remove_visit_from_day(plan, origen_iso, visita_id)

        # Añadir al destino
        plan = self.add_visit_to_day(plan, destino_iso, visita_a_mover)

        return plan

    def optimize_day(self, plan: Dict, dia_iso: str) -> Dict:
        """
        Optimiza el orden de visitas de un día específico

        Args:
            plan: Plan actual
            dia_iso: Día a optimizar

        Returns:
            Plan con día optimizado
        """
        if dia_iso not in plan:
            return plan

        visitas = self.extract_visits_from_day(plan[dia_iso])

        if len(visitas) > 2:
            visitas_opt, tiempo_opt = self.optimizer.optimize_route(visitas, DURACION_VISITA_SEGUNDOS)
            plan[dia_iso] = visitas_opt

        return plan

    def optimize_all_days(self, plan: Dict) -> Dict:
        """
        Optimiza todos los días del plan

        Args:
            plan: Plan actual

        Returns:
            Plan completamente optimizado
        """
        for dia_iso in list(plan.keys()):
            plan = self.optimize_day(plan, dia_iso)

        return plan

    # ==================== CONVERSIONS BETWEEN MODES ====================

    def convert_auto_to_manual(self, plan_auto: Dict) -> Dict:
        """
        Convierte un plan automático a formato manual editable

        Args:
            plan_auto: Plan generado automáticamente

        Returns:
            Plan en formato manual
        """
        plan_manual = {}

        for dia_iso, datos in plan_auto.items():
            visitas = self.extract_visits_from_day(datos)
            plan_manual[dia_iso] = visitas

        return plan_manual

    def merge_plans(self, plan_base: Dict, plan_adicional: Dict) -> Dict:
        """
        Fusiona dos planes combinando visitas de cada día

        Args:
            plan_base: Plan base
            plan_adicional: Plan a fusionar

        Returns:
            Plan fusionado
        """
        plan_fusionado = plan_base.copy()

        for dia_iso, datos in plan_adicional.items():
            visitas_nuevas = self.extract_visits_from_day(datos)

            if dia_iso in plan_fusionado:
                # Fusionar con día existente
                visitas_existentes = self.extract_visits_from_day(plan_fusionado[dia_iso])
                plan_fusionado[dia_iso] = visitas_existentes + visitas_nuevas
            else:
                # Crear nuevo día
                plan_fusionado[dia_iso] = visitas_nuevas

        return plan_fusionado
