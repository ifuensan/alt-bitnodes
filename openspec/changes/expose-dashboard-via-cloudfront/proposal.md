## Why

El dashboard alt-bitnodes está corriendo en una t4g.medium en AWS, pero `uvicorn` solo escucha en `127.0.0.1:8000` y no es accesible desde fuera de la instancia. Para que la API y el dashboard sean realmente públicos (sucesor de bitnodes.io) hay que ponerlos detrás de una capa con TLS, dominio público y al menos un mínimo de protección contra abuso. Hacerlo vía CloudFront aprovecha ACM gratuito, CDN para los estáticos y aísla el EC2 de tráfico arbitrario de internet.

## What Changes

- Nuevo reverse proxy `nginx` en el EC2 escuchando en `:80`, proxy a `127.0.0.1:8000`, validando un header secreto `X-Origin-Auth` inyectado por CloudFront.
- Rate limiting básico en nginx (`limit_req_zone`) sobre la API para mitigar abuso.
- Nueva distribución CloudFront delante de la app con cache diferenciado: `OFF` para rutas dinámicas (`/`, `/api/*`), `ON` para `/static/*`.
- Certificado ACM en `us-east-1` para `pesquisa.hacknodes.xyz`, validado por DNS.
- Origin de CloudFront apuntando a `origin.hacknodes.xyz` (A record nuevo al IP del EC2), no a la IP directa.
- Security Group del EC2 restringido en puerto `80` a la prefix list `com.amazonaws.global.cloudfront.origin-facing`; puerto `8000` no expuesto.
- Plantilla CloudFormation (`deploy/cloudformation/edge.yaml`) que crea ACM + CloudFront + SG rule. DNS records (validación ACM, `pesquisa`, `origin`) los crea el usuario manualmente en su proveedor externo (Namecheap/GoDaddy/etc).
- `deploy/install.sh` instala y configura nginx (sitio, header secret leído de `/etc/alt-bitnodes/origin-auth.env`), añade systemd unit / habilita servicio.
- `deploy/README.md` documenta el bootstrap CloudFormation y los DNS records que el operador debe crear.

## Capabilities

### New Capabilities
- `public-edge`: Exposición pública del dashboard vía CloudFront + nginx, incluyendo TLS, dominio personalizado, autenticación de origin y rate limiting básico.

### Modified Capabilities
<!-- ninguna; los specs existentes (latency-api, rankings-api, rtt-history, dashboard-bar-charts) no cambian sus requisitos funcionales -->

## Impact

- **Nuevo**: `deploy/cloudformation/edge.yaml`, `deploy/nginx/alt-bitnodes.conf` (template), entrada en `install.sh`.
- **Modificado**: `deploy/install.sh` (instala nginx, copia config, genera secret), `deploy/README.md` (instrucciones DNS + bootstrap CloudFormation).
- **Sin cambios**: `app.py`, `deploy/alt-bitnodes.service` (sigue ligando a 127.0.0.1:8000).
- **Operacional**: el operador debe crear 3 DNS records en el proveedor externo (validación ACM, `pesquisa`, `origin`) y desplegar la stack CloudFormation una vez.
- **Coste**: CloudFront free tier cubre ~1 TB/mes inbound y 10M requests; tráfico esperado del dashboard cabe dentro del free tier inicial. ACM es gratis. nginx es ligero (~10 MB RES).
- **Seguridad**: puerto 80 deja de estar abierto al mundo (solo prefix list de CloudFront + header secreto). Sin WAF en esta fase — se puede añadir luego sin tocar el resto.
