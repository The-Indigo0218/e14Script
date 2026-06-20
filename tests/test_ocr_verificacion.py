"""Tests de BackendVerificado (doble lectura) — sin red, con backends falsos."""

from __future__ import annotations

from e14.ocr import BackendGemini, BackendVerificado, LecturaOCR, UMBRAL_REVISION, crear_backend

# Mismas columnas reales del layout "acta_completa" (segunda vuelta: c1, c2 +
# no-candidato + suma_total). Se completan todas para no depender de defaults.
COLS = ["c1", "c2", "blanco", "nulos", "no_marcados", "suma_total"]


class _BackendFalso:
    """Backend inyectable: devuelve la LecturaOCR fija que le pasen."""

    def __init__(self, nombre: str, lectura: LecturaOCR):
        self.nombre = nombre
        self._lectura = lectura

    def reconocer_votos(self, imagen_alineada, layout_id: str) -> LecturaOCR:
        return self._lectura


def _lectura(confianza_alta=0.95, **overrides) -> LecturaOCR:
    """Lectura completa con las 6 columnas reales; pasa valores/confianzas puntuales por kwarg."""
    valores = {c: 1 for c in COLS}
    confianzas = {c: confianza_alta for c in COLS}
    for clave, valor in overrides.items():
        col, campo = clave.rsplit("_", 1)  # ej. c1_valor / c1_conf
        if campo == "valor":
            valores[col] = valor
        elif campo == "conf":
            confianzas[col] = valor
    presentes = [confianzas[c] for c in COLS if valores[c] is not None]
    revisar = (not presentes) or any(cf < UMBRAL_REVISION for cf in presentes)
    return LecturaOCR(valores=valores, confianzas=confianzas,
                      confianza_global=min(presentes) if presentes else 0.0,
                      necesita_revision=revisar)


def test_no_consulta_verificador_si_todo_tiene_confianza_alta():
    principal = _BackendFalso("gemini", _lectura(c1_valor=10))
    verificador = _BackendFalso("gpt", _lectura(c1_valor=999))
    back = BackendVerificado(principal, verificador)
    resultado = back.reconocer_votos(None, "acta_completa")
    # No tocó nada: si hubiera consultado al verificador, c1 sería 999.
    assert resultado.valores["c1"] == 10
    assert resultado.necesita_revision is False


def test_verificador_confirma_sube_confianza():
    principal = _BackendFalso("gemini", _lectura(c1_valor=89, c1_conf=0.5))
    verificador = _BackendFalso("gpt", _lectura(c1_valor=89, c1_conf=0.92))
    back = BackendVerificado(principal, verificador)
    resultado = back.reconocer_votos(None, "acta_completa")
    assert resultado.valores["c1"] == 89
    assert resultado.confianzas["c1"] >= UMBRAL_REVISION
    assert resultado.necesita_revision is False
    assert "verificador confirma" in resultado.notas


def test_verificador_discrepa_queda_para_revision_sin_inventar_valor():
    principal = _BackendFalso("gemini", _lectura(c1_valor=87, c1_conf=0.5))
    verificador = _BackendFalso("gpt", _lectura(c1_valor=89, c1_conf=0.9))
    back = BackendVerificado(principal, verificador)
    resultado = back.reconocer_votos(None, "acta_completa")
    # No se promedia (88) ni se sobreescribe a ciegas: se queda con el del principal.
    assert resultado.valores["c1"] == 87
    assert resultado.necesita_revision is True
    assert "DISCREPANCIA principal=87 verificador=89" in resultado.notas


def test_verificador_recupera_valor_que_el_principal_no_pudo_leer():
    principal = _BackendFalso("gemini", _lectura(c1_valor=None, c1_conf=0.0))
    verificador = _BackendFalso("gpt", _lectura(c1_valor=42, c1_conf=0.85))
    back = BackendVerificado(principal, verificador)
    resultado = back.reconocer_votos(None, "acta_completa")
    assert resultado.valores["c1"] == 42
    assert resultado.confianzas["c1"] == 0.85
    assert "recuperado por verificador" in resultado.notas


def _sin_env_de_ocr(monkeypatch):
    for clave in ("OCR_BACKEND", "GEMINI_API_KEY", "OPENAI_API_KEY", "OCR_VERIFICAR_BAJA_CONFIANZA"):
        monkeypatch.delenv(clave, raising=False)
    # cargar_env() solo hace setdefault desde .env; con las claves ya seteadas
    # explícitamente abajo, no las pisa.
    monkeypatch.setattr("e14.ocr.cargar_env", lambda *a, **k: None)


def test_crear_backend_no_verifica_por_defecto_aunque_haya_ambas_claves(monkeypatch):
    _sin_env_de_ocr(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    back = crear_backend()
    assert isinstance(back, BackendGemini)  # NO BackendVerificado: nadie lo pidió.


def test_crear_backend_verifica_solo_si_se_pide_por_parametro(monkeypatch):
    _sin_env_de_ocr(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    back = crear_backend(verificar_baja_confianza=True)
    assert isinstance(back, BackendVerificado)


def test_crear_backend_verifica_si_se_pide_por_variable_de_entorno(monkeypatch):
    _sin_env_de_ocr(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    monkeypatch.setenv("OCR_VERIFICAR_BAJA_CONFIANZA", "1")
    back = crear_backend()
    assert isinstance(back, BackendVerificado)


def test_crear_backend_parametro_explicito_gana_a_la_variable_de_entorno(monkeypatch):
    _sin_env_de_ocr(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    monkeypatch.setenv("OCR_VERIFICAR_BAJA_CONFIANZA", "1")
    back = crear_backend(verificar_baja_confianza=False)
    assert isinstance(back, BackendGemini)
