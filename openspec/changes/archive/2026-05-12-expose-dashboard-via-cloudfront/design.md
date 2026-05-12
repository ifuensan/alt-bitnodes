## Context

El stack alt-bitnodes está hoy compuesto por:
- `bitnodes.service`: ejecuta el crawler upstream (crawl/ping/resolve/export/seeder/cache_inv) → Redis + ficheros JSON en `data/export/`.
- `alt-bitnodes.service`: `uvicorn app:app --host 127.0.0.1 --port 8000` (FastAPI + Jinja).
- `redis-server.service`, `tor.service`, `tcpdump-pcap.service`.

Despliegue automatizado vía `deploy/install.sh` + GitHub Actions workflow (`Deploy to EC2`). La instancia es **t4g.medium (ARM, Ubuntu 24.04) en `us-east-1`**, IP `100.50.100.201`.

El dominio público objetivo es `pesquisa.hacknodes.xyz`. El DNS está en un proveedor externo (Namecheap/GoDaddy/etc) — no en Route 53 —, así que los records se gestionan manualmente. ACM en `us-east-1` (requisito de CloudFront).

Decisión de stack ya tomada en `proposal.md`: **CloudFront → nginx:80 (EC2) → uvicorn:8000**, sin ALB, sin WAF en esta fase.

## Goals / Non-Goals

**Goals:**
- Servir `https://pesquisa.hacknodes.xyz` con cert válido y HSTS razonable.
- Aislar el EC2: el puerto 80 solo es alcanzable desde la prefix list de CloudFront, y solo procesa requests con el header secreto correcto.
- Cachear estáticos (`/static/*`) en edge; rutas dinámicas pasan al origin sin cache.
- Rate limit básico en nginx para mitigar abuso volumétrico.
- Idempotencia: `deploy/install.sh` debe poder re-correrse sin romper nada.
- Documentar lo manual (records DNS, despliegue de CloudFormation, rotación del secret).

**Non-Goals:**
- WAF gestionado (se evaluará después).
- Logging centralizado de CloudFront (logs S3/Athena) — fuera de fase 1.
- Autenticación de usuarios — la app es pública por diseño.
- Migración a ALB o Route 53.
- Multi-región / failover.
- IPv6 en el origin (CloudFront sí soporta IPv6 hacia el cliente; el path EC2 sigue IPv4).

## Decisions

### 1. Reverse proxy: nginx (no Caddy, no proxy en FastAPI)
**Why:** nginx es ligero, conocido y suficiente. Caddy aporta auto-TLS pero acá TLS lo maneja CloudFront, así que el valor diferencial desaparece. Hacer el proxy en FastAPI/Starlette es posible pero mezcla responsabilidades y no da rate limiting.

**Alternativas consideradas:** Caddy (descartado por TLS redundante), Traefik (overkill para un solo backend), serving directo desde uvicorn en `0.0.0.0:80` (descartado: rompe el principio de separar terminación HTTP del runtime de la app).

### 2. Defensa en profundidad: prefix list + header secreto
**Why:** La prefix list `com.amazonaws.global.cloudfront.origin-facing` cubre las IPs de CloudFront, pero esos rangos los comparten todos los clientes de CloudFront. Cualquiera con cuenta AWS podría montar una distribution que apunte a nuestro origin si supiera la IP. El header secreto cierra esa puerta: nginx solo responde si `X-Origin-Auth` coincide.

**Rotación:** secret almacenado en `/etc/alt-bitnodes/origin-auth.env` (modo 0600, owner root). Para rotar: cambiar valor en CloudFormation parameter, redeploy stack (CloudFront actualiza el header), luego actualizar el archivo en EC2 y `systemctl reload nginx`. Documentado en `deploy/README.md`.

**Alternativa considerada:** mTLS entre CloudFront y origin (CloudFront 2024 lo soporta). Más seguro pero añade complejidad operativa (gestión de cert cliente, rotación). Se puede migrar más adelante si el secret resulta insuficiente.

### 3. Cache policies de CloudFront
- **`/static/*`** → managed `CachingOptimized` (TTL ~1 día). Los assets están versionados por el commit SHA en los nombres (ya hay SRI hashes pinned), así que cachear agresivamente es seguro.
- **Resto** (`/`, `/api/*`) → managed `CachingDisabled`. Los datos cambian con cada snapshot del crawler (~10 min), y queremos respuestas frescas. Si en el futuro necesitamos cachear `/api/*` con TTL corto, se crea una behavior dedicada con `CachingPolicy` custom (TTL 60s, varía por query string).
- **Métodos**: GET/HEAD/OPTIONS. La API actual es read-only.

### 4. Origin: subdominio `origin.hacknodes.xyz`, no IP cruda
**Why:** Si hay que cambiar el EC2 (resize, recrear), basta con repuntar el A record. CloudFront no necesita actualización. Además es lo que recomienda AWS para origens fuera de su ecosistema.

### 5. Validación ACM por DNS
**Why:** Es el único método soportado para certs públicos sin email forwarding. CloudFormation expone los CNAMEs de validación como outputs; el operador los crea en su proveedor DNS antes de que la stack termine (la stack queda en `CREATE_IN_PROGRESS` esperando validación, ~15 min máx).

### 6. CloudFormation, no Terraform
**Why:** Elegido por el usuario. Ventajas en este caso: sin estado externo (S3/DynamoDB), sin instalar tooling extra (`aws` CLI ya está), rollback nativo, integración con consola para inspeccionar.

**Trade-off:** menos portable si más adelante hay multi-cloud; aceptable por ahora.

