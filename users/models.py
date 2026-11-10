from datetime import timedelta
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class CustomUser(AbstractUser):
    # Definición de Roles del Sistema
    ROLE_CHOICES = (
        ('CLIENTE', 'Cliente'),
        ('TECNICO', 'Técnico'),
        ('GERENTE', 'Gerente'),
    )

    cedula = models.CharField(
        'Cédula de Identidad', max_length=20, unique=True, null=True, blank=True
    )
    telefono = models.CharField(
        'Teléfono de Contacto', max_length=20, null=True, blank=True
    )
    modo_oscuro = models.BooleanField('Preferir Modo Oscuro', default=True)
    rol = models.CharField(
        'Rol de Usuario', max_length=10, choices=ROLE_CHOICES, default='CLIENTE'
    )

    # Control de seguridad y bloqueo por intentos fallidos
    intentos_fallidos = models.PositiveIntegerField('Intentos Fallidos', default=0)
    bloqueado_hasta = models.DateTimeField('Bloqueado Hasta', null=True, blank=True)

    def esta_bloqueado(self):
        """Retorna True si la cuenta se encuentra bloqueada temporalmente."""
        if self.bloqueado_hasta:
            if timezone.now() < self.bloqueado_hasta:
                return True
            # Si el tiempo ya pasó, limpiamos el bloqueo
            self.bloqueado_hasta = None
            self.intentos_fallidos = 0
            self.save(update_fields=['bloqueado_hasta', 'intentos_fallidos'])
        return False

    def minutos_restantes_bloqueo(self):
        """Devuelve los minutos que restan para que expire el bloqueo."""
        if self.bloqueado_hasta and timezone.now() < self.bloqueado_hasta:
            delta = self.bloqueado_hasta - timezone.now()
            return max(1, int(delta.total_seconds() / 60))
        return 0

    def registrar_intento_fallido(self, max_intentos=5, minutos_bloqueo=15):
        """Incrementa los intentos fallidos y bloquea si alcanza el límite."""
        self.intentos_fallidos += 1
        if self.intentos_fallidos >= max_intentos:
            self.bloqueado_hasta = timezone.now() + timedelta(minutes=minutos_bloqueo)
            self.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])
            return True  # Fue bloqueado ahora
        self.save(update_fields=['intentos_fallidos'])
        return False

    def resetear_intentos(self):
        """Restaura los intentos a cero tras un login exitoso."""
        if self.intentos_fallidos > 0 or self.bloqueado_hasta is not None:
            self.intentos_fallidos = 0
            self.bloqueado_hasta = None
            self.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])

    def __str__(self):
        return (
            f'{self.username} - {self.get_rol_display()} ({self.cedula or "Sin Cédula"})'
        )


class HistorialAcceso(models.Model):
    """Registro de auditoría de cada intento de inicio de sesión."""
    usuario = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='historial_accesos',
        verbose_name='Usuario'
    )
    identificador_ingresado = models.CharField(
        'Identificador Ingresado',
        max_length=150,
        help_text='Texto escrito en el campo de usuario (cédula, correo o username)'
    )
    ip_address = models.GenericIPAddressField(
        'Dirección IP',
        null=True,
        blank=True
    )
    user_agent = models.TextField(
        'Navegador / Dispositivo',
        blank=True,
        null=True
    )
    exitoso = models.BooleanField(
        '¿Acceso Exitoso?',
        default=False
    )
    motivo_fallo = models.CharField(
        'Motivo (si falló)',
        max_length=255,
        blank=True,
        null=True
    )
    fecha_hora = models.DateTimeField(
        'Fecha y Hora',
        auto_now_add=True
    )

    class Meta:
        verbose_name = 'Historial de Acceso'
        verbose_name_plural = 'Historial de Accesos'
        ordering = ['-fecha_hora']

    def __str__(self):
        estado = "Exitoso" if self.exitoso else f"Fallido ({self.motivo_fallo or 'Sin motivo'})"
        return f"{self.identificador_ingresado} - {estado} [{self.fecha_hora.strftime('%Y-%m-%d %H:%M:%S')}]"