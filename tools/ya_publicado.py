"""
¿Ya hay una página de hoy?  Lo usa el respaldo del flujo diario.

Lee la marca `data-generado` que pagina_web.py escribe dentro de docs/index.html y dice
"si" cuando la página se generó HOY (hora de Ciudad de México) a partir de la hora de
corte. Con eso, la corrida de respaldo de las 6:47 sabe si la principal de las 6:07 ya
cumplió y puede saltarse el trabajo.

Ante cualquier duda (archivo ausente, marca ilegible, sin zona horaria, fecha del futuro)
dice "no": es preferible generar una página de más que dejar al usuario sin la de hoy.

Uso:
    python tools/ya_publicado.py [ruta_html] [hora_de_corte]
Imprime "si" o "no".
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ciudad de México no usa horario de verano desde 2022: es UTC-6 todo el año.
CDMX = timezone(timedelta(hours=-6))

# Una página generada antes de esta hora (por ejemplo, la de anoche) no cuenta como "la de hoy":
# todavía no trae los cierres de la sesión anterior de EE. UU. y México.
HORA_CORTE = 6


def fecha_generacion(ruta):
    """Fecha y hora (con zona horaria) en que se generó la página, o None si no se puede leer."""
    try:
        contenido = Path(ruta).read_text(encoding="utf-8")
    except OSError:
        return None
    marca = re.search(r'data-generado="([^"]+)"', contenido)
    if not marca:
        return None
    try:
        fecha = datetime.fromisoformat(marca.group(1))
    except ValueError:
        return None
    # Sin zona horaria no se puede comparar con certeza contra "hoy en CDMX".
    return fecha if fecha.tzinfo else None


def ya_publicado(ruta, ahora=None, hora_corte=HORA_CORTE):
    """True si la página se generó hoy (hora de CDMX) desde `hora_corte` hasta ahora."""
    ahora = (ahora or datetime.now(CDMX)).astimezone(CDMX)
    generado = fecha_generacion(ruta)
    if generado is None:
        return False
    corte = ahora.replace(hour=hora_corte, minute=0, second=0, microsecond=0)
    # "<= ahora" descarta marcas del futuro, que solo pasan si un reloj anda mal.
    return corte <= generado.astimezone(CDMX) <= ahora


def main():
    ruta = sys.argv[1] if len(sys.argv) > 1 else "docs/index.html"
    try:
        hora_corte = int(sys.argv[2]) if len(sys.argv) > 2 else HORA_CORTE
    except ValueError:
        hora_corte = HORA_CORTE
    print("si" if ya_publicado(ruta, hora_corte=hora_corte) else "no")


if __name__ == "__main__":
    main()
