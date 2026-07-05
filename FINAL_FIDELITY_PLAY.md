# Final Fidelity Play (One-Go Execution)

This pass focuses on pushing from deterministic broad coverage to stricter
official-rule behavior in the live runtime.

## Implemented in this play

1. **Official rules baseline module**
   - Added `core/official_rules.py`
   - Opening setup constants and rule context
   - Turn-context aware legality checks
   - Global state invariants (bench/prize caps)
   - Official setup routine with mulligan + bonus draw behavior

2. **Setup phase wiring**
   - `core/setup_engine.py` now delegates setup to official setup routine
   - Consistent opening hand/prize initialization

3. **Legal-action fidelity**
   - `core/legal_actions_full.py` now applies official-rule checks
   - First-turn attack/supporter restrictions are surfaced as legality reasons
   - Added richer action legality metadata (`rule_refs`)

4. **Turn-engine enforcement**
   - `core/turn_engine.py` now:
     - updates official turn context every turn
     - validates selected actions against official restrictions
     - forces pass for illegal scripted/selected actions
     - enforces invariants after setup/action/checkup
     - applies attack cost payment before attack program execution

5. **Regression coverage**
   - Added `tests/test_official_rules.py`
   - Expanded tests for legal actions and turn flow restrictions

## Validation

- Unit tests: `114` passing
- Quality gates: passing
- Sampled text resolution: `100.0%`
- Replay determinism: passing
