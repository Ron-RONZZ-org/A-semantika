"""Triple CLI tests: aldoni, forigi, serci, vidi."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from A_semantika.cli import app


def test_triple_aldoni_requires_node_and_predicate(runner: CliRunner) -> None:
    """Triple aldoni requires existing nodes and predicates."""
    # Create a node
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Hundo", "-y"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Mamulo", "-y"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "-y"])

    # Get node UUIDs
    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if "Hundo" in l or "Mamulo" in l]
    uuid_map = {}
    for line in lines:
        parts = line.strip().split()
        if parts:
            uuid_map["Hundo" if "Hundo" in line else "Mamulo"] = parts[0]

    if "Hundo" in uuid_map and "Mamulo" in uuid_map:
        result = runner.invoke(app, [
            "aldoni",
            uuid_map["Hundo"],
            "rdf:type",
            uuid_map["Mamulo"],
            "-y",
        ])
        assert result.exit_code == 0, f"aldoni failed: {result.stdout}"
        assert "kreita" in result.stdout or "Arc" in result.stdout


def test_triple_serci(runner: CliRunner) -> None:
    """Searching triples should work end-to-end."""
    # Setup
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Hundo", "-y"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Mamulo", "-y"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "-y"])

    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    uuids = [l.split()[0] for l in lines if len(l.split()) >= 1]

    if len(uuids) >= 2:
        runner.invoke(app, ["aldoni", uuids[0], "rdf:type", uuids[1], "-y"])
        result = runner.invoke(app, ["serci", "--subjekto", uuids[0]])
        assert result.exit_code == 0


def test_triple_vidi(runner: CliRunner) -> None:
    """Viewing triples for a subject should work."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Hundo", "-y"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Mamulo", "-y"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "-y"])

    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    uuids = [l.split()[0] for l in lines if len(l.split()) >= 1]

    if len(uuids) >= 2:
        runner.invoke(app, ["aldoni", uuids[0], "rdf:type", uuids[1], "-y"])
        result = runner.invoke(app, ["vidi", uuids[0]])
        assert result.exit_code == 0
        assert "rdf:type" in result.stdout or "tipo" in result.stdout


def test_triple_aldoni_jes_flag(runner: CliRunner) -> None:
    """--jes flag should skip confirmation for triple aldoni."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::SubjJes", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::ObjJes", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    uuids = [l.split()[0] for l in lines if len(l.split()) >= 1]

    if len(uuids) >= 2:
        result = runner.invoke(app, [
            "aldoni", uuids[0], "rdf:type", uuids[1], "--jes",
        ])
        assert result.exit_code == 0, f"aldoni --jes failed: {result.stdout}"
        assert "kreita" in result.stdout or "Arc" in result.stdout or "created" in result.stdout


def test_triple_serci_by_subject_label(runner: CliRunner) -> None:
    """serci --subject should accept labels, not just UUID prefixes."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Liono", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Besto", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    uuids = {l.split(" ", 1)[1] if len(l.split()) > 1 else l.split()[0]: l.split()[0]
             for l in lines}

    liono_uuid = next((uid for label, uid in uuids.items() if "Liono" in label), None)
    besto_uuid = next((uid for label, uid in uuids.items() if "Besto" in label), None)

    if liono_uuid and besto_uuid:
        runner.invoke(app, ["aldoni", liono_uuid, "rdf:type", besto_uuid, "--jes"])
        result = runner.invoke(app, ["serci", "--subjekto", "Liono"])
        assert result.exit_code == 0
        assert "Liono" in result.stdout


