# Toma de inventarios / Physical inventory count

<!-- lang:es -->
## ¿Qué es?

La **Toma de inventarios** registra el resultado de un **conteo físico** de bodega. Compara
lo que el sistema cree que hay (**Cantidad en sistema**) con lo que la persona realmente
contó (**Cantidad**) y deja registrada la **diferencia**.

## Cómo registrarla

1. Abra un documento **Toma de inventarios** nuevo (requiere un **conteo físico** previo).
2. Indique la **empresa**, la **bodega** y la **fecha** del conteo.
3. Elija el **tipo de operación**: caducidad de producto, pérdida, daño, **ajuste de
   existencias** o corrección de fechas de vencimiento.
4. Elija el **método de contabilización**: obtener la cantidad **al momento de
   contabilizar**, o **fijar la cantidad en el documento** (en este caso puede digitar la
   diferencia manualmente).
5. Cargue las líneas de bienes en la pestaña **Bienes**: con **Recolección** (doble clic
   sobre el bien o la carpeta para ver su contenido, doble clic en cada bien para añadirlo
   a la tabla inferior, y **Aceptar**) o **Llenar** (todos los bienes para la venta; el
   botón **Cant.** llena la columna de cantidad en sistema). El sistema muestra la **Cantidad en sistema**; usted
   ingresa la **Cantidad** contada y la **Diferencia** se calcula sola.
6. Decida si genera asientos contables con el interruptor **Generar asientos contables**:
   - **No** → registra el conteo solo a efectos operativos, **sin** afectar la contabilidad.
     Útil para cerrar el día en bodega antes de conciliar el costo.
   - **Sí** → además llene la pestaña **Contabilidad** (use **obtener cuentas y costos**
     para traer las cuentas donde están las existencias) y la pestaña **Cuentas**
     (la **contrapartida** del ajuste, cualquier cuenta del plan).
7. **Contabilice** el documento para que la diferencia quede aplicada al inventario.

## Cómo leer la diferencia

- **Físico mayor que sistema** → diferencia positiva (en verde): el sobrante se registra
  como **entrada** en el Kardex.
- **Físico menor que sistema** → diferencia negativa (en rojo): el faltante se registra
  como **salida** en el Kardex.
- **Iguales** → diferencia vacía: la toma no genera registro en el Kardex, pero igual
  conviene registrarla como constancia del conteo.

## Recomendación

Si aún no tiene claro el costo del ajuste, registre la toma con **Generar asientos
contables = No**, cierre la operación de bodega, y más tarde vuelva a hacer la toma con
asientos cuando el costo esté resuelto.

> Nota: el asistente le explica el procedimiento; todavía no realiza el conteo ni contabiliza
> por usted.
<!-- lang:en -->
## What it is

The **physical inventory count** records the result of a **stock count** in a warehouse. It
compares what the system thinks is on hand (**Cantidad en sistema** / system quantity) with
what the counter actually counted (**Cantidad** / counted quantity) and records the
**difference**.

## How to record it

1. Open a new **Toma de inventarios** (inventory count) document.
2. Enter the **company**, the **warehouse** and the count **date**.
3. Load the goods lines. The system shows the **system quantity**; you enter the **counted
   quantity**. The **difference** is computed automatically.
4. Decide whether to generate accounting entries with the **Generar asientos contables**
   (generate accounting entries) switch:
   - **No** → records the count for operational purposes only, **without** touching the
     accounting. Useful to close the warehouse day before the cost is reconciled.
   - **Yes** → besides the quantity, it records the adjustment in the accounting.
5. **Post it** (*Contabilizar*) so the difference is applied to inventory. Operation types
   include expiry, loss, damage, stock adjustment and expiry-date correction; the posting
   method either reads quantities at posting time or fixes them in the document. Lines load
   via filtered collection or fill-all (with a button to populate system quantities); with
   accounting entries on, the Contabilidad tab pulls accounts/costs and the Cuentas tab
   holds the offset account. Surplus counts post as Kardex **inflows** (green difference),
   shortages as **outflows** (red), equal counts leave no Kardex record but are still worth
   keeping as evidence.

## Tip

If you are not yet sure of the adjustment cost, record the count with **Generar asientos
contables = No**, close the warehouse operation, and later redo the count with accounting
entries once the cost is resolved.

> Note: the assistant explains the procedure; it does not perform the count or post it for
> you yet.
