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

    # --------------------------------------------------------------------------
    # 6. Navegación 100% por Teclado, Focus-Ring y Prevención de Trampas (ISO 9241-11)
    # --------------------------------------------------------------------------
    def test_navegacion_teclado_focus_ring_y_sin_trampas_iso_9241_11(self):
        """
        Valida los Criterios de Aceptación de la norma ISO 9241-11:
        1. Navegación 100% por teclado (Skip-link #skipToContent, soporte de ArrowDown/ArrowUp/Enter/Escape y atajos Alt+M, Alt+I, Ctrl+Enter).
        2. Visibilidad del Foco (focus-ring explícito en todos los botones, inputs, textareas, selects y enlaces).
        3. Prevención de Trampas de Foco (ventana emergente #modalAsistenteIA con salida por Escape y retorno de foco al elemento disparador).
        """
        self.client.login(username='cliente_test', password='Password123*')
        resp = self.client.get(reverse('crear_reporte'))
        self.assertEqual(resp.status_code, 200)

        # 1. Enlace de salto al contenido principal y atajos de teclado
        self.assertContains(resp, 'id="skipToContent"')
        self.assertContains(resp, 'id="mainContent"')
        self.assertContains(resp, "e.key === 'ArrowDown'")
        self.assertContains(resp, "e.key === 'ArrowUp'")
        self.assertContains(resp, "Alt+I")
        self.assertContains(resp, "Ctrl+Enter")

        # 2. Visibilidad del indicador de foco activo (focus-ring) en todos los controles
        self.assertContains(resp, "button:focus-visible")
        self.assertContains(resp, "input:focus-visible")
        self.assertContains(resp, "textarea:focus-visible")
        self.assertContains(resp, "a:focus-visible")
        self.assertContains(resp, "outline: 3px solid #D97706 !important")

        # 3. Prevención de trampas de foco en la ventana emergente del Asistente de IA
        self.assertContains(resp, 'id="modalAsistenteIA"')
        self.assertContains(resp, 'id="btnCerrarModalIAX"')
        self.assertContains(resp, 'id="btnIgnorarModalIA"')
        self.assertContains(resp, 'id="btnConfirmarModalIA"')
        self.assertContains(resp, 'window.cerrarModalIA = cerrarModalIA')
        self.assertContains(resp, "e.key === 'Escape'")

    # --------------------------------------------------------------------------
    # 7. Dashboard Administrativo Gerencial (SIG-543): ORM Real, JSON y Filtros
    # --------------------------------------------------------------------------
    def test_dashboard_gerencial_sig_543_orm_json_y_filtros_responsivos(self):
        """
        Valida los 3 Criterios de Aceptación del Dashboard Gerencial (SIG-543):
        1. Métricas Obligatorias: Cumplimiento de SLA, Volumen de Escalamientos por Modalidad,
           Distribución de Carga de Trabajo por Técnico y Tiempos Medios de Resolución.
        2. Consumo de Datos Reales desde el ORM de Django y respuesta JSON dinámica
           (/api/v1/gerencia/dashboard-metricas/).
        3. Adaptabilidad Responsiva: Panel de filtros agrupado en cabecera desplegable
           (#btnToggleFiltrosDashboard y #panelFiltrosColapsable con hidden xl:block) en tableta (768px).
        """
        from django.utils import timezone
        from datetime import timedelta
        from catalogos.models import Categoria, Prioridad, EstadoTicket, ModalidadAtencion
        from tickets.models import Equipo, Ticket, Escalamiento

        cat = Categoria.objects.create(nombre='Redes')
        prio = Prioridad.objects.create(nombre='Alta', nivel=3)
        est_resuelto = EstadoTicket.objects.create(nombre='RESUELTO', es_final=True)
        mod_remoto = ModalidadAtencion.objects.create(nombre='Remoto')
        eq = Equipo.objects.create(serial='SN-SIG-543', marca='Cisco', modelo='Catalyst')

        ahora = timezone.now()
        t_sig = Ticket.objects.create(
            folio='INC-SIG-001',
            asunto='Caída de enlace WAN',
            descripcion='Enlace principal sin respuesta',
            usuario=self.cliente,
            tecnico_asignado=self.tecnico,
            equipo=eq,
            categoria=cat,
            prioridad=prio,
            estado=est_resuelto,
            modalidad=mod_remoto,
            fecha_asignacion=ahora - timedelta(hours=4),
            fecha_cierre=ahora,
        )
        Escalamiento.objects.create(
            ticket=t_sig,
            tecnico_origen=self.tecnico,
            grupo_o_tecnico_destino='Nivel 3 - Telecomunicaciones',
            motivo='Requiere reconfiguración BGP'
        )

        self.client.login(username='gerente_test', password='Password123*')

        # A) Verificar vista HTML y adaptabilidad responsiva del panel de filtros
        resp_html = self.client.get(reverse('gerente_dashboard'))
        self.assertEqual(resp_html.status_code, 200)
        self.assertContains(resp_html, 'id="btnToggleFiltrosDashboard"')
        self.assertContains(resp_html, 'id="panelFiltrosColapsable"')
        self.assertContains(resp_html, 'hidden xl:block')
        self.assertContains(resp_html, 'id="chartCumplimientoSLA"')
        self.assertContains(resp_html, 'id="chartEscalamientosModalidad"')
        self.assertContains(resp_html, 'id="chartCargaTecnicos"')
        self.assertContains(resp_html, 'id="chartTiemposResolucion"')

        # B) Verificar endpoint JSON dinámico con datos reales del ORM
        resp_json = self.client.get(reverse('api_gerente_dashboard_metricas'))
        self.assertEqual(resp_json.status_code, 200)
        payload = resp_json.json()
        self.assertEqual(payload['status'], 'success')
        self.assertEqual(payload['sig_module'], 'SIG-543')

        data = payload['data']
        self.assertEqual(data['kpis']['total_tickets'], 1)
        self.assertEqual(data['kpis']['cumplimiento_sla_pct'], 100)
        self.assertEqual(data['kpis']['tiempo_medio_resolucion_hrs'], 4.0)
        self.assertEqual(data['kpis']['total_escalamientos'], 1)

        # Verificar escalamiento en modalidad Remoto
        mod_remoto_item = next(
            (m for m in data['volumen_escalamientos_modalidad'] if m['modalidad'] == 'Remoto'),
            None
        )
        self.assertIsNotNone(mod_remoto_item)
        self.assertEqual(mod_remoto_item['cantidad'], 1)
        self.assertEqual(mod_remoto_item['porcentaje'], 100)

        # Verificar distribución de carga por técnico
        self.assertEqual(len(data['distribucion_carga_tecnicos']), 1)
        self.assertEqual(data['distribucion_carga_tecnicos'][0]['resueltos'], 1)
        self.assertEqual(data['distribucion_carga_tecnicos'][0]['tiempo_promedio_hrs'], 4.0)
