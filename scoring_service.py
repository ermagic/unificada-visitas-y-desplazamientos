"""
Servicio para calcular scores de idoneidad de visitas
"""
from typing import Dict
from datetime import date

from models import Visit, ScoreInfo
from config import (
    get_daily_time_budget, PESO_CAPACIDAD, PESO_PROXIMIDAD,
    PROXIMIDAD_IDEAL, PROXIMIDAD_MAXIMA, DURACION_VISITA_SEGUNDOS
)
from route_optimizer import RouteOptimizer


class ScoringService:
    """Servicio para calcular qué tan idónea es una visita para un día"""

    def __init__(self, optimizer: RouteOptimizer = None):
        self.optimizer = optimizer or RouteOptimizer()

    def calculate_score(
        self,
        visita: dict,
        dia: date,
        plan_actual: Dict[str, dict]
    ) -> ScoreInfo:
        """
        Calcula el score de idoneidad de una visita para un día específico

        Args:
            visita: Diccionario con datos de la visita
            dia: Fecha del día a evaluar
            plan_actual: Plan actual (legacy format)

        Returns:
            ScoreInfo con score y detalles
        """
        dia_iso = dia.isoformat()
        datos_dia = plan_actual.get(dia_iso, [])
        visitas_dia = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia

        # Factor 1: Capacidad disponible
        capacidad_disponible = self._calculate_capacity_factor(dia, visitas_dia)

        # Factor 2: Proximidad geográfica
        proximidad = self._calculate_proximity_factor(visita, visitas_dia)

        # Score combinado
        score = (capacidad_disponible * PESO_CAPACIDAD) + (proximidad * PESO_PROXIMIDAD)

        # Calcular % de capacidad usada
        limite = get_daily_time_budget(dia.weekday())
        tiempo_actual = self._calculate_day_time(visitas_dia)
        capacidad_pct = (tiempo_actual / limite * 100) if limite > 0 else 0

        return ScoreInfo(
            score=score,
            capacidad_disponible=capacidad_disponible,
            proximidad=proximidad,
            capacidad_pct=capacidad_pct
        )

    def _calculate_capacity_factor(self, dia: date, visitas_dia: list) -> float:
        """
        Calcula el factor de capacidad disponible (0-1)

        Args:
            dia: Fecha del día
            visitas_dia: Visitas ya asignadas al día

        Returns:
            Factor de capacidad (0=lleno, 1=vacío)
        """
        limite = get_daily_time_budget(dia.weekday())
        tiempo_actual = self._calculate_day_time(visitas_dia)
        capacidad_disponible = max(0, (limite - tiempo_actual) / limite)

        return capacidad_disponible

    def _calculate_proximity_factor(self, visita: dict, visitas_dia: list) -> float:
        """
        Calcula el factor de proximidad geográfica (0-1)

        Args:
            visita: Visita a evaluar
            visitas_dia: Visitas ya en el día

        Returns:
            Factor de proximidad (1=muy cerca, 0=muy lejos)
        """
        if not visitas_dia:
            # Bonus por ser el primero del día
            return 0.7

        # Calcular distancia promedio a las visitas del día
        distancias = []
        for v_existente in visitas_dia:
            dist, _ = self.optimizer.get_distance_duration(
                visita['direccion_texto'],
                v_existente['direccion_texto']
            )
            if dist:
                distancias.append(dist)

        if not distancias:
            return 0.5  # Valor neutral si no se pudo calcular

        dist_promedio = sum(distancias) / len(distancias)

        # Normalizar: 0-20km = 1.0, >50km = 0
        proximidad = max(0, 1 - (dist_promedio / PROXIMIDAD_MAXIMA))

        return proximidad

    def _calculate_day_time(self, visitas: list) -> int:
        """Calcula tiempo total de un día"""
        if not visitas:
            return 0

        _, tiempo = self.optimizer.optimize_route(visitas, DURACION_VISITA_SEGUNDOS)
        return tiempo

    def calculate_scores_for_all_days(
        self,
        visita: dict,
        dias_disponibles: list,
        plan_actual: Dict[str, dict]
    ) -> Dict[str, ScoreInfo]:
        """
        Calcula scores para todos los días disponibles

        Args:
            visita: Visita a evaluar
            dias_disponibles: Lista de fechas (date objects)
            plan_actual: Plan actual

        Returns:
            Dict {fecha_iso: ScoreInfo}
        """
        scores = {}

        for dia in dias_disponibles:
            scores[dia.isoformat()] = self.calculate_score(visita, dia, plan_actual)

        return scores

    def get_best_day(
        self,
        visita: dict,
        dias_disponibles: list,
        plan_actual: Dict[str, dict]
    ) -> tuple:
        """
        Obtiene el mejor día para una visita

        Args:
            visita: Visita a evaluar
            dias_disponibles: Lista de días disponibles
            plan_actual: Plan actual

        Returns:
            Tupla (fecha, ScoreInfo) del mejor día
        """
        scores = self.calculate_scores_for_all_days(visita, dias_disponibles, plan_actual)

        if not scores:
            return None, None

        mejor_dia_iso = max(scores.keys(), key=lambda d: scores[d].score)
        mejor_dia = date.fromisoformat(mejor_dia_iso)

        return mejor_dia, scores[mejor_dia_iso]

    def sort_days_by_score(
        self,
        visita: dict,
        dias_disponibles: list,
        plan_actual: Dict[str, dict]
    ) -> list:
        """
        Ordena días por score de idoneidad (mejor primero)

        Args:
            visita: Visita a evaluar
            dias_disponibles: Lista de días
            plan_actual: Plan actual

        Returns:
            Lista de fechas ordenadas por score descendente
        """
        scores = self.calculate_scores_for_all_days(visita, dias_disponibles, plan_actual)

        return sorted(
            dias_disponibles,
            key=lambda d: scores[d.isoformat()].score,
            reverse=True
        )
