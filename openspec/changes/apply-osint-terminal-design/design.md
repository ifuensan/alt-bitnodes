## Context

`alt-bitnodes` frontend hoy:
- `static/app.css` — 66 líneas, 6 tokens (`--bg --panel --border --text --muted --accent`), `font-family: -apple-system...`, `border-radius` 6–8px en paneles/KPIs/inputs, tema dark único.
- `templates/index.html` — header, 5 stat tiles (`.kpi`), grid (globo Plotly + 3 bar charts), 2 tablas (leaderboard + nodes), footer.
- `static/app.js` — Observable Plot para los bar charts con colores hex hardcoded (`#f7931a`, `#e6edf3`, `#0e1116`, `#2d333b`); Plotly para el globo con su propio bloque de `layout` lleno de hex (`#161b22`, `#0e1116`, etc.).

El `DESIGN.md` de `bitcoin-node-scanner` define el sistema objetivo. Su frontmatter YAML tiene los valores exactos de los 18 tokens × 2 temas, la escala tipográfica (7 niveles) y los tokens de spacing (8px grid). Su prosa explica el rationale: color semántico, monospace único, sin elevación, sharp corners.

Constraint clave: este proyecto no es el scanner. No tiene findings de seguridad, ni L402, ni command palette. El sistema se **adapta**, no se copia.

## Goals / Non-Goals

**Goals:**
- Una sola hoja `static/app.css` reescrita sobre los tokens del DESIGN.md, con dark + light.
- JetBrains Mono self-hosted como única familia, con la escala tipográfica del DESIGN.md.
- Sharp corners (`border-radius: 0`) y cero elevación en todos los componentes.
- Toggle de tema en el header, persistido en `localStorage['pesquisa:theme']`, aplicado con `<html data-theme>`.
- Charts (Observable Plot) y globo (Plotly) leyendo los tokens en vez de hex fijos, y respetando el tema activo.
- Cero cambios de funcionalidad: mismo HTML semántico, mismos endpoints, mismos datos.

**Non-Goals:**
- No portar componentes inexistentes aquí: L402, command palette, pills `EXPOSED/STALE/CVE`.
- No rediseñar el layout (sigue siendo header → KPIs → grid → tablas → footer).
- No tocar backend, API, MCP, crawler.
- No añadir build step (Sass, PostCSS, bundler): CSS plano con custom properties, como ahora.
- No animaciones ni transiciones más allá de las que ya hay (hover de tabla).

## Decisions

### Decisión 1 — Tokens como CSS custom properties, theme switch por `data-theme`

`:root` define la paleta **dark** (canónica). `html[data-theme="light"]` redefine los mismos nombres de token con los valores light. Todos los componentes referencian `var(--token)` sin saber qué tema está activo — igual que el DESIGN.md describe.

Set de tokens (nombres del DESIGN.md, adaptados): `bg`, `surface`, `surface-2`, `border`, `border-dim`, `text`, `text-dim`, `muted`, `dim`, `primary`, `ok`, `warn`, `alert`, `accent`, más los `*-bg` que se usen. Se mantienen los nombres del DESIGN.md para que el rationale sea trazable; los que no apliquen aquí (`l402-bg`, `on-primary` si no se usa) se omiten.

**Alternativa considerada**: dos archivos CSS (uno por tema) cargados condicionalmente. Descartado — el patrón `data-theme` + custom properties es un único archivo, sin flash de tema incorrecto si el `<script>` del toggle corre antes del render.

### Decisión 2 — Anti-FOUC: resolver el tema antes del primer paint

Un `<script>` inline pequeño en el `<head>` lee `localStorage['pesquisa:theme']` (o `prefers-color-scheme` si no hay valor) y pone `data-theme` en `<html>` **antes** de que el body se pinte. El toggle del header solo actualiza el atributo + localStorage en caliente. Es el patrón estándar para evitar el parpadeo dark→light.

### Decisión 3 — JetBrains Mono self-hosted, subset de 3 pesos

