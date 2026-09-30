import json

from fastapi.testclient import TestClient

from tests.conftest import run_worker, wav_bytes


def upload_voice(c: TestClient, data: bytes, name="My voice", consent=True, basis="my_own_voice",
                 filename="ref.wav", transcript="Hello this is me."):
    return c.post("/api/voices", files={"file": (filename, data, "application/octet-stream")},
                  data={"name": name, "language": "en-us", "transcript": transcript,
                        "tags": json.dumps(["narration"]), "permission_basis": basis,
                        "consent_confirmed": str(consent).lower()})


def test_voice_requires_consent(studio: TestClient):
    r = upload_voice(studio, wav_bytes(), consent=False)
    assert r.status_code == 422 and r.json()["error"]["code"] == "consent_required"
    r = upload_voice(studio, wav_bytes(), basis="i_found_it_online")
    assert r.status_code == 422


def test_voice_upload_validates_by_decoding(studio: TestClient, settings):
    # extension says wav, content is garbage
    r = upload_voice(studio, b"RIFF....not really audio" * 100)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_media"
    r = upload_voice(studio, b"")
    assert r.status_code == 422
    # too short / silent
    assert upload_voice(studio, wav_bytes(seconds=0.5)).status_code == 422
    silent = upload_voice(studio, wav_bytes(seconds=4, amp=0.0))
    assert silent.status_code == 422 and "silent" in silent.json()["error"]["message"]
    # an FLAC file with a .txt name is fine because content is decoded, not trusted by extension
    ok = upload_voice(studio, wav_bytes(seconds=4, fmt="FLAC", channels=2), filename="voice.txt")
    assert ok.status_code == 201, ok.text
    v = ok.json()
    assert v["duration"] > 3.9 and v["consent"]["permission_basis"] == "my_own_voice"
    assert any("channels" in w for w in v["analysis"]["warnings"])
    assert v["compatible_engine"] is None  # no cloning engine integrated/installed
    assert v["tags"] == ["narration"]


def test_voice_edit_trim_revoke_delete(studio: TestClient, settings):
    v = upload_voice(studio, wav_bytes(seconds=6)).json()
    r = studio.patch(f"/api/voices/{v['id']}", json={"name": "Renamed", "reference_transcript": "New text",
                                                     "trim_start": 1.0, "trim_end": 4.0})
    assert r.status_code == 200
    v2 = r.json()
    assert v2["name"] == "Renamed" and abs(v2["duration"] - 3.0) < 0.05
    assert v2["reference_asset_id"] != v["reference_asset_id"]
    refs = list((settings.media_dir / "reference").rglob("*.wav"))
    assert len(refs) == 1  # old reference released
    r = studio.patch(f"/api/voices/{v['id']}", json={"revoke_consent": True})
    assert r.json()["consent"]["revoked_at"]
    d = studio.delete(f"/api/voices/{v['id']}")
    assert d.status_code == 200 and d.json()["reference_audio_deleted"] is True
    assert not list((settings.media_dir / "reference").rglob("*.wav"))
    assert studio.get(f"/api/voices/{v['id']}").status_code == 404


def test_voice_upload_size_limit(studio: TestClient, settings):
    settings.max_upload_bytes = 1000
    r = upload_voice(studio, wav_bytes(seconds=4))
    assert r.status_code == 413


def test_transcription_flow_with_mock_asr(studio: TestClient):
    r = studio.post("/api/transcriptions", files={"file": ("a.wav", wav_bytes(seconds=3), "audio/wav")},
                    data={"model_id": "mock-asr"})
    assert r.status_code == 202, r.text
    tid = r.json()["id"]
    assert run_worker() == 1
    t = studio.get(f"/api/transcriptions/{tid}").json()
    assert t["text"] == "hello world" and t["timestamp_kind"] == "chunk" and t["job_status"] == "completed"
    srt = studio.get(f"/api/transcriptions/{tid}/export?format=srt")
    assert srt.status_code == 200 and "00:00:00,000 -->" in srt.text
    studio.patch(f"/api/transcriptions/{tid}", json={"edited_text": "Hello, world."})
    assert studio.get(f"/api/transcriptions/{tid}/export?format=txt").text == "Hello, world."
    assert studio.get(f"/api/transcriptions/{tid}/export?format=vtt").status_code == 409
    assert studio.delete(f"/api/transcriptions/{tid}").status_code == 200


def test_transcription_requires_installed_asr(studio: TestClient):
    r = studio.post("/api/transcriptions", files={"file": ("a.wav", wav_bytes(), "audio/wav")},
                    data={"model_id": "whisper-tiny-sherpa"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "model_not_installed"
    r = studio.post("/api/transcriptions", files={"file": ("a.wav", wav_bytes(), "audio/wav")},
                    data={"model_id": "mock-tts"})
    assert r.status_code == 422


def test_normalize_and_transliterate_preview(studio: TestClient):
    r = studio.post("/api/text/normalize", json={"text": "Fee Rs. 2,500", "language": "en-us"})
    assert r.json()["text"] == "Fee two thousand five hundred rupees"
    r = studio.post("/api/text/transliterate", json={"text": "aap kaise hain?"})
    assert r.json()["text"] == "آپ کیسے ہیں؟"
