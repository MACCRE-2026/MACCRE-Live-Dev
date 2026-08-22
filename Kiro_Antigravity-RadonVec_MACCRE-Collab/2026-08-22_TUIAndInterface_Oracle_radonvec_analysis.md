# SUBSYSTEM ARCHITECTURAL SPECIFICATION & RFC: RADONVEC INTEGRATION INTO TUI LAYER

**Specialist Oracle:** `TUIAndInterface_Oracle`  
**Target Domain:** `maccre_tui/` (`nexus_plex.py`, `nexus_plex.css`, `widgets/*`, `modals/*`)  
**Specification Timestamp:** 2026-08-22T16:05:00-04:00  
**Document ID:** `2026-08-22_TUIAndInterface_Oracle_radonvec_analysis.md`  
**Handover Reference:** `B:\EXO_GANS\RADONVEC_HANDOVER.md` (`2026-08-22_RadonVec_Handover_and_Oracle_Directives.md`)  
**Compliance Standard:** Sovereign Edge Omni-Builder Doctrine (Rev 19.0)  

---

## 1. EXECUTIVE SUMMARY & SUBSYSTEM REFRESHER

Pursuant to the **RadonVec Technology Handover Directive** (`B:\EXO_GANS\RADONVEC_HANDOVER.md`), the **TUI & Interface Oracle** has executed a comprehensive domain analysis and drafted this architectural Request for Comments (RFC) for integrating continuous tomographic visualization, time-travel history scrubbing, and angular telemetry into the NexusPlex TUI command center (`maccre_tui/`).

### 1.1 The RadonVec Paradigm in Terminal & Edge UI
Traditional observability platforms render high-dimensional cognitive states as flat, static text tables or rigid 2D node graphs. RadonVec reconceptualizes state churn across multi-agent swarms as a **sparse 3D/4D topological volume** ($V \in \mathbb{R}^{S \times S \times S}$), slicing it along rotating angular fan planes ($\theta \in [0, \pi)$) into lightweight, RLE-quantized 2D sinogram frames ($P \in \mathbb{R}^{M \times S \times S}$).

For the TUI layer (`maccre_tui/`), this unlocks three transformative UI/UX capabilities:
1. **Native ANSI/Braille 3D/4D Vector Space Projection (`RadonCortexVisualizer`)**: Real-time rendering of rotating sinogram projections and isometric 3D point-cloud centroids directly inside the Textual split-pane terminal.
2. **True Continuous VCR Time-Travel Scrubbing (`RadonTimelineScrubber`)**: Replacing discrete step jumps with a continuous microsecond timeline slider. Dropping the "FBP needle" onto timestamp $t$ reinflates the 3D cognitive state twin on the fly via Filtered Backprojection (FBP).
3. **Real-Time $O(1)$ Telemetry Matrix**: Live header gauges displaying **Angular Anisotropy ($\Delta \theta_{\text{var}}$)**, **Index Drift ($\delta_{\text{drift}}$)**, and **Sinogram Compression Ratio ($C_R$)** without traversing heavy database logs.

---

