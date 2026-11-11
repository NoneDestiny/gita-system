from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
import os


class Equipo(models.Model):
    serial = models.CharField(max_length=50, unique=True, verbose_name="Serial / Etiqueta")
    marca = models.CharField(max_length=50)
    modelo = models.CharField(max_length=50)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Equipo"
        verbose_name_plural = "Equipos"

    def __str__(self):
        return f"{self.marca} {self.modelo} (SN: {self.serial})"


class Ticket(models.Model):
    # Generación de Folio
    folio = models.CharField(max_length=20, unique=True, editable=False, verbose_name="Folio del Ticket")
    asunto = models.CharField(max_length=150)
    descripcion = models.TextField()

    # Relaciones de Negocio (Protegidas para evitar pérdida de historial)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT, 
        related_name="tickets_creados",
        verbose_name="Usuario / Cliente"
    )
    tecnico_asignado = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="tickets_asignados",
        verbose_name="Técnico"
    )
    equipo = models.ForeignKey(
        Equipo, 
        on_delete=models.PROTECT, 
        related_name="tickets"
    )
    
    # Catálogos
    categoria = models.ForeignKey('catalogos.Categoria', on_delete=models.PROTECT)
    prioridad = models.ForeignKey('catalogos.Prioridad', on_delete=models.PROTECT)
    estado = models.ForeignKey('catalogos.EstadoTicket', on_delete=models.PROTECT)
    modalidad = models.ForeignKey('catalogos.ModalidadAtencion', on_delete=models.PROTECT, null=True, blank=True)

    # Marcas temporales exactas (KPIs para SIG-543)
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")
    fecha_asignacion = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Asignación")
    fecha_cierre = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Cierre")

    class Meta:
        verbose_name = "Ticket"
        verbose_name_plural = "Tickets"
        ordering = ['-fecha_creacion']

    def save(self, *args, **kwargs):
        # Autogenerador de folio secuencial único (Ej: TK-00001)
        if not self.folio:
            ultimo_ticket = Ticket.objects.order_by('id').last()
            nuevo_id = (ultimo_ticket.id + 1) if ultimo_ticket else 1
            candidato = f"TK-{nuevo_id:05d}"
            while Ticket.objects.filter(folio=candidato).exists():
                nuevo_id += 1
                candidato = f"TK-{nuevo_id:05d}"
            self.folio = candidato
            
        # Registro automático de fecha de asignación si se asigna un técnico y no tenía fecha
        if self.tecnico_asignado and not self.fecha_asignacion:
            self.fecha_asignacion = timezone.now()
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.folio} - {self.asunto}"


# --- VALIDACIÓN DE SEGURIDAD PARA EVIDENCIAS ---
def validar_evidencia(file):
    ext = os.path.splitext(file.name)[1].lower()
    valid_extensions = ['.jpg', '.jpeg', '.png']
    if ext not in valid_extensions:
        raise ValidationError('Archivo no permitido. Solo se aceptan formatos JPG, JPEG y PNG.')
    
    max_size = 5 * 1024 * 1024  # 5 MB
    if file.size > max_size:
        raise ValidationError(f'El archivo excede el límite de 5MB permitido por seguridad.')


# --- MODELOS SATÉLITE (BD-04) ---

class Evidencia(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='evidencias')
    archivo = models.FileField(
        upload_to='evidencias/%Y/%m/', 
        validators=[validar_evidencia],
        help_text="Límite: 5MB. Formatos: JPG, PNG, JPEG."
    )
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_subida = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evidencia"
        verbose_name_plural = "Evidencias"


class Intervencion(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='intervenciones')
    tecnico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    descripcion = models.TextField(verbose_name="Detalle de la intervención")
    tiempo_invertido_minutos = models.PositiveIntegerField(default=0, help_text="Útil para cálculo de métricas")
    fecha_registro = models.DateTimeField(auto_now_add=True)


class Escalamiento(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='escalamientos')
    tecnico_origen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='escalamientos_emitidos')
    grupo_o_tecnico_destino = models.CharField(max_length=100, verbose_name="Destino del escalamiento")
    motivo = models.TextField()
    fecha_escalamiento = models.DateTimeField(auto_now_add=True)


class Asignacion(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='historial_asignaciones')
    tecnico_asignado = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='asignaciones_recibidas')
    asignado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='acciones_asignar')
    fecha_asignacion = models.DateTimeField(auto_now_add=True)


class CambioEstado(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='historial_estados')
    estado_anterior = models.ForeignKey('catalogos.EstadoTicket', on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    estado_nuevo = models.ForeignKey('catalogos.EstadoTicket', on_delete=models.PROTECT, related_name='+')
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    motivo = models.CharField(max_length=255, blank=True, null=True)
    fecha_cambio = models.DateTimeField(auto_now_add=True)


class Auditoria(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='logs_auditoria')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    accion = models.CharField(max_length=255, help_text="Ej: Ticket creado, Evidencia eliminada, etc.")
    fecha_evento = models.DateTimeField(auto_now_add=True)


class Notificacion(models.Model):
    """
    Registro histórico de correos electrónicos automáticos enviados por el sistema.
    """
    TIPO_CHOICES = (
        ('CREACION', 'Creación de Ticket'),
        ('ESCALAMIENTO', 'Escalamiento'),
        ('RESOLUCION', 'Resolución / Cierre'),
        ('ACTUALIZACION', 'Actualización de Estado'),
    )

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='notificaciones', null=True, blank=True)
    destinatario = models.EmailField(verbose_name="Correo Destinatario")
    usuario_destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='notificaciones_recibidas'
    )
    tipo_evento = models.CharField(max_length=20, choices=TIPO_CHOICES, default='CREACION')
    asunto = models.CharField(max_length=255)
    cuerpo_html = models.TextField()
    fecha_envio = models.DateTimeField(auto_now_add=True)
    exitoso = models.BooleanField(default=True)
    error_log = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Notificación de Correo"
        verbose_name_plural = "Notificaciones de Correo"
        ordering = ['-fecha_envio']

    def __str__(self):
        return f"[{self.tipo_evento}] {self.asunto} -> {self.destinatario}"