def test_triple_serci_by_predicate_label(runner: CliRunner) -> None:
    """serci --predicate should accept partial names."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Urso", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Mamulo2", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    ls_result = runner.invoke(app, ["nodo", "ls"])
    urso_uuid = None
    mamulo2_uuid = None
    for line in ls_result.stdout.strip().split("\n"):
        parts = line.strip().split()
        if len(parts) >= 2:
            label = " ".join(parts[1:])
            if "Urso" in label:
                urso_uuid = parts[0]
            elif "Mamulo2" in label:
                mamulo2_uuid = parts[0]

    if urso_uuid and mamulo2_uuid:
        runner.invoke(app, ["aldoni", urso_uuid, "rdf:type", mamulo2_uuid, "--jes"])
        result = runner.invoke(app, ["serci", "--predikato", "tipo"])
        assert result.exit_code == 0


def test_triple_serci_by_object_label(runner: CliRunner) -> None:
    """serci --object should accept labels, not just UUID prefixes."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Rib-o", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Fiŝo", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    ls_result = runner.invoke(app, ["nodo", "ls"])
    fish_uuid = None
    for line in ls_result.stdout.strip().split("\n"):
        parts = line.strip().split()
        if len(parts) >= 2 and "Fiŝo" in " ".join(parts[1:]):
            fish_uuid = parts[0]

    if fish_uuid:
        # Find the subject UUID
        rib_o_uuid = None
        for line in ls_result.stdout.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) >= 2 and "Rib-o" in " ".join(parts[1:]):
                rib_o_uuid = parts[0]
                break

        if rib_o_uuid and fish_uuid:
            runner.invoke(app, ["aldoni", rib_o_uuid, "rdf:type", fish_uuid, "--jes"])
            result = runner.invoke(app, ["serci", "--objekto", "Fiŝo"])
            assert result.exit_code == 0


def test_triple_forigi_full_triplet_backward_compat(runner: CliRunner) -> None:
    """forigi with full SPO triplet should still work (backward compat)."""
    subj_uuid = "c1111111-1111-1111-1111-111111111111"
    obj_uuid = "c2222222-2222-2222-2222-222222222222"
    runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::ForigCompSubj", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", obj_uuid, "-e", "eo::ForigCompObj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    # Add triple
    result = runner.invoke(app, ["aldoni", subj_uuid[:8], "rdf:type", obj_uuid[:8], "--jes"])
    assert result.exit_code == 0

    # Delete with full SPO
    result = runner.invoke(app, ["forigi", subj_uuid[:8], "rdf:type", obj_uuid[:8], "--jes"])
    assert result.exit_code == 0
    assert "forigita" in result.stdout or "Arc deleted" in result.stdout


def test_triple_forigi_interactive_subject_only(runner: CliRunner) -> None:
    """forigi with only subject should show interactive picker."""
    subj_uuid = "a1111111-1111-1111-1111-111111111111"
    obj_uuid = "a2222222-2222-2222-2222-222222222222"
    runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::IntSubj", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", obj_uuid, "-e", "eo::IntObj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    # Add triple
    r = runner.invoke(app, ["aldoni", subj_uuid[:8], "rdf:type", obj_uuid[:8], "--jes"])
    assert r.exit_code == 0, f"Triple aldoni failed: {r.stdout}"

    # Delete with only subject → interactive picker
    result = runner.invoke(app, ["forigi", subj_uuid[:8], "--jes"], input="1\n")
    assert result.exit_code in (0,), f"Interactive forigi failed: {result.stdout}"


def test_triple_forigi_interactive_subject_and_predicate(runner: CliRunner) -> None:
    """forigi with subject+predicate should show filtered picker."""
    subj_uuid = "b1111111-1111-1111-1111-111111111111"
    obj_uuid = "b2222222-2222-2222-2222-222222222222"
    runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::IntSPSubj", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", obj_uuid, "-e", "eo::IntSPObj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    # Add triple
    r = runner.invoke(app, ["aldoni", subj_uuid[:8], "rdf:type", obj_uuid[:8], "--jes"])
    assert r.exit_code == 0, f"Triple aldoni failed: {r.stdout}"

    # subject + predicate → filtered picker
    result = runner.invoke(app, ["forigi", subj_uuid[:8], "rdf:type", "--jes"], input="1\n")
    assert result.exit_code in (0,), f"Interactive forigi SP failed: {result.stdout}"


