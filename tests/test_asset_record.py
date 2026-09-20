import json
import stat
from pathlib import Path

import pytest


def _media_metadata() -> dict[str, object]:
    return {
        "duration": 12.5,
        "width": 1920,
        "height": 1080,
        "fps": 25.0,
        "video_codec": "h264",
        "audio_codec": "aac",
        "container": "mov,mp4,m4a,3gp,3g2,mj2",
    }


@pytest.fixture
def asset_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from tools import asset_record as module

    monkeypatch.setattr(module, "ASSET_ROOT", tmp_path / "assets")
    monkeypatch.setattr(module, "probe_media", lambda _path: _media_metadata())
    return module


def test_hash_and_asset_id_are_deterministic(asset_record, tmp_path: Path) -> None:
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"same media bytes")

    digest = asset_record.sha256_file(source)

    assert digest == asset_record.sha256_file(source)
    assert asset_record.asset_id_for_sha256(digest) == f"ast_{digest[:20]}"


def test_register_accepts_a_path_string(asset_record, tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"media")

    record = asset_record.register_asset(str(source))

    assert record["asset_id"].startswith("ast_")


def test_register_copies_once_and_reuses_duplicate_record(asset_record, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"same media bytes")

    first = asset_record.register_asset(source)
    second = asset_record.register_asset(source)
    records = list((asset_record.ASSET_ROOT / "source").rglob("*.asset.json"))

    assert first == second
    assert len(records) == 1
    target = asset_record.ASSET_ROOT / first["path"]
    assert target.read_bytes() == b"same media bytes"
    assert not (target.stat().st_mode & stat.S_IWUSR)


def test_defaults_are_fail_closed_and_record_validates(asset_record, tmp_path: Path) -> None:
    from contracts.validate_contracts import validate

    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")

    record = asset_record.register_asset(source)

    assert record["rights"] == {
        "rights_status": "UNKNOWN",
        "commercial_use": "unknown",
        "person_consent": "unknown",
        "provider_data_scope": "cloud_not_approved",
    }
    assert record["ai_involvement"] == {"ai_generated": "unknown"}
    assert validate("asset", record) == []


def test_invalid_rights_write_nothing(asset_record, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")

    with pytest.raises(asset_record.AssetRecordError, match="Schema"):
        asset_record.register_asset(source, rights_status="friendly")

    assert not list(asset_record.ASSET_ROOT.rglob("*"))


def test_register_subtitle_file_succeeds(asset_record, tmp_path: Path) -> None:
    from contracts.validate_contracts import validate

    srt = tmp_path / "cues.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")

    record = asset_record.register_asset(srt)

    assert record["media_type"] == "subtitle"
    assert record["role"] == "SOURCE"
    assert record["technical"] == {}
    assert validate("asset", record) == []


def test_register_document_json_succeeds(asset_record, tmp_path: Path) -> None:
    from contracts.validate_contracts import validate

    spec = tmp_path / "spec.json"
    spec.write_text('{"canvas": {"preset": "A5"}, "layers": []}', encoding="utf-8")

    record = asset_record.register_asset(spec)

    assert record["media_type"] == "document"
    assert record["technical"] == {}
    assert validate("asset", record) == []


def test_register_editable_source_role(asset_record, tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    spec.write_text('{"canvas": {"preset": "A5"}, "layers": []}', encoding="utf-8")

    record = asset_record.register_asset(spec, role="EDITABLE_SOURCE")

    assert record["role"] == "EDITABLE_SOURCE"
    assert record["path"].startswith("editable_source/")


def test_register_asset_rejects_unknown_role(asset_record, tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    spec.write_text("{}", encoding="utf-8")

    with pytest.raises(asset_record.AssetRecordError, match="role"):
        asset_record.register_asset(spec, role="MASTER")


def test_register_reference_person_with_full_consent_validates(
    asset_record, tmp_path: Path
) -> None:
    from PIL import Image

    from contracts.validate_contracts import validate

    image_path = tmp_path / "face-front.png"
    Image.new("RGB", (10, 10), (1, 2, 3)).save(image_path)

    record = asset_record.register_asset(
        image_path,
        role="REFERENCE",
        reference_kind="person",
        person_consent="documented",
        purpose_binding=["proj-demo-001"],
        edit_approval=True,
    )

    assert record["role"] == "REFERENCE"
    assert record["reference_kind"] == "person"
    assert record["rights"]["person_consent"] == "documented"
    assert record["rights"]["purpose_binding"] == ["proj-demo-001"]
    assert record["rights"]["edit_approval"] is True
    assert validate("asset", record) == []


def test_register_reference_person_without_consent_is_rejected(
    asset_record, tmp_path: Path
) -> None:
    from PIL import Image

    image_path = tmp_path / "face-front.png"
    Image.new("RGB", (10, 10), (1, 2, 3)).save(image_path)

    with pytest.raises(asset_record.AssetRecordError, match="Schema"):
        asset_record.register_asset(image_path, role="REFERENCE", reference_kind="person")
    assert not list(asset_record.ASSET_ROOT.rglob("*"))


def test_register_asset_rejects_unknown_reference_kind(asset_record, tmp_path: Path) -> None:
    image_path = tmp_path / "face.png"
    from PIL import Image

    Image.new("RGB", (10, 10), (1, 2, 3)).save(image_path)

    with pytest.raises(asset_record.AssetRecordError, match="reference_kind"):
        asset_record.register_asset(image_path, role="REFERENCE", reference_kind="alien")


def test_register_image_reports_dimensions(asset_record, tmp_path: Path) -> None:
    from PIL import Image

    from contracts.validate_contracts import validate

    image_path = tmp_path / "picture.png"
    Image.new("RGB", (120, 60), (10, 20, 30)).save(image_path)

    record = asset_record.register_asset(image_path)

    assert record["media_type"] == "image"
    assert record["technical"] == {"width": 120, "height": 60}
    assert validate("asset", record) == []


def test_original_is_never_changed(asset_record, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original remains mutable")
    before_mode = source.stat().st_mode

    record = asset_record.register_asset(source)

    assert source.read_bytes() == b"original remains mutable"
    assert source.stat().st_mode == before_mode
    manifest = asset_record.ASSET_ROOT / record["path"]
    manifest = manifest.with_name(f"{record['asset_id']}.asset.json")
    assert json.loads(manifest.read_text(encoding="utf-8"))["asset_id"] == record["asset_id"]