## 2. SUBSYSTEM ARCHITECTURAL SPECIFICATION

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 NEXUS_PLEX TUI COMMAND CENTER                                    │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ [CustomHeader]                                                                                   │
│ Project: [ UAP_Research ▾]  │ Anisotropy: 0.14 [||....] BALANCED │ Drift: 0.02 │ CR: 94.8% (RLE) │
├───────────────────────────────────────┬──────────────────────────────────────────────────────────┤
│ LEFT PANE (35%)                       │ RIGHT PANE (65%)                                         │
│ ┌───────────────────────────────────┐ │ ┌──────────────────────────────────────────────────────┐ │
│ │ [Tab 1: DAG] [Tab 2: 3D Cortex]   │ │ │ MacroNode Workshop / Agent Studio Arena              │ │
│ │                                   │ │ │                                                      │ │
│ │   RadonCortexVisualizer           │ │ │   Active Flow Line / Chat Arena                      │ │
│ │   ┌─────────────────────────────┐ │ │   [Node_01] ──▶ [Node_02] ──▶ [Node_03] (Active)       │ │
│ │   │ Braille Fan-Plane Canvas    │ │ │                                                      │ │
│ │   │ θ = 67.5° [Frame #42]       │ │ │ ┌──────────────────────────────────────────────────┐ │ │
│ │   │  ⠁⠂⠆⠖⠶⠲⠘⠰⠤⠄           │ │ │ │ VCR Time-Travel Scrubber                         │ │ │
│ │   │  ⢀⣀⣠⣤⣴⣶⣾⣿⣷⣶⣤⣄⣀   │ │ │ │ [⏮] [◀] [⏸] [▶] [⏭] [Live ◉]                    │ │ │
│ │   │  ⠘⠛⠿⠿⠿⠿⠿⠿⠿⠿⠛⠁   │ │ │ │ ────●────────────────────────────── [00:04.120]  │ │ │
│ │   │ Centroid: (0.12, -0.45, 0.81)│ │ │ └──────────────────────────────────────────────────┘ │ │
│ │   └─────────────────────────────┘ │ │                                                      │ │
│ ├───────────────────────────────────┤ │                                                      │ │
│ │ Nexus Copilot Chat                │ │                                                      │ │
│ └───────────────────────────────────┘ │ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 2.1 Native Textual TUI Split-Pane Widget (`RadonCortexVisualizer`)

The TUI layer must provide zero-dependency, native terminal rendering of 3D cognitive state volumes without requiring external graphical windows.

#### Component Architecture:
* **Widget Class**: `RadonCortexVisualizer(Vertical)` located in `maccre_tui/widgets/radon_cortex_visualizer.py`.
* **Rendering Sub-Engines**:
  1. **Braille Fan-Plane Canvas (`BrailleSinogramCanvas`)**:
     - Maps normalized sinogram slice matrices $P_\theta(s, z) \in [0, 1]$ to Unicode Braille characters ($2 \times 4$ dot matrix, `U+2800` to `U+28FF`).
     - Each terminal character cell represents a $2 \times 4$ sub-pixel grid, allowing a $64 \times 64$ slice to be rendered crisply in a $32 \times 16$ character cell viewport.
     - Colorized using Rich style gradients (`#161b22` $\to$ `#1f6feb` $\to$ `#58a6ff` $\to$ `#f0883e` $\to$ `#ffffff`).
  2. **Isometric 3D Vector Point-Cloud Canvas (`IsometricCortexCanvas`)**:
     - Computes real-time orthographic / isometric projections of active cluster centroids from `thought_pins.db` and `memory_pins.db`:
       $$\begin{bmatrix} x' \\ y' \end{bmatrix} = \begin{bmatrix} \cos\alpha & -\sin\alpha & 0 \\ \sin\alpha\cos\beta & \cos\alpha\cos\beta & -\sin\beta \end{bmatrix} \begin{bmatrix} x \\ y \\ z \end{bmatrix}$$
     - Renders node filaments and cluster gravity wells with directional depth cues (dim foreground/bright active nodes).
* **View Modes**:
  - `MODE_FAN_ROTATING`: Cycles through angular slices $\theta_0 \dots \theta_{M-1}$ at 10 Hz to visually inspect directional slice coverage.
  - `MODE_FBP_VOLUME`: Renders orthographic projection of the reinflated 3D voxel density twin $V_{\text{reconstructed}}$.
  - `MODE_ANISOTROPY_RADAR`: Polar radar plot showing angular density distribution across projection angles.

---

### 2.2 Local WebGL/Three.js Browser Sidecar Bridge (`RadonBridgeServer`)

For full 60 FPS hardware-accelerated 4D navigation, `maccre_tui/` provides a seamless bridge to the interactive Three.js visualizer built during the hackathon.

#### Bridge Architecture:
* **Micro-Daemon**: Zero-dependency Python standard library `http.server` running in a daemon thread managed by `maccre_core._net.omnidaemon`.
* **Port Binding**: Bound locally to `http://127.0.0.1:8765/radon_live`.
* **Protocol & Payload**:
  - Serves static WebGL client assets (`index.html`, `three.min.js`, `OrbitControls.js`).
  - Implements lightweight SSE (`Server-Sent Events`) or WebSocket channel pushing `.rvf` (RadonVec Frame) byte arrays or JSON coordinate twins.
* **TUI Integration**:
  - Hotkey `Ctrl+V` or Header Button `[🌐 4D Visualizer]` triggers `NexusPlex.action_launch_radon_webgl()`.
  - Automatically spawns default browser or renders WebGL URL link in Nexus Chat log.
  - Modal Screen `RadonBridgeModal(ModalScreen)` displays live server telemetry, connected client count, and frame broadcast rate.

---

### 2.3 Interactive VCR Transport Time-Travel Scrubber UI

The existing VCR transport control in `nexus_plex.py` (which supports `idle`, `running`, `paused` states) is upgraded into a continuous **Time-Travel Navigation System**.

#### Component Architecture:
* **Widget Class**: `RadonTimelineScrubber(Horizontal)` in `maccre_tui/widgets/radon_timeline_scrubber.py`.
* **Controls**:
  - **Transport Buttons**: `[⏮ First]` `[◀ Step Prev]` `[⏸ Pause / FlowStasis]` `[▶ Play / Resume]` `[Step Next ▶]` `[⏭ Latest]` `[◉ Live Follow]`.
  - **Interactive Time Slider**: Textual `Slider` or custom timeline tick bar with sub-millisecond precision scrubbing across historical timestamps $t_0 \dots t_{\text{current}}$.
  - **Timestamp / Frame Badge**: `Static` displaying `00:04.120 [Frame #42 / 128] [Δt = -01:12.4]`.
* **Scrubbing Mechanics & Needle Drop**:
  1. When operator scrubs the slider (or uses `[` / `]` hotkeys), `RadonTimelineScrubber` emits `TimelineScrubbed(timestamp_ms, frame_idx)`.
  2. Main app captures event and executes non-blocking worker `@work(thread=True)`.
  3. Worker pulls matching sinogram delta frame from SQLite WAL (`swarm_queue.db` or `thought_pins.db`), executes Inverse Filtered Backprojection (FBP), and reinflates the 3D state twin at that exact microsecond.
  4. App dispatches `app.call_from_thread(visualizer.update_state, state_twin)` and updates the `TopologyVisualizer` tree state:
     - Nodes completed *after* timestamp $t$ revert to `QUEUED` / `IDLE` (dim).
     - Node executing *at* timestamp $t$ highlights in `ACTIVE` pulsing amber.
     - Nodes completed *before* timestamp $t$ remain `COMPLETED` (green).
  5. Operator can inspect exact historical payload, inject context, or branch into an alternate execution timeline ("Time-Travel Branching").

#### Multi-Agent Chat Arena Integration (`AgentStudioChatScreen`):
* In `AgentStudioChatScreen`, the timeline scrubber allows operators to scrub through multi-turn agent dialogues.
* As the slider moves, agent semantic embedding coordinates mutate in the `RadonCortexVisualizer`, visually demonstrating how agent reasoning vectors converge or diverge during complex problem solving.

---

### 2.4 Real-Time Header & Status Matrix Telemetry Readouts

To provide instantaneous $O(1)$ health visibility without polling heavy databases, `CustomHeader` in `nexus_plex.py` is augmented with dedicated RadonVec telemetry metrics.

#### Telemetry Readouts:
1. **Angular Anisotropy Gauge ($\Delta \theta_{\text{var}}$)**:
   - Evaluates variance in projected energy across rotating fan slices:
     $$\Delta \theta_{\text{var}} = \frac{1}{M} \sum_{m=0}^{M-1} \left( \|P_{\theta_m}\|_F - \bar{P} \right)^2$$
   - Visual readout: `Anisotropy: 0.12 [||....] BALANCED` (Green) $\to$ `0.85 [||||||||] COLLAPSE WARNING` (Red).
   - High anisotropy indicates vector cluster collapse, dead-space concentration, or severe embedding fragmentation.
2. **Index Drift Metric ($\delta_{\text{drift}}$)**:
   - Evaluates rate of centroid shift between consecutive sinogram frames:
     $$\delta_{\text{drift}} = \|\mathbf{c}_t - \mathbf{c}_{t-1}\|_2$$
   - Visual readout: `Drift: 0.03 Δ/s` (Green) $\to$ `Drift: 0.94 Δ/s HIGH CHURN` (Amber).
3. **Sinogram Compression Ratio ($C_R$)**:
   - Live telemetry on spatial data reduction:
     $$C_R = \left( 1 - \frac{\text{bytes}(\text{RLE}(\text{Quantize}(P)))}{\text{bytes}(V)} \right) \times 100\%$$
   - Visual readout: `CR: 94.8% (RLE-8)`.

---

### 2.5 Textual Event Loop Safety & Concurrency Architecture

Under **Sovereign Physical Law III (Omni CI/CD & Textual Concurrency)**, mathematical transforms (Forward Radon Projection and Inverse Filtered Backprojection) MUST NOT execute on Textual's main asyncio event loop.

#### Threading & Concurrency Contract:
* **Background Worker Execution**:
  All FBP reconstructions and disk reads are wrapped in Textual `@work(thread=True, exclusive=True)` workers or executed via a dedicated `concurrent.futures.ThreadPoolExecutor(max_workers=2)`.
* **Thread-Safe UI Mutations**:
  All widget updates, canvas repaints, and tree node state mutations are dispatched exclusively through `self.call_from_thread(...)`.
* **Debounced Scrubbing**:
  The timeline slider implements a 50ms trailing-edge debounce timer (`_scrub_debounce_timer`). Rapid mouse drags update the slider label instantly at 60 FPS, while suppressing intermediate heavy FBP inversion passes until the operator settles on a target timestamp.
* **Zero-Allocation Palette Caching**:
  Pre-allocates Braille glyph mappings and ANSI true-color lookup tables at module import time, eliminating per-frame string allocations and garbage collection pauses.

---

## 3. HIGH-CONTRAST CSS STYLING SPECIFICATION

The following CSS rules will be appended to `maccre_tui/nexus_plex.css` to govern all new RadonVec UI components:

```css
/* ── RadonVec Cortex & Visualizer ────────────────────────────────────────── */
RadonCortexVisualizer {
    width: 100%;
    height: 1fr;
    border: solid #58a6ff;
    background: #0d1117;
    padding: 0 1;
}

#radon-canvas-container {
    width: 100%;
    height: 1fr;
    background: #090d13;
    border: round #30363d;
    content-align: center middle;
}

.radon-fan-active {
    color: #58a6ff;
    text-style: bold;
}

.radon-centroid-peak {
    color: #f0883e;
    text-style: bold;
}

/* ── Radon Timeline Scrubber ─────────────────────────────────────────────── */
RadonTimelineScrubber {
    height: 3;
    width: 100%;
    layout: horizontal;
    background: #161b22;
    border-top: solid #30363d;
    padding: 0 1;
}

#btn-timeline-play, #btn-timeline-pause {
    width: 6;
    height: 3;
    min-width: 6;
}

#timeline-slider {
    width: 1fr;
    height: 3;
    color: #58a6ff;
}

#timeline-badge {
    width: 28;
    height: 3;
    color: #79c0ff;
    text-style: bold;
    content-align: right middle;
}

/* ── Radon Header Telemetry Matrix ───────────────────────────────────────── */
#radon-header-telemetry {
    layout: horizontal;
    height: 100%;
    width: auto;
    padding: 0 1;
}

.telemetry-badge-good {
    color: #3fb950;
    text-style: bold;
}

.telemetry-badge-warn {
    color: #d29922;
    text-style: bold;
}

.telemetry-badge-crit {
    color: #f85149;
    text-style: bold;
}
```

---

## 4. DETAILED IMPLEMENTATION & FILE MUTATION ROADMAP

| Phase / File | Target Component | Modification Details |
| :--- | :--- | :--- |
| **`maccre_tui/widgets/radon_cortex_visualizer.py`** | `RadonCortexVisualizer`, `BrailleSinogramCanvas`, `IsometricCortexCanvas` | **[NEW]** Complete Textual widget rendering ANSI/Braille sinogram fan slices and isometric 3D state twin projections. |
| **`maccre_tui/widgets/radon_timeline_scrubber.py`** | `RadonTimelineScrubber`, `TimelineScrubbed` message | **[NEW]** Continuous microsecond timeline scrubber with play/pause transport, debounced needle dropping, and live badge. |
| **`maccre_tui/widgets/radon_bridge_modal.py`** | `RadonBridgeModal` | **[NEW]** Modal dialogue for managing local Three.js WebGL micro-daemon, client connections, and frame streaming. |
| **`maccre_tui/nexus_plex.py`** | `NexusPlex`, `CustomHeader`, `AgentStudioChatScreen` | **[MODIFY]** Integrate `RadonCortexVisualizer` into left pane tab stack; wire `RadonTimelineScrubber` into VCR transport; add real-time telemetry matrix to `CustomHeader`; add `Ctrl+V` hotkey. |
| **`maccre_tui/nexus_plex.css`** | Global Stylesheet | **[MODIFY]** Append styles for `RadonCortexVisualizer`, `RadonTimelineScrubber`, and telemetry header badges. |
| **`maccre_core/_net/omnidaemon.py`** | `RadonBridgeServer` | **[MODIFY]** Zero-dependency `http.server` micro-daemon serving WebGL 4D visualizer. |

---

## 5. STRICT PHYSICAL LAWS & OMNI QA VERIFICATION PLAN

1. **Omni QA Compliance**:
   - Strict adherence to Python 3.11+ type annotations across all new widget methods and message signatures.
   - Zero unused imports and maximum 120-character line limits.
   - Verified globally via `omni qa .`.
2. **Resource Teardown**:
   - Timer handles (`set_interval`), worker tasks, and WebGL HTTP daemons wrapped in strict `try/finally` blocks and teardown hooks (`on_unmount`).
3. **Portability Mandate (Law VIII)**:
   - All filesystem references anchored dynamically via `get_maccre_root()`.

---

## 6. CONCLUSION & RECOMMENDED IMMEDIATE ACTIONS

The integration of RadonVec into `maccre_tui/` transforms the NexusPlex TUI from a standard task orchestration console into an advanced **Continuous Tomographic C2 Matrix**. 

**Immediate Oracle Recommendations**:
1. Proceed with implementing `radon_cortex_visualizer.py` and `radon_timeline_scrubber.py` following Phase 4.99 stabilization.
2. Coordinate with `NetAndClient_Oracle` on zero-dependency WebSocket streaming standards for the WebGL sidecar bridge.
3. Coordinate with `OrchestrationAndEngine_Oracle` on binding `TimelineScrubbed` events to `FlowEngine` SQLite WAL state snapshots.
