from django.shortcuts import render, redirect
from django.contrib import messages
from .models import ModeloRepuesto # <-- Cambia esto por tu modelo real

def gerente_inventario(request):
    # 1. Si el usuario envía un formulario (POST)
    if request.method == 'POST':
        accion = request.POST.get('accion')
        codigo = request.POST.get('codigo')
        
        # Necesitarás capturar el resto de tus campos aquí, ejemplo:
        # nombre = request.POST.get('nombre')
        # cantidad = request.POST.get('cantidad')

        if accion == 'crear':
            # Crea un registro nuevo en la Base de Datos
            ModeloRepuesto.objects.create(
                codigo=codigo,
                # nombre=nombre,
                # cantidad=cantidad
            )
            messages.success(request, "Repuesto creado con éxito.")

        elif accion == 'editar':
            # Busca el repuesto y actualízalo
            try:
                repuesto = ModeloRepuesto.objects.get(codigo=codigo)
                # repuesto.nombre = nombre
                # repuesto.cantidad = cantidad
                repuesto.save()
                messages.success(request, "Repuesto actualizado con éxito.")
            except ModeloRepuesto.DoesNotExist:
                messages.error(request, "El repuesto no existe.")

        # Tras guardar, recarga la página limpiamente para evitar reenvíos de formulario
        return redirect('gerente_inventario')

    # 2. Si el usuario solo entra a ver la página (GET)
    repuestos_lista = ModeloRepuesto.objects.all()
    contexto = {
        'repuestos': repuestos_lista
    }
    return render(request, 'gerencia/inventario.html', contexto)