# Phase II Reactivation Design

## Goal

Let a user explicitly re-enable Phase II after it was automatically suspended because Phase I changed, while retaining every existing Phase I validation and confirmation safeguard.

## Current behaviour

`Phase2ActivationService.activate()` accepts a suspended grant and creates a new active grant after it validates the current Phase I activation inputs. However, `activation_blocker()` returns the suspension reason, and the activation template hides the confirmation form whenever a blocker is present. A suspended user therefore has no UI path to invoke the safe reactivation operation.

## Design

The Phase II route will treat a suspension as informational rather than as an activation blocker. It will pass the suspension reason to the template separately and continue to render the existing confirmation form. The service remains responsible for validating the current Phase I snapshot before issuing the new grant; an invalid or incomplete Phase I state still blocks the form.

The page will explain that reactivation creates a fresh, reversible approval and requires the same exact `ENABLE PHASE II` confirmation. No provider approval, discovery, scoring, publication, or job-site activity is added or enabled by this change.

## Testing

Add an integration test that creates a valid Phase I acceptance, activates Phase II, changes Phase I readiness to trigger suspension, and asserts that the suspended page shows both the reason and the reactivation form. The existing activation POST test continues to prove the route records a new active grant.

## Scope

Only the Phase II activation service, activation route/template, and integration tests change. Existing data models, activation confirmations, and provider controls remain unchanged.
