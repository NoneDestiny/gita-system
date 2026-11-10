from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from users.views import (
    CustomLoginView,
    logout_view,
    api_login_view,
    error_403_view,
    # Flujo Cliente
    cliente_historico_view,
    # Flujo Técnico
    tecnico_tickets_asignados_view,
    tecnico_solucion_caso_view,
    tecnico_historial_view,
    # Flujo Gerencia
    gerente_dashboard_view,
    gerente_inventario_view,
    gerente_gestion_tecnicos_view,
    # Flujo General
    mis_equipos_view,
    crear_reporte_view,
    datos_usuario_view,
)

urlpatterns = [
    # Redirección raíz al login
    path('', RedirectView.as_view(url='/login/', permanent=False)),

    # Autenticación y Cierre de Sesión
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', logout_view, name='logout'),
    path('api/v1/auth/login/', api_login_view, name='api_login'),

    # Rutas protegidas por RBAC - CLIENTE
    path('cliente/historico/', cliente_historico_view, name='cliente_historico'),

    # Rutas protegidas por RBAC - TÉCNICO
    path('tecnico/tickets-asignados/', tecnico_tickets_asignados_view, name='tecnico_tickets_asignados'),
    path('tecnico/solucion-caso/', tecnico_solucion_caso_view, name='tecnico_solucion_caso'),
    path('tecnico/historial/', tecnico_historial_view, name='tecnico_historial'),

    # Rutas protegidas por RBAC - GERENTE
    path('gerencia/dashboard/', gerente_dashboard_view, name='gerente_dashboard'),
    path('gerencia/inventario/', gerente_inventario_view, name='gerente_inventario'),
    path('gerencia/gestion-tecnicos/', gerente_gestion_tecnicos_view, name='gerente_gestion_tecnicos'),

    # Vistas Generales Autenticadas
    path('equipos/', mis_equipos_view, name='mis_equipos'),
    path('reporte/crear/', crear_reporte_view, name='crear_reporte'),
    path('perfil/', datos_usuario_view, name='datos_usuario'),

    # Panel de Administración de Django
    path('admin/', admin.site.urls),
]

# Manejador personalizado para error HTTP 403 Forbidden (RBAC)
handler403 = error_403_view
