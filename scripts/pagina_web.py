"""
Página web del reporte, pensada para leerse en el iPhone (y el iPad).
Stdlib-only: no necesita ninguna librería.

Genera UN solo archivo HTML autocontenido (los estilos van adentro) que se publica
en GitHub Pages. No usa JavaScript salvo un aviso de 6 líneas que avisa si la página
lleva días sin actualizarse.

SEGURIDAD: los titulares de noticias y los nombres vienen de internet, así que todo
texto externo pasa por `esc()` (html.escape) y solo se aceptan enlaces http/https.
Sin eso, un titular con "<script>" se ejecutaría dentro de tu página.
"""

import html
from datetime import datetime, timedelta, timezone

# Ciudad de México no usa horario de verano desde 2022: es UTC-6 todo el año.
# Se fija a mano porque `zoneinfo` en Windows necesita instalar datos extra.
CDMX = timezone(timedelta(hours=-6))

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# Orden en que se muestran las alertas: primero las más graves.
ORDEN_SEVERIDAD = ["alta", "media", "baja", "info"]
ETIQUETA_SEVERIDAD = {"alta": "Alta", "media": "Media", "baja": "Baja", "info": "Info"}

# Días de antigüedad a partir de los cuales la página avisa que está vieja.
DIAS_MAX_ANTIGUEDAD = 4


# ---------------------------------------------------------------------------
# Formato (duplica a propósito los helpers de research.py para no importarlo
# desde aquí: research.py importa este módulo y se crearía un ciclo)
# ---------------------------------------------------------------------------

def esc(texto):
    """Escapa texto externo para meterlo de forma segura dentro del HTML."""
    return html.escape(str(texto), quote=True)


def num(v, decimales=2):
    return "—" if v is None else f"{v:,.{decimales}f}"


def pct(v, decimales=1):
    return "—" if v is None else f"{v:+.{decimales}f}%"


def pct_html(v, decimales=1):
    """Porcentaje con color según signo. El signo (+/-) va siempre en el texto,
    así no se depende solo del color para distinguir ganancia de pérdida."""
    if v is None:
        return "—"
    clase = "pos" if v > 0 else "neg" if v < 0 else ""
    return f'<span class="{clase}">{pct(v, decimales)}</span>'


def rsi_txt(v):
    if v is None:
        return "—"
    flecha = " ↓" if v < 30 else " ↑" if v > 70 else ""
    return f"{v:.0f}{flecha}"


def enlace_seguro(url):
    """Devuelve la URL solo si es http/https; si no, cadena vacía (descarta javascript:, data:, etc.)."""
    url = (url or "").strip()
    return url if url.lower().startswith(("https://", "http://")) else ""


def fecha_larga(dt):
    return f"{DIAS[dt.weekday()]} {dt.day} de {MESES[dt.month - 1]} de {dt.year}"


# ---------------------------------------------------------------------------
# Piezas reutilizables
# ---------------------------------------------------------------------------

def fila(m, celdas):
    """
    Una fila de instrumento: ticker + nombre a la izquierda, precio y cambio del
    día a la derecha, y debajo una cuadrícula de métricas.
    `celdas` es una lista de (etiqueta, html_del_valor).
    """
    tendencia = {
        "alcista": '<span class="pos" title="Tendencia alcista">▲</span>',
        "bajista": '<span class="neg" title="Tendencia bajista">▼</span>',
    }.get(m.get("tendencia"), "")

    texto_aviso = {"muy_baja": "liquidez muy baja", "baja": "liquidez baja"}.get(m.get("liquidez"))
    aviso = f'<span class="aviso">⚠ {texto_aviso}</span>' if texto_aviso else ""

    cuadricula = "".join(
        f"<div><dt>{esc(etiqueta)}</dt><dd>{valor}</dd></div>" for etiqueta, valor in celdas
    )
    return (
        '<li class="fila">'
        '<div class="cab">'
        f'<div class="id"><b>{esc(m["ticker"])}</b> {tendencia}'
        f'<span class="nombre">{esc(m["nombre"])}</span>{aviso}</div>'
        f'<div class="der"><span class="precio">{num(m["precio"])}</span>'
        f'<span class="dia">{pct_html(m["ret_1d"])} <small>1D</small></span></div>'
        "</div>"
        f'<dl class="met">{cuadricula}</dl>'
        "</li>"
    )


