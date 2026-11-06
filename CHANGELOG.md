# Changelog de GITA

## [v0.3.0] - 2026-11-06

# 🚀 Release Notes: Arquitectura de Base de Datos (BD-03 a BD-06)

Se ha finalizado la estructuración del backend en PostgreSQL. El repositorio entra en fase de estabilidad de datos y está listo para la integración con las vistas (Frontend).

## 🛑 1. Cambios Globales y Configuraciones (settings.py)
* **ELIMINADO:** Se eliminó el archivo `db.sqlite3` y su uso quedó deprecado.
* **MODIFICADO:** Se forzó estrictamente el motor `django.db.backends.postgresql` en `settings.py`, eliminando condicionales. Ahora depende 100% de las variables del `.env` (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, etc.).
* **AÑADIDO:** Se configuraron las variables `MEDIA_URL = '/media/'` y `MEDIA_ROOT` para habilitar la carga local de evidencias.

## 🎫 2. Módulo de Tickets y Trazabilidad (apps: tickets)
* **AÑADIDO (BD-03):** Entidades `Equipo` (gestión de hardware) y `Ticket`. 
  * *Regla de Negocio:* El `Ticket` autogenera un folio secuencial (Ej: TK-00001) al guardarse.
  * *Relaciones:* Se usó `on_delete=models.PROTECT` en llaves foráneas críticas (usuarios, catálogos) para evitar pérdida de históricos.
* **AÑADIDO (BD-04):** Entidades satélite para la Tríada CIA (Confidencialidad, Integridad, Disponibilidad).
  * `Evidencia`: Incorpora validación de seguridad a nivel de servidor (Solo JPG/PNG/JPEG, límite de 5MB).
  * `Intervencion`, `Escalamiento`, `Asignacion`, `CambioEstado`: Cuentan con *timestamps* inmutables para cálculos de SLA en el futuro dashboard.
  * `Auditoria`: Modelo de logs. **Nota para admin.py:** Se sobreescribieron los permisos `has_change_permission` y `has_delete_permission` dejándolo en "Solo Lectura" absoluto.

## 📦 3. Módulo de Inventario (apps: inventario)
* **AÑADIDO (BD-05):** Entidades `Repuesto` y `MovimientoInventario`.
  * *Lógica Matemática:* Se sobreescribió el método `save()` en `MovimientoInventario`. Suma o resta automáticamente el `stock_actual` de la tabla `Repuesto` al registrar un nuevo movimiento y lanza `ValidationError` para evitar stock negativo.
  * *Regla de Negocio (Conchas de mango):* Si el movimiento es "ENTRADA", bloquea la vinculación a un ticket (es administrativo). Si es "SALIDA", hace obligatorio vincular un ticket de justificación.

## 📊 4. Datos Iniciales y Pruebas (Fixtures)
* **AÑADIDO (BD-06):** Comando personalizado `generar_mock` (`tickets/management/commands/generar_mock.py`) que fabrica 50 tickets con fechas aleatorias en el pasado para poblar el Dashboard.
* **AÑADIDO:** Archivo maestro `fixtures/datos_iniciales.json` con la exportación completa de catálogos, equipos, usuarios (con contraseña `Admin123$`) y los 50 tickets.

### 📝 Guía de Sincronización de Datos (Para el Equipo)

Para evitar problemas de base de datos vacía al conectar el Frontend, sigue las instrucciones según lo que necesites hacer:

**Caso A: Cargar los datos maestros (Para integrar Frontend hoy)**
Si acabas de hacer `git pull`, tu base de datos local necesita las tablas y los datos.
1. Verifica que tu archivo `.env` apunte a la base de datos correcta (`gita_db`).
2. Crea las tablas vacías:
   `python manage.py migrate`
3. Inyecta los catálogos y los 50 tickets de prueba pre-generados:
   `python manage.py loaddata fixtures/datos_iniciales.json`
*(Nota: Puedes loguearte al sistema usando el usuario `cliente_test` con la contraseña `Admin123$`)*.

**Caso B: Usar el Script para regenerar datos desde cero**
Si por alguna razón tu base de datos se corrompe, o necesitas recalcular las fechas de los 50 tickets tomando como base el día de hoy, usa el script generador:
1. Ejecuta el script (⚠️ **Advertencia:** esto limpiará las tablas actuales y creará data nueva):
   `python manage.py generar_mock`
2. Si los datos que generaste son importantes y quieres compartirlos con nosotros, toma una "foto" exportándolos al archivo JSON maestro:
   `python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission --indent 4 > fixtures/datos_iniciales.json`