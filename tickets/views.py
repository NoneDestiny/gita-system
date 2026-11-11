from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
import json
import logging
from google import genai
from google.genai import types
from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger(__name__)

client = None
if hasattr(settings, 'GEMINI_API_KEY') and settings.GEMINI_API_KEY:
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

from users.permissions import cliente_required, tecnico_required, obtener_ruta_por_rol
from catalogos.models import Categoria, EstadoTicket, Prioridad
from inventario.models import Repuesto, MovimientoInventario
from .models import (
    Ticket, 
    Equipo, 
    Evidencia, 
    CambioEstado, 
    Escalamiento, 
    Intervencion, 
    Asignacion, 
    Auditoria,
    validar_evidencia
)
from .emails import notificar_ticket_segundo_plano


# ==============================================================================
# FLUJO DEL CLIENTE
# ==============================================================================

@cliente_required
def cliente_historico_view(request):
    """
    Vista de consulta y seguimiento de tickets propios del cliente autenticado.
    Incorpora motor de búsqueda por texto (folio, asunto, descripción),
    filtros rápidos por estado y categoría, y ordenamiento dinámico.
    """
    tickets = Ticket.objects.filter(
        usuario=request.user
    ).select_related('categoria', 'prioridad', 'estado', 'equipo', 'modalidad')

    # 1. Motor de Búsqueda (?q=)
    query = request.GET.get('q', '').strip()
    if query:
        tickets = tickets.filter(
            Q(folio__icontains=query) |
            Q(asunto__icontains=query) |
            Q(descripcion__icontains=query)
        )

    # 2. Filtro por Estado (?estado=ID o ?estado=NOMBRE)
    estado_filtro = request.GET.get('estado', '').strip()
    if estado_filtro:
        if estado_filtro.isdigit():
            tickets = tickets.filter(estado_id=int(estado_filtro))
        else:
            tickets = tickets.filter(estado__nombre__iexact=estado_filtro)

    # 3. Filtro por Categoría (?categoria=ID o ?categoria=NOMBRE)
    categoria_filtro = request.GET.get('categoria', '').strip()
    if categoria_filtro:
        if categoria_filtro.isdigit():
            tickets = tickets.filter(categoria_id=int(categoria_filtro))
        else:
            tickets = tickets.filter(categoria__nombre__iexact=categoria_filtro)

    # 4. Ordenamiento (?orden=)
    orden = request.GET.get('orden', 'Fecha').strip()
    mapa_orden = {
        'Fecha': '-fecha_creacion',
        'Prioridad': '-prioridad__nivel',
        'Estado': 'estado__nombre',
        'Asunto': 'asunto',
        'Código reporte': 'folio',
    }
    tickets = tickets.order_by(mapa_orden.get(orden, '-fecha_creacion'))

    context = {
        'tickets': tickets,
        'total_tickets': tickets.count(),
        'categorias': Categoria.objects.all(),
        'estados': EstadoTicket.objects.all(),
        'query_actual': query,
        'estado_actual': estado_filtro,
        'categoria_actual': categoria_filtro,
        'orden_actual': orden if orden in mapa_orden else 'Fecha',
        'usuario': request.user,
        'modulo': 'historico',
    }
    return render(request, 'cliente/historico.html', context)


@login_required
def detalle_ticket_view(request, ticket_id):
    """
    Vista de detalle completo de un ticket:
    - Si es CLIENTE, solo puede consultar tickets propios.
    - Si es TECNICO o GERENTE, puede consultar cualquier ticket del sistema.
    """
    ticket = get_object_or_404(
        Ticket.objects.select_related(
            'categoria', 'prioridad', 'estado', 'equipo', 'modalidad', 'usuario', 'tecnico_asignado'
        ).prefetch_related('evidencias', 'intervenciones'),
        id=ticket_id
    )

    rol_usuario = getattr(request.user, 'rol', 'CLIENTE')
    if rol_usuario == 'CLIENTE' and ticket.usuario_id != request.user.id and not request.user.is_superuser:
        raise PermissionDenied("No tienes permiso para ver los detalles de un ticket ajeno.")

    evidencias = ticket.evidencias.all()
    evidencia_principal = evidencias.first()
    ultima_intervencion = ticket.intervenciones.order_by('-fecha_registro').first()

    context = {
        'ticket': ticket,
        'evidencia': evidencia_principal,
        'evidencias': evidencias,
        'ultima_intervencion': ultima_intervencion,
        'usuario': request.user,
        'modulo': 'detalle_ticket',
    }
    return render(request, 'general/detalle_ticket.html', context)


