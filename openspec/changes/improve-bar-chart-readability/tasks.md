## 1. Reescribir makeBarChart()

- [x] 1.1 Sustituir `height: 240` por altura dinámica: `data.length * BAR_HEIGHT + MARGIN_TOP + MARGIN_BOTTOM` (BAR_HEIGHT 28, MARGIN_TOP 10, MARGIN_BOTTOM 34)
- [x] 1.2 Calcular `marginLeft` desde el label más largo: `Math.min(longest * MONO_CHAR_PX + LABEL_PAD_LEFT, 420)` (MONO_CHAR_PX 7.5, PAD 14 — corregido de 7px para evitar recorte del primer carácter)
- [x] 1.3 Añadir `Plot.axisY({ textAnchor: "start", fontFamily: monospace, tickSize: 0, dx: -marginLeft + 8 })`
- [x] 1.4 Mover el truncado dentro de `makeBarChart`: `data` lleva `label` (truncada a 39+`…` si >40) y `full` (original)
- [x] 1.5 Actualizar `Plot.tip` para mostrar `full` + `value` en el título del tooltip

## 2. Limpiar las llamadas

- [x] 2.1 Quitar el truncado de las llamadas `makeBarChart("chart-uas"/"chart-asns", ...)` — pasar la etiqueta cruda
- [x] 2.2 `static/app.css`: `.plot` usa `min-height: 240px` (no `height` fijo) — no pelea con la altura dinámica, no requiere cambio

## 3. Ajustes tras revisión visual (feedback del usuario)

- [x] 3.1 Ancho responsive: pasar `width: el.clientWidth` a `Plot.plot()` para que el chart ocupe todo el panel
- [x] 3.2 Chart de países: mapear ISO-2 → nombre completo con `Intl.DisplayNames` (`countryName()`), con fallback al código crudo
- [x] 3.3 Tooltip a ~1.5×: `fontSize: 18`, `textPadding: 12`, `lineHeight: 1.3` (se probó 3× y 2×, 1.5× fue el elegido)

## 4. Verificación

- [x] 4.1 Dashboard en local con snapshot real (15 barras): barras sin solapar, etiquetas alineadas a la izquierda sin recorte, tooltip completo y legible
- [x] 4.2 Re-render limpio al cambiar de snapshot
- [x] 4.3 Chart de countries con nombres completos y `marginLeft` ajustado

## 5. Despliegue

- [ ] 5.1 Commit + push (workflow Deploy to EC2 corre install.sh)
- [ ] 5.2 Invalidación CloudFront en `/static/app.js`, `/` (y `/static/app.css` no se tocó)
- [ ] 5.3 Verificar en `https://pesquisa.hacknodes.xyz/` que el cambio está live
