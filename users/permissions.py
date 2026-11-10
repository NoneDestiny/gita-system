from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib.auth.mixins import AccessMixin
from django.contrib import messages


def obtener_ruta_por_rol(user):
    """
    Retorna la URL de inicio del sistema según el rol del usuario (Redirección Dinámica).
    - CLIENTE  -> Histórico / Mis Tickets (/cliente/historico/)
    - TECNICO  -> Bandeja de Asignaciones (/tecnico/tickets-asignados/)
    - GERENTE  -> Dashboard Gerencial (/gerencia/dashboard/)
    """
    if not user.is_authenticated:
        return '/login/'
    
    rol = getattr(user, 'rol', None)
    
    if rol == 'GERENTE' or user.is_superuser:
        return '/gerencia/dashboard/'
    elif rol == 'TECNICO':
        return '/tecnico/tickets-asignados/'
    elif rol == 'CLIENTE':
        return '/cliente/historico/'
    
    return '/login/'


# ==============================================================================
# DECORADORES PARA FUNCIONES (FBV)
# ==============================================================================

def role_required(allowed_roles=None, raise_exception=True):
    """
    Decorador para proteger vistas basadas en funciones según roles permitidos.
    
    :param allowed_roles: Lista o tupla de roles permitidos (ej. ['GERENTE', 'TECNICO']).
    :param raise_exception: Si es True, lanza PermissionDenied (HTTP 403 Forbidden).
                            Si es False, redirige al usuario a su ruta por defecto con mensaje de error.
    """
    if allowed_roles is None:
        allowed_roles = []
    elif isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"/login/?next={request.path}")

            # Superusuario tiene acceso administrativo global
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            user_role = getattr(request.user, 'rol', None)
            if user_role not in allowed_roles:
                if raise_exception:
                    raise PermissionDenied("Acceso denegado: No tienes permisos para acceder a esta sección.")
                else:
                    messages.error(request, "No tienes permisos suficientes para acceder a esa sección.")
                    return redirect(obtener_ruta_por_rol(request.user))

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def cliente_required(view_func=None, raise_exception=True):
    """Decorador específico: solo rol CLIENTE."""
    actual_decorator = role_required(['CLIENTE'], raise_exception=raise_exception)
    if view_func:
        return actual_decorator(view_func)
    return actual_decorator


def tecnico_required(view_func=None, raise_exception=True):
    """Decorador específico: solo rol TECNICO."""
    actual_decorator = role_required(['TECNICO'], raise_exception=raise_exception)
    if view_func:
        return actual_decorator(view_func)
    return actual_decorator


def gerente_required(view_func=None, raise_exception=True):
    """Decorador específico: solo rol GERENTE."""
    actual_decorator = role_required(['GERENTE'], raise_exception=raise_exception)
    if view_func:
        return actual_decorator(view_func)
    return actual_decorator


# ==============================================================================
# MIXINS PARA VISTAS BASADAS EN CLASES (CBV)
# ==============================================================================

class RoleRequiredMixin(AccessMixin):
    """
    Mixin para proteger Vistas Basadas en Clases (CBV) restringiendo por roles.
    Devuelve HTTP 403 Forbidden (PermissionDenied) o redirige según raise_exception.
    """
    allowed_roles = []
    raise_exception = True

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        user_role = getattr(request.user, 'rol', None)
        roles = self.allowed_roles if isinstance(self.allowed_roles, (list, tuple)) else [self.allowed_roles]

        if user_role not in roles:
            if self.raise_exception:
                raise PermissionDenied("Acceso denegado: No tienes permisos para acceder a esta sección.")
            messages.error(request, "No tienes autorización para ver esta página.")
            return redirect(obtener_ruta_por_rol(request.user))

        return super().dispatch(request, *args, **kwargs)


class ClienteRequiredMixin(RoleRequiredMixin):
    """CBV Mixin para rol CLIENTE."""
    allowed_roles = ['CLIENTE']


class TecnicoRequiredMixin(RoleRequiredMixin):
    """CBV Mixin para rol TECNICO."""
    allowed_roles = ['TECNICO']


class GerenteRequiredMixin(RoleRequiredMixin):
    """CBV Mixin para rol GERENTE."""
    allowed_roles = ['GERENTE']
