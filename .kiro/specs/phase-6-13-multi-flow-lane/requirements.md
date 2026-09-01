# Requirements Document: Phase 6.13 — Multi-Flow-Line Authoring & Visualization

## Introduction

Phase 6.13 extends MACCRE's parallel scatter execution (Phase 6.12) with multi-lane topology authoring, visualization, and referencing capabilities. Users can author per-lane topologies where each CTRL_SCATTER branch executes different node sequences, visualize parallel lanes with heterogeneous temporal lengths, and reference nodes across lanes via tether IDs. This removes the current "single-timeline illusion" planning ceiling where scatter can fan out 8 agents but all branches must execute identical sequences.

## Glossary

- **Flow_Line**: A linear temporal trajectory from flow start to flow finish, identified by a hierarchical tether ID (e.g., `X`, `X.1`, `X.2`)
- **Flow_Lane**: A parallel execution branch spawned by CTRL_SCATTER, one per slotted agent, visualized as a horizontal row in the Active Flow Sequence
- **Tether_ID**: Hierarchical identifier for flow lines (root `X` spawns children `X.1`, `X.2` at CTRL_SCATTER nodes)
- **Active_Flow_Sequence**: TUI widget displaying the linear sequence of MacroNode steps in the current flow
- **TopologyVisualizer**: TUI widget rendering the flow topology as a tree structure with state-driven node styling
- **NodeConfigModal**: TUI modal dialog for configuring MacroNode instances (payload routing, agents, instructions, control node parameters)
- **Node_Catalog**: TUI panel listing available MacroNodes that can be added to the flow
- **Scatter_Slot**: A configured agent position within a CTRL_SCATTER node, one slot per parallel lane
- **CTRL_SCATTER**: Control node that fans out execution to N parallel lanes (max 8 concurrent agents per Phase 6.12)
- **CTRL_MERGE**: Control node that gathers results from parallel lanes and waits for all branches to complete
- **CTRL_CONCAT**: Control node that concatenates outputs from parallel lanes with a delimiter
- **CTRL_BRANCH**: Control node that routes execution based on conditional logic and can gather from multiple inputs
- **Gather_Node**: Any control node that waits for multiple upstream branches (CTRL_MERGE, CTRL_CONCAT, CTRL_BRANCH)
- **FlowStep**: Data model representing one step in a flow, containing MacroNode name, agent mapping, payload mode, and configuration
- **TopologyNodeData**: Data model representing one node in the topology visualization, containing node ID, role, next nodes, wait-for dependencies, flow line ID, and tether ID
- **NodeAppendix**: Structured argument type that injects a 2D topology map into an agent's silent API context
- **TetherNotesModal**: Floating, draggable modal for tracking tether IDs the user wants to reference
- **Temporal_Position**: The sequential index of a node within its flow line from scatter to merge
- **Heterogeneous_Length**: The property where parallel lanes contain different numbers of nodes between scatter and merge points

## Requirements

### Requirement 1: CTRL_SCATTER Modal Reactive Rendering

**User Story:** As a flow author, I want to see scatter agent slots appear immediately when I add them in NodeConfigModal, so that I can visually confirm my multi-agent configuration without closing and reopening the modal.

#### Acceptance Criteria

1.1. WHEN the user clicks the "+ Add Agent" button in NodeConfigModal for a CTRL_SCATTER node, THE NodeConfigModal SHALL render the agent label, ⚙ Overrides button, and ✕ Remove button within 200ms

1.2. WHEN the user clicks the "✕" button for a scatter agent slot, THE NodeConfigModal SHALL remove that slot's visual elements within 200ms

1.3. WHEN the scatter agent list contains 8 agents (MAX_SCATTER_AGENTS), THE NodeConfigModal SHALL disable the "+ Add Agent" button

1.4. WHEN the user clicks "⚙ Overrides" for a scatter agent slot, THE NodeConfigModal SHALL open the agent overrides dialog with the current configuration for that specific agent

1.5. FOR ALL scatter agent slot modifications (add, remove, reorder), the scatter slot header count SHALL update to reflect the current number of slotted agents

### Requirement 2: Active Flow Sequence Scatter Visualization

**User Story:** As a flow author, I want to see all slotted scatter agents appear in the Active Flow Sequence after configuring CTRL_SCATTER, so that I have visual confirmation of N-way fan-out before executing the flow.

#### Acceptance Criteria

