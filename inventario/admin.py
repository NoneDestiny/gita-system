from django.contrib import admin
from .models import Repuesto, MovimientoInventario

@admin.register(Repuesto)
class RepuestoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'stock_actual', 'stock_minimo')
    search_fields = ('codigo', 'nombre')
    # Opcional: Resaltar en el panel si el stock está por debajo del mínimo (para el frontend será útil luego)

@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ('repuesto', 'tipo_movimiento', 'cantidad', 'ticket', 'fecha_movimiento', 'registrado_por')
    list_filter = ('tipo_movimiento', 'fecha_movimiento')
    search_fields = ('repuesto__nombre', 'ticket__folio')
    readonly_fields = ('fecha_movimiento',)