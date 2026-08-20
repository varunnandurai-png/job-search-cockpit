from job_search_cockpit.launcher import build_launch_plan, prepare_vault


def test_launcher_binds_preopened_loopback_socket(vault_settings, monkeypatch):
    monkeypatch.setattr("job_search_cockpit.launcher.sys.platform", "darwin")
    launch = build_launch_plan(vault_settings)
    try:
        assert launch.socket.getsockname()[0] == "127.0.0.1"
        assert launch.url.startswith("http://127.0.0.1:")
        assert "/launch?token=" in launch.url
        assert launch.socket.fileno() >= 0
    finally:
        launch.close()


def test_launch_plan_does_not_reuse_token_or_port(vault_settings, monkeypatch):
    monkeypatch.setattr("job_search_cockpit.launcher.sys.platform", "darwin")
    first = build_launch_plan(vault_settings)
    first_url = first.url
    first_port = first.port
    first_token = first.launch_session.token
    first.close()
    second = build_launch_plan(vault_settings)
    try:
        assert second.url != first_url
        assert second.launch_session.token != first_token
        assert second.port > 0
        assert first_port > 0
    finally:
        second.close()


def test_clean_restart_does_not_create_noop_backups(vault_settings, monkeypatch):
    monkeypatch.setattr("job_search_cockpit.launcher.sys.platform", "darwin")
    first = prepare_vault(vault_settings)
    first.coordinator.dispose()
    first.instance_lock.release()
    initial_backups = tuple(vault_settings.backup_dir.glob("*.sqlite3"))

    second = prepare_vault(vault_settings)
    try:
        assert tuple(vault_settings.backup_dir.glob("*.sqlite3")) == initial_backups
    finally:
        second.coordinator.dispose()
        second.instance_lock.release()
