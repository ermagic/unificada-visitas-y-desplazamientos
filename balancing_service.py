"""
Servicio para análisis y balanceo de planes de visitas
"""
from typing import Dict, List
from datetime import date

from models import Visit, DayPlan, WeekPlan, Problem, Suggestion, AnalysisResult
from config import (
    get_daily_time_budget, UMBRAL_SOBRECARGA, UMBRAL_BAJA_OCUPACION,
    UMBRAL_MEJORA_OPTIMIZACION, MAX_SUGERENCIAS_MOSTRAR, DURACION_VISITA_SEGUNDOS
)
from route_optimizer import RouteOptimizer


class BalancingService:
    """Servicio para analizar y sugerir mejoras en planes"""

    def __init__(self, optimizer: RouteOptimizer = None):
        self.optimizer = optimizer or RouteOptimizer()

    def analyze_plan(self, plan: Dict[str, dict]) -> AnalysisResult:
        """
        Analiza un plan completo y genera problemas y sugerencias

        Args:
            plan: Diccionario con formato legacy {fecha_iso: {ruta: [...], tiempo_total: int}}

        Returns:
            AnalysisResult con problemas y sugerencias detectados
        """
        if not plan:
            return AnalysisResult()

        # Convertir plan a estructura analizable
        dias_info = self._build_days_info(plan)

        # Detectar problemas
        problemas = self._detect_problems(dias_info)

        # Generar sugerencias
        sugerencias = self._generate_suggestions(dias_info)

        return AnalysisResult(
            problemas=problemas,
            sugerencias=sugerencias[:MAX_SUGERENCIAS_MOSTRAR]
        )

    def _build_days_info(self, plan: Dict[str, dict]) -> Dict[str, dict]:
        """Construye información detallada de cada día"""
        dias_info = {}

        for dia_iso in sorted(plan.keys()):
            dia = date.fromisoformat(dia_iso)
            datos_dia = plan[dia_iso]
            visitas = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia

            tiempo_total = self._calculate_day_time(visitas)
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

        return dias_info

    def _calculate_day_time(self, visitas: List[dict]) -> int:
        """Calcula tiempo total de un día"""
        if not visitas:
            return 0
        _, tiempo = self.optimizer.optimize_route(visitas, DURACION_VISITA_SEGUNDOS)
        return tiempo

    def _detect_problems(self, dias_info: Dict[str, dict]) -> List[Problem]:
        """Detecta problemas en el plan"""
        problemas = []

        for dia_iso, info in dias_info.items():
            # Problema: Sobrecarga
            if info['capacidad_usada'] > UMBRAL_SOBRECARGA:
                exceso_mins = (info['tiempo_total'] - info['limite']) / 60
                problemas.append(Problem(
                    tipo='sobrecarga',
                    dia=info['dia'].strftime('%A %d/%m'),
                    mensaje=f"Sobrecargado ({info['capacidad_usada']:.0f}% - excede {exceso_mins:.0f} min)",
                    severidad=5
                ))

            # Problema: Baja ocupación
            elif info['capacidad_usada'] < UMBRAL_BAJA_OCUPACION and info['num_visitas'] > 0:
                problemas.append(Problem(
                    tipo='subcapacidad',
                    dia=info['dia'].strftime('%A %d/%m'),
                    mensaje=f"Baja ocupación ({info['capacidad_usada']:.0f}% - solo {info['num_visitas']} visitas)",
                    severidad=2
                ))

        return sorted(problemas, key=lambda p: p.severidad, reverse=True)

    def _generate_suggestions(self, dias_info: Dict[str, dict]) -> List[Suggestion]:
        """Genera sugerencias de mejora"""
        sugerencias = []
        dias_list = list(dias_info.items())

        # Sugerencia 1: Mover visitas entre días
        sugerencias.extend(self._suggest_move_visits(dias_list))

        # Sugerencia 2: Optimizar orden de visitas
        sugerencias.extend(self._suggest_optimize_order(dias_info))

        return sugerencias

    def _suggest_move_visits(self, dias_list: List[tuple]) -> List[Suggestion]:
        """Sugiere mover visitas para balancear carga"""
        sugerencias = []

        for i, (dia_iso_origen, info_origen) in enumerate(dias_list):
            if info_origen['capacidad_usada'] > UMBRAL_SOBRECARGA:
                for j, (dia_iso_destino, info_destino) in enumerate(dias_list):
                    if i != j and info_destino['capacidad_usada'] < 90:
                        # Buscar visita movible
                        for visita in info_origen['visitas']:
                            tiempo_sin_visita = self._calculate_day_time(
                                [v for v in info_origen['visitas'] if v['id'] != visita['id']]
                            )
                            tiempo_con_visita = self._calculate_day_time(
                                info_destino['visitas'] + [visita]
                            )

                            if (tiempo_sin_visita <= info_origen['limite'] and
                                tiempo_con_visita <= info_destino['limite']):
                                sugerencias.append(Suggestion(
                                    tipo='mover',
                                    mensaje=f"Mover '{visita['direccion_texto'][:40]}...' de {info_origen['dia'].strftime('%A')} a {info_destino['dia'].strftime('%A')}",
                                    beneficio=f"Balancea carga (-{(info_origen['tiempo_total']-tiempo_sin_visita)/60:.0f}min origen, +{(tiempo_con_visita-info_destino['tiempo_total'])/60:.0f}min destino)",
                                    data={
                                        'origen': dia_iso_origen,
                                        'destino': dia_iso_destino,
                                        'visita_id': visita['id']
                                    }
                                ))
                                break

        return sugerencias

    def _suggest_optimize_order(self, dias_info: Dict[str, dict]) -> List[Suggestion]:
        """Sugiere optimizar orden de visitas"""
        sugerencias = []

        for dia_iso, info in dias_info.items():
            if info['num_visitas'] > 3:
                # Simular optimización
                visitas_originales = info['visitas']
                visitas_optimizadas, tiempo_opt = self.optimizer.optimize_route(
                    visitas_originales,
                    DURACION_VISITA_SEGUNDOS
                )

                # Ver si hay mejora significativa
                orden_diferente = [v['id'] for v in visitas_originales] != [v['id'] for v in visitas_optimizadas]

                if orden_diferente and abs(tiempo_opt - info['tiempo_total']) > UMBRAL_MEJORA_OPTIMIZACION:
                    ahorro = (info['tiempo_total'] - tiempo_opt) / 60
                    if ahorro > 0:
                        sugerencias.append(Suggestion(
                            tipo='optimizar',
                            mensaje=f"Reordenar visitas del {info['dia'].strftime('%A')} por proximidad",
                            beneficio=f"Ahorras ~{ahorro:.0f} minutos",
                            data={'dia': dia_iso}
                        ))

        return sugerencias

    def apply_suggestion(self, plan: Dict[str, dict], suggestion: Suggestion) -> Dict[str, dict]:
        """
        Aplica una sugerencia al plan

        Args:
            plan: Plan actual
            suggestion: Sugerencia a aplicar

        Returns:
            Plan modificado
        """
        if suggestion.tipo == 'mover':
            return self._apply_move_suggestion(plan, suggestion)
        elif suggestion.tipo == 'optimizar':
            return self._apply_optimize_suggestion(plan, suggestion)
        return plan

    def _apply_move_suggestion(self, plan: Dict[str, dict], suggestion: Suggestion) -> Dict[str, dict]:
        """Aplica sugerencia de mover visita"""
        origen = suggestion.data['origen']
        destino = suggestion.data['destino']
        visita_id = suggestion.data['visita_id']

        # Extraer visitas
        origen_datos = plan[origen]
        origen_visitas = origen_datos['ruta'] if isinstance(origen_datos, dict) else origen_datos

        # Encontrar y remover visita
        visita_a_mover = next((v for v in origen_visitas if v['id'] == visita_id), None)
        if not visita_a_mover:
            return plan

        origen_visitas.remove(visita_a_mover)

        # Añadir al destino
        if destino not in plan:
            plan[destino] = []

        destino_datos = plan[destino]
        destino_visitas = destino_datos['ruta'] if isinstance(destino_datos, dict) else destino_datos
        destino_visitas.append(visita_a_mover)

        return plan

    def _apply_optimize_suggestion(self, plan: Dict[str, dict], suggestion: Suggestion) -> Dict[str, dict]:
        """Aplica sugerencia de optimizar día"""
        dia_iso = suggestion.data['dia']
        datos_dia = plan[dia_iso]
        visitas = datos_dia['ruta'] if isinstance(datos_dia, dict) else datos_dia

        visitas_opt, _ = self.optimizer.optimize_route(visitas, DURACION_VISITA_SEGUNDOS)
        plan[dia_iso] = visitas_opt

        return plan