2.1. WHEN the user saves NodeConfigModal configuration for a CTRL_SCATTER node with N slotted agents, THE Active_Flow_Sequence SHALL display N agent names beneath the CTRL_SCATTER node label

2.2. THE Active_Flow_Sequence SHALL display each scatter agent name in the format `{agent_name}.{tether_id}` (e.g., "ResearchAgent.X.1")

2.3. WHEN a CTRL_SCATTER node has zero slotted agents, THE Active_Flow_Sequence SHALL display a warning indicator "[!] No agents configured"

2.4. WHEN the user hovers over a scatter agent name in Active_Flow_Sequence, THE Active_Flow_Sequence SHALL display a tooltip showing the full tether ID

2.5. FOR ALL scatter agent names displayed, the text color SHALL use a distinct accent color (different from regular node names) to indicate parallel execution

### Requirement 3: Multi-Lane Expansion Toggle

**User Story:** As a flow author, I want to expand the Active Flow Sequence vertically to see all parallel lanes created by scatter, so that I can visualize heterogeneous lane topologies and understand temporal alignment.

#### Acceptance Criteria

3.1. THE Active_Flow_Sequence SHALL provide a toggle button labeled "◧ Expand All / ◨ Collapse All"

3.2. WHEN the user clicks "◧ Expand All" AND the flow contains CTRL_SCATTER nodes, THE Active_Flow_Sequence SHALL expand to show one row per flow lane

3.3. WHEN the Active_Flow_Sequence is in expanded mode, THE Active_Flow_Sequence SHALL render each lane as a horizontal row with lane label `{agent_name}.{tether_id}` on the left

3.4. WHEN lanes have heterogeneous lengths, THE Active_Flow_Sequence SHALL insert dashed filler boxes to align all lanes temporally at the CTRL_MERGE boundary

3.5. WHEN the user clicks "◨ Collapse All", THE Active_Flow_Sequence SHALL return to single-row mode showing only the primary flow line

3.6. WHILE the Active_Flow_Sequence is in expanded mode, each lane row SHALL provide an individual expand/collapse button (▾ / ▸)

3.7. WHEN the user collapses an individual lane, THE Active_Flow_Sequence SHALL replace that lane's nodes with a summary indicator showing node count (e.g., "[3 nodes]")

### Requirement 4: Per-Lane Node Highlighting

**User Story:** As a flow author, I want to double-click a node name in TopologyVisualizer to highlight it and see which lane it belongs to, so that I can prepare to insert new nodes on that specific flow line.

#### Acceptance Criteria

4.1. WHEN the user double-clicks a node label in TopologyVisualizer, THE TopologyVisualizer SHALL highlight that node with a distinct border color (e.g., cyan)

4.2. WHEN a node is highlighted in TopologyVisualizer, THE Node_Catalog SHALL apply a matching border color to indicate insertion-ready state

4.3. WHEN the user clicks elsewhere (background, different node, modal overlay), THE TopologyVisualizer SHALL remove the highlight from the previously highlighted node

4.4. WHEN a node is highlighted, THE Active_Flow_Sequence SHALL scroll to and highlight the corresponding node in the expanded lane view if applicable

4.5. WHILE a node is highlighted, THE TopologyVisualizer SHALL display the node's tether ID in a tooltip when the user hovers over the highlighted node

### Requirement 5: Per-Lane Node Insertion

**User Story:** As a flow author, I want to add a node from the catalog while a lane node is highlighted, so that the new node inserts immediately after the highlighted node on that specific flow line rather than at the end of the entire flow.

#### Acceptance Criteria

5.1. WHEN a node on flow line `X.N` is highlighted AND the user clicks a node in Node_Catalog, THE Flow_Engine SHALL insert the selected node immediately after the highlighted node on flow line `X.N`

5.2. IF the highlighted node is not between a CTRL_SCATTER and its corresponding Gather_Node boundary, THEN THE Flow_Engine SHALL reject the insertion and display an error message "Cannot insert outside scatter→merge boundaries"

5.3. WHEN the insertion succeeds, THE TopologyVisualizer SHALL update to show the new node in the correct position within the tree structure

5.4. WHEN the insertion succeeds, THE Active_Flow_Sequence SHALL update to show the new node in the correct lane and temporal position

5.5. WHEN the insertion succeeds, THE Flow_Engine SHALL assign the new node a tether ID that matches its parent flow line (e.g., if inserted on line `X.2`, tether becomes `X.2`)