Descargar de la release oficial (OFL, libre) los woff2 de los pesos **400, 500, 600** a `static/fonts/`. `@font-face` en `app.css` con `font-display: swap`. Tres pesos cubren la escala del DESIGN.md (body 400, títulos/números 500, refuerzo 600). No se incluyen italics ni otros pesos — no se usan.

**Alternativa considerada**: CDN (Google Fonts). Descartada por decisión del usuario — self-hosted evita dependencia externa en el critical path y funciona detrás de CloudFront sin saltos a otro origen.

### Decisión 4 — Escala tipográfica como utilidades de token, no clases por componente

Las 7 entradas tipográficas del DESIGN.md (`display`, `title`, `body`, `body-sm`, `meta`, `label`, `mono-num`) se expresan como grupos de propiedades aplicadas directamente a los selectores existentes (`header h1` → `title`, `.kpi .value` → `mono-num`, `.kpi .label` → `label`, `td/th` → `body-sm`, etc.). No se crea un framework de clases utilitarias — el HTML actual es pequeño y semántico, se reestila in-place.

Mapeo inicial:
| Elemento | Token tipográfico |
|---|---|
| `header h1` | `title` 17/500 |
| `.kpi .value` (`#kpi-*`) | `mono-num` 16/500 |
| `.kpi .label` | `label` 10/500 +0.6 LS, uppercase |
| `.panel h2` | `label` |
| `td`, `th`, `#filter`, `select` | `body-sm` 12/400 |
| `#snapshot-meta`, footer | `meta` 11/400 |

### Decisión 5 — Color semántico: `primary` solo marca/CTA, estados con `ok/warn/alert`

