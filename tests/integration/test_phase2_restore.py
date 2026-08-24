from job_search_cockpit.phase2.types import ActivationCommand
from tests.integration.test_phase2_activation import _service


def test_restore_suspends_the_previous_activation(phase2_settings) -> None:
    with _service(phase2_settings) as (service, _port):
        grant = service.activate(ActivationCommand(actor="Varun", confirmation="ENABLE PHASE II"))
        backup_id = next(phase2_settings.backup_dir.glob("*.sqlite3")).stem

        service.restore(backup_id=backup_id, actor="Varun", reason="Sanitized recovery test")
        view = service.activation_view()

    assert view.state == "suspended"
    assert view.restore_generation > grant.restore_generation
