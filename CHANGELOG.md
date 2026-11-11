# Changelog de GITA

## [v0.3.0] - 2026-11-06
**Autor:** Manuel

### 🚀 Arquitectura de Base de Datos Completa (BD-03 a BD-06)
El repositorio entra en fase de estabilidad de datos en PostgreSQL y está listo para la integración con el frontend.

#### ✨ Añadido
- **Tickets & Equipos:** Entidades con autogeneración de folios (BD-03).
- **Trazabilidad CIA:** Modelos inmutables para Intervención, Escalamiento y Auditoría (BD-04).
- **Inventario:** Entidad Repuesto con validación matemática de stock (BD-05).
- **Fixtures:** Script `generar_mock.py` y archivo maestro `datos_iniciales.json` (BD-06).

#### 🔧 Modificado
- **Configuración (`settings.py`):** Forzado el motor de PostgreSQL y la integración estricta con el archivo `.env`.

#### 🗑️ Eliminado
- **Bases Locales:** Depreciación y eliminación absoluta del archivo `db.sqlite3`.

---

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