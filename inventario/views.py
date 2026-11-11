import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from users.permissions import gerente_required
from .models import Repuesto

logger = logging.getLogger(__name__)


@gerente_required
def gerente_inventario(request):
    """
    Controlador CRUD de Inventario de Repuestos exclusivo para el rol GERENTE.
    """
    if request.method == 'POST':
        accion = request.POST.get('accion', '').strip()
        codigo = request.POST.get('codigo', '').strip()
        nombre_repuesto = (
            request.POST.get('descripcion') or request.POST.get('nombre') or ''
        ).strip()

        if not codigo or not nombre_repuesto:
            messages.error(request, "El código y la descripción del repuesto son obligatorios.")
            return redirect('gerente_inventario')

        try:
            stock = int(request.POST.get('stock', 0))
            stock_min = int(request.POST.get('stock_min', 0))
            if stock < 0 or stock_min < 0:
                raise ValueError("Stock negativo no permitido.")
        except ValueError:
            messages.error(request, "Los valores de stock deben ser números enteros positivos o cero.")
            return redirect('gerente_inventario')

        if accion == 'crear':
            try:
                if Repuesto.objects.filter(codigo__iexact=codigo).exists():
                    messages.error(request, f"Ya existe un repuesto registrado con el código {codigo}.")
                else:
                    Repuesto.objects.create(
                        codigo=codigo,
                        nombre=nombre_repuesto,
                        stock_actual=stock,
                        stock_minimo=stock_min,
                    )
                    messages.success(request, "Repuesto agregado exitosamente.")
            except Exception as exc:
                logger.error("Error al crear repuesto %s: %s", codigo, exc)
                messages.error(request, "No se pudo registrar el repuesto. Verifique los datos ingresados.")

        elif accion == 'editar':
            try:
                repuesto = Repuesto.objects.get(codigo=codigo)
                repuesto.nombre = nombre_repuesto
                repuesto.stock_actual = stock
                repuesto.stock_minimo = stock_min
                repuesto.save()
                messages.success(request, "Repuesto actualizado correctamente.")
            except Repuesto.DoesNotExist:
                messages.error(request, "El repuesto que intentas editar no existe.")
            except Exception as exc:
                logger.error("Error al editar repuesto %s: %s", codigo, exc)
                messages.error(request, "No se pudo actualizar el repuesto. Intente nuevamente.")

        return redirect('gerente_inventario')

    repuestos_lista = Repuesto.objects.all().order_by('codigo')
    return render(request, 'gerencia/inventario.html', {
        'modulo': 'inventario',
        'usuario': request.user,
        'repuestos': repuestos_lista,
    })
