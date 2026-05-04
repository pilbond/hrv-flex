"""
Tests de regresión para SYA-11: _build_error_context, _build_exit_context,
_build_error_location y _build_better_fit_readout con anclas estructuradas.

Cubre los casos críticos del diseño:
- VERDE + bajo coste: no fuerza culpa donde no la hay
- ÁMBAR + ejecución coherente: distingue error de decisión vs ejecución
- ÁMBAR + pico de bloque + necesitada: nombra el timing como causa
- Campos opcionales ausentes: no rompe cuando composite_context es None
"""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analysis.session_analysis_pipeline import (
    ERROR_EXIT_CONTEXT_VERSION,
    QUALITY_SESSION_WORK_MIN_THRESHOLD,
    _build_better_fit_readout,
    _build_error_context,
    _build_error_location,
    _build_exit_context,
    _build_recent_block_rows_7d,
    build_conversational_payload,
)


def _base_session_row(**overrides):
    row = {
        "session_id": "i_test",
        "Fecha": "2026-04-25",
        "start_time": "09:00",
        "sport": "cycling",
        "sport_family": "bike",
        "z3_pct": "15.0",
        "cardiac_drift_pct": "5.0",
        "work_total_min": "35.0",
        "moving_min": "180.0",
        "load": "120",
        "work_n_blocks": "2",
    }
    row.update(overrides)
    return row


def _composite_high_cost():
    return {
        "thermal_context": {"thermal_band": "high"},
        "durability_context": {"durability_hint": "fade_like"},
        "subjective_coherence": {"subjective_coherence_score": 88.0},
    }


def _composite_low_cost():
    return {
        "thermal_context": {"thermal_band": "low"},
        "durability_context": {"durability_hint": "steady_easy"},
        "subjective_coherence": {"subjective_coherence_score": 72.0},
    }


class TestErrorContext(unittest.TestCase):

    def test_version_field_present(self):
        ec = _build_error_context("caution_first", "VERDE", [], [], _base_session_row(), None, None)
        self.assertEqual(ec["version"], ERROR_EXIT_CONTEXT_VERSION)

    def test_verde_low_cost_no_mismatch(self):
        """VERDE sin costes dominantes: gate_mode caution_first, sin mismatch."""
        ec = _build_error_context(
            "caution_first", "VERDE+", [], [],
            _base_session_row(z3_pct="15.0"),
            _composite_low_cost(), None,
        )
        self.assertEqual(ec["gate_mode"], "caution_first")
        self.assertEqual(ec["gate_vs_execution_delta"], "aligned")
        self.assertFalse(ec["cost_vs_gate_mismatch"])
        self.assertEqual(ec["negative_cost_count"], 0)

    def test_ambar_high_z3_coherent_marks_decision_error(self):
        """ÁMBAR + z3>50% + coherencia alta = error de decisión, no ejecución."""
        ec = _build_error_context(
            "gate_first", "ÁMBAR+++",
            ["pos1"], ["neg1", "neg2", "neg3"],
            _base_session_row(z3_pct="65.0"),
            _composite_high_cost(), None,
        )
        self.assertEqual(ec["gate_mode"], "gate_first")
        self.assertEqual(ec["gate_vs_execution_delta"], "exceeded")
        self.assertTrue(ec["cost_vs_gate_mismatch"])
        self.assertEqual(ec["execution_coherence"], "high")
        self.assertEqual(ec["thermal_penalty"], "high")
        self.assertEqual(ec["durability_hint"], "fade_like")

    def test_ambar_low_z3_aligned(self):
        """ÁMBAR pero z3 bajo: gate restrictivo pero ejecución dentro del margen."""
        ec = _build_error_context(
            "gate_first", "ÁMBAR+",
            ["pos1"], ["neg1"],
            _base_session_row(z3_pct="30.0"),
            _composite_low_cost(), None,
        )
        self.assertEqual(ec["gate_vs_execution_delta"], "aligned")
        self.assertFalse(ec["cost_vs_gate_mismatch"])

    def test_no_composite_does_not_crash(self):
        """Sin composite_context: campos opcionales ausentes, core siempre presente."""
        ec = _build_error_context("gate_first", "ÁMBAR", [], [], _base_session_row(), None, None)
        self.assertIn("gate_mode", ec)
        self.assertIn("gate_vs_execution_delta", ec)
        self.assertNotIn("execution_coherence", ec)
        self.assertNotIn("thermal_penalty", ec)
        self.assertNotIn("durability_hint", ec)

    def test_coherence_low_when_below_threshold(self):
        composite = {"subjective_coherence": {"subjective_coherence_score": 70.0}}
        ec = _build_error_context("gate_first", "ÁMBAR", [], [], _base_session_row(), composite, None)
        self.assertEqual(ec["execution_coherence"], "low")


