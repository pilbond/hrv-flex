import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from analysis import swim_context as swim

POOL = 25.0


def make_exercise(
    blocks,
    *,
    pool=POOL,
    units="POOL_UNIT_METERS",
    start="2026-05-19T15:30:40",
    tz=120,
    duration_ms=3_600_000,
    laps=None,
    swolf_offset=0.0,
    pools_swum=None,
    stroke_count_offset=0,
    pauses=None,
):
    """Ejercicio Polar v4 sintético y coherente.

    `blocks`: lista de (estilo, n_fases, duracion_ms_por_fase, brazadas_por_fase).
    """
    phases = []
    offset = 5_000
    by_style = {}
    for style, count, phase_ms, strokes in blocks:
        for _ in range(count):
            phases.append({
                "startOffsetMillis": offset,
                "durationMillis": phase_ms,
                "style": style,
                "strokes": strokes,
            })
            offset += phase_ms + 2_000
            group = by_style.setdefault(style, {"count": 0, "ms": 0, "strokes": 0})
            group["count"] += 1
            group["ms"] += phase_ms
            group["strokes"] += strokes
    styles = []
    for style, group in by_style.items():
        if style not in swim.LENGTH_VALIDATED_STYLES:
            continue
        styles.append({
            "style": f"SWIMMING_STYLE_{style}",
            "distanceMeters": group["count"] * pool,
            "strokeCount": group["strokes"] + stroke_count_offset,
            "swimmingTimeTotalMillis": group["ms"],
            "hrAvg": 115,
            "hrMax": 130,
            "swolfAvg": (group["ms"] / 1000 + group["strokes"]) / group["count"] + swolf_offset,
        })
    distance = sum(s["distanceMeters"] for s in styles)
    return {
        "startTime": start,
        "timezoneOffsetMinutes": tz,
        "durationMillis": duration_ms,
        "distanceMeters": distance,
        "statistics": {"swimmingStatistics": {
            "distanceMeters": distance,
            "totalStrokeCount": sum(s["strokeCount"] for s in styles),
            "poolsSwum": len(phases) if pools_swum is None else pools_swum,
            "poolUnits": units,
            "poolLength": pool,
            "swimmingStyles": styles,
        }},
        "laps": {"laps": laps or []},
        "samples": {
            "swimmingPhases": {"phases": phases},
            "samples": [{"type": "HEART_RATE", "intervalMillis": 1000, "values": [110] * 10}],
        },
        "pauseTimes": pauses if pauses is not None else [],
    }


def session_row(**overrides):
    row = {
        "session_id": "s1",
        "sport": "swim",
        "Fecha": "2026-05-19",
        "start_time": "15:30",
        "duration_min": "60.0",
        "rpe": "",
    }
    row.update(overrides)
    return row


def source(exercise, status="matched"):
    return {
        "retrieved_at_utc": "2026-11-08T00:00:00+00:00",
        "features": list(swim.POLAR_SWIM_FEATURES),
        "match": {"status": status, "start_delta_min": 0.5, "duration_gap_min": 0.0, "dst_fallback": False},
        "exercise": exercise,
    }


MIXED = [("BREASTSTROKE", 4, 38_000, 18), ("BACKSTROKE", 6, 50_000, 36)]