5.6. WHEN the insertion succeeds, THE TopologyVisualizer SHALL remove the highlight from the previously highlighted node

5.7. IF no node is highlighted AND the user clicks a node in Node_Catalog, THEN THE Flow_Engine SHALL append the node to the end of the primary flow line (backward-compatible behavior)

### Requirement 6: Lane Auto-Naming

**User Story:** As a flow author, I want scatter lanes to be automatically named with a meaningful default format, so that I can distinguish lanes without manual naming unless I choose to customize them.

#### Acceptance Criteria

6.1. WHEN a CTRL_SCATTER node creates N flow lanes with N slotted agents, THE Flow_Engine SHALL assign each lane a default name in the format `{agent_name}.{tether_id}`

6.2. WHEN the user opens NodeConfigModal for a CTRL_SCATTER node with existing lanes, THE NodeConfigModal SHALL display an editable text field for each lane's custom name

6.3. WHEN the user modifies a lane name in NodeConfigModal and clicks Save, THE Flow_Engine SHALL persist the custom lane name and use it in all visualizations

6.4. WHEN a lane has a custom name, THE Active_Flow_Sequence SHALL display the custom name instead of the auto-generated format

6.5. FOR ALL lane names (auto-generated or custom), the maximum length SHALL be 50 characters

### Requirement 7: CTRL_MERGE Wait-All Deterministic Gather

**User Story:** As a flow author, I want CTRL_MERGE to wait for all scatter branches to complete regardless of heterogeneous lane lengths, so that downstream nodes receive complete data from all parallel agents.

#### Acceptance Criteria

7.1. WHEN a Gather_Node (CTRL_MERGE, CTRL_CONCAT, CTRL_BRANCH) is reached by any lane, THE Flow_Engine SHALL check completion status of all upstream scatter lanes that feed into that Gather_Node

7.2. WHILE any upstream scatter lane has uncompleted nodes before the Gather_Node boundary, THE Flow_Engine SHALL prevent the Gather_Node from executing

7.3. WHEN all upstream scatter lanes have completed their pre-merge nodes, THE Flow_Engine SHALL execute the Gather_Node within 500ms

7.4. WHEN the Gather_Node begins execution, THE TopologyVisualizer SHALL mark the Gather_Node as ACTIVE

7.5. FOR ALL lanes feeding into a Gather_Node, the completion check SHALL use the lane's final node before the merge boundary (not the lane's total length)

### Requirement 8: CTRL_MERGE Synthesis Agent Slot

**User Story:** As a flow author, I want to optionally configure a synthesis or judge agent on CTRL_MERGE nodes, so that I can programmatically select or route gathered results before continuing the flow.

#### Acceptance Criteria

8.1. WHEN the user opens NodeConfigModal for a CTRL_MERGE node, THE NodeConfigModal SHALL display an optional "Synthesis Agent" dropdown populated with all roster agents

8.2. WHEN the user selects a synthesis agent AND saves the configuration, THE Flow_Engine SHALL execute that agent after all scatter lanes complete but before merging payloads

8.3. WHEN a synthesis agent is configured, THE Flow_Engine SHALL provide that agent with structured arguments containing all scatter lane output payloads as a list

8.4. WHEN the synthesis agent completes, THE Flow_Engine SHALL parse the agent's response for a `ROUTE TO: $TetherID` directive

8.5. IF the synthesis agent's response contains `ROUTE TO: $TetherID` AND `$TetherID` matches an existing node's tether ID, THEN THE Flow_Engine SHALL route execution to that node and skip the default merge behavior

8.6. IF the synthesis agent's response does not contain a valid routing directive, THEN THE Flow_Engine SHALL proceed with the default merge behavior (structured or concat based on merge_mode)

### Requirement 9: CTRL_MERGE Fallback and Self-Heal

**User Story:** As a flow author, I want to configure fallback behavior for CTRL_MERGE nodes when scatter lanes timeout or fail, so that the flow can self-heal and continue execution rather than deadlocking indefinitely.

#### Acceptance Criteria

9.1. WHEN the user opens NodeConfigModal for a Gather_Node, THE NodeConfigModal SHALL display optional fields for "Timeout (seconds)" and "Partial Merge Threshold (%)"

9.2. WHEN a Gather_Node has a configured timeout AND the timeout expires before all lanes complete, THE Flow_Engine SHALL log a warning message listing incomplete lanes