class TestExitContext(unittest.TestCase):

    def test_version_field_present(self):
        ex = _build_exit_context("bike", "caution_first", _base_session_row(), None, None, [])
        self.assertEqual(ex["version"], ERROR_EXIT_CONTEXT_VERSION)

    def test_target_hit_uses_constant_threshold(self):
        """work_total_min exactamente en el umbral: target_hit=True."""
        row = _base_session_row(work_total_min=str(QUALITY_SESSION_WORK_MIN_THRESHOLD))
        ex = _build_exit_context("bike", "caution_first", row, None, None, [])
        self.assertTrue(ex["execution_quality"]["target_hit"])

    def test_target_not_hit_below_threshold(self):
        row = _base_session_row(work_total_min="5.0")
        ex = _build_exit_context("bike", "caution_first", row, None, None, [])
        self.assertFalse(ex["execution_quality"]["target_hit"])

    def test_cost_within_expected_false_when_high_drift(self):
        row = _base_session_row(cardiac_drift_pct="15.0")
        ex = _build_exit_context("bike", "caution_first", row, _composite_low_cost(), None, [])
        self.assertFalse(ex["execution_quality"]["cost_within_expected"])

    def test_cost_within_expected_true_when_low_drift_no_fade(self):
        row = _base_session_row(cardiac_drift_pct="4.0")
        ex = _build_exit_context("bike", "caution_first", row, _composite_low_cost(), None, [])
        self.assertTrue(ex["execution_quality"]["cost_within_expected"])

    def test_no_recent_rows_rank_is_1(self):
        """Sin sesiones recientes del mismo deporte: esta es la única → rank 1."""
        ex = _build_exit_context("bike", "caution_first", _base_session_row(), None, None, [])
        self.assertEqual(ex["block_role_signals"]["load_rank_in_sport_7d"], 1)
        self.assertTrue(ex["block_role_signals"]["is_peak_load_in_block"])

    def test_sessions_since_last_quality_counts_only_same_sport(self):
        """Solo cuenta sesiones del mismo deporte (bike) sin calidad antes de la primera con calidad.
        road_run no se cuenta aunque no tenga trabajo útil."""
        recent = [
            {"Fecha": "2026-04-24", "sport": "bike", "work_total_min": "3.0", "load": "80"},
            {"Fecha": "2026-04-23", "sport": "bike", "work_total_min": "2.0", "load": "60"},
            {"Fecha": "2026-04-22", "sport": "bike", "work_total_min": "35.0", "load": "140"},
            {"Fecha": "2026-04-21", "sport": "road_run", "work_total_min": "0.0", "load": "50"},
        ]
        ex = _build_exit_context("bike", "caution_first", _base_session_row(), None, None, recent)
        self.assertEqual(ex["block_role_signals"]["sessions_since_last_quality"], 2)

    def test_long_duration_bike_threshold_180(self):
        row = _base_session_row(moving_min="200.0")
        ex = _build_exit_context("bike", "caution_first", row, None, None, [])
        self.assertTrue(ex["adaptation_signals"]["long_duration"])

        row_short = _base_session_row(moving_min="150.0")
        ex_short = _build_exit_context("bike", "caution_first", row_short, None, None, [])
        self.assertFalse(ex_short["adaptation_signals"]["long_duration"])

    def test_long_duration_trail_threshold_90(self):
        row = _base_session_row(sport="trail_run", moving_min="100.0")
        ex = _build_exit_context("trail", "caution_first", row, None, None, [])
        self.assertTrue(ex["adaptation_signals"]["long_duration"])

    def test_effort_vs_fields_included_when_present(self):
        row = _base_session_row(effort_vs_recent="above", effort_vs_anchor="at")
        ex = _build_exit_context("bike", "caution_first", row, None, None, [])
        self.assertEqual(ex["block_role_signals"]["effort_vs_recent"], "above")
        self.assertEqual(ex["block_role_signals"]["effort_vs_anchor"], "at")

    def test_effort_vs_fields_absent_when_missing(self):
        ex = _build_exit_context("bike", "caution_first", _base_session_row(), None, None, [])
        self.assertNotIn("effort_vs_recent", ex["block_role_signals"])
        self.assertNotIn("effort_vs_anchor", ex["block_role_signals"])