def bloque(titulo_html, filas_html, abierto=False, cuenta=None):
    """Sección plegable (<details>): se abre y cierra con un toque, sin JavaScript."""
    insignia = f'<span class="cuenta">{cuenta}</span>' if cuenta is not None else ""
    atributo = " open" if abierto else ""
    return (
        f'<details class="bloque"{atributo}>'
        f'<summary><span class="tit">{titulo_html}</span>{insignia}</summary>'
        f'<ul class="lista">{filas_html}</ul>'
        "</details>"
    )


def lista_noticias(items):
    salida = []
    for n in items:
        titulo = esc(n.get("titulo") or "(sin título)")
        url = enlace_seguro(n.get("link"))
        if url:
            salida.append(
                f'<li class="nota"><a href="{esc(url)}" target="_blank" '
                f'rel="noopener noreferrer">{titulo}</a></li>'
            )
        else:
            salida.append(f'<li class="nota">{titulo}</li>')
    return "".join(salida)


# ---------------------------------------------------------------------------
# Secciones
# ---------------------------------------------------------------------------

def seccion_panorama(metricas):
    faros = [("^MXX", "IPC (BMV)"), ("MXN=X", "USD/MXN"),
             ("VOO.MX", "S&P 500 vía VOO"), ("QQQ.MX", "Nasdaq 100 vía QQQ")]
    tarjetas = []
    for ticker, etiqueta in faros:
        m = metricas.get(ticker)
        if not m:
            continue
        tarjetas.append(
            '<div class="tarjeta">'
            f'<div class="etq-t">{esc(etiqueta)}</div>'
            f'<div class="nivel">{num(m["precio"])}</div>'
            f'<div class="delta">{pct_html(m["ret_1d"])} <small>1D</small> · '
            f'{pct_html(m["ret_ytd"])} <small>año</small></div>'
            "</div>"
        )
    if not tarjetas:
        return ""
    return f'<section><h2>Panorama</h2><div class="rejilla">{"".join(tarjetas)}</div></section>'


def seccion_alertas(resultados, metricas):
    con_aciertos = [b for b in resultados.values() if b["coincidencias"]]
    if not con_aciertos:
        return '<section><h2>Alertas</h2><p class="vacio">Ninguna regla se activó hoy.</p></section>'

    def prioridad(b):
        sev = b["regla"].get("severidad", "info")
        return ORDEN_SEVERIDAD.index(sev) if sev in ORDEN_SEVERIDAD else len(ORDEN_SEVERIDAD)

    # sorted() es estable: dentro de una misma severidad se conserva el orden del watchlist.
    bloques = []
    for b in sorted(con_aciertos, key=prioridad):
        regla = b["regla"]
        sev = regla.get("severidad", "info")
        if sev not in ETIQUETA_SEVERIDAD:
            sev = "info"
        filas = "".join(
            fila(metricas[t], [
                ("RSI", esc(rsi_txt(metricas[t]["rsi14"]))),
                ("1M", pct_html(metricas[t]["ret_1m"])),
                ("vs máx. 52s", pct_html(metricas[t]["dd_desde_max52"])),
                ("Vol. anual", f'{num(metricas[t]["vol_anual"], 1)}%'),
            ])
            for t in b["coincidencias"]
        )
        titulo = (f'<span class="etq {sev}">{ETIQUETA_SEVERIDAD[sev]}</span>'
                  f'{esc(regla.get("descripcion", regla.get("id", "")))}')
        bloques.append(bloque(titulo, filas, cuenta=len(b["coincidencias"])))
    return f'<section><h2>Alertas</h2>{"".join(bloques)}</section>'


