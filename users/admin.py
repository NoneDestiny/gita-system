from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = [
        'username',
        'email',
        'cedula',
        'rol',
        'telefono',
        'modo_oscuro',
        'is_staff',
    ]

    # Campos al editar un usuario existente
    fieldsets = UserAdmin.fieldsets + (
        (
            'Información Adicional (Gita System)',
            {'fields': ('cedula', 'telefono', 'rol', 'modo_oscuro')},
        ),
    )

    # Campos al crear un usuario nuevo desde el Admin
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            'Información Adicional (Gita System)',
            {'fields': ('cedula', 'telefono', 'rol', 'modo_oscuro')},
        ),
    )


admin.site.register(CustomUser, CustomUserAdmin)