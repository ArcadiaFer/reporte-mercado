"""
Descarga de datos de mercado, macro y noticias.
Stdlib-only: no requests/pandas required.

Fuentes:
  - Yahoo Finance chart API  -> precios históricos (BMV, SIC, FX, índices)
  - Yahoo Finance RSS        -> titulares por emisora
  - Expansión RSS            -> noticias generales de mercado
  - Banxico SIE API          -> macro (requiere token gratuito)

Todas las funciones fallan en suave: devuelven None o lista vacía y registran
el motivo en `ERRORES` en vez de lanzar excepción, para que un ticker caído no
tumbe el reporte completo.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

UA = {"User-Agent": "Mozilla/5.0 (compatible; gbm-research/1.0)"}
TIMEOUT = 20
PAUSA_ENTRE_LLAMADAS = 0.2  # segundos, para no saturar Yahoo
INTENTOS = 3                # intentos por descarga de precios ante fallos pasajeros
PAUSA_REINTENTO = 1.5       # segundos de espera antes de volver a intentar

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rango}&interval=1d"
YAHOO_NEWS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=MX&lang=es-MX"
EXPANSION_RSS = "https://expansion.mx/rss/mercados"
BANXICO_URL = "https://www.banxico.org.mx/SieAPIRest/service/v1/series/{ids}/datos/{rango}"

# Bitácora de fallos acumulados durante la corrida.
ERRORES = []


def _registrar_error(contexto, exc):
    ERRORES.append(f"{contexto}: {type(exc).__name__} — {exc}")


# ---------------------------------------------------------------------------
# HTTP + caché
# ---------------------------------------------------------------------------

def _get(url, headers=None):
    """GET simple. Devuelve bytes o lanza la excepción original."""
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _get_con_reintento(url):
    """
    GET que reintenta ante fallos pasajeros de red (Yahoo a veces corta la conexión sin
    responder; con ~70 descargas por corrida pasa de vez en cuando). Un error 4xx como
    404 (ticker inexistente) no se reintenta: esperar no lo arregla. El 429 (Yahoo pide
    ir más lento) sí, pero con la misma pausa de siempre.
    """
    for intento in range(1, INTENTOS + 1):
        try:
            return _get(url)
        except urllib.error.HTTPError as e:
            definitivo = 400 <= e.code < 500 and e.code != 429
            if definitivo or intento == INTENTOS:
                raise
        except Exception:
            if intento == INTENTOS:
                raise
        time.sleep(PAUSA_REINTENTO)


def _ruta_cache(cache_dir, clave):
    seguro = "".join(c if c.isalnum() or c in "-_." else "_" for c in clave)
    return Path(cache_dir) / f"{seguro}.json"


def _leer_cache(cache_dir, clave, ttl_min):
    """Devuelve el payload cacheado si sigue fresco, si no None."""
    if not cache_dir or ttl_min <= 0:
        return None
    ruta = _ruta_cache(cache_dir, clave)
    if not ruta.exists():
        return None
    try:
        edad_min = (time.time() - ruta.stat().st_mtime) / 60.0
        if edad_min > ttl_min:
            return None
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _escribir_cache(cache_dir, clave, payload):
    if not cache_dir:
        return
    try:
        ruta = _ruta_cache(cache_dir, clave)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        pass  # el caché es un lujo, nunca una dependencia dura


# ---------------------------------------------------------------------------
# Precios (Yahoo Finance)
# ---------------------------------------------------------------------------

def descargar_precios(ticker, rango="1y", cache_dir=None, ttl_min=60):
    """
    Descarga la serie diaria de un ticker.

    Devuelve dict con:
      ticker, nombre, moneda, bolsa, fechas (list[date ISO]),
      cierres (list[float]), volumenes (list[int|None])
    o None si falla.
    """
    clave = f"{ticker}_{rango}"
    crudo = _leer_cache(cache_dir, clave, ttl_min)

    if crudo is None:
        url = YAHOO_CHART.format(sym=urllib.parse.quote(ticker, safe=""), rango=rango)
        try:
            crudo = json.loads(_get_con_reintento(url))
            _escribir_cache(cache_dir, clave, crudo)
            time.sleep(PAUSA_ENTRE_LLAMADAS)
        except Exception as e:
            _registrar_error(f"precios {ticker}", e)
            return None

    try:
        res = crudo["chart"]["result"][0]
        meta = res.get("meta", {})
        marcas = res.get("timestamp") or []
        quote = res["indicators"]["quote"][0]
        cierres_crudos = quote.get("close") or []
        vols_crudos = quote.get("volume") or [None] * len(marcas)

        fechas, cierres, volumenes = [], [], []
        for i, ts in enumerate(marcas):
            if i >= len(cierres_crudos) or cierres_crudos[i] is None:
                continue
            fechas.append(datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat())
            cierres.append(float(cierres_crudos[i]))
            volumenes.append(vols_crudos[i] if i < len(vols_crudos) else None)

        if not cierres:
            _registrar_error(f"precios {ticker}", ValueError("serie vacía"))
            return None

        return {
            "ticker": ticker,
            "nombre": meta.get("longName") or meta.get("shortName") or ticker,
            "moneda": meta.get("currency", "?"),
            "bolsa": meta.get("fullExchangeName", "?"),
            "fechas": fechas,
            "cierres": cierres,
            "volumenes": volumenes,
        }
    except Exception as e:
        _registrar_error(f"parseo {ticker}", e)
        return None


def descargar_universo(tickers, rango="1y", cache_dir=None, ttl_min=60, verboso=True):
    """Descarga una lista de tickers. Devuelve dict {ticker: serie}."""
    datos = {}
    total = len(tickers)
    for i, t in enumerate(tickers, 1):
        if verboso:
            print(f"  [{i:>2}/{total}] {t:<16}", end="", flush=True)
        serie = descargar_precios(t, rango, cache_dir, ttl_min)
        if serie:
            datos[t] = serie
            if verboso:
                print(f"OK  {len(serie['cierres'])} cierres")
        elif verboso:
            print("FALLO")
    return datos


# ---------------------------------------------------------------------------
# Noticias (RSS)
# ---------------------------------------------------------------------------

def _parsear_rss(contenido, limite):
    """Extrae items de un feed RSS 2.0. Devuelve list[dict]."""
    raiz = ET.fromstring(contenido)
    canal = raiz.find("channel")
    if canal is None:
        return []
    items = []
    for item in canal.findall("item")[:limite]:
        titulo = item.findtext("title") or ""
        items.append({
            "titulo": titulo.strip(),
            "fecha": (item.findtext("pubDate") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
        })
    return items


def noticias_ticker(ticker, limite=4):
    """Titulares de Yahoo Finance para una emisora. Lista vacía si falla."""
    url = YAHOO_NEWS.format(sym=urllib.parse.quote(ticker, safe=""))
    try:
        items = _parsear_rss(_get(url), limite)
        time.sleep(PAUSA_ENTRE_LLAMADAS)
        return items
    except Exception as e:
        _registrar_error(f"noticias {ticker}", e)
        return []


def noticias_mercado(limite=12):
    """Noticias generales de mercado desde Expansión."""
    try:
        return _parsear_rss(_get(EXPANSION_RSS), limite)
    except Exception as e:
        _registrar_error("noticias mercado (Expansión)", e)
        return []


# ---------------------------------------------------------------------------
# Macro (Banxico SIE)
# ---------------------------------------------------------------------------

def macro_banxico(series_ids, token, rango="oportuno"):
    """
    Consulta series del SIE de Banxico.

    `series_ids` es una lista de IDs (ej. ["SF43718", "SF43783"]).
    El título de cada serie viene de la propia API, así que un ID equivocado
    se detecta solo. Devuelve list[dict] con id, titulo, fecha, valor.
    Sin token devuelve lista vacía.
    """
    if not token or not series_ids:
        return []

    url = BANXICO_URL.format(ids=",".join(series_ids), rango=rango)
    cabeceras = dict(UA)
    cabeceras["Bmx-Token"] = token

    try:
        payload = json.loads(_get(url, headers=cabeceras))
    except urllib.error.HTTPError as e:
        _registrar_error(f"Banxico HTTP {e.code}", e)
        return []
    except Exception as e:
        _registrar_error("Banxico", e)
        return []

    salida = []
    for serie in payload.get("bmx", {}).get("series", []):
        datos = serie.get("datos") or []
        ultimo = datos[-1] if datos else {}
        salida.append({
            "id": serie.get("idSerie", "?"),
            "titulo": serie.get("titulo", "?"),
            "fecha": ultimo.get("fecha", "—"),
            "valor": ultimo.get("dato", "—"),
        })
    return salida
