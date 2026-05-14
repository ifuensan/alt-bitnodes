## Why

Los tres gráficos de barras del dashboard (top countries, top user agents, top ASNs) usan una altura fija de 240px. Con 13–15 barras eso comprime cada fila a ~12px y las etiquetas se solapan verticalmente. Además las etiquetas del eje Y van alineadas a la derecha: como las versiones de Bitcoin (`/Satoshi:30.2.0/`, `/Satoshi:29.3.0/Knots:20260210+bip110-v0.4.1/UASF-BIP110:0.4/`) tienen longitud muy variable, cada una arranca a una distancia distinta del borde y son imposibles de escanear de un vistazo. El panel desperdicia espacio vertical y horizontal mientras el contenido queda ilegible.

## What Changes

- **Altura dinámica**: la altura del chart pasa a calcularse según el número de barras (`n × barHeight + márgenes`, con `barHeight` ≈ 26–28px) en vez del `height: 240` fijo. Cada barra tiene aire suficiente para que su etiqueta no pise a la vecina.
- **Etiquetas del eje Y alineadas a la izquierda**: las labels arrancan todas a la misma `x`, en fuente monoespaciada, para que las versiones de Bitcoin se alineen carácter a carácter y se lean en columna.
- **`marginLeft` ajustado** al ancho real del texto más largo (con un tope) en lugar de los valores fijos 80/260 actuales.
- **Truncado revisado**: bajar el límite de 54 a ~40 caracteres y mantener el tooltip de Observable Plot mostrando la etiqueta completa al hacer hover.
- El resto del contrato se mantiene: Observable Plot, barras horizontales, orden descendente, tema oscuro, re-render limpio al cambiar de snapshot.

## Capabilities

### New Capabilities
<!-- Ninguna. -->

### Modified Capabilities
- `dashboard-bar-charts`: cambian los requisitos de layout — la altura fija de 240px pasa a altura dinámica por número de barras, y se añade un requisito de legibilidad de etiquetas (alineación a la izquierda + monospace + truncado a 40 chars con tooltip completo).

## Impact

- **Código**: `static/app.js` — función `makeBarChart()` (altura, `marginLeft`, estilo de eje Y); la lógica de truncado en las tres llamadas `makeBarChart(...)`.
- **CSS**: posiblemente `static/app.css` si el contenedor `.chart` tiene altura fija que haya que soltar.
- **Sin impacto en**: API REST, datos del endpoint `/api/snapshot/{ts}/stats`, backend, MCP server.
- **Despliegue**: cambio sólo de assets estáticos; tras el push conviene invalidar CloudFront en `/static/app.js` (+ `/static/app.css` si se toca) para que se vea sin esperar al TTL.
