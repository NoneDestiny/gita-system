import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from catalogos.models import Categoria, Prioridad, EstadoTicket, ModalidadAtencion
from tickets.models import Equipo, Ticket

User = get_user_model()

class Command(BaseCommand):
    help = 'Genera data masiva de prueba para el Dashboard (BD-06)'

    def handle(self, *args, **kwargs):
        self.stdout.write("Borrando data anterior (limpieza)...")
        Ticket.objects.all().delete()
        Equipo.objects.all().delete()
        Categoria.objects.all().delete()
        Prioridad.objects.all().delete()
        EstadoTicket.objects.all().delete()
        
        self.stdout.write("Creando Catálogos...")
        # 1. Estados
        est_abierto = EstadoTicket.objects.create(nombre="Abierto")
        est_progreso = EstadoTicket.objects.create(nombre="En Progreso")
        est_resuelto = EstadoTicket.objects.create(nombre="Resuelto")
        est_cerrado = EstadoTicket.objects.create(nombre="Cerrado")
        estados = [est_abierto, est_progreso, est_resuelto, est_cerrado]

        # 2. Prioridades y Categorías
        pri_alta = Prioridad.objects.create(nombre="Alta")
        pri_baja = Prioridad.objects.create(nombre="Baja")
        cat_hard = Categoria.objects.create(nombre="Hardware")
        cat_soft = Categoria.objects.create(nombre="Software")
        cat_redes = Categoria.objects.create(nombre="Redes")

        # 3. Equipos
        equipo1 = Equipo.objects.create(serial="SN-100", marca="Dell", modelo="OptiPlex")
        equipo2 = Equipo.objects.create(serial="SN-200", marca="HP", modelo="ProBook")

        self.stdout.write("Creando Usuarios de Prueba...")
        # Creamos al cliente y a los técnicos de tu equipo
        cliente, _ = User.objects.get_or_create(username="cliente_test", email="cliente@gita.com")
        if not cliente.password:
            cliente.set_password("Admin123$")
            cliente.save()

        tecnico_rainer, _ = User.objects.get_or_create(username="rainer_tech", email="rainer@gita.com")
        tecnico_kevin, _ = User.objects.get_or_create(username="kevin_tech", email="kevin@gita.com")
        tecnicos = [tecnico_rainer, tecnico_kevin, None] # None para simular tickets sin asignar

        self.stdout.write("Generando volumen de Tickets para el Dashboard...")
        ahora = timezone.now()
        
        for i in range(1, 51): # Generará 50 tickets distribuidos en los últimos 60 días
            fecha_creacion_random = ahora - timedelta(days=random.randint(1, 60))
            
            estado_random = random.choice(estados)
            tecnico_random = random.choice(tecnicos)
            
            ticket = Ticket(
                asunto=f"Incidencia de prueba #{i}",
                descripcion="Falla reportada generada automáticamente para pruebas de volumen en la defensa.",
                usuario=cliente,
                equipo=random.choice([equipo1, equipo2]),
                categoria=random.choice([cat_hard, cat_soft, cat_redes]),
                prioridad=random.choice([pri_alta, pri_baja]),
                estado=estado_random,
                tecnico_asignado=tecnico_random if estado_random != est_abierto else None
            )
            # Truco para sobreescribir el auto_now_add de Django y simular fechas pasadas
            ticket.save()
            Ticket.objects.filter(id=ticket.id).update(fecha_creacion=fecha_creacion_random)
            
            if estado_random in [est_resuelto, est_cerrado]:
                Ticket.objects.filter(id=ticket.id).update(
                    fecha_cierre=fecha_creacion_random + timedelta(days=random.randint(1, 5))
                )

        self.stdout.write(self.style.SUCCESS("¡Generación masiva completada! Data lista para probar."))