@login_required
def crear_ticket_view(request):
    """
    Controlador para el registro de una nueva incidencia (Rol Cliente y Usuarios Autenticados).
    - Validación Multimedia Estricta: JPG, PNG, JPEG máx 5MB.
    - Generación de Código Único: Asigna automáticamente estado inicial,
      prioridad por defecto, usuario y genera el folio secuencial en save().
    """
    if request.method == 'POST':
        asunto = request.POST.get('asunto', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        serial_val = request.POST.get('serial') or request.POST.get('equipo')
        cat_val = request.POST.get('categoria')

        errores = []

        if not asunto:
            errores.append("El campo 'Asunto' es obligatorio.")
        if not descripcion:
            errores.append("El campo 'Descripción' es obligatorio.")

        equipo = None
        if serial_val:
            filtro_eq = Q(serial__iexact=serial_val)
            if str(serial_val).isdigit():
                filtro_eq |= Q(id=int(serial_val))
            equipo = Equipo.objects.filter(filtro_eq).first()
        if not equipo:
            equipo = Equipo.objects.first()
            if not equipo:
                equipo = Equipo.objects.create(
                    serial='GENERIC-001',
                    marca='Genérica',
                    modelo='Equipo TI'
                )

        categoria = None
        if cat_val:
            filtro_cat = Q(nombre__iexact=cat_val)
            if str(cat_val).isdigit():
                filtro_cat |= Q(id=int(cat_val))
            categoria = Categoria.objects.filter(filtro_cat).first()
        if not categoria:
            categoria = Categoria.objects.first()
            if not categoria:
                categoria = Categoria.objects.create(
                    nombre='General',
                    descripcion='Incidencia general'
                )

        # Validación Multimedia Estricta
        archivos = request.FILES.getlist('evidencias') or request.FILES.getlist('evidencia')
        for archivo in archivos:
            try:
                validar_evidencia(archivo)
            except ValidationError as e:
                errores.append(f"Error en archivo '{archivo.name}': {e.message}")

        if errores:
            for err in errores:
                messages.error(request, err)
        else:
            # 1. Asignar Estado Inicial Automático
            estado_inicial = (
                EstadoTicket.objects.filter(es_inicial=True).first() or
                EstadoTicket.objects.filter(nombre__iexact='CREADO').first() or
                EstadoTicket.objects.first()
            )
            if not estado_inicial:
                estado_inicial = EstadoTicket.objects.create(nombre='CREADO', es_inicial=True)

            # 2. Asignar Prioridad por defecto
            prioridad_defecto = (
                Prioridad.objects.filter(nombre__iexact='Media').first() or
                Prioridad.objects.first()
            )
            if not prioridad_defecto:
                prioridad_defecto = Prioridad.objects.create(nombre='Media', nivel=2)

            # 3. Guardar Ticket (Genera automáticamente el Folio único secuencial en save())
            ticket = Ticket(
                asunto=asunto,
                descripcion=descripcion,
                usuario=request.user,
                equipo=equipo,
                categoria=categoria,
                prioridad=prioridad_defecto,
                estado=estado_inicial,
            )
            ticket.save()

            # 4. Guardar Evidencias válidas
            for archivo in archivos:
                Evidencia.objects.create(
                    ticket=ticket,
                    archivo=archivo,
                    subido_por=request.user
                )

            # 5. Enviar notificación por correo en segundo plano (Asíncrono)
            notificar_ticket_segundo_plano(ticket, 'CREACION')

            messages.success(request, f"¡Ticket registrado con éxito! Folio generado: {ticket.folio}")
            return redirect('cliente_historico')

    context = {
        'categorias': Categoria.objects.all(),
        'equipos': Equipo.objects.all(),
        'usuario': request.user,
        'modulo': 'crear_reporte',
    }
    return render(request, 'general/crear_reporte.html', context)


# ==============================================================================
# FLUJO DEL PERSONAL TÉCNICO (RBAC, DIAGNÓSTICOS, TRAZABILIDAD Y ESCALAMIENTO)
# ==============================================================================

@tecnico_required
def tecnico_tickets_asignados_view(request):
    """
    Bandeja de trabajo del personal técnico:
    Muestra los tickets asignados al técnico en sesión y tickets disponibles sin asignar,
    con soporte de ordenamiento dinámico (?orden=).
    """
    orden = request.GET.get('orden', 'Prioridad').strip()
    mapa_orden = {
        'Prioridad': '-prioridad__nivel',
        'Asunto': 'asunto',
        'Estado': 'estado__nombre',
        'Fecha': '-fecha_creacion',
    }
    campo_orden = mapa_orden.get(orden, '-prioridad__nivel')

    tickets_propios = Ticket.objects.filter(
        tecnico_asignado=request.user
    ).select_related('categoria', 'prioridad', 'estado', 'equipo', 'usuario').order_by(campo_orden)

    tickets_disponibles = Ticket.objects.filter(
        tecnico_asignado__isnull=True
    ).select_related('categoria', 'prioridad', 'estado', 'equipo', 'usuario').order_by('-fecha_creacion')

    context = {
        'tickets_asignados': tickets_propios,
        'tickets_disponibles': tickets_disponibles,
        'orden_actual': orden if orden in mapa_orden else 'Prioridad',
        'usuario': request.user,
        'modulo': 'tickets_asignados',
    }
    return render(request, 'tecnico/tickets_asignados.html', context)


@tecnico_required
def autoasignar_ticket_view(request, ticket_id):
    """
    Permite al técnico autoasignarse un ticket:
    - Marca fecha_asignacion automáticamente (Cálculo de Tiempos).
    - Cambia estado a 'En Revisión' / 'EN_PROCESO'.
    - Registra en Asignacion, CambioEstado y Auditoria.
    """
    ticket = get_object_or_404(Ticket, id=ticket_id)

    # 1. Asignar técnico y marcar fecha_asignacion automática
    ticket.tecnico_asignado = request.user
    if not ticket.fecha_asignacion:
        ticket.fecha_asignacion = timezone.now()

    # 2. Registrar en Asignación
    Asignacion.objects.create(
        ticket=ticket,
        tecnico_asignado=request.user,
        asignado_por=request.user
    )

    # 3. Transición de estado a 'En Revisión'
    estado_en_revision = (
        EstadoTicket.objects.filter(nombre__in=['EN_PROCESO', 'En Revisión', 'En Proceso']).first() or
        ticket.estado
    )
    if ticket.estado != estado_en_revision:
        estado_ant = ticket.estado
        ticket.estado = estado_en_revision
        # Trazabilidad Inquebrantable
        CambioEstado.objects.create(
            ticket=ticket,
            estado_anterior=estado_ant,
            estado_nuevo=estado_en_revision,
            modificado_por=request.user,
            motivo="Autoasignación del ticket por el técnico."
        )

    # 4. Auditoría
    Auditoria.objects.create(
        ticket=ticket,
        usuario=request.user,
        accion=f"Autoasignación por el técnico {request.user.username}"
    )

    ticket.save()
    messages.success(request, f"Te has autoasignado exitosamente el ticket {ticket.folio}.")
    return redirect('tecnico_tickets_asignados')


@tecnico_required
def solucionar_ticket_view(request, ticket_id=None):
    """
    Gestión y resolución de incidencias por el técnico:
    - Registro de diagnósticos e intervenciones técnicas con tiempo invertido.
    - Lógica transaccional de uso de repuestos (MovimientoInventario con select_for_update),
      validación de stock insuficiente y disparo de alertas de reposición.
    - Subida de evidencia técnica adjunta y consulta de la evidencia del cliente.
    - Cambio de estado con Trazabilidad Inquebrantable en CambioEstado.
    - Marcado automático de fecha_cierre cuando el ticket pasa a Resuelto o Cerrado.
    """
    ticket = None
    if ticket_id:
        ticket = get_object_or_404(Ticket, id=ticket_id)
    else:
        tid = request.GET.get('ticket_id') or request.POST.get('ticket_id')
        if tid and str(tid).isdigit():
            ticket = get_object_or_404(Ticket, id=int(tid))
        else:
            ticket = Ticket.objects.filter(tecnico_asignado=request.user).first()

    if request.method == 'POST' and ticket:
        nuevo_estado_id = request.POST.get('nuevo_estado')
        diagnostico = (request.POST.get('diagnostico') or request.POST.get('solucion') or '').strip()
        tiempo_minutos = request.POST.get('tiempo_minutos', '0').strip()
        tiempo_val = int(tiempo_minutos) if tiempo_minutos.isdigit() else 0

        # Captura de datos de uso de repuesto (opcional en la intervención)
        repuesto_id_raw = (request.POST.get('repuesto_id') or '').strip()
        cantidad_rep_raw = (request.POST.get('cantidad_repuesto') or '0').strip()

        cantidad_repuesto = 0
        if repuesto_id_raw:
            try:
                cantidad_repuesto = int(cantidad_rep_raw)
                if cantidad_repuesto <= 0:
                    raise ValueError()
            except ValueError:
                messages.error(request, "La cantidad del repuesto a utilizar debe ser un número entero mayor a cero.")
                return redirect('tecnico_solucion_caso_detalle', ticket_id=ticket.id)

        # Validar evidencia técnica antes de abrir la transacción si fue adjuntada
        archivo_tecnico = request.FILES.get('evidencia_tecnica')
        if archivo_tecnico:
            try:
                validar_evidencia(archivo_tecnico)
            except ValidationError as e:
                messages.error(request, f"Error en evidencia técnica '{archivo_tecnico.name}': {e.message}")
                return redirect('tecnico_solucion_caso_detalle', ticket_id=ticket.id)

        # Obtener nuevo estado
        nuevo_estado = None
        if nuevo_estado_id:
            filtro_est = Q(nombre__iexact=nuevo_estado_id)
            if str(nuevo_estado_id).isdigit():
                filtro_est |= Q(id=int(nuevo_estado_id))
            nuevo_estado = EstadoTicket.objects.filter(filtro_est).first()

        if not nuevo_estado:
            nuevo_estado = EstadoTicket.objects.filter(nombre__in=['RESUELTO', 'Resuelto']).first() or ticket.estado

        alerta_reposicion_msg = None
        repuesto_usado_info = ""

        try:
            # Transacción Atómica: Si el descuento de inventario falla por stock insuficiente,
            # se revierte absolutamente toda la operación sin alterar el ticket ni crear registros huérfanos.
            with transaction.atomic():
                # 0. Descuento transaccional de repuesto con bloqueo de fila (select_for_update)
                if repuesto_id_raw:
                    filtro_rep = Q(codigo__iexact=repuesto_id_raw)
                    if repuesto_id_raw.isdigit():
                        filtro_rep |= Q(id=int(repuesto_id_raw))
                    repuesto_obj = Repuesto.objects.select_for_update().filter(filtro_rep).first()
                    if not repuesto_obj:
                        raise ValidationError("El repuesto seleccionado no existe en el inventario.")

                    MovimientoInventario.objects.create(
                        repuesto=repuesto_obj,
                        tipo_movimiento='SALIDA',
                        cantidad=cantidad_repuesto,
                        ticket=ticket,
                        registrado_por=request.user,
                        observacion=diagnostico[:255] if diagnostico else f"Uso en intervención del ticket {ticket.folio}"
                    )
                    repuesto_obj.refresh_from_db()
                    repuesto_usado_info = f" [Repuesto utilizado: {cantidad_repuesto}x {repuesto_obj.nombre} ({repuesto_obj.codigo})]"

                    # Detección automática de Alerta de Reposición (stock <= stock_minimo)
                    if repuesto_obj.requiere_reposicion:
                        alerta_reposicion_msg = (
                            f"⚠️ ALERTA DE REPOSICIÓN: El repuesto '{repuesto_obj.nombre}' ({repuesto_obj.codigo}) "
                            f"quedó en estado CRÍTICO ({repuesto_obj.stock_actual} disponibles / mínimo requerido: {repuesto_obj.stock_minimo})."
                        )
                        Auditoria.objects.create(
                            ticket=ticket,
                            usuario=request.user,
                            accion=f"ALERTA_STOCK_CRITICO: {repuesto_obj.codigo} cayó a {repuesto_obj.stock_actual} unidades (mín: {repuesto_obj.stock_minimo})"
                        )

                # Guardar evidencia técnica si existe
                if archivo_tecnico:
                    Evidencia.objects.create(
                        ticket=ticket,
                        archivo=archivo_tecnico,
                        subido_por=request.user
                    )

                # 1. Trazabilidad Inquebrantable: Registrar CambioEstado
                estado_anterior = ticket.estado
                if estado_anterior != nuevo_estado:
                    ticket.estado = nuevo_estado
                    CambioEstado.objects.create(
                        ticket=ticket,
                        estado_anterior=estado_anterior,
                        estado_nuevo=nuevo_estado,
                        modificado_por=request.user,
                        motivo=(diagnostico + repuesto_usado_info)[:255] if diagnostico else "Cambio de estado por resolución técnica."
                    )

                # 2. Registrar Intervención y Diagnóstico
                if diagnostico or repuesto_usado_info:
                    Intervencion.objects.create(
                        ticket=ticket,
                        tecnico=request.user,
                        descripcion=f"{diagnostico}{repuesto_usado_info}".strip(),
                        tiempo_invertido_minutos=tiempo_val
                    )

                # 3. Cálculo de Tiempos: Marcar automáticamente fecha_cierre al resolver/cerrar
                nombres_cierre = ['RESUELTO', 'CERRADO', 'Resuelto', 'Cerrado']
                if nuevo_estado.es_final or nuevo_estado.nombre in nombres_cierre:
                    if not ticket.fecha_cierre:
                        ticket.fecha_cierre = timezone.now()

                # 4. Auditoría
                Auditoria.objects.create(
                    ticket=ticket,
                    usuario=request.user,
                    accion=f"Actualización de estado a {nuevo_estado.nombre} con diagnóstico{repuesto_usado_info}"
                )

                ticket.save()

        except ValidationError as exc:
            msg_err = exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc)
            messages.error(request, msg_err)
            return redirect('tecnico_solucion_caso_detalle', ticket_id=ticket.id)

        # 5. Notificación por correo al cliente
        tipo_notif = 'RESOLUCION' if nuevo_estado.nombre.upper() in ['RESUELTO', 'CERRADO'] else 'ACTUALIZACION'
        notificar_ticket_segundo_plano(ticket, tipo_notif, mensaje_extra=diagnostico)

        if alerta_reposicion_msg:
            messages.warning(request, alerta_reposicion_msg)

        messages.success(request, f"Diagnóstico registrado y ticket {ticket.folio} actualizado a {nuevo_estado.nombre}.")
        return redirect('tecnico_tickets_asignados')

    evidencia_cliente = None
    movimientos_ticket = []
    if ticket:
        evidencia_cliente = ticket.evidencias.filter(subido_por=ticket.usuario).first() or ticket.evidencias.first()
        movimientos_ticket = ticket.repuestos_utilizados.select_related('repuesto', 'registrado_por').all()

    context = {
        'ticket': ticket,
        'evidencia_cliente': evidencia_cliente,
        'movimientos_ticket': movimientos_ticket,
        'repuestos': Repuesto.objects.all().order_by('nombre'),
        'estados': EstadoTicket.objects.all(),
        'usuario': request.user,
        'modulo': 'solucion_caso',
    }
    return render(request, 'tecnico/solucion_caso.html', context)


