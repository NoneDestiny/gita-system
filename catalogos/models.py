from django.db import models


class Categoria(models.Model):
    nombre = models.CharField('Nombre', max_length=50, unique=True)
    descripcion = models.TextField('Descripción', blank=True, null=True)
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Prioridad(models.Model):
    nombre = models.CharField('Nombre', max_length=30, unique=True)
    nivel = models.PositiveIntegerField('Nivel de Urgencia', default=1, help_text='1 es menor urgencia')
    descripcion = models.TextField('Descripción', blank=True, null=True)

    class Meta:
        verbose_name = 'Prioridad'
        verbose_name_plural = 'Prioridades'
        ordering = ['nivel']

    def __str__(self):
        return f"{self.nombre} (Nivel {self.nivel})"


class EstadoTicket(models.Model):
    nombre = models.CharField('Nombre', max_length=30, unique=True)
    descripcion = models.TextField('Descripción', blank=True, null=True)
    es_inicial = models.BooleanField('¿Es estado inicial?', default=False)
    es_final = models.BooleanField('¿Es estado final/cerrado?', default=False)

    class Meta:
        verbose_name = 'Estado de Ticket'
        verbose_name_plural = 'Estados de Ticket'
        ordering = ['id']

    def __str__(self):
        return self.nombre


class SLA(models.Model):
    nombre = models.CharField('Nombre del Plan SLA', max_length=50, unique=True)
    tiempo_resolucion_horas = models.PositiveIntegerField('Tiempo de Resolución (Horas)')
    descripcion = models.TextField('Descripción', blank=True, null=True)

    class Meta:
        verbose_name = 'SLA (Acuerdo de Nivel de Servicio)'
        verbose_name_plural = 'SLAs'

    def __str__(self):
        return f"{self.nombre} ({self.tiempo_resolucion_horas}h)"


class ModalidadAtencion(models.Model):
    nombre = models.CharField('Nombre', max_length=50, unique=True)  # Ej: Presencial, Remoto, Taller
    descripcion = models.TextField('Descripción', blank=True, null=True)

    class Meta:
        verbose_name = 'Modalidad de Atención'
        verbose_name_plural = 'Modalidades de Atención'

    def __str__(self):
        return self.nombre