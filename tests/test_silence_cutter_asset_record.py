from pathlib import Path

from tools import silence_cutter


def test_register_cut_output_creates_a_master_from_the_source_parent(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "cut.mp4"
    source.write_bytes(b"source")
    output.write_bytes(b"cut")
    captured: dict[str, object] = {}
    monkeypatch.setattr(silence_cutter, "sha256_file", lambda _path: "a" * 64)
    monkeypatch.setattr(silence_cutter, "asset_id_for_sha256", lambda _digest: "ast_sourceparent")
    monkeypatch.setattr(
        silence_cutter,
        "register_derived",
        lambda path, **kwargs: captured.update({"path": path, **kwargs}) or {"asset_id": "ast_cut"},
    )

    record = silence_cutter.register_cut_output(str(source), str(output))

    assert record == {"asset_id": "ast_cut"}
    assert captured == {
        "path": str(output),
        "parents": ["ast_sourceparent"],
        "role": "MASTER",
        "tool": "silence_cutter",
        "operation": "remove_silence",
    }


def test_register_cut_output_warns_without_failing_the_cut(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "cut.mp4"
    source.write_bytes(b"source")
    output.write_bytes(b"cut")
    monkeypatch.setattr(silence_cutter, "sha256_file", lambda _path: "a" * 64)
    monkeypatch.setattr(silence_cutter, "asset_id_for_sha256", lambda _digest: "ast_sourceparent")
    monkeypatch.setattr(
        silence_cutter,
        "register_derived",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            silence_cutter.AssetRecordError("parent missing")
        ),
    )

    assert silence_cutter.register_cut_output(str(source), str(output)) is None
    assert "Asset-Registrierung: WARN — parent missing" in capsys.readouterr().err
