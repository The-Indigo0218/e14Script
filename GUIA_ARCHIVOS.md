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
│   ├── auditar.py                → ORQUESTADOR: audita un lote (municipio) de punta a punta
│   ├── cobertura.py              → Tablero de cobertura / detalle de un lote (sin OCR)
│   ├── leer_testigos.py          → E-14 de testigos (CSV o PDF/OCR)
│   ├── leer_registraduria.py     → E-14 oficial (PDF + OCR)
│   ├── comparar.py               → Cruzar y generar Excel
│   ├── probar_api.py             → Verificar clave Gemini/GPT antes de OCR masivo
│   ├── ver_acta.py               → Ver actas.db sin re-OCR (sin API)
│   ├── validar_alineacion.py     → Solo capa 1 local: inliers + debug/
│   └── cli_args.py               → Flags: --tipo, --codigo, --solo-pagina-1
│
├── 📦 e14/  (motor — no se ejecuta directo)
│   ├── modelo.py                 → ActaE14, 2 candidatos (segunda vuelta), tipo_acta, copias_en_evidencia
│   ├── almacen.py                → SQLite (actas.db) + historial de re-auditoría
│   ├── mesa.py                   → Nomenclatura NuMunicipio_zona_puesto_mesa, código canónico, emparejamiento
│   ├── catalogo.py               → Excel "Mesa a Mesa" → universo de mesas por municipio
│   ├── cobertura.py              → Cruza catálogo vs archivos presentes (estados del lote)
│   ├── alineacion.py             → Capa 1: SIFT + homografía vs plantilla
│   ├── preprocess.py             → Recorte negro, zoom, CLAHE antes del OCR
│   ├── ocr.py                    → Capa 2: Gemini / GPT / manual + informe API
│   ├── evidencia.py              → Detectar copias visibles (Claveros, Delegados…)
│   ├── lectura.py                → Orquesta evidencia + alineación + OCR → ActaE14
│   ├── informe.py                → Tabla legible de votos en consola
│   ├── comparador.py             → Capa 3: comparar (estados SIN_LECTURA, etc.)
│   └── __init__.py
│
├── 🧪 tests/  (pytest)
│   ├── conftest.py               → Fixtures: Excel sintético + lote de prueba
│   ├── test_mesa.py              → Nomenclatura canónica
│   ├── test_catalogo.py          → Lectura del Excel (universo, nombres, mojibake)
│   ├── test_cobertura.py         → Estados del lote
│   ├── test_auditar.py           → Orquestador (lector falso, sin OCR)
│   └── test_almacen.py           → Persistencia + versionado de re-auditoría
│
├── 📁 Entradas
│   ├── datos/<NN_nombre>/        → un LOTE = un municipio (ej. 01_cartagena/)
│   │   ├── testigos/             → PDF/fotos del testigo del municipio
│   │   └── registraduria/        → PDF oficiales del municipio
│   ├── datos/testigos/           → (legacy) par de prueba 21_01_13_testigo.pdf (sí va al git)
│   ├── datos/registraduria/      → (legacy) 21_01_13_registraduria.pdf (sí va al git)
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

## Flujo por lote (camino recomendado)

Un **lote = un municipio**. El Excel "Mesa a Mesa" de la Registraduría es el catálogo.

| Archivo | Qué hace |
|---------|----------|
| **`cobertura.py`** | Lee el catálogo (Excel) y dice, por municipio, cuántas mesas hay y cuántas están **listas** (testigo + oficial). Tablero del departamento o detalle de un lote; `--crear-carpetas` arma `datos/<NN_nombre>/`. No gasta OCR. |
| **`auditar.py`** | **Orquestador.** Para un `--municipio`: calcula cobertura, selecciona las mesas listas, las lee con el pipeline (Capa 1 + OCR), guarda con código canónico y genera el Excel de comparación. `--plan`, `--limite`, `--reauditar`, `--incluir-parciales`. |

```bash
python cobertura.py "ruta/al/…Mesa_Mesa…xlsx"                      # tablero depto
python cobertura.py "ruta/al/…xlsx" --municipio 1 --crear-carpetas  # arma carpetas del lote
python auditar.py  "ruta/al/…xlsx" --municipio 1 --plan             # qué se procesaría (sin OCR)
python auditar.py  "ruta/al/…xlsx" --municipio 1 --solo-pagina-1    # auditar el lote
```

## Los scripts de bajo nivel (un archivo a la vez)

`auditar.py` los reutiliza por dentro; también sirven sueltos.

