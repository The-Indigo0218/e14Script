# Auditoría de actas E-14 — Presidenciales Colombia 2026

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

### 4. Par de prueba incluido en el repo

El commit trae un par real de Cartagena (zona 21, puesto 01, mesa 13):

```
datos/testigos/21_01_13_testigo.pdf          ← foto del testigo (2 copias: Claveros + Delegados)
datos/registraduria/21_01_13_registraduria.pdf  ← PDF oficial (3 páginas, copia Delegados)
```

**Convención de nombres:** `ZONA_PUESTO_MESA` + sufijo de fuente:

| Archivo | `codigo_mesa` resultante |
|---------|--------------------------|
| `21_01_13_testigo.pdf` | `21_01_13` |
| `21_01_13_registraduria.pdf` | `21_01_13` |

El comparador cruza por ese mismo `codigo_mesa`. Ver `e14/mesa.py`.

### 5. Correr el flujo completo (modo prueba barato)

`--solo-pagina-1` procesa **solo candidatos 1–7** (1 llamada OCR por acta). Ideal para
validar el pipeline sin gastar cuota.

```bash
# Paso 1 — testigo (copia Claveros en la foto)
python leer_testigos.py datos/testigos/21_01_13_testigo.pdf actas.db \
  --tipo claveros --solo-pagina-1

# Paso 2 — Registraduría (copia Delegados)
python leer_registraduria.py datos/registraduria/21_01_13_registraduria.pdf actas.db \
  --solo-pagina-1

# Paso 3 — comparar
python comparar.py actas.db comparacion_21_01_13.xlsx
```

### 6. Resultado esperado (pág. 1, candidatos 1–7)

| Campo | Valor esperado |
|-------|----------------|
| c1 (Cepeda) | 130 |
| c2 (Claudia López) | 3 |
| c4 (Abelardo) | 77 |
| c3, c5, c6, c7 | 0 |

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

### 8. Sin clave API (solo probar el flujo)

Sin `GEMINI_API_KEY`, los lectores usan el backend **manual**: alinean el PDF pero dejan
los votos en `null` y marcan `REVISAR`. Sirve para verificar instalación y capa 1 sin red.

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
  modelo.py             contrato ActaE14 + 13 candidatos
  almacen.py            SQLite (actas.db)
  mesa.py               código zona_puesto_mesa y emparejamiento
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
plantillas/             E-14 en blanco oficial (alineación)
datos/
  testigos/             E-14 del testigo (incluye par de prueba 21_01_13)
  registraduria/        E-14 oficial (incluye par de prueba 21_01_13)
ejemplos/               CSV de ejemplo
```

---

## Convención de archivos (importante)

**Formato recomendado:**

```
datos/testigos/ZONA_PUESTO_MESA_testigo.pdf
datos/registraduria/ZONA_PUESTO_MESA_registraduria.pdf
```

Ejemplo: `21_01_13_testigo.pdf` ↔ `21_01_13_registraduria.pdf` → mesa `21_01_13`.

**No uses** nombres largos tipo `88-128-15-85-001.pdf` salvo que declares `--codigo`
manualmente: el parser de zona/puesto/mesa espera tres segmentos numéricos.

---

## Flags de los lectores

| Flag | Uso |
|------|-----|
| `--tipo claveros\|delegados\|transmision` | De qué **copia** del E-14 se leyeron los votos |
| `--codigo 21_01_13` | Forzar código de mesa (un solo archivo) |
| `--solo-pagina-1` / `--solo-p1` | Solo candidatos 1–7; 1 OCR por acta; más barato |
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
| `HTTP 429` en `probar_api.py` | Cuota Gemini agotada | Esperar; no reintentar en bucle |
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
- PDFs en `datos/` **excepto** el par de prueba `21_01_13_*` (whitelist en `.gitignore`)
