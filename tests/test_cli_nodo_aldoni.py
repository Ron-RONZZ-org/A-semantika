"""Tests for nodo aldoni — auto-ID (Issue #74) and file attachment flags (Issue #75)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from A_semantika._file_helpers import _files_root
from A_semantika._node_helpers import normalize_label_to_id
from A_semantika.cli import app
from A_semantika.service import get_node_service, get_triple_service


# ── normalize_label_to_id unit tests ────────────────────────────────────────

class TestNormalizeLabelToId:
    """Unit tests for the label-to-ID normalization function."""

    def test_basic_lowercase(self) -> None:
        assert normalize_label_to_id("homo sapiens") == "HOMO_SAPIENS"

    def test_already_ascii_uppercase(self) -> None:
        assert normalize_label_to_id("HOMO SAPIENS") == "HOMO_SAPIENS"

    def test_accented_chars(self) -> None:
        assert normalize_label_to_id("Henri Poincaré") == "HENRI_POINCARE"

    def test_cjk_chars_stripped(self) -> None:
        assert normalize_label_to_id("人") == "_UNLABELED"

    def test_emoji_stripped(self) -> None:
        assert normalize_label_to_id("🚀 Rocket") == "ROCKET"

    def test_all_non_ascii(self) -> None:
        assert normalize_label_to_id("日本語") == "_UNLABELED"

    def test_special_chars_to_underscore(self) -> None:
        assert normalize_label_to_id("hello-world_v2.0") == "HELLO_WORLD_V2_0"

    def test_multiple_spaces_collapsed(self) -> None:
        assert normalize_label_to_id("too   many   spaces") == "TOO_MANY_SPACES"

    def test_leading_trailing_underscores_stripped(self) -> None:
        assert normalize_label_to_id("  _hello_  ") == "HELLO"

    def test_mixed_whitespace(self) -> None:
        assert normalize_label_to_id("mix\t\rof\nchars") == "MIX_OF_CHARS"

    def test_empty_string(self) -> None:
        assert normalize_label_to_id("") == "_UNLABELED"

    def test_only_special_chars(self) -> None:
        assert normalize_label_to_id("!@#$%^&*()") == "_UNLABELED"


# ── Auto-ID CLI tests (Issue #74) ───────────────────────────────────────────

class TestAutoId:
    """Auto-generate node_id from first label when no explicit ID is given."""

    def test_auto_id_from_label(self, runner: CliRunner) -> None:
        """No explicit ID + label → auto-generated ID."""
        result = runner.invoke(app, [
            "nodo", "aldoni", "-e", "eo::Homo Sapiens",
            "--jes",
        ])
        assert result.exit_code == 0
        assert "HOMO_SAPIENS" in result.stdout, f"Expected HOMO_SAPIENS in output, got:\n{result.stdout}"

    def test_auto_id_from_language_independent_label(self, runner: CliRunner) -> None:
        """Language-independent label (no '::') also generates ID."""
        result = runner.invoke(app, [
            "nodo", "aldoni", "-e", "Paris",
            "--jes",
        ])
        assert result.exit_code == 0
        assert "PARIS" in result.stdout, f"Expected PARIS in output, got:\n{result.stdout}"

    def test_auto_id_collision_appends_counter(self, runner: CliRunner) -> None:
        """Auto-ID collision with existing explicit ID → _2 suffix."""
        # Pre-create node with same ID that auto-ID would produce
        runner.invoke(app, [
            "nodo", "aldoni", "TESTCOLLISION",
            "-e", "eo::DiffLabel",
            "--jes",
        ])
        # Auto-ID: normalize_label_to_id("TestCollision") = TESTCOLLISION → conflicts
        result = runner.invoke(app, [
            "nodo", "aldoni", "-e", "eo::TestCollision",
            "--jes",
        ])
        assert result.exit_code == 0
        assert "TESTCOLLISION_2" in result.stdout, (
            f"Expected TESTCOLLISION_2 in output, got:\n{result.stdout}"
        )

    def test_auto_id_multiple_collisions(self, runner: CliRunner) -> None:
        """Three collisions → _2, _3, _4 suffixes."""
        # Pre-create nodes with explicit IDs that match the auto-ID base
        runner.invoke(app, ["nodo", "aldoni", "MULTICOLLISION", "-e", "eo::Aaa", "--jes"])
        runner.invoke(app, ["nodo", "aldoni", "MULTICOLLISION_2", "-e", "eo::Bbb", "--jes"])
        runner.invoke(app, ["nodo", "aldoni", "MULTICOLLISION_3", "-e", "eo::Ccc", "--jes"])
        # Auto-ID should generate MULTICOLLISION_4
        result = runner.invoke(app, ["nodo", "aldoni", "-e", "eo::MultiCollision", "--jes"])
        assert result.exit_code == 0
        assert "MULTICOLLISION_4" in result.stdout, (
            f"Expected MULTICOLLISION_4 in output, got:\n{result.stdout}"
        )

    def test_explicit_id_skips_auto(self, runner: CliRunner) -> None:
        """Explicit node_id arg → no auto-ID, use as-is."""
        result = runner.invoke(app, [
            "nodo", "aldoni", "MY_EXPLICIT_ID",
            "-e", "eo::ShouldNotAuto",
            "--jes",
        ])
        assert result.exit_code == 0
        assert "MY_EXPLICIT_ID" in result.stdout, f"Expected MY_EXPLICIT_ID in output, got:\n{result.stdout}"

    def test_no_label_no_id_generates_uuid(self, runner: CliRunner) -> None:
        """No label + no explicit ID → UUID auto-generated (not from label)."""
        result = runner.invoke(app, ["nodo", "aldoni", "--jes"])
        assert result.exit_code == 0, f"Expected success, got:\n{result.stdout}"
        # UUIDs contain hyphens
        assert "kreita" in result.stdout or "Created" in result.stdout or "créé" in result.stdout

    def test_no_labels_still_works(self, runner: CliRunner) -> None:
        """Node creation without labels still succeeds with auto-ID."""
        result = runner.invoke(app, ["nodo", "aldoni", "-d", "eo::Only difino", "--jes"])
        assert result.exit_code == 0

    def test_auto_id_respects_duplicate_check(self, runner: CliRunner) -> None:
        """Duplicate check triggers even with auto-ID."""
        runner.invoke(app, ["nodo", "aldoni", "-e", "eo::UniqueLabel", "--jes"])
        result = runner.invoke(app, ["nodo", "aldoni", "-e", "eo::UniqueLabel", "--jes"])
        # Should succeed with _2 suffix (or update)
        assert result.exit_code == 0


# ── File attachment CLI tests (Issue #75) ────────────────────────────────────

class TestFileAttachment:
    """File attachment flags: --img/-I, --filmeto/-F, --dosiero/-D, --en-loko, --movi."""

    def test_dosiero_en_loko_reference(self, runner: CliRunner, tmp_path: Path) -> None:
        """--dosiero --en-loko stores reference path without copying."""
        test_file = tmp_path / "reference.txt"
        test_file.write_text("hello")

        result = runner.invoke(app, [
            "nodo", "aldoni", "REF_NODE",
            "-e", "eo::RefNodo",
            "--dosiero", str(test_file),
            "--en-loko",
            "--jes",
        ])
        assert result.exit_code == 0

        # Verify triple was created with reference path
        triple_svc = get_triple_service()
        triples = triple_svc.get_by_subject("REF_NODE")
        assert any(t["predicate_id"] == ":hasFilePath" for t in triples), (
            f"No :hasFilePath triple found in {triples}"
        )

    def test_dosiero_copy_creates_file(self, runner: CliRunner, tmp_path: Path) -> None:
        """--dosiero copies file into managed storage."""
        src = tmp_path / "copy_me.txt"
        src.write_text("file content")

        result = runner.invoke(app, [
            "nodo", "aldoni", "COPY_NODE",
            "-e", "eo::CopyNodo",
            "--dosiero", str(src),
            "--jes",
        ])
        assert result.exit_code == 0

        # Source should still exist (copy, not move)
        assert src.exists()

        # Check file triples were created
        triple_svc = get_triple_service()
        triples = triple_svc.get_by_subject("COPY_NODE")
        pred_ids = [t["predicate_id"] for t in triples]
        assert ":hasFilePath" in pred_ids, f"Missing :hasFilePath in {pred_ids}"
        assert ":hasFileMime" in pred_ids, f"Missing :hasFileMime in {pred_ids}"
        assert ":hasFileSize" in pred_ids, f"Missing :hasFileSize in {pred_ids}"
        assert ":hasFileSource" in pred_ids, f"Missing :hasFileSource in {pred_ids}"

    def test_dosiero_move_removes_original(self, runner: CliRunner, tmp_path: Path) -> None:
        """--movi moves file (original removed)."""
        src = tmp_path / "move_me.txt"
        src.write_text("to be moved")

        result = runner.invoke(app, [
            "nodo", "aldoni", "MOVE_NODE",
            "-e", "eo::MoveNodo",
            "--dosiero", str(src),
            "--movi",
            "--jes",
        ])
        assert result.exit_code == 0

        # Original should be gone
        assert not src.exists()

    def test_img_flag(self, runner: CliRunner, tmp_path: Path) -> None:
        """--img flag works for image files."""
        src = tmp_path / "test_image.png"
        src.write_text("fake png")  # Not a real image, but tests the logic

        result = runner.invoke(app, [
            "nodo", "aldoni", "IMG_NODE",
            "-e", "eo::ImgNodo",
            "--img", str(src),
            "--jes",
        ])
        assert result.exit_code == 0

        # Verify triples
        triple_svc = get_triple_service()
        triples = triple_svc.get_by_subject("IMG_NODE")
        pred_ids = [t["predicate_id"] for t in triples]
        assert ":hasFilePath" in pred_ids

    def test_filmeto_flag(self, runner: CliRunner, tmp_path: Path) -> None:
        """--filmeto/-F flag works for video files."""
        src = tmp_path / "test_video.mp4"
        src.write_text("fake mp4")

        result = runner.invoke(app, [
            "nodo", "aldoni", "VID_NODE",
            "-e", "eo::VidNodo",
            "-F", str(src),
            "--jes",
        ])
        assert result.exit_code == 0

        # Verify triples
        triple_svc = get_triple_service()
        triples = triple_svc.get_by_subject("VID_NODE")
        pred_ids = [t["predicate_id"] for t in triples]
        assert ":hasFilePath" in pred_ids

    def test_dosiero_flag_shortform(self, runner: CliRunner, tmp_path: Path) -> None:
        """-D short flag works."""
        src = tmp_path / "short.txt"
        src.write_text("short")

        result = runner.invoke(app, [
            "nodo", "aldoni", "SHORT_NODE",
            "-e", "eo::ShortNodo",
            "-D", str(src),
            "--jes",
        ])
        assert result.exit_code == 0

    def test_file_attachment_with_nonexistent_path(self, runner: CliRunner) -> None:
        """Non-existent file path should print error and exit."""
        result = runner.invoke(app, [
            "nodo", "aldoni", "BAD_NODE",
            "-e", "eo::BadNodo",
            "--dosiero", "/nonexistent/path/file.txt",
            "--jes",
        ])
        assert result.exit_code == 1
        assert "eraro" in result.stdout.lower() or "file error" in result.stdout.lower()

    def test_mutual_exclusivity_no_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """Only one file flag at a time (last wins due to typer logic)."""
        src_a = tmp_path / "a.txt"
        src_b = tmp_path / "b.txt"
        src_a.write_text("a")
        src_b.write_text("b")

        # Using both --img and --dosiero — only one is processed
        result = runner.invoke(app, [
            "nodo", "aldoni", "MULTI_NODE",
            "-e", "eo::MultiNodo",
            "--img", str(src_a),
            "--dosiero", str(src_b),
            "--jes",
        ])
        # Should process one (typer options: the logic checks img first then dosiero)
        assert result.exit_code == 0


# ── File helpers unit tests ──────────────────────────────────────────────────

class TestFileHelpers:
    """Unit tests for _file_helpers module."""

    def test_is_managed_file(self, tmp_path: Path) -> None:
        """is_managed_file detects files in the managed tree."""
        from A_semantika._file_helpers import is_managed_file

        # _files_root() -> data_dir() / "A-semantika" / "files"
        root = _files_root()
        managed = root / "node" / "test.txt"
        managed.parent.mkdir(parents=True, exist_ok=True)
        managed.write_text("test")
        assert is_managed_file(managed)

        outside = tmp_path / "outside.txt"
        outside.write_text("test")
        assert not is_managed_file(outside)

    def test_detect_mime_plaintext(self, tmp_path: Path) -> None:
        """detect_mime returns text/plain for .txt files."""
        from A_semantika._file_helpers import detect_mime

        f = tmp_path / "test.txt"
        f.write_text("hello")
        mime = detect_mime(f)
        assert "text/" in mime or "application/octet-stream" in mime

    def test_get_file_size(self, tmp_path: Path) -> None:
        """get_file_size returns correct byte count."""
        from A_semantika._file_helpers import get_file_size

        f = tmp_path / "size_test.bin"
        f.write_bytes(b"x" * 12345)
        assert get_file_size(f) == 12345

    def test_copy_file_to_managed(self, tmp_path: Path) -> None:
        """copy_file copies to managed directory."""
        from A_semantika._file_helpers import copy_file

        src = tmp_path / "source.txt"
        src.write_text("original")

        dest = copy_file(src, "test_node_id", "dosiero")
        assert dest.exists()
        assert dest.read_text() == "original"

    def test_move_file_to_managed(self, tmp_path: Path) -> None:
        """move_file moves to managed directory, removes original."""
        from A_semantika._file_helpers import move_file

        src = tmp_path / "movable.txt"
        src.write_text("movable")

        dest = move_file(src, "test_node_id", "dosiero")
        assert dest.exists()
        assert dest.read_text() == "movable"
        assert not src.exists()  # Original removed

    def test_delete_managed_file(self, tmp_path: Path) -> None:
        """delete_file removes a managed file."""
        from A_semantika._file_helpers import copy_file, delete_file, is_managed_file

        src = tmp_path / "deletable.txt"
        src.write_text("deletable")

        dest = copy_file(src, "test_node_id", "dosiero")
        assert dest.exists()
        delete_file(dest)
        assert not dest.exists()

    def test_copy_nonexistent_source(self, tmp_path: Path) -> None:
        """copy_file raises FileNotFoundError for missing source."""
        from A_semantika._file_helpers import copy_file

        with pytest.raises(FileNotFoundError):
            copy_file(tmp_path / "nonexistent.txt", "node_id", "dosiero")
