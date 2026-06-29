# Finanzas personales

App de escritorio para manejar tu presupuesto mensual: ingresos, gastos
fijos recurrentes, gastos variables categorizados, inversiones
(obligatorias y discrecionales), retiros, ahorro acumulado histórico, y
gráficas de tendencia. Corre 100% local — tus datos viven en un archivo
SQLite en tu máquina, sin conexión a internet ni servidores.

Protegida con login: contraseña requerida al abrir, cierre de sesión
automático tras 30 minutos de inactividad, y recuperación por código de
un solo uso si la olvidas.

## Cómo instalar y correr

Requiere [uv](https://docs.astral.sh/uv/) instalado.

```bash
cd finanzas_app
uv sync
uv run flet run src/finanzas_app/main.py
```

Para correr las pruebas:

```bash
uv run pytest -v
```

Si prefieres no usar `uv run` cada vez, activa el entorno virtual que
`uv sync` crea en `.venv/`:

```bash
source .venv/bin/activate   # En Windows: .venv\Scripts\activate
flet run src/finanzas_app/main.py
pytest -v
```

**La primera vez que abras la app** te va a pedir tu nombre y crear una
contraseña, y te mostrará un código de recuperación — guárdalo fuera de
la app (un gestor de contraseñas o una nota física), porque es la única
forma de recuperar el acceso si olvidas la contraseña, y solo se
muestra una vez.

## Estructura del proyecto

```
src/finanzas_app/
├── main.py                    # punto de entrada: login + Dashboard/Ahorro/Tendencias/Configuración
├── models/
│   └── schema.py               # tablas SQLite y conexión
├── data/
│   ├── db.py                   # CRUD crudo sobre SQLite
│   ├── repository.py           # traduce SQL a DataFrames de pandas
│   ├── validation.py           # normalización y validación de inputs
│   ├── auth.py                  # hashing de contraseña y código de recuperación
│   └── backup.py                 # respaldo manual de la base de datos
├── services/
│   ├── budget.py                # cálculos de presupuesto del mes
│   ├── categorization.py        # agregaciones por categoría
│   └── trends.py                 # tendencias históricas, acumulados, filtro por rango
├── reports/
│   ├── charts.py                  # gráficas con matplotlib (PNG en base64)
│   └── pdf_export.py               # exportación del presupuesto a PDF
└── views/
    ├── theme.py                    # paletas claro/oscuro y helpers de estilo
    └── login.py                     # pantallas de login, creación y recuperación

tests/      # 95 pruebas con pytest, una por capa
data/       # se crea sola; ahí vive finanzas.db y backups/ (no se sube a git)
```

Cada capa solo conoce a la de abajo: `views`/`reports` → `services` →
`data` → `models`. `services/` nunca toca SQL directo; `data/` nunca
importa Flet. La página de Configuración (nombre, contraseña, respaldo)
vive directamente en `main.py`, no en un módulo aparte de `views/`.

## Qué hace la app hoy

**Login** — contraseña requerida al abrir, saludo con tu nombre,
recuperación por código de un solo uso, cierre de sesión automático
tras 30 minutos sin interacción.

**Dashboard** — selector de mes/año, las 6 métricas clave del mes
(ingresos, fijos, disponible discrecional, variables, balance,
invertido obligatorio), formularios de ingresos y gastos variables con
resumen agrupado por categoría, gestión completa de gastos fijos
(crear/editar/desactivar con vigencia por fecha), y una barra de
almacenamiento que muestra fijos/variables/invertido/disponible como
segmentos proporcionales de un vistazo.

**Ahorro** — acumulado histórico de ahorro (todos los meses, siempre
visible sin importar el mes seleccionado), formularios de inversión
(marcando obligatoria/discrecional) y retiros, resumen del mes.

**Tendencias** — selector de rango de fechas libre, y tres gráficas:
distribución de gastos variables por categoría (dona), fijos vs.
variables por mes (barras), y ahorro acumulado (línea).

**Configuración** — cambiar tu nombre o tu contraseña (ambos pidiendo
solo la contraseña actual como confirmación, sin código de
recuperación, porque ya estás autenticado dentro de la app), y crear un
respaldo manual de la base de datos con un clic.

**Exportar a PDF** (Dashboard) — genera un resumen del mes (tarjetas,
tablas de fijos/ingresos/variables, ahorro acumulado) listo para
guardar o mandar al teléfono. *Estado conocido*: el diálogo de "Guardar
como" (`ft.FilePicker`) no terminó de comportarse de forma confiable en
todas las versiones de Flet probadas; si el botón de exportar falla, el
problema está ahí, no en `reports/pdf_export.py`, que genera el
documento correctamente cuando se le da una ruta de archivo directa.

## Conceptos clave del modelo de datos

- **Ingresos y gastos variables**: captura puntual, mes por mes. No hay
  plantilla — cada mes empieza en blanco para estos dos.
- **Gastos fijos** (`fixed_expense_definitions`): se definen una sola vez
  y persisten indefinidamente. Si cambias un monto (ej. sube la renta),
  los meses pasados conservan el monto viejo — el cambio solo aplica
  desde la fecha que indiques en adelante. "Eliminar" un gasto fijo no
  borra su historial, solo deja de aplicar a futuro.
- **Inversiones**: cada una se marca `is_mandatory` (ej. un aporte
  recurrente a tu empresa) o discrecional (depende de si alcanza el
  presupuesto del mes). `available_for_discretionary` ya resta las
  obligatorias, como si fueran casi un gasto fijo más.
- **Retiros de inversión**: se registran en su propia tabla; el monto
  siempre lo decides tú al capturarlo. El sistema solo resta ese número
  del acumulado al recalcular — nunca decide ni sugiere cuánto retirar.
- **Ahorro acumulado** (`trends.add_cumulative_savings`): es neto —
  aportes menos retiros, más el rendimiento capturado (si lo capturas;
  si no, cuenta como 0). Persiste entre meses: invertir en junio y
  consultar julio sigue mostrando ese acumulado, no se resetea.
- **Rangos de fechas en Tendencias**: el acumulado siempre se calcula
  sobre el historial completo *antes* de filtrar por rango — así pedir
  "últimos 3 meses" no resetea el acumulado a cero al inicio del rango.

## Seguridad y autenticación

- La contraseña y el código de recuperación se guardan con
  **PBKDF2-HMAC-SHA256** (200,000 iteraciones) + salt aleatorio por
  secreto — nunca en texto plano, ni siquiera abriendo el archivo
  `finanzas.db` directamente.
- El código de recuperación se muestra **una sola vez**, justo después
  de crear o resetear la contraseña. Resetear genera uno nuevo e
  invalida el anterior. Cambiar la contraseña desde Configuración (ya
  autenticado) *no* invalida el código vigente.
- La sesión se cierra sola tras 30 minutos sin interacción (cambiar de
  mes, agregar un registro, navegar entre páginas — cualquier acción
  reinicia el contador), devolviendo a la pantalla de login.
- Esto protege contra alguien que abra la app o el archivo `.db`
  casualmente. No es un sistema de cifrado de disco — si necesitas esa
  capa adicional, considera cifrar la carpeta `data/` con una
  herramienta del sistema operativo (BitLocker, FileVault, VeraCrypt).

## Respaldo de datos

Desde Configuración, "Crear respaldo ahora" copia tu base de datos
activa a `data/backups/finanzas_AAAA-MM-DD_HHMM.db`, usando el
mecanismo oficial de respaldo de SQLite (`Connection.backup()`) en vez
de copiar el archivo crudo — evita corrupción si hubiera alguna
escritura en curso. Cada respaldo es un archivo `.db` independiente y
completo; puedes abrirlo con cualquier herramienta SQLite si alguna vez
necesitas recuperar datos de un punto anterior.

## Notas de diseño que vale la pena recordar

- `month_balance` **no** resta inversiones — invertir es una decisión
  sobre el dinero disponible, no un gasto. Para ver el efecto de las
  inversiones obligatorias en lo que realmente te queda libre, usa
  `available_for_discretionary`.
- Las categorías se normalizan automáticamente (espacios, mayúsculas,
  Title Case respetando preposiciones en español) para que "Comida" y
  "comida " no se conviertan en dos categorías distintas en las
  gráficas ni en los resúmenes.
- `add_investment(..., return_amount=...)` es opcional — puedes
  capturar el aporte sin saber aún el rendimiento del mes.
- Las columnas numéricas de `get_all_months_summary_df()` se fuerzan
  explícitamente a `float64` (no solo `fillna`) — sin esto, operaciones
  estrictas de matplotlib como `fill_between` fallan en runtime con un
  error críptico. Hay una prueba dedicada a vigilar esto
  (`test_columnas_numericas_son_float64_no_object`).

## Compatibilidad de versión de Flet

Durante el desarrollo encontramos varias diferencias de API entre
versiones de Flet (la usada para construir vs. la instalada en la
máquina final), entre ellas:
- `ft.alignment.center` → `ft.Alignment.CENTER`
- `expand` en `Container` exige `int`/`bool`, no acepta `float`
- `ft.app()` está deprecado a favor de `ft.run()`
- `page.services` puede ser una lista simple (`.append()`) en vez de un
  `ServiceRegistry` con `.register_service()`, según la versión

Si al actualizar Flet aparece un error de tipo `AttributeError` o
`TypeError` sobre un parámetro o atributo, es probable que sea este
mismo patrón — revisa la API exacta en tu versión instalada antes de
asumir que el código está mal.

## Pendientes conocidos

- El botón de exportar a PDF puede no abrir el diálogo de guardado
  correctamente en algunas versiones de Flet (ver sección de arriba).
