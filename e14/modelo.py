"""
Modelo de datos compartido (el "contrato" entre los 3 scripts).

Tanto el lector de testigos como el de la Registraduría deben producir un
objeto ActaE14 con esta MISMA estructura. El comparador asume esta estructura.

Así, "divide y vencerás": cada script es independiente, pero todos hablan el
mismo idioma (estas columnas).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

# ─── CANDIDATOS PRESIDENCIALES 2022 — SEGUNDA VUELTA (rama de pruebas) ──────────
# número (str) -> (nombre, agrupación). SOLO los 2 finalistas pasan a segunda vuelta.
# Esta rama (pruebas-segunda-vuelta-2022) valida el pipeline con datos REALES de la
# 2ª vuelta presidencial del 19-jun-2022 (resultados oficiales conocidos):
#   1. Gustavo Petro Urrego — vicepresidencial: Francia Márquez (Pacto Histórico)
#   2. Rodolfo Hernández Suárez — vicepresidencial: Marelen Castillo
#      (Liga de Gobernantes Anticorrupción)
# IMPORTANTE: el orden c1/c2 DEBE coincidir con el orden de las columnas en el
# formulario E-14 oficial de 2022. Aquí se asume c1=Petro, c2=Hernández; verificar
# contra el E-14 real antes de confiar en la comparación (si el formulario invierte
# el orden, intercambiar estas dos entradas).
CANDIDATOS: dict[str, tuple[str, str]] = {
    "1": ("GUSTAVO PETRO URREGO",      "PACTO HISTÓRICO"),
    "2": ("RODOLFO HERNÁNDEZ SUÁREZ",  "LIGA DE GOBERNANTES ANTICORRUPCIÓN"),
}

# Categorías de votos NO atribuibles a un candidato
CATEGORIAS_NO_CANDIDATO = ["blanco", "nulos", "no_marcados"]

# Identificadores de fuente
FUENTE_TESTIGO = "testigo"
FUENTE_REGISTRADURIA = "registraduria"

# ─── TIPO DE EJEMPLAR DEL E-14 (de qué COPIA se tomó el dato) ──────────────────
# El E-14 se imprime en varias copias con la MISMA información pero distinto
# destinatario. Saber de cuál salió cada dato es clave para auditar: si la copia
# de claveros y la de delegados de la misma mesa no coinciden, ya es una alerta.
TIPO_CLAVEROS = "claveros"        # ejemplar que va al arca triclave (claveros)
TIPO_DELEGADOS = "delegados"      # ejemplar de los delegados de la Registraduría
TIPO_TRANSMISION = "transmision"  # ejemplar usado para el pre-conteo / transmisión
TIPO_DESCONOCIDO = "desconocido"  # no se pudo determinar

TIPOS_ACTA: dict[str, str] = {
    TIPO_CLAVEROS:    "Claveros",
    TIPO_DELEGADOS:   "Delegados",
    TIPO_TRANSMISION: "Transmisión",
    TIPO_DESCONOCIDO: "Desconocido",
}


def normalizar_tipo_acta(valor: str | None) -> str:
    """Lleva texto libre ('CLAVEROS', 'delegado', etc.) a un tipo canónico."""
    t = (valor or "").strip().lower()
    if not t:
        return TIPO_DESCONOCIDO
    if "clav" in t:
        return TIPO_CLAVEROS
    if "deleg" in t:
        return TIPO_DELEGADOS
    if "transm" in t or "pre" in t:
        return TIPO_TRANSMISION
    return TIPO_DESCONOCIDO


def etiqueta_tipo_acta(valor: str | None) -> str:
    """Nombre legible del tipo de ejemplar."""
    return TIPOS_ACTA.get(normalizar_tipo_acta(valor), TIPOS_ACTA[TIPO_DESCONOCIDO])


def parsear_copias(raw: str | list[str] | None) -> list[str]:
    """Convierte 'claveros,delegados' o lista a tipos canónicos ordenados."""
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        items = [x.strip() for x in str(raw).split(",") if x.strip()]
    orden = [TIPO_CLAVEROS, TIPO_DELEGADOS, TIPO_TRANSMISION]
    vistos = {normalizar_tipo_acta(x) for x in items}
    vistos.discard(TIPO_DESCONOCIDO)
    return [c for c in orden if c in vistos]


def serializar_copias(copias: list[str] | str | None) -> str:
    """Guarda en DB como 'claveros,delegados'."""
    return ",".join(parsear_copias(copias))


def copias_a_texto(copias: list[str] | str | None) -> str:
    """Texto legible: 'Claveros + Delegados' o '—'."""
    lista = parsear_copias(copias)
    if not lista:
        return "—"
    return " + ".join(etiqueta_tipo_acta(c) for c in lista)


def resumen_trazabilidad_e14(
    fuente: str,
    copias_en_evidencia: list[str] | str | None,
    copia_lectura: str | None,
) -> str:
    """
    Resumen para consola/Excel: qué hay en la foto y de dónde salieron los votos.
    """
    quien = "evidencia jurados" if fuente == FUENTE_TESTIGO else "acta oficial"
    visibles = parsear_copias(copias_en_evidencia)
    leida = etiqueta_tipo_acta(copia_lectura)
    if visibles:
        n = len(visibles)
        bloque = copias_a_texto(visibles)
        if n >= 2:
            linea_ev = f"En la {quien} aparecen {n} copias: {bloque}"
        else:
            linea_ev = f"En la {quien} aparece copia: {bloque}"
    else:
        linea_ev = f"Copias en la {quien}: no detectadas"
    return f"{linea_ev} | Votos leídos desde: {leida}"


def columnas_voto() -> list[str]:
    """Orden canónico de las columnas de votos (candidatos + categorías)."""
    return [f"c{n}" for n in sorted(int(k) for k in CANDIDATOS)] + list(CATEGORIAS_NO_CANDIDATO)


@dataclass
class ActaE14:
    """Una lectura de un acta E-14 para una mesa, desde una fuente."""

    # ── Identificación de la mesa (clave para comparar) ──
    codigo_mesa: str                 # identificador único de mesa (ej. "88-128-15-85-001")
    fuente: str                      # FUENTE_TESTIGO o FUENTE_REGISTRADURIA

    # ── Ejemplares del E-14 (trazabilidad jurados / auditoría) ──
    tipo_acta: str | None = None              # copia DE LA QUE se leyeron los votos
    copias_en_evidencia: str | None = None    # copias VISIBLES en foto/PDF ("claveros,delegados")

    # ── Metadatos (informativos) ──
    departamento: str | None = None
    municipio: str | None = None
    zona: str | None = None
    puesto: str | None = None
    mesa: str | None = None

    # ── Votos por candidato (segunda vuelta: solo 2) ──
    c1: int | None = None
    c2: int | None = None

    # ── Otras categorías ──
    blanco: int | None = None
    nulos: int | None = None
    no_marcados: int | None = None

    # ── Totales del acta ──
    suma_total: int | None = None
    total_votos_urna: int | None = None
    total_votantes_e11: int | None = None

    # ── Trazabilidad / auditoría ──
    archivo_origen: str | None = None       # ruta del PDF/imagen leído
    confianza: float | None = None          # 0..1 de la lectura (OCR)
    necesita_revision: bool = False         # marcado para revisión humana
    notas: str | None = None

    # ── Verificación humana (persiste entre corridas de comparar.py) ──
    verificado_manualmente: bool = False    # un humano confirmó/corrigió esta lectura
    notas_verificacion: str | None = None   # comentario de quien verificó

    def votos(self) -> dict[str, int | None]:
        """Devuelve {columna_voto: valor} en orden canónico."""
        return {col: getattr(self, col) for col in columnas_voto()}

    def suma_calculada(self) -> int:
        """Suma de candidatos + blanco + nulos + no_marcados (ignora None)."""
        return sum(v for v in self.votos().values() if v is not None)

    def cuadra_internamente(self) -> bool | None:
        """
        Validación interna (capa 4): la suma de votos debe coincidir con el
        total declarado en el acta. None si no hay total para comparar.
        """
        objetivo = self.suma_total if self.suma_total is not None else self.total_votos_urna
        if objetivo is None:
            return None
        return self.suma_calculada() == objetivo

    def como_dict(self) -> dict:
        return asdict(self)
