"""
Test simple para diagnosticar el problema de supervisor.py
"""
import streamlit as st

st.write("# Test 1: Streamlit funciona ✓")

try:
    from route_optimizer import RouteOptimizer
    st.write("# Test 2: RouteOptimizer importado ✓")
except Exception as e:
    st.error(f"Error importando RouteOptimizer: {e}")
    st.stop()

try:
    from balancing_service import BalancingService
    from scoring_service import ScoringService
    from plan_manager import PlanManager
    from ui_components import UIComponents
    st.write("# Test 3: Todos los servicios importados ✓")
except Exception as e:
    st.error(f"Error importando servicios: {e}")
    st.stop()

try:
    if 'test_optimizer' not in st.session_state:
        st.session_state.test_optimizer = RouteOptimizer()
    st.write("# Test 4: RouteOptimizer instanciado ✓")
except Exception as e:
    st.error(f"Error creando RouteOptimizer: {e}")
    import traceback
    st.code(traceback.format_exc())
    st.stop()

st.success("✅ Todos los tests pasaron!")
st.write("El problema debe estar en la función mostrar_planificador_supervisor()")
