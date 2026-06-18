# Auditoría de actas E-14 — Segunda vuelta presidencial Colombia 2026 (Bolívar)

Herramienta para **leer actas E-14** (oficial de la Registraduría y la del testigo
electoral), pasarlas a una tabla común y **comparar** para detectar discrepancias.
Todo lo dudoso (confianza < 80%, suma que no cuadra o fuentes que difieren) se
**marca para revisión humana**.

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
GEMINI_MODEL=gemini-2.5-flash
```

Verifica **antes** de procesar actas:

```bash
python probar_api.py
# Debe imprimir: ✅ La API respondió correctamente
```

Si sale `HTTP 429`, espera unos minutos (cuota del free tier) y reintenta. No corras los
lectores en bucle mientras la cuota esté agotada.

### 4. Plantilla y par de prueba

El repo trae un par de **primera vuelta** (Cartagena, zona 21, puesto 01, mesa 13)
que sirvió para probar el pipeline, pero **ya no alinea** contra la plantilla de
segunda vuelta (formato distinto: 2 candidatos en vez de 13). Para volver a
probar de punta a punta, coloca un par real de segunda vuelta:

```
datos/testigos/MUNICIPIO_ZONA_PUESTO_MESA_testigo.pdf
datos/registraduria/MUNICIPIO_ZONA_PUESTO_MESA_registraduria.pdf
```

**Convención de nombres:** `MUNICIPIO_ZONA_PUESTO_MESA` + sufijo de fuente. El
municipio es obligatorio porque zona/puesto/mesa se numeran **dentro de cada
municipio** — al procesar un departamento completo (varios municipios), dos
mesas de municipios distintos pueden compartir el mismo número de
zona_puesto_mesa, y sin el municipio el comparador las fusionaría por error.

| Archivo | `codigo_mesa` resultante |
|---------|--------------------------|
| `cartagena_21_01_13_testigo.pdf` | `cartagena_21_01_13` |
| `cartagena_21_01_13_registraduria.pdf` | `cartagena_21_01_13` |

El comparador cruza por ese mismo `codigo_mesa`. Ver `e14/mesa.py`.

**Plantilla:** coloca el PDF oficial en blanco de segunda vuelta en
`plantillas/muestra-formulario-e14-segunda-vuelta.pdf` (ver `e14/alineacion.py`
si el layout real no entra en una sola página).

### 5. Flujo recomendado: primero oficial, luego testigo

**Orden sugerido** (1 llamada API por script, sin bucles):

```bash
# Paso 1 — SOLO Registraduría (1 llamada OCR; acta de segunda vuelta = 1 sola página de votos)
python leer_registraduria.py datos/registraduria/cartagena_21_01_13_registraduria.pdf actas.db \
  --solo-pagina-1
# Al terminar imprime tabla de votos leídos y el siguiente comando

# Paso 2 — Ver qué quedó en la base SIN gastar más API
python ver_acta.py actas.db --fuente registraduria

# Paso 3 — Testigo (otra llamada OCR, cuando tengas cuota)
python leer_testigos.py datos/testigos/cartagena_21_01_13_testigo.pdf actas.db \
  --tipo claveros --solo-pagina-1

