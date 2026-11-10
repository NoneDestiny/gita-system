from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import authenticate


class CustomAuthenticationForm(AuthenticationForm):
    """
    Formulario de autenticación general para usuarios del sistema GITA
    (Clientes, Técnicos y Gerentes).
    Permite ingresar con username, correo o cédula y muestra los mensajes
    de advertencia sobre intentos restantes o bloqueo temporal.
    """

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)
        self.fields['username'].label = "Usuario, Correo o Cédula"
        self.fields['username'].widget.attrs.update({
            'placeholder': 'Ej. usuario01, correo@ejemplo.com o 12345678',
            'autofocus': True,
        })

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username is not None and password:
            self.user_cache = authenticate(self.request, username=username, password=password)
            if self.user_cache is None:
                error_msg = getattr(self.request, '_auth_error', None)
                if error_msg:
                    raise forms.ValidationError(error_msg)
                raise self.get_invalid_login_error()
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class CustomAdminAuthenticationForm(AdminAuthenticationForm):
    """
    Formulario personalizado exclusivo para el panel de administración (/admin/).
    Exige permisos de staff (is_staff=True).
    """

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)
        self.fields['username'].label = "Usuario, Correo o Cédula"
        self.fields['username'].widget.attrs.update({
            'placeholder': 'Ej. admin, admin@gita.com o 12345678',
            'autofocus': True,
        })

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username is not None and password:
            self.user_cache = authenticate(self.request, username=username, password=password)
            if self.user_cache is None:
                error_msg = getattr(self.request, '_auth_error', None)
                if error_msg:
                    raise forms.ValidationError(error_msg)
                raise self.get_invalid_login_error()
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data
