from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

class Repuesto(models.Model):
    codigo = models.CharField(max_length=50, unique=True, verbose_name="Código de Repuesto")
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, null=True)
    stock_actual = models.PositiveIntegerField(default=0, help_text="Cantidad restante en almacén")
    stock_minimo = models.PositiveIntegerField(default=5, help_text="Umbral para alerta de reabastecimiento")

    class Meta:
        verbose_name = "Repuesto"
        verbose_name_plural = "Repuestos"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.codigo} - {self.nombre} (Stock: {self.stock_actual})"


class MovimientoInventario(models.Model):
    TIPO_CHOICES = [
        ('ENTRADA', 'Entrada (Abastecimiento)'),
        ('SALIDA', 'Salida (Uso en Ticket / Descarte)'),
    ]
    
    # Relación 1:N hacia Repuesto
    repuesto = models.ForeignKey(Repuesto, on_delete=models.PROTECT, related_name='movimientos')
    tipo_movimiento = models.CharField(max_length=10, choices=TIPO_CHOICES)
    cantidad = models.PositiveIntegerField()
    
    # Vinculación hacia el Ticket atendido (opcional, porque una 'ENTRADA' no tiene ticket)
    ticket = models.ForeignKey(
        'tickets.Ticket', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='repuestos_utilizados',
        help_text="Ticket en el que se utilizó este repuesto (solo para salidas)"
    )
    
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_movimiento = models.DateTimeField(auto_now_add=True)
    observacion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Movimiento de Inventario"
        verbose_name_plural = "Movimientos de Inventario"
        ordering = ['-fecha_movimiento']

    def save(self, *args, **kwargs):
        # 1. Blindaje de Reglas de Negocio (Relación con el Ticket)
        if self.tipo_movimiento == 'SALIDA' and not self.ticket:
            raise ValidationError("Toda SALIDA de inventario debe estar vinculada obligatoriamente a un Ticket justificativo.")
        
        if self.tipo_movimiento == 'ENTRADA' and self.ticket:
            raise ValidationError("Una ENTRADA por abastecimiento es administrativa y no puede estar vinculada a un Ticket.")

        # 2. Lógica Matemática (Solo se calcula al crear el registro por primera vez)
        if not self.pk: 
            if self.tipo_movimiento == 'ENTRADA':
                self.repuesto.stock_actual += self.cantidad
            
            elif self.tipo_movimiento == 'SALIDA':
                # Prevención de stock negativo
                if self.repuesto.stock_actual < self.cantidad:
                    raise ValidationError(f"Stock insuficiente. Solo quedan {self.repuesto.stock_actual} unidades de {self.repuesto.nombre}.")
                self.repuesto.stock_actual -= self.cantidad
            
            # Guardamos el nuevo cálculo en la tabla principal del repuesto
            self.repuesto.save()
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tipo_movimiento} de {self.cantidad}x {self.repuesto.nombre}"