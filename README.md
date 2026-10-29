# Mercado GBM — reporte diario

Reporte de research de mercado para el universo invertible desde una casa de bolsa mexicana:
acciones de la BMV, acciones y ETFs de EE. UU. que se compran en el SIC, el panorama del mercado
estadounidense (S&P 500, Nasdaq, Dow, VIX, bono a 10 años y los 11 sectores) y referencias macro.
Se genera cada día hábil por la mañana y se publica como una página pensada para leerse en el celular.

**Qué calcula:** rendimientos (5 días a 12 meses), RSI, volatilidad, caída desde el máximo de 52
semanas, tendencia (medias de 50 y 200 sesiones), correlación contra el IPC y el S&P 500, y un
conjunto de reglas de screening definidas en `config/watchlist.json`. También mide qué tan
confiables son los precios de cada instrumento del SIC (muchos cierran días sin operaciones).

**Cómo se analizan los valores del SIC.** Un valor como `VOO.MX` es la versión mexicana de `VOO`
(que cotiza en Nueva York). Su volumen es mínimo y muchas sesiones cierran sin operaciones, así
que sus indicadores no son confiables. Por eso los indicadores y las alertas se calculan sobre el
mercado de origen (en dólares), y el ticker del SIC se muestra como «En GBM+», con su precio en
pesos y un aviso si su liquidez es baja. Cada valor del SIC declara su origen en el campo `origen`
de `config/watchlist.json`.

> **Alcance.** Es una herramienta de research: describe lo que hicieron los precios y qué reglas
> técnicas se activaron. No es una recomendación de compra o venta ni asesoría de inversión, no
> contiene datos de ningún portafolio y no ejecuta operaciones.

## Cómo funciona

```
scripts/fuentes.py       descarga de datos (Yahoo Finance, Banxico, noticias RSS)
scripts/indicadores.py   indicadores técnicos y medidas de calidad de datos
scripts/universo.py      empareja cada valor del SIC con su mercado de origen
scripts/seguimiento.py   lee y valida tu lista de EE. UU. (config/seguimiento_eeuu.txt)
scripts/screening.py     motor de reglas (comparaciones sobre números, sin IA)
scripts/research.py      orquestador: descarga -> indicadores -> reglas -> reporte
scripts/pagina_web.py    genera la página HTML para celular
tools/generar_icono.py   genera los iconos de la página
tools/ya_publicado.py    dice si la página de hoy ya se generó (lo usan las corridas de respaldo)
config/watchlist.json    universo de seguimiento y reglas
docs/                    la página publicada (GitHub Pages)
.github/workflows/       tarea diaria que regenera la página
```

Solo usa la biblioteca estándar de Python: no hay nada que instalar.

## Tu lista de EE. UU.

Además del universo fijo, puedes seguir las acciones y ETFs de EE. UU. que quieras. Escribe sus
tickers en `config/seguimiento_eeuu.txt` (uno por línea, sin `.MX`; máximo 30) y listo: en la
siguiente corrida aparecen en el bloque «Mi lista de EE. UU.» con los mismos indicadores y alertas.
La página tiene un botón «Editar mi lista» que abre ese archivo en github.com, así que se puede
hacer desde el celular; al guardar, la página se actualiza sola en unos 2 minutos.

Cada valor se revisa solo: si existe en Yahoo Finance, si tiene versión en el SIC (la que se
compra en GBM+, por ejemplo `BRK-B` → `BRKB.MX`) y qué tan activo es ese precio. Si algo está mal
escrito, está repetido o no aparece en el SIC, la sección «Mi lista» de la página lo avisa. Que
un valor tenga versión `.MX` en Yahoo no garantiza que tu casa de bolsa lo ofrezca: confírmalo
antes de operar.

## Usarlo en tu computadora

```bash
python scripts/research.py                          # reporte en reports/research_<fecha>.md
python scripts/research.py --web docs/index.html    # además genera la página para celular
python scripts/research.py --tickers WALMEX.MX,VOO.MX --sin-noticias
```

## Publicación automática

El flujo `.github/workflows/reporte-diario.yml` corre de lunes a viernes a las 06:07 (hora de
Ciudad de México), regenera `docs/index.html` y lo guarda en el repositorio; GitHub Pages sirve la
carpeta `docs/`. También se puede lanzar a mano desde la pestaña **Actions → Run workflow**, y se
dispara solo cada vez que se guardan cambios en `scripts/`, `config/` (incluida tu lista de
EE. UU.) o `tools/`.

**Las tareas programadas de GitHub no son puntuales.** En este repositorio llegaron unas 6 horas
tarde (programadas a las 06:07 y 06:47, ejecutadas entre las 11:55 y las 12:30). Por eso el
disparo principal es externo: una automatización de **Atajos en el iPhone** que a las 06:00 llama a
la API de GitHub, lo mismo que hace el botón «Run workflow»; esas corridas arrancan en segundos:

```
POST https://api.github.com/repos/<usuario>/<repositorio>/actions/workflows/reporte-diario.yml/dispatches
Authorization: Bearer <token de acceso fino con permiso "Actions: Read and write" solo sobre este repositorio>
Accept: application/vnd.github+json
Cuerpo (JSON): {"ref": "main"}
```

Las horas programadas (06:07 y 06:47) se quedan como respaldo por si el iPhone no disparó. Antes de
trabajar revisan si la página ya se generó hoy (`tools/ya_publicado.py` lee la marca de fecha del
propio HTML): si ya existe, no hacen nada, así una corrida tardía no reemplaza la página de la
mañana por una de mediodía. El disparo del iPhone, el botón manual y los cambios de código siempre
corren.

Para incluir la sección de macro (Banxico), guarda tu token gratuito como secreto del repositorio
con el nombre `BANXICO_TOKEN` (Settings → Secrets and variables → Actions).

Fuentes: Yahoo Finance (precios y titulares por emisora), Expansión (noticias de mercado) y Banxico SIE
(macro). Los precios pueden traer retraso y no sustituyen la información oficial de tu casa de bolsa.
