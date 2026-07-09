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

## Compilar el ejecutable de Windows (.exe)

Genera un ejecutable nativo de Windows (Nexus Budget) que no requiere
tener Python instalado para correr.

### Requisitos previos (solo la primera vez)

1. **Visual Studio Community 2022** con el workload
   **"Desktop development with C++"** — lo usa Flutter internamente
   para compilar el ejecutable nativo. Descarga gratuita en
   visualstudio.microsoft.com.

2. **Modo de desarrollador de Windows** activado — necesario para que
   Flutter pueda crear symlinks durante el build:
   ```powershell
   start ms-settings:developers
   ```

3. **Ícono de la app** en `src/assets/icon.png` — PNG de 1024×1024 px
   con fondo transparente. Flet genera automáticamente todos los
   tamaños que Windows necesita a partir de ese archivo.

4. **Archivo de entrada** `src/main.py` con este contenido exacto:
   ```python
   from finanzas_app.main import main
   import flet as ft

   ft.app(target=main)
   ```

### Comandos

```powershell
# Sincronizar dependencias primero
uv sync

# Generar el ejecutable
uv run flet build windows
```

La primera vez descarga Flutter automáticamente (~varios GB) y puede
tardar 15-30 minutos. Las siguientes veces es mucho más rápido.

### Resultado

El ejecutable queda en:
```
build/windows/nexus-budget/nexus-budget.exe
```

La carpeta completa `nexus-budget/` es autocontenida — puedes copiarla
a cualquier ubicación (otra carpeta, USB, otro PC con Windows) y la app
funciona sin instalar nada. La base de datos se crea automáticamente en
`nexus-budget/data/finanzas.db` junto al ejecutable.

**No subas la carpeta `build/` a git** — ya está en `.gitignore` porque
pesa varios cientos de MB y se regenera con un comando.

### Para regenerar el .exe tras cambios en el código

```powershell
uv run flet build windows
```

No es necesario borrar la carpeta `build/` antes — se sobreescribe
automáticamente. La base de datos en `build/windows/nexus-budget/data/`
no se toca durante el build.

## Estructura del proyecto

```
src/
├── main.py                    # punto de entrada para flet build
├── assets/
│   └── icon.png                # ícono de la app (1024×1024 PNG)
└── finanzas_app/
    ├── main.py                  # lógica principal: login + Dashboard/Ahorro/Tendencias/Configuración
    ├── models/
    │   └── schema.py             # tablas SQLite y conexión
    ├── data/
    │   ├── db.py                 # CRUD crudo sobre SQLite
    │   ├── repository.py         # traduce SQL a DataFrames de pandas
    │   ├── validation.py         # normalización y validación de inputs
    │   ├── auth.py               # hashing de contraseña y código de recuperación
    │   └── backup.py             # respaldo manual de la base de datos
    ├── services/
    │   ├── budget.py             # cálculos de presupuesto del mes
    │   ├── categorization.py     # agregaciones por categoría
    │   └── trends.py             # tendencias históricas, acumulados, filtro por rango
    ├── reports/
    │   ├── charts.py             # gráficas con matplotlib (PNG en base64)
    │   └── pdf_export.py         # exportación del presupuesto a PDF
    └── views/
        ├── theme.py              # paletas claro/oscuro y helpers de estilo
        └── login.py              # pantallas de login, creación y recuperación

tests/      # 95 pruebas con pytest, una por capa
data/       # se crea sola; ahí vive finanzas.db y backups/ (no se sube a git)
build/      # generado por flet build windows (no se sube a git)
```

Cada capa solo conoce a la de abajo: `views`/`reports` → `services` →
`data` → `models`. `services/` nunca toca SQL directo; `data/` nunca
importa Flet. La página de Configuración (nombre, contraseña, respaldo)
vive directamente en `finanzas_app/main.py`, no en un módulo aparte.

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
solo la contraseña actual como confirmación), y crear un respaldo
manual de la base de datos con un clic.

**Exportar a PDF** (Dashboard) — genera un resumen del mes listo para
guardar o mandar al teléfono. *Estado conocido*: el diálogo de
"Guardar como" (`ft.FilePicker`) no terminó de comportarse de forma
confiable en todas las versiones de Flet probadas.

## Conceptos clave del modelo de datos

- **Ingresos y gastos variables**: captura puntual, mes por mes. No hay
  plantilla — cada mes empieza en blanco para estos dos.
- **Gastos fijos** (`fixed_expense_definitions`): se definen una sola vez
  y persisten indefinidamente. Si cambias un monto, los meses pasados
  conservan el monto viejo — el cambio solo aplica desde la fecha que
  indiques. "Eliminar" un gasto fijo no borra su historial, solo deja
  de aplicar a futuro desde la fecha que indiques.
- **Inversiones**: cada una se marca `is_mandatory` o discrecional.
  `available_for_discretionary` ya resta las obligatorias.
- **Retiros de inversión**: el monto siempre lo decides tú al capturarlo.
- **Ahorro acumulado**: neto — aportes menos retiros, más rendimiento
  capturado. Persiste entre meses.
- **Rangos de fechas en Tendencias**: el acumulado se calcula sobre el
  historial completo *antes* de filtrar por rango.

## Seguridad y autenticación

- Contraseña y código de recuperación guardados con
  **PBKDF2-HMAC-SHA256** (200,000 iteraciones) + salt aleatorio —
  nunca en texto plano.
- El código de recuperación se muestra **una sola vez** al crear o
  resetear la contraseña. Resetear genera uno nuevo e invalida el anterior.
- Sesión automática cerrada tras 30 minutos sin interacción.

## Respaldo de datos

Desde Configuración, "Crear respaldo ahora" copia tu base de datos a
`data/backups/finanzas_AAAA-MM-DD_HHMM.db` usando el mecanismo oficial
de SQLite (`Connection.backup()`). Cada respaldo es un archivo `.db`
independiente y completo.

## Notas de diseño

- `month_balance` **no** resta inversiones — invertir es una decisión
  sobre el dinero disponible, no un gasto.
- Las categorías se normalizan automáticamente (Title Case, espacios,
  preposiciones en español).
- Las columnas numéricas de `get_all_months_summary_df()` se fuerzan a
  `float64` — sin esto, matplotlib falla en runtime con un error
  críptico. Hay una prueba dedicada a vigilar esto.

## Compatibilidad de versión de Flet

Diferencias de API encontradas entre versiones:
- `ft.alignment.center` → `ft.Alignment.CENTER`
- `expand` en `Container` exige `int`/`bool`, no `float`
- `ft.app()` deprecado a favor de `ft.run()`
- `page.services` puede ser lista simple (`.append()`) o `ServiceRegistry`

## Pendientes conocidos

- El botón de exportar a PDF puede no abrir el diálogo de guardado
  correctamente en algunas versiones de Flet.
