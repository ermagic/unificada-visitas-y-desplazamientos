"""
Generador de Icono para Continuidades MAE Barcelona
Crea un archivo .ico con el mismo estilo del splash screen
"""

from PIL import Image, ImageDraw, ImageFont
import os


def crear_icono():
    """Crea el icono de la aplicación"""

    # Crear imagen de 256x256 (tamaño estándar para iconos)
    size = 256
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fondo con gradiente (simular gradiente con círculos concéntricos)
    colores_fondo = [
        (15, 23, 42),  # #0f172a - azul oscuro
        (30, 41, 59),  # #1e293b - azul medio
        (51, 65, 85),  # #334155 - azul grisáceo
    ]

    # Dibujar fondo con efecto de gradiente circular
    for i in range(len(colores_fondo)):
        radio = size - (i * 40)
        color = colores_fondo[i]
        draw.ellipse(
            [(size // 2 - radio // 2, size // 2 - radio // 2),
             (size // 2 + radio // 2, size // 2 + radio // 2)],
            fill=color
        )

    # Círculo base principal (fondo del icono)
    draw.ellipse([20, 20, 236, 236], fill=(15, 23, 42))

    # Borde azul brillante
    draw.ellipse([20, 20, 236, 236], outline=(59, 130, 246), width=4)

    # Nodos de red (representando fibra óptica) - más pequeños y centrados
    nodos = [
        (128, 70),  # arriba centro
        (180, 110),  # derecha arriba
        (180, 150),  # derecha abajo
        (128, 190),  # abajo centro
        (75, 150),  # izquierda abajo
        (75, 110),  # izquierda arriba
    ]

    # Líneas de conexión (hexágono)
    for i in range(len(nodos)):
        x1, y1 = nodos[i]
        x2, y2 = nodos[(i + 1) % len(nodos)]
        draw.line([(x1, y1), (x2, y2)], fill=(59, 130, 246), width=2)

    # Dibujar nodos
    for x, y in nodos:
        draw.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(30, 64, 175), outline=(96, 165, 250), width=2)

    # Nodo central grande
    draw.ellipse([118, 118, 138, 138], fill=(59, 130, 246), outline=(96, 165, 250), width=3)

    # Intentar cargar una fuente, si no, usar la default
    try:
        # Intentar con fuente del sistema
        font_letra = ImageFont.truetype("arial.ttf", 48)
        font_pequeña = ImageFont.truetype("arial.ttf", 20)
    except:
        try:
            font_letra = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
            font_pequeña = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except:
            font_letra = ImageFont.load_default()
            font_pequeña = ImageFont.load_default()

    # Texto "MAE" en el centro (simplificado para el icono)
    texto = "MAE"

    # Obtener el bbox del texto para centrarlo
    bbox = draw.textbbox((0, 0), texto, font=font_letra)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    posicion_x = (size - text_width) // 2
    posicion_y = (size - text_height) // 2 - 5

    # Sombra del texto
    draw.text((posicion_x + 2, posicion_y + 2), texto, font=font_letra, fill=(0, 0, 0, 180))

    # Texto principal
    draw.text((posicion_x, posicion_y), texto, font=font_letra, fill=(255, 255, 255))

    # Guardar en múltiples tamaños para el .ico
    icono_path = "continuidades_mae.ico"

    # Crear versiones en diferentes tamaños
    tamaños = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    imagenes = []

    for tamaño in tamaños:
        img_resize = img.resize(tamaño, Image.Resampling.LANCZOS)
        imagenes.append(img_resize)

    # Guardar como .ico con todos los tamaños
    imagenes[0].save(
        icono_path,
        format='ICO',
        sizes=tamaños,
        append_images=imagenes[1:]
    )

    print(f"✅ Icono creado exitosamente: {icono_path}")
    print(f"📁 Ubicación: {os.path.abspath(icono_path)}")

    # También guardar una versión PNG para previsualización
    img.save("continuidades_mae_preview.png", "PNG")
    print(f"🖼️  Preview PNG creado: continuidades_mae_preview.png")

    return icono_path


if __name__ == "__main__":
    try:
        crear_icono()
        print("\n✨ Para usar el icono en PyInstaller:")
        print(
            'pyinstaller --onefile --windowed --icon=continuidades_mae.ico --name="Continuidades MAE Barcelona" main.py')
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()