class SwimContextCompleteTest(unittest.TestCase):
    def test_complete_polar_session_validates_lengths_and_swolf(self):
        laps = [{"splitTimeMillis": 400_000, "durationMillis": 400_000, "distanceMeters": 250.0,
                 "statistics": {"swimmingStatistics": {"poolsSwum": 10, "strokes": 288, "avgSecsPerPool": 40.0}}}]
        ctx, phases, lap_rows = swim.build_swim_context(
            session_row(), source(make_exercise(MIXED, laps=laps)), cardio_score=0
        )
        self.assertEqual(ctx["swim_source"], "polar_v4")
        self.assertEqual(ctx["granularity"], "length")
        self.assertEqual(ctx["length_validation_status"], "passed")
        self.assertEqual(ctx["n_lengths_validated"], 10)
        self.assertEqual(ctx["swolf_source"], "polar")
        self.assertEqual(ctx["swolf_validation_status"], "validated_against_phases")
        self.assertAlmostEqual(ctx["swolf_by_stroke"]["BREASTSTROKE"], 56.0, places=3)
        self.assertAlmostEqual(ctx["swolf_by_stroke"]["BACKSTROKE"], 86.0, places=3)
        self.assertEqual(ctx["primary_stroke"], "BACKSTROKE")
        self.assertEqual(ctx["breaststroke_pct"], 40.0)
        self.assertEqual(ctx["distance_unclassified_m"], 0.0)
        # ritmo agregado = 100 x suma de tiempos / suma de distancias
        self.assertAlmostEqual(ctx["pace_s_per_100m"], 100 * (4 * 38 + 6 * 50) / 250, places=2)
        self.assertEqual(len(phases), 10)
        self.assertTrue(all(p["length_validated"] and p["distance_m"] == POOL for p in phases))
        self.assertEqual(phases[0]["swolf_derived"], 56.0)
        self.assertEqual(lap_rows[0]["pools_swum"], 10)
        self.assertEqual(lap_rows[0]["start_s"], 0.0)

    def test_no_global_swolf_field(self):
        ctx, _, _ = swim.build_swim_context(session_row(), source(make_exercise(MIXED)))
        self.assertNotIn("swolf_avg", ctx)
        self.assertNotIn("swolf_mean", ctx)
        self.assertIsInstance(ctx["swolf_by_stroke"], dict)

    def test_missing_laps_keeps_phases_and_lengths(self):
        ctx, phases, laps = swim.build_swim_context(session_row(), source(make_exercise(MIXED)))
        self.assertEqual(ctx["granularity"], "length")
        self.assertEqual(ctx["n_laps"], 0)
        self.assertEqual(laps, [])
        self.assertEqual(len(phases), 10)

    def test_pause_duration_from_start_and_end(self):
        pauses = [{"startTime": "2026-05-19T16:30:27.968", "endTime": "2026-05-19T16:30:32.504"}]
        ctx, _, _ = swim.build_swim_context(session_row(), source(make_exercise(MIXED, pauses=pauses)))
        self.assertEqual(ctx["pause_count"], 1)
        self.assertAlmostEqual(ctx["pause_total_s"], 4.536, places=3)

    def test_non_swim_session_has_no_context(self):
        self.assertEqual(swim.build_swim_context(session_row(sport="road_run"), None), (None, [], []))


class SwimContextLoadTest(unittest.TestCase):
    def test_missing_rpe_degrades_without_false(self):
        ctx, _, _ = swim.build_swim_context(session_row(), source(make_exercise(MIXED)), cardio_score=0)
        self.assertEqual(ctx["status"], "partial")
        self.assertIn("rpe_missing", ctx["quality_reasons"])
        self.assertIsNone(ctx["srpe_load"])
        self.assertIsNone(ctx["rpe_vs_cardio_discordance"])

    def test_srpe_and_discordance(self):
        ctx, _, _ = swim.build_swim_context(
            session_row(rpe="5"), source(make_exercise(MIXED)), cardio_score=0, intervals_session_rpe=290
        )
        self.assertEqual(ctx["status"], "available")
        self.assertEqual(ctx["srpe_load"], 300.0)
        self.assertEqual(ctx["srpe_unit"], "AU")
        self.assertEqual(ctx["srpe_minus_intervals_session_rpe"], 10.0)
        self.assertTrue(ctx["rpe_vs_cardio_discordance"])

    def test_no_discordance_with_cardio_or_low_rpe(self):
        ctx, _, _ = swim.build_swim_context(session_row(rpe="5"), source(make_exercise(MIXED)), cardio_score=1)
        self.assertFalse(ctx["rpe_vs_cardio_discordance"])
        ctx, _, _ = swim.build_swim_context(session_row(rpe="3"), source(make_exercise(MIXED)), cardio_score=0)
        self.assertFalse(ctx["rpe_vs_cardio_discordance"])
        ctx, _, _ = swim.build_swim_context(session_row(rpe="5"), source(make_exercise(MIXED)), cardio_score=None)
        self.assertIsNone(ctx["rpe_vs_cardio_discordance"])

    def test_provider_zero_rpe_is_not_valid(self):
        ctx, _, _ = swim.build_swim_context(session_row(rpe="0"), source(make_exercise(MIXED)), intervals_session_rpe=0)
        self.assertIsNone(ctx["rpe"])
        self.assertIsNone(ctx["intervals_session_rpe"])
        self.assertIn("rpe_missing", ctx["quality_reasons"])

    def test_missing_duration(self):
        ctx, _, _ = swim.build_swim_context(session_row(rpe="4", duration_min=""), source(make_exercise(MIXED)))
        self.assertIn("duration_missing", ctx["quality_reasons"])
        self.assertIsNone(ctx["srpe_load"])


