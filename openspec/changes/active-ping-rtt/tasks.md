## 1. Fork ifuensan/bitnodes — ping.py registra RTT

- [ ] 1.1 Abrir `ping.py` y localizar el emparejamiento `ping`→`pong`: confirmar si ya guarda el timestamp de envío del `ping` o hay que añadirlo
- [ ] 1.2 Al recibir el `pong` que casa, calcular `rtt_ms = now - ping_sent_ts` y escribir a `rtt:<addr>-<port>` (`lpush` + `ltrim` a `rtt_count` + `expire` a `ttl`), portando los valores de `conf/cache_inv.*.conf`
- [ ] 1.3 Añadir/ajustar la config de `ping.py` con `rtt_count` y `ttl` (o leerlos de donde corresponda en el crawler)
- [ ] 1.4 Probar en local: arrancar `ping.py`, confirmar que `rtt:*` se puebla en Redis con el formato esperado

## 2. Fork ifuensan/bitnodes — retirar el pipeline pcap

- [ ] 2.1 Quitar las 3 líneas de `cache_inv` de `run-bitnodes.sh`
- [ ] 2.2 Borrar `cache_inv.py`, `pcap.py`, `start_pcap.sh`, `conf/cache_inv.*`
- [ ] 2.3 Commit + push del fork; desplegar en EC2
- [ ] 2.4 Verificar en el EC2: `rtt:*` se sigue poblando (ahora desde `ping.py`), `cache_inv` ya no corre, `bitnodes.service` arranca limpio

## 3. alt-bitnodes — borrar units pcap

- [ ] 3.1 Borrar `deploy/tcpdump-pcap.service`, `deploy/run-tcpdump.sh`, `deploy/pcap-cleanup.service`, `deploy/pcap-cleanup.timer`
- [ ] 3.2 `deploy/install.sh`: quitar la instalación de esas units (líneas `install -m 0644 ... pcap ...`), el sed de placeholders sobre ellas, y todo el bloque de `stop`/`disable`/`pkill` de tcpdump
- [ ] 3.3 Confirmar que `install.sh` ya no referencia `run-tcpdump.sh` ni el dir de pcaps

## 4. alt-bitnodes — documentación

- [ ] 4.1 `deploy/README.md`: quitar referencias al pipeline pcap; describir que el RTT viene de pings activos
- [ ] 4.2 `deploy/TUNING.md`: actualizar la sección de oscilación de snapshots (la causa #2 "tcpdump" ya no aplica — el sniffer no existe)
- [ ] 4.3 `docs/follow-ups.md`: cerrar el item "Replace pcap-based RTT with active pings from `cache_inv`"

## 5. Despliegue y verificación

- [ ] 5.1 Commit + push de alt-bitnodes (workflow corre install.sh sin nada de pcap)
- [ ] 5.2 Limpiar `~/bitnodes/data/pcap/f9beb4d9/` en el EC2 una vez (pcaps muertos, ~250 MB)
- [ ] 5.3 Verificar: `latency_ms` no-null en `/api/v1/snapshots/latest/`, leaderboard con filas
- [ ] 5.4 Verificar: `journalctl` sin `tcpdump-pcap`, sin proceso `tcpdump`, sin `cache_inv`
- [ ] 5.5 Verificar: snapshots estables ~4000+ sin oscilación durante ≥30 min
- [ ] 5.6 Verificar: la height de bloque por nodo vuelve a poblarse en el snapshot (el sweep ahora converge)
