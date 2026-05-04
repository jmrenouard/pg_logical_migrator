# Design Doc: TUI Monkey Test for pg_logical_migrator

## Goal
Implement an automated "monkey test" for the Textual-based TUI to detect crashes, race conditions, or UI freezes by simulating rapid, random user inputs.

## Architecture
The monkey test will use Textual's `App.run_test()` and `pilot` mechanism to interact with the `MigratorApp`.

### Mocking Strategy
To ensure the test is fast, deterministic, and doesn't require a live PostgreSQL environment, we will mock the backend components:
- `src.db.PostgresClient`: To avoid actual DB connections.
- `src.checker.DBChecker`: To simulate check results.
- `src.migrator.Migrator`: To simulate migration steps.
- `src.post_sync.PostSync`: To simulate post-sync actions.
- `src.validation.Validator`: To simulate validation results.

### Test Implementation (`tests/integration/test_tui_monkey.py`)
- **Action Loop**: A loop running for 100-200 iterations.
- **Random Actions**:
    - `pilot.press("tab")`, `pilot.press("shift+tab")` for navigation.
    - `pilot.press("enter")`, `pilot.press("space")` for activations.
    - `pilot.press("down")`, `pilot.press("up")` for list/select navigation.
    - `pilot.click(selector)`: Randomly clicking buttons and widgets.
    - `pilot.type(text)`: Entering random strings into `Input` fields.
    - `pilot.press("ctrl+c")` or other escape keys.
- **Error Monitoring**: The test will fail if any unhandled exception occurs within the app during the monkey run.

## Proposed Approach
1.  **Setup**: Use `unittest.mock` to patch backend classes in `src.tui`.
2.  **Instrumentation**: Create a list of all interactive widgets (Buttons, Selects, Inputs, TabPanes).
3.  **Execution**: Use `random.choice` to select an action and an optional target widget.
4.  **Verification**: Assert that the app is still running and hasn't crashed after the loop.

## Success Criteria
- The monkey test runs for the specified number of iterations without throwing an exception.
- No UI freezes or deadlocks detected.

## Next Steps
- Implement the test in `tests/integration/test_tui_monkey.py`.
- Run the test using `pytest`.
- Analyze and fix any issues found.
