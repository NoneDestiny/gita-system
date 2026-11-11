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

# --- FLUJO GERENCIA ---
@gerente_required
def gerente_dashboard_view(request):
    """Dashboard de métricas gerenciales exclusivo para GERENTE conectado a BD."""
    from django.db.models import F, Q, Sum
    from django.utils import timezone
    from datetime import timedelta
    from tickets.models import Ticket
    from inventario.models import MovimientoInventario

    # 1. Alertas de Inventario Crítico y Movimientos Operativos de Salida
    repuestos_criticos = Repuesto.objects.filter(stock_actual__lte=F('stock_minimo')).order_by('stock_actual')
    movimientos_salida = MovimientoInventario.objects.filter(
        tipo_movimiento='SALIDA'
    ).select_related('repuesto', 'ticket', 'registrado_por').order_by('-fecha_movimiento')[:5]
    total_repuestos_usados = (
        MovimientoInventario.objects.filter(tipo_movimiento='SALIDA').aggregate(total=Sum('cantidad'))['total'] or 0
    )

    # 2. Carga de Trabajo por Técnico
    tecnicos_qs = CustomUser.objects.filter(rol='TECNICO', is_active=True)
    estados_finales = ['RESUELTO', 'CERRADO', 'Resuelto', 'Cerrado']
    umbral_atraso = timezone.now() - timedelta(hours=24)

    carga_tecnicos = []
    for tec in tecnicos_qs:
        tickets_tec = Ticket.objects.filter(tecnico_asignado=tec).select_related('estado')
        asignados_activos = tickets_tec.exclude(Q(estado__es_final=True) | Q(estado__nombre__in=estados_finales))
        resueltos = tickets_tec.filter(Q(estado__es_final=True) | Q(estado__nombre__in=estados_finales))
        atrasados = asignados_activos.filter(fecha_creacion__lt=umbral_atraso)

        carga_tecnicos.append({
            'id': tec.id,
            'nombre': tec.get_full_name() or tec.username,
            'asignados': asignados_activos.count(),
            'resueltos': resueltos.count(),
            'atrasados': atrasados.count(),
        })

    # 3. KPIs Globales
    todos_tickets = Ticket.objects.select_related('estado')
    total_tickets = todos_tickets.count()
    tickets_abiertos_qs = todos_tickets.exclude(Q(estado__es_final=True) | Q(estado__nombre__in=estados_finales))
    tickets_resueltos_qs = todos_tickets.filter(Q(estado__es_final=True) | Q(estado__nombre__in=estados_finales))

    tickets_abiertos_count = tickets_abiertos_qs.count()
    tickets_atrasados_global = tickets_abiertos_qs.filter(fecha_creacion__lt=umbral_atraso).count()

    if total_tickets > 0:
        cumplimiento_pct = max(0, round(((total_tickets - tickets_atrasados_global) / total_tickets) * 100))
    else:
        cumplimiento_pct = 100

    # Tiempo promedio de resolución en horas
    tiempos_horas = []
    for t in tickets_resueltos_qs:
        inicio = t.fecha_asignacion or t.fecha_creacion
        if inicio and t.fecha_cierre and t.fecha_cierre >= inicio:
            horas = (t.fecha_cierre - inicio).total_seconds() / 3600.0
            tiempos_horas.append(horas)

    tiempo_promedio_hrs = round(sum(tiempos_horas) / len(tiempos_horas), 1) if tiempos_horas else 0.0

    return render(request, 'gerencia/dashboard.html', {
        'modulo': 'dashboard',
        'usuario': request.user,
        'repuestos_criticos': repuestos_criticos,
        'movimientos_salida': movimientos_salida,
        'total_repuestos_usados': total_repuestos_usados,
        'carga_tecnicos': carga_tecnicos,
        'tickets_abiertos_count': tickets_abiertos_count,
        'cumplimiento_pct': cumplimiento_pct,
        'tiempo_promedio_hrs': tiempo_promedio_hrs,
    })


@gerente_required
def gerente_inventario_view(request):
    """Delega al controlador CRUD de inventario en la app inventario."""
    from inventario.views import gerente_inventario
    return gerente_inventario(request)


