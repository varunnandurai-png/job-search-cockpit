from uuid import uuid4

from job_search_cockpit.phase1_contract.service import Phase1ContractService
from job_search_cockpit.ports import PreparedVault
from job_search_cockpit.storage.models import ImportRun, ImportRunSource
from tests.support.web import authenticated_test_app


def test_phase2_page_explains_that_setup_is_not_live(vault_settings) -> None:
    with authenticated_test_app(vault_settings) as client:
        page = client.get("/phase-2")

    assert page.status_code == 200
    assert "Phase II is not enabled" in page.text
    assert "No job sources have been contacted" in page.text
    assert "providers are not approved" in page.text


def test_phase2_activation_post_uses_csrf_and_redirect(vault_settings) -> None:
    with authenticated_test_app(vault_settings) as client:
        response = client.post(
            "/phase-2/activate",
            data={"confirmation": "ENABLE PHASE II", "reason": "Start setup"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/phase-2"


def _record_sanitized_phase1_acceptance(prepared: PreparedVault) -> None:
    import_run_id = str(uuid4())
    coordinator = prepared.coordinator

    def add_complete_import(session: object) -> None:
        session.add(
            ImportRun(
                id=import_run_id,
                manifest_version="four-source-v1",
                candidate_digest="a" * 64,
                status="committed",
                complete=True,
            )
        )
        for source_key in ("assessment", "profile_json", "master_profile", "resume_workflow"):
            session.add(
                ImportRunSource(
                    id=str(uuid4()),
                    import_run_id=import_run_id,
                    source_key=source_key,
                    status="ready",
                    content_hash="b" * 64,
                    failure_class=None,
                    redacted_message=None,
                )
            )

    coordinator.run(add_complete_import, "sanitized_activation_fixture", expected_version=None)
    contract = prepared.services.phase1_contract_service
    assert isinstance(contract, Phase1ContractService)
    contract.record_acceptance(
        acceptance_run_id="sanitized-acceptance-run",
        result_fingerprint="c" * 64,
        actor="Varun",
        confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
    )


def test_phase2_page_records_a_confirmed_setup_activation(vault_settings) -> None:
    with authenticated_test_app(
        vault_settings,
        configure_prepared=_record_sanitized_phase1_acceptance,
    ) as client:
        before = client.get("/phase-2")
        response = client.post(
            "/phase-2/activate",
            data={"confirmation": "ENABLE PHASE II", "reason": "Sanitized setup"},
            follow_redirects=False,
        )
        after = client.get("/phase-2")

    assert "Enable setup" in before.text
    assert response.status_code == 303
    assert "Phase II is enabled for setup only" in after.text