class SwimContextFallbackTest(unittest.TestCase):
    def test_fit_fallback_skips_terminal_empty_lap_and_ignores_fit_swolf(self):
        fit_laps = [
            {"total_timer_time": 824.0, "total_distance": 450.0, "SWOLF": 45.7},
            {"total_timer_time": 940.0, "total_distance": 525.0, "SWOLF": 44.7},
            {"total_timer_time": 1.0, "total_distance": None},
        ]
        ctx, phases, laps = swim.build_swim_context(session_row(rpe="4"), None, fit_laps=fit_laps, cardio_score=0)
        self.assertEqual(ctx["swim_source"], "intervals_fit_laps")
        self.assertEqual(ctx["granularity"], "lap")
        self.assertEqual(len(laps), 2)
        self.assertEqual(laps[1]["start_s"], 824.0)
        self.assertEqual(ctx["swolf_source"], "none")
        self.assertIsNone(ctx["swolf_by_stroke"])
        self.assertIn("polar_unavailable", ctx["quality_reasons"])
        self.assertEqual(phases, [])
        self.assertNotIn("SWOLF", json.dumps(laps))

    def test_without_polar_fit_or_rpe_is_unavailable(self):
        ctx, _, _ = swim.build_swim_context(session_row(), None, polar_error="PolarV4Error: 401")
        self.assertEqual(ctx["status"], "unavailable")
        self.assertEqual(ctx["swim_source"], "none")
        self.assertEqual(ctx["granularity"], "none")
        self.assertEqual(ctx["polar_match"]["error"], "PolarV4Error: 401")

    def test_ambiguous_match_source_degrades(self):
        ctx, _, _ = swim.build_swim_context(session_row(), {"match": {"status": "ambiguous_match"}, "exercise": None})
        self.assertIn("ambiguous_match", ctx["quality_reasons"])
        self.assertEqual(ctx["swim_source"], "none")


