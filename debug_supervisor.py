"""
Debug script para encontrar exactamente dónde falla supervisor.py
"""
import streamlit as st
import sys
import traceback

st.title("🔍 Debug de Supervisor.py")

# Test 1: Imports básicos
try:
    st.write("### Test 1: Imports básicos")
    import pandas as pd
    from datetime import date, timedelta
    import smtplib
    from email.mime.text import MIMEText
    st.success("✓ Imports básicos OK")
except Exception as e:
    st.error(f"✗ Error en imports básicos: {e}")
    st.code(traceback.format_exc())
    st.stop()

# Test 2: Import database
try:
    st.write("### Test 2: Database")
    from database import supabase
    st.success("✓ Database OK")
except Exception as e:
    st.error(f"✗ Error importando database: {e}")
    st.code(traceback.format_exc())
    st.stop()

# Test 3: Import config
try:
    st.write("### Test 3: Config")
    from config import get_daily_time_budget, DURACION_VISITA_SEGUNDOS, PUNTO_INICIO_MARTIN, MIN_VISITAS_AUTO_ASIGNAR
    st.success(f"✓ Config OK - DURACION_VISITA_SEGUNDOS={DURACION_VISITA_SEGUNDOS}")
except Exception as e:
    st.error(f"✗ Error importando config: {e}")
    st.code(traceback.format_exc())
    st.stop()

# Test 4: Import route_optimizer
try:
    st.write("### Test 4: RouteOptimizer")
    from route_optimizer import RouteOptimizer
    st.success("✓ RouteOptimizer importado")
except Exception as e:
    st.error(f"✗ Error importando RouteOptimizer: {e}")
    st.code(traceback.format_exc())
    st.stop()

# Test 5: Import otros servicios
try:
    st.write("### Test 5: Otros servicios")
    from balancing_service import BalancingService
    from scoring_service import ScoringService
    from plan_manager import PlanManager
    from ui_components import UIComponents
    st.success("✓ Todos los servicios importados")
except Exception as e:
    st.error(f"✗ Error importando servicios: {e}")
    st.code(traceback.format_exc())
    st.stop()

# Test 6: Crear instancia de RouteOptimizer
try:
    st.write("### Test 6: Instanciar RouteOptimizer")
    if 'debug_optimizer' not in st.session_state:
        st.session_state.debug_optimizer = RouteOptimizer()
    st.success("✓ RouteOptimizer instanciado")
except Exception as e:
    st.error(f"✗ Error creando RouteOptimizer: {e}")
    st.code(traceback.format_exc())
    st.info("💡 Este error sugiere que falta configurar secrets en Streamlit Cloud")
    st.info("Ve a: Settings → Secrets y asegúrate de que está configurado google.api_key")
    st.stop()

# Test 7: Crear todos los servicios
try:
    st.write("### Test 7: Crear todos los servicios")
    if 'debug_services' not in st.session_state:
        optimizer = st.session_state.debug_optimizer
        st.session_state.debug_services = {
            'optimizer': optimizer,
            'balancer': BalancingService(optimizer),
            'scorer': ScoringService(optimizer),
            'manager': PlanManager(optimizer),
            'ui': UIComponents()
        }
    st.success("✓ Todos los servicios creados")
except Exception as e:
    st.error(f"✗ Error creando servicios: {e}")
    st.code(traceback.format_exc())
    st.stop()

# Test 8: Importar supervisor completo
try:
    st.write("### Test 8: Importar supervisor.py")
    # No importar, solo verificar que existe
    import os
    if os.path.exists("supervisor.py"):
        st.success("✓ supervisor.py existe")
        with open("supervisor.py", "r", encoding="utf-8") as f:
            lines = f.readlines()
            st.info(f"Archivo tiene {len(lines)} líneas")
            st.info(f"Última línea: {lines[-1].strip()}")
    else:
        st.error("✗ supervisor.py NO existe")
except Exception as e:
    st.error(f"✗ Error verificando supervisor.py: {e}")
    st.code(traceback.format_exc())

st.success("🎉 Todos los tests pasaron!")
st.info("Si llegaste aquí, el problema NO es con los imports o la inicialización.")
st.info("El problema podría ser que la función mostrar_planificador_supervisor() no se ejecuta.")
