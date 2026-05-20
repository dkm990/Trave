# Backend test failures audit

Branch: `audit/backend-test-failures`  
Command: `.\.venv\Scripts\pytest.exe -q`  
Result: `12 failed, 166 passed` (after `split_equally` import compatibility fix)

## Failure table

| Test file | Test name | Error | Checked code/method | Likely type | Risk for working bot | Recommended action |
|---|---|---|---|---|---|---|
| `backend/tests/test_expense_edit_analytics.py` | `test_edit_amount_recalculates_base` | `AttributeError: _StubCurrencyInfo has no attribute rate_date` | `ExpenseService.add_expense` (`exchange_rate_date=rate_info.rate_date`) | Test fixture drift (stub outdated vs current contract) | Low | Update test stub `_StubCurrencyInfo` to include `rate_date` (do not change runtime logic). |
| `backend/tests/test_expense_edit_analytics.py` | `test_edit_participants_recalculates_shares` | same `rate_date` `AttributeError` | `ExpenseService.add_expense` | Test fixture drift | Low | Same fix as above. |
| `backend/tests/test_expense_edit_analytics.py` | `test_cancel_expense_excludes_from_balance` | same `rate_date` `AttributeError` | `ExpenseService.add_expense` | Test fixture drift | Low | Same fix as above. |
| `backend/tests/test_expense_edit_analytics.py` | `test_filter_by_payer` | same `rate_date` `AttributeError` | `ExpenseService.add_expense` | Test fixture drift | Low | Same fix as above. |
| `backend/tests/test_expense_edit_analytics.py` | `test_filter_excludes_canceled_by_default` | same `rate_date` `AttributeError` | `ExpenseService.add_expense` + `list_filtered` | Mixed: fixture drift now; possible behavior drift later | Medium | First fix stub; then validate expected default filtering policy for canceled expenses. |
| `backend/tests/test_expense_edit_analytics.py` | `test_filter_search_in_title` | same `rate_date` `AttributeError` | `ExpenseService.add_expense` + `list_filtered` | Test fixture drift | Low | Same stub fix. |
| `backend/tests/test_expense_edit_analytics.py` | `test_analytics_excludes_canceled` | same `rate_date` `AttributeError` | `ExpenseService.add_expense` + `analytics` | Mixed: fixture drift now; possible policy drift later | Medium | First fix stub; then re-check analytics inclusion/exclusion rules for statuses. |
| `backend/tests/test_expense_edit_analytics.py` | `test_analytics_by_payer_and_participant` | same `rate_date` `AttributeError` | `ExpenseService.add_expense` + `analytics` | Test fixture drift | Low | Same stub fix. |
| `backend/tests/test_parser.py` | `test_parse_short_form_usd_lunch` | `AssertionError: title '50 usd lunch' != 'lunch'` | `RuleBasedProvider.parse_intent` / `_extract_title` | Real parsing regression (or parser rules changed without test update) | Medium | Decide desired short-form behavior; if product expects title cleanup, fix parser; otherwise update test and document new behavior. |
| `backend/tests/test_today_summary.py` | `test_today_summary_groups_by_category` | `AssertionError` on first key order (`'taxi'` vs `'food'`) | `ExpenseService._build_summary` (`by_category` dict insertion order) | Test too strict / brittle | Low | Update test to avoid relying on dict key order, or explicitly sort in service if order is a product requirement. |
| `backend/tests/test_today_summary.py` | `test_today_summary_pending_excluded` | `AssertionError: count 1 != 0` | `ExpenseService.today_summary` query filters only `status != 'canceled'` | Likely real behavior mismatch (pending included) | High | Product decision needed: should pending be excluded? If yes, change service filter; if no, update test/spec. |
| `backend/tests/test_trip_admin.py` | `test_summary_total_and_balances` | `AttributeError: ExpenseService has no list_expenses` | `ExpenseService` API surface; test calls removed/renamed method | Test outdated after refactor | Low | Update test to use current method (`list_filtered` or direct query helper), no runtime change needed. |

## Grouped root causes

1. **Outdated test stubs/contracts** (8 failures): `_StubCurrencyInfo` missing `rate_date`.
2. **Outdated test against refactored service API** (1 failure): `list_expenses` removed/renamed.
3. **Behavior/spec mismatches requiring decision** (3 failures):
   - parser short form title extraction;
   - today summary pending-status policy;
   - category ordering expectation (likely test brittleness).

## Priority plan

1. **Fix tests-only contract drift first (safe, low risk):**
   - update `_StubCurrencyInfo` in `test_expense_edit_analytics.py`;
   - update `test_trip_admin.py` for current `ExpenseService` API.
2. **Resolve high-impact behavior policy next:**
   - confirm whether `pending_confirmed` must be excluded from summary.
3. **Then parser/title and ordering expectations:**
   - parser short-form title cleanup (`"50 USD lunch"` -> `"lunch"`) only after product confirmation;
   - avoid brittle dict-order assertion unless order is explicit UX/API contract.

## Tests that are risky to “just patch”

- `test_today_summary_pending_excluded` and `test_parse_short_form_usd_lunch`: changing tests without product decision may hide real user-facing regressions.
- Any analytics/filter status behavior tests: these can affect user balances/summaries and should be aligned with business rules first.
