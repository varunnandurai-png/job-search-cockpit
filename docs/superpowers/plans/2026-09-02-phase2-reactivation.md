# Phase II Reactivation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a user to explicitly re-enable a suspended Phase II activation after current Phase I validation succeeds.

**Architecture:** Keep suspension validation and reactivation issuance in `Phase2ActivationService`. Split the page's informational suspension reason from a genuine blocker so the template can render the existing guarded form for a suspended state.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, SQLAlchemy, pytest.

## Global Constraints

- The exact confirmation remains `ENABLE PHASE II`.
- A current, valid Phase I snapshot remains mandatory before reactivation.
- No provider, discovery, scoring, publication, or application action is enabled by this change.

---

### Task 1: Render explicit reactivation for a suspended grant

**Files:**
- Modify: `tests/integration/test_phase2_activation_page.py`
- Modify: `src/job_search_cockpit/phase2/activation.py`
- Modify: `src/job_search_cockpit/web/routes/phase2.py`
- Modify: `src/job_search_cockpit/web/templates/phase2_activation.html`

**Interfaces:**
- Consumes: `Phase2ActivationService.validate_current()` and `Phase2ActivationService.activation_blocker()`.
- Produces: an activation page that shows a suspension reason and the existing CSRF-protected activation form when current Phase I inputs validate.

- [ ] **Step 1: Write the failing test**

```python
def test_suspended_phase2_page_offers_explicit_reactivation(vault_settings) -> None:
    with authenticated_test_app(
        vault_settings,
        configure_prepared=_record_sanitized_phase1_acceptance,
    ) as client:
        client.post("/phase-2/activate", data={"confirmation": "ENABLE PHASE II"})
        # Mutate the approved Phase I fixture through its coordinator to invalidate the grant.
        page = client.get("/phase-2")

    assert "Phase II is suspended" in page.text
    assert "Phase I changed:" in page.text
    assert "Reactivate setup" in page.text
    assert 'action="/phase-2/activate"' in page.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_phase2_activation_page.py::test_suspended_phase2_page_offers_explicit_reactivation -q`

Expected: FAIL because the current template hides the form whenever the suspension reason is treated as a blocker.

- [ ] **Step 3: Write minimal implementation**

```python
# activation.py
def activation_blocker(self) -> str | None:
    if self.activation_view().state == "suspended":
        self.phase1_port.activation_inputs()
        return None

# phase2_activation.html
{% if state == "suspended" %}
  <p>{{ suspension_reason }}</p>
{% endif %}
```

Pass `suspension_reason` from the route and change the form heading/button copy to `Reactivate setup` / `Reactivate Phase II setup` when `state == "suspended"`.

- [ ] **Step 4: Run focused tests to verify it passes**

Run: `uv run pytest tests/integration/test_phase2_activation_page.py -q`

Expected: PASS, including the new suspended-reactivation case and existing activation cases.

- [ ] **Step 5: Run quality checks and commit**

Run: `uv run ruff check . && uv run mypy src && uv run pytest tests/integration/test_phase2_activation_page.py -q`

Then stage only the two documentation files and the four task files, inspect the staged diff for secrets, and commit with:

```bash
git commit -m "fix: allow explicit Phase II reactivation"
```