@gerente_required
def gerente_gestion_tecnicos_view(request):
    """Gestión de equipo técnico para GERENTE con métricas dinámicas desde BD."""
    from django.db.models import Q
    from django.utils import timezone
    from datetime import timedelta
    from tickets.models import Ticket

    tecnicos_qs = CustomUser.objects.filter(rol='TECNICO', is_active=True)
    estados_finales = ['RESUELTO', 'CERRADO', 'Resuelto', 'Cerrado']
    umbral_atraso = timezone.now() - timedelta(hours=24)

    tecnicos_data = []
    for tec in tecnicos_qs:
        tickets_tec = Ticket.objects.filter(tecnico_asignado=tec).select_related('estado')
        total_tec = tickets_tec.count()
        activos_qs = tickets_tec.exclude(Q(estado__es_final=True) | Q(estado__nombre__in=estados_finales))
        activos_count = activos_qs.count()
        atrasados_count = activos_qs.filter(fecha_creacion__lt=umbral_atraso).count()

        if total_tec > 0:
            cumplimiento_sla = max(0, round(((total_tec - atrasados_count) / total_tec) * 100))
        else:
            cumplimiento_sla = 100

        if activos_count == 0:
            estado_actual = "Disponible"
        elif activos_count < 5:
            estado_actual = "En servicio"
        else:
            estado_actual = "Carga alta"

        tecnicos_data.append({
            'id': tec.id,
            'username': tec.username,
            'nombre_completo': tec.get_full_name() or tec.username,
            'tickets_activos_count': activos_count,
            'cumplimiento_sla': cumplimiento_sla,
            'estado_actual': estado_actual,
        })

    return render(request, 'gerencia/gestion_tecnicos.html', {
        'modulo': 'gestion_tecnicos',
        'usuario': request.user,
        'tecnicos': tecnicos_data,
    })


