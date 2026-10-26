"""
Indicadores técnicos sobre series de precios de cierre.
Stdlib-only: no pandas/numpy required.

Todas las funciones reciben una lista de cierres ordenada de más antiguo a más
reciente y devuelven None cuando no hay suficientes datos para el cálculo.
"""

import math

DIAS_HABILES_ANIO = 252


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def limpiar(serie):
    """Elimina None de la serie preservando el orden."""
    return [x for x in serie if x is not None]


def _variaciones(serie):
    """Diferencias absolutas entre cierres consecutivos."""
    return [serie[i] - serie[i - 1] for i in range(1, len(serie))]


def _rendimientos_log(serie):
    """Rendimientos logarítmicos diarios. Ignora cierres <= 0."""
    out = []
    for i in range(1, len(serie)):
        prev, cur = serie[i - 1], serie[i]
        if prev > 0 and cur > 0:
            out.append(math.log(cur / prev))
    return out


# ---------------------------------------------------------------------------
# Tendencia
# ---------------------------------------------------------------------------

def sma(serie, n):
    """Media móvil simple de los últimos n periodos."""
    s = limpiar(serie)
    if len(s) < n:
        return None
    return sum(s[-n:]) / n


def ema(serie, n):
    """Media móvil exponencial. Semilla = SMA de los primeros n valores."""
    s = limpiar(serie)
    if len(s) < n:
        return None
    k = 2.0 / (n + 1)
    valor = sum(s[:n]) / n
    for precio in s[n:]:
        valor = precio * k + valor * (1 - k)
    return valor


def cruce_medias(serie, corta=50, larga=200):
    """
    Posición relativa de la media corta respecto de la larga.
    Devuelve 'alcista', 'bajista' o None si no hay historia suficiente.
    """
    mc, ml = sma(serie, corta), sma(serie, larga)
    if mc is None or ml is None:
        return None
    return "alcista" if mc > ml else "bajista"


# ---------------------------------------------------------------------------
# Momentum
# ---------------------------------------------------------------------------

def rsi(serie, n=14):
    """
    Índice de Fuerza Relativa con suavizado de Wilder.
    Escala 0-100: <30 se lee como sobreventa, >70 como sobrecompra.
    """
    s = limpiar(serie)
    if len(s) < n + 1:
        return None

    variaciones = _variaciones(s)
    ganancias = [max(d, 0.0) for d in variaciones]
    perdidas = [max(-d, 0.0) for d in variaciones]

    # Promedio simple sobre las primeras n variaciones como semilla.
    prom_gan = sum(ganancias[:n]) / n
    prom_per = sum(perdidas[:n]) / n

    # Suavizado de Wilder para el resto de la serie.
    for i in range(n, len(variaciones)):
        prom_gan = (prom_gan * (n - 1) + ganancias[i]) / n
        prom_per = (prom_per * (n - 1) + perdidas[i]) / n

    if prom_per == 0:
        return 100.0
    rs = prom_gan / prom_per
    return 100.0 - (100.0 / (1.0 + rs))


def retorno_pct(serie, n):
    """Rendimiento porcentual sobre los últimos n periodos."""
    s = limpiar(serie)
    if len(s) < n + 1 or s[-1 - n] == 0:
        return None
    return (s[-1] / s[-1 - n] - 1.0) * 100.0


def retorno_desde(serie, indice):
    """Rendimiento porcentual desde una posición absoluta de la serie."""
    s = limpiar(serie)
    if not s or indice < 0 or indice >= len(s) or s[indice] == 0:
        return None
    return (s[-1] / s[indice] - 1.0) * 100.0


# ---------------------------------------------------------------------------
# Riesgo
# ---------------------------------------------------------------------------

def volatilidad_anualizada(serie, ventana=None):
    """
    Desviación estándar de rendimientos log diarios, anualizada (252 días).
    Devuelve porcentaje. `ventana` limita el cálculo a los últimos N cierres.
    """
    s = limpiar(serie)
    if ventana:
        s = s[-ventana:]
    rends = _rendimientos_log(s)
    if len(rends) < 2:
        return None
    media = sum(rends) / len(rends)
    var = sum((r - media) ** 2 for r in rends) / (len(rends) - 1)
    return math.sqrt(var) * math.sqrt(DIAS_HABILES_ANIO) * 100.0


def max_drawdown(serie):
    """Caída máxima pico-a-valle de la serie, en porcentaje (valor negativo)."""
    s = limpiar(serie)
    if len(s) < 2:
        return None
    pico = s[0]
    peor = 0.0
    for precio in s:
        if precio > pico:
            pico = precio
        if pico > 0:
            caida = (precio / pico - 1.0) * 100.0
            if caida < peor:
                peor = caida
    return peor


def dist_desde_maximo(serie, ventana=None):
    """
    Distancia porcentual del último cierre respecto al máximo de la ventana.
    Valor negativo = el precio está por debajo de su máximo.
    """
    s = limpiar(serie)
    if ventana:
        s = s[-ventana:]
    if not s:
        return None
    maximo = max(s)
    if maximo == 0:
        return None
    return (s[-1] / maximo - 1.0) * 100.0


