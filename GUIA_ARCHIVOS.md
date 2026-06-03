# Guía de archivos del proyecto `auditoria-e14`

Mapa de **para qué sirve cada archivo** en este repositorio. Si ves muchos nombres, la idea es simple: **3 scripts que ejecutas tú**, un **paquete `e14/`** con la lógica, **carpetas de datos** y **documentación**.

---

## Vista rápida (árbol)

```
auditoria-e14/
├── 📄 Documentación (léelos para contexto)
│   ├── README.md                 → Cómo instalar y correr el proyecto
│   ├── GUIA_ARCHIVOS.md          → Este archivo
│   ├── VISION_Y_DECISIONES.md    → Por qué se diseñó así (API, capas, costos)
│   └── PLAN_PASO_A_PASO.md       → Roadmap técnico pendiente
│
├── ▶️ Scripts que TÚ ejecutas (3 pasos + 1 utilidad)
│   ├── leer_testigos.py          → Paso 1: cargar E-14 de jurados/testigos
│   ├── leer_registraduria.py     → Paso 2: leer E-14 oficial (PDF/foto + OCR)
│   ├── comparar.py               → Paso 3: cruzar y generar Excel
│   ├── probar_api.py             → Verificar que la clave Gemini/GPT funciona
│   └── cli_args.py               → Ayuda interna: leer --tipo, --codigo, etc.
│
├── 📦 e14/  (motor del sistema — no hace falta ejecutarlo directo)
│   ├── modelo.py                 → Contrato de datos (ActaE14, candidatos, copias)
│   ├── almacen.py                → Base SQLite (actas.db)
│   ├── alineacion.py             → Capa 1: enderezar el escaneo con la plantilla
│   ├── ocr.py                    → Capa 2: leer dígitos (Gemini / GPT / manual)
│   ├── evidencia.py              → Detectar copias visibles (Claveros, Delegados…)
│   ├── lectura.py                → Une capa 1 + 2 en un solo flujo PDF→ActaE14
│   ├── comparador.py             → Lógica de comparar testigo vs oficial
│   └── __init__.py               → Marca el paquete Python
│
├── 📁 Entradas y referencias
│   ├── datos/testigos/           → Aquí van fotos/PDF del testigo (no van al git)
│   ├── datos/registraduria/      → Aquí van PDF oficiales (no van al git)
│   ├── plantillas/               → E-14 en blanco oficial (para alinear)
│   └── ejemplos/                 → CSV de prueba + foto de referencia
│
└── ⚙️ Configuración
    ├── requirements.txt          → Dependencias Python
    ├── .env.example              → Plantilla de claves API (copiar a .env)
    ├── .env                      → Tus claves (local, NO subir a git)
    └── .gitignore                → Qué ignorar (venv, claves, actas reales)
```

---

## Los 3 scripts principales (flujo de trabajo)

| Archivo | ¿Lo ejecutas? | Qué hace |
|---------|---------------|----------|
| **`leer_testigos.py`** | Sí | **Paso 1.** Toma la evidencia de los jurados: un **CSV** con números o **PDF/fotos** del E-14. Guarda en `actas.db` con `fuente='testigo'`. Registra **qué copias aparecen en la foto** y **de cuál se leyeron los votos** (`--tipo claveros`, etc.). |
| **`leer_registraduria.py`** | Sí | **Paso 2.** Procesa el E-14 **oficial** (carpeta `datos/registraduria/`). Alinea la imagen, pasa OCR (Gemini si hay clave) y guarda con `fuente='registraduria'`. Por defecto asume ejemplar **Delegados**. |
| **`comparar.py`** | Sí | **Paso 3.** Lee `actas.db`, compara mesa por mesa testigo vs oficial, imprime resumen y genera **`comparacion_E14.xlsx`** (hojas Resumen, Comparación, Discrepancias, **Trazabilidad E-14**). |

Orden típico:

```bash
python leer_testigos.py datos/testigos actas.db --tipo claveros
python leer_registraduria.py datos/registraduria actas.db
python comparar.py actas.db comparacion_E14.xlsx
```

---

## Utilidades en la raíz

| Archivo | Qué hace |
|---------|----------|
| **`probar_api.py`** | Hace una llamada mínima a Gemini o GPT para confirmar que `GEMINI_API_KEY` en `.env` está bien **antes** de procesar cientos de actas. |
| **`cli_args.py`** | Código compartido para interpretar argumentos: `entrada`, `actas.db`, `--codigo MESA`, `--tipo claveros\|delegados\|transmision`. Lo usan los dos lectores; no lo ejecutas solo. |

---

## Paquete `e14/` (lógica interna)

Piensa en esto como **capas**. Los scripts de arriba solo orquestan; el trabajo pesado está aquí.

