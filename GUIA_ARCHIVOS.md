# Guía de archivos del proyecto `auditoria-e14`

Mapa de **para qué sirve cada archivo**. Tres scripts que ejecutas tú, un paquete `e14/`
con la lógica, carpetas de datos y documentación.

**Para reproducir el proyecto desde cero**, sigue la sección *Guía de reproducción* en
`README.md` (instalación, `.env`, par `21_01_13`, comandos esperados).

---

## Vista rápida (árbol)

```
auditoria-e14/
├── 📄 Documentación
│   ├── README.md                 → Instalación + guía de reproducción paso a paso
│   ├── GUIA_ARCHIVOS.md          → Este archivo
│   ├── VISION_Y_DECISIONES.md    → Por qué se diseñó así (API, capas, costos)
│   └── PLAN_PASO_A_PASO.md       → Roadmap y tareas pendientes
│
├── ▶️ Scripts que TÚ ejecutas
│   ├── leer_testigos.py          → Paso 1: E-14 de testigos (CSV o PDF/OCR)
│   ├── leer_registraduria.py     → Paso 2: E-14 oficial (PDF + OCR)
│   ├── comparar.py               → Paso 3: cruzar y generar Excel
│   ├── probar_api.py             → Verificar clave Gemini/GPT antes de OCR masivo
│   ├── ver_acta.py               → Ver actas.db sin re-OCR (sin API)
│   ├── validar_alineacion.py     → Solo capa 1 local: inliers + debug/
│   └── cli_args.py               → Flags: --tipo, --codigo, --solo-pagina-1
│
├── 📦 e14/  (motor — no se ejecuta directo)
│   ├── modelo.py                 → ActaE14, candidatos, tipo_acta, copias_en_evidencia
│   ├── almacen.py                → SQLite (actas.db)
│   ├── mesa.py                   → Código zona_puesto_mesa y emparejamiento de carpetas
│   ├── alineacion.py             → Capa 1: SIFT + homografía vs plantilla
│   ├── preprocess.py             → Recorte negro, zoom, CLAHE antes del OCR
│   ├── ocr.py                    → Capa 2: Gemini / GPT / manual + informe API
│   ├── evidencia.py              → Detectar copias visibles (Claveros, Delegados…)
│   ├── lectura.py                → Orquesta evidencia + alineación + OCR → ActaE14
│   ├── informe.py                → Tabla legible de votos en consola
│   ├── comparador.py             → Capa 3: comparar (estados SIN_LECTURA, etc.)
│   └── __init__.py
│
├── 📁 Entradas
│   ├── datos/testigos/           → PDF/fotos del testigo
│   │   └── 21_01_13_testigo.pdf  → ✅ Par de prueba (sí va al git)
│   ├── datos/registraduria/      → PDF oficiales
│   │   └── 21_01_13_registraduria.pdf → ✅ Par de prueba (sí va al git)
│   ├── plantillas/               → E-14 en blanco (referencia alineación)
│   └── ejemplos/                 → CSV de ejemplo
│
└── ⚙️ Configuración
    ├── requirements.txt
    ├── .env.example              → Plantilla de claves (copiar a .env)
    ├── .env                      → Claves reales (NO subir)
    └── .gitignore
```

---

## Los 3 scripts principales

| Archivo | Qué hace |
|---------|----------|
| **`leer_testigos.py`** | **Paso 1.** CSV con números o PDF/foto del E-14 del testigo → `actas.db` (`fuente='testigo'`). Flags: `--tipo`, `--solo-pagina-1`. |
| **`leer_registraduria.py`** | **Paso 2.** PDF oficial → alineación → OCR Gemini → `actas.db` (`fuente='registraduria'`). Por defecto `--tipo delegados`. |
| **`comparar.py`** | **Paso 3.** Cruza por `codigo_mesa`, imprime pares disponibles en carpetas, genera Excel (Resumen, Comparación, Discrepancias, Trazabilidad E-14). |

### Comandos con el par de prueba incluido

```bash
python probar_api.py
python leer_testigos.py datos/testigos/21_01_13_testigo.pdf actas.db --tipo claveros --solo-pagina-1
python leer_registraduria.py datos/registraduria/21_01_13_registraduria.pdf actas.db --solo-pagina-1
python comparar.py actas.db comparacion_21_01_13.xlsx
```

Votos esperados en pág. 1: **c1=130, c2=3, c4=77** (resto 0).

---

## Utilidades en la raíz

| Archivo | Qué hace |
|---------|----------|
| **`probar_api.py`** | Llamada mínima a Gemini/GPT. Correr **siempre** antes del primer OCR masivo. |
| **`cli_args.py`** | Parsea: `entrada`, `actas.db`, `--codigo`, `--tipo`, `--solo-pagina-1` / `--solo-p1`. |

---

## Paquete `e14/` (capas)

