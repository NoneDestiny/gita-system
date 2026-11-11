#!/usr/bin/env bash
# Salir si hay un error
set -o errexit

# Instalar dependencias
pip install -r requirements.txt

# Recolectar archivos estáticos (CSS, JS) para que no den error 404
python manage.py collectstatic --noinput

# Aplicar las migraciones a la base de datos de Supabase
python manage.py migrate