Hoy `--accent` (#f7931a) se usa como relleno en KPIs, barras de chart, enlaces del footer. El DESIGN.md es estricto: Bitcoin orange = marca/CTA, no relleno. Adaptación pragmática para alt-bitnodes:
- `primary` (#F7931A): título/logo del header, indicador del toggle de tema, enlaces del footer.
- Las **barras de los charts** pueden seguir usando `primary` como fill — es el dato principal del dashboard y no hay otro "estado" que comunicar; se documenta como excepción consciente al "no usar primary de relleno".
- `ok/warn/alert` quedan disponibles como tokens para usos futuros (p. ej. marcar nodos onion con `warn`, latencias altas con `alert`) pero **este cambio no introduce esos usos** — solo deja los tokens definidos.

**Alternativa considerada**: cambiar el fill de las barras a un gris neutro y reservar orange solo para marca. Descartado — las barras son el contenido, no decoración; el naranja ahí es legítimo y el dashboard perdería su color característico.

### Decisión 6 — Charts leen tokens vía `getComputedStyle`

Observable Plot y Plotly reciben colores como strings JS, no CSS. En `app.js`, una función `themeTokens()` lee los valores actuales con `getComputedStyle(document.documentElement).getPropertyValue('--token')` y los pasa a las configs de Plot/Plotly. Al cambiar de tema, los charts se re-renderizan (ya hay re-render en cambio de snapshot; el toggle dispara el mismo camino).

**Alternativa considerada**: hardcodear dos juegos de color en JS. Descartado — duplica la fuente de verdad; `getComputedStyle` mantiene CSS como única fuente.

**Excepción — el globo (Plotly choropleth)**: los bar charts sí funcionan con los tokens generales, pero el globo necesita **contraste interno** entre el land base y los países con datos. En el tema light todos los tokens de superficie son casi blancos, así que un choropleth derivado de ellos no se ve. El globo tiene por eso una paleta dedicada por tema (`globePalette()`): land/ocean oscuros + un ramp naranja con endpoints afinados por tema, en vez de derivarse 1:1 de los tokens. Sigue siendo "naranja como color de dato" (coherente con las barras), pero con su propio contraste.

### Decisión 8 — Reestructurar el grid: Distribution + Top countries en la misma fila

El layout original ponía el globo (`map-panel`) como columna izquierda ocupando `grid-row: span 3` — un panel desproporcionadamente alto. Se reestructura el grid a `1fr 1fr`: fila 1 = Distribution + Top countries lado a lado (igual altura, porque el grid estira ambas celdas a la más alta y `#globe` es `flex: 1`), filas 2-3 = Top user agents y Top ASNs a ancho completo (`.panel-full { grid-column: 1 / -1 }`). Los charts ya son responsive al ancho, así que se adaptan sin más.

Surgió como feedback durante la implementación; se mantiene dentro de este cambio por ser puramente CSS/estructura de plantilla. El botón para **colapsar** esa fila (funcionalidad nueva) queda explícitamente fuera — se trata en un proposal aparte.

### Decisión 7 — Sharp corners y sin elevación, barrido completo

`border-radius: 0` en `.kpi`, `.panel`, `.controls select`, `#filter`, `#globe`. Eliminar cualquier `box-shadow` (hoy no hay, pero se verifica). Jerarquía de superficies: `body` = `bg`, `.panel`/`.kpi` = `surface`, filas de tabla expandidas/sticky headers = `surface-2`, todo separado por `1px solid var(--border)`.

## Risks / Trade-offs

- [El globo Plotly tiene su propio sistema de theming y muchos hex en `layout`] → Se re-tematiza el bloque `layout` de `updateGlobe()` leyendo tokens; el colorscale del choropleth (verdes) se mantiene como caso aparte (es escala de datos, no chrome) o se deriva de `ok`. Riesgo acotado, es un solo objeto de config.
- [Flash de tema incorrecto (FOUC)] → Mitigado por la Decisión 2 (script inline en `<head>` antes del paint).
- [Densidad: el DESIGN.md pide tablas muy densas (9px padding); el dashboard actual usa 8px] → Ya está cerca; se ajusta a los valores del DESIGN.md sin drama.
- [JetBrains Mono es más ancha que la sans-serif del sistema → las tablas y los charts pueden necesitar más ancho] → Las tablas tienen `overflow:auto`; los charts ya calculan `marginLeft` desde el ancho de carácter monospace (cambio `improve-bar-chart-readability`), así que el supuesto monospace ya está asumido ahí.
- [Light theme menos probado] → Se valida explícitamente en ambos temas en la fase de verificación.
- [CloudFront cachea `/static/*` 1 día] → Invalidación explícita de `app.css`, `app.js`, `fonts/*`, `/` tras el deploy.

## Migration Plan

1. Añadir `static/fonts/` con los woff2 de JetBrains Mono (400/500/600) + `@font-face` en `app.css`.
2. Reescribir `static/app.css` sobre los tokens del DESIGN.md (dark + light), sharp corners, sin elevación, escala tipográfica aplicada a los selectores existentes.
3. `templates/index.html`: script anti-FOUC en `<head>`, `<link>`/preload de la fuente, botón de toggle de tema en `.controls`.
4. `static/app.js`: lógica del toggle (set `data-theme` + localStorage), `themeTokens()` helper, re-tematizar `makeBarChart()` y `updateGlobe()` para consumir tokens, re-render de charts al cambiar de tema.
5. Verificación local en navegador: ambos temas, los 3 charts, el globo, las 2 tablas, el toggle, sin FOUC.
6. Commit + push; invalidación CloudFront de `app.css`, `app.js`, `fonts/*`, `/`.

**Rollback**: revertir el commit; los assets vuelven al estado anterior en el siguiente deploy + invalidación.

## Open Questions

- ¿El colorscale verde del choropleth (globo) se mantiene tal cual o se deriva de `ok`? Propuesto: mantener — es escala de datos, no chrome; decisión final al ver el render.
- ¿Se quita `display` 22/500 de la escala por no usarse (el DESIGN.md mismo dice "Not present in the dashboard")? Propuesto: no definirlo, añadirlo si surge una hero surface.
- ¿Pesos 400/500/600 o basta 400/500? El DESIGN.md dice que 600 es "raro". Propuesto: incluir los 3, descartar 600 en la fase 5 si no se usa.
