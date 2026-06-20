# Visión y decisiones — Auditoría de actas E-14 (Presidenciales Colombia 2026)

> Documento de **por qué**. Explica qué construimos y por qué tomamos cada decisión.
> Para el **cómo** (paso a paso), ver `PLAN_PASO_A_PASO.md`.

---

## 1. Objetivo

Construir una herramienta que **lea automáticamente las actas E-14** (el acta donde
los jurados anotan a mano el conteo de votos por candidato) y **detecte
discrepancias** entre:

- el **E-14 oficial** publicado por la Registraduría, y
- el **E-14 registrado por los testigos electorales** de nuestro lado.

Cuando los números no coincidan, o cuando la lectura automática no sea confiable,
el sistema lo **marca para revisión humana** en lugar de dar un dato falso.

**Alcance inicial:** primera vuelta presidencial (13 candidatos), enfocado en las
**~2.641 mesas de Cartagena**. Diseñado para escalar a más mesas después.

---

## 2. El problema de fondo

Los votos en el E-14 están **escritos a mano**, en casillas individuales (un dígito
por cajita, ej. `1 0 6` = 106). Esto hace que:

- El OCR tradicional (Tesseract) **no sirva**: está hecho para texto impreso.
- Ningún OCR sea 100% confiable en manuscrito (~85–95% en el mejor caso).

Por eso el sistema **no se diseña para confiar ciegamente** en la lectura, sino para
**señalar lo dudoso** y apoyarse en dos validaciones independientes (ver §4).

---

## 3. Decisiones clave (argumentadas)

### 3.1. Leemos E-14 directo, NO el preconteo estructurado de la Registraduría

La Registraduría publica el preconteo ya en formato de datos (más barato y exacto).
**Aun así elegimos leer el E-14.**

- **Por qué:** el objetivo es auditar **la fuente primaria** (el acta). Si tomáramos
  el preconteo estructurado para un lado y el E-14 para el otro, estaríamos
  comparando **dos cosas distintas**, y una diferencia podría deberse al cambio de
  fuente y no a un error real. Comparar **E-14 contra E-14** mantiene una sola verdad
  auditable.
- **Costo asumido:** leer ambos lados con OCR cuesta un poco más, pero sigue siendo
  muy bajo (ver §6). Se prioriza **integridad sobre ahorro**.

### 3.2. Capa 1 — Alineación por plantilla (no heurísticas de orientación)

La imagen escaneada llega rotada/torcida. Para enderezarla **descartamos** las
heurísticas de píxeles (probadas y fallaron: distinguir "derecho" de "boca abajo" es
imposible mirando sólo píxeles).

- **Decisión:** alinear cada página contra la **plantilla oficial en blanco** del
  E-14 usando *feature matching* (SIFT) + homografía.
- **Por qué:** una sola operación corrige rotación (incluido 180°), inclinación,
  escala y perspectiva; es **offline y gratis**; y como la plantilla es de posición
  conocida, deja **cada casilla en coordenadas fijas** → recorte exacto para el OCR.
- **Evidencia:** ya probado sobre un acta real; las páginas de votos alinean bien
  (60–76 inliers) y el número de inliers sirve de **control de calidad** (pocos
  inliers ⇒ marcar para revisión).

### 3.3. Capa 2 — OCR con modelo multimodal en la nube

Para leer los dígitos manuscritos usamos un **modelo de visión multimodal**, porque
en los benchmarks recientes son los mejores en formularios manuscritos y pueden
devolver **JSON estructurado con confianza** por casilla.

#### ¿Gemini o GPT? → **Recomendación: Gemini como motor principal, GPT como verificador opcional.**

| Criterio | Gemini | GPT (visión) | Quién gana |
|---|---|---|---|
| Precisión en formularios manuscritos | Líder en benchmark reciente (~85% exact-match, mejor en campos discretos y numéricos) | Muy cerca, 2º lugar | **Gemini** |
| Alucinaciones (inventar números) | Buena | Ligeramente mejor (~6% tasa) | GPT |
| Salida estructurada (JSON/esquema) | Soporta `response_schema` nativo | Soporta JSON mode / structured outputs | Empate |
| Costo por imagen | Más barato (sobre todo Flash) | Algo más caro | **Gemini** |
| Manejo de imagen rotada/sucia | Robusto | Robusto | Empate |

- **Por qué Gemini de base:** mejor precisión medida en manuscrito + más barato, lo
  que importa al escalar a miles de mesas. Su `response_schema` nos da los votos como
  JSON tipado directamente.
- **Por qué dejar GPT como verificador:** en mesas marginales (confianza media) se
  puede pedir una **segunda lectura con GPT**; si ambos coinciden, la confianza sube;
  si no, va a revisión. Esto es opcional y se activa sólo cuando vale la pena (poco
  costo extra, sólo en casos dudosos).
