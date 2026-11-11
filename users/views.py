import json
import secrets
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST, require_http_methods
from django.core.exceptions import PermissionDenied
from inventario.models import Repuesto

from .models import CustomUser
from .forms import CustomAuthenticationForm, CustomAdminAuthenticationForm
from .permissions import (
    obtener_ruta_por_rol,
    role_required,
    cliente_required,
    tecnico_required,
    gerente_required,
    RoleRequiredMixin,
    ClienteRequiredMixin,
    TecnicoRequiredMixin,
    GerenteRequiredMixin,
)


# ==============================================================================
# VISTA DE LOGIN CON REDIRECCIÓN DINÁMICA POR ROL
# ==============================================================================

class CustomLoginView(LoginView):
    """
    Vista de inicio de sesión con soporte para:
    1. Redirección Inteligente post-login según el rol del usuario:
       - CLIENTE -> /cliente/historico/
       - TECNICO -> /tecnico/tickets-asignados/
       - GERENTE -> /gerencia/dashboard/
    2. Checkbox 'Recordarme' para persistencia de sesión.
    3. Redirección automática si el usuario ya está autenticado.
    """
    template_name = 'auth/login.html'
    authentication_form = CustomAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        # Si se especificó un parámetro 'next' seguro, verificar si corresponde
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={self.request.get_host()}):
            return next_url
        
        # Redirección dinámica basada en rol
        return obtener_ruta_por_rol(self.request.user)

    def form_valid(self, form):
        # Manejo del checkbox "Recordarme"
        remember_me = self.request.POST.get('remember_me')
        if remember_me:
            # 2 semanas de persistencia
            self.request.session.set_expiry(1209600)
        else:
            # Expira al cerrar el navegador
            self.request.session.set_expiry(0)

        return super().form_valid(form)


# ==============================================================================
# ENDPOINT API DE AUTENTICACIÓN (POST /api/v1/auth/login/)
# ==============================================================================

