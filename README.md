# Auditoría de actas E-14 — Presidenciales Colombia 2026

Herramienta para **leer actas E-14** (oficial de la Registraduría y la del testigo
electoral), pasarlas a una tabla común y **comparar** para detectar discrepancias.
Todo lo dudoso (confianza < 80%, suma que no cuadra o fuentes que difieren) se
**marca para revisión humana**.

> 📄 Lee primero `VISION_Y_DECISIONES.md` (el porqué), `PLAN_PASO_A_PASO.md` (el cómo) y
> **`GUIA_ARCHIVOS.md`** (qué hace cada archivo del repo).

## Estado

Listo para **solo conectar la API de OCR**. Sin clave funciona en modo "manual"
(no lee dígitos, marca todo para revisión) para poder probar el flujo completo.

| Capa | Archivo | Estado |
|---|---|---|
| 1. Alineación por plantilla | `e14/alineacion.py` | ✅ |
| 2. OCR (Gemini/GPT) | `e14/ocr.py` | ✅ listo, falta poner la clave |
| 3. Comparación | `e14/comparador.py`, `comparar.py` | ✅ |
| 4. Validación (suma/confianza) | en los lectores | ✅ |
| Almacén | `e14/almacen.py` (SQLite) | ✅ |

## Estructura

```
e14/                paquete con la lógica
  modelo.py         contrato de datos (ActaE14 + 13 candidatos)
  almacen.py        base de datos SQLite
  alineacion.py     CAPA 1: alineación contra la plantilla oficial
  ocr.py            CAPA 2: backends Gemini / GPT / manual
  comparador.py     CAPA 3: lógica de comparación
  lectura.py        lectura compartida PDF → ActaE14 (la usan ambos lectores)
leer_testigos.py        SCRIPT 1: E-14 del testigo (CSV o PDF/OCR) → tabla
leer_registraduria.py   SCRIPT 2: PDF oficial → capa1 → OCR → tabla
comparar.py             SCRIPT 3: cruza fuentes → Excel de discrepancias
probar_api.py           verifica que la clave del .env funcione (ping mínimo)
plantillas/             plantilla oficial en blanco del E-14
datos/
  registraduria/        coloca aquí los E-14 OFICIALES en PDF
  testigos/             coloca aquí los E-14 de TESTIGOS en PDF (o usa un CSV)
ejemplos/               datos de ejemplo (CSV de testigos)
```

> Nombra cada PDF con el **código de mesa** (ej. `88-128-15-85-001.pdf`) e igual en
> ambas carpetas, para que la comparación cruce la misma mesa.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Probar GRATIS con Gemini Flash (antes de pagar nada)

Gemini tiene **capa gratuita** en Google AI Studio. Sirve para validar el flujo con
unas pocas actas sin gastar.

1. Saca una clave gratis en https://aistudio.google.com/apikey
2. Pégala en el archivo `.env` (ya creado):

```bash
GEMINI_API_KEY=AIza...tu_clave...
```

3. Verifica que la clave responde:

```bash
python probar_api.py        # debe decir: ✅ La API respondió correctamente
```

El modelo por defecto es `gemini-2.5-flash` (rápido y dentro de la capa gratis).
La fábrica `crear_backend()` detecta la clave automáticamente; nada más cambia.

## Uso (prueba con 2 actas)

Pon un E-14 en cada carpeta con el **mismo nombre = código de mesa**:
`datos/registraduria/88-128-15-85-001.pdf` y `datos/testigos/88-128-15-85-001.pdf`.

```bash
# 1) E-14 de testigos (carpeta de PDFs por OCR; o un CSV)
python leer_testigos.py datos/testigos actas.db

# 2) E-14 oficial (carpeta de PDFs). Con clave → lee de verdad; sin clave → modo manual
python leer_registraduria.py datos/registraduria actas.db

# 3) comparar y generar Excel de discrepancias
python comparar.py actas.db comparacion_E14.xlsx
```

## Ejemplar del E-14 (de qué COPIA salió el dato)

El E-14 se imprime en varias copias con la misma información pero distinto destinatario.
Cada acta guarda de cuál copia se tomó el dato (campo `tipo_acta`), para poder auditarlo:

| Tipo | Quién la guarda | Uso típico |
|---|---|---|
| `claveros` | Claveros (arca triclave) | copia que suele tener el testigo |
| `delegados` | Delegados de la Registraduría | suele ser la copia oficial publicada |
| `transmision` | Puesto de transmisión | usada para el pre-conteo |
| `desconocido` | — | no se indicó |

Cómo indicarlo:

```bash
# Por línea de comando
python leer_testigos.py datos/testigos actas.db --tipo claveros
python leer_registraduria.py datos/registraduria actas.db --tipo delegados

# O por fila, con la columna 'tipo_acta' en el CSV de testigos (manda sobre --tipo)
```

Al procesar, el sistema **detecta en la foto/PDF** si aparecen 1, 2 o 3 copias
(Claveros, Delegados, Transmisión) y lo imprime en consola. Los votos se guardan
indicando **de cuál copia se leyeron** (`--tipo` o columna `tipo_acta`).

El Excel incluye hoja **Trazabilidad E-14** y columnas *Copias en evidencia* /
*Votos leídos desde* por cada fuente. Si la foto del testigo trae varias copias,
se marca alerta para revisar si los números coinciden entre ellas.

## Criterios de revisión manual

Una mesa/casilla va a revisión humana si: confianza OCR < 80%, la suma de votos no
cuadra con el total, las dos fuentes no coinciden, o la alineación fue pobre.
