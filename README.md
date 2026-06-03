# Auditoría de actas E-14 — Presidenciales Colombia 2026

Herramienta para **leer actas E-14** (oficial de la Registraduría y la del testigo
electoral), pasarlas a una tabla común y **comparar** para detectar discrepancias.
Todo lo dudoso (confianza < 80%, suma que no cuadra o fuentes que difieren) se
**marca para revisión humana**.

> 📄 Lee primero `VISION_Y_DECISIONES.md` (el porqué) y `PLAN_PASO_A_PASO.md` (el cómo).

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
leer_testigos.py        SCRIPT 1: E-14 del testigo (CSV) → tabla
leer_registraduria.py   SCRIPT 2: PDF oficial → capa1 → OCR → tabla
comparar.py             SCRIPT 3: cruza fuentes → Excel de discrepancias
plantillas/             plantilla oficial en blanco del E-14
ejemplos/               datos de ejemplo
```

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Conectar la API (único paso pendiente)

```bash
cp .env.example .env
# edita .env y pon GEMINI_API_KEY=...   (o OPENAI_API_KEY=...)
```

La fábrica `crear_backend()` detecta la clave automáticamente. Nada más cambia.

## Uso

```bash
# 1) E-14 de testigos desde CSV
python leer_testigos.py ejemplos/ejemplo_testigos.csv actas.db

# 2) E-14 oficial (PDF o carpeta). Con clave → lee de verdad; sin clave → modo manual
python leer_registraduria.py acta_oficial.pdf actas.db --codigo 88-128-15-85-001

# 3) comparar y generar Excel de discrepancias
python comparar.py actas.db comparacion_E14.xlsx
```

## Criterios de revisión manual

Una mesa/casilla va a revisión humana si: confianza OCR < 80%, la suma de votos no
cuadra con el total, las dos fuentes no coinciden, o la alineación fue pobre.