def dist_desde_minimo(serie, ventana=None):
    """Distancia porcentual del último cierre respecto al mínimo de la ventana."""
    s = limpiar(serie)
    if ventana:
        s = s[-ventana:]
    if not s:
        return None
    minimo = min(s)
    if minimo == 0:
        return None
    return (s[-1] / minimo - 1.0) * 100.0


# ---------------------------------------------------------------------------
# Calidad de datos / liquidez
# ---------------------------------------------------------------------------
#
# Los instrumentos del SIC (acciones y ETFs extranjeros listados en México)
# operan con volúmenes mucho menores que en su mercado de origen. Cuando una
# sesión cierra sin operaciones, el proveedor arrastra el cierre anterior: el
# precio se repite y aparece como un rendimiento de 0.00%. Eso deprime la
# volatilidad medida y rompe las correlaciones, así que conviene medirlo
# explícitamente en vez de confiar a ciegas en los indicadores.

UMBRAL_LIQUIDEZ_BAJA = 5.0     # % de sesiones inertes
UMBRAL_LIQUIDEZ_MUY_BAJA = 20.0


def pct_cierres_repetidos(serie, ventana=None):
    """% de sesiones cuyo cierre es idéntico al de la sesión previa."""
    s = limpiar(serie)
    if ventana:
        s = s[-ventana:]
    if len(s) < 2:
        return None
    repetidos = sum(1 for i in range(1, len(s)) if s[i] == s[i - 1])
    return repetidos / (len(s) - 1) * 100.0


def pct_sesiones_sin_volumen(volumenes, ventana=None):
    """
    % de sesiones con volumen cero o ausente.

    Devuelve None cuando la serie no trae volumen en NINGUNA sesión: eso no
    significa que el instrumento no opere, sino que el proveedor no publica
    volumen para ese tipo de activo (pares de divisas y varios índices). Sin
    esta distinción, USD/MXN — el mercado más líquido que existe — quedaría
    clasificado como ilíquido. En esos casos la clasificación recae solo en
    los cierres repetidos.
    """
    v = list(volumenes or [])
    if ventana:
        v = v[-ventana:]
    if not v:
        return None
    sin_volumen = sum(1 for x in v if not x)
    if sin_volumen == len(v):
        return None
    return sin_volumen / len(v) * 100.0


def clasificar_liquidez(pct_repetidos, pct_sin_volumen):
    """
    Etiqueta la confiabilidad de la serie: 'ok', 'baja' o 'muy_baja'.
    Se queda con el peor de los dos indicadores.
    """
    señales = [x for x in (pct_repetidos, pct_sin_volumen) if x is not None]
    if not señales:
        return None
    peor = max(señales)
    if peor >= UMBRAL_LIQUIDEZ_MUY_BAJA:
        return "muy_baja"
    if peor >= UMBRAL_LIQUIDEZ_BAJA:
        return "baja"
    return "ok"


# ---------------------------------------------------------------------------
# Relación entre activos
# ---------------------------------------------------------------------------

def correlacion(fechas_a, serie_a, fechas_b, serie_b):
    """
    Correlación de Pearson entre los rendimientos log diarios de dos series.

    La alineación es POR FECHA, no por posición: dos instrumentos pueden tener
    distinto número de sesiones (feriados de BMV vs SIC, suspensiones) y alinear
    por índice recorre una serie respecto de la otra, lo que anula la
    correlación medida. Se intersectan los calendarios y solo se comparan días
    en que ambos cotizaron.

    Devuelve None si quedan menos de 3 días en común.
    """
    mapa_b = {f: c for f, c in zip(fechas_b, serie_b) if c is not None}
    comunes = [(f, c) for f, c in zip(fechas_a, serie_a)
               if c is not None and f in mapa_b]
    if len(comunes) < 3:
        return None

    comunes.sort(key=lambda p: p[0])
    ca = [c for _, c in comunes]
    cb = [mapa_b[f] for f, _ in comunes]

    # Rendimientos calculados en paralelo para garantizar que ra[i] y rb[i]
    # correspondan siempre al mismo par de fechas.
    ra, rb = [], []
    for i in range(1, len(ca)):
        if ca[i - 1] > 0 and ca[i] > 0 and cb[i - 1] > 0 and cb[i] > 0:
            ra.append(math.log(ca[i] / ca[i - 1]))
            rb.append(math.log(cb[i] / cb[i - 1]))

    m = len(ra)
    if m < 2:
        return None

    media_a = sum(ra) / m
    media_b = sum(rb) / m
    cov = sum((ra[i] - media_a) * (rb[i] - media_b) for i in range(m))
    var_a = sum((x - media_a) ** 2 for x in ra)
    var_b = sum((x - media_b) ** 2 for x in rb)
    if var_a == 0 or var_b == 0:
        return None
    return cov / math.sqrt(var_a * var_b)