9.3. WHEN a Gather_Node has a configured partial merge threshold (e.g., 75%) AND that percentage of lanes complete within the timeout, THE Flow_Engine SHALL proceed with merging only the completed lane payloads

9.4. WHEN the Flow_Engine proceeds with partial merge, THE TopologyVisualizer SHALL mark incomplete lanes' final nodes as FAILED

9.5. WHEN a Gather_Node has no configured timeout, THE Flow_Engine SHALL wait indefinitely for all lanes to complete (default deterministic behavior)

9.6. WHEN the Flow_Engine applies fallback behavior, THE Flow_Engine SHALL write a detailed event to the telemetry database including gather node ID, timeout value, completed lanes, and incomplete lanes

### Requirement 10: Tether ID Display in Active Flow Sequence

**User Story:** As a flow author, I want to see tether IDs displayed alongside node names in the Active Flow Sequence, so that I can reference nodes by tether ID without opening additional modals or searching through topology.

#### Acceptance Criteria

10.1. THE Active_Flow_Sequence SHALL display each node in the format `NodeName (TetherID)` (e.g., "DET_REVIEW (X.2.1)")

10.2. WHEN the user hovers over a node in Active_Flow_Sequence, THE Active_Flow_Sequence SHALL display a tooltip showing the full tether ID and flow line ID

10.3. WHEN the Active_Flow_Sequence is in expanded multi-lane mode, THE Active_Flow_Sequence SHALL display tether IDs for all nodes in all visible lanes

10.4. FOR ALL tether ID displays, the text color SHALL use a muted accent color distinct from the node name to improve readability

10.5. WHEN a node has no tether ID assigned (e.g., before Phase 6.13 migration), THE Active_Flow_Sequence SHALL display only the node name without parentheses

### Requirement 11: Tether ID Display in TopologyVisualizer

**User Story:** As a flow author, I want to see tether IDs in the TopologyVisualizer tree view, so that I can understand the hierarchical structure of flow lines while viewing the topology DAG.

#### Acceptance Criteria

11.1. THE TopologyVisualizer SHALL render each tree node label in the format `NodeName (TetherID)` when tether ID is available

11.2. WHEN the user hovers over a tree node in TopologyVisualizer, THE TopologyVisualizer SHALL display a tooltip showing the node's full tether ID, flow line ID, and role

11.3. WHEN the TopologyVisualizer renders a CTRL_SCATTER node with N child lanes, THE TopologyVisualizer SHALL indent child lane nodes and visually group them under the scatter parent

11.4. WHEN the TopologyVisualizer renders a Gather_Node, THE TopologyVisualizer SHALL display incoming edges from all upstream scatter lanes

11.5. FOR ALL tether ID displays in tree nodes, the tether ID SHALL be rendered in a muted color with smaller font size than the node name

### Requirement 12: TetherNotesModal Keyboard Shortcut

**User Story:** As a flow author, I want to press SHIFT+F7 and click a node to open a floating note-taking modal, so that I can track tether IDs I want to reference without losing my place in the topology visualization.

#### Acceptance Criteria

12.1. WHEN the user presses SHIFT+F7, THE TUI SHALL enter "tether note mode" and display a visual indicator (e.g., cursor changes, status message)

12.2. WHILE in tether note mode AND the user clicks a node in TopologyVisualizer, THE TUI SHALL open a TetherNotesModal populated with that node's name, tether ID, and flow line ID

12.3. THE TetherNotesModal SHALL be draggable by its title bar to any position on the screen

12.4. THE TetherNotesModal SHALL display a list of all previously noted nodes with their tether IDs, organized by insertion order

12.5. WHEN the TetherNotesModal contains at least one noted node, THE TetherNotesModal SHALL provide a "📋 Copy All Tether IDs" button that copies all tether IDs to the system clipboard as a newline-separated list

12.6. THE TetherNotesModal SHALL provide a "✕" button to remove individual noted nodes from the list

12.7. WHEN the user clicks outside the TetherNotesModal, THE TetherNotesModal SHALL remain open (must explicitly close via close button or ESC key)

12.8. WHEN the user presses ESC while TetherNotesModal has focus, THE TetherNotesModal SHALL close

### Requirement 13: TetherNotesModal Docking

**User Story:** As a flow author, I want to dock the TetherNotesModal to the TUI header, so that I can free up screen space while keeping my tether ID references accessible via a single click.

#### Acceptance Criteria

