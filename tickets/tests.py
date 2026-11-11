import time
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from users.models import CustomUser
from catalogos.models import Categoria, EstadoTicket, Prioridad
from tickets.models import (
    Ticket, 
    Equipo, 
    Evidencia, 
    Notificacion, 
    CambioEstado, 
    Escalamiento, 
    Intervencion, 
    Asignacion
)
from tickets.emails import notificar_ticket_segundo_plano, _enviar_correo_tarea


class ClienteTicketMVTTestCase(TestCase):
    """
    Pruebas para los Criterios de Aceptación del Rol Cliente:
    1. Validación Multimedia Estricta (formato JPG/PNG/JPEG y máx 5MB).
    2. Generación de Código Único (Folio) y estado inicial automático.
    3. Motor de Búsqueda y Filtros en la vista de seguimiento.
    4. Notificaciones por Correo Electrónico y registro histórico en BD.
    """

    def setUp(self):
        self.client = Client()

        self.cliente = CustomUser.objects.create_user(
            username='cliente_criterio',
            email='cliente@test.com',
            cedula='V-99999999',
            password='Password123*',
            rol='CLIENTE'
        )

        self.otro_cliente = CustomUser.objects.create_user(
            username='otro_cliente',
            email='otro@test.com',
            cedula='V-88888888',
            password='Password123*',
            rol='CLIENTE'
        )

        self.categoria_soft = Categoria.objects.create(nombre='Software', descripcion='Apps')
        self.categoria_hard = Categoria.objects.create(nombre='Hardware', descripcion='Piezas')
        self.estado_creado = EstadoTicket.objects.create(nombre='CREADO', es_inicial=True)
        self.estado_proceso = EstadoTicket.objects.create(nombre='EN_PROCESO')
        self.prioridad_media = Prioridad.objects.create(nombre='Media', nivel=2)

        self.equipo = Equipo.objects.create(serial='SN-TEST-001', marca='Dell', modelo='Latitude')
        self.client.login(username='cliente_criterio', password='Password123*')

    def test_evidencia_formato_invalido_rechazada(self):
        archivo_invalido = SimpleUploadedFile("doc.pdf", b"pdf content", content_type="application/pdf")
        response = self.client.post(reverse('crear_reporte'), {
            'asunto': 'Falla con PDF',
            'descripcion': 'Probando subida indebida',
            'serial': self.equipo.serial,
            'categoria': self.categoria_soft.nombre,
            'evidencias': archivo_invalido
        })
        self.assertEqual(Ticket.objects.count(), 0)

    def test_evidencia_exceso_tamano_rechazada(self):
        archivo_grande = SimpleUploadedFile("foto.jpg", b"0" * (6 * 1024 * 1024), content_type="image/jpeg")
        response = self.client.post(reverse('crear_reporte'), {
            'asunto': 'Falla con Imagen Grande',
            'descripcion': 'Probando exceso',
            'serial': self.equipo.serial,
            'categoria': self.categoria_soft.nombre,
            'evidencias': archivo_grande
        })
        self.assertEqual(Ticket.objects.count(), 0)

    def test_evidencia_valida_aceptada(self):
        archivo_valido = SimpleUploadedFile("captura.png", b"png content", content_type="image/png")
        response = self.client.post(reverse('crear_reporte'), {
            'asunto': 'Falla de Sistema',
            'descripcion': 'Pantalla azul',
            'serial': self.equipo.serial,
            'categoria': self.categoria_soft.nombre,
            'evidencias': archivo_valido
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(Evidencia.objects.count(), 1)

    def test_generacion_codigo_unico_y_estado_inicial(self):
        response = self.client.post(reverse('crear_reporte'), {
            'asunto': 'Teclado no responde',
            'descripcion': 'Falla teclas',
            'serial': self.equipo.serial,
            'categoria': self.categoria_hard.nombre,
        })
        self.assertEqual(response.status_code, 302)
        ticket = Ticket.objects.first()
        self.assertIsNotNone(ticket)
        self.assertTrue(ticket.folio.startswith('TK-'))
        self.assertEqual(ticket.estado.nombre, 'CREADO')
        self.assertEqual(ticket.prioridad.nombre, 'Media')
        self.assertEqual(ticket.usuario, self.cliente)
        self.assertIsNotNone(ticket.fecha_creacion)

    def test_busqueda_y_filtros_tickets_propios(self):
        t1 = Ticket.objects.create(
            asunto='Monitor parpadea',
            descripcion='Se apaga',
            usuario=self.cliente,
            equipo=self.equipo,
            categoria=self.categoria_hard,
            prioridad=self.prioridad_media,
            estado=self.estado_creado,
        )
        t2 = Ticket.objects.create(
            asunto='Error en Excel',
            descripcion='Fórmula no calcula',
            usuario=self.cliente,
            equipo=self.equipo,
            categoria=self.categoria_soft,
            prioridad=self.prioridad_media,
            estado=self.estado_proceso,
        )
        Ticket.objects.create(
            asunto='Ticket ajeno',
            descripcion='No visible',
            usuario=self.otro_cliente,
            equipo=self.equipo,
            categoria=self.categoria_soft,
            prioridad=self.prioridad_media,
            estado=self.estado_creado,
        )

        resp = self.client.get(reverse('cliente_historico'))
        self.assertEqual(resp.context['total_tickets'], 2)

        resp_q = self.client.get(reverse('cliente_historico'), {'q': 'Monitor'})
        self.assertEqual(resp_q.context['total_tickets'], 1)

        resp_est = self.client.get(reverse('cliente_historico'), {'estado': 'EN_PROCESO'})
        self.assertEqual(resp_est.context['total_tickets'], 1)

        resp_cat = self.client.get(reverse('cliente_historico'), {'categoria': 'Hardware'})
        self.assertEqual(resp_cat.context['total_tickets'], 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_envio_notificacion_y_registro_historico(self):
        ticket = Ticket.objects.create(
            asunto='Impresora sin tóner',
            descripcion='Reemplazo urgente',
            usuario=self.cliente,
            equipo=self.equipo,
            categoria=self.categoria_hard,
            prioridad=self.prioridad_media,
            estado=self.estado_creado,
        )
        notificar_ticket_segundo_plano(ticket, 'CREACION', async_mode=False)

        self.assertGreaterEqual(len(mail.outbox), 1)
        email_enviado = mail.outbox[-1]
        self.assertIn(ticket.folio, email_enviado.subject)

        notif_db = Notificacion.objects.filter(ticket=ticket, tipo_evento='CREACION').first()
        self.assertIsNotNone(notif_db)
        self.assertTrue(notif_db.exitoso)

    def test_maquetacion_cliente_predictiva_cards_e_independencia_color(self):
        """
        Verifica los 5 criterios de aceptación de maquetación para el Rol Cliente:
        1. Formularios predictivos (datalist sugerenciasAsunto, filtroPredictivoSerial, reglasPredictivas).
        2. Retroalimentación inmediata en tiempo real (feedbackAsunto, feedbackDescripcion, role="alert").
        3. Carga de evidencias con indicación visual de 5MB y restricción JPG, PNG, JPEG.
        4. Transformación móvil en lista de tarjetas verticales (<article> en xl:hidden grid-cols-1).
        5. Independencia del color en estados (texto explícito + icono SVG + aria-label="Estado del ticket: ...").
        """
        # 1-3: Vista de creación de reporte
        resp_crear = self.client.get(reverse('crear_reporte'))
        self.assertEqual(resp_crear.status_code, 200)
        self.assertContains(resp_crear, 'id="sugerenciasAsunto"')
        self.assertContains(resp_crear, 'id="filtroPredictivoSerial"')
        self.assertContains(resp_crear, 'reglasPredictivas')
        self.assertContains(resp_crear, 'id="feedbackAsunto"')
        self.assertContains(resp_crear, 'id="feedbackDescripcion"')
        self.assertContains(resp_crear, 'Formatos: JPG, PNG, JPEG')
        self.assertContains(resp_crear, 'Límite máximo: 5 MB')
        self.assertContains(resp_crear, 'accept=".jpg,.jpeg,.png,image/jpeg,image/png"')

        # 4-5: Vista de seguimiento histórico
        Ticket.objects.create(
            asunto='Falla de red',
            descripcion='Sin conexión al servidor',
            usuario=self.cliente,
            equipo=self.equipo,
            categoria=self.categoria_hard,
            prioridad=self.prioridad_media,
            estado=self.estado_proceso,
        )
        resp_hist = self.client.get(reverse('cliente_historico'))
        self.assertEqual(resp_hist.status_code, 200)
        self.assertContains(resp_hist, 'xl:hidden grid grid-cols-1 md:grid-cols-2')
        self.assertContains(resp_hist, '<article')
        self.assertContains(resp_hist, 'aria-label="Estado del ticket: EN_PROCESO (En atención técnica)"')
        self.assertContains(resp_hist, 'role="status"')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_notificacion_resolucion_y_escalamiento(self):
        ticket = Ticket.objects.create(
            asunto='Falla de Servidor',
            descripcion='Servicio caído',
            usuario=self.cliente,
            equipo=self.equipo,
            categoria=self.categoria_soft,
            prioridad=self.prioridad_media,
            estado=self.estado_creado,
        )
        notificar_ticket_segundo_plano(ticket, 'ESCALAMIENTO', mensaje_extra="Nivel 2", async_mode=False)
        self.assertTrue(Notificacion.objects.filter(ticket=ticket, tipo_evento='ESCALAMIENTO').exists())

        notificar_ticket_segundo_plano(ticket, 'RESOLUCION', mensaje_extra="Reemplazado", async_mode=False)
        self.assertTrue(Notificacion.objects.filter(ticket=ticket, tipo_evento='RESOLUCION').exists())

    def test_detalle_ticket_propio_y_bloqueo_ajeno(self):
        ticket_propio = Ticket.objects.create(
            asunto='Teclado dañado',
            descripcion='Falla tecla Enter',
            usuario=self.cliente,
            equipo=self.equipo,
            categoria=self.categoria_hard,
            prioridad=self.prioridad_media,
            estado=self.estado_creado,
        )
        ticket_ajeno = Ticket.objects.create(
            asunto='Mouse ajeno',
            descripcion='No mueve',
            usuario=self.otro_cliente,
            equipo=self.equipo,
            categoria=self.categoria_hard,
            prioridad=self.prioridad_media,
            estado=self.estado_creado,
        )

        resp_ok = self.client.get(reverse('detalle_ticket', kwargs={'ticket_id': ticket_propio.id}))
        self.assertEqual(resp_ok.status_code, 200)
        self.assertContains(resp_ok, ticket_propio.folio)

        resp_forbidden = self.client.get(reverse('detalle_ticket', kwargs={'ticket_id': ticket_ajeno.id}))
        self.assertEqual(resp_forbidden.status_code, 403)


class TecnicoGestionTicketTestCase(TestCase):
    """
    Pruebas para los Criterios de Aceptación del Personal Técnico:
    1. Trazabilidad Inquebrantable (CambioEstado en cada salto de ciclo de vida).
    2. Métricas de Escalamiento (Escalamiento e Intervención obligatorias para SIG-543).
    3. Cálculo de Tiempos (fecha_asignacion y fecha_cierre automáticas).
    """

    def setUp(self):
        self.client = Client()

        # Usuario Técnico
        self.tecnico = CustomUser.objects.create_user(
            username='tecnico_casos',
            email='tecnico@gita.com',
            cedula='V-77777777',
            password='Password123*',
            rol='TECNICO'
        )

        # Usuario Cliente
        self.cliente = CustomUser.objects.create_user(
            username='cliente_incidencia',
            email='cliente@empresa.com',
            cedula='V-66666666',
            password='Password123*',
            rol='CLIENTE'
        )

        # Catálogos del Ciclo de Vida: Abierto -> En Revisión -> Resuelto -> Cerrado
        self.categoria = Categoria.objects.create(nombre='Redes', descripcion='Conectividad')
        self.prioridad = Prioridad.objects.create(nombre='Alta', nivel=3)
        self.estado_abierto = EstadoTicket.objects.create(nombre='Abierto', es_inicial=True)
        self.estado_revision = EstadoTicket.objects.create(nombre='En Revisión')
        self.estado_resuelto = EstadoTicket.objects.create(nombre='Resuelto')
        self.estado_cerrado = EstadoTicket.objects.create(nombre='Cerrado', es_final=True)

        self.equipo = Equipo.objects.create(serial='SN-SWITCH-01', marca='Cisco', modelo='Catalyst 2960')

        # Ticket inicial sin técnico
        self.ticket = Ticket.objects.create(
            asunto='Switch piso 2 sin conexión',
            descripcion='Luces parpadean en ámbar',
            usuario=self.cliente,
            equipo=self.equipo,
            categoria=self.categoria,
            prioridad=self.prioridad,
            estado=self.estado_abierto,
        )

        # Autenticar técnico
        self.client.login(username='tecnico_casos', password='Password123*')

    # --------------------------------------------------------------------------
    # CRITERIO 1: Trazabilidad Inquebrantable
    # --------------------------------------------------------------------------
    def test_trazabilidad_inquebrantable_cambio_estado(self):
        """Todo cambio de estado debe insertar un registro automático en CambioEstado."""
        self.ticket.tecnico_asignado = self.tecnico
        self.ticket.estado = self.estado_revision
        self.ticket.save()

        # Técnico soluciona el caso cambiando a 'Resuelto'
        url = reverse('tecnico_solucion_caso_detalle', kwargs={'ticket_id': self.ticket.id})
        response = self.client.post(url, {
            'nuevo_estado': self.estado_resuelto.id,
            'diagnostico': 'Se reinició el firmware del switch y se restableció el enlace troncal.',
            'tiempo_minutos': '45'
        })
        self.assertEqual(response.status_code, 302)

        # Verificar registro inquebrantable en CambioEstado
        cambio = CambioEstado.objects.filter(ticket=self.ticket).latest('fecha_cambio')
        self.assertEqual(cambio.estado_anterior, self.estado_revision)
        self.assertEqual(cambio.estado_nuevo, self.estado_resuelto)
        self.assertEqual(cambio.modificado_por, self.tecnico)
        self.assertIsNotNone(cambio.fecha_cambio)

        # Verificar registro de la Intervención
        intervencion = Intervencion.objects.filter(ticket=self.ticket).latest('fecha_registro')
        self.assertEqual(intervencion.tecnico, self.tecnico)
        self.assertEqual(intervencion.tiempo_invertido_minutos, 45)

    # --------------------------------------------------------------------------
    # CRITERIO 2: Métricas de Escalamiento (SIG-543)
    # --------------------------------------------------------------------------
    def test_metricas_escalamiento_e_intervencion_sig543(self):
        """Cada escalamiento debe crear registro obligatorio en Escalamiento e Intervención."""
        self.ticket.tecnico_asignado = self.tecnico
        self.ticket.save()

        url_escalar = reverse('tecnico_escalar', kwargs={'ticket_id': self.ticket.id})
        response = self.client.post(url_escalar, {
            'grupo_o_tecnico_destino': 'Nivel 2 - Redes e Infraestructura',
            'motivo': 'Falla física en el puerto uplink del router frontera.',
            'tiempo_minutos': '30'
        })
        self.assertEqual(response.status_code, 302)

        # 1. Registro obligatorio en Escalamiento para cálculo de volumen SIG-543
        escalamiento = Escalamiento.objects.filter(ticket=self.ticket).first()
        self.assertIsNotNone(escalamiento)
        self.assertEqual(escalamiento.tecnico_origen, self.tecnico)
        self.assertEqual(escalamiento.grupo_o_tecnico_destino, 'Nivel 2 - Redes e Infraestructura')
        self.assertIn('Falla física', escalamiento.motivo)

        # 2. Registro obligatorio en Intervención
        intervencion = Intervencion.objects.filter(ticket=self.ticket).first()
        self.assertIsNotNone(intervencion)
        self.assertEqual(intervencion.tiempo_invertido_minutos, 30)
        self.assertIn('Escalamiento', intervencion.descripcion)

    # --------------------------------------------------------------------------
    # CRITERIO 3: Cálculo de Tiempos (fecha_asignacion y fecha_cierre)
    # --------------------------------------------------------------------------
    def test_calculo_tiempos_asignacion_y_cierre(self):
        """Marca automáticamente fecha_asignacion en autoasignación y fecha_cierre al resolver/cerrar."""
        # 1. Estado inicial: sin fechas de asignación ni cierre
        self.assertIsNone(self.ticket.fecha_asignacion)
        self.assertIsNone(self.ticket.fecha_cierre)

        # 2. Autoasignación: debe fijar fecha_asignacion
        url_autoasignar = reverse('tecnico_autoasignar', kwargs={'ticket_id': self.ticket.id})
        resp_asignar = self.client.post(url_autoasignar)
        self.assertEqual(resp_asignar.status_code, 302)

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.tecnico_asignado, self.tecnico)
        self.assertIsNotNone(self.ticket.fecha_asignacion)
        self.assertIsNone(self.ticket.fecha_cierre)

        # 3. Resolución/Cierre: debe fijar fecha_cierre automáticamente
        url_resolver = reverse('tecnico_solucion_caso_detalle', kwargs={'ticket_id': self.ticket.id})
        resp_resolver = self.client.post(url_resolver, {
            'nuevo_estado': self.estado_resuelto.id,
            'diagnostico': 'Problema resuelto satisfactoriamente.',
            'tiempo_minutos': '20'
        })
        self.assertEqual(resp_resolver.status_code, 302)

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.estado, self.estado_resuelto)
        self.assertIsNotNone(self.ticket.fecha_cierre)
        # La fecha de cierre debe ser posterior o igual a la de asignación
        self.assertGreaterEqual(self.ticket.fecha_cierre, self.ticket.fecha_asignacion)
