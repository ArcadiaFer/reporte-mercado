"""
Estructura del universo de seguimiento y emparejamiento SIC <-> mercado de origen.

Un valor del SIC (por ejemplo VOO.MX) es la versión mexicana de un valor que se
negocia en EE. UU. (VOO). Tiene dos caras:

  - la de ORIGEN (VOO): precios en dólares y volumen real. Es la que se usa para
    calcular indicadores y correr el screening, porque sus datos son confiables.
  - la del SIC (VOO.MX): precios en pesos, lo que realmente pagarías en GBM+. Su
    volumen es mínimo y muchas sesiones cierran sin operaciones, así que sus
    indicadores no son confiables; se muestra solo como referencia de ejecución.

Este módulo une las dos caras y etiqueta cada métrica con su categoría. Lo usan
tanto el reporte Markdown como la página web, para que ambos coincidan.
"""

# Todas las categorías del watchlist: (clave, título). Sirve para saber qué descargar.
CATEGORIAS = [
    ("bmv", "Acciones BMV"),
    ("etf_sic", "ETFs de EE. UU. (vía SIC)"),
    ("accion_sic", "Acciones de EE. UU. (vía SIC)"),
    # La lista propia del usuario (config/seguimiento_eeuu.txt). No viene del JSON: la arma
    # seguimiento.py en cada corrida y la agrega al universo en memoria.
    ("lista_us", "Mi lista de EE. UU."),
    ("sector_us", "Sectores de EE. UU. (referencia)"),
    ("referencia", "Referencias de México"),
    ("indice_us", "Índices de EE. UU."),
]

# Las que se listan en las tablas. Los índices de EE. UU. (S&P, VIX, bono a 10 años)
# solo aparecen como tarjetas del panorama: no son algo que se compre.
CATEGORIAS_LISTADO = [c for c in CATEGORIAS if c[0] != "indice_us"]

# Qué categoría toma la cara de ORIGEN (EE. UU.) de cada categoría que trae pares SIC.
CATEGORIA_ORIGEN = {"etf_sic": "etf_us", "accion_sic": "accion_us", "lista_us": "lista_us"}

# En la lista propia la categoría es la misma para ambas caras del par, así que la cara
# SIC necesita un nombre distinto: las reglas técnicas corren sobre la de origen
# ("lista_us") y la de liquidez sobre la del SIC ("lista_sic"). En etf_sic y accion_sic
# no hace falta: ahí la clave del watchlist ya es la de la cara SIC.
CATEGORIA_SIC = {"lista_us": "lista_sic"}

# Categorías que entran a los "extremos del mes": una por instrumento invertible,
# sin sectores (son referencia) ni índices.
CATEGORIAS_EXTREMOS = {"bmv", "etf_sic", "etf_us", "accion_sic", "accion_us", "lista_us", "lista_sic"}

# Categorías cuyo precio es dinero (se muestra con su moneda). Las demás son
# niveles de índice o tipos de cambio, donde "USD" o "MXN" confundiría.
CATEGORIAS_CON_MONEDA = {"bmv", "etf_sic", "accion_sic", "etf_us", "accion_us", "sector_us",
                         "lista_us", "lista_sic"}


# ---------------------------------------------------------------------------
# Qué descargar
# ---------------------------------------------------------------------------

def tickers_del_universo(universo):
    """Todos los tickers a descargar: los de cada categoría más los de origen del SIC."""
    vistos, salida = set(), []
    for clave, _ in CATEGORIAS:
        for entrada in universo.get(clave, []):
            for t in (entrada["ticker"], entrada.get("origen")):
                if t and t not in vistos:
                    vistos.add(t)
                    salida.append(t)
    return salida


def con_origenes(universo, pedidos):
    """
    Si se pidió un subconjunto (--tickers VOO.MX), agrega el ticker de origen de cada
    valor del SIC pedido: sin él no habría datos confiables con qué analizarlo.
    """
    origen_de = {e["ticker"]: e["origen"]
                 for clave, _ in CATEGORIAS for e in universo.get(clave, []) if e.get("origen")}
    salida = []
    for t in pedidos:
        for candidato in (t, origen_de.get(t)):
            if candidato and candidato not in salida:
                salida.append(candidato)
    return salida


# ---------------------------------------------------------------------------
# Etiquetado de métricas
# ---------------------------------------------------------------------------

def fecha_dominante(metricas):
    """
    Fecha de último cierre más frecuente entre las series.

    El encabezado debe decir "datos al <fecha>" según lo que trae la mayoría, no según
    el máximo: un índice con la barra del día en curso (o el VIX operando de madrugada)
    adelantaría la fecha de todo el reporte aunque las acciones lleguen a la sesión anterior.
    """
    cuenta = {}
    for m in metricas.values():
        cuenta[m["ultima_fecha"]] = cuenta.get(m["ultima_fecha"], 0) + 1
    if not cuenta:
        return None
    # En empate gana la más reciente.
    return max(cuenta.items(), key=lambda par: (par[1], par[0]))[0]


