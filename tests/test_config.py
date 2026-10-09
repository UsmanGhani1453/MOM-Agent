from app.config import normalize_host


def test_bad_hosts_are_made_connectable():
    assert normalize_host("0.0.0.0:11434") == "http://127.0.0.1:11434"
    assert normalize_host("http://0.0.0.0:11434") == "http://127.0.0.1:11434"
    assert normalize_host("localhost") == "http://127.0.0.1:11434"
    assert normalize_host("127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert normalize_host("http://192.168.1.5:9999") == "http://192.168.1.5:9999"