@gerente_required
def gerente_detalle_tecnico_view(request, tecnico_id):
    """
    Vista gerencial de detalle de un técnico específico:
    Permite consultar su carga de tickets y asignar/quitar tickets mediante modales.
    """
    from django.shortcuts import get_object_or_404
    from django.db.models import Q
    from django.utils import timezone
    from datetime import timedelta
    from catalogos.models import Prioridad, EstadoTicket
    from tickets.models import Ticket, Asignacion, CambioEstado, Auditoria

    tecnico = get_object_or_404(CustomUser, id=tecnico_id, rol='TECNICO')
    estados_finales = ['RESUELTO', 'CERRADO', 'Resuelto', 'Cerrado']
    umbral_atraso = timezone.now() - timedelta(hours=24)

    if request.method == 'POST':
        accion = request.POST.get('accion', '').strip()
        ticket_id = request.POST.get('ticket_id', '').strip()

        if not ticket_id or not ticket_id.isdigit():
            messages.error(request, "Debe seleccionar un ticket válido.")
            return redirect('gerente_detalle_tecnico', tecnico_id=tecnico.id)

        ticket = get_object_or_404(Ticket, id=int(ticket_id))

        if accion == 'asignar':
            prioridad_val = request.POST.get('prioridad', '').strip()
            if prioridad_val:
                filtro_p = Q(nombre__iexact=prioridad_val)
                if prioridad_val.isdigit():
                    filtro_p |= Q(id=int(prioridad_val))
                prio_obj = Prioridad.objects.filter(filtro_p).first()
                if prio_obj:
                    ticket.prioridad = prio_obj

            ticket.tecnico_asignado = tecnico
            if not ticket.fecha_asignacion:
                ticket.fecha_asignacion = timezone.now()

            estado_revision = (
                EstadoTicket.objects.filter(nombre__in=['EN_PROCESO', 'En Revisión', 'En Proceso']).first()
                or ticket.estado
            )
            if ticket.estado != estado_revision:
                est_ant = ticket.estado
                ticket.estado = estado_revision
                CambioEstado.objects.create(
                    ticket=ticket,
                    estado_anterior=est_ant,
                    estado_nuevo=estado_revision,
                    modificado_por=request.user,
                    motivo=f"Asignado gerencialmente al técnico {tecnico.username}."
                )

            Asignacion.objects.create(
                ticket=ticket,
                tecnico_asignado=tecnico,
                asignado_por=request.user
            )
            Auditoria.objects.create(
                ticket=ticket,
                usuario=request.user,
                accion=f"Ticket asignado a {tecnico.username} por gerencia ({request.user.username})"
            )
            ticket.save()
            messages.success(request, f"Ticket {ticket.folio} asignado exitosamente a {tecnico.get_full_name() or tecnico.username}.")

        elif accion == 'quitar':
            if ticket.tecnico_asignado_id == tecnico.id:
                ticket.tecnico_asignado = None
                Auditoria.objects.create(
                    ticket=ticket,
                    usuario=request.user,
                    accion=f"Ticket desasignado de {tecnico.username} por gerencia ({request.user.username})"
                )
                ticket.save()
                messages.success(request, f"Ticket {ticket.folio} retirado de la bandeja de {tecnico.get_full_name() or tecnico.username}.")
            else:
                messages.error(request, "El ticket seleccionado no pertenece a este técnico.")

        return redirect('gerente_detalle_tecnico', tecnico_id=tecnico.id)

    tickets_tecnico = Ticket.objects.filter(
        tecnico_asignado=tecnico
    ).select_related('prioridad', 'estado', 'modalidad').order_by('-fecha_creacion')

    total_tec = tickets_tecnico.count()
    activos_qs = tickets_tecnico.exclude(Q(estado__es_final=True) | Q(estado__nombre__in=estados_finales))
    atrasados_count = activos_qs.filter(fecha_creacion__lt=umbral_atraso).count()
    cumplimiento_sla = max(0, round(((total_tec - atrasados_count) / total_tec) * 100)) if total_tec > 0 else 100

    tickets_tabla = []
    for t in tickets_tecnico:
        es_final = t.estado.es_final or (t.estado.nombre in estados_finales)
        atrasado = (not es_final) and (t.fecha_creacion < umbral_atraso)
        tickets_tabla.append({
            'id': t.id,
            'folio': t.folio,
            'asunto': t.asunto,
            'prioridad': t.prioridad.nombre if t.prioridad else 'Media',
            'estado_nombre': t.estado.nombre if t.estado else 'Creado',
            'estado_sla': 'Atrasado' if atrasado else ('Completado' if es_final else 'A tiempo'),
            'es_atrasado': atrasado,
            'modalidad': t.modalidad.nombre if t.modalidad else 'Presencial',
        })

    tickets_sin_asignar = Ticket.objects.filter(
        tecnico_asignado__isnull=True
    ).exclude(Q(estado__es_final=True) | Q(estado__nombre__in=estados_finales)).order_by('-fecha_creacion')

    return render(request, 'gerencia/detalles_tickettecnico.html', {
        'modulo': 'gestion_tecnicos',
        'usuario': request.user,
        'tecnico': tecnico,
        'nombre_tecnico': tecnico.get_full_name() or tecnico.username,
        'cumplimiento_sla': cumplimiento_sla,
        'tickets_tecnico': tickets_tabla,
        'total_asignados': len(tickets_tabla),
        'tickets_sin_asignar': tickets_sin_asignar,
        'prioridades': Prioridad.objects.all(),
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
    """Perfil y datos del usuario autenticado (incluyendo preferencia de tema)."""
    if request.method == 'POST':
        telefono = request.POST.get('telefono', '').strip()
        campos_actualizar = []
        if hasattr(request.user, 'telefono') and telefono:
            request.user.telefono = telefono
            campos_actualizar.append('telefono')

        if 'modo_oscuro' in request.POST and hasattr(request.user, 'modo_oscuro'):
            val_tema = str(request.POST.get('modo_oscuro')).lower()
            request.user.modo_oscuro = val_tema in ('true', '1', 'dark', 'on')
            campos_actualizar.append('modo_oscuro')

        if campos_actualizar:
            request.user.save(update_fields=campos_actualizar)
            messages.success(request, "Tus datos han sido actualizados con éxito.")
        return redirect('datos_usuario')

    return render(request, 'general/datos_usuario.html', {
        'modulo': 'perfil',
        'usuario': request.user,
    })


@login_required
@require_POST
def api_cambiar_tema_view(request):
    """
    Endpoint API para sincronizar el selector de tema (Oscuro/Claro)
    con el campo `modo_oscuro` del modelo CustomUser en el backend.
    Soporta payload JSON ({"modo_oscuro": true/false} o {"tema": "dark"/"light"})
    o datos de formulario estándar.
    """
    nuevo_modo_oscuro = None

    if request.content_type and 'application/json' in request.content_type:
        try:
            data = json.loads(request.body.decode('utf-8') or '{}')
            if 'modo_oscuro' in data:
                nuevo_modo_oscuro = bool(data['modo_oscuro'])
            elif 'tema' in data:
                nuevo_modo_oscuro = str(data['tema']).lower() in ('dark', 'oscuro', 'true', '1')
        except (ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({
                'status': 'error',
                'message': 'Formato JSON inválido.'
            }, status=400)
    else:
        if 'modo_oscuro' in request.POST:
            nuevo_modo_oscuro = str(request.POST.get('modo_oscuro')).lower() in ('true', '1', 'dark', 'oscuro', 'on')
        elif 'tema' in request.POST:
            nuevo_modo_oscuro = str(request.POST.get('tema')).lower() in ('dark', 'oscuro', 'true', '1')

    # Si no se especificó un valor explícito, alterna (toggle) el estado actual
    if nuevo_modo_oscuro is None:
        nuevo_modo_oscuro = not getattr(request.user, 'modo_oscuro', True)

    request.user.modo_oscuro = nuevo_modo_oscuro
    request.user.save(update_fields=['modo_oscuro'])

    return JsonResponse({
        'status': 'success',
        'modo_oscuro': request.user.modo_oscuro,
        'tema': 'dark' if request.user.modo_oscuro else 'light',
        'message': f"Tema actualizado a {'Oscuro' if request.user.modo_oscuro else 'Claro'}."
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