def seccion_mercado(universo, categorias, metricas):
    bloques = []
    primero = True
    for clave, titulo in categorias:
        entradas = [e for e in universo.get(clave, []) if e["ticker"] in metricas]
        if not entradas:
            continue
        entradas.sort(key=lambda e: metricas[e["ticker"]]["ret_1m"] if metricas[e["ticker"]]["ret_1m"] is not None else -999,
                      reverse=True)
        filas = "".join(
            fila(metricas[e["ticker"]], [
                ("5D", pct_html(metricas[e["ticker"]]["ret_5d"])),
                ("1M", pct_html(metricas[e["ticker"]]["ret_1m"])),
                ("3M", pct_html(metricas[e["ticker"]]["ret_3m"])),
                ("Año", pct_html(metricas[e["ticker"]]["ret_ytd"])),
                ("12M", pct_html(metricas[e["ticker"]]["ret_1a"])),
                ("RSI", esc(rsi_txt(metricas[e["ticker"]]["rsi14"]))),
                ("Vol. anual", f'{num(metricas[e["ticker"]]["vol_anual"], 1)}%'),
                ("vs máx. 52s", pct_html(metricas[e["ticker"]]["dd_desde_max52"])),
            ])
            for e in entradas
        )
        bloques.append(bloque(esc(titulo), filas, abierto=primero, cuenta=len(entradas)))
        primero = False
    if not bloques:
        return ""
    nota = ('<p class="nota-pie">Ordenado por rendimiento del último mes. '
            "▲/▼ = tendencia (media de 50 vs 200 sesiones). ⚠ = datos poco confiables por baja liquidez.</p>")
    return f'<section><h2>Mercado</h2>{"".join(bloques)}{nota}</section>'