# Paso 4 — Comparar
python comparar.py actas.db comparacion_cartagena_21_01_13.xlsx
```

`--solo-pagina-1` = solo la página de candidatos/totales, sin la hoja de firmas (más
barato: 1 OCR por acta). Si solo cargaste la oficial y corres `comparar.py`, te muestra
el contenido de la Registraduría y avisa que falta el testigo.

### 6. Resultado esperado

Define aquí el resultado esperado de tu par de prueba real de segunda vuelta (c1, c2,
blanco, nulos, no_marcados) una vez lo proceses, para detectar regresiones futuras.
Si la API respondió bien, ambas fuentes deberían coincidir y el Excel no tendrá
discrepancias en esas columnas. Revisa la consola: cada acta muestra confianza, inliers
de alineación e informe OCR (`OK:` / `REVISAR:`).

### 7. Procesar carpetas completas

Cuando quieras todas las mesas emparejadas de una carpeta:

```bash
python leer_testigos.py datos/testigos actas.db --tipo claveros
python leer_registraduria.py datos/registraduria actas.db
python comparar.py actas.db comparacion_E14.xlsx
```

`comparar.py` lista al inicio qué pares existen en ambas carpetas y cuáles faltan.

### 8. Validación 100% local (sin API, sin cuota)

Para probar instalación y calidad del escaneo **sin gastar Gemini**:

```bash
# Solo capa 1: alinea, reporta inliers, guarda imagen en debug/
python validar_alineacion.py datos/registraduria/cartagena_21_01_13_registraduria.pdf --solo-pagina-1
python validar_alineacion.py datos/testigos/cartagena_21_01_13_testigo.pdf --solo-pagina-1

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
| Emparejamiento por mesa | `e14/mesa.py` | ✅ |
| Preprocesamiento OCR | `e14/preprocess.py` | ✅ |
| Almacén | `e14/almacen.py` (SQLite) | ✅ |

Pendiente: app Windows, DB en nube, recorte por casilla (ver `PLAN_PASO_A_PASO.md`).

---

## Estructura del repo

```
e14/                    paquete con la lógica
  modelo.py             contrato ActaE14 + 2 candidatos (segunda vuelta)
  almacen.py            SQLite (actas.db)
  mesa.py               código municipio_zona_puesto_mesa y emparejamiento
  alineacion.py         CAPA 1: SIFT + homografía vs plantilla
  preprocess.py         recorte de negro, zoom, CLAHE antes del OCR
  ocr.py                CAPA 2: Gemini / GPT / manual
  evidencia.py          detectar copias visibles en la foto
  lectura.py            PDF → ActaE14 (une capas 1 y 2)
  comparador.py         CAPA 3: lógica de comparación
leer_testigos.py        SCRIPT 1: testigo (CSV o PDF) → tabla
leer_registraduria.py   SCRIPT 2: oficial PDF → tabla
comparar.py             SCRIPT 3: cruza fuentes → Excel
probar_api.py           ping mínimo a Gemini/GPT
cli_args.py             flags --tipo, --codigo, --solo-pagina-1
plantillas/             E-14 en blanco oficial de segunda vuelta (alineación)
datos/
  testigos/             E-14 del testigo (par de prueba 21_01_13 es de primera vuelta)
  registraduria/        E-14 oficial (idem)
ejemplos/               CSV de ejemplo
```

---

## Convención de archivos (importante)

**Formato recomendado:**

```
datos/testigos/MUNICIPIO_ZONA_PUESTO_MESA_testigo.pdf
datos/registraduria/MUNICIPIO_ZONA_PUESTO_MESA_registraduria.pdf
```

Ejemplo: `cartagena_21_01_13_testigo.pdf` ↔ `cartagena_21_01_13_registraduria.pdf` →
mesa `cartagena_21_01_13`.

El municipio es obligatorio (no solo zona_puesto_mesa) porque, al procesar un
departamento completo, la numeración de zona/puesto/mesa se repite entre
municipios distintos — sin el municipio en la clave, el comparador fusionaría
mesas de lugares distintos que comparten el mismo número.

**No uses** nombres largos tipo `88-128-15-85-001.pdf` salvo que declares `--codigo`
manualmente: el parser espera el municipio seguido de tres segmentos numéricos
(zona, puesto, mesa).

---

## Flags de los lectores

| Flag | Uso |
|------|-----|
| `--tipo claveros\|delegados\|transmision` | De qué **copia** del E-14 se leyeron los votos |
| `--codigo cartagena_21_01_13` | Forzar código de mesa (un solo archivo) |
| `--solo-pagina-1` / `--solo-p1` | Solo la página de candidatos/totales (sin firmas); 1 OCR por acta |
| `[actas.db]` | Base SQLite de salida (default: `actas.db`) |

Por defecto: testigos sin `--tipo` → `desconocido`; registraduría → `delegados`.

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
