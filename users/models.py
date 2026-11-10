from django.contrib.auth.models import AbstractUser
from django.db import models


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

    def __str__(self):
        return (
            f'{self.username} - {self.get_rol_display()} ({self.cedula or "Sin Cédula"})'
        )