| Archivo | Qué hace |
|---------|----------|
| **`leer_testigos.py`** | CSV con números o PDF/foto del E-14 del testigo → `actas.db` (`fuente='testigo'`). Flags: `--tipo`, `--solo-pagina-1`. |
| **`leer_registraduria.py`** | PDF oficial → alineación → OCR Gemini → `actas.db` (`fuente='registraduria'`). Por defecto `--tipo delegados`. |
| **`comparar.py`** | Cruza por `codigo_mesa`, imprime pares disponibles en carpetas, genera Excel (Resumen, Comparación, Discrepancias, Trazabilidad E-14). |

### Comandos con el par de prueba (legacy) incluido

```bash
python probar_api.py
python leer_testigos.py datos/testigos/21_01_13_testigo.pdf actas.db --tipo claveros --solo-pagina-1
python leer_registraduria.py datos/registraduria/21_01_13_registraduria.pdf actas.db --solo-pagina-1
python comparar.py actas.db comparacion_21_01_13.xlsx
```

Votos esperados en pág. 1: **c1=130, c2=3, c4=77** (resto 0). El par `21_01_13` es
legacy (sin `NuMunicipio` ni carpeta de lote); para datos reales usa el flujo por lote.

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
| **`almacen.py`** | DB | SQLite `actas.db`; clave `(codigo_mesa, fuente)`. Tabla `actas_historial`: versiones anteriores al re-auditar (`historial()`, `num_versiones()`). |
| **`mesa.py`** | Nomenclatura | `1_21_01_13_testigo.pdf` → código canónico `1_21_1_13` (`codigo_canonico`, `normalizar_codigo`); `pares_disponibles()` y `mapa_codigo_archivo()` entre carpetas. |
| **`catalogo.py`** | Catálogo | Lee el Excel "Mesa a Mesa" → `Catalogo`: universo de mesas por municipio, `MUN→nombre` (códigos Registraduría, repara mojibake), `crear_estructura_lote()`. |
| **`cobertura.py`** | Cobertura | `cobertura_lote()` cruza catálogo vs archivos: listas / solo_testigo / solo_registraduria / faltan_ambas / fuera_de_catalogo. |
| **`alineacion.py`** | **1** | PDF → gris; SIFT + homografía vs `plantillas/muestra-formulario-e14-segunda-vuelta.pdf`. Layouts: `acta_completa` (2 candidatos + totales, 1 página), `firmas`. Parámetro `solo_layouts` para forzar uno. |
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
<NuMunicipio>_<ZONA>_<PUESTO>_<MESA>_testigo.pdf
<NuMunicipio>_<ZONA>_<PUESTO>_<MESA>_registraduria.pdf
```

- **`NuMunicipio`** = número de municipio de la **Registraduría** (columna `MUN` del
  Excel catálogo, **no** DANE). Va primero porque zona/puesto/mesa se numeran dentro de
  cada municipio; sin él se fusionarían mesas de municipios distintos con el mismo número.
- Los **ceros a la izquierda no importan**: `1_21_01_13` ≡ `1_21_1_13` (código canónico),
  así el archivo cruza con el catálogo.

El sufijo `_testigo` / `_registraduria` se quita para obtener el código. Ver
`e14/mesa.py` → `codigo_mesa_desde_archivo()`, `normalizar_codigo()`,
`municipio_zona_puesto_mesa_desde_codigo()`. ⚠️ Codificación Registraduría: Bolívar = 5
y los municipios **no son consecutivos** (Cartagena = 1, Magangué = 28, Mompós = 43…).

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
| **`codigo_mesa`** | Clave de cruce (canónica), ej. `1_21_1_13` (`NuMunicipio_zona_puesto_mesa`) |
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
| Nomenclatura / código canónico de mesa | `e14/mesa.py` |
| Lectura del Excel catálogo (universo, nombres) | `e14/catalogo.py` |
| Estados/cobertura del lote | `e14/cobertura.py` |
| Orquestación de un lote (selección, límite, re-auditar) | `auditar.py` |
| Mejorar enderezado | `e14/alineacion.py` |
| Mejorar imagen antes del OCR | `e14/preprocess.py` |
| Prompt / API / reintentos OCR | `e14/ocr.py` |
| Detección Claveros/Delegados en foto | `e14/evidencia.py` |
| Flujo PDF completo | `e14/lectura.py` |
| Columnas del Excel | `comparar.py` |
| Nueva columna en DB / historial re-auditoría | `e14/modelo.py` + `e14/almacen.py` |
| Documentar reproducción | `README.md` |

---

*Última actualización: catálogo desde Excel, nomenclatura numérica `NuMunicipio_zona_puesto_mesa`, cobertura y orquestador por lote (`auditar.py`), versionado de re-auditoría, suite de tests.*
