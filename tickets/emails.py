import logging
import threading
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.db import close_old_connections
from .models import Notificacion

logger = logging.getLogger(__name__)


def _enviar_correo_tarea(ticket, tipo_evento, email_destinatario, usuario, asunto, contexto):
    """
    Función que envía el correo vía SMTP y guarda el registro histórico en Notificacion.
    """
    close_old_connections()

    cuerpo_html = render_to_string('emails/notificacion_ticket.html', contexto)
    cuerpo_texto = strip_tags(cuerpo_html)

    remitente = getattr(settings, 'DEFAULT_FROM_EMAIL', 'GITA System <manuelp67werewolf@gmail.com>')
    exitoso = True
    error_log = None

    try:
        email = EmailMultiAlternatives(
            subject=asunto,
            body=cuerpo_texto,
            from_email=remitente,
            to=[email_destinatario],
        )
        email.attach_alternative(cuerpo_html, "text/html")
        email.send(fail_silently=False)
        logger.info(f"Correo enviado exitosamente a {email_destinatario}")
    except Exception as e:
        exitoso = False
        error_log = str(e)
        logger.error(f"Error al enviar correo a {email_destinatario}: {error_log}")

    # Registro histórico en la Base de Datos (Auditoría)
    try:
        Notificacion.objects.create(
            ticket=ticket,
            destinatario=email_destinatario,
            usuario_destinatario=usuario,
            tipo_evento=tipo_evento,
            asunto=asunto,
            cuerpo_html=cuerpo_html,
            exitoso=exitoso,
            error_log=error_log
        )
    except Exception as db_err:
        logger.error(f"Error al guardar registro de Notificación en BD: {db_err}")
    finally:
        close_old_connections()


import sys


def notificar_ticket_segundo_plano(ticket, tipo_evento, destinatario=None, mensaje_extra=None, async_mode=None):
    """
    Dispara el envío de correo automático en SEGUNDO PLANO (Asíncrono vía Threading).
    No bloquea la respuesta HTTP al usuario.
    """
    if async_mode is None:
        async_mode = 'test' not in sys.argv

    if not ticket:
        return

    usuario_dest = ticket.usuario
    email_dest = destinatario or (usuario_dest.email if usuario_dest else None)

    if not email_dest:
        return

    config_eventos = {
        'CREACION': {
            'asunto': f"[GITA] Ticket Creado Exitosamente: {ticket.folio} - {ticket.asunto}",
            'titulo': "¡Tu reporte de incidencia ha sido recibido!",
            'intro': "Hemos registrado tu solicitud en el sistema y se le ha asignado un folio para su seguimiento.",
            'badge': "creacion",
            'display': "Ticket Creado"
        },
        'ESCALAMIENTO': {
            'asunto': f"[GITA] Ticket Escalado a Nivel Superior: {ticket.folio}",
            'titulo': "Actualización: Tu caso ha sido escalado",
            'intro': "Tu ticket ha sido derivado a un equipo especializado para una pronta resolución.",
            'badge': "escalamiento",
            'display': "Ticket Escalado"
        },
        'RESOLUCION': {
            'asunto': f"[GITA] Incidencia Resuelta/Cerrada: {ticket.folio}",
            'titulo': "¡Tu incidencia ha sido completada!",
            'intro': "El equipo técnico ha finalizado la atención y tu caso ha sido marcado como Resuelto.",
            'badge': "resolucion",
            'display': "Caso Resuelto"
        },
        'ACTUALIZACION': {
            'asunto': f"[GITA] Estado Actualizado en Ticket {ticket.folio}: {ticket.estado.nombre}",
            'titulo': "Cambio de Estado en tu Incidencia",
            'intro': f"El estado de tu ticket ahora es: {ticket.estado.nombre}.",
            'badge': "actualizacion",
            'display': f"Estado: {ticket.estado.nombre}"
        }
    }

    cfg = config_eventos.get(tipo_evento, config_eventos['ACTUALIZACION'])

    contexto = {
        'ticket': ticket,
        'titulo_notificacion': cfg['titulo'],
        'mensaje_introductorio': cfg['intro'],
        'tipo_evento_display': cfg['display'],
        'tipo_badge': cfg['badge'],
        'mensaje_extra': mensaje_extra,
        'enlace_ticket': "http://127.0.0.1:8000/cliente/historico/",
    }

    args = (ticket, tipo_evento, email_dest, usuario_dest, cfg['asunto'], contexto)

    if async_mode:
        hilo = threading.Thread(target=_enviar_correo_tarea, args=args, daemon=True)
        hilo.start()
    else:
        _enviar_correo_tarea(*args)