def test_triple_forigi_interactive_no_match(runner: CliRunner) -> None:
    """forigi interactive with no matches should show error."""
    result = runner.invoke(app, [
        "forigi", "nonexistent", "--jes",
    ])
    assert result.exit_code == 1
    assert "Neniuj" in result.stdout or "No matching" in result.stdout


def test_triple_aldoni_i_alias(runner: CliRunner) -> None:
    """The -i flag should work as an alias for --int."""
    runner.invoke(app, ["nodo", "aldoni", "IntSubj", "-e", "eo::IntSubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "wdt:P1082", "-e", "eo::populacho", "--jes"])

    result = runner.invoke(app, [
        "aldoni", "IntSubj", "wdt:P1082", "42", "-i", "--jes",
    ])
    assert result.exit_code == 0, f"-i alias failed: {result.stdout}"
    assert "kreita" in result.stdout or "created" in result.stdout or "Arc" in result.stdout


def test_triple_aldoni_str_dosiero_happy(runner: CliRunner, tmp_path: str) -> None:
    """--str-dosiero should read a .md file and store as string literal."""
    runner.invoke(app, ["nodo", "aldoni", "MdSubj", "-e", "eo::MdSubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    from pathlib import Path
    md_file = Path(tmp_path) / "test.md"
    md_file.write_text("# Noto\n\nĈi tio estas testa noto.", encoding="utf-8")

    result = runner.invoke(app, [
        "aldoni", "MdSubj", "rdf:type", "--str-dosiero", str(md_file), "--jes",
    ])
    assert result.exit_code == 0, f"--str-dosiero failed: {result.stdout}"
    assert "kreita" in result.stdout or "created" in result.stdout or "Arc" in result.stdout


def test_triple_aldoni_str_dosiero_file_not_found(runner: CliRunner) -> None:
    """--str-dosiero should give a clear error when file does not exist."""
    runner.invoke(app, ["nodo", "aldoni", "NotFoundSubj", "-e", "eo::NotFoundSubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    result = runner.invoke(app, [
        "aldoni", "NotFoundSubj", "rdf:type", "--str-dosiero", "/nonexistent/file.md", "--jes",
    ])
    assert result.exit_code == 1
    assert "ne trovita" in result.stdout or "not found" in result.stdout or "non trouvé" in result.stdout


def test_triple_aldoni_needs_object_or_str_dosiero(runner: CliRunner) -> None:
    """At least one of OBJEKTO or --str-dosiero must be provided."""
    runner.invoke(app, ["nodo", "aldoni", "NoObjSubj", "-e", "eo::NoObjSubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    result = runner.invoke(app, [
        "aldoni", "NoObjSubj", "rdf:type", "--jes",
    ])
    assert result.exit_code == 1
    assert "Bezonas" in result.stdout or "Requires" in result.stdout or "Nécessite" in result.stdout


def test_triple_aldoni_str_dosiero_mutual_exclusion(runner: CliRunner) -> None:
    """Object positional arg and --str-dosiero should be mutually exclusive."""
    result = runner.invoke(app, [
        "aldoni", "SomeSubj", "rdf:type", "SomeObj", "--str-dosiero", "test.md", "--jes",
    ])
    assert result.exit_code == 1
    assert "Ne eblas" in result.stdout or "Cannot" in result.stdout or "Impossible" in result.stdout


def test_serci_backward_compat_uuid_prefix(runner: CliRunner) -> None:
    """serci --subject should still work with UUID prefixes."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::CompatTest", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    uuid_prefix = None
    for line in ls_result.stdout.strip().split("\n"):
        parts = line.strip().split()
        if len(parts) >= 2 and "CompatTest" in " ".join(parts[1:]):
            uuid_prefix = parts[0]
            break

    if uuid_prefix:
        result = runner.invoke(app, ["serci", "--subjekto", uuid_prefix])
        assert result.exit_code == 0
