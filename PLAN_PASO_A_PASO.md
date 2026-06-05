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

  e14/                         paquete con la lógica
    modelo.py                  CONTRATO: ActaE14 + columnas de votos
    almacen.py                 SQLite (luego nube)
    mesa.py                    código zona_puesto_mesa + emparejamiento carpetas
    alineacion.py              CAPA 1: SIFT + homografía
    preprocess.py              recorte/zoom/CLAHE antes del OCR
    ocr.py                     CAPA 2: Gemini / GPT / manual
    evidencia.py               copias visibles en la foto
    lectura.py                 orquestador PDF → ActaE14
    comparador.py              CAPA 3: comparación

  leer_testigos.py             SCRIPT 1: testigo (CSV o PDF) → tabla
  leer_registraduria.py        SCRIPT 2: oficial → capa1 → OCR → tabla
  comparar.py                  SCRIPT 3: cruza fuentes → Excel
  probar_api.py                verificar clave antes de OCR masivo
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
| Modelo de datos (`modelo.py`) | ✅ | `ActaE14`, `tipo_acta`, `copias_en_evidencia` |
| Almacén SQLite (`almacen.py`) | ✅ | Tabla `actas`, clave (mesa, fuente) |
| Emparejamiento (`mesa.py`) | ✅ | `21_01_13_testigo.pdf` ↔ `21_01_13_registraduria.pdf` |
| Capa 1 alineación (`alineacion.py`) | ✅ | Probada mesa 21_01_13; QA por inliers |
| Preprocesamiento (`preprocess.py`) | ✅ | Recorte negro + zoom para OCR |
| Capa 2 OCR (`ocr.py`) | ✅ | Gemini/GPT conectados; informe API en notas |
| Trazabilidad copias (`evidencia.py`) | ✅ | Foto testigo + título PDF oficial |
| Lectura unificada (`lectura.py`) | ✅ | PDF/imagen; `--solo-pagina-1` |
| Comparador (`comparador.py` + `comparar.py`) | ✅ | Excel + hoja Trazabilidad E-14 |
| Script 1 testigos (`leer_testigos.py`) | ✅ | CSV y PDF/OCR |
| Script 2 registraduría (`leer_registraduria.py`) | ✅ | Pipeline completo con Gemini |
| Par de prueba en repo | ✅ | `datos/*/21_01_13_*.pdf` — ver `README.md` |
| DB en la nube | ⏳ | Hoy SQLite local |
| App de escritorio + instalador Windows | ⏳ | Pendiente |

---

## 4. Pasos pendientes (en orden)

### Paso A — ~~Conectar el OCR (capa 2) con Gemini~~ ✅ HECHO
Ver `e14/ocr.py` (`BackendGemini`), `probar_api.py` y guía de reproducción en `README.md`.

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

## 5. Cómo correr (reproducir con el par incluido en el repo)

Ver **`README.md` → Guía de reproducción** (paso a paso completo).

Resumen rápido (mesa Cartagena 21_01_13, candidatos 1–7):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # pegar GEMINI_API_KEY
python probar_api.py

python leer_testigos.py datos/testigos/21_01_13_testigo.pdf actas.db --tipo claveros --solo-pagina-1
python leer_registraduria.py datos/registraduria/21_01_13_registraduria.pdf actas.db --solo-pagina-1
python comparar.py actas.db comparacion_21_01_13.xlsx
```

Esperado pág. 1: c1=130, c2=3, c4=77. Dependencias: `requirements.txt`.

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
