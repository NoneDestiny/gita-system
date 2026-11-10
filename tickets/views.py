from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone

from users.permissions import cliente_required, tecnico_required
from catalogos.models import Categoria, EstadoTicket, Prioridad
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
    Incorpora motor de búsqueda por texto (folio, asunto, descripción)
    y filtros rápidos por estado y categoría.
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

    context = {
        'tickets': tickets,
        'total_tickets': tickets.count(),
        'categorias': Categoria.objects.all(),
        'estados': EstadoTicket.objects.all(),
        'query_actual': query,
        'estado_actual': estado_filtro,
        'categoria_actual': categoria_filtro,
        'usuario': request.user,
        'modulo': 'historico',
    }
    return render(request, 'cliente/historico.html', context)


@cliente_required
def crear_ticket_view(request):
    """
    Controlador para el registro de una nueva incidencia (Rol Cliente).
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
            equipo = Equipo.objects.filter(
                Q(serial__iexact=serial_val) | Q(id__iexact=serial_val)
            ).first()
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
            categoria = Categoria.objects.filter(
                Q(nombre__iexact=cat_val) | Q(id__iexact=cat_val)
            ).first()
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
    Muestra los tickets asignados al técnico en sesión y tickets disponibles sin asignar.
    """
    tickets_propios = Ticket.objects.filter(
        tecnico_asignado=request.user
    ).select_related('categoria', 'prioridad', 'estado', 'equipo', 'usuario')

    tickets_disponibles = Ticket.objects.filter(
        tecnico_asignado__isnull=True
    ).select_related('categoria', 'prioridad', 'estado', 'equipo', 'usuario')

    context = {
        'tickets_asignados': tickets_propios,
        'tickets_disponibles': tickets_disponibles,
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
    - Cambio de estado con Trazabilidad Inquebrantable en CambioEstado.
    - Marcado automático de fecha_cierre cuando el ticket pasa a Resuelto o Cerrado.
    """
    ticket = None
    if ticket_id:
        ticket = get_object_or_404(Ticket, id=ticket_id)
    else:
        # Si no se pasó id por URL, tomar el primer ticket asignado o query param
        tid = request.GET.get('ticket_id') or request.POST.get('ticket_id')
        if tid:
            ticket = get_object_or_404(Ticket, id=tid)
        else:
            ticket = Ticket.objects.filter(tecnico_asignado=request.user).first()

    if request.method == 'POST' and ticket:
        nuevo_estado_id = request.POST.get('nuevo_estado')
        diagnostico = request.POST.get('diagnostico', '').strip()
        tiempo_minutos = request.POST.get('tiempo_minutos', '0').strip()
        tiempo_val = int(tiempo_minutos) if tiempo_minutos.isdigit() else 0

        # Obtener nuevo estado
        nuevo_estado = None
        if nuevo_estado_id:
            nuevo_estado = EstadoTicket.objects.filter(
                Q(id__iexact=nuevo_estado_id) | Q(nombre__iexact=nuevo_estado_id)
            ).first()

        if not nuevo_estado:
            nuevo_estado = EstadoTicket.objects.filter(nombre__in=['RESUELTO', 'Resuelto']).first() or ticket.estado

        # 1. Trazabilidad Inquebrantable: Registrar CambioEstado
        estado_anterior = ticket.estado
        if estado_anterior != nuevo_estado:
            ticket.estado = nuevo_estado
            CambioEstado.objects.create(
                ticket=ticket,
                estado_anterior=estado_anterior,
                estado_nuevo=nuevo_estado,
                modificado_por=request.user,
                motivo=diagnostico[:255] if diagnostico else "Cambio de estado por resolución técnica."
            )

        # 2. Registrar Intervención y Diagnóstico
        if diagnostico:
            Intervencion.objects.create(
                ticket=ticket,
                tecnico=request.user,
                descripcion=diagnostico,
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
            accion=f"Actualización de estado a {nuevo_estado.nombre} con diagnóstico"
        )

        ticket.save()

        # 5. Notificación por correo al cliente
        tipo_notif = 'RESOLUCION' if nuevo_estado.nombre.upper() in ['RESUELTO', 'CERRADO'] else 'ACTUALIZACION'
        notificar_ticket_segundo_plano(ticket, tipo_notif, mensaje_extra=diagnostico)

        messages.success(request, f"Diagnóstico registrado y ticket {ticket.folio} actualizado a {nuevo_estado.nombre}.")
        return redirect('tecnico_tickets_asignados')

    context = {
        'ticket': ticket,
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
    ).distinct().select_related('categoria', 'prioridad', 'estado', 'usuario')

    context = {
        'tickets': tickets_atendidos,
        'usuario': request.user,
        'modulo': 'historial_tecnico',
    }
    return render(request, 'tecnico/historial_tecnico.html', context)
