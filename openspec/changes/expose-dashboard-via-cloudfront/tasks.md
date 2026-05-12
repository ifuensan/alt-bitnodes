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
- [ ] 3.5 Validar el template: `aws cloudformation validate-template --template-body file://deploy/cloudformation/edge.yaml` (la sesión AWS local expiró; YAML estructural ya validado con PyYAML; pendiente correr el comando real antes del deploy).

## 4. Documentación

- [x] 4.1 Sección nueva en `deploy/README.md`: "Exposición pública (CloudFront + nginx)". Incluir prerequisitos (AWS CLI configurado, permisos), comando `aws cloudformation deploy ...` con todos los parameter-overrides.
- [x] 4.2 Subsección "DNS records a crear en el proveedor externo" con tabla: type/name/value para (a) validación ACM, (b) `pesquisa.hacknodes.xyz` CNAME → CloudFront, (c) `origin.hacknodes.xyz` A → IP del EC2.
- [x] 4.3 Subsección "Rotación del OriginAuthSecret" con los 4 pasos (generar nuevo secret, update stack con override, actualizar `/etc/alt-bitnodes/origin-auth.env` en EC2, `systemctl reload nginx`).
- [x] 4.4 Subsección "Rollback" con `aws cloudformation delete-stack`, instrucción para deshabilitar nginx (`systemctl disable --now nginx`) y limpiar DNS records.
- [x] 4.5 Subsección "Smoke tests post-deploy" con 3 comandos `curl` (HTTPS público responde 200, HTTP directo al EC2 responde 403, HTTP directo con secret responde 200).

## 5. Despliegue y validación

- [ ] 5.1 Operador genera el secret local: `openssl rand -hex 32 > /tmp/origin-secret`.
- [ ] 5.2 Operador despliega la stack: `aws cloudformation deploy --template-file deploy/cloudformation/edge.yaml --stack-name alt-bitnodes-edge --parameter-overrides DomainName=pesquisa.hacknodes.xyz OriginHostname=origin.hacknodes.xyz OriginAuthSecret=$(cat /tmp/origin-secret) OriginEc2SecurityGroupId=<sg-id> --region us-east-1 --capabilities CAPABILITY_NAMED_IAM`.
- [ ] 5.3 Operador consulta outputs y crea los CNAMEs de validación ACM en el proveedor DNS.
- [ ] 5.4 Tras `CREATE_COMPLETE`, operador crea record A `origin.hacknodes.xyz → 100.50.100.201` y CNAME `pesquisa.hacknodes.xyz → <CloudFrontDomain>`.
- [ ] 5.5 Operador escribe el secret en el EC2 vía SSH: `echo "ORIGIN_AUTH_SECRET=$(cat /tmp/origin-secret)" | ssh ... "sudo tee /etc/alt-bitnodes/origin-auth.env" && ssh ... "sudo chmod 600 /etc/alt-bitnodes/origin-auth.env"`.
- [ ] 5.6 Merge a `main` → workflow `Deploy to EC2` corre install.sh → nginx instalado y configurado.
- [ ] 5.7 Ejecutar smoke tests: `curl -fsSI https://pesquisa.hacknodes.xyz/` (200), `curl -sI http://100.50.100.201/` (403), `curl -sI -H "X-Origin-Auth: $(cat /tmp/origin-secret)" http://100.50.100.201/` (200).
- [ ] 5.8 Verificar cache: `curl -sI https://pesquisa.hacknodes.xyz/static/<algún-asset>` debe incluir `X-Cache: Miss/Hit from cloudfront` y `Cache-Control` agresivo.
- [ ] 5.9 Verificar rate limit: ráfaga `for i in {1..100}; do curl -so /dev/null -w "%{http_code}\n" https://pesquisa.hacknodes.xyz/api/<endpoint>; done | sort | uniq -c` — esperar mezcla de 200 y 503.
- [ ] 5.10 Borrar `/tmp/origin-secret` local tras confirmar todo.

## 6. Cierre

- [ ] 6.1 Configurar billing alarm de CloudWatch en 5 USD/mes para detectar consumos anómalos de CloudFront.
- [ ] 6.2 Confirmar que el dashboard responde por dominio público y que nada quedó accesible directo por IP sin secret.
- [ ] 6.3 Archivar el change con `/opsx:archive` una vez validado en producción.
