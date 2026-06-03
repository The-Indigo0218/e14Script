# Plan paso a paso — Auditoría de actas E-14

> Documento de **cómo**. Pensado para que **cualquier persona o IA** que lo lea
> entienda el contexto completo y pueda continuar el desarrollo.
> Para el **por qué** de cada decisión, ver `VISION_Y_DECISIONES.md`.

---

## 0. Contexto mínimo (leer primero)

- **Qué es un E-14:** "Acta de Escrutinio de los Jurados de Votación". Es el documento
  donde, al cerrar la mesa, los jurados anotan **a mano** cuántos votos sacó cada
  candidato. Es la fuente primaria del conteo en Colombia.
- **Estructura del E-14 (primera vuelta 2026):** son 3 páginas escaneadas, y cada
  página trae **3 copias** de la misma acta (CLAVEROS / DELEGADOS / TRANSMISIÓN):
  - **Página de candidatos 1–7** + "Nivelación de la mesa" (total votantes E-11,
    total votos en la urna, incinerados).
  - **Página de candidatos 8–13** + votos en blanco / nulos / no marcados + **suma total**.
  - **Página de firmas/cédulas** de los jurados (secundaria para el conteo).
- **Los votos** se escriben con un dígito por casilla (ej. `1 0 6` = 106).
- **13 candidatos** (ver lista exacta en `e14/modelo.py`).

- **Objetivo del software:** leer el E-14 oficial y el del testigo, pasarlos a una
  tabla común, y **comparar** para detectar diferencias; marcar para revisión humana
  todo lo que tenga **confianza < 80%**, sume mal, o difiera entre fuentes.

---

## 1. Arquitectura y módulos

```
auditoria-e14/                 (este repositorio)
  VISION_Y_DECISIONES.md       por qué
  PLAN_PASO_A_PASO.md          cómo (este archivo)

  e14/                         paquete con la lógica (a migrar desde el prototipo)
    modelo.py                  CONTRATO: estructura ActaE14 + columnas de votos
    almacen.py                 base de datos (SQLite; luego nube)
    alineacion.py              CAPA 1: alineación por plantilla (SIFT+homografía)
    ocr.py                     CAPA 2: punto de conexión del OCR (Gemini/GPT)
    comparador.py              CAPA 3: lógica de comparación

  leer_testigos.py             SCRIPT 1: carga E-14 del testigo a la tabla
  leer_registraduria.py        SCRIPT 2: PDF oficial → capa1 → OCR → tabla
  comparar.py                  SCRIPT 3: cruza fuentes → Excel de discrepancias
```

**Contrato compartido:** los 3 scripts hablan el mismo "idioma": el objeto `ActaE14`
(una fila por mesa y por fuente). Mientras se respete ese contrato, cada parte se
puede desarrollar y probar por separado ("divide y vencerás").

---

## 2. Flujo de datos

```
   E-14 testigo ──[Script 1]──┐
                              ├──► tabla común (DB) ──[Script 3]──► Excel discrepancias
   E-14 oficial ──[Script 2]──┘
```

Cada fila de la tabla: `codigo_mesa`, `fuente` (testigo|registraduria), votos
`c1..c13`, `blanco`, `nulos`, `no_marcados`, totales, **confianza**,
`necesita_revision`, notas.

---

## 3. Estado actual (qué está hecho)

| Componente | Estado | Notas |
|---|---|---|
| Modelo de datos (`modelo.py`) | ✅ | Contrato `ActaE14` + 13 candidatos |
| Almacén SQLite (`almacen.py`) | ✅ | Tabla `actas`, clave (mesa, fuente) |
| Capa 1 alineación (`alineacion.py`) | ✅ | Probada en acta real; QA por inliers |
| Comparador (`comparador.py` + `comparar.py`) | ✅ | Excel de 3 hojas; probado |
| Script 1 testigos (`leer_testigos.py`) | ✅ | Carga desde CSV |
| Script 2 registraduría (`leer_registraduria.py`) | ✅ pipeline | Falta enchufar OCR real |
| Capa 2 OCR (`ocr.py`) | ⏳ | Interfaz lista; backend nube por implementar |
| DB en la nube | ⏳ | Hoy SQLite local |
| App de escritorio + instalador Windows | ⏳ | Pendiente |

---

## 4. Pasos pendientes (en orden)

### Paso A — Conectar el OCR (capa 2) con Gemini
1. Crear clave de API de Gemini.
2. Implementar `BackendNube` en `e14/ocr.py`:
   - Recibe la imagen **ya alineada** (capa 1) y el `layout_id`.
   - Envía la imagen pidiendo **JSON estricto** con `response_schema`:
     `{ "c1": {valor, confianza}, ..., "blanco": {...}, ... }`.
   - El prompt indica qué casillas existen según el layout (cand 1–7, o 8–13 + totales).
   - Devuelve `LecturaOCR` (valores + confianzas + confianza_global).
3. Regla: si `confianza < 0.80` en una casilla → marcar `necesita_revision`.

### Paso B — Recorte por casilla (opcional, para máxima precisión)
- Usando las coordenadas fijas de la plantilla (capa 1 ya alinea a ellas), recortar
  cada casilla y, si hace falta, enviarlas en lote o validar dígito por dígito.

### Paso C — Cola de revisión manual
- Listar todo lo marcado `necesita_revision` con el recorte de la casilla al lado del
  número leído, para que un humano confirme/corrija. Persistir la corrección.

### Paso D — Comparador "modo auditoría"
- Sobre la base ya poblada por A/C, correr `comparar.py` y generar el Excel/reporte de
  discrepancias entre testigo y oficial (ya funciona; sólo se alimenta con datos OCR).

### Paso E — DB en la nube
- Migrar `almacen.py` de SQLite a una DB en la nube (Supabase/Neon, capa gratuita).
  La interfaz del almacén no cambia para el resto del sistema.

### Paso F — App de escritorio + instalador
- Interfaz gráfica (abrir PDF, ver resultados/confianza, confirmar dudosos, exportar).
- Empaquetar en `.exe` con instalador para Windows.
- Mantener la lógica/clave de API en un servicio propio (no dentro del .exe).

---

## 5. Cómo correr (estado actual del prototipo)

```bash
# 1) cargar E-14 de testigos desde un CSV
python leer_testigos.py ejemplo_testigos.csv actas.db

# 2) leer E-14 oficiales (PDF o carpeta) — hoy en modo OCR "manual"
python leer_registraduria.py acta_oficial.pdf actas.db --codigo 88-128-15-85-001

# 3) comparar y generar Excel de discrepancias
python comparar.py actas.db comparacion_E14.xlsx
```

Dependencias: ver `requirements.txt` (OpenCV, PyMuPDF, numpy, openpyxl).

---

## 6. Criterios de "marcar para revisión" (resumen)

Una mesa/casilla va a **revisión humana** si se cumple cualquiera:
- Confianza del OCR **< 80%**.
- La **suma** de votos no cuadra con el total declarado.
- El E-14 **oficial y el del testigo no coinciden**.
- La **alineación** (capa 1) tuvo pocos inliers (imagen dudosa).

---

## 7. Glosario rápido

- **E-11:** lista de votantes habilitados de la mesa (total votantes).
- **Inliers:** coincidencias válidas al alinear contra la plantilla; medida de calidad.
- **Homografía:** transformación que endereza/alinea la imagen a la plantilla.
- **Layout:** cuál de las páginas lógicas del E-14 es (cand 1–7 / 8–13 / firmas).
- **Confianza:** qué tan seguro está el OCR de cada número leído (0–1).
