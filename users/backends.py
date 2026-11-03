from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from .models import HistorialAcceso


def obtener_ip_cliente(request):
    """Extrae la IP real del cliente considerando proxies."""
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class MultiFieldAuthBackend(ModelBackend):
    """
    Backend de autenticación que permite iniciar sesión usando:
    - Nombre de usuario (username)
    - Correo electrónico (email)
    - Cédula de identidad (cedula)
    
    Además, gestiona el bloqueo por intentos fallidos y el historial de accesos.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)

        if not username or not password:
            return None

        ip = obtener_ip_cliente(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '') if request else ''

        # Buscar usuario por username, email o cédula
        try:
            user = UserModel.objects.filter(
                Q(username__iexact=username) |
                Q(email__iexact=username) |
                Q(cedula__iexact=username)
            ).first()
        except Exception:
            return None

        # Caso 1: Usuario no encontrado
        if user is None:
            HistorialAcceso.objects.create(
                usuario=None,
                identificador_ingresado=username,
                ip_address=ip,
                user_agent=user_agent,
                exitoso=False,
                motivo_fallo="Usuario no encontrado"
            )
            if request:
                request._auth_error = "El usuario, correo o cédula ingresado no está registrado en el sistema."
            return None

        # Caso 2: Usuario está bloqueado por demasiados intentos
        if user.esta_bloqueado():
            minutos = user.minutos_restantes_bloqueo()
            motivo = f"Cuenta bloqueada temporalmente ({minutos} min restantes)."
            HistorialAcceso.objects.create(
                usuario=user,
                identificador_ingresado=username,
                ip_address=ip,
                user_agent=user_agent,
                exitoso=False,
                motivo_fallo=motivo
            )
            if request:
                request._auth_error = f"Tu cuenta está bloqueada temporalmente. Intenta de nuevo en {minutos} minuto(s)."
            return None

        # Caso 3: Validar contraseña
        if user.check_password(password) and self.user_can_authenticate(user):
            # Login exitoso: restablecer intentos fallidos
            user.resetear_intentos()
            HistorialAcceso.objects.create(
                usuario=user,
                identificador_ingresado=username,
                ip_address=ip,
                user_agent=user_agent,
                exitoso=True,
                motivo_fallo=None
            )
            return user
        else:
            # Login fallido: registrar intento fallido
            bloqueado_ahora = user.registrar_intento_fallido(max_intentos=5, minutos_bloqueo=15)
            if bloqueado_ahora:
                motivo = "Límite de 5 intentos fallidos alcanzado. Cuenta bloqueada por 15 minutos."
                if request:
                    request._auth_error = "Has excedido el número de intentos permitidos (5). Tu cuenta ha sido bloqueada temporalmente por 15 minutos."
            else:
                restantes = 5 - user.intentos_fallidos
                motivo = f"Contraseña incorrecta. Le quedan {restantes} intento(s)."
                if request:
                    request._auth_error = f"Contraseña incorrecta. Te quedan {restantes} intento(s) antes del bloqueo."

            HistorialAcceso.objects.create(
                usuario=user,
                identificador_ingresado=username,
                ip_address=ip,
                user_agent=user_agent,
                exitoso=False,
                motivo_fallo=motivo
            )
            return None