| Archivo | Capa | Qué hace |
|---------|------|----------|
| **`modelo.py`** | Contrato | Define **`ActaE14`**: código de mesa, votos c1–c13, blanco/nulos, **`tipo_acta`** (copia de la que se leyeron votos), **`copias_en_evidencia`** (qué copias salen en la foto). Lista de los 13 candidatos de primera vuelta. |
| **`almacen.py`** | Base de datos | Guarda y lee actas en **`actas.db`** (SQLite). Una fila por `(mesa, fuente)`. |
| **`alineacion.py`** | **Capa 1** | Convierte PDF/foto a imagen, la **endereza** contra `plantillas/muestra-formulario-e-14.pdf` (SIFT + homografía). Sin esto el OCR falla si la foto está torcida. |
| **`ocr.py`** | **Capa 2** | Lee los números manuscritos. Backends: **Gemini** (recomendado), **GPT**, o **manual** (sin clave, no lee nada). Umbral 80 % → revisión humana. |
| **`evidencia.py`** | Trazabilidad | Detecta si en la foto del jurado aparecen **Claveros**, **Delegados** y/o **Transmisión** (texto del PDF, Gemini o heurística de layout). |
| **`lectura.py`** | Orquestador | Une evidencia + alineación + OCR en **`leer_acta_pdf()`**. Acepta PDF, JPG, PNG. Imprime el resumen 📷 en consola. |
| **`comparador.py`** | **Capa 3** | Compara dos filas de la misma mesa columna por columna; arma alertas si hay varias copias en la foto del testigo. |
| **`__init__.py`** | Paquete | Versión del módulo (`0.1.0`). |

---

## Documentación

| Archivo | Para quién | Contenido |
|---------|------------|-----------|
| **`README.md`** | Todos | Instalación, `.env`, uso con Gemini Flash gratis, carpetas `datos/`, criterios de revisión. |
| **`GUIA_ARCHIVOS.md`** | Todos | Este mapa de archivos. |
| **`VISION_Y_DECISIONES.md`** | Equipo / IA | Objetivo del auditor, por qué leer el E-14 directo, Gemini vs GPT, costos Cartagena. |
| **`PLAN_PASO_A_PASO.md`** | Desarrollo | Estado del proyecto y tareas pendientes (app Windows, nube, etc.). |

---

## Carpetas de datos (entrada y salida)

| Carpeta / archivo | Qué pones ahí | ¿Va al git? |
|-------------------|---------------|-------------|
| **`datos/testigos/`** | Fotos o PDF que envía el **testigo electoral** (evidencia jurados). Mismo nombre = mismo código de mesa que en registraduría. | Solo la carpeta vacía (`.gitkeep`). Los PDF/fotos **no** (privacidad). |
| **`datos/registraduria/`** | PDF del E-14 **oficial** publicado por la Registraduría. | Igual: carpetas sí, actas no. |
| **`plantillas/muestra-formulario-e-14.pdf`** | Formulario E-14 **en blanco** oficial. Referencia fija para alinear cualquier escaneo. | Sí (es plantilla pública de muestra). |
| **`ejemplos/ejemplo_testigos.csv`** | CSV de ejemplo con columnas `tipo_acta` y `copias_en_evidencia`. | Sí. |
| **`ejemplos/actas_reales/`** | Foto de referencia (ej. Cartagena zona 21 mesa 013) para probar detección de copias. | Sí (imagen de ejemplo). |

---

## Configuración y archivos generados al correr

| Archivo | Qué es |
|---------|--------|
| **`requirements.txt`** | Lista de librerías: OpenCV, PyMuPDF, numpy, openpyxl, requests. |
| **`.env.example`** | Plantilla: `OCR_BACKEND`, `GEMINI_API_KEY`, `GEMINI_MODEL`. |
| **`.env`** | Tus claves reales. **Nunca** subir a git. |
| **`.gitignore`** | Excluye `.venv/`, `.env`, `*.db`, `*.xlsx`, actas en `datos/`. |
| **`.venv/`** | Entorno virtual Python (se crea con `python -m venv .venv`). No va al git. |
| **`actas.db`** | Base de datos que crean los lectores. Se genera al correr; no va al git. |
| **`comparacion_E14.xlsx`** | Reporte Excel que crea `comparar.py`. No va al git. |

---

## Campos importantes en la base (para no confundirse)

| Campo en `ActaE14` / SQLite | Significado |
|-----------------------------|-------------|
| **`fuente`** | `testigo` o `registraduria` — de dónde viene el registro en el flujo. |
| **`copias_en_evidencia`** | Copias que **se ven** en la foto (`claveros,delegados` = 2 copias en la misma imagen). |
| **`tipo_acta`** | Copia **de la que se tomaron los votos** que guardamos (ej. solo Claveros). |

Si la foto tiene Claveros y Delegados pero los votos los leyeron solo de Claveros, queda registrado así — sirve para detectar si alguien cambió números entre copias.

---

## ¿Qué archivo toco si quiero…?

| Quiero… | Archivo |
|---------|---------|
| Cambiar lista de candidatos | `e14/modelo.py` |
| Mejorar enderezado de fotos torcidas | `e14/alineacion.py` |
| Cambiar prompt o API de OCR | `e14/ocr.py` |
| Mejorar detección Claveros/Delegados en foto | `e14/evidencia.py` |
| Cambiar columnas del Excel | `comparar.py` |
| Añadir columna nueva a la DB | `e14/modelo.py` + `e14/almacen.py` |
| Solo documentar una decisión | `VISION_Y_DECISIONES.md` |

---

*Última actualización: trazabilidad de ejemplares E-14 (Claveros / Delegados / Transmisión) en evidencia jurados.*
