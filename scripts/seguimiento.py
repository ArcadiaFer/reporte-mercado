"""
Lista propia de acciones y ETFs de EE. UU.

El usuario escribe, en config/seguimiento_eeuu.txt, los tickers de EE. UU. que quiere
seguir (un valor por línea, o varios separados por coma). En cada corrida este módulo:

  1. lee y valida el archivo (cualquier error de escritura se reporta, no tumba la corrida);
  2. descarga cada ticker y comprueba que exista en Yahoo Finance;
  3. busca su versión en el SIC (VOO -> VOO.MX) para saber si se puede comprar en GBM+;
  4. arma las entradas que research.py suma al universo, con la misma forma que las de
     config/watchlist.json, para que reciban el mismo análisis y las mismas reglas.

El archivo se puede editar desde el celular en github.com: al guardar, el flujo diario se
dispara solo (ver .github/workflows/reporte-diario.yml) y la página se actualiza.

SEGURIDAD: el archivo es texto libre, así que cada ticker pasa por una lista blanca de
caracteres antes de usarse en una URL, y los mensajes que de él salen se escapan al
mostrarse en la página (pagina_web.esc).
"""

import os
import re
from pathlib import Path

import fuentes

RUTA_RELATIVA = "config/seguimiento_eeuu.txt"

# Tope de valores: cada uno cuesta hasta dos descargas por corrida.
MAX_VALORES = 30

# Letras, números, punto y guion, de 1 a 10 caracteres (BRK-B, BF.B, NVDA). Sin ^, sin =:
# los índices y divisas no son valores que se compren.
PATRON_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")

PATRON_REPOSITORIO = re.compile(r"^[\w.\-]+/[\w.\-]+$")
PATRON_RAMA = re.compile(r"^[\w.\-/]+$")


# ---------------------------------------------------------------------------
# Lectura del archivo
# ---------------------------------------------------------------------------

def leer_lista(ruta):
    """
    Lee el archivo y devuelve (tickers, avisos).

    Formato: un ticker por línea o varios separados por coma o espacio; lo que sigue a
    "#" es comentario. Acepta minúsculas. Un archivo que no existe equivale a una lista
    vacía. Los renglones inválidos se omiten y se avisa cuál era y por qué.
    """
    try:
        # utf-8-sig tolera la marca que el Bloc de notas de Windows agrega al inicio.
        texto = Path(ruta).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return [], []
    except OSError as e:
        return [], [f"No se pudo leer tu lista: {e}"]

    tickers, avisos = [], []
    for numero, linea in enumerate(texto.splitlines(), 1):
        sin_comentario = linea.split("#", 1)[0]
        for crudo in re.split(r"[,\s]+", sin_comentario.strip()):
            t = crudo.strip().upper()
            if not t:
                continue
            if t.endswith(".MX"):
                avisos.append(f"Línea {numero}: «{t}» lleva .MX. Escribe el ticker de EE. UU. "
                              "(por ejemplo VOO); el del SIC se busca solo.")
            elif not PATRON_TICKER.match(t):
                avisos.append(f"Línea {numero}: «{crudo[:15]}» no parece un ticker válido y se omitió.")
            elif t not in tickers:
                tickers.append(t)

    if len(tickers) > MAX_VALORES:
        avisos.append(f"Tu lista tiene {len(tickers)} valores; solo se analizan los primeros "
                      f"{MAX_VALORES}.")
        tickers = tickers[:MAX_VALORES]
    return tickers, avisos


def variantes_sic(ticker):
    """
    Posibles nombres del mismo valor en el SIC según Yahoo. Los tickers con guion o punto
    cambian: BRK-B cotiza como BRKB.MX. Se prueba primero la forma sin símbolos.
    """
    sin_simbolos = ticker.replace("-", "").replace(".", "")
    candidatos = [f"{sin_simbolos}.MX"]
    if sin_simbolos != ticker:
        candidatos.append(f"{ticker}.MX")
    return candidatos


def enlace_edicion(entorno=None, ruta=RUTA_RELATIVA):
    """
    Enlace para editar la lista desde github.com, armado con las variables que GitHub
    Actions pone en cada corrida. Devuelve None fuera de Actions (en tu computadora no
    hay a dónde apuntar) o si las variables traen algo raro.
    """
    env = os.environ if entorno is None else entorno
    repositorio = env.get("GITHUB_REPOSITORY", "")
    rama = env.get("GITHUB_REF_NAME") or "main"
    if not PATRON_REPOSITORIO.match(repositorio):
        return None
    if not PATRON_RAMA.match(rama):
        rama = "main"
    return f"https://github.com/{repositorio}/edit/{rama}/{ruta}"


# ---------------------------------------------------------------------------
# Armado de las entradas
# ---------------------------------------------------------------------------

def _ubicaciones(universo, titulos):
    """{ticker: título de la sección} de todo lo que ya está en el watchlist, origen incluido."""
    donde = {}
    for clave, titulo in titulos:
        for e in universo.get(clave, []):
            donde.setdefault(e["ticker"], titulo)
            if e.get("origen"):
                donde.setdefault(e["origen"], titulo)
    return donde


def cargar(ruta, universo, titulos, rango, cache_dir, ttl_min, verboso=True):
    """
    Devuelve (entradas, series, avisos, pedidos):

      entradas  lista para universo["lista_us"], con la forma del watchlist:
                  con SIC:  {"ticker": "NVDA.MX", "nombre": ..., "origen": "NVDA"}
                  sin SIC:  {"ticker": "XYZ", "nombre": ..., "sin_sic": True}
      series    {ticker: serie} ya descargadas (origen y, si existe, SIC)
      avisos    mensajes para el usuario (typos, repetidos, no está en el SIC...)
      pedidos   tickers que se pidieron, para el conteo "N de M instrumentos"

    `titulos` es la lista (clave, título) de universo.CATEGORIAS, para poder decir en qué
    sección ya sigues un valor que repites.
    """
    tickers, avisos = leer_lista(ruta)
    ya_seguidos = _ubicaciones(universo, titulos)

    entradas, series, pedidos = [], {}, []
    for t in tickers:
        if t in ya_seguidos:
            avisos.append(f"{t}: ya lo sigues en «{ya_seguidos[t]}».")
            continue

        pedidos.append(t)
        serie = fuentes.descargar_precios(t, rango, cache_dir, ttl_min, silencioso=True)
        if not serie:
            avisos.append(f"{t}: no se encontró en Yahoo Finance. Revisa que esté bien escrito.")
            if verboso:
                print(f"  Mi lista: {t:<8} no encontrado")
            continue
        series[t] = serie

        sic = None
        for candidato in variantes_sic(t):
            serie_sic = fuentes.descargar_precios(candidato, rango, cache_dir, ttl_min, silencioso=True)
            if serie_sic:
                series[candidato] = serie_sic
                pedidos.append(candidato)
                sic = candidato
                break

        entrada = {"ticker": sic or t, "nombre": serie["nombre"]}
        if sic:
            entrada["origen"] = t
        else:
            entrada["sin_sic"] = True
        entradas.append(entrada)
        if verboso:
            print(f"  Mi lista: {t:<8} OK  SIC: {sic or 'no aparece'}")

    return entradas, series, avisos, pedidos