@tecnico_required
def escalar_ticket_view(request, ticket_id):
    """
    Escalamiento de tickets:
    - Registra en la tabla Escalamiento (Métricas obligatorias para SIG-543).
    - Registra obligatoriamente en Intervencion.
    - Notifica al equipo y cliente en segundo plano.
    """
    ticket = get_object_or_404(Ticket, id=ticket_id)

    if request.method == 'POST':
        destino = request.POST.get('grupo_o_tecnico_destino', '').strip()
        motivo = request.POST.get('motivo', '').strip()
        tiempo_minutos = request.POST.get('tiempo_minutos', '0').strip()
        tiempo_val = int(tiempo_minutos) if tiempo_minutos.isdigit() else 0

        if not destino or not motivo:
            messages.error(request, "Debe indicar el grupo/técnico destino y el motivo del escalamiento.")
            return redirect('tecnico_solucion_caso_detalle', ticket_id=ticket.id)

        # 1. Métricas de Escalamiento obligatorias (SIG-543)
        Escalamiento.objects.create(
            ticket=ticket,
            tecnico_origen=request.user,
            grupo_o_tecnico_destino=destino,
            motivo=motivo
        )

        # 2. Registrar Intervención obligatoria vinculada
        Intervencion.objects.create(
            ticket=ticket,
            tecnico=request.user,
            descripcion=f"Escalamiento a {destino}. Motivo: {motivo}",
            tiempo_invertido_minutos=tiempo_val
        )

        # 3. Auditoría
        Auditoria.objects.create(
            ticket=ticket,
            usuario=request.user,
            accion=f"Ticket escalado a {destino} por {request.user.username}"
        )

        # 4. Notificar vía Correo en Segundo Plano
        notificar_ticket_segundo_plano(ticket, 'ESCALAMIENTO', mensaje_extra=f"Escalado a {destino}: {motivo}")

        messages.success(request, f"Ticket {ticket.folio} escalado exitosamente a {destino}.")
        return redirect('tecnico_tickets_asignados')

    return redirect('tecnico_tickets_asignados')