| Archivo | Capa | Qué hace |
|---------|------|----------|
| **`modelo.py`** | Contrato | `ActaE14`: mesa, votos c1–c13, `tipo_acta`, `copias_en_evidencia`, confianza. |
| **`almacen.py`** | DB | SQLite `actas.db`; clave `(codigo_mesa, fuente)`. |
| **`mesa.py`** | Emparejamiento | `21_01_13_testigo.pdf` → código `21_01_13`; `pares_disponibles()` entre carpetas. |
| **`alineacion.py`** | **1** | PDF → gris; SIFT + homografía vs `plantillas/muestra-formulario-e-14.pdf`. Layouts: `candidatos_1_7`, `candidatos_8_13`, `firmas`. Parámetro `solo_layouts` para forzar uno. |
| **`preprocess.py`** | Pre-OCR | `recortar_margenes_negros()` (PDF alto → mucho negro tras alinear), `mejorar_para_ocr()` (CLAHE + zoom). |
| **`ocr.py`** | **2** | Gemini (recomendado), GPT, manual. Prompt para puntos como ceros (`..3`→3). Reintentos 429. Campo `detalle_api` en notas. |
| **`evidencia.py`** | Trazabilidad | Qué copias aparecen en la foto. PDF oficial: lee título pág. 1; fotos testigo: Gemini o heurística de layout. |
| **`lectura.py`** | Orquestador | `leer_acta_pdf()`: evidencia → capa 1 → preprocess → OCR (+ re-OCR zoom si faltan casillas). Con `layouts` activo, solo procesa **página 1** del PDF. |
| **`comparador.py`** | **3** | Discrepancias columna a columna; alertas por copias múltiples en evidencia. |

---

## Documentación

| Archivo | Contenido |
|---------|-----------|
| **`README.md`** | **Empezar aquí.** Reproducción completa, flags, troubleshooting, convención de nombres. |
| **`GUIA_ARCHIVOS.md`** | Este mapa. |
| **`VISION_Y_DECISIONES.md`** | Decisiones de diseño y costos. |
| **`PLAN_PASO_A_PASO.md`** | Estado y pendientes (Windows, nube, recorte por casilla). |

---

## Carpetas de datos

| Ruta | Contenido | ¿Va al git? |
|------|-----------|-------------|
| **`datos/testigos/`** | Evidencia del testigo electoral | Carpeta sí (`.gitkeep`). PDFs: solo `21_01_13_testigo.pdf` (whitelist). |
| **`datos/registraduria/`** | PDF oficial Registraduría | Igual: solo `21_01_13_registraduria.pdf` en whitelist. |
| **`plantillas/`** | E-14 en blanco oficial | Sí |
| **`ejemplos/ejemplo_testigos.csv`** | CSV demo (código `88-128-15-85-001`, formato legacy) | Sí |

### Convención de nombres (usar esta)

```
ZONA_PUESTO_MESA_testigo.pdf
ZONA_PUESTO_MESA_registraduria.pdf
```

El sufijo `_testigo` / `_registraduria` se quita para obtener `codigo_mesa`. Ver
`e14/mesa.py` → `codigo_mesa_desde_archivo()`.

---

## Configuración y artefactos generados

| Archivo | Qué es |
|---------|--------|
| **`requirements.txt`** | opencv-python-headless, PyMuPDF, numpy, openpyxl, requests |
| **`.env.example`** | Plantilla: `OCR_BACKEND`, `GEMINI_API_KEY`, `GEMINI_MODEL`, etc. |
| **`.env`** | Claves reales — **nunca** al git |
| **`actas.db`** | Generado por los lectores |
| **`comparacion_*.xlsx`** | Generado por `comparar.py` |
| **`debug/`** | Imágenes de depuración local (ignorado por git) |

---

## Campos clave en SQLite

| Campo | Significado |
|-------|-------------|
| **`codigo_mesa`** | Clave de cruce, ej. `21_01_13` |
| **`fuente`** | `testigo` o `registraduria` |
| **`tipo_acta`** | Copia de la que se **leyeron** los votos |
| **`copias_en_evidencia`** | Copias **visibles** en la imagen |
| **`confianza`** | Mínimo de confianzas OCR de la acta (0–1) |
| **`necesita_revision`** | 1 si hay que revisar a mano |
| **`notas`** | Alineación (inliers), informe API, alertas trazabilidad |

---

## ¿Qué archivo toco si quiero…?

| Objetivo | Archivo |
|----------|---------|
| Cambiar candidatos | `e14/modelo.py` |
| Convención de nombres de archivo | `e14/mesa.py` |
| Mejorar enderezado | `e14/alineacion.py` |
| Mejorar imagen antes del OCR | `e14/preprocess.py` |
| Prompt / API / reintentos OCR | `e14/ocr.py` |
| Detección Claveros/Delegados en foto | `e14/evidencia.py` |
| Flujo PDF completo | `e14/lectura.py` |
| Columnas del Excel | `comparar.py` |
| Nueva columna en DB | `e14/modelo.py` + `e14/almacen.py` |
| Documentar reproducción | `README.md` |

---

*Última actualización: emparejamiento por mesa, preprocess OCR, par de prueba 21_01_13, modo `--solo-pagina-1`.*
