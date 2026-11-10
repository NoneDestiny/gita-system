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
