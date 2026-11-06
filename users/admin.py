from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .forms import CustomAdminAuthenticationForm
from .models import CustomUser, HistorialAcceso

# Usar el formulario con soporte para Cédula/Email/Username y alertas de seguridad
admin.site.login_form = CustomAdminAuthenticationForm


@admin.action(description='Desbloquear cuentas seleccionadas')
def desbloquear_cuentas(modeladmin, request, queryset):
    for usuario in queryset:
        usuario.resetear_intentos()
    modeladmin.message_user(request, f"Se han desbloqueado {queryset.count()} usuario(s) exitosamente.")


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = [
        'username',
        'email',
        'cedula',
        'rol',
        'intentos_fallidos',
        'bloqueado_hasta',
        'is_staff',
    ]
    list_filter = ['rol', 'is_staff', 'is_active', 'modo_oscuro']
    actions = [desbloquear_cuentas]

    # Campos al editar un usuario existente
    fieldsets = UserAdmin.fieldsets + (
        (
            'Información Adicional (Gita System)',
            {'fields': ('cedula', 'telefono', 'rol', 'modo_oscuro')},
        ),
        (
            'Seguridad y Bloqueos',
            {'fields': ('intentos_fallidos', 'bloqueado_hasta')},
        ),
    )

    # Campos al crear un usuario nuevo desde el Admin
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            'Información Adicional (Gita System)',
            {'fields': ('cedula', 'telefono', 'rol', 'modo_oscuro')},
        ),
    )


@admin.register(HistorialAcceso)
class HistorialAccesoAdmin(admin.ModelAdmin):
    list_display = [
        'fecha_hora',
        'identificador_ingresado',
        'usuario',
        'exitoso',
        'motivo_fallo',
        'ip_address',
    ]
    list_filter = ['exitoso', 'fecha_hora']
    search_fields = [
        'identificador_ingresado',
        'usuario__username',
        'usuario__cedula',
        'usuario__email',
        'ip_address',
        'motivo_fallo',
    ]
    readonly_fields = [
        'fecha_hora',
        'identificador_ingresado',
        'usuario',
        'exitoso',
        'motivo_fallo',
        'ip_address',
        'user_agent',
    ]

    def has_add_permission(self, request):
        # Es un log de auditoría del sistema; no debe crearse a mano
        return False

    def has_delete_permission(self, request, obj=None):
        # Proteger registros de auditoría contra eliminación accidental
        return False


admin.site.register(CustomUser, CustomUserAdmin)