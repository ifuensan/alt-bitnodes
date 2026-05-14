## Why

El frontend de `alt-bitnodes` (`Pesquisa Dashboard`) se montó con un CSS mínimo y ad-hoc: 6 tokens de color, fuente del sistema (`-apple-system` sans-serif), bordes redondeados de 6–8px, tema oscuro único y sin sistema tipográfico. Funciona, pero no tiene identidad visual coherente.

El proyecto hermano `bitcoin-node-scanner` ya tiene un sistema de diseño maduro y documentado en su `DESIGN.md`: la estética "OSINT terminal" — JetBrains Mono en todo, paleta de 18 tokens semánticos con variantes dark/light, sharp corners, sin elevación, color que codifica estado y no decoración. Aplicar ese mismo sistema a `alt-bitnodes` le da una identidad consistente con el ecosistema y eleva el dashboard de "funcional" a "herramienta seria", sin cambiar nada de su funcionalidad.

## What Changes

- **Tipografía**: adoptar **JetBrains Mono** como única familia (self-hosted, woff2 en `/static/fonts/`), con la escala tipográfica del DESIGN.md (`display`, `title`, `body`, `body-sm`, `meta`, `label`, `mono-num`). Jerarquía por tamaño/peso/color, nunca por cambio de familia.
- **Tokens de color**: sustituir los 6 tokens actuales por el set de tokens semánticos del DESIGN.md, con **dos paletas** (dark canónica + light opt-in). Toggle de tema en el header, persistido en `localStorage` (`pesquisa:theme`), aplicado vía `<html data-theme="...">`.
- **Formas**: sharp corners en todo (`border-radius: 0`) — paneles, KPIs, inputs, selects, tablas.
- **Elevación**: eliminar cualquier sombra/glow; jerarquía de superficies por pasos de color plano + bordes de 1px (`bg → surface → surface-2`).
- **Componentes** reestilados con los nuevos tokens: header + toggle de tema, stat tiles (KPIs), paneles/cards, filas de tabla densas, inputs/selects, footer.
- **Charts**: re-tematizar Observable Plot (los tres bar charts) y Plotly (el globo) para que tomen los nuevos tokens de color y la fuente monoespaciada.
- **Adaptación al contexto**: NO se importan componentes del DESIGN.md que no existen en `alt-bitnodes` — sin `L402`, sin command palette, sin pills de findings de seguridad (`EXPOSED/STALE/CVE`). `alt-bitnodes` es un dashboard de exploración de la red, no una consola OSINT de seguridad.
- Sin cambios en funcionalidad, endpoints, datos ni comportamiento — es un re-skin puro.

## Capabilities

### New Capabilities
- `dashboard-design-system`: el sistema de diseño del dashboard — tokens de color (dark + light), escala tipográfica JetBrains Mono, reglas de forma/elevación, toggle de tema persistido, y cómo los componentes (header, stat tiles, paneles, tablas, inputs, footer) y los charts consumen esos tokens.

### Modified Capabilities
- `dashboard-bar-charts`: el requisito de estilo ("Dark theme styling") se reescribe para que los colores y la fuente provengan de los tokens del nuevo sistema de diseño (incluido el modo light) en lugar de valores hex codificados.

## Impact

- **Código**: `static/app.css` (reescritura completa con el nuevo sistema de tokens), `templates/index.html` (toggle de tema en el header, `data-theme`, `<link>` a la fuente self-hosted), `static/app.js` (lógica del toggle + persistencia; re-tematizado de los charts Observable Plot y del globo Plotly para leer tokens en vez de hex fijos).
- **Assets nuevos**: `static/fonts/` con los woff2 de JetBrains Mono (subconjunto de pesos: 400, 500, 600).
- **Sin impacto en**: backend (`app.py`, `queries/`), API REST, MCP server, crawler, despliegue de infra.
- **Despliegue**: cambio sólo de assets estáticos + plantilla. Tras el push conviene invalidar CloudFront en `/static/app.css`, `/static/app.js`, `/static/fonts/*` y `/`.
- **Referencia**: el `DESIGN.md` de `bitcoin-node-scanner` es la fuente de verdad de los valores de token y el rationale; este cambio lo adapta, no lo copia literalmente.
