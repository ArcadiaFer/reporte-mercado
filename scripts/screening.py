"""
Motor de screening por reglas.

Las reglas viven en config/watchlist.json y se evalúan contra el diccionario de
métricas que produce research.py. El motor es puramente determinístico: no hay
modelo de lenguaje decidiendo nada aquí, solo comparaciones sobre números.

Formato de una regla:

    {
      "id": "sobreventa",
      "descripcion": "RSI14 por debajo de 30",
      "severidad": "media",
      "logica": "y",
      "condiciones": [
        {"metrica": "rsi14", "op": "<", "valor": 30}
      ]
    }

`valor` puede ser un número o el nombre de otra métrica (comparación cruzada),
en cuyo caso se escribe como {"metrica": "precio", "op": ">", "ref": "sma200"}.
"""

OPERADORES = {
    "<":  lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">":  lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

SEVERIDADES = {"alta": "🔴", "media": "🟡", "baja": "🔵", "info": "⚪"}


# ---------------------------------------------------------------------------
# Evaluación
# ---------------------------------------------------------------------------

def _resolver_referencia(cond, metricas):
    """Devuelve (valor_comparacion, ok). ok=False si la referencia no existe."""
    if "ref" in cond:
        ref = metricas.get(cond["ref"])
        return ref, ref is not None
    return cond.get("valor"), cond.get("valor") is not None


def evaluar_condicion(cond, metricas):
    """
    Evalúa una condición contra las métricas de un instrumento.
    Devuelve True, False o None (métrica no disponible → no concluyente).
    """
    izq = metricas.get(cond.get("metrica"))
    if izq is None:
        return None

    op = OPERADORES.get(cond.get("op"))
    if op is None:
        return None

    der, ok = _resolver_referencia(cond, metricas)
    if not ok:
        return None

    # Las comparaciones de texto solo tienen sentido con == / !=
    if isinstance(izq, str) or isinstance(der, str):
        if cond.get("op") not in ("==", "!="):
            return None
        return op(str(izq), str(der))

    try:
        return op(float(izq), float(der))
    except (TypeError, ValueError):
        return None


def evaluar_regla(regla, metricas):
    """
    Aplica una regla completa. Devuelve True solo si la lógica se satisface con
    información suficiente; None si faltan métricas para concluir.
    """
    condiciones = regla.get("condiciones") or []
    if not condiciones:
        return None

    resultados = [evaluar_condicion(c, metricas) for c in condiciones]

    if any(r is None for r in resultados):
        # Con lógica "o" todavía se puede concluir positivo si alguna dio True.
        if regla.get("logica", "y") == "o" and any(r is True for r in resultados):
            return True
        return None

    if regla.get("logica", "y") == "o":
        return any(resultados)
    return all(resultados)


def correr_screening(reglas, metricas_por_ticker):
    """
    Evalúa todas las reglas contra todos los instrumentos.

    Devuelve dict {id_regla: {"regla": regla, "coincidencias": [ticker, ...]}}
    conservando el orden en que las reglas fueron definidas.
    """
    salida = {}
    for regla in reglas:
        coincidencias = [
            ticker
            for ticker, metricas in metricas_por_ticker.items()
            if evaluar_regla(regla, metricas) is True
        ]
        salida[regla.get("id", "sin_id")] = {
            "regla": regla,
            "coincidencias": coincidencias,
        }
    return salida


def icono_severidad(regla):
    return SEVERIDADES.get(regla.get("severidad", "info"), "⚪")