### 7. Rate limit en nginx
- Zone `api` (10 MB shared memory) con `rate=20r/s` por `$binary_remote_addr` real (extraído del header `X-Forwarded-For` que setea CloudFront).
- Burst 40, `nodelay`.
- Solo aplica a `location /api/`. El dashboard HTML no lo necesita (CloudFront cachea estáticos, y los hits a `/` son baratos).
- Si pega un cliente legítimo (ej. nuestros propios scripts), se sube fácil con `nginx -t && systemctl reload nginx`.

**Importante:** `$binary_remote_addr` por defecto sería la IP de CloudFront. Para que el rate limit funcione por cliente real hay que usar `ngx_http_realip_module` con `set_real_ip_from <prefix-list CloudFront>` + `real_ip_header X-Forwarded-For`. nginx en Ubuntu 24.04 viene con el módulo compilado.

### 8. Idempotencia en install.sh
- nginx config se escribe desde template con `sed` (sustituye `__SECRET__`, `__SERVER_NAME__`).
- El secret se genera con `openssl rand -hex 32` **solo si no existe** el fichero `/etc/alt-bitnodes/origin-auth.env`. Para rotar, el operador lo borra antes de correr install.sh o lo edita a mano.
- `systemctl enable --now nginx` siempre.
- Validación con `nginx -t` antes de reload.

## Risks / Trade-offs

- **[Risk]** El secret del header acaba en el template de CloudFormation como parameter `NoEcho`. Si alguien tiene acceso a la cuenta AWS puede leerlo. → **Mitigación:** rotación periódica documentada; usar IAM mínimo para acceso a CloudFormation; futuro: mover a AWS Secrets Manager y referenciar dynamically.
- **[Risk]** Prefix list `com.amazonaws.global.cloudfront.origin-facing` cubre IPs compartidas. Sin el header secreto, cualquier cuenta AWS podría apuntar al origin. → **Mitigación:** ya cubierto por el header secreto.
- **[Risk]** Coste de CloudFront si tráfico explota. → **Mitigación:** free tier cubre 1 TB/mes y 10M req; configurar billing alarm en 5 USD/mes; rate limit en nginx evita amplificación desde un cliente.
- **[Risk]** Cambio en `app.py` que añade un endpoint `/admin` o similar — sin auth seguiría siendo público. → **Mitigación:** convención: si se añaden endpoints sensibles, gatearlos con un header/token en la app o bloquear en nginx; fuera del scope de este change.
- **[Risk]** Validación ACM se queda colgada si el operador no crea los DNS records a tiempo. → **Mitigación:** README explícito con orden de pasos y un timeout claro (ACM aborta a las 72h, pero la práctica es resolver en <1h).
- **[Risk]** Cliente legítimo del crawler (Mojo o scripts internos) acaba ratelimited en producción. → **Mitigación:** rate=20r/s burst=40 con nodelay deja ~60 req en una ráfaga corta; suficiente para un cliente educado.
- **[Trade-off]** Sin logs CloudFront → cuesta investigar abuso. Aceptable en fase 1; activable con un cambio menor más adelante (output S3 bucket).
- **[Trade-off]** Sin WAF → posibles requests maliciosas pasan a nginx. nginx + FastAPI son resilientes a lo trivial; rate limit absorbe lo volumétrico.

## Migration Plan

1. Merge del change a `main`.
2. Operador genera el `OriginAuthSecret` localmente (`openssl rand -hex 32`).
3. `aws cloudformation deploy --template-file deploy/cloudformation/edge.yaml --stack-name alt-bitnodes-edge --parameter-overrides OriginAuthSecret=<secret> DomainName=pesquisa.hacknodes.xyz OriginHostname=origin.hacknodes.xyz --region us-east-1 --capabilities CAPABILITY_NAMED_IAM`.
4. Stack queda en `CREATE_IN_PROGRESS` esperando validación ACM. Operador lee outputs `AcmValidationCnames`, los crea en su DNS provider.
5. Stack termina (~10–15 min). Outputs incluyen `CloudFrontDomain` (ej. `dxxxx.cloudfront.net`) y `OriginSecurityGroupId`.
6. Operador crea en DNS provider:
   - A record `origin.hacknodes.xyz` → `100.50.100.201`
   - CNAME `pesquisa.hacknodes.xyz` → `dxxxx.cloudfront.net`
7. Operador escribe `/etc/alt-bitnodes/origin-auth.env` en EC2 con el mismo secret (puede hacerse vía SSH antes o después; nginx solo lo necesita al recibir requests).
8. Push del repo → workflow `Deploy to EC2` corre `install.sh` → instala nginx, copia config, `systemctl reload`.
9. Smoke test: `curl -I https://pesquisa.hacknodes.xyz/` (debe responder 200), `curl -I http://100.50.100.201/` (debe responder 403 — sin header secreto), `curl -I -H "X-Origin-Auth: <secret>" http://100.50.100.201/` (200).

**Rollback:** `aws cloudformation delete-stack --stack-name alt-bitnodes-edge`. Quitar la línea de nginx de `install.sh`. `systemctl stop nginx && apt purge nginx`. DNS records se pueden dejar (apuntando a CloudFront muerto no causa daño) o borrar manualmente. uvicorn sigue accesible en `127.0.0.1:8000` como antes — la app no se afecta.

## Open Questions

- ¿Conviene activar **gzip / brotli** en nginx, o dejar que CloudFront comprima? CloudFront comprime por defecto si el response es <10 MB y `Cache-Control` lo permite — probablemente suficiente. Pendiente confirmar con un benchmark tras el despliegue.
- ¿Logging? Decisión: por ahora solo `access.log` y `error.log` locales de nginx (rotación con `logrotate` default de Ubuntu). Si surge necesidad de observabilidad fina, se añade integración con CloudWatch Logs (ya hay agente instalado).
