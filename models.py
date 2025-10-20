"""
Modelos de datos para el sistema de planificación de visitas
"""
from dataclasses import dataclass, field
from datetime import date, time
from typing import Optional, List, Dict
from enum import Enum


class VisitStatus(Enum):
    """Estados posibles de una visita"""
    PROPUESTA = "Propuesta"
    ASIGNADA = "Asignada"
    ASIGNADA_SUPERVISOR = "Asignada a Supervisor"
    REALIZADA = "Realizada"
    CANCELADA = "Cancelada"


class UserRole(Enum):
    """Roles de usuario"""
    ADMIN = "Admin"
    SUPERVISOR = "Supervisor"
    COORDINADOR = "Coordinador"


@dataclass
class Visit:
    """Representa una visita a realizar"""
    id: str
    direccion_texto: str
    equipo: str
    usuario_id: str
    status: str
    fecha: Optional[date] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    hora_asignada: Optional[str] = None
    fecha_asignada: Optional[str] = None
    ayuda_solicitada: bool = False
    observaciones: Optional[str] = None
    nombre_coordinador: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'Visit':
        """Crea una Visit desde un diccionario de Supabase"""
        # Extraer nombre del coordinador si viene en usuarios
        nombre_coordinador = None
        if 'usuarios' in data and isinstance(data['usuarios'], dict):
            nombre_coordinador = data['usuarios'].get('nombre_completo')

        return cls(
            id=data['id'],
            direccion_texto=data['direccion_texto'],
            equipo=data['equipo'],
            usuario_id=data['usuario_id'],
            status=data['status'],
            fecha=date.fromisoformat(data['fecha']) if data.get('fecha') else None,
            lat=data.get('lat'),
            lon=data.get('lon'),
            hora_asignada=data.get('hora_asignada'),
            fecha_asignada=data.get('fecha_asignada'),
            ayuda_solicitada=data.get('ayuda_solicitada', False),
            observaciones=data.get('observaciones'),
            nombre_coordinador=nombre_coordinador
        )

    def to_dict(self) -> dict:
        """Convierte la Visit a diccionario compatible con código legacy"""
        return {
            'id': self.id,
            'direccion_texto': self.direccion_texto,
            'equipo': self.equipo,
            'usuario_id': self.usuario_id,
            'status': self.status,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'lat': self.lat,
            'lon': self.lon,
            'hora_asignada': self.hora_asignada,
            'fecha_asignada': self.fecha_asignada,
            'ayuda_solicitada': self.ayuda_solicitada,
            'observaciones': self.observaciones,
            'nombre_coordinador': self.nombre_coordinador
        }


@dataclass
class DayPlan:
    """Representa el plan de un día específico"""
    fecha: date
    visitas: List[Visit] = field(default_factory=list)
    tiempo_total_segundos: int = 0
    limite_segundos: int = 0

    @property
    def capacidad_usada_porcentaje(self) -> float:
        """Calcula el porcentaje de capacidad usado"""
        if self.limite_segundos == 0:
            return 0.0
        return (self.tiempo_total_segundos / self.limite_segundos) * 100

    @property
    def esta_sobrecargado(self) -> bool:
        """Verifica si el día excede su capacidad"""
        return self.tiempo_total_segundos > self.limite_segundos

    @property
    def tiene_baja_ocupacion(self) -> bool:
        """Verifica si el día tiene baja ocupación"""
        return self.capacidad_usada_porcentaje < 50 and len(self.visitas) > 0

    def to_dict(self) -> dict:
        """Convierte a formato legacy"""
        return {
            'ruta': [v.to_dict() for v in self.visitas],
            'tiempo_total': self.tiempo_total_segundos
        }


@dataclass
class WeekPlan:
    """Representa el plan de una semana completa"""
    dias: Dict[str, DayPlan] = field(default_factory=dict)  # iso_date -> DayPlan
    visitas_no_asignadas: List[Visit] = field(default_factory=list)

    def get_dia(self, fecha: date) -> Optional[DayPlan]:
        """Obtiene el plan de un día específico"""
        return self.dias.get(fecha.isoformat())

    def add_dia(self, fecha: date, plan: DayPlan):
        """Añade el plan de un día"""
        self.dias[fecha.isoformat()] = plan

    def get_all_visits(self) -> List[Visit]:
        """Obtiene todas las visitas del plan"""
        all_visits = []
        for day_plan in self.dias.values():
            all_visits.extend(day_plan.visitas)
        return all_visits

    def to_legacy_dict(self) -> dict:
        """Convierte a formato legacy compatible con código existente"""
        return {
            fecha_iso: day_plan.to_dict()
            for fecha_iso, day_plan in self.dias.items()
        }


@dataclass
class Problem:
    """Representa un problema detectado en un plan"""
    tipo: str  # 'sobrecarga', 'subcapacidad', etc.
    dia: str
    mensaje: str
    severidad: int = 1  # 1-5


@dataclass
class Suggestion:
    """Representa una sugerencia de mejora"""
    tipo: str  # 'mover', 'optimizar', etc.
    mensaje: str
    beneficio: str
    data: dict = field(default_factory=dict)  # Datos adicionales para aplicar la sugerencia


@dataclass
class AnalysisResult:
    """Resultado del análisis de un plan"""
    problemas: List[Problem] = field(default_factory=list)
    sugerencias: List[Suggestion] = field(default_factory=list)

    @property
    def tiene_problemas_criticos(self) -> bool:
        """Verifica si hay problemas críticos"""
        return any(p.tipo == 'sobrecarga' for p in self.problemas)

    @property
    def plan_esta_balanceado(self) -> bool:
        """Verifica si el plan está bien balanceado"""
        return len(self.problemas) == 0 and len(self.sugerencias) == 0


@dataclass
class ScoreInfo:
    """Información de score de idoneidad"""
    score: float  # 0.0 - 1.0
    capacidad_disponible: float
    proximidad: float
    capacidad_pct: float

    @property
    def estrellas(self) -> str:
        """Genera representación visual en estrellas"""
        num_estrellas = int(self.score * 5 + 0.5)
        return "⭐" * num_estrellas

    @property
    def categoria(self) -> str:
        """Categoriza el score"""
        if self.score >= 0.8:
            return "Excelente"
        elif self.score >= 0.6:
            return "Bueno"
        elif self.score >= 0.4:
            return "Aceptable"
        else:
            return "No recomendado"
