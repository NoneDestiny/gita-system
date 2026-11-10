from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from users.models import CustomUser
from catalogos.models import Categoria, EstadoTicket, Prioridad
from tickets.models import Ticket, Equipo, Evidencia


class ClienteTicketMVTTestCase(TestCase):
    """
    Pruebas para los Criterios de Aceptación del Rol Cliente:
    1. Validación Multimedia Estricta (formato JPG/PNG/JPEG y máx 5MB).
    2. Generación de Código Único (Folio) y estado inicial automático.
    3. Motor de Búsqueda y Filtros en la vista de seguimiento.
    """

    def setUp(self):
        self.client = Client()

        # Usuario Cliente
        self.cliente = CustomUser.objects.create_user(
            username='cliente_criterio',
            email='cliente@test.com',
            cedula='V-99999999',
            password='Password123*',
            rol='CLIENTE'
        )

        # Segundo Cliente para comprobar aislamiento
        self.otro_cliente = CustomUser.objects.create_user(
            username='otro_cliente',
            email='otro@test.com',
            cedula='V-88888888',
            password='Password123*',
            rol='CLIENTE'
        )

        # Catálogos
        self.categoria_soft = Categoria.objects.create(nombre='Software', descripcion='Apps')
        self.categoria_hard = Categoria.objects.create(nombre='Hardware', descripcion='Piezas')
        self.estado_creado = EstadoTicket.objects.create(nombre='CREADO', es_inicial=True)
        self.estado_proceso = EstadoTicket.objects.create(nombre='EN_PROCESO')
        self.prioridad_media = Prioridad.objects.create(nombre='Media', nivel=2)

        # Equipo
        self.equipo = Equipo.objects.create(serial='SN-TEST-001', marca='Dell', modelo='Latitude')

        # Login del cliente principal
        self.client.login(username='cliente_criterio', password='Password123*')

    # --------------------------------------------------------------------------
    # CRITERIO 1: Validación Multimedia Estricta
    # --------------------------------------------------------------------------
    def test_evidencia_formato_invalido_rechazada(self):
        """Archivos con formato distinto a JPG, JPEG o PNG deben ser rechazados."""
        archivo_invalido = SimpleUploadedFile(
            "documento.pdf",
            b"contenido falso pdf",
            content_type="application/pdf"
        )
        response = self.client.post(reverse('crear_reporte'), {
            'asunto': 'Falla con PDF',
            'descripcion': 'Probando subida indebida',
            'serial': self.equipo.serial,
            'categoria': self.categoria_soft.nombre,
            'evidencias': archivo_invalido
        })
        # Debe fallar y no crear ningún ticket
        self.assertEqual(Ticket.objects.count(), 0)

    def test_evidencia_exceso_tamano_rechazada(self):
        """Archivos mayores a 5 MB deben ser rechazados."""
        tamano_grande = 6 * 1024 * 1024  # 6 MB
        archivo_grande = SimpleUploadedFile(
            "foto_grande.jpg",
            b"0" * tamano_grande,
            content_type="image/jpeg"
        )
        response = self.client.post(reverse('crear_reporte'), {
            'asunto': 'Falla con Imagen Grande',
            'descripcion': 'Probando exceso de tamano',
            'serial': self.equipo.serial,
            'categoria': self.categoria_soft.nombre,
            'evidencias': archivo_grande
        })
        self.assertEqual(Ticket.objects.count(), 0)

    def test_evidencia_valida_aceptada(self):
        """Archivos JPG menores a 5 MB deben ser aceptados y vinculados al ticket."""
        archivo_valido = SimpleUploadedFile(
            "captura.png",
            b"contenido imagen png",
            content_type="image/png"
        )
        response = self.client.post(reverse('crear_reporte'), {
            'asunto': 'Falla de Sistema',
            'descripcion': 'Pantalla azul al iniciar',
            'serial': self.equipo.serial,
            'categoria': self.categoria_soft.nombre,
            'evidencias': archivo_valido
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(Evidencia.objects.count(), 1)

    # --------------------------------------------------------------------------
    # CRITERIO 2: Generación de Código Único (Folio) y Estado Inicial
    # --------------------------------------------------------------------------
    def test_generacion_codigo_unico_y_estado_inicial(self):
        """Al guardar un ticket, se le genera folio único, estado inicial CREADO y fecha."""
        response = self.client.post(reverse('crear_reporte'), {
            'asunto': 'Teclado no responde',
            'descripcion': 'No funcionan las teclas numéricas',
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

    # --------------------------------------------------------------------------
    # CRITERIO 3: Motor de Búsqueda y Filtros en Seguimiento
    # --------------------------------------------------------------------------
    def test_busqueda_y_filtros_tickets_propios(self):
        """La vista /cliente/historico/ soporta búsqueda por texto y filtros por estado y categoría."""
        t1 = Ticket.objects.create(
            asunto='Monitor parpadea',
            descripcion='Se apaga cada 5 minutos',
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
        # Ticket de otro cliente (no debe aparecer)
        Ticket.objects.create(
            asunto='Ticket ajeno',
            descripcion='No debe ser visible para este usuario',
            usuario=self.otro_cliente,
            equipo=self.equipo,
            categoria=self.categoria_soft,
            prioridad=self.prioridad_media,
            estado=self.estado_creado,
        )

        # 1. Sin filtros: debe ver solo sus 2 tickets
        resp = self.client.get(reverse('cliente_historico'))
        self.assertEqual(resp.context['total_tickets'], 2)

        # 2. Búsqueda por texto (query ?q=Monitor)
        resp_q = self.client.get(reverse('cliente_historico'), {'q': 'Monitor'})
        self.assertEqual(resp_q.context['total_tickets'], 1)
        self.assertEqual(resp_q.context['tickets'][0].asunto, 'Monitor parpadea')

        # 3. Filtro por Estado (?estado=EN_PROCESO)
        resp_est = self.client.get(reverse('cliente_historico'), {'estado': 'EN_PROCESO'})
        self.assertEqual(resp_est.context['total_tickets'], 1)
        self.assertEqual(resp_est.context['tickets'][0].asunto, 'Error en Excel')

        # 4. Filtro por Categoría (?categoria=Hardware)
        resp_cat = self.client.get(reverse('cliente_historico'), {'categoria': 'Hardware'})
        self.assertEqual(resp_cat.context['total_tickets'], 1)
        self.assertEqual(resp_cat.context['tickets'][0].asunto, 'Monitor parpadea')