@csrf_protect
@require_POST
def api_login_view(request):
    """
    Endpoint REST para autenticación asíncrona (JSON).
    Payload:
      {
        "identificador": "30346898",
        "password": "...",
        "recordarme": true
      }
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({
            'status': 'error',
            'code': 'INVALID_PAYLOAD',
            'message': 'El formato de la petición debe ser JSON válido.'
        }, status=400)

    identificador = (data.get('identificador') or '').strip()
    password = data.get('password') or ''
    recordarme = bool(data.get('recordarme', False))

    if not identificador or not password:
        return JsonResponse({
            'status': 'error',
            'code': 'MISSING_FIELDS',
            'message': 'Debe ingresar el identificador y la contraseña.'
        }, status=400)

    # Autenticar a través de MultiFieldAuthBackend
    user = authenticate(request, username=identificador, password=password)

    if user is not None:
        if not user.is_active:
            return JsonResponse({
                'status': 'error',
                'code': 'USER_INACTIVE',
                'message': 'Esta cuenta de usuario se encuentra inactiva. Contacte al administrador.'
            }, status=403)

        # Iniciar sesión en Django
        auth_login(request, user)

        if recordarme:
            request.session.set_expiry(1209600)  # 14 días
        else:
            request.session.set_expiry(0)       # Al cerrar el navegador

        redirect_url = obtener_ruta_por_rol(user)

        # Simulación de tokens para API / SPA
        dummy_token = secrets.token_urlsafe(32)
        dummy_refresh = secrets.token_urlsafe(48)

        return JsonResponse({
            'status': 'success',
            'message': 'Autenticación exitosa',
            'data': {
                'usuario': {
                    'id': user.id,
                    'username': user.username,
                    'nombre_completo': user.get_full_name() or user.username,
                    'email': user.email,
                    'cedula': getattr(user, 'cedula', '') or '',
                    'rol': getattr(user, 'rol', 'CLIENTE'),
                    'modo_oscuro': getattr(user, 'modo_oscuro', True),
                },
                'redirect_url': redirect_url,
                'tokens': {
                    'access_token': dummy_token,
                    'refresh_token': dummy_refresh,
                    'expires_in': 3600
                }
            }
        }, status=200)

    # En caso de fallo de autenticación
    # Verificar si el usuario consultado quedó bloqueado o tiene intentos restantes
    error_msg = getattr(request, '_auth_error', 'Credenciales incorrectas.')
    
    # Buscar si el usuario existe para obtener sus métricas de bloqueo
    user_obj = CustomUser.objects.filter(
        models_q_filter(identificador)
    ).first()

    if user_obj and user_obj.esta_bloqueado():
        minutos = user_obj.minutos_restantes_bloqueo()
        return JsonResponse({
            'status': 'error',
            'code': 'ACCOUNT_LOCKED',
            'message': f"Cuenta bloqueada temporalmente por 15 minutos debido a demasiados intentos fallidos.",
            'bloqueado_hasta': user_obj.bloqueado_hasta.isoformat() if user_obj.bloqueado_hasta else None,
            'minutos_restantes': minutos
        }, status=423)

    intentos_restantes = max(0, 5 - getattr(user_obj, 'intentos_fallidos', 0)) if user_obj else 0

    return JsonResponse({
        'status': 'error',
        'code': 'INVALID_CREDENTIALS',
        'message': error_msg,
        'intentos_restantes': intentos_restantes
    }, status=401)


def models_q_filter(identificador):
    from django.db.models import Q
    return Q(username__iexact=identificador) | Q(email__iexact=identificador) | Q(cedula__iexact=identificador)


# ==============================================================================
# VISTA DE CIERRE DE SESIÓN
# ==============================================================================

def logout_view(request):
    """
    Cierra la sesión del usuario, invalida la sesión y redirige al login.
    """
    auth_logout(request)
    request.session.flush()
    return redirect('/login/')


# ==============================================================================
# VISTAS PROTEGIDAS CON CONTROL DE ACCESO BASADO EN ROLES (RBAC)
# ==============================================================================

# --- FLUJO CLIENTE ---
@cliente_required
def cliente_historico_view(request):
    """Bandeja de histórico de tickets exclusiva para CLIENTE."""
    return render(request, 'cliente/historico.html', {
        'modulo': 'historico',
        'usuario': request.user
    })


# --- FLUJO TÉCNICO ---
@tecnico_required
def tecnico_tickets_asignados_view(request):
    """Bandeja de asignaciones exclusiva para TÉCNICO."""
    return render(request, 'tecnico/tickets_asignados.html', {
        'modulo': 'tickets_asignados',
        'usuario': request.user
    })


@tecnico_required
def tecnico_solucion_caso_view(request):
    """Resolución técnica de tickets."""
    return render(request, 'tecnico/solucion_caso.html', {
        'modulo': 'solucion_caso',
        'usuario': request.user
    })


@tecnico_required
def tecnico_historial_view(request):
    """Historial de casos resueltos por el técnico."""
    return render(request, 'tecnico/historial_tecnico.html', {
        'modulo': 'historial_tecnico',
        'usuario': request.user
    })


# --- FLUJO GERENCIA ---
@gerente_required
def gerente_dashboard_view(request):
    """Dashboard de métricas gerenciales exclusivo para GERENTE."""
    return render(request, 'gerencia/dashboard.html', {
        'modulo': 'dashboard',
        'usuario': request.user
    })


from inventario.models import Repuesto

@gerente_required
def gerente_inventario_view(request):
    if request.method == 'POST':
        accion = request.POST.get('accion')
        codigo = request.POST.get('codigo')
        
        # El HTML manda 'name="descripcion"', lo atrapamos y lo guardamos en 'nombre'
        # ya que es el campo obligatorio en tu modelo.
        nombre_repuesto = request.POST.get('descripcion')
        
        try:
            stock = int(request.POST.get('stock', 0))
            stock_min = int(request.POST.get('stock_min', 0))
        except ValueError:
            messages.error(request, "Los valores de stock deben ser números válidos.")
            return redirect('gerente_inventario') 

        if accion == 'crear':
            try:
                if Repuesto.objects.filter(codigo=codigo).exists():
                    messages.error(request, f"Ya existe un repuesto con el código {codigo}.")
                else:
                    Repuesto.objects.create(
                        codigo=codigo,
                        nombre=nombre_repuesto,  # <-- CORREGIDO
                        stock_actual=stock,      # <-- CORREGIDO
                        stock_minimo=stock_min   # <-- CORREGIDO
                    )
                    messages.success(request, "Repuesto agregado exitosamente.")
            except Exception as e:
                print(f"❌ ERROR AL CREAR: {e}")
                messages.error(request, f"Error interno: {str(e)}")

        elif accion == 'editar':
            try:
                repuesto = Repuesto.objects.get(codigo=codigo)
                repuesto.nombre = nombre_repuesto  # <-- CORREGIDO
                repuesto.stock_actual = stock      # <-- CORREGIDO
                repuesto.stock_minimo = stock_min  # <-- CORREGIDO
                repuesto.save()
                messages.success(request, "Repuesto actualizado correctamente.")
            except Repuesto.DoesNotExist:
                messages.error(request, "El repuesto que intentas editar no existe.")
            except Exception as e:
                print(f"❌ ERROR AL EDITAR: {e}")
                messages.error(request, f"Error interno: {str(e)}")

        return redirect('gerente_inventario')

    # 2. MOSTRAR LA PÁGINA NORMALMENTE (GET)
    repuestos_lista = Repuesto.objects.all().order_by('codigo')
    
    return render(request, 'gerencia/inventario.html', {
        'modulo': 'inventario',
        'usuario': request.user,
        'repuestos': repuestos_lista
    })


@gerente_required
def gerente_gestion_tecnicos_view(request):
    """Gestión de equipo técnico para GERENTE."""
    return render(request, 'gerencia/gestion_tecnicos.html', {
        'modulo': 'gestion_tecnicos',
        'usuario': request.user
    })


# --- VISTAS OPERATIVAS COMUNES (AUTENTICADAS) ---
@login_required
def mis_equipos_view(request):
    """Vista de equipos asociados."""
    from tickets.models import Equipo
    equipos = Equipo.objects.all()
    return render(request, 'general/equipos.html', {
        'modulo': 'equipos',
        'usuario': request.user,
        'equipos': equipos,
    })


@login_required
def crear_reporte_view(request):
    """Creación de nuevos reportes de incidencia (Redirige al controlador MVT de tickets)."""
    return redirect('crear_reporte')


@login_required
def datos_usuario_view(request):
    """Perfil y datos del usuario autenticado."""
    if request.method == 'POST':
        telefono = request.POST.get('telefono', '').strip()
        if hasattr(request.user, 'telefono') and telefono:
            request.user.telefono = telefono
            request.user.save(update_fields=['telefono'])
            messages.success(request, "Tus datos han sido actualizados con éxito.")
        return redirect('datos_usuario')

    return render(request, 'general/datos_usuario.html', {
        'modulo': 'perfil',
        'usuario': request.user,
    })


# ==============================================================================
# MANEJADOR DE ERROR 403 (ACCESO DENEGADO)
# ==============================================================================

def error_403_view(request, exception=None):
    """
    Vista personalizada para error 403 Forbidden cuando un usuario intenta
    forzar URLs ajenas a su rol.
    """
    context = {
        'mensaje': str(exception) if exception else "No tienes los permisos necesarios para acceder a este recurso.",
        'ruta_retorno': obtener_ruta_por_rol(request.user) if request.user.is_authenticated else '/login/',
    }
    return render(request, 'errors/403.html', context, status=403)
