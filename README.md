# Auditoría de actas E-14 — Segunda vuelta presidencial Colombia 2026 (Bolívar)

Herramienta para **leer actas E-14** (oficial de la Registraduría y la del testigo
electoral), pasarlas a una tabla común y **comparar** para detectar discrepancias.
Todo lo dudoso (confianza < 80%, suma que no cuadra o fuentes que difieren) se
**marca para revisión humana**.

El trabajo se organiza **por lotes**: un **lote = un municipio**. Una sola instancia
procesa un municipio a la vez (volumen acotado, modular). El **Excel "Mesa a Mesa" de
la Registraduría** es el *catálogo* (universo de mesas) que dice qué número le toca a
cada municipio y cuántas mesas tiene. Con eso se mide la **cobertura** (cuántas mesas
ya tenemos vs cuántas faltan) y se orquesta la auditoría del lote (`auditar.py`).

> Lee primero `VISION_Y_DECISIONES.md` (el porqué), `PLAN_PASO_A_PASO.md` (roadmap) y
> **`GUIA_ARCHIVOS.md`** (qué hace cada archivo del repo).

---

## Guía de reproducción (para otro ingeniero)

Sigue estos pasos **en orden**. Con el par de prueba que ya viene en el repo no necesitas
buscar PDFs externos.

### Requisitos

