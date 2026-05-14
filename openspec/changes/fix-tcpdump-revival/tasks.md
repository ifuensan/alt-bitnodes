## 1. Romper la dependencia

- [x] 1.1 `deploy/bitnodes.service`: `Wants=network-online.target tcpdump-pcap.service` → `Wants=network-online.target`
- [x] 1.2 Comentario en el `[Unit]` de `bitnodes.service` explicando por qué tcpdump-pcap NO está en `Wants=` (postmortem 2026-05-13 + este cambio)

## 2. Sanear install.sh

- [x] 2.1 Bloque tcpdump de `install_systemd_units()`: `stop` + `pkill` se conservan como saneamiento idempotente; comentario reescrito — el fix real está en `bitnodes.service`, este bloque solo limpia estados antiguos
- [x] 2.2 `disable tcpdump-pcap.service` se mantiene como defensa en profundidad (comentado como redundante pero inocuo)

## 3. Despliegue y verificación

- [x] 3.1 Commit + push (commit `20aec6b`, workflow Deploy to EC2 → success; install.sh reinstaló `bitnodes.service` con el nuevo `[Unit]`)
- [x] 3.2 No hizo falta matar tcpdump a mano — `install.sh` (stop+pkill) dejó el host limpio
- [x] 3.3 `ExecMainStartTimestamp`: bitnodes `17:46:18`, tcpdump-pcap **vacío** (no arrancó) — antes coincidían al segundo
- [x] 3.4 `journalctl -u tcpdump-pcap.service --since <deploy>` → sin nuevos `Started` ✓
- [x] 3.5 Snapshots monótonos crecientes sin oscilar: 3964 → 4028 → 4054 → 4075