def anotar(universo, metricas):
    """
    Etiqueta cada métrica (modifica `metricas` en sitio) con:
      categoria        a qué grupo pertenece
      nombre           el del watchlist (más legible que la razón social de Yahoo)
      tipo             'tasa' (rendimiento de un bono) o 'volatilidad' (VIX) si aplica
      sin_sic          True si es un valor de la lista propia que no se encontró en el SIC
      origen           (solo cara SIC) ticker de origen cuya serie está disponible
      sic_*            (solo cara de origen) ticker, precio y liquidez de su versión SIC
      fecha_distinta   su último cierre, si difiere del que trae la mayoría
    """
    # Primero las caras de origen y luego las entradas propias: si un mismo ticker
    # está en ambos lados, gana la categoría de su entrada propia.
    for clave, _ in CATEGORIAS:
        for e in universo.get(clave, []):
            origen = e.get("origen")
            if not origen or origen not in metricas:
                continue
            mo = metricas[origen]
            mo["categoria"] = CATEGORIA_ORIGEN.get(clave, clave)
            mo["nombre"] = e["nombre"]
            mo["sic_ticker"] = e["ticker"]
            ms = metricas.get(e["ticker"])
            if ms:
                mo["sic_precio"] = ms["precio"]
                mo["sic_moneda"] = ms["moneda"]
                mo["sic_liquidez"] = ms["liquidez"]
                ms["origen"] = origen

    for clave, _ in CATEGORIAS:
        for e in universo.get(clave, []):
            m = metricas.get(e["ticker"])
            if not m:
                continue
            # Una entrada con "origen" es la cara SIC de un par; su categoría puede ser otra
            # que la de la clave (ver CATEGORIA_SIC). Sin "origen" es una serie normal.
            m["categoria"] = CATEGORIA_SIC.get(clave, clave) if e.get("origen") else clave
            m["nombre"] = e["nombre"]
            m["tipo"] = e.get("tipo")
            m["sin_sic"] = bool(e.get("sin_sic"))

    dominante = fecha_dominante(metricas)
    for m in metricas.values():
        m["fecha_distinta"] = m["ultima_fecha"] if m["ultima_fecha"] != dominante else None


def principal(entrada, metricas):
    """
    Métricas con las que se muestra una entrada del watchlist: las de su ORIGEN si se
    descargaron (más confiables); si no, las propias. None si no hay ninguna.
    """
    origen = entrada.get("origen")
    if origen and origen in metricas:
        return metricas[origen]
    return metricas.get(entrada["ticker"])


def cara_de_origen(m, metricas):
    """
    Si `m` es la cotización SIC de un valor cuyo origen se descargó, devuelve las
    métricas del origen; si no, la misma `m`. Se usa para mostrar una alerta: aunque la
    regla se haya activado por el SIC (liquidez), los números a la vista deben ser los
    confiables, no los del precio local con cierres rancios.
    """
    origen = m.get("origen")
    return metricas[origen] if origen and origen in metricas else m


def representantes(metricas):
    """
    Una métrica por instrumento: la cara SIC de un valor cuyo origen sí se descargó
    se omite, porque ya está representada por su origen. Evita contar dos veces a VOO.
    """
    return [m for m in metricas.values() if not m.get("origen")]


def cotiza_con_moneda(m):
    """True si el precio de esta métrica es dinero y conviene mostrarlo con su moneda."""
    moneda = m.get("moneda")
    return m.get("categoria") in CATEGORIAS_CON_MONEDA and bool(moneda) and moneda != "?"


def es_neutro(m):
    """True para series donde subir no es 'bueno' ni 'malo' (VIX, tasas): sin verde/rojo."""
    return m.get("tipo") in ("tasa", "volatilidad")


def cambio_pb(nivel, variacion_pct):
    """
    Cambio en puntos base de una tasa, a partir de su nivel actual y de su variación
    porcentual (la que calculan los indicadores). 100 pb = 1 punto porcentual.
    Ejemplo: un bono de 4.99% que subió 0.6% en el día pasó de 4.96% a 4.99% = +3 pb.
    """
    if nivel is None or variacion_pct is None:
        return None
    previo = nivel / (1.0 + variacion_pct / 100.0)
    return (nivel - previo) * 100.0


def pb_txt(pb):
    """Puntos base como texto. Redondea antes de poner el signo para no mostrar '-0 pb'."""
    if pb is None:
        return "—"
    entero = round(pb)
    return f"{entero:+d} pb" if entero else "0 pb"