13.1. THE TetherNotesModal SHALL provide a "⬆ Dock" button in its title bar

13.2. WHEN the user clicks "⬆ Dock", THE TetherNotesModal SHALL collapse to an icon in the TUI header bar labeled with the current note count (e.g., "📌 6 notes")

13.3. WHEN the docked icon is clicked, THE TetherNotesModal SHALL expand to its previous size and position

13.4. WHILE the TetherNotesModal is docked, THE TUI_Header SHALL display the docked icon in a fixed position (e.g., top-right corner)

13.5. WHEN the user enters SHIFT+F7 mode and adds a new note WHILE the modal is docked, THE TUI SHALL update the docked icon's note count without expanding the modal

13.6. WHEN the user clicks "⬇ Undock" in the expanded modal, THE TetherNotesModal SHALL detach from the header and return to floating draggable state

### Requirement 14: Node Selection Dropdowns with Tether ID Grouping

**User Story:** As a flow author, I want to see tether IDs next to node names in all node selection dropdowns (e.g., Route To, Loop Target), so that I can unambiguously identify target nodes when multiple nodes share the same name.

#### Acceptance Criteria

14.1. WHEN the user opens a dropdown that lists flow nodes (e.g., "Route To" in CTRL_BRANCH config, "Loop Target" in CTRL_RECURSION config), THE NodeConfigModal SHALL display each option in the format `NodeName (TetherID)`

14.2. THE NodeConfigModal SHALL group dropdown options by flow line ID, with a visual separator or header between groups (e.g., "Flow Line X.1", "Flow Line X.2")

14.3. WITHIN each flow line group, THE NodeConfigModal SHALL sort nodes by their temporal position (sequential order within the lane)

14.4. WHEN multiple nodes have the same node name, THE NodeConfigModal SHALL render them as distinct options differentiated by their tether IDs

14.5. WHEN the user selects an option from a grouped dropdown, THE Flow_Engine SHALL persist the selected node's tether ID (not just the node name) in the configuration

### Requirement 15: NodeAppendix Structured Argument - ALL Mode

**User Story:** As a flow author, I want to inject a complete 2D topology map into an agent's context, so that the agent can reason about the entire flow structure and reference any node by tether ID in its response.

#### Acceptance Criteria

15.1. WHEN the user opens the structured arguments section in NodeConfigModal, THE NodeConfigModal SHALL provide a "NodeAppendix" argument type option

15.2. WHEN the user adds a NodeAppendix argument with mode "ALL", THE Flow_Engine SHALL inject a JSON structure containing all nodes across all flow lines into the agent's silent API context

15.3. THE NodeAppendix JSON structure SHALL include for each node: node ID, role, tether ID, flow line ID, temporal position, and next node tether IDs

15.4. THE NodeAppendix JSON structure SHALL organize nodes hierarchically by flow line (root flow line first, then child lanes grouped under their parent CTRL_SCATTER node)

15.5. WHEN the agent receives the NodeAppendix, THE Flow_Engine SHALL prepend it to the agent's system prompt as a code block with the header "## Topology Reference"

### Requirement 16: NodeAppendix Structured Argument - Scoped Mode

**User Story:** As a flow author, I want to inject only the current lane's topology into an agent's context, so that the agent can focus on its local execution path without being overwhelmed by unrelated parallel lanes.

#### Acceptance Criteria

16.1. WHEN the user adds a NodeAppendix argument with mode "Scoped", THE Flow_Engine SHALL inject a JSON structure containing only nodes on the same flow line as the receiving agent

16.2. THE scoped NodeAppendix SHALL include all nodes from the flow line's start (either root node or CTRL_SCATTER parent) to its end (CTRL_MERGE boundary or flow termination)

16.3. THE scoped NodeAppendix SHALL include the immediate CTRL_SCATTER parent and CTRL_MERGE child nodes as context boundaries, even though they belong to a different tether ID

16.4. FOR ALL scoped NodeAppendix injections, the JSON structure format SHALL match the ALL mode format (same schema, subset of nodes)

16.5. WHEN the agent's flow line is the root line (not spawned by CTRL_SCATTER), THE scoped NodeAppendix SHALL include all nodes on the primary flow line

### Requirement 17: FlowStep Data Model Enhancement

**User Story:** As a system maintainer, I want FlowStep to store per-lane child steps in a nested list structure, so that the flow engine can serialize and deserialize multi-lane topologies without data loss.