- **Modelo Gemini por defecto: `gemini-3.5-flash`** (antes `gemini-2.5-flash`).
  **Evidencia (2026-06-20):** contra un E-14 real de la 2ª vuelta 2022,
  `gemini-2.5-flash` leyó 87 votos donde el acta dice 89 (confianza reportada 95%,
  o sea el número alto NO garantiza exactitud); `gemini-3.5-flash` leyó el valor
  correcto con 95-100% de confianza, sobre la misma imagen alineada.
  `gemini-2.5-pro` no es opción en el tier gratis (cuota 0, requiere facturación).
- **Aislamiento:** el proveedor vive detrás de una interfaz (`e14/ocr.py`), así que
  cambiar Gemini↔GPT no toca el resto del sistema.

### 3.4. Umbral de confianza: < 80% → revisión manual

Toda casilla/mesa con **confianza por debajo del 80%** se envía a una cola de
**revisión humana**, mostrando el recorte de la casilla junto al número leído.

- **Por qué 80%:** equilibra esfuerzo humano y seguridad. Con volúmenes bajos
  (Cartagena, primera vuelta) es viable revisar a mano todo lo que caiga bajo el
  umbral, logrando una precisión final **casi perfecta y auditable**.
- Además de la confianza, se marca para revisión si: la **suma no cuadra** (§4) o si
  **las dos fuentes no coinciden**.

### 3.5. Almacenamiento y app

- **Datos:** una base de datos (hoy SQLite local; preparada para migrar a una **DB en
  la nube** tipo Supabase/Neon, cuya capa gratuita sobra para Cartagena).
- **Distribución:** app de escritorio para **Windows** empaquetada en **instalador**
  (el usuario final no ve código ni terminal).
- **Protección del código:** la lógica valiosa y la clave de API conviene que vivan en
  un **servicio propio** (no dentro del .exe, que es descompilable), de cara a reusar
  el sistema en **segunda vuelta**.

### 3.6. Trabajo por lotes (un municipio) con el Excel de la Registraduría como catálogo

Con **una sola instancia** y miles de mesas, no auditamos todo de golpe: la **unidad de
trabajo es el lote = un municipio**. El usuario elige qué municipio auditar.

- **Por qué un municipio:** mantiene el volumen acotado y el costo de OCR controlable, y
  permite avanzar de forma modular y medible (Cartagena, ~2.517 mesas, primero).
- **El Excel "Mesa a Mesa" de la Registraduría es el *catálogo*** (universo de mesas), no
  la entrada de actas. De ahí salen: el **número de cada municipio**, cuántas mesas tiene,
  y la **cobertura** (cuántas ya tenemos vs cuántas faltan). Solo se gasta OCR en las
  mesas **listas** (con testigo y oficial presentes).

#### Codificación: la de la **Registraduría**, NO DANE

El Excel usa los **códigos electorales de la Registraduría** (en él **Bolívar = 5** y los
municipios **no son consecutivos**), distintos del estándar **DANE DIVIPOLA** (Bolívar =
13). Se eligió la codificación de la **Registraduría** como base de la nomenclatura
`NuMunicipio-zona-puesto-mesa` porque es **la misma fuente** de las actas E-14 que
auditamos; mezclarla con DANE introduciría errores de cruce. Los códigos de archivo se
normalizan (sin ceros a la izquierda) para casar siempre con el catálogo.

### 3.7. El ESTADO vive en la DB; la evidencia no se mueve; la re-auditoría se versiona

- Los **PDFs son evidencia inmutable**: entran a `datos/<municipio>/{testigos,registraduria}/`
  y **no se mueven**. El estado de avance (pendiente, leída, en revisión) vive en la **DB**,
  no en carpetas (mover archivos duplicaría el estado y se desincronizaría).
- **Re-auditar no pierde lo anterior:** antes de sobrescribir una lectura, la versión previa
  se archiva en `actas_historial` (con número de versión y fecha). `actas` mantiene la
  versión vigente, así el comparador no cambia. La verificación manual se conserva.

---

## 4. Cómo se garantiza la confiabilidad (doble validación)

1. **Reconteo interno (suma cuadra):** suma de los 13 candidatos + blancos + nulos +
   no marcados **debe igualar** el total de votos en la urna. Si no cuadra → revisar.
2. **Cruce entre fuentes:** la lectura del E-14 oficial vs la del E-14 del testigo.
   - Coinciden + suma cuadra → **alta confianza**.
   - Difieren → **revisión humana** (y posible alerta de irregularidad).

Estas dos validaciones, sumadas al umbral de confianza del OCR, son las que hacen el
sistema **auditable** pese a que ningún OCR de manuscrito sea perfecto.

---

## 5. Capas del sistema

