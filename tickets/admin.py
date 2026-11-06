from django.contrib import admin
from .models import (
    Equipo, 
    Ticket, 
    Evidencia, 
    Intervencion, 
    Escalamiento, 
    Asignacion, 
    CambioEstado, 
    Auditoria
)

@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ('serial', 'marca', 'modelo', 'fecha_registro')
    search_fields = ('serial', 'marca', 'modelo')

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('folio', 'asunto', 'usuario', 'tecnico_asignado', 'estado', 'fecha_creacion')
    list_filter = ('estado', 'prioridad', 'categoria')
    search_fields = ('folio', 'asunto', 'descripcion')
    readonly_fields = ('folio', 'fecha_creacion', 'fecha_asignacion', 'fecha_cierre')

# --- REGISTRO DE MODELOS SATÉLITE (BD-04) ---

@admin.register(Evidencia)
class EvidenciaAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'archivo', 'subido_por', 'fecha_subida')
    list_filter = ('fecha_subida',)
    search_fields = ('ticket__folio', 'subido_por__username')
    readonly_fields = ('fecha_subida',)

@admin.register(Intervencion)
class IntervencionAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'tecnico', 'tiempo_invertido_minutos', 'fecha_registro')
    list_filter = ('tecnico', 'fecha_registro')
    search_fields = ('ticket__folio', 'descripcion')
    readonly_fields = ('fecha_registro',)

@admin.register(Escalamiento)
class EscalamientoAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'tecnico_origen', 'grupo_o_tecnico_destino', 'fecha_escalamiento')
    list_filter = ('fecha_escalamiento',)
    search_fields = ('ticket__folio', 'tecnico_origen__username', 'grupo_o_tecnico_destino')
    readonly_fields = ('fecha_escalamiento',)

@admin.register(Asignacion)
class AsignacionAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'tecnico_asignado', 'asignado_por', 'fecha_asignacion')
    list_filter = ('fecha_asignacion',)
    search_fields = ('ticket__folio', 'tecnico_asignado__username', 'asignado_por__username')
    readonly_fields = ('fecha_asignacion',)

@admin.register(CambioEstado)
class CambioEstadoAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'estado_anterior', 'estado_nuevo', 'modificado_por', 'fecha_cambio')
    list_filter = ('estado_nuevo', 'fecha_cambio')
    search_fields = ('ticket__folio', 'modificado_por__username')
    readonly_fields = ('fecha_cambio',)

@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'accion', 'usuario', 'fecha_evento')
    list_filter = ('fecha_evento',)
    search_fields = ('ticket__folio', 'accion', 'usuario__username')
    # Protegemos los logs para que ni siquiera el superusuario pueda alterarlos desde el panel
    readonly_fields = ('ticket', 'usuario', 'accion', 'fecha_evento')

    # Bloqueamos la eliminación y modificación desde el admin para mantener la integridad CIA
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False