# -*- coding: utf-8 -*-
# Fichero: setup.py

import sqlite3
import bcrypt
from database import inicializar_db, obtener_conexion

def crear_admin_interactivo():
    """
    Función interactiva para crear el primer usuario administrador.
    Pregunta al usuario por los datos en la terminal.
    """
    print("--- Configuración del Usuario Administrador ---")
    
    conn = obtener_conexion()
    cursor = conn.cursor()
    
    # Comprobamos si ya existe algún usuario
    cursor.execute("SELECT COUNT(id) FROM usuarios")
    if cursor.fetchone()[0] > 0:
        print("✅ Ya existen usuarios en la base de datos. No se creará un nuevo administrador.")
        conn.close()
        return

    print("Vamos a crear la cuenta de administrador principal.")
    print("Esta será la cuenta con todos los permisos.")
    
    nombre_completo = input("Introduce tu nombre completo: ")
    username = input("Introduce un nombre de usuario para el login (ej: admin): ")
    password = input("Introduce una contraseña segura: ")

    if not all([nombre_completo, username, password]):
        print("\n❌ Error: Todos los campos son obligatorios. Por favor, vuelve a ejecutar el script.")
        conn.close()
        return

    # Hashear la contraseña con bcrypt
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    # Insertar en la base de datos
    try:
        cursor.execute(
            "INSERT INTO usuarios (nombre_completo, username, password_hash, rol) VALUES (?, ?, ?, ?)",
            (nombre_completo, username, hashed_password, 'admin')
        )
        conn.commit()
        print(f"\n🎉 ¡Éxito! Usuario administrador '{username}' creado correctamente.")
    except sqlite3.IntegrityError:
        print(f"\n❌ Error: El usuario '{username}' ya existe.")
    finally:
        conn.close()

# --- Script Principal ---
if __name__ == "__main__":
    print("🚀 Iniciando configuración de la aplicación...")
    
    # 1. Crear las tablas de la base de datos
    print("\nPASO 1: Creando estructura de la base de datos...")
    inicializar_db()
    
    # 2. Crear el usuario administrador de forma interactiva
    print("\nPASO 2: Creando el usuario administrador...")
    crear_admin_interactivo()
    
    print("\n✅ Configuración finalizada. Ahora puedes importar el CSV y ejecutar la aplicación.")