| Requisito | Versión mínima |
|-----------|----------------|
| Python | 3.11+ (probado en 3.12) |
| SO | Linux, macOS o Windows |
| Red | Solo para OCR (Gemini/GPT); alineación es offline |
| Clave API | [Google AI Studio](https://aistudio.google.com/apikey) — capa gratis de Gemini Flash |

### 1. Clonar y entrar al proyecto

```bash
cd auditoria-e14
```

### 2. Entorno virtual e dependencias

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configurar la API

```bash
cp .env.example .env
```

Edita `.env` y pega tu clave:

```bash
GEMINI_API_KEY=AIza...tu_clave...
GEMINI_MODEL=gemini-3.5-flash
```

> `gemini-3.5-flash` quedó como modelo por defecto tras probarlo contra E-14 reales de la
> 2ª vuelta 2022: corrigió un error de dígito manuscrito que `gemini-2.5-flash` no detectaba
> (87 en vez de 89, con 95% de confianza reportada en ambos casos — la confianza del modelo
> no garantiza exactitud). `gemini-2.5-pro` no es una alternativa en el tier gratis: su cuota
> ahí es 0 y requiere facturación.

Verifica **antes** de procesar actas:

```bash
python probar_api.py
# Debe imprimir: ✅ La API respondió correctamente
```

Si sale `HTTP 429`, espera unos minutos (cuota del free tier) y reintenta. No corras los
lectores en bucle mientras la cuota esté agotada.

**Doble verificación con GPT (opcional, cuando Gemini reporta confianza baja):** **apagado
por defecto, solo se activa si lo pedís explícitamente** — nunca se gasta esta llamada
extra sin que alguien lo solicite a propósito. Dos formas de pedirlo (con `OPENAI_API_KEY`
puesta en `.env`):
- **Por corrida** (recomendado): `python auditar.py ... --verificar-baja-confianza`
- **Siempre** (si preferís dejarlo prendido de forma permanente): `OCR_VERIFICAR_BAJA_CONFIANZA=1` en `.env`

Con cualquiera de las dos, las casillas con confianza < 80% se le vuelven a preguntar a
GPT como segunda opinión: si coinciden, la confianza sube; si discrepan, queda marcado
para revisión con ambos valores en las notas (nunca se promedia ni se inventa un valor).
Solo gasta la llamada extra en las casillas dudosas, no en cada acta.

### 4. Plantilla y par de prueba

El repo trae un par de **primera vuelta** (Cartagena, zona 21, puesto 01, mesa 13)
que sirvió para probar el pipeline, pero **ya no alinea** contra la plantilla de
segunda vuelta (formato distinto: 2 candidatos en vez de 13). Para volver a
probar de punta a punta, coloca un par real de segunda vuelta en la **carpeta del
lote** (un municipio):

```
datos/<NN_nombre>/testigos/<NuMunicipio>_<ZONA>_<PUESTO>_<MESA>_testigo.pdf
datos/<NN_nombre>/registraduria/<NuMunicipio>_<ZONA>_<PUESTO>_<MESA>_registraduria.pdf
```

**Nomenclatura: `NuMunicipio-zona-puesto-mesa`** (separadas por `_` o `-`).

- **`NuMunicipio`** es el **número de municipio de la Registraduría** (el del Excel
  "Mesa a Mesa", columna `MUN`), **no** el código DANE. Ojo: en esa codificación
  Bolívar es el **departamento 5** y los municipios **no son consecutivos**
  (Cartagena = 1, Magangué = 28, Mompós = 43…). Ver `e14/catalogo.py`.
- El municipio es **obligatorio** porque zona/puesto/mesa se numeran **dentro de cada
  municipio**: sin él, el comparador fusionaría mesas de municipios distintos que
  comparten el mismo zona_puesto_mesa.
- Los **ceros a la izquierda no importan**: `1_21_01_13` y `1_21_1_13` son la misma
  mesa (se normalizan al código canónico). Así el nombre de archivo cruza con el
  catálogo aunque uno traiga ceros y el otro no.

| Archivo | `codigo_mesa` (canónico) |
|---------|--------------------------|
| `1_21_01_13_testigo.pdf` | `1_21_1_13` |
| `1_21_01_13_registraduria.pdf` | `1_21_1_13` |

El comparador cruza por ese código canónico. Ver `e14/mesa.py`
(`codigo_canonico`, `normalizar_codigo`).

> Las carpetas del lote (`datos/<NN_nombre>/…`) las crea automáticamente
> `cobertura.py --crear-carpetas` o `auditar.py` (ej. `datos/01_cartagena/`).

**Plantilla:** coloca el PDF oficial en blanco de segunda vuelta en
`plantillas/muestra-formulario-e14-segunda-vuelta.pdf` (ver `e14/alineacion.py`
si el layout real no entra en una sola página).

### 4.1. Traer los E-14 desde Google Drive (opcional, en vez de copiarlos a mano)

Si el equipo sube las actas a una carpeta compartida de Google Drive (en vez de
pasártelas archivo por archivo), `descargar_drive.py` las trae solo:

- **No importa cómo organicen las carpetas dentro de Drive.** Busca recursivamente
  bajo la carpeta raíz que le indiques y clasifica cada archivo **por su nombre**
  (la misma nomenclatura `NuMunicipio_zona_puesto_mesa_<testigo|registraduria>` de
  siempre). El equipo que sube los archivos se organiza como quiera adentro de esa
  carpeta; lo único que importa es el **nombre del archivo**.
- **No re-descarga lo que ya está local** con el mismo tamaño (idempotente, igual
  que `auditar.py`).
- Los archivos que no calzan con la nomenclatura (o cuyo municipio no está en el
  catálogo) se listan al final **sin inventar nada** — hay que renombrarlos en Drive.

**Quién necesita acceso a la carpeta de Drive:** la persona dueña del Drive la
comparte (botón "Compartir" de Drive, como cualquier carpeta) con:
- **Editor** para el equipo que sube/escrapea las actas.
- **Lector** para cualquiera que solo vaya a correr `descargar_drive.py` /
  `auditar.py` en su máquina.

No hay ninguna clave ni cuenta de servicio que repartir: cada persona se autentica
con **su propia cuenta de Google** (ver abajo).

**Configuración (una sola vez, por persona):**

1. Entrá a [Google Cloud Console](https://console.cloud.google.com/) con tu cuenta
   de Google y creá un proyecto nuevo (cualquier nombre).
2. **APIs y servicios → Biblioteca** → buscá "Google Drive API" → **Habilitar**.
   Repetí lo mismo para "Google Sheets API" (se usa en §4.2, para el panel maestro
   de resultados).
3. **APIs y servicios → Pantalla de consentimiento de OAuth**: tipo "Externo",
   completá los campos obligatorios (nombre de la app, tu correo) y guardá. Si te
   pide agregar "usuarios de prueba", agregá los correos de Google de todas las
   personas del equipo que van a correr el script (mientras la app no esté
   publicada, solo esos correos pueden autenticarse).
4. **APIs y servicios → Credenciales → Crear credenciales → ID de cliente de
   OAuth**. Tipo de aplicación: **"Aplicación de escritorio"**. Creala y descargá
   el JSON.
5. Guardá ese archivo en la raíz del proyecto como **`drive_credentials.json`**
   (no se versiona, ya está en `.gitignore`). Cada persona del equipo repite los
   pasos 1-5 con su propia cuenta, **o** comparten el mismo `drive_credentials.json`
   entre todos (es solo el cliente OAuth, no una clave personal — sigue pidiendo
   el login individual de cada uno al usarlo).
6. Instalá las dependencias nuevas si no lo hiciste: `pip install -r requirements.txt`.

**Uso:**

```bash
# El ID de la carpeta es el que aparece en la URL de Drive:
#   https://drive.google.com/drive/folders/<ESTE_ES_EL_ID>
python descargar_drive.py "ruta/al/Bolivar_Mesa_Mesa_2026 Presidencial.xlsx" \
    --carpeta-drive <ID_DE_LA_CARPETA>
```

La primera vez abre el navegador para que autorices con tu cuenta de Google;
después queda cacheado en `.drive_token.json` (tampoco se versiona) y no vuelve a
pedir login mientras el token siga vigente. El permiso pedido incluye lectura y
escritura de Drive y de Sheets (lo necesita §4.2 para subir resultados), no solo
lectura — si ya habías autorizado con una versión anterior de este programa que
solo pedía lectura, borrá `.drive_token.json` y volvé a correr el comando para
re-autorizar con los permisos nuevos.

`--dry-run` muestra qué se descargaría sin bajar nada (para revisar antes de
gastar ancho de banda). Una vez bajados los archivos a `datos/<NN_nombre>/…`,
seguís con `auditar.py` exactamente igual que si los hubieras copiado a mano.

### 4.2. Centralizar resultados del equipo (Drive + panel en Sheets)

Cada persona audita su zona/puesto en **su `actas.db` local** (§5, con `--zona`/
`--puesto` si querés acotar). Para juntar todo en una base maestra sin perder
trazabilidad ni mergear nada sin que alguien lo revise:

1. **Creá la hoja de cálculo maestra:** un Google Sheet en blanco, compartido con
   el mismo grupo de gente. El ID es el que aparece en su URL:
   `https://docs.google.com/spreadsheets/d/<ESTE_ES_EL_ID>/edit`. No hace falta
   crear el encabezado a mano — `subir_resultados.py` lo crea solo la primera vez.
2. **Creá (o reutilizá) una carpeta de Drive para los resultados** — el ID es el
   mismo tipo que usaste en §4.1 — y compartila igual: Editor para quien sube
   resultados, Lector para quien solo consolida.
3. **Cada persona, al terminar su zona/puesto**, sube su `actas.db`:

   ```bash
   python subir_resultados.py actas.db --persona "juan" \
       --carpeta-drive <ID_CARPETA_RESULTADOS> --hoja <ID_HOJA_MAESTRA> \
       --municipio 1 --zona 1
   ```

   Esto sube el archivo a Drive y agrega una fila al panel ("Panel" dentro de la
   hoja) con un resumen (mesas leídas, coinciden, discrepancia, casillas con
   confianza baja) y estado **"Pendiente"**.
4. **El jefe y vos revisan el panel en tiempo real** (es una hoja de Sheets común,
   se ve actualizarse sola) y escriben **"Sí"** en la columna "Aprobado" de las
   filas que correspondan — eso pasa por fuera del código, es edición normal de
   la hoja.
5. **Consolidás** lo aprobado a la base maestra:

   ```bash
   python consolidar_resultados.py actas_maestra.db \
       --carpeta-drive <ID_CARPETA_RESULTADOS> --hoja <ID_HOJA_MAESTRA>
   ```

   Solo mergea filas con "Aprobado" = sí; cada fila mergeada queda marcada
   "Mergeado" para no repetirse en la próxima corrida. Si una mesa ya existía en
   la maestra, el versionado de siempre (`Almacen`) archiva la versión anterior
   en vez de perderla. `--dry-run` muestra qué se mergearía sin tocar nada.
6. Corré `comparar.py` sobre `actas_maestra.db` para el Excel consolidado de todo
   lo aprobado hasta el momento.

### 5. Auditar un lote completo (camino recomendado)

Con el **Excel de la Registraduría** como catálogo, primero ves cuántas mesas hay y
cuántas tenés listas, y luego auditás el lote de un municipio con un solo comando.

```bash
# a) Tablero de cobertura de TODO el departamento (no gasta OCR)
python cobertura.py "ruta/al/Bolivar_Mesa_Mesa_2026 Presidencial.xlsx"

# b) Detalle de un lote y crea sus carpetas (datos/01_cartagena/…)
python cobertura.py "ruta/al/…xlsx" --municipio 1 --crear-carpetas
#   -> ahí colocas los PDFs: datos/01_cartagena/{testigos,registraduria}/

# c) Ver qué se procesaría (sin gastar OCR)
python auditar.py "ruta/al/…xlsx" --municipio 1 --plan

# d) Auditar el lote: lee pares, guarda en DB y genera el Excel de comparación
python auditar.py "ruta/al/…xlsx" --municipio 1 --solo-pagina-1 --limite 50 --paralelo 4
```

- **Lote = un municipio** (`--municipio`, el `NuMunicipio` del catálogo).
- `auditar.py` solo procesa las mesas **listas** (testigo **y** oficial presentes),
  así no se gasta OCR en mesas a medias. `--incluir-parciales` para forzar las demás.
- **Idempotente**: no reprocesa lo ya leído; `--reauditar` fuerza y **archiva la
  versión anterior** (historial, ver §re-auditoría). `--limite N` acota el volumen.
- **`--paralelo N`** lee N actas a la vez (varios hilos llamando a Gemini en
  simultáneo) para terminar el lote más rápido. El cuello de botella de cada lectura
  es esperar la respuesta de la API, no CPU, así que paraleliza bien. Empezá con
  `--paralelo 4` y subí mientras no veas errores `429`; tu límite real de RPM está en
  https://aistudio.google.com/rate-limit (varía según tu tier de facturación).
- Internamente reutiliza el pipeline de los scripts de abajo (mismo `leer_acta_pdf`
  + `comparar`). Esos scripts siguen sirviendo para procesar un archivo suelto.

### 6. Flujo manual por script: primero oficial, luego testigo

**Orden sugerido** (1 llamada API por script, sin bucles):

```bash
# Paso 1 — SOLO Registraduría (1 llamada OCR; acta de segunda vuelta = 1 sola página de votos)
python leer_registraduria.py datos/registraduria/21_01_13_registraduria.pdf actas.db \
  --solo-pagina-1
# Al terminar imprime tabla de votos leídos y el siguiente comando

# Paso 2 — Ver qué quedó en la base SIN gastar más API
python ver_acta.py actas.db --fuente registraduria

# Paso 3 — Testigo (otra llamada OCR, cuando tengas cuota)
python leer_testigos.py datos/testigos/21_01_13_testigo.pdf actas.db \
  --tipo claveros --solo-pagina-1

# Paso 4 — Comparar
python comparar.py actas.db comparacion_21_01_13.xlsx
```

> El par de prueba `21_01_13_*` es **legacy** (solo zona_puesto_mesa, sin
> `NuMunicipio` ni carpeta de lote). Sigue sirviendo para probar instalación. Para
> datos reales usa la nomenclatura numérica completa y el flujo por lote de §5.

`--solo-pagina-1` = solo la página de candidatos/totales, sin la hoja de firmas (más
barato: 1 OCR por acta). Si solo cargaste la oficial y corres `comparar.py`, te muestra
el contenido de la Registraduría y avisa que falta el testigo.

### 7. Resultado esperado

Define aquí el resultado esperado de tu par de prueba real de segunda vuelta (c1, c2,
blanco, nulos, no_marcados) una vez lo proceses, para detectar regresiones futuras.
Si la API respondió bien, ambas fuentes deberían coincidir y el Excel no tendrá
discrepancias en esas columnas. Revisa la consola: cada acta muestra confianza, inliers
de alineación e informe OCR (`OK:` / `REVISAR:`).

### 8. Procesar carpetas completas (bajo nivel)

Para todas las mesas emparejadas de una carpeta suelta (sin pasar por `auditar.py`):

```bash
python leer_testigos.py datos/01_cartagena/testigos actas.db --tipo claveros
python leer_registraduria.py datos/01_cartagena/registraduria actas.db
python comparar.py actas.db comparacion_E14.xlsx
```

`comparar.py` lista al inicio qué pares existen en ambas carpetas y cuáles faltan.
Para el flujo por lote con cobertura y control de volumen, prefiere `auditar.py` (§5).

### 9. Validación 100% local (sin API, sin cuota)

Para probar instalación y calidad del escaneo **sin gastar Gemini**:

```bash
# Solo capa 1: alinea, reporta inliers, guarda imagen en debug/
python validar_alineacion.py datos/registraduria/21_01_13_registraduria.pdf --solo-pagina-1
python validar_alineacion.py datos/testigos/21_01_13_testigo.pdf --solo-pagina-1

# Ver qué hay en la base (sin re-OCR)
python ver_acta.py actas.db --fuente registraduria
```

Sin `GEMINI_API_KEY`, los lectores usan backend **manual**: alinean pero dejan votos en
`null`. El comparador marca **SIN_LECTURA** (ya no dice “coinciden” en vacío).

---

## Estado del proyecto

| Capa | Archivo | Estado |
|---|---|---|
| 1. Alineación por plantilla | `e14/alineacion.py` | ✅ |
| 2. OCR (Gemini/GPT) | `e14/ocr.py` | ✅ (requiere clave en `.env`) |
| 3. Comparación | `e14/comparador.py`, `comparar.py` | ✅ |
| 4. Validación (suma/confianza) | lectores + `e14/lectura.py` | ✅ |
| Nomenclatura + emparejamiento por mesa | `e14/mesa.py` | ✅ |
| Catálogo (Excel → universo) | `e14/catalogo.py`, `cobertura.py` | ✅ |
| Cobertura por lote | `e14/cobertura.py`, `cobertura.py` | ✅ |
| Orquestador de lote | `auditar.py` | ✅ |
| Preprocesamiento OCR | `e14/preprocess.py` | ✅ |
| Almacén + versionado de re-auditoría | `e14/almacen.py` (SQLite) | ✅ |
| Tests | `tests/` (pytest, 30) | ✅ |

Pendiente: app Windows, DB en nube, recorte por casilla (ver `PLAN_PASO_A_PASO.md`).

Correr los tests: `pytest -q` (o `.venv/bin/python -m pytest -q`).

---

## Estructura del repo

```
e14/                    paquete con la lógica
  modelo.py             contrato ActaE14 + 2 candidatos (segunda vuelta)
  almacen.py            SQLite (actas.db) + historial de re-auditoría
  mesa.py               nomenclatura NuMunicipio_zona_puesto_mesa, código canónico, emparejamiento
  catalogo.py           Excel "Mesa a Mesa" → universo de mesas por municipio
  cobertura.py          cruza catálogo vs archivos presentes (estados del lote)
  alineacion.py         CAPA 1: SIFT + homografía vs plantilla
  preprocess.py         recorte de negro, zoom, CLAHE antes del OCR
  ocr.py                CAPA 2: Gemini / GPT / manual
  evidencia.py          detectar copias visibles en la foto
  lectura.py            PDF → ActaE14 (une capas 1 y 2)
  comparador.py         CAPA 3: lógica de comparación
auditar.py              ORQUESTADOR: audita un lote (municipio) de punta a punta
cobertura.py            SCRIPT: tablero de cobertura / detalle de un lote
leer_testigos.py        SCRIPT 1: testigo (CSV o PDF) → tabla
leer_registraduria.py   SCRIPT 2: oficial PDF → tabla
comparar.py             SCRIPT 3: cruza fuentes → Excel
probar_api.py           ping mínimo a Gemini/GPT
cli_args.py             flags --tipo, --codigo, --solo-pagina-1
tests/                  pruebas pytest (catálogo, cobertura, orquestador, almacén, mesa)
plantillas/             E-14 en blanco oficial de segunda vuelta (alineación)
datos/
  <NN_nombre>/          un LOTE = un municipio (ej. 01_cartagena/)
    testigos/           E-14 del testigo del municipio
    registraduria/      E-14 oficial del municipio
  testigos/             (legacy) par de prueba 21_01_13 (primera vuelta)
  registraduria/        (legacy) idem
ejemplos/               CSV de ejemplo
```

---

## Convención de archivos (importante)

**Formato recomendado** (dentro de la carpeta del lote del municipio):

```
datos/<NN_nombre>/testigos/<NuMunicipio>_<ZONA>_<PUESTO>_<MESA>_testigo.pdf
datos/<NN_nombre>/registraduria/<NuMunicipio>_<ZONA>_<PUESTO>_<MESA>_registraduria.pdf
```

Ejemplo (Cartagena = municipio 1): `1_21_01_13_testigo.pdf` ↔
`1_21_01_13_registraduria.pdf` → mesa canónica `1_21_1_13`.

- **`NuMunicipio` = número de municipio de la Registraduría** (columna `MUN` del Excel
  catálogo, **no** DANE). Es obligatorio porque zona/puesto/mesa se repiten entre
  municipios; sin él, el comparador fusionaría mesas de lugares distintos.
- Los **ceros a la izquierda son indiferentes** (`1_21_01_13` ≡ `1_21_1_13`): se
  normalizan al código canónico que también produce el catálogo, así cruzan siempre.

**No uses** nombres largos tipo `88-128-15-85-001.pdf` salvo que declares `--codigo`
manualmente: el parser espera el municipio seguido de tres segmentos numéricos
(zona, puesto, mesa).

---

## Flags de los lectores

| Flag | Uso |
|------|-----|
| `--tipo claveros\|delegados\|transmision` | De qué **copia** del E-14 se leyeron los votos |
| `--codigo 1_21_01_13` | Forzar código de mesa (un solo archivo) |
| `--solo-pagina-1` / `--solo-p1` | Solo la página de candidatos/totales (sin firmas); 1 OCR por acta |
| `[actas.db]` | Base SQLite de salida (default: `actas.db`) |

Por defecto: testigos sin `--tipo` → `desconocido`; registraduría → `delegados`.

## Flags de cobertura y auditoría por lote

`cobertura.py <excel> [--municipio N] [--datos datos] [--crear-carpetas]`

`auditar.py <excel> --municipio N`:

| Flag | Uso |
|------|-----|
| `--municipio N` / `-m N` | Lote a auditar (el `NuMunicipio` del catálogo). Obligatorio. |
| `--zona N` | Acotar a esta zona dentro del municipio (ej. `--municipio 1 --zona 1`) |
| `--puesto N` | Acotar a este puesto dentro de la zona (**requiere `--zona`**; nunca puesto solo — el número de puesto se repite en muchas zonas) |
| `--plan` | Listar qué mesas se procesarían y salir (**no gasta OCR**) |
| `--limite N` | Procesar solo las primeras N mesas (control de volumen/costo) |
| `--paralelo N` | Leer N actas a la vez en hilos (default 1 = secuencial). Acelera el lote; el guardado en SQLite sigue siendo secuencial. Si ves `429`, bajalo — el límite real de RPM está en https://aistudio.google.com/rate-limit |
| `--verificar-baja-confianza` | Doble lectura con GPT, solo en casillas con confianza < 80% (requiere `OPENAI_API_KEY`). **Apagado salvo que se pida con este flag.** |
| `--reauditar` | Reprocesar mesas ya leídas (archiva la versión anterior) |
| `--incluir-parciales` | Incluir mesas con una sola fuente (por defecto solo las **listas**) |
| `--tipo-testigo`, `--solo-pagina-1` | Igual que en los lectores |
| `--datos`, `--db`, `--salida` | Carpeta base, SQLite y Excel de salida |

## Flags de descargar_drive.py

`descargar_drive.py <excel> --carpeta-drive <ID> [--datos datos] [--dry-run]`

| Flag | Uso |
|------|-----|
| `--carpeta-drive ID` | ID de la carpeta raíz en Drive (de la URL). Obligatorio. |
| `--dry-run` | Mostrar qué se descargaría, sin bajar nada |
| `--credenciales archivo.json` | client_secret.json de OAuth (default: `drive_credentials.json`) |
| `--token archivo.json` | Caché local de la sesión ya autorizada (default: `.drive_token.json`) |
| `--datos` | Carpeta base local donde colocar lo descargado (default: `datos`) |

## Flags de subir_resultados.py / consolidar_resultados.py

`subir_resultados.py <actas.db> --persona NOMBRE --carpeta-drive <ID> --hoja <ID> [--municipio N] [--zona N] [--puesto N]`

`consolidar_resultados.py <actas_maestra.db> --carpeta-drive <ID> --hoja <ID> [--dry-run]`

| Flag | Uso |
|------|-----|
| `--persona NOMBRE` | Quién sube (identifica la fila en el panel). Obligatorio en `subir_resultados.py`. |
| `--carpeta-drive ID` | Carpeta de Drive donde viven los `actas.db` subidos por el equipo. Obligatorio. |
| `--hoja ID` | ID de la hoja de cálculo maestra (de su URL). Obligatorio. |
| `--municipio`, `--zona`, `--puesto` | Solo informativos, para identificar qué se subió en el panel |
| `--dry-run` (solo consolidar) | Mostrar qué se mergearía sin tocar la base maestra ni el panel |
| `--credenciales`, `--token` | Igual que en `descargar_drive.py` |

## Re-auditoría (historial de versiones)

Re-correr el OCR sobre una mesa ya leída **no pierde** la lectura anterior: antes de
sobrescribir, la versión previa se archiva en la tabla `actas_historial` (con número de
versión y fecha). `actas` siempre tiene la versión vigente, así `comparar.py` no cambia.
La **verificación manual** también se conserva al re-auditar. Ver
`e14/almacen.py` → `historial()` y `num_versiones()`.

---

## Ejemplar del E-14 (trazabilidad)

El E-14 se imprime en varias copias. Cada acta guarda:

| Campo | Significado |
|-------|-------------|
| `tipo_acta` | Copia **de la que se tomaron los votos** |
| `copias_en_evidencia` | Copias **visibles** en la foto/PDF |

| Tipo | Quién la guarda |
|------|-----------------|
| `claveros` | Arca triclave — suele ser la del testigo |
| `delegados` | Delegados Registraduría — suele ser la oficial publicada |
| `transmision` | Puesto de transmisión (pre-conteo) |

El Excel incluye hoja **Trazabilidad E-14** con esas columnas por fuente.

---

## Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---------|----------------|-----------|
| `HTTP 429` en OCR | Cuota Gemini agotada | Esperar; usar `ver_acta.py` para ver la base sin API |
| Quiero ver la oficial sin re-OCR | Ya está en `actas.db` | `python ver_acta.py actas.db --fuente registraduria` |
| Todos los votos `null`, confianza `—` | Sin clave o error API | Revisar `.env`; correr `probar_api.py` |
| `REVISAR` en c2/c4 con otros OK | Dígitos con puntos (`..3`, `.77`) | Re-correr; el pipeline hace zoom y re-OCR |
| Nota “2 copias” en PDF oficial alto | Heurística vieja | Actualizado: oficial usa título pág. 1 |
| Alineación pobre (< 25 inliers) | PDF muy distinto a plantilla | Revisar escaneo; marcar revisión manual |
| Discrepancia testigo vs oficial | Copias distintas o OCR parcial | Confirmar `--tipo`; comparar notas OCR |

---

## Criterios de revisión manual

Una mesa/casilla va a revisión si: confianza OCR < 80%, la suma no cuadra, las fuentes
difieren, o la alineación fue pobre (pocos inliers).

---

## Qué NO va al git

- `.env` (claves)
- `actas.db`, `*.xlsx` (salidas generadas)
- `debug/` (imágenes de depuración)
- PDFs en `datos/` **excepto** el par de prueba `21_01_13_*` (whitelist en `.gitignore`;
  ese par es de primera vuelta, solo sirve para probar instalación, no alinea contra la
  plantilla de segunda vuelta)
