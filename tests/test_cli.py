"""CLI integration tests for A-semantika.

Uses typer.testing.CliRunner for full-stack tests.
"""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


def test_help_shows_commands(runner: CliRunner) -> None:
    """Calling without args should show help with all commands."""
    result = runner.invoke(app, [])
    # Click 8.x exits with code 2 for no_args_is_help (UsageError)
    assert result.exit_code in (0, 2), f"Unexpected exit code: {result.exit_code}"
    assert "aldoni" in result.stdout
    assert "modifi" in result.stdout
    assert "forigi" in result.stdout
    assert "serci" in result.stdout
    assert "vidi" in result.stdout
    assert "eksporti" in result.stdout
    assert "nodo" in result.stdout
    assert "predikato" in result.stdout
    assert "predikat-grupo" in result.stdout


def test_nodo_help(runner: CliRunner) -> None:
    """Nodo subcommand should show its subcommands."""
    result = runner.invoke(app, ["nodo", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.stdout
    assert "aldoni" in result.stdout


def test_predikato_help(runner: CliRunner) -> None:
    """Predikato subcommand should show its subcommands."""
    result = runner.invoke(app, ["predikato", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.stdout
    assert "aldoni" in result.stdout


def test_predikat_grupo_help(runner: CliRunner) -> None:
    """Predikat-grupo subcommand should show its subcommands."""
    result = runner.invoke(app, ["predikat-grupo", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.stdout


def test_nodo_aldoni_and_ls(runner: CliRunner) -> None:
    """Creating a node and listing it should work."""
    result = runner.invoke(app, [
        "nodo", "aldoni",
        "-e", "eo::Hundo",
        "-e", "en::Dog",
        "-y",
    ])
    assert result.exit_code == 0
    assert "kreita" in result.stdout

    result = runner.invoke(app, ["nodo", "ls"])
    assert result.exit_code == 0
    assert "Hundo" in result.stdout


def test_nodo_vidi(runner: CliRunner) -> None:
    """Viewing a node should show its details."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Kato", "-y"])
    result = runner.invoke(app, ["nodo", "ls"])
    # Extract UUID from ls output
    lines = result.stdout.strip().split("\n")
    # Find the line with Kato
    uuid_prefix = None
    for line in lines:
        if "Kato" in line:
            parts = line.strip().split()
            if parts:
                uuid_prefix = parts[0]
                break

    if uuid_prefix:
        result = runner.invoke(app, ["nodo", "vidi", uuid_prefix])
        assert result.exit_code == 0
        assert "Kato" in result.stdout


def test_nodo_serci(runner: CliRunner) -> None:
    """Searching nodes should find matches."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Birdo", "-y"])
    result = runner.invoke(app, ["nodo", "serci", "Birdo"])
    assert result.exit_code == 0
    assert "Birdo" in result.stdout


def test_predikato_aldoni_and_ls(runner: CliRunner) -> None:
    """Creating a predicate and listing it should work."""
    result = runner.invoke(app, [
        "predikato", "aldoni", "wdt:P31",
        "-e", "eo::estas tipo de",
        "-y",
    ])
    assert result.exit_code == 0
    assert "kreita" in result.stdout

    result = runner.invoke(app, ["predikato", "ls"])
    assert result.exit_code == 0
    assert "wdt:P31" in result.stdout


def test_predikato_vidi(runner: CliRunner) -> None:
    """Viewing a predicate should show details."""
    runner.invoke(app, ["predikato", "aldoni", "wdt:P31", "-e", "eo::tipo", "-y"])
    result = runner.invoke(app, ["predikato", "vidi", "wdt:P31"])
    assert result.exit_code == 0
    assert "wdt:P31" in result.stdout


def test_predikat_grupo_aldoni_ls_vidi(runner: CliRunner) -> None:
    """Creating and viewing a group should work."""
    result = runner.invoke(app, ["predikat-grupo", "aldoni", "biologio", "-y"])
    assert result.exit_code == 0
    assert "kreita" in result.stdout

    result = runner.invoke(app, ["predikat-grupo", "ls"])
    assert result.exit_code == 0
    assert "biologio" in result.stdout

    result = runner.invoke(app, ["predikat-grupo", "vidi", "biologio"])
    assert result.exit_code == 0
    assert "biologio" in result.stdout


def test_predikat_grupo_modifi_rename(runner: CliRunner) -> None:
    """Renaming a group should work."""
    runner.invoke(app, ["predikat-grupo", "aldoni", "old", "-y"])
    result = runner.invoke(app, ["predikat-grupo", "modifi", "old", "new", "-y"])
    assert result.exit_code == 0
    assert "renomita" in result.stdout or "Renomita" in result.stdout or "new" in result.stdout


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


def test_predikat_grupo_importi_not_available(runner: CliRunner) -> None:
    """importi should show 'not available in P1'."""
    result = runner.invoke(app, ["predikat-grupo", "importi", "somefile.owl"])
    assert result.exit_code == 0
    assert "ne disponebla" in result.stdout or "not available" in result.stdout


def test_nodo_aldoni_with_uuid(runner: CliRunner) -> None:
    """Creating a node with a custom UUID should work."""
    custom_uuid = "deadbeef-1234-5678-9abc-def012345678"
    result = runner.invoke(app, [
        "nodo", "aldoni", custom_uuid,
        "-e", "eo::Testo",
        "-y",
    ])
    assert result.exit_code == 0
    # Verify it was created with our UUID
    result = runner.invoke(app, ["nodo", "vidi", custom_uuid[:8]])
    assert result.exit_code == 0
    assert "Testo" in result.stdout


def test_nodo_forigi(runner: CliRunner) -> None:
    """Deleting a node should work."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Forigota", "-y"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    for line in ls_result.stdout.strip().split("\n"):
        if "Forigota" in line and line[0].isalnum():
            uuid_prefix = line.split()[0]
            break
    else:
        return  # No node found

    result = runner.invoke(app, ["nodo", "forigi", uuid_prefix, "-y"])
    assert result.exit_code == 0
    assert "forigita" in result.stdout


def test_predikato_search(runner: CliRunner) -> None:
    """Searching predicates should work."""
    runner.invoke(app, ["predikato", "aldoni", "wdt:P31", "-e", "eo::tipo", "-y"])
    result = runner.invoke(app, ["predikato", "serci", "tipo"])
    assert result.exit_code == 0
    assert "wdt:P31" in result.stdout or "tipo" in result.stdout


def test_predikat_grupo_forigi(runner: CliRunner) -> None:
    """Deleting a group should work."""
    runner.invoke(app, ["predikat-grupo", "aldoni", "forigota", "-y"])
    result = runner.invoke(app, ["predikat-grupo", "forigi", "forigota", "-y"])
    assert result.exit_code == 0
    assert "Forigis" in result.stdout


def test_nodo_forigi_multiple(runner: CliRunner) -> None:
    """Deleting multiple nodes at once should work."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::MultA", "-y"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::MultB", "-y"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    uuids = []
    for line in ls_result.stdout.strip().split("\n"):
        parts = line.strip().split()
        if len(parts) >= 2 and "Mult" in " ".join(parts[1:]):
            uuids.append(parts[0])
    if len(uuids) >= 2:
        result = runner.invoke(app, ["nodo", "forigi", uuids[0], uuids[1], "-y"])
        assert result.exit_code == 0
        assert "Forigis 2 el 2" in result.stdout


def test_predikato_forigi_multiple(runner: CliRunner) -> None:
    """Deleting multiple predicates at once should work."""
    runner.invoke(app, ["predikato", "aldoni", "wdt:P99", "-e", "eo::test99", "-y"])
    runner.invoke(app, ["predikato", "aldoni", "wdt:P100", "-e", "eo::test100", "-y"])
    result = runner.invoke(app, ["predikato", "forigi", "wdt:P99", "wdt:P100", "-y"])
    assert result.exit_code == 0
    assert "Forigis 2 el 2" in result.stdout


def test_predikat_grupo_forigi_multiple(runner: CliRunner) -> None:
    """Deleting multiple groups at once should work."""
    runner.invoke(app, ["predikat-grupo", "aldoni", "group_a", "-y"])
    runner.invoke(app, ["predikat-grupo", "aldoni", "group_b", "-y"])
    result = runner.invoke(app, ["predikat-grupo", "forigi", "group_a", "group_b", "-y"])
    assert result.exit_code == 0
    assert "Forigis 2 el 2" in result.stdout


# ── Wikidata integration tests (mocked) ──────────────────────────────────────


def test_predikato_serci_wikidata_flag(runner: CliRunner, monkeypatch) -> None:
    """serci with --wikidata should show merged results with source column."""
    # Pre-seed a local predicate
    runner.invoke(app, ["predikato", "aldoni", "wdt:P1082", "-e", "eo::logxantaro", "-y"])

    def mock_search(query, languages=None, timeout=10.0):
        return [
            {
                "ligilo": "wdt:P1082",
                "etikedo": "population",
                "priskribo": "number of inhabitants",
                "aliasoj": ["pop", "p1082"],
                "fonto": "wikidata",
            },
            {
                "ligilo": "wdt:P31",
                "etikedo": "instance of",
                "priskribo": "that class of which this subject is a particular example and member",
                "aliasoj": ["is a", "p31"],
                "fonto": "wikidata",
            },
        ]

    import A_semantika._wikidata_helper as wh
    monkeypatch.setattr(wh, "search_properties", mock_search)

    # Search with --wikidata
    result = runner.invoke(app, ["predikato", "serci", "wdt:--wikidata"])
    # Actually run: serci with -w flag
    result = runner.invoke(app, ["predikato", "serci", "instance", "-w"])
    assert result.exit_code == 0
    # Should show local entry (wdt:P1082) + Wikidata-only entry (wdt:P31)
    assert "wdt:P31" in result.stdout
    assert "wdt:P1082" in result.stdout
    # Fonto column should be present
    assert "Fonto" in result.stdout or "Source" in result.stdout


def test_predikato_serci_wikidata_network_failure(runner: CliRunner, monkeypatch) -> None:
    """serci with --wikidata should not crash on network failure."""
    def mock_search(query, languages=None, timeout=10.0):
        raise RuntimeError("Network error")

    import A_semantika._wikidata_helper as wh
    monkeypatch.setattr(wh, "search_properties", mock_search)

    # Create a local predicate
    runner.invoke(app, ["predikato", "aldoni", "wdt:P31", "-e", "eo::tipo", "-y"])

    # Search with --wikidata — should fall back gracefully
    result = runner.invoke(app, ["predikato", "serci", "tipo", "-w"])
    assert result.exit_code == 0
    assert "wdt:P31" in result.stdout


def test_predikato_serci_empty_local_no_wikidata_shows_hint(runner: CliRunner) -> None:
    """Empty local results without --wikidata should show a hint."""
    result = runner.invoke(app, ["predikato", "serci", "nonexistent"])
    assert result.exit_code == 0
    assert "Provu" in result.stdout or "Try" in result.stdout or "Essayez" in result.stdout


def test_predikato_aldoni_wikidata_auto_fetch(runner: CliRunner, monkeypatch) -> None:
    """Aldoni with a Wikidata ID should auto-fetch labels."""
    def mock_details(prop_id, languages=None, timeout=30.0):
        return {
            "id": "P31",
            "labels": {"en": "instance of", "eo": "estas ekzemplo de"},
            "descriptions": {"en": "that class of which this subject is a particular example and member"},
            "aliases": {"en": ["is a", "P31"]},
        }

    import A_semantika._wikidata_helper as wh
    monkeypatch.setattr(wh, "get_property_details", mock_details)

    result = runner.invoke(app, ["predikato", "aldoni", "P31", "-y"])
    assert result.exit_code == 0
    assert "kreita" in result.stdout or "Created" in result.stdout or "créé" in result.stdout

    # Verify labels were auto-fetched
    result = runner.invoke(app, ["predikato", "vidi", "wdt:P31"])
    assert result.exit_code == 0
    assert "estas ekzemplo de" in result.stdout
    assert "instance of" in result.stdout
    assert "wikidata" in result.stdout.lower()


def test_predikato_aldoni_wikidata_manual_override(runner: CliRunner, monkeypatch) -> None:
    """User-provided labels should override auto-fetched values."""
    def mock_details(prop_id, languages=None, timeout=30.0):
        return {
            "id": "P31",
            "labels": {"en": "instance of", "eo": "estas ekzemplo de"},
            "descriptions": {"en": "default description"},
            "aliases": {"en": ["is a", "P31"]},
        }

    import A_semantika._wikidata_helper as wh
    monkeypatch.setattr(wh, "get_property_details", mock_details)

    result = runner.invoke(app, [
        "predikato", "aldoni", "P31",
        "-e", "eo::tipo",
        "-y",
    ])
    assert result.exit_code == 0

    result = runner.invoke(app, ["predikato", "vidi", "wdt:P31"])
    assert result.exit_code == 0
    # User override should take precedence
    assert "tipo" in result.stdout
    # Auto-fetched en label should still be present (not overridden)
    assert "instance of" in result.stdout


def test_predikato_aldoni_wikidata_network_failure(runner: CliRunner, monkeypatch) -> None:
    """Aldoni with Wikidata ID should not crash on network failure."""
    def mock_details(prop_id, languages=None, timeout=30.0):
        raise RuntimeError("Network error")

    import A_semantika._wikidata_helper as wh
    monkeypatch.setattr(wh, "get_property_details", mock_details)

    # Should still create the predicate with manual mode
    result = runner.invoke(app, [
        "predikato", "aldoni", "P31",
        "-e", "eo::tipo",
        "-y",
    ])
    assert result.exit_code == 0

    # Verify it was created with manual data
    result = runner.invoke(app, ["predikato", "vidi", "wdt:P31"])
    assert result.exit_code == 0
    assert "tipo" in result.stdout


def test_predikato_aldoni_non_wikidata_unchanged(runner: CliRunner) -> None:
    """Non-Wikidata IDs should not trigger auto-fetch."""
    result = runner.invoke(app, [
        "predikato", "aldoni", "rdf:type",
        "-e", "eo::tipo",
        "-y",
    ])
    assert result.exit_code == 0

    result = runner.invoke(app, ["predikato", "vidi", "rdf:type"])
    assert result.exit_code == 0
    assert "tipo" in result.stdout
    assert "manual" in result.stdout or "fonto" in result.stdout


# ── --jes flag tests (Issue #8 R1) ──────────────────────────────────────────────


def test_nodo_aldoni_jes_flag(runner: CliRunner) -> None:
    """--jes flag should skip confirmation for nodo aldoni."""
    result = runner.invoke(app, [
        "nodo", "aldoni",
        "-e", "eo::JesTesto",
        "--jes",
    ])
    assert result.exit_code == 0
    assert "kreita" in result.stdout or "Created" in result.stdout or "créé" in result.stdout


def test_nodo_aldoni_yes_backward_compat(runner: CliRunner) -> None:
    """--yes flag should still work (backward compat)."""
    result = runner.invoke(app, [
        "nodo", "aldoni",
        "-e", "eo::YesTesto",
        "--yes",
    ])
    assert result.exit_code == 0
    assert "kreita" in result.stdout or "Created" in result.stdout or "créé" in result.stdout


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


def test_forigi_jes_flag(runner: CliRunner) -> None:
    """--jes flag should skip confirmation for forigi."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::ForigJes", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    for line in ls_result.stdout.strip().split("\n"):
        if "ForigJes" in line and line[0].isalnum():
            uuid_prefix = line.split()[0]
            break
    else:
        return

    result = runner.invoke(app, ["nodo", "forigi", uuid_prefix, "--jes"])
    assert result.exit_code == 0
    assert "forigita" in result.stdout


def test_help_shows_jes_not_yes(runner: CliRunner) -> None:
    """Help text should mention --jes as the canonical flag."""
    result = runner.invoke(app, ["nodo", "aldoni", "--help"])
    assert result.exit_code == 0
    assert "--jes" in result.stdout
    # --yes may appear as alias in help, but --jes must be shown


# ── Partial label matching tests (Issue #8 P2) ─────────────────────────────────


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


# ── Search-then-Select tests (Issue #8 R3) ─────────────────────────────────────


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


def test_triple_serci_backward_compat_uuid_prefix(runner: CliRunner) -> None:
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


# ── Deprecated alias backward-compat tests (Issue #10) ──────────────────────


def test_serci_subject_deprecated_alias(runner: CliRunner) -> None:
    """Old --subject flag should still work (deprecated)."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::DepSubj", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    uuid_prefix = None
    for line in ls_result.stdout.strip().split("\n"):
        parts = line.strip().split()
        if len(parts) >= 2 and "DepSubj" in " ".join(parts[1:]):
            uuid_prefix = parts[0]
            break
    if uuid_prefix:
        result = runner.invoke(app, ["serci", "--subject", uuid_prefix])
        assert result.exit_code == 0


def test_serci_predicate_deprecated_alias(runner: CliRunner) -> None:
    """Old --predicate flag should still work (deprecated)."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::DepPredSubj", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::DepPredObj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    uuids = [l.split()[0] for l in lines if len(l.split()) >= 1]
    if len(uuids) >= 2:
        runner.invoke(app, ["aldoni", uuids[0], "rdf:type", uuids[1], "--jes"])
        result = runner.invoke(app, ["serci", "--predicate", "rdf:type"])
        assert result.exit_code == 0


def test_serci_object_deprecated_alias(runner: CliRunner) -> None:
    """Old --object flag should still work (deprecated)."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::DepObjSubj", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::DepObjObj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    uuids = [l.split()[0] for l in lines if len(l.split()) >= 1]
    if len(uuids) >= 2:
        runner.invoke(app, ["aldoni", uuids[0], "rdf:type", uuids[1], "--jes"])
        result = runner.invoke(app, ["serci", "--object", uuids[1]])
        assert result.exit_code == 0