#### Acceptance Criteria

17.1. THE FlowStep class SHALL provide a `children: list[list[FlowStep]]` attribute initialized to an empty list by default

17.2. WHEN a CTRL_SCATTER FlowStep fans out to N lanes, THE Flow_Engine SHALL populate `children` with N sublists, one per lane

17.3. WHEN a lane contains M nodes between scatter and merge, THE Flow_Engine SHALL populate that lane's sublist with M FlowStep objects in temporal order

17.4. THE FlowStep.to_dict() method SHALL recursively serialize all child FlowSteps into nested JSON structure

17.5. THE FlowStep.from_dict() classmethod SHALL recursively deserialize nested JSON structure into FlowStep objects with populated `children` attribute

17.6. WHEN a FlowStep has no child lanes (not a CTRL_SCATTER or a leaf node), THE FlowStep.children attribute SHALL remain an empty list

### Requirement 18: Tether ID Auto-Generation for Child Lanes

**User Story:** As a system maintainer, I want scatter lanes to automatically receive hierarchical tether IDs, so that tether ID namespacing reflects the tree structure of flow lines without manual bookkeeping.

#### Acceptance Criteria

18.1. WHEN a CTRL_SCATTER node with tether ID `X` spawns N lanes, THE Flow_Engine SHALL assign child lanes tether IDs `X.1`, `X.2`, ..., `X.N` in the order agents are slotted

18.2. WHEN a node is inserted into a lane with tether ID `X.K`, THE Flow_Engine SHALL assign the inserted node tether ID `X.K` (inherits parent lane's tether)

18.3. WHEN a CTRL_SCATTER node within a child lane (nested scatter) spawns lanes, THE Flow_Engine SHALL append a new level to the tether hierarchy (e.g., `X.1.1`, `X.1.2`)

18.4. WHEN the flow contains no CTRL_SCATTER nodes (linear flow), THE Flow_Engine SHALL assign all nodes a root tether ID (e.g., `X`)

18.5. FOR ALL tether ID assignments, the Flow_Engine SHALL ensure uniqueness within a single flow execution (no duplicate tether IDs)

### Requirement 19: Nested Scatter Support

**User Story:** As a flow author, I want to nest CTRL_SCATTER nodes within scatter lanes until complexity becomes unmanageable, so that the system does not artificially limit my authoring capability but naturally surfaces when I have exceeded manageable complexity.

#### Acceptance Criteria

19.1. THE Flow_Engine SHALL allow a CTRL_SCATTER node to be inserted within a child lane of another CTRL_SCATTER node (nested scatter)

19.2. WHEN nested scatter depth reaches 3 levels (root → child → grandchild), THE TopologyVisualizer SHALL display a warning icon next to nested CTRL_SCATTER nodes

19.3. WHEN nested scatter creates more than 64 total concurrent lanes, THE Flow_Engine SHALL reject further scatter node insertions and display an error message "Exceeded maximum concurrent lane limit (64)"

19.4. WHEN the user attempts to execute a flow with nested scatter, THE Flow_Engine SHALL validate that all nested scatter branches have corresponding CTRL_MERGE nodes before allowing execution

19.5. FOR ALL nested scatter topologies, THE TopologyVisualizer SHALL render child lanes with increased indentation to visually indicate nesting depth

### Requirement 20: Active Flow Sequence Dynamic Vertical Scaling

**User Story:** As a flow author, I want the Active Flow Sequence to scale vertically when I expand multi-lane views, so that I can see all lanes without horizontal scrolling or clipped content.

#### Acceptance Criteria

20.1. THE Active_Flow_Sequence CSS SHALL use relative height units (e.g., `height: auto; max-height: 70vh`) instead of fixed pixel heights

20.2. WHEN the user expands multi-lane view AND the total lane count exceeds the available vertical space, THE Active_Flow_Sequence SHALL display a vertical scrollbar

20.3. THE Active_Flow_Sequence SHALL maintain a minimum height of 10 lines to prevent collapse when only 1-2 nodes are present

20.4. WHEN the terminal window is resized, THE Active_Flow_Sequence SHALL recalculate its maximum height to maintain proportional screen usage

20.5. THE Active_Flow_Sequence SHALL preserve horizontal width (no horizontal scaling) regardless of content length or zoom level

### Requirement 21: TopologyVisualizer Dynamic Vertical Scaling

**User Story:** As a flow author, I want the TopologyVisualizer to scale vertically as I add more nodes, so that I can see the entire topology tree without clipping or forced scrolling at low zoom levels.

#### Acceptance Criteria

21.1. THE TopologyVisualizer CSS SHALL use relative height units (e.g., `height: 1fr; min-height: 6`) to allow dynamic expansion

21.2. WHEN the topology tree exceeds the available vertical space, THE TopologyVisualizer SHALL display a vertical scrollbar

21.3. THE TopologyVisualizer SHALL maintain a minimum height of 10 lines to ensure visibility of at least 3-4 nodes

21.4. WHEN the user collapses or expands tree branches, THE TopologyVisualizer SHALL recalculate its content height and adjust scrollbar visibility

21.5. THE TopologyVisualizer SHALL preserve horizontal width regardless of terminal zoom level

### Requirement 22: Terminal Zoom Button Persistence

**User Story:** As a flow author, I want buttons above and below the Active Flow Sequence to remain visible at all terminal zoom levels (50%, 100%, 150%), so that I can always access flow controls without hunting for off-screen elements.

#### Acceptance Criteria

22.1. THE Active_Flow_Sequence parent container SHALL use CSS positioning (e.g., `position: relative`) to anchor button rows

22.2. THE button rows above Active_Flow_Sequence (e.g., "🏗 Build Flow", "▶ Run Flow") SHALL use relative positioning within the container (e.g., `position: sticky; top: 0`)

22.3. THE button rows below Active_Flow_Sequence SHALL use relative positioning within the container (e.g., `position: sticky; bottom: 0`)

22.4. WHEN the terminal zoom level changes (50%, 100%, 150%), THE button rows SHALL remain within the visible viewport without requiring horizontal scrolling

22.5. FOR ALL zoom levels, button text SHALL remain readable (minimum font size 8pt after zoom scaling)

### Requirement 23: Per-Lane Node Parser and Pretty Printer

**User Story:** As a system maintainer, I want per-lane topologies to serialize and deserialize correctly through the flow history persistence layer, so that users can save, resume, and share multi-lane flows without corruption.

#### Acceptance Criteria

23.1. THE Flow_Engine SHALL serialize multi-lane FlowStep trees to JSON using the enhanced `FlowStep.to_dict()` method

23.2. THE Flow_Engine SHALL deserialize multi-lane FlowStep trees from JSON using the enhanced `FlowStep.from_dict()` classmethod

23.3. WHEN a multi-lane flow is saved to `flow_history.json`, THE Flow_Engine SHALL preserve all child lane structures, tether IDs, and temporal ordering

23.4. WHEN a multi-lane flow is loaded from `flow_history.json`, THE Flow_Engine SHALL reconstruct the exact topology including all nested lanes and node configurations

23.5. FOR ALL multi-lane flows, the round-trip property SHALL hold: loading then saving a flow produces an equivalent JSON structure (parse → print → parse equivalence)

### Requirement 24: Multi-Lane Topology Validation

**User Story:** As a flow author, I want the system to validate multi-lane topologies before execution, so that I receive clear error messages for invalid structures (orphaned lanes, missing merge nodes) rather than runtime failures.

#### Acceptance Criteria

24.1. WHEN the user attempts to execute a flow, THE Flow_Engine SHALL validate that every CTRL_SCATTER node has a reachable CTRL_MERGE, CTRL_CONCAT, or CTRL_BRANCH node

24.2. IF a CTRL_SCATTER node has no reachable Gather_Node, THEN THE Flow_Engine SHALL reject execution and display an error message "CTRL_SCATTER at tether {tether_id} has no merge point"

24.3. WHEN the user attempts to execute a flow, THE Flow_Engine SHALL validate that all Gather_Node wait-for dependencies reference existing tether IDs

24.4. IF a Gather_Node references a non-existent tether ID, THEN THE Flow_Engine SHALL reject execution and display an error message "Gather node {node_id} references invalid tether ID {tether_id}"

24.5. WHEN validation detects errors, THE TopologyVisualizer SHALL highlight all invalid nodes with a red border

24.6. WHEN validation succeeds, THE Flow_Engine SHALL proceed to preflight checks without additional user prompts

### Requirement 25: Migration Support for Pre-6.13 Flows

**User Story:** As a system maintainer, I want flows authored before Phase 6.13 to load correctly without tether IDs or child lane structures, so that existing workflows remain functional after upgrading.

#### Acceptance Criteria

25.1. WHEN the Flow_Engine loads a FlowStep from JSON that lacks a `children` field, THE Flow_Engine SHALL initialize `children` to an empty list

25.2. WHEN the Flow_Engine loads a TopologyNodeData that lacks a `tether_id` field, THE Flow_Engine SHALL assign a default tether ID (e.g., `LEGACY_X`) and log a warning

25.3. WHEN a legacy flow contains CTRL_SCATTER nodes without slotted agents in the new format, THE Flow_Engine SHALL interpret them as single-agent scatter (backward-compatible execution)

25.4. WHEN the Active_Flow_Sequence renders a node with no tether ID, THE Active_Flow_Sequence SHALL display only the node name without parentheses (graceful degradation)

25.5. FOR ALL legacy flows, the Flow_Engine SHALL log a migration notice recommending the user re-save the flow to populate tether IDs and child lane structures

### Requirement 26: Telemetry for Multi-Lane Execution

**User Story:** As a system operator, I want multi-lane execution metrics (lane count, temporal skew, merge wait times) recorded in the telemetry database, so that I can analyze parallel efficiency and identify bottlenecks.

#### Acceptance Criteria

26.1. WHEN a CTRL_SCATTER node executes, THE Flow_Engine SHALL write a telemetry event containing scatter node ID, tether ID, lane count, and timestamp

26.2. WHEN a Gather_Node waits for incomplete lanes, THE Flow_Engine SHALL record the wait duration (time from first lane arrival to last lane arrival) in milliseconds

26.3. WHEN a Gather_Node applies fallback behavior (timeout, partial merge), THE Flow_Engine SHALL write a telemetry event containing the fallback reason, completed lane count, and incomplete lane tether IDs

26.4. WHEN a nested scatter executes, THE Flow_Engine SHALL write a telemetry event containing the nesting depth and total concurrent lane count

26.5. FOR ALL multi-lane telemetry events, the schema SHALL include a `lane_topology` JSON field containing a snapshot of the flow line hierarchy at time of execution

### Requirement 27: CTRL_SCATTER Agent Slot Reordering

**User Story:** As a flow author, I want to reorder scatter agent slots via drag-and-drop in NodeConfigModal, so that I can control which agent receives which tether ID without deleting and re-adding slots.

#### Acceptance Criteria

27.1. WHEN the user clicks and holds on a scatter agent slot row in NodeConfigModal, THE NodeConfigModal SHALL allow the row to be dragged vertically

27.2. WHILE dragging a slot row, THE NodeConfigModal SHALL display a visual insertion indicator (horizontal line) showing where the row will be inserted

27.3. WHEN the user releases the mouse button, THE NodeConfigModal SHALL reorder the `scatter_agents` list to match the new visual order

27.4. WHEN slot reordering completes, THE NodeConfigModal SHALL update all tether ID references in the slot labels (e.g., slot 1 becomes `X.1`, slot 2 becomes `X.2`)

27.5. WHEN the user saves the modal after reordering, THE Flow_Engine SHALL persist the new agent order and update all downstream tether ID assignments

### Requirement 28: Heterogeneous Lane Length Dashed Filler

**User Story:** As a flow author viewing expanded multi-lane mode, I want shorter lanes to display dashed filler boxes that align them temporally with longer lanes, so that I can visually understand when lanes reach the merge boundary at different times.

#### Acceptance Criteria

28.1. WHEN the Active_Flow_Sequence renders lanes in expanded mode, THE Active_Flow_Sequence SHALL calculate the maximum lane length (node count from scatter to merge)

28.2. FOR ALL lanes with node count less than the maximum, THE Active_Flow_Sequence SHALL append dashed boxes to the right side of the lane until it matches the maximum length

28.3. THE dashed filler boxes SHALL use a distinct visual style (dashed border, no background fill, dimmed color) to differentiate them from real nodes

28.4. WHEN the user hovers over a dashed filler box, THE Active_Flow_Sequence SHALL display a tooltip "Temporal alignment filler (no node)"

28.5. WHEN the user clicks a dashed filler box, THE Active_Flow_Sequence SHALL take no action (non-interactive)

---

## Document Metadata

**Feature Name:** phase-6-13-multi-flow-lane  
**Workflow Type:** requirements-first  
**Spec Type:** feature  
**Author:** Kiro AI Agent  
**Created:** 2025-01-24  
**Status:** Initial Draft — Awaiting User Review