class SwimLengthValidationTest(unittest.TestCase):
    def test_unknown_pool_or_yards_blocks_lengths(self):
        for field, value in (("poolLength", None), ("poolUnits", "POOL_UNIT_YARDS")):
            exercise = make_exercise(MIXED)
            exercise["statistics"]["swimmingStatistics"][field] = value
            ctx, phases, _ = swim.build_swim_context(session_row(), source(exercise))
            self.assertIn("pool_unknown", ctx["quality_reasons"])
            self.assertEqual(ctx["length_validation_status"], "failed")
            self.assertEqual(ctx["granularity"], "phase")
            self.assertTrue(all(p["distance_m"] is None for p in phases))
            self.assertEqual(ctx["swolf_validation_status"], "not_validated")

    def test_drill_and_turn_phases_are_not_lengths(self):
        blocks = MIXED + [("DRILL", 2, 60_000, 0), ("TURN", 1, 3_000, 0)]
        ctx, phases, _ = swim.build_swim_context(session_row(), source(make_exercise(blocks)))
        self.assertIn("unsupported_phase_type", ctx["quality_reasons"])
        self.assertEqual(ctx["length_validation_status"], "passed")
        drill = [p for p in phases if p["style"] in {"DRILL", "TURN"}]
        self.assertEqual(len(drill), 3)
        self.assertTrue(all(not p["length_validated"] and p["distance_m"] is None for p in drill))
        self.assertTrue(all(p["exclusion_reason"] == "unsupported_phase_type" for p in drill))
        self.assertEqual(ctx["n_lengths_validated"], 10)

    def test_inconsistent_phases_fail_validation(self):
        ctx, phases, _ = swim.build_swim_context(
            session_row(), source(make_exercise(MIXED, stroke_count_offset=3))
        )
        self.assertIn("phase_validation_failed", ctx["quality_reasons"])
        self.assertEqual(ctx["length_validation_status"], "failed")
        self.assertTrue(all(p["exclusion_reason"] == "phase_validation_failed" for p in phases))

    def test_phase_count_must_match_pools_swum(self):
        ctx, _, _ = swim.build_swim_context(session_row(), source(make_exercise(MIXED, pools_swum=11)))
        self.assertEqual(ctx["length_validation_status"], "failed")

    def test_overlapping_phases_fail_validation(self):
        exercise = make_exercise(MIXED)
        phases = exercise["samples"]["swimmingPhases"]["phases"]
        phases[1]["startOffsetMillis"] = phases[0]["startOffsetMillis"] + 1_000
        ctx, _, _ = swim.build_swim_context(session_row(), source(exercise))
        self.assertEqual(ctx["length_validation_status"], "failed")

    def test_suspicious_polar_swolf_blocks_derived_lengths(self):
        ctx, phases, _ = swim.build_swim_context(session_row(), source(make_exercise(MIXED, swolf_offset=1.0)))
        self.assertEqual(ctx["swolf_validation_status"], "mismatch")
        self.assertIn("source_mismatch", ctx["quality_reasons"])
        self.assertEqual(ctx["length_validation_status"], "failed")
        self.assertEqual(ctx["n_lengths_validated"], 0)
        self.assertTrue(all(not p["length_validated"] and p["swolf_derived"] is None for p in phases))
        self.assertIsNone(swim.build_style_history(ctx, []))

    def test_empty_style_statistics_block_lengths(self):
        exercise = make_exercise(MIXED)
        exercise["statistics"]["swimmingStatistics"]["swimmingStyles"] = []
        ctx, phases, _ = swim.build_swim_context(session_row(), source(exercise))
        self.assertEqual(ctx["length_validation_status"], "failed")
        self.assertIn("phase_validation_failed", ctx["quality_reasons"])
        self.assertTrue(all(p["distance_m"] is None and p["swolf_derived"] is None for p in phases))
        self.assertEqual(ctx["swolf_source"], "none")

    def test_style_in_phases_without_statistics_blocks_lengths(self):
        exercise = make_exercise(MIXED)
        stats = exercise["statistics"]["swimmingStatistics"]
        stats["swimmingStyles"] = [s for s in stats["swimmingStyles"] if "BACKSTROKE" not in s["style"]]
        ctx, _, _ = swim.build_swim_context(session_row(), source(exercise))
        self.assertEqual(ctx["length_validation_status"], "failed")

    def test_missing_official_swolf_keeps_lengths_without_derived_swolf(self):
        exercise = make_exercise(MIXED)
        for style in exercise["statistics"]["swimmingStatistics"]["swimmingStyles"]:
            style.pop("swolfAvg")
        ctx, phases, _ = swim.build_swim_context(session_row(), source(exercise))
        self.assertEqual(ctx["length_validation_status"], "passed")
        self.assertEqual(ctx["swolf_source"], "none")
        self.assertTrue(all(p["swolf_derived"] is None for p in phases))

    def test_phase_without_offset_or_duration_fails_validation(self):
        for index, field in ((0, "startOffsetMillis"), (5, "startOffsetMillis"), (0, "durationMillis")):
            exercise = make_exercise(MIXED)
            exercise["samples"]["swimmingPhases"]["phases"][index].pop(field)
            ctx, phases, _ = swim.build_swim_context(session_row(), source(exercise))
            self.assertEqual(ctx["length_validation_status"], "failed", (index, field))
            self.assertTrue(all(not p["length_validated"] for p in phases))

    def test_style_without_swim_time_has_no_aggregate_pace(self):
        exercise = make_exercise(MIXED)
        exercise["statistics"]["swimmingStatistics"]["swimmingStyles"][0].pop("swimmingTimeTotalMillis")
        ctx, _, _ = swim.build_swim_context(session_row(rpe="4"), source(exercise), cardio_score=1)
        self.assertIsNone(ctx["pace_s_per_100m"])
        self.assertIsNone(ctx["swim_time_s"])
        self.assertIn("duration_missing", ctx["quality_reasons"])
        self.assertEqual(ctx["status"], "partial")

    def test_too_few_lengths_per_style(self):
        blocks = [("FREESTYLE", 8, 40_000, 20), ("BREASTSTROKE", 2, 40_000, 18)]
        ctx, _, _ = swim.build_swim_context(session_row(), source(make_exercise(blocks)))
        breast = next(s for s in ctx["styles"] if s["style"] == "BREASTSTROKE")
        self.assertTrue(breast["too_few_lengths"])
        self.assertIn("too_few_lengths", ctx["quality_reasons"])


