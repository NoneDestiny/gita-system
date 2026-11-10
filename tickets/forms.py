import os
from django import forms
from django.core.exceptions import ValidationError
from .models import Ticket, Equipo
from catalogos.models import Categoria


def validar_archivo_evidencia(file):
    """
    Validación estricta de archivo de evidencia:
    - Extensiones permitidas: .jpg, .jpeg, .png
    - Tipos MIME permitidos: image/jpeg, image/png
    - Límite de tamaño: 5 MB (5 * 1024 * 1024 bytes)
    """
    if not file:
        return
    
    # 1. Extensión
    ext = os.path.splitext(file.name)[1].lower()
    formatos_permitidos = ['.jpg', '.jpeg', '.png']
    if ext not in formatos_permitidos:
        raise ValidationError(
            f"Formato '{ext}' no permitido. Solo se aceptan archivos JPG, JPEG y PNG."
        )

    # 2. Tamaño
    limite_mb = 5
    if file.size > limite_mb * 1024 * 1024:
        raise ValidationError(
            f"El archivo excede el tamaño máximo permitido de {limite_mb} MB."
        )

    # 3. Tipo de contenido MIME si está disponible
    content_type = getattr(file, 'content_type', '')
    if content_type and content_type not in ['image/jpeg', 'image/png']:
        raise ValidationError("El tipo de contenido del archivo no es una imagen válida.")


class TicketCreateForm(forms.ModelForm):
    """
    Formulario para el registro de incidencias por parte del Cliente.
    """
    evidencia = forms.FileField(
        required=False,
        validators=[validar_archivo_evidencia],
        widget=forms.ClearableFileInput(attrs={
            'accept': '.jpg,.jpeg,.png',
            'class': 'block w-full text-sm text-gray-300 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-[#D47C35] file:text-gray-900 hover:file:bg-[#b86729] cursor-pointer'
        })
    )

    class Meta:
        model = Ticket
        fields = ['asunto', 'categoria', 'equipo', 'descripcion']
        widgets = {
            'asunto': forms.TextInput(attrs={
                'class': 'w-full bg-[#828282] text-gray-900 placeholder-gray-500 rounded p-2.5 focus:ring-2 focus:ring-orange-500',
                'placeholder': 'Ej. Falla al encender equipo...',
                'maxlength': '150',
                'required': True,
            }),
            'categoria': forms.Select(attrs={
                'class': 'w-full bg-[#828282] text-gray-900 rounded p-2.5 focus:ring-2 focus:ring-orange-500',
                'required': True,
            }),
            'equipo': forms.Select(attrs={
                'class': 'w-full bg-[#828282] text-gray-900 rounded p-2.5 focus:ring-2 focus:ring-orange-500',
                'required': True,
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'w-full bg-[#828282] text-gray-900 placeholder-gray-500 rounded p-2.5 focus:ring-2 focus:ring-orange-500',
                'rows': 4,
                'placeholder': 'Describa detalladamente el problema presentado...',
                'required': True,
            }),
        }

    def clean_evidencia(self):
        evidencia = self.cleaned_data.get('evidencia')
        if evidencia:
            validar_archivo_evidencia(evidencia)
        return evidencia
