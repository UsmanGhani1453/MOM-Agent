import io

from tests.conftest import FakeTranscriber, wait_done


def upload(client, name="meeting.mp3", data=b"fake-audio"):
    return client.post("/upload", files={"file": (name, io.BytesIO(data), "audio/mpeg")},
                       data={"meeting_date": "2026-10-08"}, follow_redirects=False)


def test_full_flow(make_client, settings):
    with make_client()[0] as client:
        r = upload(client)
        assert r.status_code == 303
        mid = r.headers["location"].rsplit("/", 1)[1]
        assert wait_done(client, mid)["status"] == "done"

        page = client.get(f"/meetings/{mid}")
        assert "AI project sync" in page.text and "Build the agent" in page.text

        d = client.get(f"/meetings/{mid}/download")
        assert d.status_code == 200 and d.content[:2] == b"PK"  # a real .docx (zip)

        assert "AI project sync" in client.get("/").text
        # audio is deleted after success
        assert not list(settings.upload_dir.glob("*.mp3"))

        client.post(f"/meetings/{mid}/delete", follow_redirects=False)
        assert client.get(f"/meetings/{mid}/status").status_code == 404


def test_rejects_bad_extension(make_client):
    with make_client()[0] as client:
        r = upload(client, name="notes.txt")
        assert r.status_code == 400 and "Unsupported" in r.text


def test_rejects_oversize(make_client, settings):
    import dataclasses
    tiny_settings = dataclasses.replace(settings, max_upload_mb=1)
    with make_client(settings_override=tiny_settings)[0] as client:
        r = upload(client, data=b"x" * (2 * 1024 * 1024))
        assert r.status_code == 413
        assert not list(tiny_settings.upload_dir.iterdir())


def test_failure_then_retry_reuses_transcript(make_client):
    client, llm, tr = make_client(outputs=["bad"])
    with client:
        mid = upload(client).headers["location"].rsplit("/", 1)[1]
        s = wait_done(client, mid)
        assert s["status"] == "failed" and "valid minutes" in s["error"]
        llm.outputs = ['{"meeting_title": "Recovered"}']
        client.post(f"/meetings/{mid}/retry", follow_redirects=False)
        assert wait_done(client, mid)["status"] == "done"
        assert tr.calls == 1  # transcription was NOT repeated


def test_empty_speech_reports_clear_error(make_client):
    client, _, _ = make_client(transcriber=FakeTranscriber(text=""))
    with client:
        mid = upload(client).headers["location"].rsplit("/", 1)[1]
        s = wait_done(client, mid)
        assert s["status"] == "failed" and "no speech" in s["error"]


def test_unknown_meeting_404(make_client):
    with make_client()[0] as client:
        assert client.get("/meetings/nope").status_code == 404
        assert client.get("/meetings/nope/status").status_code == 404