def seccion_extremos(metricas):
    elegibles = [m for t, m in metricas.items()
                 if m["ret_1m"] is not None and t not in ("MXN=X", "^MXX")]
    if len(elegibles) < 2:
        return ""
    ordenados = sorted(elegibles, key=lambda m: m["ret_1m"], reverse=True)
    # Con universos chicos se recorta para que nadie aparezca a la vez entre los mejores y los peores.
    k = min(5, len(ordenados) // 2)

    def filas(grupo):
        return "".join(
            fila(m, [("1M", pct_html(m["ret_1m"])), ("3M", pct_html(m["ret_3m"])),
                     ("RSI", esc(rsi_txt(m["rsi14"])))])
            for m in grupo
        )

    return (
        "<section><h2>Extremos del mes</h2>"
        + bloque("Los que más subieron", filas(ordenados[:k]), cuenta=k)
        + bloque("Los que más cayeron", filas(ordenados[-k:][::-1]), cuenta=k)
        + "</section>"
    )


def seccion_correlaciones(correlaciones):
    if not correlaciones:
        return ""
    filas = "".join(
        '<li class="fila"><div class="cab">'
        f'<div class="id"><b>{esc(t)}</b><span class="nombre">{esc(nombre)}</span></div>'
        f'<div class="der corr"><span>IPC <b>{"—" if r_ipc is None else f"{r_ipc:.2f}"}</b></span>'
        f'<span>S&amp;P <b>{"—" if r_spx is None else f"{r_spx:.2f}"}</b></span></div>'
        "</div></li>"
        for t, nombre, r_ipc, r_spx in correlaciones
    )
    nota = ('<p class="nota-pie">Correlación de rendimientos diarios del último año. '
            "Cerca de 1 = se mueve igual que el índice; cerca de 0 = aporta diversificación.</p>")
    return ("<section><h2>Correlación con los índices</h2>"
            + bloque("Ver tabla completa", filas, cuenta=len(correlaciones)) + nota + "</section>")


def seccion_macro(macro, hay_token):
    # Sin token no se muestra nada: no tiene caso publicar un aviso de configuración.
    if not hay_token or not macro:
        return ""
    filas = "".join(
        '<li class="fila"><div class="cab">'
        f'<div class="id"><b>{esc(s["titulo"])}</b><span class="nombre">{esc(s["id"])} · {esc(s["fecha"])}</span></div>'
        f'<div class="der"><span class="precio">{esc(s["valor"])}</span></div>'
        "</div></li>"
        for s in macro
    )
    return "<section><h2>Macro · Banxico</h2>" + bloque("Indicadores", filas, cuenta=len(macro)) + "</section>"


def seccion_noticias(noticias_ticker, noticias_mercado):
    partes = []
    if noticias_mercado:
        partes.append(bloque("Mercado (Expansión)", lista_noticias(noticias_mercado),
                             cuenta=len(noticias_mercado)))
    for ticker, items in noticias_ticker.items():
        if items:
            partes.append(bloque(esc(ticker), lista_noticias(items), cuenta=len(items)))
    if not partes:
        return ""
    return "<section><h2>Noticias</h2>" + "".join(partes) + "</section>"


def seccion_calidad(metricas):
    sospechosos = sorted(
        [m for m in metricas.values() if m.get("liquidez") in ("baja", "muy_baja")],
        key=lambda m: m["pct_sin_volumen"] or 0, reverse=True,
    )
    explicacion = (
        '<p class="nota-pie">Los instrumentos del SIC operan con mucho menos volumen que en su mercado '
        "de origen. Si una sesión cierra sin operaciones, el precio anterior se arrastra y el rendimiento "
        "aparece como 0%: eso subestima la volatilidad y distorsiona las correlaciones.</p>"
    )
    if not sospechosos:
        return ('<section><h2>Calidad de datos</h2><p class="vacio">Todas las series operaron con regularidad.</p>'
                + explicacion + "</section>")

    filas = "".join(
        '<li class="fila"><div class="cab">'
        f'<div class="id"><b>{esc(m["ticker"])}</b><span class="nombre">{esc(m["nombre"])}</span></div>'
        f'<div class="der"><span class="aviso">{"muy baja" if m["liquidez"] == "muy_baja" else "baja"}</span>'
        f'<span class="dia">{num(m["pct_repetidos"], 0)}% cierres repetidos</span></div>'
        "</div></li>"
        for m in sospechosos
    )
    return ("<section><h2>Calidad de datos</h2>"
            + bloque("Instrumentos poco confiables", filas, cuenta=len(sospechosos))
            + explicacion + "</section>")


# ---------------------------------------------------------------------------
# Estilos y script
# ---------------------------------------------------------------------------

ESTILOS = """
:root{
  color-scheme: light dark;
  --fondo:#f2f5f9; --tarjeta:#ffffff; --texto:#13202f; --suave:#586577; --linea:#dce2eb;
  --pos:#0a7a3d; --neg:#c0262c; --acento:#1b4f94;
  --sev-alta:#c0262c; --sev-media:#a85f00; --sev-baja:#1b4f94; --sev-info:#667386;
}
@media (prefers-color-scheme: dark){
  :root{
    --fondo:#0c1521; --tarjeta:#152131; --texto:#e7edf4; --suave:#98a7b8; --linea:#24344a;
    --pos:#4fd484; --neg:#ff8080; --acento:#82b6ff;
    --sev-alta:#ff8080; --sev-media:#f2b550; --sev-baja:#82b6ff; --sev-info:#98a7b8;
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--fondo); color:var(--texto);
  font:16px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  padding:max(14px,env(safe-area-inset-top)) max(16px,env(safe-area-inset-right))
          max(28px,env(safe-area-inset-bottom)) max(16px,env(safe-area-inset-left));
}
main{max-width:760px; margin:0 auto}
h1{font-size:28px; margin:6px 0 2px; letter-spacing:-.01em}
.sub{color:var(--suave); font-size:14px; margin:0 0 6px}
h2{font-size:13px; text-transform:uppercase; letter-spacing:.08em; color:var(--suave);
   margin:28px 4px 10px; font-weight:700}
a{color:var(--acento)}
small{color:var(--suave); font-size:11px}
.pos{color:var(--pos)} .neg{color:var(--neg)}
.aviso-global{background:var(--tarjeta); border:1px solid var(--sev-alta); color:var(--sev-alta);
   border-radius:12px; padding:12px 14px; margin:12px 0; font-weight:600}
.vacio{color:var(--suave); margin:4px}

.rejilla{display:grid; grid-template-columns:1fr 1fr; gap:10px}
.tarjeta{background:var(--tarjeta); border:1px solid var(--linea); border-radius:14px; padding:12px 14px}
.etq-t{font-size:13px; color:var(--suave)}
.nivel{font-size:22px; font-weight:700; margin:2px 0; font-variant-numeric:tabular-nums}
.delta{font-size:13px}

details.bloque{background:var(--tarjeta); border:1px solid var(--linea); border-radius:14px;
   margin:10px 0; overflow:hidden}
summary{display:flex; align-items:center; gap:10px; min-height:52px; padding:10px 16px;
   cursor:pointer; list-style:none; font-weight:600}
summary::-webkit-details-marker{display:none}
summary::after{content:"›"; color:var(--suave); font-size:22px; line-height:1; transition:transform .15s}
details[open]>summary::after{transform:rotate(90deg)}
.tit{flex:1; min-width:0}
.cuenta{font-size:13px; font-weight:700; background:var(--fondo); border-radius:999px; padding:2px 10px}
.etq{display:inline-block; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.05em;
   padding:1px 7px; border:1px solid currentColor; border-radius:6px; margin-right:8px; vertical-align:1px}
.etq.alta{color:var(--sev-alta)} .etq.media{color:var(--sev-media)}
.etq.baja{color:var(--sev-baja)} .etq.info{color:var(--sev-info)}

.lista{list-style:none; margin:0; padding:0}
.fila{padding:12px 16px; border-top:1px solid var(--linea)}
.cab{display:flex; justify-content:space-between; align-items:flex-start; gap:12px}
.id{min-width:0}
.nombre{display:block; color:var(--suave); font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.aviso{display:block; font-size:12px; color:var(--sev-media); font-weight:600}
.der{text-align:right; flex-shrink:0; font-variant-numeric:tabular-nums}
.precio{display:block; font-weight:700}
.dia{display:block; font-size:13px}
.corr span{display:block; font-size:14px}
.met{display:grid; grid-template-columns:repeat(4,1fr); gap:8px 10px; margin:10px 0 0}
.met div{min-width:0}
dt{font-size:11px; color:var(--suave); text-transform:uppercase; letter-spacing:.04em}
dd{margin:0; font-weight:600; font-size:14px; font-variant-numeric:tabular-nums}
.nota{padding:12px 16px; border-top:1px solid var(--linea); font-size:15px}
.nota a{text-decoration:none}
.nota-pie{color:var(--suave); font-size:13px; margin:8px 6px 0}
footer{margin-top:32px; color:var(--suave); font-size:12px}
footer p{margin:8px 0}

@media (min-width:700px){
  .rejilla{grid-template-columns:repeat(4,1fr)}
  .met{grid-template-columns:repeat(8,1fr)}
}
"""

# Si el proceso diario deja de correr, la página se queda congelada con datos viejos y
# nada lo avisaría. Este script compara la fecha de generación contra hoy y, si pasaron
# más de DIAS_MAX_ANTIGUEDAD días, muestra un aviso rojo arriba.
SCRIPT_ANTIGUEDAD = """
(function(){
  try {
    var gen = new Date(document.documentElement.getAttribute('data-generado'));
    var dias = (Date.now() - gen.getTime()) / 86400000;
    if (dias > %d) {
      var b = document.getElementById('viejo');
      b.hidden = false;
      b.textContent = 'Este reporte tiene ' + Math.floor(dias) + ' días de antigüedad. Revisa que la tarea diaria siga funcionando.';
    }
  } catch (e) {}
})();
""" % DIAS_MAX_ANTIGUEDAD


# ---------------------------------------------------------------------------
# Página completa
# ---------------------------------------------------------------------------

def construir_pagina(universo, categorias, metricas, resultados, correlaciones, macro, hay_token,
                     noticias_ticker, noticias_mercado, solicitados, errores, rango):
    ahora = datetime.now(CDMX)

    ultima = max((m["ultima_fecha"] for m in metricas.values()), default=None)
    datos_al = "—"
    if ultima:
        d = datetime.strptime(ultima, "%Y-%m-%d")
        datos_al = f"{d.day} {MESES[d.month - 1][:3]} {d.year}"

    incidencias = ""
    if errores:
        filas_error = "".join(f'<li class="nota">{esc(e)}</li>' for e in errores[:10])
        incidencias = bloque("Incidencias de la corrida", filas_error, cuenta=len(errores))

    cuerpo = "".join([
        seccion_panorama(metricas),
        seccion_alertas(resultados, metricas),
        seccion_mercado(universo, categorias, metricas),
        seccion_extremos(metricas),
        seccion_correlaciones(correlaciones),
        seccion_macro(macro, hay_token),
        seccion_noticias(noticias_ticker, noticias_mercado),
        seccion_calidad(metricas),
    ])

    pie = (
        "<footer>"
        f"<p>{len(metricas)} de {solicitados} instrumentos · ventana de {esc(rango)} · "
        f"{len(errores)} incidencias</p>"
        f"{incidencias}"
        "<p><b>Alcance.</b> Este reporte describe lo que hicieron los precios y qué reglas técnicas "
        "se activaron. No es una recomendación de compra o venta ni asesoría de inversión: las "
        "decisiones de operación son tuyas.</p>"
        "<p><b>Fuentes.</b> Precios y titulares por emisora: Yahoo Finance. Noticias de mercado: "
        "Expansión. Macro: Banxico SIE. Los precios pueden traer retraso y no sustituyen la "
        "información oficial de tu casa de bolsa.</p>"
        "</footer>"
    )

    return (
        "<!doctype html>\n"
        f'<html lang="es" data-generado="{esc(ahora.isoformat(timespec="seconds"))}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<meta name="robots" content="noindex, nofollow">\n'
        '<meta name="theme-color" content="#f2f5f9" media="(prefers-color-scheme: light)">\n'
        '<meta name="theme-color" content="#0c1521" media="(prefers-color-scheme: dark)">\n'
        '<meta name="apple-mobile-web-app-capable" content="yes">\n'
        '<meta name="mobile-web-app-capable" content="yes">\n'
        '<meta name="apple-mobile-web-app-title" content="Mercado">\n'
        '<link rel="apple-touch-icon" href="icono-180.png">\n'
        '<link rel="manifest" href="manifest.webmanifest">\n'
        "<title>Mercado GBM</title>\n"
        f"<style>{ESTILOS}</style>\n"
        "</head>\n"
        "<body>\n<main>\n"
        "<h1>Mercado GBM</h1>\n"
        f'<p class="sub">{esc(fecha_larga(ahora))} · generado {ahora.strftime("%H:%M")} (CDMX) · '
        f"datos al {esc(datos_al)}</p>\n"
        '<div id="viejo" class="aviso-global" hidden></div>\n'
        f"{cuerpo}\n"
        f"{pie}\n"
        "</main>\n"
        f"<script>{SCRIPT_ANTIGUEDAD}</script>\n"
        "</body>\n</html>\n"
    )
