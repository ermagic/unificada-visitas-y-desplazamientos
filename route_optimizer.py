# Fichero: route_optimizer.py - Optimización de rutas eficiente con caché
import googlemaps
from datetime import datetime, timedelta
from database import supabase
import streamlit as st
from config import (
    CACHE_TTL_DIAS, GOOGLE_MAPS_CHUNK_SIZE,
    LIMITE_VISITAS_2OPT, MAX_ITERACIONES_2OPT
)

class RouteOptimizer:
    def __init__(self):
        self.gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
        self.cache_ttl_days = CACHE_TTL_DIAS
    
    def get_route_from_cache(self, origen, destino):
        """Intenta recuperar una ruta del caché"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=self.cache_ttl_days)).isoformat()
            
            response = supabase.table('rutas_cache').select('*').eq(
                'origen', origen
            ).eq(
                'destino', destino
            ).gte(
                'fecha_calculo', cutoff_date
            ).limit(1).execute()
            
            if response.data:
                return response.data[0]['distancia_metros'], response.data[0]['duracion_segundos']
            
            return None, None
        except:
            return None, None
    
    def save_route_to_cache(self, origen, destino, distancia, duracion):
        """Guarda una ruta en el caché"""
        try:
            supabase.table('rutas_cache').insert({
                'origen': origen,
                'destino': destino,
                'distancia_metros': distancia,
                'duracion_segundos': duracion
            }).execute()
        except:
            pass  # Si falla el guardado, no es crítico
    
    def get_distance_duration(self, origen, destino):
        """Obtiene distancia y duración, usando caché si existe"""
        # Intentar caché primero
        cached_dist, cached_dur = self.get_route_from_cache(origen, destino)
        if cached_dist and cached_dur:
            return cached_dist, cached_dur
        
        # Si no hay caché, llamar a la API
        try:
            result = self.gmaps.distance_matrix(origen, destino, mode="driving")
            distancia = result['rows'][0]['elements'][0]['distance']['value']
            duracion = result['rows'][0]['elements'][0]['duration']['value']
            
            # Guardar en caché para futuro
            self.save_route_to_cache(origen, destino, distancia, duracion)
            
            return distancia, duracion
        except:
            return None, None
    
    def build_distance_matrix(self, locations):
        """Construye matriz de distancias optimizada con caché"""
        n = len(locations)
        dist_matrix = [[0] * n for _ in range(n)]
        time_matrix = [[0] * n for _ in range(n)]
        
        # Preparar lista de pares que necesitan cálculo
        pairs_to_fetch = []
        for i in range(n):
            for j in range(i + 1, n):
                # Intentar caché
                dist, dur = self.get_route_from_cache(locations[i], locations[j])
                if dist and dur:
                    dist_matrix[i][j] = dist
                    dist_matrix[j][i] = dist
                    time_matrix[i][j] = dur
                    time_matrix[j][i] = dur
                else:
                    pairs_to_fetch.append((i, j))
        
        # Batch API call para los que faltan
        if pairs_to_fetch:
            # Dividir en chunks para evitar límites de API
            chunk_size = GOOGLE_MAPS_CHUNK_SIZE
            for chunk_start in range(0, len(pairs_to_fetch), chunk_size):
                chunk = pairs_to_fetch[chunk_start:chunk_start + chunk_size]
                
                origins = [locations[i] for i, j in chunk]
                destinations = [locations[j] for i, j in chunk]
                
                try:
                    result = self.gmaps.distance_matrix(origins, destinations, mode="driving")
                    
                    for idx, (i, j) in enumerate(chunk):
                        if idx < len(result['rows']):
                            element = result['rows'][idx]['elements'][0]
                            if element['status'] == 'OK':
                                dist = element['distance']['value']
                                dur = element['duration']['value']
                                
                                dist_matrix[i][j] = dist
                                dist_matrix[j][i] = dist
                                time_matrix[i][j] = dur
                                time_matrix[j][i] = dur
                                
                                # Guardar en caché
                                self.save_route_to_cache(locations[i], locations[j], dist, dur)
                except:
                    # Si falla el batch, intentar uno por uno
                    for i, j in chunk:
                        dist, dur = self.get_distance_duration(locations[i], locations[j])
                        if dist and dur:
                            dist_matrix[i][j] = dist
                            dist_matrix[j][i] = dist
                            time_matrix[i][j] = dur
                            time_matrix[j][i] = dur
        
        return dist_matrix, time_matrix
    
    def nearest_neighbor(self, time_matrix, duracion_visita_seg):
        """Algoritmo Nearest Neighbor para construir ruta inicial"""
        n = len(time_matrix)
        if n == 0:
            return [], 0
        
        unvisited = set(range(n))
        current = 0  # Empezar desde el primer punto
        route = [current]
        unvisited.remove(current)
        total_time = 0
        
        while unvisited:
            nearest = min(unvisited, key=lambda x: time_matrix[current][x])
            total_time += time_matrix[current][nearest] + duracion_visita_seg
            route.append(nearest)
            unvisited.remove(nearest)
            current = nearest
        
        # Añadir la última visita sin viaje de vuelta
        total_time += duracion_visita_seg
        
        return route, total_time
    
    def two_opt(self, route, time_matrix, duracion_visita_seg, max_iterations=100):
        """Mejora la ruta usando 2-opt con límite de iteraciones"""
        improved = True
        best_route = route[:]
        iterations = 0

        while improved and iterations < max_iterations:
            iterations += 1
            improved = False
            for i in range(1, len(route) - 1):
                for j in range(i + 1, len(route)):
                    # Intercambiar aristas
                    new_route = route[:i] + route[i:j][::-1] + route[j:]

                    # Calcular tiempo de la nueva ruta
                    new_time = self._calculate_route_time(new_route, time_matrix, duracion_visita_seg)
                    old_time = self._calculate_route_time(best_route, time_matrix, duracion_visita_seg)

                    if new_time < old_time:
                        best_route = new_route
                        improved = True

            route = best_route[:]

        return best_route
    
    def _calculate_route_time(self, route, time_matrix, duracion_visita_seg):
        """Calcula el tiempo total de una ruta"""
        total = 0
        for i in range(len(route) - 1):
            total += time_matrix[route[i]][route[i+1]]
        total += len(route) * duracion_visita_seg
        return total

    def _find_nearest(self, visita_base, visitas_candidatas):
        """
        Encuentra la visita más cercana a visita_base dentro de visitas_candidatas

        Args:
            visita_base: Visita de referencia
            visitas_candidatas: Lista de visitas entre las que buscar

        Returns:
            índice de la visita más cercana en visitas_candidatas
        """
        if not visitas_candidatas:
            return None

        mejor_idx = 0
        mejor_tiempo = float('inf')

        for idx, candidata in enumerate(visitas_candidatas):
            _, tiempo = self.get_distance_duration(
                visita_base['direccion_texto'],
                candidata['direccion_texto']
            )

            if tiempo and tiempo < mejor_tiempo:
                mejor_tiempo = tiempo
                mejor_idx = idx

        return mejor_idx
    
    def optimize_route(self, visitas, duracion_visita_seg=2700):
        """
        Optimiza una lista de visitas usando Nearest Neighbor + 2-opt

        Args:
            visitas: Lista de diccionarios con 'direccion_texto'
            duracion_visita_seg: Duración de cada visita en segundos (default 45min)

        Returns:
            (visitas_ordenadas, tiempo_total_seg)
        """
        if not visitas or len(visitas) <= 1:
            return visitas, len(visitas) * duracion_visita_seg

        # Extraer direcciones
        locations = [v['direccion_texto'] for v in visitas]

        # Construir matriz de tiempos con caché
        _, time_matrix = self.build_distance_matrix(locations)

        # Aplicar Nearest Neighbor
        route_indices, _ = self.nearest_neighbor(time_matrix, duracion_visita_seg)

        # Mejorar con 2-opt SOLO para rutas pequeñas/medianas
        # Para rutas grandes, Nearest Neighbor es suficiente y mucho más rápido
        if 3 < len(route_indices) <= LIMITE_VISITAS_2OPT:
            route_indices = self.two_opt(route_indices, time_matrix, duracion_visita_seg, max_iterations=MAX_ITERACIONES_2OPT)

        # Calcular tiempo total final
        total_time = self._calculate_route_time(route_indices, time_matrix, duracion_visita_seg)

        # Reordenar visitas según los índices
        optimized_visitas = [visitas[i] for i in route_indices]

        return optimized_visitas, total_time
    
    def optimize_multiday(self, visitas_disponibles, dias_disponibles, duracion_visita_seg=2700, tiempo_jornada_func=None):
        """
        Distribuye y optimiza visitas en múltiples días usando heurística greedy inteligente

        Args:
            visitas_disponibles: Lista de visitas
            dias_disponibles: Lista de fechas (date objects)
            duracion_visita_seg: Duración por visita
            tiempo_jornada_func: Función que recibe weekday y retorna segundos de jornada

        Returns:
            (plan_dict, visitas_no_asignadas)
            plan_dict: {fecha_iso: {'ruta': [visitas_optimizadas], 'tiempo_total': segundos}}
            visitas_no_asignadas: lista de visitas que no cupieron
        """
        if not tiempo_jornada_func:
            tiempo_jornada_func = lambda wd: 7*3600 if wd == 4 else 9*3600

        plan = {}
        visitas_restantes = visitas_disponibles[:]

        for dia in dias_disponibles:
            presupuesto = tiempo_jornada_func(dia.weekday())
            visitas_dia = []
            tiempo_acumulado = 0

            # ESTRATEGIA GREEDY: Añadir visitas una a una de forma inteligente
            while visitas_restantes:
                if not visitas_dia:
                    # Primera visita del día: tomar la primera disponible
                    candidata = visitas_restantes[0]
                    tiempo_nueva = duracion_visita_seg
                else:
                    # Buscar la visita más cercana a la última añadida
                    idx_cercana = self._find_nearest(visitas_dia[-1], visitas_restantes)
                    if idx_cercana is None:
                        break

                    candidata = visitas_restantes[idx_cercana]

                    # Calcular tiempo de viaje desde la última visita
                    _, tiempo_viaje = self.get_distance_duration(
                        visitas_dia[-1]['direccion_texto'],
                        candidata['direccion_texto']
                    )

                    tiempo_nueva = duracion_visita_seg + (tiempo_viaje if tiempo_viaje else 1800)

                # Verificar si cabe en el presupuesto
                if tiempo_acumulado + tiempo_nueva <= presupuesto:
                    visitas_dia.append(candidata)
                    visitas_restantes.remove(candidata)
                    tiempo_acumulado += tiempo_nueva
                else:
                    # No cabe más, pasar al siguiente día
                    break

            # Optimizar el día completo UNA SOLA VEZ al final (si tiene pocas visitas)
            if visitas_dia:
                if len(visitas_dia) <= LIMITE_VISITAS_2OPT:
                    # Para días pequeños, vale la pena optimizar
                    visitas_optimizadas, tiempo_final = self.optimize_route(visitas_dia, duracion_visita_seg)
                else:
                    # Para días grandes, usar el orden greedy (ya es bueno)
                    visitas_optimizadas = visitas_dia
                    tiempo_final = tiempo_acumulado

                plan[dia.isoformat()] = {
                    'ruta': visitas_optimizadas,
                    'tiempo_total': tiempo_final
                }

        return plan, visitas_restantes


# Función de utilidad para usar fácilmente
def optimizar_ruta_visitas(visitas, duracion_visita_seg=2700):
    """Función helper para optimizar una lista de visitas"""
    optimizer = RouteOptimizer()
    return optimizer.optimize_route(visitas, duracion_visita_seg)