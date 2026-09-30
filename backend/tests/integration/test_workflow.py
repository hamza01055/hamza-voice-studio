"""Project -> generation -> takes -> export workflow using the TEST-ONLY mock engine."""

import threading

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import GenerationJob
from app.db.session import get_engine, session_factory
from app.jobs import queue
from tests import mock_engine
from tests.conftest import run_worker

SCRIPT = "First paragraph here.\n\nSecond paragraph, with 15 items.\n\nThird one!"


def make_project(c: TestClient, script: str = SCRIPT, **kw) -> dict:
    r = c.post("/api/projects", json={"name": "Book", "script": script, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def seg_ids(p: dict) -> list[str]:
    return [s["id"] for ch in p["chapters"] for s in ch["segments"]]


def test_project_persistence_and_segmentation(studio: TestClient):
    p = make_project(studio)
    segs = p["chapters"][0]["segments"]
    assert [s["original_text"] for s in segs] == ["First paragraph here.", "Second paragraph, with 15 items.",
                                                  "Third one!"]
    assert segs[1]["normalized_text"] == "Second paragraph, with fifteen items."
    assert [s["position"] for s in segs] == [0, 1, 2]
    # reopen
    again = studio.get(f"/api/projects/{p['id']}").json()
    assert seg_ids(again) == seg_ids(p)
    lst = studio.get("/api/projects").json()
    assert lst["total"] == 1 and lst["items"][0]["segment_count"] == 3


def test_reorder_split_delete_segments(studio: TestClient):
    p = make_project(studio)
    a, b, c = seg_ids(p)
    studio.patch(f"/api/segments/{c}", json={"position": 0})
    assert seg_ids(studio.get(f"/api/projects/{p['id']}").json()) == [c, a, b]
    r = studio.post(f"/api/segments/{b}/split", json={"at": 17})
    assert r.status_code == 200
    ids = seg_ids(studio.get(f"/api/projects/{p['id']}").json())
    assert ids[:3] == [c, a, b] and len(ids) == 4
    studio.delete(f"/api/segments/{a}")
    assert a not in seg_ids(studio.get(f"/api/projects/{p['id']}").json())


def test_generate_select_regenerate_and_export(studio: TestClient, settings):
    p = make_project(studio)
    ids = seg_ids(p)
    r = studio.post("/api/generations", json={"segment_ids": ids, "idempotency_key": "k1"})
    assert r.status_code == 202 and len(r.json()["jobs"]) == 3
    # duplicate submission with the same key creates nothing new
    r2 = studio.post("/api/generations", json={"segment_ids": ids, "idempotency_key": "k1"})
    assert [j["job_id"] for j in r2.json()["jobs"]] == [j["job_id"] for j in r.json()["jobs"]]
    assert all(j["deduplicated"] for j in r2.json()["jobs"])
    assert run_worker() == 3
    jobs = studio.get("/api/jobs?type=tts").json()["items"]
    assert {j["status"] for j in jobs} == {"completed"}
    proj = studio.get(f"/api/projects/{p['id']}").json()
    segs = proj["chapters"][0]["segments"]
    assert all(s["selected_take_id"] for s in segs)
    first_take = segs[0]["selected_take_id"]

    # regenerate only segment 0 (two takes)
    r = studio.post("/api/generations", json={"segment_ids": [ids[0]], "takes": 2})
    assert len(r.json()["jobs"]) == 2
    run_worker()
    takes = studio.get(f"/api/segments/{ids[0]}/takes").json()
    assert len(takes["items"]) == 3
    assert takes["selected_take_id"] == first_take  # regeneration does not replace the selection
    other = [t for t in takes["items"] if t["id"] != first_take][0]
    assert studio.post(f"/api/segments/{ids[0]}/selected-take", json={"take_id": other["id"]}).status_code == 200
    # other segments untouched
    assert len(studio.get(f"/api/segments/{ids[1]}/takes").json()["items"]) == 1

    # audio playback with range
    a = studio.get(f"/api/assets/{other['output_asset_id']}/audio", headers={"Range": "bytes=0-43"})
    assert a.status_code == 206 and len(a.content) == 44 and a.content[:4] == b"RIFF"

    for fmt in ("wav", "mp3"):
        r = studio.post(f"/api/projects/{p['id']}/exports", json={"format": fmt, "file_name": "Book"})
        assert r.status_code == 202
        assert run_worker("io") == 1
        e = studio.get(f"/api/exports/{r.json()['export']['id']}").json()
        assert e["status"] == "completed", e
        assert e["file_name"] == f"Book.{fmt}" and e["duration"] > 1
        f = studio.get(f"/api/exports/{e['id']}/file")
        assert f.status_code == 200 and len(f.content) == e["byte_size"]
    # a second export never overwrites the first
    r = studio.post(f"/api/projects/{p['id']}/exports", json={"format": "mp3", "file_name": "Book"})
    run_worker("io")
    assert studio.get(f"/api/exports/{r.json()['export']['id']}").json()["file_name"] == "Book (1).mp3"


def test_export_requires_takes(studio: TestClient):
    p = make_project(studio)
    r = studio.post(f"/api/projects/{p['id']}/exports", json={"format": "wav"})
    run_worker("io")
    e = studio.get(f"/api/exports/{r.json()['export']['id']}").json()
    assert e["status"] == "failed"
    job = studio.get(f"/api/jobs/{r.json()['job_id']}").json()
    assert job["error_code"] == "missing_takes"


def test_stale_takes_after_text_edit(studio: TestClient):
    p = make_project(studio)
    sid = seg_ids(p)[0]
    studio.post("/api/generations", json={"segment_ids": [sid]})
    run_worker()
    s = studio.patch(f"/api/segments/{sid}", json={"original_text": "Changed text now."}).json()
    assert s["text_revision"] == 2 and s["selected_take_stale"] is True
    takes = studio.get(f"/api/segments/{sid}/takes").json()["items"]
    assert takes[0]["stale"] is True and takes[0]["input_text"] == "First paragraph here."


def test_old_job_does_not_overwrite_new_text_or_selection(studio: TestClient):
    p = make_project(studio)
    sid = seg_ids(p)[0]
    studio.post("/api/generations", json={"segment_ids": [sid]})
    # user edits while the job is queued
    studio.patch(f"/api/segments/{sid}", json={"original_text": "Newer text."})
    run_worker()
    s = [x for x in studio.get(f"/api/projects/{p['id']}").json()["chapters"][0]["segments"] if x["id"] == sid][0]
    assert s["original_text"] == "Newer text."
    assert s["selected_take_id"] is None  # stale take not auto-selected
    assert studio.get(f"/api/segments/{sid}/takes").json()["items"][0]["stale"] is True


def test_cancel_queued_and_running(studio: TestClient):
    p = make_project(studio)
    ids = seg_ids(p)
    jobs = studio.post("/api/generations", json={"segment_ids": ids}).json()["jobs"]
    r = studio.post(f"/api/jobs/{jobs[2]['job_id']}/cancel")
    assert r.json()["status"] == "cancelled"

    # cancel the running job from inside the engine's sentence loop
    def on_sentence(i):
        if i == 1:
            with session_factory()() as db:
                j = db.get(GenerationJob, jobs[0]["job_id"])
                if j.status in ("running", "loading_model"):
                    queue.request_cancel(db, j)
                    db.commit()

    mock_engine.Behaviour.on_sentence = on_sentence
    from app.jobs.worker import Worker

    w = Worker("test-worker")
    # the heartbeat thread normally propagates cancel flags; emulate it here
    orig = w._run

    def run_with_flag(ctx):
        def flag_poll():
            import time
            for _ in range(200):
                if queue.cancel_flags(get_engine(), [ctx.job_id]).get(ctx.job_id):
                    ctx.cancel_event.set()
                    return
                time.sleep(0.01)
        t = threading.Thread(target=flag_poll)
        t.start()
        orig(ctx)
        t.join()

    w._run = run_with_flag
    mock_engine.Behaviour.sentences = 50

    def slow_sentence(i):
        on_sentence(i)
        import time
        time.sleep(0.02)

    mock_engine.Behaviour.on_sentence = slow_sentence
    w.process_next("inference")
    j0 = studio.get(f"/api/jobs/{jobs[0]['job_id']}").json()
    assert j0["status"] == "cancelled"
    assert studio.get(f"/api/segments/{ids[0]}/takes").json()["items"] == []  # no partial take persisted
    assert studio.post(f"/api/jobs/{jobs[0]['job_id']}/cancel").status_code == 409
    # retry a cancelled job
    assert studio.post(f"/api/jobs/{jobs[0]['job_id']}/retry").json()["status"] == "queued"
    mock_engine.Behaviour.on_sentence = None
    mock_engine.Behaviour.sentences = 2
    run_worker()
    assert studio.get(f"/api/jobs/{jobs[0]['job_id']}").json()["status"] == "completed"


def test_retry_policy_transient_and_permanent(studio: TestClient, settings):
    p = make_project(studio)
    sid = seg_ids(p)[0]
    mock_engine.Behaviour.fail_times = 1  # transient -> automatic retry once
    job = studio.post("/api/generations", json={"segment_ids": [sid]}).json()["jobs"][0]["job_id"]
    run_worker()
    j = studio.get(f"/api/jobs/{job}").json()
    assert j["status"] == "completed" and j["retry_count"] == 1

    mock_engine.Behaviour.fail_times = 5
    job = studio.post("/api/generations", json={"segment_ids": [seg_ids(p)[1]]}).json()["jobs"][0]["job_id"]
    run_worker()
    j = studio.get(f"/api/jobs/{job}").json()
    assert j["status"] == "failed" and j["retry_count"] == settings.max_auto_retries and j["retryable"]

    mock_engine.Behaviour.fail_times = 0
    mock_engine.Behaviour.empty_output = True  # invalid output is not retried automatically
    job = studio.post("/api/generations", json={"segment_ids": [seg_ids(p)[2]]}).json()["jobs"][0]["job_id"]
    run_worker()
    j = studio.get(f"/api/jobs/{job}").json()
    assert j["status"] == "failed" and j["error_code"] == "invalid_output" and j["retry_count"] == 0


def test_nan_output_and_model_exception(studio: TestClient):
    p = make_project(studio)
    mock_engine.Behaviour.nan_output = True
    job = studio.post("/api/generations", json={"segment_ids": [seg_ids(p)[0]]}).json()["jobs"][0]["job_id"]
    run_worker()
    assert studio.get(f"/api/jobs/{job}").json()["error_code"] == "invalid_output"
    mock_engine.Behaviour.nan_output = False
    mock_engine.Behaviour.raise_exc = RuntimeError("boom")
    job = studio.post("/api/generations", json={"segment_ids": [seg_ids(p)[1]]}).json()["jobs"][0]["job_id"]
    run_worker()
    j = studio.get(f"/api/jobs/{job}").json()
    assert j["status"] == "failed" and j["error_code"] == "internal_error" and "boom" not in j["error_message"]


def test_out_of_memory_is_reported(studio: TestClient):
    p = make_project(studio)
    mock_engine.Behaviour.raise_exc = MemoryError()
    job = studio.post("/api/generations", json={"segment_ids": [seg_ids(p)[0]]}).json()["jobs"][0]["job_id"]
    run_worker()
    assert studio.get(f"/api/jobs/{job}").json()["error_code"] == "out_of_memory"


def test_missing_model_and_unsupported_language(studio: TestClient):
    p = make_project(studio, default_language="fr")
    r = studio.post("/api/generations", json={"segment_ids": seg_ids(p)})
    assert r.status_code == 202 and r.json()["jobs"] == []
    assert all(s["code"] == "unsupported_language" for s in r.json()["skipped"])
    p2 = make_project(studio)
    studio.patch(f"/api/projects/{p2['id']}", json={"settings": {"model_id": "kokoro-multi-lang-v1_0",
                                                                 "voice": "af_heart"}})
    r = studio.post("/api/generations", json={"segment_ids": seg_ids(p2)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "model_not_installed"


def test_atomic_claim_no_double_processing(studio: TestClient, settings):
    p = make_project(studio, script="\n\n".join(f"Line {i}." for i in range(20)))
    studio.post("/api/generations", json={"segment_ids": seg_ids(p)})
    claimed: list[str] = []
    lock = threading.Lock()

    def claimer(n):
        while True:
            jid = queue.claim(get_engine(), "inference", f"w{n}", 30)
            if not jid:
                return
            with lock:
                claimed.append(jid)

    threads = [threading.Thread(target=claimer, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(claimed) == 20 and len(set(claimed)) == 20


def test_interrupted_job_recovery(studio: TestClient, settings):
    p = make_project(studio)
    ids = seg_ids(p)
    jobs = studio.post("/api/generations", json={"segment_ids": ids}).json()["jobs"]
    # simulate a worker crash mid-job: claimed, lease expired
    j1 = queue.claim(get_engine(), "inference", "dead-worker", -1)
    j2 = queue.claim(get_engine(), "inference", "dead-worker", -1)
    with session_factory()() as db:
        db.get(GenerationJob, j2).retry_count = settings.max_auto_retries  # already retried
        db.commit()
    with session_factory()() as db:
        rec = queue.recover_stale(db)
        db.commit()
    assert set(rec) == {j1, j2}
    assert studio.get(f"/api/jobs/{j1}").json()["status"] == "queued"
    j2d = studio.get(f"/api/jobs/{j2}").json()
    assert j2d["status"] == "interrupted" and j2d["error_code"] == "interrupted"
    assert studio.post(f"/api/jobs/{j2}/retry").json()["status"] == "queued"
    run_worker()
    assert {studio.get(f"/api/jobs/{j['job_id']}").json()["status"] for j in jobs} == {"completed"}


def test_restart_recovers_running_jobs(studio: TestClient):
    from app.main import startup_tasks

    p = make_project(studio)
    studio.post("/api/generations", json={"segment_ids": seg_ids(p)[:1]})
    jid = queue.claim(get_engine(), "inference", "old-process", 300)  # lease still valid
    startup_tasks()  # what the API does on restart, before any worker exists
    assert studio.get(f"/api/jobs/{jid}").json()["status"] == "queued"


def test_bounded_queue(studio: TestClient, settings):
    p = make_project(studio, script="\n\n".join(f"L{i}." for i in range(60)))
    r = studio.post("/api/generations", json={"segment_ids": seg_ids(p)})
    assert r.status_code == 429 and r.json()["error"]["code"] == "queue_full"


def test_delete_project_removes_audio_and_cancels_jobs(studio: TestClient, settings):
    p = make_project(studio)
    ids = seg_ids(p)
    studio.post("/api/generations", json={"segment_ids": ids[:2]})
    run_worker()
    studio.post("/api/generations", json={"segment_ids": [ids[2]]})  # stays queued
    files = list((settings.media_dir / "take").rglob("*.wav"))
    assert len(files) == 2
    r = studio.delete(f"/api/projects/{p['id']}")
    assert r.status_code == 200 and r.json()["cancelled_jobs"] == 1 and r.json()["deleted_audio_files"] == 2
    assert not list((settings.media_dir / "take").rglob("*.wav"))
    assert studio.get(f"/api/projects/{p['id']}").status_code == 404
    with session_factory()() as db:
        assert all(j.status == "cancelled" for j in db.scalars(select(GenerationJob).where(
            GenerationJob.segment_id.is_(None), GenerationJob.type == "tts", GenerationJob.status != "completed")))


def test_resegment_keeps_unchanged_segments(studio: TestClient):
    p = make_project(studio)
    ids = seg_ids(p)
    studio.post("/api/generations", json={"segment_ids": ids})
    run_worker()
    ch = p["chapters"][0]["id"]
    r = studio.post(f"/api/projects/{p['id']}/segments", json={
        "chapter_id": ch, "replace": True, "script": "First paragraph here.\n\nBrand new.\n\nThird one!"})
    new_ids = seg_ids(r.json()["project"])
    assert new_ids[0] == ids[0] and new_ids[2] == ids[2] and new_ids[1] != ids[1]
    segs = r.json()["project"]["chapters"][0]["segments"]
    assert segs[0]["selected_take_id"] and not segs[1]["selected_take_id"]
    # only_missing skips segments that already have a current take
    g = studio.post("/api/generations", json={"segment_ids": new_ids, "only_missing": True}).json()
    assert len(g["jobs"]) == 1 and len(g["skipped"]) == 2


def test_chapters_and_ordered_export(studio: TestClient):
    p = make_project(studio, script="One.\n\nTwo.")
    r = studio.post(f"/api/projects/{p['id']}/chapters", json={"title": "Chapter 2", "script": "Three."})
    proj = r.json()
    assert [c["title"] for c in proj["chapters"]] == ["Chapter 1", "Chapter 2"]
    studio.post("/api/generations", json={"segment_ids": seg_ids(proj)})
    run_worker()
    ch2 = proj["chapters"][1]["id"]
    r = studio.post(f"/api/projects/{p['id']}/exports", json={"format": "wav", "chapter_id": ch2})
    run_worker("io")
    e = studio.get(f"/api/exports/{r.json()['export']['id']}").json()
    assert e["status"] == "completed" and e["details"]["segments"] == 1


def test_sse_stream_reports_job(studio: TestClient, settings):
    p = make_project(studio)
    job = studio.post("/api/generations", json={"segment_ids": seg_ids(p)[:1]}).json()["jobs"][0]["job_id"]
    run_worker()
    with studio.stream("GET", f"/api/jobs/{job}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    assert "event: job" in body and '"completed"' in body


def test_settings_roundtrip(studio: TestClient):
    r = studio.patch("/api/settings", json={"theme": "dark", "export_format": "wav"})
    assert r.json()["theme"] == "dark" and r.json()["analytics_enabled"] is False
    assert studio.patch("/api/settings", json={"analytics_enabled": True}).json()["analytics_enabled"] is False
    assert studio.patch("/api/settings", json={"theme": "neon"}).status_code == 422
