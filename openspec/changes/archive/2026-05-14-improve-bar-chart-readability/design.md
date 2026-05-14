## Context

`static/app.js::makeBarChart(containerId, labels, values, label)` renderiza los tres charts categóricos con Observable Plot. Estado actual:

- `height: 240` fijo para los tres charts, sin importar cuántas barras haya (13–15 típicamente).
- `marginLeft` codificado: `80` para `chart-countries`, `260` para los otros dos.
- Etiquetas en el eje Y con la alineación por defecto de Plot (a la derecha, pegadas a la barra).
- Truncado previo a la llamada: `k.length > 56 ? k.slice(0,54) + "…" : k` para user agents y ASNs.
- `Plot.tip` ya está montado, así que el hover muestra el dato — pero sobre la etiqueta **ya truncada**, no la original.

El endpoint `/api/snapshot/{ts}/stats` devuelve `top_countries`, `top_user_agents`, `top_asns` como listas `[[label, count], ...]` (máx. 15 cada una). No cambia.

## Goals / Non-Goals

**Goals:**
- Que las 13–15 barras se vean sin solaparse: altura proporcional al número de barras.
- Que las etiquetas de versiones de Bitcoin se lean en columna: alineadas a la izquierda, monospace.
- Que el tooltip muestre la etiqueta **completa**, no la truncada.
- Que los charts ocupen el ancho real del panel en vez del default ~640px de Plot.
- Que el chart de países muestre el **nombre completo** del país, no el código ISO-2.
- Que el tooltip sea legible (~1.5× el tamaño base) al hacer hover.
- Mantener el contrato existente del spec `dashboard-bar-charts` (Observable Plot, barras horizontales, orden descendente, tema oscuro, re-render limpio).

**Non-Goals:**
- No cambiar la librería de charts ni el endpoint de datos.
- No añadir interactividad nueva (zoom, filtros, click-through).
- No tocar el chart de mapa (`countries_iso3` / Plotly geo) — sólo los tres `barX`.
- No hacer los charts responsive a `resize` en caliente más allá de lo que Plot ya hace.

## Decisions

### Decisión 1 — Altura dinámica: `n × barHeight + márgenes`

Sustituir `height: 240` por un cálculo:

```js
const BAR_HEIGHT = 28;          // px por barra, deja aire para la etiqueta
const MARGIN_TOP = 10;
const MARGIN_BOTTOM = 34;       // espacio para el eje X + su label
const height = data.length * BAR_HEIGHT + MARGIN_TOP + MARGIN_BOTTOM;
```

Con 15 barras → ~464px; con 5 → ~184px. El panel crece con el contenido en vez de comprimirlo.

**Alternativa considerada**: mantener 240px y hacer scroll interno. Descartado — esconder datos tras scroll en un dashboard de un vistazo va en contra del propósito del panel.

### Decisión 2 — Etiquetas del eje Y a la izquierda, en monospace

Observable Plot alinea las etiquetas del eje Y a la derecha por defecto. Para alinearlas a la izquierda y darles ancho fijo de carácter:

```js
y: {
  label: null,
  tickSize: 0,
  // alinear las etiquetas al inicio del margen izquierdo
},
style: {
  background: "transparent",
  color: "#e6edf3",
  fontSize: "12px",
},
// el eje Y se dibuja con un mark explícito para controlar textAnchor + fuente
marks: [
  Plot.axisY({
    textAnchor: "start",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
    dx: -marginLeft + 4,   // empuja la etiqueta al borde izquierdo del margen
  }),
  Plot.barX(...),
  ...
]
```

`Plot.axisY({ textAnchor: "start", dx: ... })` es la vía idiomática en Plot ≥0.6 para reposicionar y realinear las etiquetas del eje. La fuente monoespaciada hace que `/Satoshi:30.2.0/` y `/Satoshi:29.0.0/` se alineen dígito a dígito.

**Alternativa considerada**: dibujar las etiquetas como `Plot.text` encima de cada barra (estilo "label on top"). Descartado — duplica la altura por entrada y rompe la lectura "etiqueta → barra" en horizontal que el usuario ya espera.

### Decisión 3 — `marginLeft` calculado desde el texto más largo

En vez de `80 / 260` fijos:

```js
const longest = Math.max(...labels.map(l => l.length));
const marginLeft = Math.min(8 + longest * 7, 380);  // ~7px por char monospace, tope 380
```

