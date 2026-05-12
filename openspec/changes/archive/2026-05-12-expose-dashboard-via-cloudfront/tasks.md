## 1. Template nginx en el repo

- [x] 1.1 Crear `deploy/nginx/alt-bitnodes.conf.template` con: `server_name __SERVER_NAME__`, `listen 80`, `set_real_ip_from` para la prefix list de CloudFront, `real_ip_header X-Forwarded-For`, validación `if ($http_x_origin_auth != "__SECRET__") { return 403; }`, `proxy_pass http://127.0.0.1:8000`, headers de proxy estándar (Host, X-Forwarded-Proto, etc.).
- [x] 1.2 Añadir `limit_req_zone $binary_remote_addr zone=api:10m rate=20r/s;` a nivel `http` (en snippet `/etc/nginx/conf.d/alt-bitnodes-limits.conf`) y `limit_req zone=api burst=40 nodelay;` dentro de `location /api/`.
- [x] 1.3 Añadir cabeceras de seguridad básicas (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) en el bloque server.
- [x] 1.4 Lograr que `nginx -t` pase contra el template renderizado en una sandbox local (sustituir vars con valores dummy y validar).

## 2. install.sh: instalación y configuración de nginx

- [x] 2.1 Añadir `nginx` a la lista de paquetes apt en `install.sh` (línea `apt install -y ...`).
- [x] 2.2 Añadir paso `bootstrap_origin_secret`: crea `/etc/alt-bitnodes/` modo 0750, genera `/etc/alt-bitnodes/origin-auth.env` con `openssl rand -hex 32` SOLO si no existe; modo 0600 root:root; export `ORIGIN_AUTH_SECRET=...`.
- [x] 2.3 Añadir paso `configure_nginx`: copiar `deploy/nginx/alt-bitnodes.conf.template` a `/etc/nginx/sites-available/alt-bitnodes`, sustituir `__SERVER_NAME__` (`origin.hacknodes.xyz pesquisa.hacknodes.xyz _`) y `__SECRET__` con `sed`. Copiar `deploy/nginx/alt-bitnodes-limits.conf` a `/etc/nginx/conf.d/`. Symlink `sites-enabled/alt-bitnodes`. Borrar `sites-enabled/default` si existe.
- [x] 2.4 Ejecutar `nginx -t` y abortar el script si falla. Tras éxito, `systemctl enable nginx && systemctl reload nginx`.
- [x] 2.5 Verificar que un re-run del script no regenera el secret ni rompe nginx (idempotencia manual o test con `bash -x`).

## 3. CloudFormation template

- [x] 3.1 Crear `deploy/cloudformation/edge.yaml` con `AWSTemplateFormatVersion`, descripción y parameters: `DomainName`, `OriginHostname`, `OriginAuthSecret` (NoEcho=true), `OriginEc2SecurityGroupId` (al que añadir el ingress rule).
- [x] 3.2 Recurso `AWS::CertificateManager::Certificate` con `ValidationMethod: DNS` para `DomainName`. Output `AcmCertificateArn` y `AcmValidationCnames`.
- [x] 3.3 Recurso `AWS::CloudFront::Distribution`: origin con `DomainName: !Ref OriginHostname`, `CustomOriginConfig.OriginProtocolPolicy: http-only`, `OriginCustomHeaders: [{ HeaderName: X-Origin-Auth, HeaderValue: !Ref OriginAuthSecret }]`. Aliases: `[!Ref DomainName]`. ViewerCertificate con el ACM cert + `SslSupportMethod: sni-only` + `MinimumProtocolVersion: TLSv1.2_2021`. Default behavior: managed `CachingDisabled`, `AllowedMethods: [GET, HEAD, OPTIONS]`, `ViewerProtocolPolicy: redirect-to-https`. Cache behavior para `/static/*`: managed `CachingOptimized`. Output `CloudFrontDomain`.
- [x] 3.4 Recurso `AWS::EC2::SecurityGroupIngress` que abre puerto 80 al `OriginEc2SecurityGroupId` desde la managed prefix list `com.amazonaws.global.cloudfront.origin-facing`. Usar `SourcePrefixListId` con `!FindInMap` o `AWS::EC2::PrefixList` lookup.
- [x] 3.5 Validar el template: validado de facto por el `aws cloudformation deploy` exitoso (CREATE_COMPLETE). Tras el primer intento se eliminó un `DomainValidationOptions` vacío que ACM rechazaba.