class SwimMatchTest(unittest.TestCase):
    def test_matches_single_candidate(self):
        result = swim.match_swim_exercise(session_row(), [make_exercise(MIXED)])
        self.assertEqual(result["status"], "matched")
        self.assertAlmostEqual(result["start_delta_min"], 0.667, places=3)

    def test_rejects_candidate_with_very_different_duration(self):
        result = swim.match_swim_exercise(session_row(), [make_exercise(MIXED, duration_ms=600_000)])
        self.assertEqual(result["status"], "no_match")
        self.assertEqual(result["reason"], "duration_mismatch")
        ctx, _, _ = swim.build_swim_context(session_row(), {"match": result, "exercise": None})
        self.assertIn("source_mismatch", ctx["quality_reasons"])

    def test_rejects_candidate_without_duration(self):
        exercise = make_exercise(MIXED)
        exercise.pop("durationMillis")
        self.assertEqual(swim.match_swim_exercise(session_row(), [exercise])["status"], "no_match")

    def test_duration_picks_the_right_candidate(self):
        short = make_exercise(MIXED, start="2026-05-19T15:31:00", duration_ms=600_000)
        right = make_exercise(MIXED, start="2026-05-19T15:35:00")
        result = swim.match_swim_exercise(session_row(), [short, right])
        self.assertEqual(result["status"], "matched")
        self.assertIs(result["exercise"], right)

    def test_ignores_non_swim_exercises(self):
        other = {"startTime": "2026-05-19T15:30:00", "durationMillis": 3_600_000}
        result = swim.match_swim_exercise(session_row(), [other])
        self.assertEqual(result["status"], "no_match")

    def test_two_close_candidates_are_ambiguous(self):
        result = swim.match_swim_exercise(
            session_row(),
            [make_exercise(MIXED), make_exercise(MIXED, start="2026-05-19T15:40:00")],
        )
        self.assertEqual(result["status"], "ambiguous_match")
        self.assertIsNone(result["exercise"])

    def test_dst_shift_with_same_duration(self):
        result = swim.match_swim_exercise(session_row(), [make_exercise(MIXED, start="2026-05-19T16:30:40")])
        self.assertEqual(result["status"], "matched")
        self.assertTrue(result["dst_fallback"])

    def test_dst_shift_requires_similar_duration(self):
        result = swim.match_swim_exercise(
            session_row(), [make_exercise(MIXED, start="2026-05-19T16:30:40", duration_ms=1_800_000)]
        )
        self.assertEqual(result["status"], "no_match")

    def test_timezone_aware_start_is_converted_to_local(self):
        exercise = make_exercise(MIXED, start="2026-05-19T13:30:40Z", tz=120)
        self.assertEqual(swim.exercise_local_start(exercise).isoformat(), "2026-05-19T15:30:40")
        self.assertEqual(swim.match_swim_exercise(session_row(), [exercise])["status"], "matched")


class FakeClient:
    def __init__(self, sessions):
        self.sessions = sessions
        self.calls = []

    def list_training_sessions(self, date_from, date_to, features=None):
        self.calls.append((date_from, date_to, features))
        return self.sessions


