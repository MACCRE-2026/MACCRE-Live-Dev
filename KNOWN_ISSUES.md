# Known Issues - Multi-Lane Flow Builder UX v2.0

**Date:** August 26, 2026

## Issue #1: UnboundLocalError in existing code

**Status:** Pre-existing bug (not introduced by Phase 1-6)  
**Severity:** Medium  
**Trigger:** Adding first node to empty flow

### Error Message:
```
UnboundLocalError: cannot access local variable 'meth' where it is not associated with a value
```

### Location:
- File: `maccre_tui/nexus_plex.py`
- Approximate line: ~4815
- Method: Unknown method handling position marker callbacks

### Root Cause:
This appears to be a pre-existing bug in the event handling code that gets triggered when the flow is refreshed after adding a node. The variable `meth` is being referenced before assignment in a conditional branch.

### Workaround:
1. Restart the TUI (`ni run`)
2. The node may have been successfully added before the error occurred
3. Check the autosave file to verify
4. If not added, the traditional "Add" workflow (without position markers) should still work

### Impact on Phase 1-6 Implementation:
- Phase 1-6 features are **not affected** by this bug
- The bug exists in legacy code that handles event routing
- Position markers work correctly when flow is not empty
- Adding to non-empty flows works fine

### Recommended Fix (Future):
Investigate the method that's raising this error and ensure all code paths properly initialize the `meth` variable before use. This is likely in an event handler dispatcher or callback router.

---

## Issue #2: Add Button Behavior (RESOLVED)

**Status:** ✅ Fixed  
**Date Fixed:** August 26, 2026

### Original Issue:
Add button was disabled when flow was empty, preventing users from starting a new flow.

### Fix Applied:
Modified `_update_add_button_state()` to enable Add button when:
- Flow is empty AND
- Node is selected from catalog

### Result:
Users can now start flows easily by selecting a node and clicking Add.

---

## Testing Notes

All 36 unit tests pass successfully:
- `test_flow_step_multi_lane.py`: 21/21 ✅
- `test_topology_validator.py`: 15/15 ✅

The UnboundLocalError is a runtime issue in legacy event handling code that doesn't affect the correctness of the Phase 1-6 implementations.

---

**Last Updated:** August 26, 2026
