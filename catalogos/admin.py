from django.contrib import admin
from .models import Categoria, Prioridad, EstadoTicket, SLA, ModalidadAtencion


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre', 'activo']
    search_fields = ['nombre']


@admin.register(Prioridad)
class PrioridadAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre', 'nivel']
    ordering = ['nivel']


@admin.register(EstadoTicket)
class EstadoTicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre', 'es_inicial', 'es_final']


@admin.register(SLA)
class SLAAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre', 'tiempo_resolucion_horas']


@admin.register(ModalidadAtencion)
class ModalidadAtencionAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre']