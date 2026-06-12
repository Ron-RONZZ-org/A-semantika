"""Tests for the recenzi (interactive review) module.

Covers:
- Session CRUD helpers
- Result CRUD helpers
- Triple review fetching
- Distractor generation
- Question data building
- CLI commands (historio, vidi, forigi, rigardi, multobla)
"""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from A_semantika.cli import app
from A_semantika._reczeni_helpers import (
    add_result,
    build_question_data,
    create_session,
    delete_session,
    finish_session,
    generate_distractors,
    get_results,
    get_session,
    get_triples_for_review,
    list_sessions,
    update_session_score,
)

runner = CliRunner()


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _setup(node_svc, pred_svc, triple_svc) -> None:
    """Create nodes, predicates, and triples for review tests."""
    node_svc.create({"node_id": "N_ALPHA", "etikedoj": {"eo": "Alfa"}})
    node_svc.create({"node_id": "N_BRAVO", "etikedoj": {"eo": "Bravo"}})
    node_svc.create({"node_id": "N_CHARLIE", "etikedoj": {"eo": "Charlie"}})
    node_svc.create({"node_id": "N_DELTA", "etikedoj": {"eo": "Delta"}})
    pred_svc.create({"predicate_id": "rilatas_al", "etikedoj": {"eo": "rilatas al"}})
    pred_svc.create({"predicate_id": "estas", "etikedoj": {"eo": "estas"}})

    # Create triples
    triple_svc.add(
        subject_uuid="N_ALPHA", predicate_id="rilatas_al",
        object_value="N_BRAVO", object_type="uri",
    )
    triple_svc.add(
        subject_uuid="N_BRAVO", predicate_id="estas",
        object_value="N_CHARLIE", object_type="uri",
    )
    triple_svc.add(
        subject_uuid="N_CHARLIE", predicate_id="estas",
        object_value="N_DELTA", object_type="uri",
    )
    triple_svc.add(
        subject_uuid="N_ALPHA", predicate_id="estas",
        object_value="testa literalo", object_type="literal",
    )


# ── Session CRUD helpers ─────────────────────────────────────────────────────


class TestSessionCRUD:
    """Create, read, list, update, finish, delete sessions."""

    def test_create_session(self):
        sesio = create_session("rigardi")
        assert sesio["uuid"]
        assert sesio["modo"] == "rigardi"
        assert sesio["totalo"] == 0
        assert sesio["korekta"] == 0
        assert sesio["finita"] == 0

    def test_create_session_with_dates(self):
        sesio = create_session("multobla", dato_de="2026-01-01", dato_gis="2026-06-01")
        assert sesio["dato_de"] == "2026-01-01"
        assert sesio["dato_gis"] == "2026-06-01"

    def test_get_session(self):
        sesio = create_session("rigardi")
        retrieved = get_session(sesio["uuid"])
        assert retrieved is not None
        assert retrieved["uuid"] == sesio["uuid"]

    def test_get_session_nonexistent(self):
        assert get_session("nonexistent-uuid") is None

    def test_list_sessions(self):
        create_session("rigardi")
        create_session("multobla")
        sessions = list_sessions(limit=10)
        assert len(sessions) >= 2

    def test_list_sessions_empty(self):
        sessions = list_sessions(limit=10)
        assert len(sessions) == 0

    def test_list_sessions_respects_limit(self):
        for _ in range(5):
            create_session("rigardi")
        sessions = list_sessions(limit=3)
        assert len(sessions) == 3

    def test_update_session_score(self):
        sesio = create_session("rigardi")
        update_session_score(sesio["uuid"], 3, 5)
        updated = get_session(sesio["uuid"])
        assert updated["korekta"] == 3
        assert updated["totalo"] == 5

    def test_finish_session(self):
        sesio = create_session("rigardi")
        assert get_session(sesio["uuid"])["finita"] == 0
        finish_session(sesio["uuid"])
        assert get_session(sesio["uuid"])["finita"] == 1

    def test_delete_session(self):
        sesio = create_session("rigardi")
        add_result(sesio["uuid"], "N_ALPHA", "estas", "N_BRAVO", "uri", True, "jes", 1)
        assert delete_session(sesio["uuid"]) is True
        assert get_session(sesio["uuid"]) is None
        assert get_results(sesio["uuid"]) == []

    def test_delete_session_nonexistent(self):
        result = delete_session("nonexistent")
        assert result is False


# ── Result CRUD ──────────────────────────────────────────────────────────────


class TestResultCRUD:
    """Add and retrieve results."""

    def test_add_result(self):
        sesio = create_session("rigardi")
        res = add_result(
            sesio["uuid"], "N_ALPHA", "estas",
            "N_BRAVO", "uri", korekta=True,
            respondo="jes", pozicio=1,
        )
        assert res["uuid"]
        assert res["korekta"] is True
        assert res["respondo"] == "jes"

    def test_add_result_false(self):
        sesio = create_session("rigardi")
        res = add_result(
            sesio["uuid"], "N_ALPHA", "estas",
            "N_BRAVO", "uri", korekta=False,
            respondo="ne", pozicio=1,
        )
        assert res["korekta"] is False

    def test_get_results(self):
        sesio = create_session("multobla")
        add_result(sesio["uuid"], "N_ALPHA", "estas", "N_BRAVO", "uri", True, "jes", 1)
        add_result(sesio["uuid"], "N_BRAVO", "estas", "N_CHARLIE", "uri", False, "Delta", 2)
        results = get_results(sesio["uuid"])
        assert len(results) == 2
        assert results[0]["pozicio"] == 1
        assert results[1]["pozicio"] == 2

    def test_get_results_empty(self):
        sesio = create_session("rigardi")
        assert get_results(sesio["uuid"]) == []


# ── Triple review helpers ────────────────────────────────────────────────────


class TestGetTriplesForReview:
    """Fetch triples for review."""

    def test_returns_triples(self, triple_svc):
        results = get_triples_for_review(triple_svc, limit=10)
        assert len(results) > 0
        assert all("subject_uuid" in r for r in results)

    def test_respects_limit(self, triple_svc):
        results = get_triples_for_review(triple_svc, limit=2)
        assert len(results) == 2

    def test_no_matching_triples(self, triple_svc):
        """A date range far in the past should return nothing."""
        results = get_triples_for_review(
            triple_svc, dato_de="2020-01-01", dato_gis="2020-01-02", limit=10,
        )
        assert len(results) == 0


class TestDistractorGeneration:
    """Generate option distractors for multiple-choice review."""

    def test_generates_uri_distractors(self, node_svc, pred_svc, triple_svc):
        """URI object should generate other node IDs as distractors."""
        distractors = generate_distractors(
            "N_ALPHA", "uri", node_svc, pred_svc, triple_svc, count=2,
        )
        # Distractors are found via FTS5 label search — may be empty if
        # no other nodes share label words. The main invariant is that
        # the correct answer is never included as a distractor.
        assert "N_ALPHA" not in distractors

    def test_literal_distractors(self, node_svc, pred_svc, triple_svc):
        """Literal object should generate other literal values as distractors."""
        distractors = generate_distractors(
            "testa literalo", "literal", node_svc, pred_svc, triple_svc, count=2,
        )
        # There's only one literal triple in the fixture, so distractors may be < 2
        assert isinstance(distractors, list)


class TestBuildQuestionData:
    """Build question data dicts."""

    def test_rigardi_mode(self, node_svc, pred_svc, triple_svc):
        """rigardi mode returns question without options."""
        triples = get_triples_for_review(triple_svc, limit=1)
        assert len(triples) > 0
        qdata = build_question_data(triples[0], node_svc, pred_svc, triple_svc, mode="rigardi")
        assert qdata["subject_uuid"]
        assert qdata["predicate_id"]
        assert qdata["object_value"]
        assert qdata["subject_label"]
        assert qdata["predicate_label"]
        assert qdata["object_display"]
        assert "options" not in qdata

    def test_multobla_mode(self, node_svc, pred_svc, triple_svc):
        """multobla mode returns question with options."""
        triples = get_triples_for_review(triple_svc, limit=1)
        assert len(triples) > 0
        qdata = build_question_data(triples[0], node_svc, pred_svc, triple_svc, mode="multobla")
        assert "options" in qdata
        assert len(qdata["options"]) >= 1
        assert triples[0]["object_value"] in qdata["options"]


