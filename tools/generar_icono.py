"""Genera los iconos de la página (docs/icono-*.png): una línea de precios al alza sobre fondo azul.

Solo usa la biblioteca estándar de Python (el PNG se escribe a mano, igual que en lector-pwa).
Uso (desde la carpeta gbm-research):  python tools/generar_icono.py
"""
import math
import struct
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "docs"

# Puntos de la línea de precios, en coordenadas 0-1 (v crece hacia abajo).
PUNTOS = [(0.16, 0.70), (0.36, 0.50), (0.52, 0.61), (0.84, 0.25)]
GROSOR = 0.045      # medio grosor de la línea
RADIO_PUNTO = 0.062  # radio de los puntos marcadores


# ---------------------------------------------------------------- PNG a mano

def escribir_png(ruta, ancho, alto, color_en):
    """Escribe un PNG RGB. `color_en(x, y)` devuelve (r, g, b) para cada píxel."""
    filas = bytearray()
    for y in range(alto):
        filas.append(0)  # cada fila empieza con su byte de filtro: 0 = sin filtro
        for x in range(ancho):
            filas += bytes(color_en(x, y))

    def trozo(tipo, datos):
        crc = zlib.crc32(tipo + datos) & 0xFFFFFFFF
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", crc)

    cabecera = struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)  # 8 bits, color RGB
    Path(ruta).write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", cabecera)
        + trozo(b"IDAT", zlib.compress(bytes(filas), 9))
        + trozo(b"IEND", b"")
    )


# ---------------------------------------------------------------- dibujo

def mezclar(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def distancia_a_segmento(px, py, ax, ay, bx, by):
    """Distancia del punto (px, py) al segmento A-B."""
    dx, dy = bx - ax, by - ay
    largo2 = dx * dx + dy * dy
    t = 0.0 if largo2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / largo2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def color_icono(u, v):
    """Color del icono en el punto (u, v), con u y v entre 0 y 1."""
    color = mezclar((24, 44, 72), (10, 20, 36), v)  # fondo: degradado vertical

    for linea in (0.35, 0.55, 0.75):  # rejilla tenue
        if abs(v - linea) < 0.004 and 0.10 <= u <= 0.90:
            color = mezclar(color, (120, 140, 170), 0.25)

    d = min(distancia_a_segmento(u, v, *PUNTOS[i], *PUNTOS[i + 1]) for i in range(len(PUNTOS) - 1))
    if d <= GROSOR:
        color = (79, 212, 132)  # la línea, en verde

    for (pu, pv) in PUNTOS:  # puntos marcadores encima de la línea
        if math.hypot(u - pu, v - pv) <= RADIO_PUNTO:
            color = (232, 237, 244)
            if math.hypot(u - pu, v - pv) <= RADIO_PUNTO * 0.5:
                color = (79, 212, 132)
    return color


def dibujar_icono(ruta, lado, muestras):
    """`muestras` = puntos por lado y por píxel: más muestras, bordes más suaves (y más lento)."""
    def color_en(x, y):
        suma = [0, 0, 0]
        for sy in range(muestras):
            for sx in range(muestras):
                c = color_icono((x + (sx + 0.5) / muestras) / lado, (y + (sy + 0.5) / muestras) / lado)
                for i in range(3):
                    suma[i] += c[i]
        return tuple(s // (muestras * muestras) for s in suma)

    escribir_png(ruta, lado, lado, color_en)


def main():
    DESTINO.mkdir(exist_ok=True)
    dibujar_icono(DESTINO / "icono-180.png", 180, 3)  # el tamaño que usa iOS en la pantalla de inicio
    dibujar_icono(DESTINO / "icono-192.png", 192, 3)
    dibujar_icono(DESTINO / "icono-512.png", 512, 2)
    print("Iconos escritos en", DESTINO)


if __name__ == "__main__":
    main()
