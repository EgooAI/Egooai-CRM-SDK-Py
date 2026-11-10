import utils.common as common


def test_default_path_is_crm_sqlite_in_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(common, "_DEFAULT_DATABASE_PATH", None)
    assert common.resolve_database_path() == (tmp_path / "crm.sqlite").resolve()


def test_host_provider_controls_default(tmp_path, monkeypatch):
    target = tmp_path / "custom.sqlite"
    monkeypatch.setattr(common, "_DEFAULT_DATABASE_PATH", lambda: target)
    assert common.resolve_database_path() == target.resolve()
