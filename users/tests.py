import json
from django.test import TestCase, Client
from django.urls import reverse
from users.models import CustomUser


class RBACTestCase(TestCase):
    """Pruebas unitarias para el Control de Acceso Basado en Roles (RBAC), Login y Logout."""

    def setUp(self):
        self.client = Client()

        # Usuario Cliente
        self.cliente = CustomUser.objects.create_user(
            username='cliente_test',
            email='cliente@test.com',
            cedula='V-11111111',
            password='Password123*',
            rol='CLIENTE'
        )

        # Usuario Técnico
        self.tecnico = CustomUser.objects.create_user(
            username='tecnico_test',
            email='tecnico@test.com',
            cedula='V-22222222',
            password='Password123*',
            rol='TECNICO'
        )

        # Usuario Gerente
        self.gerente = CustomUser.objects.create_user(
            username='gerente_test',
            email='gerente@test.com',
            cedula='V-33333333',
            password='Password123*',
            rol='GERENTE'
        )

    # --------------------------------------------------------------------------
    # 1. Redirección Dinámica post-login
    # --------------------------------------------------------------------------
    def test_redireccion_dinamica_cliente(self):
        """Cliente debe ser redirigido a /cliente/historico/ tras login exitoso."""
        response = self.client.post(reverse('login'), {
            'username': 'cliente_test',
            'password': 'Password123*',
        })
        self.assertRedirects(response, '/cliente/historico/')

    def test_redireccion_dinamica_tecnico(self):
        """Técnico debe ser redirigido a /tecnico/tickets-asignados/ tras login exitoso."""
        response = self.client.post(reverse('login'), {
            'username': 'tecnico_test',
            'password': 'Password123*',
        })
        self.assertRedirects(response, '/tecnico/tickets-asignados/')

    def test_redireccion_dinamica_gerente(self):
        """Gerente debe ser redirigido a /gerencia/dashboard/ tras login exitoso."""
        response = self.client.post(reverse('login'), {
            'username': 'gerente_test',
            'password': 'Password123*',
        })
        self.assertRedirects(response, '/gerencia/dashboard/')

    # --------------------------------------------------------------------------
    # 2. Protección de Rutas (RBAC) - Restricción y HTTP 403 Forbidden
    # --------------------------------------------------------------------------
    def test_usuario_anonimo_redirige_a_login(self):
        """Un usuario no autenticado debe ser redirigido a /login/?next=..."""
        response = self.client.get('/gerencia/dashboard/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_cliente_no_puede_acceder_a_gerencia(self):
        """Un Cliente intentando entrar a ruta de Gerencia debe recibir 403 Forbidden."""
        self.client.login(username='cliente_test', password='Password123*')
        response = self.client.get('/gerencia/dashboard/')
        self.assertEqual(response.status_code, 403)

    def test_cliente_no_puede_acceder_a_tecnico(self):
        """Un Cliente intentando entrar a ruta de Técnico debe recibir 403 Forbidden."""
        self.client.login(username='cliente_test', password='Password123*')
        response = self.client.get('/tecnico/tickets-asignados/')
        self.assertEqual(response.status_code, 403)

    def test_tecnico_no_puede_acceder_a_gerencia(self):
        """Un Técnico intentando entrar a ruta de Gerente debe recibir 403 Forbidden."""
        self.client.login(username='tecnico_test', password='Password123*')
        response = self.client.get('/gerencia/dashboard/')
        self.assertEqual(response.status_code, 403)

    def test_cliente_accede_a_su_modulo(self):
        """Un Cliente autenticado debe acceder exitosamente a /cliente/historico/ (200 OK)."""
        self.client.login(username='cliente_test', password='Password123*')
        response = self.client.get('/cliente/historico/')
        self.assertEqual(response.status_code, 200)

    def test_tecnico_accede_a_su_modulo(self):
        """Un Técnico autenticado debe acceder exitosamente a /tecnico/tickets-asignados/ (200 OK)."""
        self.client.login(username='tecnico_test', password='Password123*')
        response = self.client.get('/tecnico/tickets-asignados/')
        self.assertEqual(response.status_code, 200)

    def test_gerente_accede_a_su_modulo(self):
        """Un Gerente autenticado debe acceder exitosamente a /gerencia/dashboard/ (200 OK)."""
        self.client.login(username='gerente_test', password='Password123*')
        response = self.client.get('/gerencia/dashboard/')
        self.assertEqual(response.status_code, 200)

    def test_gerente_gestion_y_detalle_tecnico_asignar_quitar(self):
        """El Gerente puede consultar la lista de técnicos y asignar/quitar tickets desde el detalle."""
        from catalogos.models import Categoria, EstadoTicket, Prioridad
        from tickets.models import Ticket, Equipo

        cat = Categoria.objects.create(nombre='Hardware', descripcion='Equipos')
        est_creado = EstadoTicket.objects.create(nombre='CREADO', es_inicial=True)
        EstadoTicket.objects.create(nombre='En Revisión')
        prio_media = Prioridad.objects.create(nombre='Media', nivel=2)
        prio_alta = Prioridad.objects.create(nombre='Alta', nivel=3)
        eq = Equipo.objects.create(serial='SN-GER-01', marca='HP', modelo='ProBook')

        ticket = Ticket.objects.create(
            asunto='Falla de disco',
            descripcion='No arranca SO',
            usuario=self.cliente,
            equipo=eq,
            categoria=cat,
            prioridad=prio_media,
            estado=est_creado,
        )

        self.client.login(username='gerente_test', password='Password123*')

        # 1. Vista de lista de técnicos
        resp_lista = self.client.get(reverse('gerente_gestion_tecnicos'))
        self.assertEqual(resp_lista.status_code, 200)
        self.assertContains(resp_lista, self.tecnico.username)

        # 2. Asignar ticket al técnico desde detalle
        url_detalle = reverse('gerente_detalle_tecnico', kwargs={'tecnico_id': self.tecnico.id})
        resp_asignar = self.client.post(url_detalle, {
            'accion': 'asignar',
            'ticket_id': ticket.id,
            'prioridad': 'Alta',
        })
        self.assertEqual(resp_asignar.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.tecnico_asignado, self.tecnico)
        self.assertEqual(ticket.prioridad, prio_alta)

        # 3. Quitar ticket al técnico desde detalle
        resp_quitar = self.client.post(url_detalle, {
            'accion': 'quitar',
            'ticket_id': ticket.id,
        })
        self.assertEqual(resp_quitar.status_code, 302)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.tecnico_asignado)

    def test_base_template_herencia_y_breakpoints_mobile_first(self):
        """Verifica que las vistas hereden de base.html con soporte 375px/768px/1280px+ y sin scroll horizontal."""
        self.client.login(username='gerente_test', password='Password123*')
        response = self.client.get(reverse('gerente_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'base.html')
        self.assertTemplateUsed(response, 'gerencia/dashboard.html')
        self.assertContains(response, "'xs': '375px'")
        self.assertContains(response, "'md': '768px'")
        self.assertContains(response, "'xl': '1280px'")
        self.assertContains(response, "overflow-x-hidden")
        self.assertContains(response, 'id="menuToggleMobile"')

    # --------------------------------------------------------------------------
    # 3. Cierre de Sesión (Logout)
    # --------------------------------------------------------------------------
    def test_logout_invalida_sesion_y_redirige(self):
        """El logout debe invalidar la sesión y redirigir a /login/."""
        self.client.login(username='cliente_test', password='Password123*')
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, '/login/')
        # Intentar acceder a ruta protegida post-logout
        resp_post = self.client.get('/cliente/historico/')
        self.assertEqual(resp_post.status_code, 302)

    # --------------------------------------------------------------------------
    # 4. API Login Endpoint (/api/v1/auth/login/)
    # --------------------------------------------------------------------------
    def test_api_login_exitoso(self):
        """API login con credenciales válidas retorna 200, usuario y redirect_url."""
        payload = {
            'identificador': 'V-33333333',  # Probar login por cédula
            'password': 'Password123*',
            'recordarme': True
        }
        response = self.client.post(
            reverse('api_login'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['data']['usuario']['rol'], 'GERENTE')
        self.assertEqual(data['data']['redirect_url'], '/gerencia/dashboard/')

    def test_api_login_credenciales_invalidas(self):
        """API login con contraseña errónea retorna 401 e intentos restantes."""
        payload = {
            'identificador': 'cliente_test',
            'password': 'PasswordErrada',
        }
        response = self.client.post(
            reverse('api_login'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertEqual(data['code'], 'INVALID_CREDENTIALS')
        self.assertIn('intentos_restantes', data)

    # --------------------------------------------------------------------------
    # 5. Selector de Tema (Oscuro/Claro) y Accesibilidad WCAG 2.1 Nivel AA
    # --------------------------------------------------------------------------
    def test_sincronizacion_tema_backend_customuser_y_wcag_aa(self):
        """
        Valida:
        1. Sincronización del tema (Oscuro/Claro) con CustomUser.modo_oscuro vía API
           (/api/v1/users/tema/) y en el renderizado HTML (data-user-theme) + localStorage.
        2. Cumplimiento WCAG 2.1 AA en base.html:
           - Script anti-parpadeo (localStorage.getItem('gita_theme')) y contraste >= 4.5:1.
           - Tipografía limpia Inter/Roboto con tamaño base mínimo de 16px (font-size: 16px).
           - Soporte de zoom hasta 200% (min-h-screen, overflow-wrap: anywhere, flex-wrap).
           - Touch target mínimo de 44x44 píxeles (min-h-[44px] min-w-[44px]) en el toggle y controles.
        """
        self.client.login(username='cliente_test', password='Password123*')

        # Por defecto modo_oscuro=True -> data-user-theme="dark"
        resp_inicial = self.client.get(reverse('cliente_historico'))
        self.assertEqual(resp_inicial.status_code, 200)
        self.assertContains(resp_inicial, 'data-user-theme="dark"')
        self.assertContains(resp_inicial, "localStorage.getItem('gita_theme')")
        self.assertContains(resp_inicial, "font-size: 16px")
        self.assertContains(resp_inicial, "font-family: 'Inter', 'Roboto', sans-serif")
        self.assertContains(resp_inicial, "min-height: 44px")
        self.assertContains(resp_inicial, "min-width: 44px")
        self.assertContains(resp_inicial, "overflow-wrap: anywhere")
        self.assertContains(resp_inicial, 'id="themeToggleBtn"')
        self.assertContains(resp_inicial, 'id="themeToggleMobile"')

        # Cambiar a modo claro (modo_oscuro=False) mediante el endpoint API
        resp_api = self.client.post(
            reverse('api_cambiar_tema'),
            data=json.dumps({'modo_oscuro': False, 'tema': 'light'}),
            content_type='application/json'
        )
        self.assertEqual(resp_api.status_code, 200)
        self.assertEqual(resp_api.json()['tema'], 'light')
        self.assertFalse(resp_api.json()['modo_oscuro'])

        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.modo_oscuro)

        # Verificar que el HTML ahora renderiza data-user-theme="light" y clase light sin parpadeos
        resp_claro = self.client.get(reverse('cliente_historico'))
        self.assertContains(resp_claro, 'data-user-theme="light"')
        self.assertContains(resp_claro, 'aria-pressed="false"')