```
PDF E-14 (oficial y testigo)
   │
   ├─ Capa 1  Alineación por plantilla (OpenCV/SIFT)         [HECHO]
   │            → imagen derecha + casillas en posición conocida
   │
   ├─ Capa 2  OCR multimodal (Gemini)                        [POR CONECTAR]
   │            → {candidato: voto, confianza} por casilla
   │
   ├─ Capa 4  Validación (suma cuadra) + confianza<80% → revisar
   │
   ├─ Almacén  DB (SQLite → nube)                            [HECHO local]
   │
   └─ Capa 3  Comparador testigo vs oficial → Excel/Reporte  [HECHO]
```

---

## 6. Costos (recalculado 2026-06-20, todo Bolívar, modelo `gemini-3.5-flash`)

**Universo real** (catálogo `cobertura.py`, sin filtro de municipio): el departamento
de Bolívar tiene **46 municipios y 5.354 mesas** (Cartagena son 2.517 de esas). La
tabla anterior de esta sección estaba calculada solo para Cartagena, con el modelo
`gemini-2.5-flash` y asumiendo 2 páginas con votos por acta. Ambos supuestos quedaron
obsoletos: el modelo subió a `gemini-3.5-flash` (commit `dba2317`, más preciso) y la
segunda vuelta usa **1 sola página de votos** por acta (`--solo-pagina-1`), no 2.

**Precio oficial de `gemini-3.5-flash`** ([ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing),
consultado 2026-06-20, tier de pago — el tier gratis de Google AI Studio sigue
existiendo pero está limitado a ~1.500 requests/día):

| Concepto | Precio |
|---|---|
| Input | $1.50 / 1M tokens |
| Output | $9.00 / 1M tokens |
| Input cacheado | $0.15 / 1M tokens |

**Tokens por llamada OCR** (1 imagen alineada + el prompt de `e14/ocr.py` + JSON de
respuesta con 6 campos — c1, c2, blanco, nulos, no_marcados, suma_total):

| Componente | Tokens | Supuesto |
|---|---|---|
| Imagen (input) | 560–1.120 | resolución `medium`–`high` (Gemini 3 cobra fijo por nivel: 280/560/1.120/imagen) |
| Prompt de texto (input) | ~300 | instrucciones + 6 etiquetas de campo |
| Respuesta JSON (output) | ~200–250 | 6 campos `{valor, confianza}` |

→ **costo por llamada OCR ≈ $0.0035–$0.0045**

**Volumen total para auditar TODO Bolívar** (testigo + oficial, las 5.354 mesas):

- Base: 5.354 mesas × 2 fuentes × 1 página = **10.708 llamadas**
- + reintento "zoom" cuando quedan casillas sin leer (visto en pruebas reales, no
  siempre ocurre): estimo +15–30% → **~12.300–13.900 llamadas**

| Escenario | Llamadas | Costo total |
|---|---|---|
| Optimista (medium, sin reintentos) | 10.708 | **~$37** |
| Conservador (high + 30% reintentos) | 13.900 | **~$63** |

**Con un presupuesto aprobado de $300 USD, auditar las 5.354 mesas de todo Bolívar
cuesta entre ~$37 y ~$63 en OCR** (incluso duplicando esa cifra por imprevistos,
sigue por debajo de $130) → queda un margen de **~$170–$260** sin tocar el
presupuesto, bastante más que los $100 de margen que se estaban evaluando.

**El cuello de botella real no es este costo de API — es la cobertura de datos.**
Hoy solo hay evidencia real (testigo + oficial) de **1 mesa de 5.354** (0.02%).
Conseguir las fotos/PDF de testigos de las ~5.353 mesas restantes en 46 municipios
es trabajo logístico humano, no algo que el presupuesto de OCR resuelva.

> Esta es una estimación de tokens, no una medición de facturación real (Google no
> publica el costo exacto por imagen para Gemini 3.x). Antes de comprometer el
> presupuesto, vale la pena correr un piloto de 50–100 mesas con facturación
> habilitada (no tier gratis) y mirar el costo real en el dashboard de Google AI
> Studio / Cloud Billing, para confirmar este rango con datos reales.

(El "$75/hora de AWS" era una instancia GPU, que NO se necesita en este enfoque.)

---

## 7. Riesgos y límites conocidos

- **Precisión del OCR en manuscrito:** ~85–95%. Mitigado por umbral 80% + doble
  validación + revisión humana.
- **Página de firmas/cédulas:** poca estructura para alinear; es secundaria y se marca
  para revisión si hace falta.
- **Papel arrugado/foto de mala calidad:** la homografía asume superficie plana;
  fotos muy dobladas pueden requerir revisión manual.
- **Dependencia de la plantilla oficial:** válido mientras el diseño del E-14 no
  cambie (para segunda vuelta se actualiza la plantilla y la lista de candidatos).
