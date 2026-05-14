## Context

`alt-bitnodes` despliega tres systemd units para el stack del crawler (`deploy/install.sh::install_systemd_units`):

- `bitnodes.service` — corre `run-bitnodes.sh` (crawl + ping + resolve + export + seeder + cache_inv).
- `tcpdump-pcap.service` — corre `run-tcpdump.sh` (sniffer pcap que alimenta `cache_inv`).
- `alt-bitnodes.service`, `alt-bitnodes-mcp.service` — el dashboard y el MCP server (no relevantes aquí).

Estado actual de las units relevantes (verificado en producción 2026-05-14):

```
# bitnodes.service [Unit]
Wants=network-online.target tcpdump-pcap.service     ◄── el problema
Requires=redis-server.service

# tcpdump-pcap.service [Unit]
After=network-online.target bitnodes.service
PartOf=bitnodes.service
# [Service]
ExecStart=/home/ubuntu/bitnodes/run-tcpdump.sh        # tcpdump -W 8 → sale tras 4 min
Restart=on-failure                                    # exit 0 no es failure → no relanza
```

`run-tcpdump.sh` usa `tcpdump -G 30 -W 8`: rota cada 30 s, máximo 8 ficheros, **sale solo con exit 0** tras ~4 minutos. No es un servicio long-running.

El postmortem del 2026-05-13 decidió que tcpdump debe estar OFF por defecto. `install.sh` lo implementó con `systemctl disable` + `stop` + `pkill`. Pero `disable` no rompe `Wants=`, así que cada `systemctl restart bitnodes.service` (uno por deploy) revive tcpdump 4 minutos.

## Goals / Non-Goals

**Goals:**
- Que `bitnodes.service` no arranque `tcpdump-pcap.service` como efecto colateral.
- Que `tcpdump-pcap.service` siga existiendo en el repo como unit arrancable manualmente (opt-in).
- Dejar `install.sh` coherente: sin lógica que pelee contra un revival que ya no ocurre.
- Capturar en un spec la regla de orquestación para que no se vuelva a romper.

**Non-Goals:**
- No reintroducir el RTT. Que `latency_ms` quede `null` es el trade-off ya aceptado; devolverlo es el cambio `active-ping-rtt`.
- No eliminar `tcpdump-pcap.service` ni `run-tcpdump.sh` del repo — eso lo hace `active-ping-rtt`.
- No tocar el crawler `ifuensan/bitnodes` (`run-bitnodes.sh`, `cache_inv.py`, `start_pcap.sh`).
- No cambiar `alt-bitnodes.service` ni `alt-bitnodes-mcp.service`.

## Decisions

### Decisión 1 — Quitar `tcpdump-pcap.service` del `Wants=`, no del repo

`deploy/bitnodes.service` pasa a:

```
[Unit]
...
Wants=network-online.target
Requires=redis-server.service
```

`Wants=` es la dependencia más débil de systemd, pero sigue arrancando la unit referida. Quitarla es el fix exacto: `bitnodes.service` deja de tener cualquier relación de activación con `tcpdump-pcap.service`.

**Alternativa considerada**: `systemctl mask tcpdump-pcap.service`. Descartada — `mask` lo hace imposible de arrancar incluso manualmente, y queremos conservarlo como opt-in. Además `mask` es estado del host, no del repo: no sobrevive a una reinstalación limpia salvo que `install.sh` lo aplique, lo que es más frágil que editar el unit-file.

### Decisión 2 — `PartOf=bitnodes.service` en `tcpdump-pcap.service` se mantiene

`tcpdump-pcap.service` tiene `PartOf=bitnodes.service`. `PartOf` solo propaga `stop`/`restart` (si paras bitnodes, se para tcpdump), **no `start`**. Es benigno y de hecho deseable: si alguien arranca tcpdump manualmente, se parará limpiamente cuando se reinicie el crawler, sin quedar huérfano. Se deja como está.

### Decisión 3 — `install.sh`: conservar el saneamiento, soltar el `disable` redundante

Hoy `install_systemd_units()` hace, tras instalar las units:

```
systemctl stop    tcpdump-pcap.service || true
systemctl stop    pcap-cleanup.timer   || true
systemctl disable tcpdump-pcap.service ...
systemctl disable pcap-cleanup.timer   ...
pkill -f run-tcpdump.sh ...
pkill -x tcpdump        ...
```

Con el `Wants=` fuera:
- El `restart bitnodes.service` posterior ya no revive tcpdump → el orden deja de ser delicado.
- El `stop` + `pkill` se conservan: son saneamiento idempotente que mata un tcpdump que pudiera haber quedado vivo de un estado anterior (p. ej. arrancado a mano, o de antes de este fix).
- El `disable tcpdump-pcap.service` se vuelve **redundante pero inocuo**: ya no hay `WantedBy` que importe porque la unit nunca se enabló, y el `Wants=` ya no existe. Se puede dejar (defensa en profundidad: si alguien lo enabla a mano, el disable lo revierte en el siguiente deploy) o quitar. Propuesto: **dejarlo**, es una línea y documenta la intención.

`pcap-cleanup.timer` queda igual (disabled) — fuera del alcance de este fix.

## Risks / Trace-offs

- [Queda un tcpdump vivo en el momento del deploy] → El bloque `stop`/`pkill` de `install.sh` lo cubre. Y aunque sobreviviera, sale solo en ≤4 min por `-W 8`.
- [Alguien vuelve a añadir `Wants=tcpdump-pcap.service` en el futuro sin saber por qué se quitó] → Mitigado por el spec `crawler-systemd-units` (captura la regla) y un comentario en el unit-file.
- [RTT a `null`] → Esperado y aceptado (postmortem 2026-05-13). El dashboard ya degrada con gracia: el leaderboard muestra "No RTT samples yet…" y `latency_ms` es `null` con HTTP 200. Sin regresión de comportamiento, solo de datos.

## Migration Plan

1. Editar `deploy/bitnodes.service`: `Wants=network-online.target` (sin `tcpdump-pcap.service`). Añadir comentario explicando por qué.
2. Revisar `deploy/install.sh`: confirmar que el bloque tcpdump sigue siendo coherente; ajustar comentarios.
3. Commit + push. El workflow corre `install.sh` → reinstala `bitnodes.service` con el nuevo `[Unit]`, `daemon-reload`, `restart bitnodes.service`.
4. Si quedara un tcpdump vivo del estado anterior: `ssh ... 'sudo systemctl stop tcpdump-pcap.service; sudo pkill -x tcpdump'` una vez.
5. Verificar: `systemctl show bitnodes.service tcpdump-pcap.service -p ExecMainStartTimestamp` — timestamps distintos; `journalctl -u tcpdump-pcap.service` sin nuevos `Started` tras el deploy; snapshots convergen sin oscilar.

**Rollback**: revertir el commit; `install.sh` restaura el `Wants=` anterior en el siguiente deploy.

## Open Questions

- ¿Quitar también del repo el `pcap-cleanup.service`/`.timer`? Quedan disabled e inertes. Propuesto: dejarlos fuera de este fix; los barre `active-ping-rtt` junto al resto del pipeline pcap.
