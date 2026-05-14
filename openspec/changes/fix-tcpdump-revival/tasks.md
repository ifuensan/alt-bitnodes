## 1. Romper la dependencia

- [x] 1.1 `deploy/bitnodes.service`: `Wants=network-online.target tcpdump-pcap.service` → `Wants=network-online.target`
- [x] 1.2 Comentario en el `[Unit]` de `bitnodes.service` explicando por qué tcpdump-pcap NO está en `Wants=` (postmortem 2026-05-13 + este cambio)

## 2. Sanear install.sh

- [x] 2.1 Bloque tcpdump de `install_systemd_units()`: `stop` + `pkill` se conservan como saneamiento idempotente; comentario reescrito — el fix real está en `bitnodes.service`, este bloque solo limpia estados antiguos
- [x] 2.2 `disable tcpdump-pcap.service` se mantiene como defensa en profundidad (comentado como redundante pero inocuo)

## 3. Despliegue y verificación

- [ ] 3.1 Commit + push (workflow Deploy to EC2 corre install.sh, reinstala `bitnodes.service` con el nuevo `[Unit]`, daemon-reload, restart)
- [ ] 3.2 Si quedara un tcpdump vivo del estado anterior: `ssh ... 'sudo systemctl stop tcpdump-pcap.service; sudo pkill -x tcpdump'` una vez
- [ ] 3.3 Verificar: `systemctl show bitnodes.service tcpdump-pcap.service -p ExecMainStartTimestamp` → timestamps distintos
- [ ] 3.4 Verificar: `journalctl -u tcpdump-pcap.service --since <deploy>` → sin nuevos `Started` tras el deploy
- [ ] 3.5 Verificar: esperar ~15 min y confirmar que los snapshots convergen a ~4000+ sin oscilar (`ls -t ~/bitnodes/data/export/f9beb4d9/*.json | head -6`)