## 4. Documentación

- [x] 4.1 Sección nueva en `deploy/README.md`: "Exposición pública (CloudFront + nginx)". Incluir prerequisitos (AWS CLI configurado, permisos), comando `aws cloudformation deploy ...` con todos los parameter-overrides.
- [x] 4.2 Subsección "DNS records a crear en el proveedor externo" con tabla: type/name/value para (a) validación ACM, (b) `pesquisa.hacknodes.xyz` CNAME → CloudFront, (c) `origin.hacknodes.xyz` A → IP del EC2.
- [x] 4.3 Subsección "Rotación del OriginAuthSecret" con los 4 pasos (generar nuevo secret, update stack con override, actualizar `/etc/alt-bitnodes/origin-auth.env` en EC2, `systemctl reload nginx`).
- [x] 4.4 Subsección "Rollback" con `aws cloudformation delete-stack`, instrucción para deshabilitar nginx (`systemctl disable --now nginx`) y limpiar DNS records.
- [x] 4.5 Subsección "Smoke tests post-deploy" con 3 comandos `curl` (HTTPS público responde 200, HTTP directo al EC2 responde 403, HTTP directo con secret responde 200).

## 5. Despliegue y validación

- [x] 5.1 Operador genera el secret local: `openssl rand -hex 32 > /tmp/origin-secret`. *(En su lugar: install.sh lo generó en el EC2 — leer con `sudo sed -n "s/^ORIGIN_AUTH_SECRET=//p" /etc/alt-bitnodes/origin-auth.env`.)*
- [x] 5.2 Operador despliega la stack: `aws cloudformation deploy ...` → `CREATE_COMPLETE` tras el fix de `DomainValidationOptions`.
- [x] 5.3 Operador consulta outputs y crea los CNAMEs de validación ACM en el proveedor DNS.
- [x] 5.4 Tras `CREATE_COMPLETE`, operador crea record A `origin.hacknodes.xyz → 100.50.100.201` y CNAME `pesquisa.hacknodes.xyz → <CloudFrontDomain>` en Namecheap.
- [x] 5.5 Secret puesto en EC2 por `install.sh` (no fue necesario inyectarlo vía SSH; CloudFormation recibió el secret leyéndolo del EC2).
- [x] 5.6 Merge a `main` → workflow `Deploy to EC2` corre `install.sh` → nginx instalado y configurado.
- [x] 5.7 Smoke tests: `GET https://pesquisa.hacknodes.xyz/` → 200; HTTP directo al EC2 sin header → SG bloquea (mejor que 403); HTTP directo con header desde el propio EC2 → 200.
- [x] 5.8 Verificar cache: `curl -sI https://pesquisa.hacknodes.xyz/static/app.css` → `x-cache: Hit from cloudfront`, age aumenta entre hits sucesivos.
- [x] 5.9 Verificar rate limit: 500 reqs con 50 en paralelo → 140×200 + 360×503. `limit_req` funcionando correctamente.
- [x] 5.10 No aplica: el secret nunca estuvo en `/tmp` local (se generó directamente en el EC2).

## 6. Cierre

- [x] 6.1 Configurar billing alarm de CloudWatch en 5 USD/mes para detectar consumos anómalos de CloudFront. *(SNS topic `billing-alerts` → `support@hacknodes.com`, alarma `billing-over-5usd` creada; INSUFFICIENT_DATA hasta que llegue el primer datapoint de billing en ~6-12h)*.
- [x] 6.2 Confirmar que el dashboard responde por dominio público y que nada quedó accesible directo por IP sin secret. *(GET https://pesquisa.hacknodes.xyz/ → 200; conexión TCP directa al EC2:80 bloqueada por SG)*.
- [x] 6.3 Archivar el change con `/opsx:archive` una vez validado en producción.
