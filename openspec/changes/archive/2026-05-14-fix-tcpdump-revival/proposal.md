## Why

El postmortem del 2026-05-13 decidió desactivar `tcpdump-pcap.service` por defecto: el sniffer causa contención de I/O que hace oscilar los snapshots (50–4000 nodos de forma aleatoria). La implementación de esa decisión fue añadir `systemctl disable tcpdump-pcap.service` a `install.sh`. **No funcionó.**

`deploy/bitnodes.service` tiene en su sección `[Unit]`:

```
Wants=network-online.target tcpdump-pcap.service
```

`systemctl disable` solo quita el symlink de auto-arranque al boot — **no rompe una dependencia `Wants=`**. Cada vez que `bitnodes.service` arranca o se reinicia (es decir, en cada deploy), systemd arrastra `tcpdump-pcap.service` vía ese `Wants=`, aunque esté `disabled`. tcpdump corre 4 minutos (`run-tcpdump.sh` usa `-W 8`, sale solo tras 8 ficheros), genera la contención, y muere — hasta el siguiente restart. Peor: `install.sh` hace `systemctl stop tcpdump` y dos líneas después `systemctl restart bitnodes.service`, **reviviendo tcpdump en el propio instalador**.

Síntomas observados en producción (2026-05-14): snapshots oscilando 4030→1028→732→1053, sweeps que no convergen (la altura de bloque por nodo, que viene del handshake `version` en `crawl.py`, no llega porque tcpdump corta los handshakes), y `tcpdump-pcap.service` arrancando en el mismo segundo que `bitnodes.service` en el journalctl.

## What Changes

- Quitar `tcpdump-pcap.service` de la línea `Wants=` de `deploy/bitnodes.service`. `bitnodes.service` deja de arrastrar el sniffer. Queda `Wants=network-online.target`.
- `tcpdump-pcap.service` permanece en el repo como unit **opt-in**: se puede arrancar manualmente (`systemctl start tcpdump-pcap.service`) si alguna vez se quiere capturar pcaps a propósito, pero nunca como efecto colateral del crawler.
- Revisar `install.sh`: con el `Wants=` fuera, el bloque `stop`/`disable`/`pkill` de tcpdump deja de pelear contra un revival automático. Se conserva como saneamiento idempotente (mata un tcpdump que hubiera quedado de un estado anterior), pero el `disable` redundante se puede simplificar.
- Sin cambios en el dashboard, la API, el MCP server ni el crawler. Es un fix de orquestación systemd.

## Capabilities

### New Capabilities
- `crawler-systemd-units`: cómo `alt-bitnodes` despliega y orquesta las systemd units del crawler `ifuensan/bitnodes` (`bitnodes.service` y el opt-in `tcpdump-pcap.service`) — qué arranca qué, qué dependencias existen entre ellas, y la regla de que la captura pcap nunca es un efecto colateral del crawler.

### Modified Capabilities
<!-- Ninguna. -->

## Impact

- **Código**: `deploy/bitnodes.service` (línea `Wants=`); `deploy/install.sh` (simplificación menor del bloque tcpdump, opcional).
- **Sin impacto en**: `app.py`, `queries/`, API REST, MCP server, el repo del crawler `ifuensan/bitnodes`.
- **Efecto colateral aceptado**: con tcpdump ya sin revivir, `cache_inv` deja de recibir pcaps frescos → `rtt:*` deja de poblarse → `latency_ms` y el leaderboard del dashboard van a `null`. Es exactamente el trade-off que el postmortem del 2026-05-13 ya aceptó ("RTT samples stop flowing... accepted as a trade for snapshot stability"). La solución de fondo que devuelve el RTT sin sniffer es el cambio aparte `active-ping-rtt`.
- **Despliegue**: cambio de unit-file. Tras el push, `install.sh` reinstala la unit; conviene un `systemctl stop tcpdump-pcap` manual una vez si quedara alguna instancia viva en el momento del deploy.
- **Verificación**: tras el deploy, `bitnodes.service` y `tcpdump-pcap.service` ya NO deben aparecer con el mismo `ExecMainStartTimestamp`; los snapshots deben dejar de oscilar y converger a ~4000+.