class TestRecentRowsWindow(unittest.TestCase):

    def test_recent_block_rows_7d_uses_full_window(self):
        rows = [
            {"session_id": "i_test", "Fecha": "2026-04-25", "start_time": "09:00", "sport": "bike", "work_total_min": "35.0", "load": "120"},
            {"session_id": "i_1", "Fecha": "2026-04-24", "start_time": "09:00", "sport": "bike", "work_total_min": "3.0", "load": "100"},
            {"session_id": "i_2", "Fecha": "2026-04-23", "start_time": "09:00", "sport": "bike", "work_total_min": "2.0", "load": "110"},
            {"session_id": "i_3", "Fecha": "2026-04-22", "start_time": "09:00", "sport": "bike", "work_total_min": "2.0", "load": "130"},
            {"session_id": "i_4", "Fecha": "2026-04-21", "start_time": "09:00", "sport": "bike", "work_total_min": "2.0", "load": "90"},
            {"session_id": "i_5", "Fecha": "2026-04-20", "start_time": "09:00", "sport": "bike", "work_total_min": "2.0", "load": "80"},
            {"session_id": "i_6", "Fecha": "2026-04-19", "start_time": "09:00", "sport": "bike", "work_total_min": "2.0", "load": "70"},
            {"session_id": "i_7", "Fecha": "2026-04-18", "start_time": "09:00", "sport": "bike", "work_total_min": "2.0", "load": "60"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "sessions.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

            with patch("analysis.session_analysis_pipeline.DEFAULT_SESSIONS_CSV", csv_path):
                rows_7d = _build_recent_block_rows_7d(_base_session_row(sport="bike"))
                self.assertEqual(len(rows_7d), 7)
                self.assertEqual(rows_7d[0]["Fecha"], "2026-04-24")
                self.assertEqual(rows_7d[0]["load"], "100")

                ex = _build_exit_context("bike", "caution_first", _base_session_row(sport="bike"), None, None, rows_7d)
                self.assertEqual(ex["block_role_signals"]["load_rank_in_sport_7d"], 2)


class TestErrorLocationUpgrade(unittest.TestCase):

    def test_verde_no_costs_returns_no_error(self):
        """VERDE + sin costes dominantes: texto de no-error claro, sin culpa forzada."""
        text = _build_error_location("caution_first", [], [], error_context=None)
        self.assertIn("No aparece un error claro", text)

    def test_verde_with_error_context_no_costs_still_no_error(self):
        """Con exit_context VERDE, el texto de no-error se mantiene."""
        ec = _build_error_context("caution_first", "VERDE", [], [], _base_session_row(), _composite_low_cost(), None)
        text = _build_error_location("caution_first", [], [], error_context=ec)
        self.assertIn("No aparece un error claro", text)

    def test_ambar_decision_error_distinguished_from_execution(self):
        """ÁMBAR + exceeded + coherence high → distingue error de decisión."""
        ec = _build_error_context(
            "gate_first", "ÁMBAR+++",
            ["pos1"], ["neg1", "neg2"],
            _base_session_row(z3_pct="65.0"),
            {"subjective_coherence": {"subjective_coherence_score": 90.0}}, None,
        )
        text = _build_error_location("gate_first", ["pos1"], ["neg1", "neg2"], error_context=ec)
        self.assertIn("decisión", text)
        self.assertIn("ejecución", text)

    def test_ambar_without_exit_exceeded_generic_text(self):
        """ÁMBAR sin anclas: cae en el texto genérico de dosificación."""
        text = _build_error_location("gate_first", ["pos1"], [], error_context=None)
        self.assertIn("dosificación", text)

    def test_caution_more_costs_than_benefits(self):
        text = _build_error_location("caution_first", ["pos1"], ["neg1", "neg2", "neg3"], error_context=None)
        self.assertIn("ajuste", text)


class TestBetterFitReadoutUpgrade(unittest.TestCase):

    def _exit(self, **overrides):
        base = {
            "version": ERROR_EXIT_CONTEXT_VERSION,
            "execution_quality": {"target_hit": True, "work_total_min": 35.0, "cost_within_expected": True},
            "block_role_signals": {"load_rank_in_sport_7d": 1, "is_peak_load_in_block": True, "sessions_since_last_quality": 0},
            "adaptation_signals": {"sport_family": "bike", "z3_pct": 20.0, "long_duration": True, "gate_vs_execution_delta": "aligned"},
        }
        base.update(overrides)
        return base

    def test_verde_cost_within_expected_acknowledges_fit(self):
        """VERDE + cost_within_expected=True → reconoce que la sesión ya encajó bien."""
        text = _build_better_fit_readout(
            "bike", "caution_first", ["pos1"], [],
            None, _base_session_row(),
            exit_context=self._exit(),
        )
        self.assertIn("ya encajó", text)

    def test_ambar_bike_thermal_high_adds_fresca(self):
        """ÁMBAR + bike + thermal high → menciona ventana más fresca."""
        ex = self._exit(adaptation_signals={"sport_family": "bike", "z3_pct": 65.0, "long_duration": True, "gate_vs_execution_delta": "exceeded", "thermal_load": "high"})
        text = _build_better_fit_readout(
            "bike", "gate_first", ["pos1"], ["neg1"],
            None, _base_session_row(z3_pct="65.0"),
            exit_context=ex,
        )
        self.assertIn("fresca", text)

    def test_ambar_bike_no_thermal_mentions_contextual(self):
        """ÁMBAR + bike sin thermal → menciona margen contextual."""
        ex = self._exit(adaptation_signals={"sport_family": "bike", "z3_pct": 30.0, "long_duration": True, "gate_vs_execution_delta": "aligned"})
        text = _build_better_fit_readout(
            "bike", "gate_first", ["pos1"], [],
            None, _base_session_row(),
            exit_context=ex,
        )
        self.assertIn("margen contextual", text)

    def test_caution_cost_not_expected_peak_needed_timing(self):
        """Caution + cost_not_within_expected + peak + sessions_since >= 3 → habla de timing."""
        ex = self._exit(
            execution_quality={"target_hit": True, "work_total_min": 35.0, "cost_within_expected": False},
            block_role_signals={"load_rank_in_sport_7d": 1, "is_peak_load_in_block": True, "sessions_since_last_quality": 4},
        )
        text = _build_better_fit_readout(
            "bike", "caution_first", ["pos1"], ["neg1", "neg2"],
            None, _base_session_row(),
            exit_context=ex,
        )
        self.assertIn("momento", text)

    def test_no_exit_context_behaves_as_before(self):
        """Sin exit_context: comportamiento original sin cambios."""
        text = _build_better_fit_readout(
            "bike", "gate_first", ["pos1"], ["neg1"],
            None, _base_session_row(),
            exit_context=None,
        )
        self.assertIn("Habría encajado mejor", text)

    def test_verde_no_error_context_no_crash(self):
        """VERDE sin exit_context ni error_context: no crashea, devuelve texto válido."""
        text = _build_better_fit_readout(
            "bike", "caution_first", [], [],
            None, _base_session_row(),
            exit_context=None,
        )
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)


class TestPayloadWiring(unittest.TestCase):

    def test_conversational_payload_exposes_error_and_exit_context(self):
        summary = {}
        manifest = {
            "date": "2026-04-25",
            "session_id": "i_test",
            "slug": "i_test",
            "sport": "bike",
            "start_time": "09:00",
        }
        payload = build_conversational_payload(summary, manifest, _base_session_row(sport="bike"))
        narrative_targets = payload["narrative_targets"]
        self.assertIn("error_context", narrative_targets)
        self.assertIn("exit_context", narrative_targets)
        self.assertEqual(narrative_targets["error_context"]["version"], ERROR_EXIT_CONTEXT_VERSION)
        self.assertEqual(narrative_targets["exit_context"]["version"], ERROR_EXIT_CONTEXT_VERSION)


if __name__ == "__main__":
    unittest.main()
