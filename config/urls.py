from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

from users.views import (
    CustomLoginView,
    logout_view,
    api_login_view,
    error_403_view,
    # Flujo Gerencia
    gerente_dashboard_view,
    api_gerente_dashboard_metricas_view,
    gerente_inventario_view,
    gerente_gestion_tecnicos_view,
    gerente_detalle_tecnico_view,
    # Flujo General
    mis_equipos_view,
    datos_usuario_view,
    api_cambiar_tema_view,
)
from tickets.views import (
    cliente_historico_view,
    detalle_ticket_view,
    crear_ticket_view,
    # Flujo Técnico
    tecnico_tickets_asignados_view,
    autoasignar_ticket_view,
    solucionar_ticket_view,
    escalar_ticket_view,
    tecnico_historial_view,
)

urlpatterns = [
    # Redirección raíz al login
    path('', RedirectView.as_view(url='/login/', permanent=False)),

    # Autenticación y Cierre de Sesión
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', logout_view, name='logout'),
    path('api/v1/auth/login/', api_login_view, name='api_login'),

    # Rutas protegidas por RBAC - CLIENTE Y DETALLE DE TICKET
    path('cliente/historico/', cliente_historico_view, name='cliente_historico'),
    path('ticket/<int:ticket_id>/', detalle_ticket_view, name='detalle_ticket'),
    path('reporte/crear/', crear_ticket_view, name='crear_reporte'),

    # Rutas protegidas por RBAC - TÉCNICO
    path('tecnico/tickets-asignados/', tecnico_tickets_asignados_view, name='tecnico_tickets_asignados'),
    path('tecnico/ticket/<int:ticket_id>/autoasignar/', autoasignar_ticket_view, name='tecnico_autoasignar'),
    path('tecnico/solucion-caso/', solucionar_ticket_view, name='tecnico_solucion_caso'),
    path('tecnico/solucion-caso/<int:ticket_id>/', solucionar_ticket_view, name='tecnico_solucion_caso_detalle'),
    path('tecnico/ticket/<int:ticket_id>/escalar/', escalar_ticket_view, name='tecnico_escalar'),
    path('tecnico/historial/', tecnico_historial_view, name='tecnico_historial'),

    # Rutas protegidas por RBAC - GERENTE (SIG-543)
    path('gerencia/dashboard/', gerente_dashboard_view, name='gerente_dashboard'),
    path('api/v1/gerencia/dashboard-metricas/', api_gerente_dashboard_metricas_view, name='api_gerente_dashboard_metricas'),
    path('gerencia/inventario/', gerente_inventario_view, name='gerente_inventario'),
    path('gerencia/gestion-tecnicos/', gerente_gestion_tecnicos_view, name='gerente_gestion_tecnicos'),
    path('gerencia/tecnicos/<int:tecnico_id>/', gerente_detalle_tecnico_view, name='gerente_detalle_tecnico'),

    # Vistas Generales Autenticadas y Preferencias de Usuario
    path('equipos/', mis_equipos_view, name='mis_equipos'),
    path('perfil/', datos_usuario_view, name='datos_usuario'),
    path('api/v1/users/tema/', api_cambiar_tema_view, name='api_cambiar_tema'),

    # Panel de Administración de Django
    path('admin/', admin.site.urls),

    path('api/triaje-gemini/', views.api_triaje_gemini_view, name='api_triaje_gemini'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Manejador personalizado para error HTTP 403 Forbidden (RBAC)
handler403 = error_403_view
