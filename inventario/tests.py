from django.test import TestCase, Client
from django.urls import reverse

from users.models import CustomUser
from catalogos.models import Categoria, Prioridad, EstadoTicket
from tickets.models import Equipo, Ticket, Intervencion, Auditoria
from inventario.models import Repuesto, MovimientoInventario


class InventarioTransaccionalTestCase(TestCase):
    """
    Pruebas unitarias y de integración para validar los 3 criterios de aceptación
    del registro transaccional de repuestos durante una intervención técnica:
    1. Atomicidad de Base de Datos (descuento seguro con bloqueo y transacción).
    2. Validación de Stock (rechazo y rollback cuando cantidad > stock_actual).
    3. Alertas de Reposición (detección automática cuando stock_actual <= stock_minimo
       e integración al Dashboard gerencial).
    """

    def setUp(self):
        self.client = Client()

        # Usuarios por rol
        self.cliente_user = CustomUser.objects.create_user(
            username='cli_inv',
            email='cli_inv@gita.local',
            cedula='V-71111111',
            password='Password123!',
            rol='CLIENTE'
        )
        self.tecnico_user = CustomUser.objects.create_user(
            username='tec_inv',
            email='tec_inv@gita.local',
            cedula='V-72222222',
            password='Password123!',
            rol='TECNICO'
        )
        self.gerente_user = CustomUser.objects.create_user(
            username='ger_inv',
            email='ger_inv@gita.local',
            cedula='V-73333333',
            password='Password123!',
            rol='GERENTE'
        )

        # Catálogos base
        self.categoria = Categoria.objects.create(nombre='Hardware')
        self.prioridad = Prioridad.objects.create(nombre='Alta', nivel=3)
        self.estado_en_proceso = EstadoTicket.objects.create(nombre='EN_PROCESO', es_final=False)
        self.estado_resuelto = EstadoTicket.objects.create(nombre='RESUELTO', es_final=True)

        # Equipo y Ticket asignado al técnico
        self.equipo = Equipo.objects.create(
            serial='SN-INV-001',
            marca='HP',
            modelo='Z4 G4'
        )
        self.ticket = Ticket.objects.create(
            folio='INC-2026-9001',
            asunto='Falla en disco de almacenamiento',
            descripcion='El disco presenta sectores dañados.',
            usuario=self.cliente_user,
            tecnico_asignado=self.tecnico_user,
            equipo=self.equipo,
            categoria=self.categoria,
            prioridad=self.prioridad,
            estado=self.estado_en_proceso
        )

        # Repuesto con stock_actual = 6, stock_minimo = 5 (Óptimo al inicio)
        self.repuesto = Repuesto.objects.create(
            codigo='SSD-NVME-1TB',
            nombre='Unidad SSD NVMe 1TB',
            stock_actual=6,
            stock_minimo=5
        )

    def test_1_atomicidad_descuento_repuesto_en_intervencion(self):
        """
        Criterio 1: Un movimiento de salida durante una intervención técnica
        descuenta unidades del modelo Repuesto de forma atómica y registra
        el MovimientoInventario vinculado al Ticket y la Intervencion.
        """
        self.client.login(username='tec_inv', password='Password123!')
        url = reverse('tecnico_solucion_caso_detalle', args=[self.ticket.id])

        # Descontamos 1 unidad (stock pasa de 6 a 5)
        response = self.client.post(url, {
            'nuevo_estado': self.estado_resuelto.id,
            'solucion': 'Se reemplazó la unidad SSD defectuosa y se clonó el sistema.',
            'tiempo_minutos': '45',
            'repuesto_id': self.repuesto.id,
            'cantidad_repuesto': '1',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.repuesto.refresh_from_db()
        self.ticket.refresh_from_db()

        # Verificar descuento exacto en base de datos
        self.assertEqual(self.repuesto.stock_actual, 5)
        self.assertEqual(self.ticket.estado, self.estado_resuelto)

        # Verificar creación del movimiento operativo vinculado al ticket
        mov = MovimientoInventario.objects.filter(ticket=self.ticket, repuesto=self.repuesto).first()
        self.assertIsNotNone(mov)
        self.assertEqual(mov.tipo_movimiento, 'SALIDA')
        self.assertEqual(mov.cantidad, 1)
        self.assertEqual(mov.registrado_por, self.tecnico_user)

        # Verificar registro de la intervención técnica
        self.assertTrue(Intervencion.objects.filter(ticket=self.ticket, tecnico=self.tecnico_user).exists())

    def test_2_validacion_stock_insuficiente_rechaza_y_hace_rollback(self):
        """
        Criterio 2: Si el técnico intenta descontar una cantidad mayor al stock restante,
        el controlador rechaza la transacción, devuelve un mensaje de error al técnico y
        hace rollback completo (no descuenta stock, no cambia estado ni crea intervención).
        """
        self.client.login(username='tec_inv', password='Password123!')
        url = reverse('tecnico_solucion_caso_detalle', args=[self.ticket.id])

        # Intentamos descontar 10 unidades cuando solo hay 6 en stock
        response = self.client.post(url, {
            'nuevo_estado': self.estado_resuelto.id,
            'solucion': 'Intento de usar más repuestos de los disponibles.',
            'tiempo_minutos': '30',
            'repuesto_id': self.repuesto.id,
            'cantidad_repuesto': '10',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Stock insuficiente')

        self.repuesto.refresh_from_db()
        self.ticket.refresh_from_db()

        # El stock debe permanecer intacto en 6
        self.assertEqual(self.repuesto.stock_actual, 6)
        # El ticket NO debe haber cambiado a RESUELTO (rollback atómico)
        self.assertEqual(self.ticket.estado, self.estado_en_proceso)
        # No debe haberse creado ni MovimientoInventario ni Intervencion
        self.assertEqual(MovimientoInventario.objects.filter(ticket=self.ticket).count(), 0)
        self.assertEqual(Intervencion.objects.filter(ticket=self.ticket).count(), 0)

    def test_3_alerta_reposicion_automatica_e_integracion_dashboard_gerencial(self):
        """
        Criterio 3: Cuando el stock cae a o por debajo de stock_minimo, el sistema
        detecta el estado crítico (requiere_reposicion=True), notifica la alerta de
        reposición, registra auditoría y expone los datos en el Dashboard gerencial.
        """
        # Al inicio con stock=6 y minimo=5, no requiere reposición
        self.assertFalse(self.repuesto.requiere_reposicion)
        self.assertEqual(self.repuesto.estado_stock, 'OPTIMO')

        self.client.login(username='tec_inv', password='Password123!')
        url = reverse('tecnico_solucion_caso_detalle', args=[self.ticket.id])

        # Usamos 2 unidades -> stock pasa de 6 a 4 (por debajo del mínimo de 5)
        response = self.client.post(url, {
            'nuevo_estado': self.estado_resuelto.id,
            'solucion': 'Instalación de 2 unidades SSD en RAID 1.',
            'tiempo_minutos': '60',
            'repuesto_id': self.repuesto.id,
            'cantidad_repuesto': '2',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.repuesto.refresh_from_db()

        # Verificar propiedades de estado de reposición
        self.assertEqual(self.repuesto.stock_actual, 4)
        self.assertTrue(self.repuesto.requiere_reposicion)
        self.assertEqual(self.repuesto.estado_stock, 'CRITICO')

        # Verificar notificación de alerta al técnico y registro en Auditoría
        self.assertContains(response, 'ALERTA DE REPOSICIÓN')
        self.assertTrue(
            Auditoria.objects.filter(ticket=self.ticket, accion__icontains='ALERTA_STOCK_CRITICO').exists()
        )

        # Verificar integración con el Dashboard Gerencial
        self.client.login(username='ger_inv', password='Password123!')
        dash_response = self.client.get(reverse('gerente_dashboard'))
        self.assertEqual(dash_response.status_code, 200)
        self.assertContains(dash_response, 'Stock Crítico: Unidad SSD NVMe 1TB')
        self.assertContains(dash_response, 'Repuestos usados: 2')
        self.assertContains(dash_response, 'INC-2026-9001')
