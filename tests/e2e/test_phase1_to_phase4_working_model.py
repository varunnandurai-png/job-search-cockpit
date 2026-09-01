from tests.support.phase3 import (
    assert_requirement_ledger_uses_phase1_projection,
    complete_local_manual_mapping,
    complete_phase1_acceptance,
    finalise_with_test_headshot,
    phase1_to_phase4_cockpit,
    request_fake_drive_backup,
    select_first_eligible_candidate,
    verification_form,
)


def test_phase1_to_phase4_working_model(vault_settings) -> None:
    with phase1_to_phase4_cockpit(vault_settings) as authenticated_cockpit:
        assert authenticated_cockpit.get("/search-profile").status_code == 200
        complete_phase1_acceptance(authenticated_cockpit)

        activated = authenticated_cockpit.post(
            "/phase-2/activate",
            data={"confirmation": "ENABLE PHASE II", "reason": "local acceptance"},
            follow_redirects=False,
        )
        assert activated.status_code == 303

        discovered = authenticated_cockpit.post(
            "/phase-2/discovery-runs", data={}, follow_redirects=False
        )
        assert discovered.status_code == 303
        review = authenticated_cockpit.get("/phase-2/review")
        revision_id, job_id = select_first_eligible_candidate(authenticated_cockpit, review)
        complete_local_manual_mapping(authenticated_cockpit, revision_id)
        verified = authenticated_cockpit.post(
            "/phase-2/verify", data=verification_form(revision_id), follow_redirects=False
        )
        assert verified.status_code == 303
        assert_requirement_ledger_uses_phase1_projection(authenticated_cockpit, job_id)

        started = authenticated_cockpit.post(
            "/phase-2/resume-reviews", data={"job_id": job_id}, follow_redirects=False
        )
        assert started.status_code == 303
        finalised = finalise_with_test_headshot(authenticated_cockpit, started)
        assert ".docx" in finalised.text and ".pdf" in finalised.text

        backup = request_fake_drive_backup(authenticated_cockpit, finalised)
        assert "backed_up" in backup.text
        assert "submit application" not in backup.text.casefold()