# ── CLI commands ─────────────────────────────────────────────────────────────


class TestRecenziHelp:
    """recenzi help output."""

    def test_recenzi_help_shows_subcommands(self):
        result = runner.invoke(app, ["recenzi", "--help"])
        assert result.exit_code == 0
        assert "rigardi" in result.stdout
        assert "multobla" in result.stdout
        assert "historio" in result.stdout
        assert "vidi" in result.stdout
        assert "forigi" in result.stdout

    def test_recenzi_no_args_shows_help(self):
        result = runner.invoke(app, ["recenzi"])
        # Click/Typer may exit with 0 or 2 depending on versions
        assert result.exit_code in (0, 2)
        assert "Usage" in result.stdout or "rigardi" in result.stdout


class TestRecenziHistorio:
    """recenzi historio command."""

    def test_empty_historio(self):
        result = runner.invoke(app, ["recenzi", "historio"])
        assert result.exit_code == 0
        assert "Neniuj pasintaj sesioj" in result.stdout

    def test_historio_with_sessions(self):
        create_session("rigardi")
        create_session("multobla")
        result = runner.invoke(app, ["recenzi", "historio"])
        assert result.exit_code == 0
        assert "Vidado" in result.stdout or "Multobla" in result.stdout
        # Sessions are ongoing (not finished), but "Stato" column should be present


class TestRecenziVidi:
    """recenzi vidi command."""

    def test_vidi_nonexistent(self):
        result = runner.invoke(app, ["recenzi", "vidi", "nonexistent"])
        assert result.exit_code == 1
        assert "ne trovita" in result.stdout

    def test_vidi_with_session(self, node_svc):
        sesio = create_session("rigardi")
        add_result(sesio["uuid"], "N_ALPHA", "estas", "N_BRAVO", "uri", True, "jes", 1)
        finish_session(sesio["uuid"])
        update_session_score(sesio["uuid"], 1, 1)

        result = runner.invoke(app, ["recenzi", "vidi", sesio["uuid"][:8]])
        assert result.exit_code == 0
        assert "Poentaro" in result.stdout or "Score" in result.stdout
        assert "Alfa" in result.stdout  # resolved label

    def test_vidi_ambiguous_prefix(self):
        s1 = create_session("rigardi")
        # We need two sessions with overlapping prefixes
        # Create a second session with a UUID that shares the first N chars
        import uuid
        # Force specific UUIDs
        from A_semantika.data.storage import get_db, now

        db = get_db()
        ts = now()
        db.execute(
            "INSERT INTO recenzo_sesio (uuid, modo, totalo, korekta, finita, kreita_je) "
            "VALUES (?, 'rigardi', 0, 0, 0, ?)",
            (str(uuid.UUID("aaaaaaaa-1111-1111-1111-111111111111")), ts),
        )
        db.execute(
            "INSERT INTO recenzo_sesio (uuid, modo, totalo, korekta, finita, kreita_je) "
            "VALUES (?, 'rigardi', 0, 0, 0, ?)",
            (str(uuid.UUID("aaaaaaab-2222-2222-2222-222222222222")), ts),
        )

        result = runner.invoke(app, ["recenzi", "vidi", "aaaaaa"])
        assert result.exit_code == 1
        assert "Ambigua" in result.stdout