`chart-countries` (labels de 2 letras) sale ~22px; user agents/ASNs salen al tope o cerca. El tope de 380px evita que una etiqueta patológica coma todo el ancho de la barra.

### Decisión 4 — Truncado a 40 chars, tooltip con la etiqueta completa

El truncado actual se hace **antes** de llamar a `makeBarChart`, así que `Plot.tip` muestra el texto ya cortado. Mover el truncado dentro de `makeBarChart` y conservar la etiqueta original para el tooltip:

```js
// data lleva ambas: label (mostrada) y full (tooltip)
const data = labels.map((l, i) => ({
  label: l.length > 40 ? l.slice(0, 39) + "…" : l,
  full: l,
  value: values[i],
}));
...
Plot.tip(data, Plot.pointerY({ x: "value", y: "label", title: d => `${d.full}\n${d.value}` , ... }))
```

Las tres llamadas `makeBarChart(...)` en el bloque de render dejan de truncar (pasan la etiqueta cruda).

### Decisión 5 — Ancho responsive desde `el.clientWidth`

Observable Plot usa ~640px de ancho por defecto si no se le pasa `width`,
dejando hueco muerto a la derecha del panel. Se pasa `width: el.clientWidth || 640`
para que el chart llene el contenedor `.plot` (que ya es `width: 100%`).

**Alternativa considerada**: re-render en `resize`. Sigue siendo non-goal —
el ancho se lee una vez al render; basta para el caso de uso (el panel no
cambia de tamaño en caliente salvo rotación/resize manual, y el cambio de
snapshot ya re-renderiza).

### Decisión 6 — Nombres de país completos con `Intl.DisplayNames`

El endpoint devuelve países como ISO-2 (`US`, `DE`). El chart `chart-countries`
mapea cada código a su nombre en inglés con `Intl.DisplayNames(["en"], {type:"region"})`,
nativo del navegador, cero dependencias. Códigos inválidos (proxies anónimos,
etc.) caen al código crudo vía try/catch.

**Alternativa considerada**: que el backend añada el nombre en `top_countries`.
Descartado — cambiaría el contrato del endpoint `/api/snapshot/{ts}/stats` por
algo que el navegador resuelve solo.

### Decisión 7 — Tooltip ~1.5× el tamaño base

`Plot.tip` con `fontSize: 18` y `textPadding: 12` (sobre la base de 12px / 8px).
Se probó 3× (36px) y 2× (24px); 1.5× quedó como el equilibrio entre
legibilidad y no tapar barras vecinas.

## Risks / Trade-offs

- [Paneles mucho más altos desequilibran el layout de la página] → Aceptable: el usuario pidió explícitamente "aprovechar el espacio". Los tres paneles crecen de forma coherente; si en el futuro molesta, se acota `data.length` a top-N menor en el backend.
- [`Plot.axisY` con `dx` negativo grande puede recortar la etiqueta si `marginLeft` se queda corto] → Mitigado: `marginLeft` se calcula desde el texto más largo real, así que el `dx` siempre cae dentro del margen.
- [Monospace a 12px ocupa más ancho que la fuente actual] → Por eso `marginLeft` se calcula con ~7px/char y tiene tope; si el tope corta, el tooltip cubre la lectura completa.
- [CloudFront cachea `/static/app.js` 1 día] → Invalidación explícita tras el deploy, igual que en cambios cosméticos anteriores (ver postmortem 2026-05-13).

## Migration Plan

1. Editar `makeBarChart()` en `static/app.js`: altura dinámica, `marginLeft` calculado, `Plot.axisY` con `textAnchor: start` + monospace, truncado interno + tooltip con `full`.
2. Quitar el truncado de las tres llamadas `makeBarChart(...)`.
3. Revisar `static/app.css` por si `.chart` / contenedores tienen `height` fijo que pelee con la altura dinámica; soltarlo si lo hay.
4. Probar local con un snapshot real (≥13 barras en los tres charts) en el navegador.
5. Commit + push; invalidar CloudFront en `/static/app.js` (+ `/static/app.css` si se tocó) y `/`.

**Rollback**: revertir el commit; los assets estáticos vuelven al estado anterior en el siguiente deploy + invalidación.

## Open Questions

- ¿Tope de `marginLeft` en 380px es suficiente, o preferimos 320 y truncar antes? Propuesto 380; se ajusta visualmente en el paso 4.
- ¿`BAR_HEIGHT` 28px o 26px? Propuesto 28; decisión final al ver el render real.