@tecnico_required
def tecnico_historial_view(request):
    """
    Historial de casos intervenidos o resueltos por el técnico.
    """
    tickets_atendidos = Ticket.objects.filter(
        Q(tecnico_asignado=request.user) | Q(intervenciones__tecnico=request.user)
    ).distinct().select_related(
        'categoria', 'prioridad', 'estado', 'usuario'
    ).prefetch_related('historial_estados', 'intervenciones')

    context = {
        'tickets': tickets_atendidos,
        'usuario': request.user,
        'modulo': 'historial_tecnico',
    }
    return render(request, 'tecnico/historial_tecnico.html', context)

# ==============================================================================
# ENDPOINT API PARA TRIAJE CON GEMINI (IA)
# ==============================================================================
@login_required
def api_triaje_gemini_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    if not client:
        return JsonResponse({
            'asunto': 'Falla de equipo TI',
            'categoria': 'Hardware',
            'sintesis': 'El asistente de IA no está configurado. Se ha asignado una categoría por defecto.'
        })

    try:
        data = json.loads(request.body)
        descripcion = data.get('descripcion', '').strip()
        
        if len(descripcion) < 10:
            return JsonResponse({'error': 'Descripción muy corta'}, status=400)

        prompt = f"""
        Eres un asistente de mesa de ayuda (Helpdesk). Analiza la siguiente descripción de un problema técnico:
        "{descripcion}"
        
        Devuelve ÚNICAMENTE un objeto JSON válido con esta estructura exacta, sin texto adicional, sin markdown, sin saludos:
        {{
            "asunto": "Resumen corto de máximo 20 caracteres",
            "categoria": "Debe ser una de estas: Hardware, Software, Redes",
            "sintesis": "Una breve explicación de por qué asignaste esa categoría (máx 2 líneas)"
        }}
        """

        # Nueva sintaxis del SDK de Google
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                timeout=15.0 # 15 segundos max
            )
        )
        
        resultado_json = json.loads(response.text)
        return JsonResponse(resultado_json)

    except Exception as e:
        logger.error(f"Error con Gemini: {str(e)}")
        return JsonResponse({
            'asunto': 'Falla de equipo TI',
            'categoria': 'Hardware',
            'sintesis': 'El asistente de IA no está disponible en este momento. Se ha asignado una categoría por defecto.'
        })