class SwimFetchCacheTest(unittest.TestCase):
    def test_fetch_writes_trimmed_cache_and_reuses_it(self):
        exercise = make_exercise(MIXED)
        exercise["id"] = "secret-id"
        client = FakeClient([{"exercises": [exercise]}])
        with TemporaryDirectory() as tmp:
            cache = Path(tmp) / swim.SOURCE_FILENAME
            payload = swim.fetch_polar_swim_source(session_row(), cache, client=client)
            self.assertEqual(client.calls, [("2026-05-19", "2026-05-20", swim.POLAR_SWIM_FEATURES)])
            self.assertEqual(payload["match"]["status"], "matched")
            text = cache.read_text(encoding="utf-8")
            self.assertNotIn("secret-id", text)
            self.assertNotIn("HEART_RATE", text)
            self.assertIn("swimmingPhases", text)
            again = swim.fetch_polar_swim_source(session_row(), cache, client=client)
            self.assertEqual(len(client.calls), 1)
            ctx, _, _ = swim.build_swim_context(session_row(), again)
            self.assertEqual(ctx["length_validation_status"], "passed")

    def test_stale_cache_is_revalidated_and_refetched(self):
        with TemporaryDirectory() as tmp:
            cache = Path(tmp) / swim.SOURCE_FILENAME
            swim.fetch_polar_swim_source(session_row(), cache, client=FakeClient([{"exercises": [make_exercise(MIXED)]}]))
            payload = json.loads(cache.read_text(encoding="utf-8"))
            payload["exercise"]["durationMillis"] = 600_000
            cache.write_text(json.dumps(payload), encoding="utf-8")
            fresh = FakeClient([{"exercises": [make_exercise(MIXED)]}])
            again = swim.fetch_polar_swim_source(session_row(), cache, client=fresh)
            self.assertEqual(len(fresh.calls), 1)
            self.assertEqual(again["exercise"]["durationMillis"], 3_600_000)

    def test_cache_for_another_date_is_refetched(self):
        with TemporaryDirectory() as tmp:
            cache = Path(tmp) / swim.SOURCE_FILENAME
            swim.fetch_polar_swim_source(session_row(), cache, client=FakeClient([{"exercises": [make_exercise(MIXED)]}]))
            client = FakeClient([])
            swim.fetch_polar_swim_source(session_row(Fecha="2026-05-20"), cache, client=client)
            self.assertEqual(len(client.calls), 1)

    def test_cached_no_match_is_refetched(self):
        with TemporaryDirectory() as tmp:
            cache = Path(tmp) / swim.SOURCE_FILENAME
            swim.fetch_polar_swim_source(session_row(), cache, client=FakeClient([]))
            client = FakeClient([{"exercises": [make_exercise(MIXED)]}])
            again = swim.fetch_polar_swim_source(session_row(), cache, client=client)
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(again["match"]["status"], "matched")

    def test_rejected_polar_source_falls_back_to_fit_laps(self):
        stale = source(make_exercise(MIXED, duration_ms=600_000))
        fit_laps = [{"total_timer_time": 600.0, "total_distance": 300.0}]
        ctx, _, laps = swim.build_swim_context(session_row(), stale, fit_laps=fit_laps)
        self.assertEqual(ctx["swim_source"], "intervals_fit_laps")
        self.assertEqual(len(laps), 1)

    def test_attach_reads_fit_even_when_cached_polar_is_rejected(self):
        from analysis import session_analysis_pipeline as pipeline

        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / swim.SOURCE_FILENAME
            source_path.write_text(json.dumps(source(make_exercise(MIXED, duration_ms=600_000))), encoding="utf-8")
            summary = {"session_cost_model": {"cardio_score": 0}}
            fit_laps = [{"total_timer_time": 600.0, "total_distance": 300.0}]
            with patch.object(pipeline._swim, "read_fit_laps", return_value=fit_laps):
                pipeline.attach_swim_context(
                    summary,
                    {"polar_swim_source_path": str(source_path)},
                    session_row(),
                    tmp_path / "artifacts",
                    fit_artifact_path=tmp_path / "session.fit",
                )
            ctx = summary["swim_context"]
            self.assertEqual(ctx["swim_source"], "intervals_fit_laps")
            self.assertEqual(ctx["n_laps"], 1)
            self.assertIn("source_mismatch", ctx["quality_reasons"])
            self.assertFalse((tmp_path / "artifacts" / swim.SOURCE_FILENAME).exists())

    def test_stale_source_in_context_is_rejected(self):
        stale = source(make_exercise(MIXED, duration_ms=600_000))
        ctx, phases, _ = swim.build_swim_context(session_row(), stale)
        self.assertEqual(ctx["swim_source"], "none")
        self.assertEqual(ctx["polar_match"]["status"], "no_match")
        self.assertIn("source_mismatch", ctx["quality_reasons"])
        self.assertEqual(phases, [])

    def test_fetch_without_swim_stores_no_exercise(self):
        client = FakeClient([{"exercises": [{"startTime": "2026-05-19T15:30:00"}]}])
        with TemporaryDirectory() as tmp:
            payload = swim.fetch_polar_swim_source(session_row(), Path(tmp) / "x.json", client=client)
        self.assertIsNone(payload["exercise"])
        self.assertEqual(payload["match"]["status"], "no_match")


