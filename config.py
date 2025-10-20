"""
Configuración y constantes del sistema de planificación
"""
from datetime import time

# ==================== TIEMPOS Y JORNADAS ====================

# Duración de visita estándar (45 minutos en segundos)
DURACION_VISITA_SEGUNDOS = 45 * 60

# Presupuestos de tiempo por día (en segundos)
JORNADA_LUNES_JUEVES = 9 * 3600  # 9 horas
JORNADA_VIERNES = 7 * 3600  # 7 horas

# Hora de inicio estándar
HORA_INICIO_DIA = time(8, 0)

# ==================== LÍMITES Y UMBRALES ====================

# Límite de visitas para planificación coordinador
LIMITE_VISITAS_PLANIFICAR_COORDINADOR = 50

# Límite de visitas para usar 2-opt (optimización pesada)
LIMITE_VISITAS_2OPT = 15

# Número máximo de iteraciones en 2-opt
MAX_ITERACIONES_2OPT = 100

# Umbral mínimo de mejora en optimización (segundos)
UMBRAL_MEJORA_OPTIMIZACION = 300  # 5 minutos

# ==================== SCORING Y BALANCEO ====================

# Pesos para cálculo de score de idoneidad
PESO_CAPACIDAD = 0.6
PESO_PROXIMIDAD = 0.4

# Umbrales de capacidad
UMBRAL_SOBRECARGA = 100  # %
UMBRAL_BAJA_OCUPACION = 50  # %

# Umbrales de proximidad (metros)
PROXIMIDAD_IDEAL = 20000  # 20 km
PROXIMIDAD_MAXIMA = 50000  # 50 km

# ==================== CACHÉ ====================

# Tiempo de vida del caché de rutas (días)
CACHE_TTL_DIAS = 30

# Tamaño de chunk para llamadas batch a Google Maps API
GOOGLE_MAPS_CHUNK_SIZE = 25

# ==================== MAPAS ====================

# Centro de Cataluña para mapas
CATALONIA_CENTER = [41.8795, 1.7887]

# Punto de inicio supervisor (Martín)
PUNTO_INICIO_MARTIN = "Plaça de Catalunya, Barcelona, España"

# Colores por día de la semana
DAY_COLORS = {
    0: 'blue',      # Lunes
    1: 'red',       # Martes
    2: 'purple',    # Miércoles
    3: 'orange',    # Jueves
    4: 'green',     # Viernes
    5: 'gray',      # Sábado
    6: 'gray'       # Domingo
}

# Nombres de días en español
DIAS_ESPANOL = {
    "Monday": "Lunes",
    "Tuesday": "Martes",
    "Wednesday": "Miércoles",
    "Thursday": "Jueves",
    "Friday": "Viernes",
    "Saturday": "Sábado",
    "Sunday": "Domingo"
}

# ==================== NOTIFICACIONES ====================

# Umbrales para alertas de desplazamiento
UMBRAL_PERNOCTACION = 80  # minutos
UMBRAL_MEDIA_DIETA = 40  # km
UMBRAL_TURNO_ESPECIAL = 60  # minutos

# ==================== UI ====================

# Número máximo de sugerencias a mostrar
MAX_SUGERENCIAS_MOSTRAR = 3

# Número mínimo de visitas para habilitar optimización automática
MIN_VISITAS_AUTO_ASIGNAR = 3


def get_daily_time_budget(weekday: int) -> int:
    """
    Devuelve el presupuesto de tiempo en segundos para un día de la semana

    Args:
        weekday: Día de la semana (0=Lunes, 4=Viernes)

    Returns:
        Segundos de jornada laboral
    """
    return JORNADA_VIERNES if weekday == 4 else JORNADA_LUNES_JUEVES


def get_dia_nombre_espanol(weekday_name: str) -> str:
    """
    Convierte nombre de día en inglés a español

    Args:
        weekday_name: Nombre en inglés (ej: "Monday")

    Returns:
        Nombre en español (ej: "Lunes")
    """
    return DIAS_ESPANOL.get(weekday_name, weekday_name)


def get_color_for_day(weekday: int) -> str:
    """
    Obtiene el color asignado a un día de la semana

    Args:
        weekday: Día de la semana (0=Lunes, 6=Domingo)

    Returns:
        Color en formato string (ej: "blue")
    """
    return DAY_COLORS.get(weekday, 'gray')
