# public-edge

## Purpose

Exposición pública del dashboard alt-bitnodes vía CloudFront + nginx en el EC2 de origen. Cubre TLS, dominio personalizado, aislamiento del origin, cache diferenciado, rate limiting básico y la documentación operativa del despliegue.

## Requirements

### Requirement: TLS público vía CloudFront

El sistema SHALL servir el dashboard y la API en `https://pesquisa.hacknodes.xyz` usando una distribución CloudFront con certificado ACM válido emitido en `us-east-1`.

#### Scenario: Cliente accede por HTTPS y obtiene contenido

- **WHEN** un cliente hace `GET https://pesquisa.hacknodes.xyz/`
- **THEN** la respuesta SHALL ser `200 OK` con el HTML del dashboard
- **AND** el certificado SHALL ser válido (cadena confiable, no expirado, CN/SAN incluye `pesquisa.hacknodes.xyz`)

#### Scenario: Redirección HTTP a HTTPS

- **WHEN** un cliente hace `GET http://pesquisa.hacknodes.xyz/`
- **THEN** CloudFront SHALL responder `301 Moved Permanently` apuntando al equivalente HTTPS

### Requirement: Aislamiento del origin EC2

El sistema SHALL impedir el acceso directo al EC2 desde internet salvo a través de CloudFront. El puerto `80` del EC2 SHALL estar accesible únicamente desde la prefix list `com.amazonaws.global.cloudfront.origin-facing` y SHALL exigir un header secreto `X-Origin-Auth` para procesar requests.

#### Scenario: Acceso directo al EC2 sin header secreto es rechazado

- **WHEN** un cliente arbitrario (no CloudFront, o CloudFront sin secret) hace `GET http://<ec2-ip>/`
- **THEN** nginx SHALL responder `403 Forbidden` sin llegar a invocar uvicorn

#### Scenario: Acceso con secret correcto desde IP fuera de la prefix list es rechazado a nivel de red

- **WHEN** un atacante conoce el secreto pero su IP no está en la prefix list de CloudFront
- **THEN** el Security Group SHALL descartar la conexión TCP antes de que nginx vea el request

#### Scenario: Request legítimo de CloudFront se procesa

- **WHEN** CloudFront forwardea un request con `X-Origin-Auth: <secret>` válido
- **THEN** nginx SHALL hacer proxy a `http://127.0.0.1:8000` y devolver la respuesta de uvicorn intacta

### Requirement: Cache diferenciado por tipo de ruta

El sistema SHALL configurar CloudFront para no cachear rutas dinámicas y cachear estáticos versionados.

#### Scenario: Ruta dinámica no se cachea

- **WHEN** un cliente hace `GET /` o `GET /api/<cualquier-cosa>`
- **THEN** CloudFront SHALL aplicar la política `CachingDisabled` y forwardear cada request al origin

#### Scenario: Asset estático se cachea en edge

- **WHEN** un cliente hace `GET /static/<archivo>`
- **THEN** CloudFront SHALL aplicar la política `CachingOptimized` (TTL default ~1 día)
- **AND** hits subsiguientes SHALL servirse desde edge sin tocar el origin (cabecera `X-Cache: Hit from cloudfront`)

### Requirement: Rate limiting en el origin

El nginx del EC2 SHALL aplicar rate limiting basado en la IP real del cliente (extraída de `X-Forwarded-For` poblado por CloudFront) a las rutas `/api/*`.

#### Scenario: Cliente bajo límite es servido normalmente

- **WHEN** un cliente hace menos de 20 requests/s a `/api/*`
- **THEN** todos los requests SHALL responder `200 OK`

#### Scenario: Cliente sobre límite recibe 429

- **WHEN** un cliente envía una ráfaga >40 requests/s sostenida a `/api/*`
- **THEN** los requests excedentes SHALL responder `503 Service Unavailable` (default de `limit_req`)
- **AND** la limitación SHALL aplicar por IP real, no por IP de CloudFront

### Requirement: Despliegue automatizado e idempotente

El sistema SHALL persistir la configuración de edge (nginx, CloudFront stack, secret bootstrap) en el repo, y `deploy/install.sh` SHALL poder ejecutarse repetidamente sin romper el estado.

#### Scenario: Bootstrap inicial

- **WHEN** un operador ejecuta `aws cloudformation deploy --template-file deploy/cloudformation/edge.yaml ...` con los parámetros documentados
- **THEN** AWS SHALL crear ACM cert, CloudFront distribution y SG ingress rule
- **AND** los outputs SHALL incluir el dominio CloudFront, los CNAMEs de validación ACM y el ID del SG

#### Scenario: Re-ejecutar install.sh

- **WHEN** `deploy/install.sh` corre por segunda vez en el mismo EC2
- **THEN** nginx SHALL seguir instalado y funcionando
- **AND** el secret existente en `/etc/alt-bitnodes/origin-auth.env` NO SHALL ser sobrescrito
- **AND** la config de nginx SHALL re-renderizarse desde el template (sin perder cambios manuales no soportados — si los hay, el operador lo sabe)

#### Scenario: Validación de config antes de aplicar

- **WHEN** `install.sh` escribe `/etc/nginx/sites-available/alt-bitnodes`
- **THEN** SHALL ejecutar `nginx -t` antes de `systemctl reload nginx`
- **AND** si `nginx -t` falla, install.sh SHALL salir con código no cero y no reiniciar nginx

### Requirement: Documentación operativa para DNS externo

El repo SHALL documentar los DNS records que el operador debe crear manualmente en el proveedor externo (Namecheap/GoDaddy/etc) y la secuencia de despliegue.

#### Scenario: Operador consulta el README

- **WHEN** un operador abre `deploy/README.md` para desplegar por primera vez
- **THEN** SHALL encontrar:
  - El comando exacto de `aws cloudformation deploy` con todos los parámetros
  - Los tres tipos de records DNS necesarios (validación ACM, `pesquisa.hacknodes.xyz`, `origin.hacknodes.xyz`) y dónde sacar los valores
  - El procedimiento de rotación del `OriginAuthSecret`
  - El procedimiento de rollback
