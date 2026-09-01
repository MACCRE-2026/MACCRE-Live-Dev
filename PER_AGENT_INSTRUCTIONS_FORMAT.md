# Per-Agent Custom Instructions Format

## Problem
When using MacroNodes with multiple agents (especially CASCADE dialogues), custom instructions were applied to ALL agents in the node. This meant instructions intended for one agent (e.g., Regular_Joe) would also be applied to other agents (e.g., OSINT_Analyst).

## Solution
**Agent-Specific Instruction Format** - Use this format in the custom_instructions field:

```
AgentName:
Instructions for this specific agent go here.
Can span multiple lines.

AnotherAgent:
Different instructions for this agent.
Also can span multiple lines.
```

## Examples

### Example 1: Dialogue with Different Personas
```
Regular_Joe:
You are 75 years old and remember the alien disclosure debates.
You are agnostic but open-minded about extraterrestrial life.

OSINT_Analyst:
Focus strictly on factual reporting.
No personal opinions or speculation.
```

### Example 2: Multi-Agent Research
```
Writer:
Use a casual, conversational tone.
Target audience is general public.

Researcher:
Maintain academic rigor.
Cite all sources using APA format.

Editor:
Check for consistency across both outputs.
```

## Legacy Behavior (Still Supported)
If you DON'T use the agent-specific format, instructions apply to all agents:

```
This instruction applies to ALL agents in this MacroNode.
```

## How It Works

1. **Parser checks** if custom_instructions contains agent names followed by colons
2. **If format detected**: Only applies instructions to matching agent names
3. **If format NOT detected**: Applies to all agents (backward compatible)

## Format Requirements

- Agent name must be at the start of a line
- Must be followed by a colon `:`
- Instructions for that agent follow on the next lines
- Separate different agents with blank lines (`\n\n`)

## Technical Details

Implemented in `flow_engine.py` `_hydrate_topology()` method (lines ~652-675):
- Parses `custom_instructions` for agent-specific blocks
- Matches against `agent_name` from topology row
- Falls back to applying to all agents if no specific match found

## Testing

After updating custom_instructions:
1. Clear Python caches (see CACHE_CLEARING_GUIDE.md)
2. Restart TUI
3. Check topology_snapshot.csv after flow runs
4. Verify `Instruction_Override` column shows correct agent-specific instructions
