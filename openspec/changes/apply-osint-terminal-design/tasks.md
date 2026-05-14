## 1. Fuente JetBrains Mono

- [x] 1.1 Descargados los woff2 de JetBrains Mono v2.304 (pesos 400/500/600) de la release oficial (OFL) a `static/fonts/` + `OFL.txt`
- [x] 1.2 Reglas `@font-face` en `static/app.css` con `font-display: swap`
- [x] 1.3 `<link rel="preload" as="font">` para el peso 400 en `<head>`

## 2. Sistema de tokens en CSS

- [x] 2.1 Paleta dark (canónica) en `:root` con los tokens del DESIGN.md
- [x] 2.2 Paleta light en `html[data-theme="light"]` con los mismos nombres
- [x] 2.3 Tokens de spacing (`--xs`…`--xl`, 8px grid)

## 3. Reescritura de app.css

- [x] 3.1 `body` y superficies: JetBrains Mono, jerarquía `bg → surface → surface-2`, separadores 1px
- [x] 3.2 Escala tipográfica aplicada a los selectores existentes (header→title, KPI value→mono-num, labels→label uppercase, tablas→body-sm, meta→meta)
- [x] 3.3 `border-radius: 0` en todos los componentes
- [x] 3.4 Sin `box-shadow`/glow — verificado, no había elevación
- [x] 3.5 Color semántico: `primary` para header/toggle/footer; `ok/warn/alert` definidos como tokens disponibles

## 4. Toggle de tema

- [x] 4.1 Script anti-FOUC inline en `<head>` (lee `localStorage['pesquisa:theme']` o `prefers-color-scheme` antes del paint)
- [x] 4.2 Botón `#theme-toggle` en `.controls` del header
- [x] 4.3 `toggleTheme()` en `app.js`: actualiza `data-theme` + `localStorage`, re-renderiza charts

## 5. Re-tematizar charts y globo

- [x] 5.1 Helper `themeTokens()` lee los tokens activos vía `getComputedStyle`
- [x] 5.2 `makeBarChart()`: hex hardcoded → valores de `themeTokens()`
- [x] 5.3 `updateGlobe()`: paleta dedicada por tema `globePalette()` (land/ocean oscuros + ramp naranja) — los tokens generales no dan contraste interno en light
- [x] 5.4 Toggle re-renderiza los 3 charts + globo vía `renderCharts()` sin nodos huérfanos

## 6. Ajuste de layout (feedback durante la implementación)

- [x] 6.1 Grid reestructurado a `1fr 1fr`: Distribution + Top countries en fila 1 a igual altura; user agents y ASNs a ancho completo (`.panel-full`) debajo
- [x] 6.2 Globo: contraste corregido en tema light (paleta dedicada — ver 5.3)

## 7. Verificación

- [x] 7.1 Tema dark — header, KPIs strip, paneles, tablas, charts, globo, footer
- [x] 7.2 Tema light — mismos elementos, contraste legible (globo incluido)
- [x] 7.3 Toggle en caliente sin FOUC, persistencia tras recargar, charts/globo siguen el tema
- [x] 7.4 Sharp corners y sin elevación verificados
- [x] 7.5 Fuente self-hosted confirmada (woff2 servidos desde `/static/fonts/`, sin CDN)

## 8. Despliegue

- [ ] 8.1 Commit + push (workflow Deploy to EC2 corre install.sh)
- [ ] 8.2 Invalidación CloudFront en `/static/app.css`, `/static/app.js`, `/static/fonts/*`, `/`
- [ ] 8.3 Verificar en `https://pesquisa.hacknodes.xyz/` que el re-skin está live en ambos temas
