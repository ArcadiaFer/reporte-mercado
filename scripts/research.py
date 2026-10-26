"""
Agente de research de mercado — universo GBM (BMV + SIC + macro).
Stdlib-only: no pandas/numpy required.

Orquesta: descarga de precios -> cálculo de indicadores -> screening por reglas
-> noticias de los instrumentos con alertas -> reporte Markdown.

Uso:
    python scripts/research.py
    python scripts/research.py --rango 5y --sin-noticias
    python scripts/research.py --tickers WALMEX.MX,VOO.MX --ttl 0
    python scripts/research.py --token-banxico <TOKEN>
    python scripts/research.py --web docs/index.html     # además genera la página para celular
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fuentes
import indicadores as ind
import pagina_web
import screening as scr

RAIZ = Path(__file__).resolve().parent.parent

# Ventanas en sesiones bursátiles (aproximación estándar del mercado).
VENTANAS = {
    "ret_1d": 1,
    "ret_5d": 5,
    "ret_1m": 21,
    "ret_3m": 63,
    "ret_6m": 126,
    "ret_1a": 252,
}
VENTANA_52S = 252

CATEGORIAS = [
    ("bmv", "Acciones BMV"),
    ("etf_sic", "ETFs del SIC"),
    ("accion_sic", "Acciones internacionales (SIC)"),
    ("referencia", "Referencias de mercado"),
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Research de mercado — universo GBM")
    p.add_argument("--config", default=str(RAIZ / "config" / "watchlist.json"),
                   help="Ruta al watchlist JSON")
    p.add_argument("--rango", default="2y",
                   help="Rango histórico de Yahoo (1y, 2y, 5y, max). Default: 2y")
    p.add_argument("--salida", default=None,
                   help="Ruta del reporte. Default: reports/research_<fecha>.md")
    p.add_argument("--tickers", default=None,
                   help="Lista separada por comas para correr un subconjunto")
    p.add_argument("--ttl", type=int, default=60,
                   help="Minutos de vida del caché de precios. 0 = sin caché")
    p.add_argument("--web", default=None,
                   help="Además del Markdown, genera la página HTML para celular en esta ruta "
                        "(ej. docs/index.html)")
    p.add_argument("--sin-noticias", action="store_true",
                   help="Omite la descarga de titulares (corre más rápido)")
    p.add_argument("--max-noticias", type=int, default=6,
                   help="Máximo de emisoras con alerta a las que se les baja noticias")
    p.add_argument("--token-banxico", default=os.environ.get("BANXICO_TOKEN"),
                   help="Token del SIE. También se lee de la variable BANXICO_TOKEN")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

def indice_inicio_anio(fechas):
    """Posición del último cierre del año anterior, para calcular el YTD."""
    anio_actual = datetime.now().year
    for i in range(len(fechas) - 1, -1, -1):
        if int(fechas[i][:4]) < anio_actual:
            return i
    return None


def calcular_metricas(serie):
    """Convierte una serie de precios en el diccionario de métricas del screening."""
    cierres = serie["cierres"]
    m = {
        "ticker": serie["ticker"],
        "nombre": serie["nombre"],
        "moneda": serie["moneda"],
        "precio": cierres[-1],
        "n_cierres": len(cierres),
        "ultima_fecha": serie["fechas"][-1],
    }

    for clave, n in VENTANAS.items():
        m[clave] = ind.retorno_pct(cierres, n)

    idx_ytd = indice_inicio_anio(serie["fechas"])
    m["ret_ytd"] = ind.retorno_desde(cierres, idx_ytd) if idx_ytd is not None else None

    m["rsi14"] = ind.rsi(cierres, 14)
    m["sma50"] = ind.sma(cierres, 50)
    m["sma200"] = ind.sma(cierres, 200)
    m["tendencia"] = ind.cruce_medias(cierres, 50, 200)
    m["vol_anual"] = ind.volatilidad_anualizada(cierres, ventana=VENTANA_52S)
    m["dd_desde_max52"] = ind.dist_desde_maximo(cierres, ventana=VENTANA_52S)
    m["drawdown_max"] = ind.max_drawdown(cierres)

    m["pct_repetidos"] = ind.pct_cierres_repetidos(cierres, VENTANA_52S)
    m["pct_sin_volumen"] = ind.pct_sesiones_sin_volumen(serie["volumenes"], VENTANA_52S)
    m["liquidez"] = ind.clasificar_liquidez(m["pct_repetidos"], m["pct_sin_volumen"])
    return m


# ---------------------------------------------------------------------------
# Formato
# ---------------------------------------------------------------------------

def pct(v, decimales=1):
    if v is None:
        return "—"
    return f"{v:+.{decimales}f}%"


def num(v, decimales=2):
    if v is None:
        return "—"
    return f"{v:,.{decimales}f}"


def rsi_txt(v):
    if v is None:
        return "—"
    etiqueta = ""
    if v < 30:
        etiqueta = " ↓"
    elif v > 70:
        etiqueta = " ↑"
    return f"{v:.0f}{etiqueta}"


def marca_liquidez(m):
    """Sufijo de advertencia para instrumentos con datos poco confiables."""
    return {"muy_baja": " ⚠⚠", "baja": " ⚠"}.get(m.get("liquidez"), "")


# ---------------------------------------------------------------------------
# Secciones del reporte
# ---------------------------------------------------------------------------

def seccion_panorama(metricas, lineas):
    lineas.append("## 1. Panorama\n")
    faros = [
        ("^MXX", "IPC (BMV)"),
        ("MXN=X", "USD/MXN"),
        ("VOO.MX", "S&P 500 vía VOO"),
        ("QQQ.MX", "Nasdaq 100 vía QQQ"),
    ]
    presentes = [(t, etq) for t, etq in faros if t in metricas]
    if not presentes:
        lineas.append("_Sin referencias de mercado en el universo cargado._\n")
        return

    lineas.append("| Referencia | Nivel | 1D | 1M | YTD | 1A |")
    lineas.append("|---|---:|---:|---:|---:|---:|")
    for t, etq in presentes:
        m = metricas[t]
        lineas.append(
            f"| {etq} | {num(m['precio'])} | {pct(m['ret_1d'])} | {pct(m['ret_1m'])} "
            f"| {pct(m['ret_ytd'])} | {pct(m['ret_1a'])} |"
        )
    lineas.append("")


def seccion_tabla_maestra(universo, metricas, lineas):
    lineas.append("## 2. Tabla maestra\n")
    for clave, titulo in CATEGORIAS:
        entradas = [e for e in universo.get(clave, []) if e["ticker"] in metricas]
        if not entradas:
            continue

        lineas.append(f"### {titulo}\n")
        lineas.append("| Ticker | Nombre | Precio | 1D | 1M | 3M | YTD | 1A | RSI | Vol.an | vs Máx52s | Tend. |")
        lineas.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:--:|")
        for e in sorted(entradas, key=lambda x: metricas[x["ticker"]]["ret_1m"] or -999, reverse=True):
            m = metricas[e["ticker"]]
            tend = {"alcista": "▲", "bajista": "▼"}.get(m["tendencia"], "—")
            lineas.append(
                f"| `{e['ticker']}`{marca_liquidez(m)} | {e['nombre']} | {num(m['precio'])} "
                f"| {pct(m['ret_1d'])} | {pct(m['ret_1m'])} | {pct(m['ret_3m'])} "
                f"| {pct(m['ret_ytd'])} | {pct(m['ret_1a'])} | {rsi_txt(m['rsi14'])} "
                f"| {num(m['vol_anual'], 1)}% | {pct(m['dd_desde_max52'])} | {tend} |"
            )
        lineas.append("")

    if any(m.get("liquidez") in ("baja", "muy_baja") for m in metricas.values()):
        lineas.append(
            "⚠ = liquidez baja · ⚠⚠ = liquidez muy baja. "
            "Sus indicadores son poco confiables; ver sección 6.\n"
        )


def seccion_screening(resultados, metricas, lineas):
    lineas.append("## 3. Alertas de screening\n")
    con_hits = [(k, v) for k, v in resultados.items() if v["coincidencias"]]
    if not con_hits:
        lineas.append("_Ninguna regla se activó en esta corrida._\n")
        return

    for _, bloque in con_hits:
        regla = bloque["regla"]
        icono = scr.icono_severidad(regla)
        lineas.append(f"### {icono} {regla['descripcion']}\n")
        lineas.append("| Ticker | Nombre | Precio | RSI | 1M | vs Máx52s |")
        lineas.append("|---|---|---:|---:|---:|---:|")
        for t in bloque["coincidencias"]:
            m = metricas[t]
            lineas.append(
                f"| `{t}` | {m['nombre'][:30]} | {num(m['precio'])} | {rsi_txt(m['rsi14'])} "
                f"| {pct(m['ret_1m'])} | {pct(m['dd_desde_max52'])} |"
            )
        lineas.append("")


def seccion_extremos(metricas, lineas):
    lineas.append("## 4. Extremos del mes\n")
    elegibles = [m for t, m in metricas.items()
                 if m["ret_1m"] is not None and t not in ("MXN=X", "^MXX")]
    if len(elegibles) < 2:
        lineas.append("_Datos insuficientes._\n")
        return

    ordenados = sorted(elegibles, key=lambda m: m["ret_1m"], reverse=True)
    # Con universos chicos se recorta el bloque para que un mismo instrumento
    # no aparezca a la vez como mejor y como peor del mes.
    k = min(5, len(ordenados) // 2)

    lineas.append("| | Ticker | Nombre | 1M | 3M | RSI |")
    lineas.append("|---|---|---|---:|---:|---:|")
    for m in ordenados[:k]:
        lineas.append(f"| ▲ | `{m['ticker']}` | {m['nombre'][:30]} | {pct(m['ret_1m'])} | {pct(m['ret_3m'])} | {rsi_txt(m['rsi14'])} |")
    for m in ordenados[-k:][::-1]:
        lineas.append(f"| ▼ | `{m['ticker']}` | {m['nombre'][:30]} | {pct(m['ret_1m'])} | {pct(m['ret_3m'])} | {rsi_txt(m['rsi14'])} |")
    lineas.append("")


def calcular_correlaciones(datos, metricas):
    """
    Correlación de cada instrumento contra el IPC y contra el S&P 500 (vía VOO).

    Devuelve una lista de filas (ticker, nombre, r_ipc, r_spx), ordenada de mayor
    a menor contra el IPC, o None si no se descargó ninguno de los dos índices.
    La usan tanto el reporte Markdown como la página web.
    """
    base_ipc = datos.get("^MXX")
    base_spx = datos.get("VOO.MX")
    if not base_ipc and not base_spx:
        return None

    def corr_contra(serie, base):
        if not base:
            return None
        return ind.correlacion(
            serie["fechas"][-VENTANA_52S:], serie["cierres"][-VENTANA_52S:],
            base["fechas"][-VENTANA_52S:], base["cierres"][-VENTANA_52S:],
        )

    filas = []
    for t, serie in datos.items():
        if t in ("^MXX", "VOO.MX"):
            continue
        r_ipc = corr_contra(serie, base_ipc)
        r_spx = corr_contra(serie, base_spx)
        if r_ipc is not None or r_spx is not None:
            filas.append((t, metricas[t]["nombre"], r_ipc, r_spx))

    filas.sort(key=lambda f: f[2] if f[2] is not None else -9, reverse=True)
    return filas


def seccion_correlaciones(datos, metricas, lineas):
    lineas.append("## 5. Correlación con los índices\n")
    lineas.append(
        "_Correlación de rendimientos diarios del último año. "
        "Cercano a 1 = se mueve igual que el índice; cercano a 0 = aporta diversificación._\n"
    )

    filas = calcular_correlaciones(datos, metricas)
    if filas is None:
        lineas.append("_Sin índices de referencia descargados._\n")
        return
    if not filas:
        lineas.append("_Datos insuficientes._\n")
        return

    lineas.append("| Ticker | Nombre | vs IPC | vs S&P 500 |")
    lineas.append("|---|---|---:|---:|")
    for t, nombre, r_ipc, r_spx in filas:
        c_ipc = f"{r_ipc:.2f}" if r_ipc is not None else "—"
        c_spx = f"{r_spx:.2f}" if r_spx is not None else "—"
        lineas.append(f"| `{t}` | {nombre[:30]} | {c_ipc} | {c_spx} |")
    lineas.append("")


def seccion_calidad(metricas, lineas):
    lineas.append("## 6. Calidad de datos y liquidez\n")
    lineas.append(
        "_Los instrumentos del SIC operan con volúmenes mucho menores que en su mercado de "
        "origen. Si una sesión cierra sin operaciones, el cierre anterior se arrastra y el "
        "rendimiento aparece como 0.00%, lo que **subestima la volatilidad y rompe las "
        "correlaciones**. Aquí se listan los instrumentos cuyos indicadores conviene tomar "
        "con reserva._\n"
    )

    sospechosos = sorted(
        [m for m in metricas.values() if m.get("liquidez") in ("baja", "muy_baja")],
        key=lambda m: m["pct_sin_volumen"] or 0, reverse=True,
    )
    if not sospechosos:
        lineas.append("Sin instrumentos problemáticos: todas las series operaron con regularidad.\n")
        return

    lineas.append("| Ticker | Nombre | Sesiones sin volumen | Cierres repetidos | Nivel |")
    lineas.append("|---|---|---:|---:|:--:|")
    for m in sospechosos:
        nivel = "⚠⚠ muy baja" if m["liquidez"] == "muy_baja" else "⚠ baja"
        lineas.append(
            f"| `{m['ticker']}` | {m['nombre'][:30]} | {num(m['pct_sin_volumen'], 1)}% "
            f"| {num(m['pct_repetidos'], 1)}% | {nivel} |"
        )
    lineas.append("")


def seccion_macro(macro, lineas, hay_token):
    lineas.append("## 7. Macro — Banxico\n")
    if not hay_token:
        lineas.append(
            "_Sin token de Banxico. Consíguelo gratis en "
            "<https://www.banxico.org.mx/SieAPIRest/service/v1/token> y córrelo con "
            "`--token-banxico <TOKEN>` o exportando `BANXICO_TOKEN`._\n"
        )
        return
    if not macro:
        lineas.append("_El SIE no devolvió datos. Revisa el token y los IDs de serie._\n")
        return

    lineas.append("| Serie | Indicador | Fecha | Valor |")
    lineas.append("|---|---|---|---:|")
    for s in macro:
        lineas.append(f"| `{s['id']}` | {s['titulo'][:55]} | {s['fecha']} | {s['valor']} |")
    lineas.append("")


def seccion_noticias(noticias_por_ticker, mercado, lineas):
    lineas.append("## 8. Noticias\n")

    if mercado:
        lineas.append("### Mercado (Expansión)\n")
        for n in mercado:
            titulo = n["titulo"] or "(sin título)"
            lineas.append(f"- [{titulo}]({n['link']})" if n["link"] else f"- {titulo}")
        lineas.append("")

    if noticias_por_ticker:
        lineas.append("### Por emisora con alerta\n")
        for t, items in noticias_por_ticker.items():
            if not items:
                continue
            lineas.append(f"**{t}**\n")
            for n in items:
                titulo = n["titulo"] or "(sin título)"
                lineas.append(f"- [{titulo}]({n['link']})" if n["link"] else f"- {titulo}")
            lineas.append("")

    if not mercado and not noticias_por_ticker:
        lineas.append("_Sin noticias recuperadas en esta corrida._\n")


def seccion_diagnostico(datos, solicitados, lineas):
    lineas.append("## 9. Diagnóstico de la corrida\n")
    lineas.append(f"- Instrumentos solicitados: **{len(solicitados)}**")
    lineas.append(f"- Series descargadas correctamente: **{len(datos)}**")
    if fuentes.ERRORES:
        lineas.append(f"- Incidencias: **{len(fuentes.ERRORES)}**\n")
        for e in fuentes.ERRORES:
            lineas.append(f"  - `{e}`")
    else:
        lineas.append("- Incidencias: **0**")
    lineas.append("")


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------

def construir_reporte(cfg, datos, metricas, resultados, macro, hay_token,
                      noticias_ticker, noticias_mkt, solicitados, rango):
    ahora = datetime.now()
    lineas = [
        "# Reporte de Research — Universo GBM",
        "",
        f"**Generado:** {ahora.strftime('%Y-%m-%d %H:%M')} (hora local)  ",
        f"**Instrumentos analizados:** {len(datos)}  ",
        f"**Ventana histórica:** {rango}  ",
        f"**Última sesión con datos:** {max(m['ultima_fecha'] for m in metricas.values()) if metricas else '—'}",
        "",
        "---",
        "",
    ]

    seccion_panorama(metricas, lineas)
    seccion_tabla_maestra(cfg["universo"], metricas, lineas)
    seccion_screening(resultados, metricas, lineas)
    seccion_extremos(metricas, lineas)
    seccion_correlaciones(datos, metricas, lineas)
    seccion_calidad(metricas, lineas)
    seccion_macro(macro, lineas, hay_token)
    seccion_noticias(noticias_ticker, noticias_mkt, lineas)
    seccion_diagnostico(datos, solicitados, lineas)

    lineas += [
        "---",
        "",
        "> **Alcance.** Este reporte es una herramienta de research: describe lo que hicieron los",
        "> precios y qué reglas técnicas se activaron. No es una recomendación de compra o venta",
        "> ni asesoría de inversión. Las decisiones de operación son del usuario.",
        "",
        "> **Fuentes.** Precios y titulares por emisora: Yahoo Finance. Noticias de mercado:",
        "> Expansión. Macro: Banxico SIE. Los precios pueden traer retraso respecto al mercado",
        "> en vivo y no sustituyen la información oficial de tu casa de bolsa.",
        "",
    ]
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)

    universo = cfg["universo"]
    todos = [e["ticker"] for cat, _ in CATEGORIAS for e in universo.get(cat, [])]

    if args.tickers:
        pedidos = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        pedidos = todos

    print(f"Descargando {len(pedidos)} instrumentos (rango={args.rango})...")
    cache_dir = RAIZ / "datos" / "cache"
    datos = fuentes.descargar_universo(pedidos, args.rango, cache_dir, args.ttl)

    if not datos:
        print("ERROR: no se descargo ninguna serie. Revisa tu conexion.")
        return 1

    print(f"Calculando indicadores sobre {len(datos)} series...")
    metricas = {t: calcular_metricas(s) for t, s in datos.items()}

    # Los nombres del watchlist son más legibles que la razón social que
    # devuelve Yahoo ("Wal-Mart de México, S.A.B. de C.V.").
    nombres = {e["ticker"]: e["nombre"]
               for cat, _ in CATEGORIAS for e in universo.get(cat, [])}
    for t, m in metricas.items():
        m["nombre"] = nombres.get(t, m["nombre"])

    print(f"Evaluando {len(cfg.get('reglas', []))} reglas de screening...")
    resultados = scr.correr_screening(cfg.get("reglas", []), metricas)

    macro = []
    hay_token = bool(args.token_banxico)
    if hay_token:
        print("Consultando Banxico SIE...")
        macro = fuentes.macro_banxico(cfg.get("macro_banxico", []), args.token_banxico)

    noticias_por_ticker, noticias_mkt = {}, []
    if not args.sin_noticias:
        print("Recuperando noticias...")
        noticias_mkt = fuentes.noticias_mercado(12)
        # Solo bajamos titulares de las emisoras que dispararon alguna alerta:
        # es donde el contexto cualitativo realmente aporta.
        con_alerta = []
        for bloque in resultados.values():
            if bloque["regla"].get("severidad") in ("alta", "media"):
                for t in bloque["coincidencias"]:
                    if t not in con_alerta:
                        con_alerta.append(t)
        for t in con_alerta[:args.max_noticias]:
            noticias_por_ticker[t] = fuentes.noticias_ticker(t, 4)

    salida = Path(args.salida) if args.salida else (
        RAIZ / "reports" / f"research_{datetime.now().strftime('%Y-%m-%d')}.md"
    )
    salida.parent.mkdir(parents=True, exist_ok=True)

    reporte = construir_reporte(
        cfg, datos, metricas, resultados, macro, hay_token,
        noticias_por_ticker, noticias_mkt, pedidos, args.rango,
    )
    with open(salida, "w", encoding="utf-8") as f:
        f.write(reporte)

    if args.web:
        # Con menos de la mitad de las series, la página sería engañosa y pisaría
        # la versión buena que ya está publicada: mejor fallar y conservar la anterior.
        if len(datos) < len(pedidos) / 2:
            print(f"ERROR: solo {len(datos)}/{len(pedidos)} series; no se genera la pagina web.")
            return 1
        pagina = pagina_web.construir_pagina(
            universo, CATEGORIAS, metricas, resultados,
            calcular_correlaciones(datos, metricas), macro, hay_token,
            noticias_por_ticker, noticias_mkt, len(pedidos), fuentes.ERRORES, args.rango,
        )
        ruta_web = Path(args.web)
        ruta_web.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta_web, "w", encoding="utf-8") as f:
            f.write(pagina)
        print(f"Pagina web -> {ruta_web}")

    activadas = sum(1 for b in resultados.values() if b["coincidencias"])
    print(f"\nListo -> {salida}")
    print(f"  {len(datos)}/{len(pedidos)} series | {activadas} reglas activadas | {len(fuentes.ERRORES)} incidencias")
    return 0


if __name__ == "__main__":
    sys.exit(main())
