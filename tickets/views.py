from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Q
from django.core.exceptions import ValidationError
from users.permissions import cliente_required
from catalogos.models import Categoria, EstadoTicket, Prioridad
from .models import Ticket, Equipo, Evidencia, validar_evidencia
from .emails import notificar_ticket_segundo_plano


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

        # Validaciones de campos obligatorios
        if not asunto:
            errores.append("El campo 'Asunto' es obligatorio.")
        if not descripcion:
            errores.append("El campo 'Descripción' es obligatorio.")

        # Obtener equipo
        equipo = None
        if serial_val:
            equipo = Equipo.objects.filter(
                Q(serial__iexact=serial_val) | Q(id__iexact=serial_val)
            ).first()
        if not equipo:
            # Fallback al primer equipo disponible o registro
            equipo = Equipo.objects.first()
            if not equipo:
                equipo = Equipo.objects.create(
                    serial='GENERIC-001',
                    marca='Genérica',
                    modelo='Equipo TI'
                )

        # Obtener categoría
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