class SwimArtifactsTest(unittest.TestCase):
    def test_csv_writers(self):
        _, phases, laps = swim.build_swim_context(session_row(), source(make_exercise(MIXED)))
        with TemporaryDirectory() as tmp:
            path = swim.write_swim_phases_csv(Path(tmp) / swim.PHASES_FILENAME, phases)
            with path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(list(rows[0].keys()), swim.PHASE_COLUMNS)
            self.assertEqual(len(rows), 10)
            self.assertIsNone(swim.write_swim_laps_csv(Path(tmp) / swim.LAPS_FILENAME, laps))

    def test_run_analysis_attaches_swim_context(self):
        from analysis import session_analysis_pipeline as pipeline

        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            row = session_row(rpe="5")
            row_path = tmp_path / "session_row.json"
            row_path.write_text(json.dumps(row), encoding="utf-8")
            source_path = tmp_path / swim.SOURCE_FILENAME
            source_path.write_text(json.dumps(source(make_exercise(MIXED))), encoding="utf-8")
            (tmp_path / "sessions.csv").write_text("session_id\ns1\n", encoding="utf-8")
            (tmp_path / "stream.csv").write_text("timestamp,hr\n", encoding="utf-8")
            manifest = {
                "slug": "2026-05-19_15-30_swim_s1",
                "session_row_path": str(row_path),
                "session_id": "s1",
                "sessions_csv": str(tmp_path / "sessions.csv"),
                "hr_stream_csv": str(tmp_path / "stream.csv"),
                "rr_csv": None,
                "rr_error": "sin RR",
                "analysis_only_context": {},
                "coach_interval_rows": [],
                "coach_group_rows": [],
                "terrain_intervals": [],
                "polar_swim_source_path": str(source_path),
                "polar_swim_error": None,
            }
            manifest_path = tmp_path / "bundle_manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(pipeline, "build_v1_snapshot", return_value=None), \
                 patch.object(pipeline, "build_runaware_context", return_value=None), \
                 patch.object(pipeline, "build_v1_shadow_comparison", return_value=None), \
                 patch.object(pipeline, "build_v1_shadow_history", return_value=None), \
                 patch.object(pipeline, "build_longitudinal_context", return_value=None), \
                 patch.object(pipeline, "build_report_sync_token", return_value="sync-token"), \
                 patch.object(pipeline, "build_analyst_prompt_markdown", return_value="prompt"), \
                 patch.object(pipeline, "build_ai_handoff_markdown", return_value="handoff"), \
                 patch.object(pipeline, "write_managed_final_report", return_value=None), \
                 patch.object(pipeline, "build_report_sync_status", return_value={"status": "in_sync"}):
                result = pipeline.run_analysis(manifest_path, tmp_path / "reports")
                summary = json.loads(Path(result["summary_path"]).read_text(encoding="utf-8"))
                payload = json.loads(Path(result["session_payload"]).read_text(encoding="utf-8"))
                technical = Path(result["technical_report_md"]).read_text(encoding="utf-8")
                self.assertEqual(summary["swim_context"]["granularity"], "length")
                self.assertEqual(payload["swim_context"], summary["swim_context"])
                self.assertIn("## Swim Context", technical)
                self.assertTrue(Path(result["swim_phases_csv"]).exists())
                artifacts = Path(result["artifacts_dir"])
                self.assertTrue((artifacts / swim.SOURCE_FILENAME).exists())
                final = pipeline.build_final_report_markdown(payload=payload, summary=summary, report_sync_token="t")
                self.assertIn("largos validados", final)


if __name__ == "__main__":
    unittest.main()