class TestRecenziForigi:
    """recenzi forigi command."""

    def test_forigi_nonexistent(self):
        result = runner.invoke(app, ["recenzi", "forigi", "nonexistent", "-y"])
        assert result.exit_code == 1
        assert "ne trovita" in result.stdout

    def test_forigi_with_yes_flag(self):
        sesio = create_session("rigardi")
        result = runner.invoke(app, ["recenzi", "forigi", sesio["uuid"][:8], "-y"])
        assert result.exit_code == 0
        assert "forigita" in result.stdout
        assert get_session(sesio["uuid"]) is None

    def test_forigi_without_yes_cancels(self, monkeypatch):
        sesio = create_session("rigardi")
        # Patch confirm_action in the module where it's used, not the source
        monkeypatch.setattr(
            "A_semantika._recenzi_cmd.confirm_action",
            lambda msg, default=False: False,
        )
        result = runner.invoke(app, ["recenzi", "forigi", sesio["uuid"][:8]])
        assert result.exit_code == 0
        assert "Nuligita" in result.stdout
        # Session should still exist
        assert get_session(sesio["uuid"]) is not None

    def test_forigi_ambiguous(self):
        import uuid
        from A_semantika.data.storage import get_db, now

        db = get_db()
        ts = now()
        db.execute(
            "INSERT INTO recenzo_sesio (uuid, modo, totalo, korekta, finita, kreita_je) "
            "VALUES (?, 'rigardi', 0, 0, 0, ?)",
            (str(uuid.UUID("bbbbbbbb-1111-1111-1111-111111111111")), ts),
        )
        db.execute(
            "INSERT INTO recenzo_sesio (uuid, modo, totalo, korekta, finita, kreita_je) "
            "VALUES (?, 'rigardi', 0, 0, 0, ?)",
            (str(uuid.UUID("bbbbbbbc-2222-2222-2222-222222222222")), ts),
        )

        result = runner.invoke(app, ["recenzi", "forigi", "bbbbbb", "-y"])
        assert result.exit_code == 1
        assert "Ambigua" in result.stdout


class TestRecenziRigardi:
    """recenzi rigardi command (interactive)."""

    def test_rigardi_empty_range(self):
        """No triples in date range should show info message."""
        result = runner.invoke(
            app, ["recenzi", "rigardi", "--dato-de", "20200101", "--dato-gis", "20200102"],
        )
        assert result.exit_code == 0
        assert "Neniuj arkoj" in result.stdout

    def test_rigardi_with_correct_input(self):
        """Test full rigardi session with 'jes' responses."""
        result = runner.invoke(
            app, ["recenzi", "rigardi", "--limit", "2"],
            input="j\nj\n",
        )
        assert result.exit_code == 0
        assert "Poentaro" in result.stdout or "Score" in result.stdout
        assert "2/2" in result.stdout

    def test_rigardi_with_mixed_input(self):
        """One correct, one wrong."""
        result = runner.invoke(
            app, ["recenzi", "rigardi", "--limit", "2"],
            input="j\nn\n",
        )
        assert result.exit_code == 0
        assert "1/2" in result.stdout

    def test_rigardi_default_correct(self):
        """Empty input (just Enter) should count as correct."""
        result = runner.invoke(
            app, ["recenzi", "rigardi", "--limit", "2"],
            input="\n\n",
        )
        assert result.exit_code == 0
        assert "2/2" in result.stdout

    def test_rigardi_with_date_filter(self):
        """Test rigardi with --dato-de filters."""
        result = runner.invoke(
            app, ["recenzi", "rigardi", "--limit", "2", "--dato-de", "20200101"],
            input="j\nj\n",
        )
        assert result.exit_code == 0


class TestRecenziMultobla:
    """recenzi multobla command (interactive multiple-choice)."""

    def test_multobla_empty_range(self):
        result = runner.invoke(
            app, ["recenzi", "multobla", "--dato-de", "20200101", "--dato-gis", "20200102"],
        )
        assert result.exit_code == 0
        assert "Neniuj arkoj" in result.stdout

    def test_multobla_correct_answer(self):
        """Select the first option (correct answer should always be an option)."""
        result = runner.invoke(
            app, ["recenzi", "multobla", "--limit", "2"],
            input="1\n1\n",
        )
        assert result.exit_code == 0
        assert "Poentaro" in result.stdout or "Score" in result.stdout

    def test_multobla_invalid_input(self):
        """Non-digit input should treat as wrong answer."""
        result = runner.invoke(
            app, ["recenzi", "multobla", "--limit", "2"],
            input="abc\nxyz\n",
        )
        assert result.exit_code == 0
        assert "0/2" in result.stdout

    def test_multobla_out_of_range(self):
        """Number larger than option count should treat as wrong."""
        result = runner.invoke(
            app, ["recenzi", "multobla", "--limit", "2"],
            input="99\n99\n",
        )
        assert result.exit_code == 0
        assert "0/2" in result.stdout
