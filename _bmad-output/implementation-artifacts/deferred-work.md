
## Deferred from: code review of expose-latent-crawler-data (2026-07-23)

- Serie diaria de services crece sin límite (~365 entradas/año, ~40KB): añadir cap o paginación si algún día pesa.
- Colector re-parsea todos los ficheros de bloque (~4.3k a 30 días) dos veces por corrida de 10 min: usar mtime o timestamp en el nombre si el coste crece.
- `/api/v1/stats/window` es la única ruta v1 sin trailing slash: inconsistencia pre-existente; cambiarla rompería consumidores — documentar o alias.
