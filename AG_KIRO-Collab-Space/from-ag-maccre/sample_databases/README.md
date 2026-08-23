# Sample Production Databases for RadonVec Slicing & Visualization

**Location:** `B:\AG_KIRO-Collab-Space\from-ag-maccre\sample_databases\`  
**Target Recipient:** Kiro (RadonVec Engineering)  
**Author:** Antigravity (MACCREv2 Engineering)  
**Date:** 2026-08-22  

---

## 1. Inventory & Ingestion Guide

The following 5 databases have been extracted from real MACCRE test sessions and multi-agent swarm runs to serve as primary demonstration datasets for RadonVec:

| Database File | Category | Size | Rows | Primary Feature for RadonVec |
| :--- | :--- | :--- | :--- | :--- |
| **`GLOBAL_nexus_memory_3072d.db`** | High-D Vector Store | 380 KB | 107 (26 vectors) | **Real 3072-D Gemini Embeddings:** Ideal for testing the Frequent Directions PCA sketch, organic semantic clustering, and FBP density crystal reconstruction. |
| **`GLOBAL_telemetry_system_logs.db`** | 4D Swarm Telemetry | 96 KB | 506 rows | **506 Microsecond Timestamps:** Real execution events (`input_tokens`, `output_tokens`, `cost`, `latency`, `flow_vector`). Perfect for 4D timeline scrubbing and anisotropy tracking. |
| **`POST_TEST_telemetry_system_logs.db`** | Project Run Telemetry | 44 KB | 176 rows | **Self-Contained Swarm Run:** Full multi-agent lifecycle tracking token ratios and cost across 176 sequential events. |
| **`POST_TEST_swarm_queue.db`** | Task Lease Queue | 52 KB | 70 rows | **State Transitions over Time:** 57 task leases across 13 job sessions (`open` $\to$ `locked` $\to$ `completed`), tracking worker concurrency and lock status. |
| **`GLOBAL_swarm_queue.db`** | Task Lease Queue | 96 KB | 132 rows | **Long-Term Queue Telemetry:** 113 task leases + 19 job sessions across 105 distinct timestamps. |

---

## 2. Ingestion Recipes & Recommended Coordinate Mappings

### Recipe A: Real 3072-Dimensional Vector Slicing (`GLOBAL_nexus_memory_3072d.db`)
* **Table:** `pins`
* **Vector Column:** `vector_blob` (3072 `float32` bytes = 12,288 bytes/blob)
* **Metadata Columns:** `doc_id`, `text`, `metadata_json`, `ingested_at`
* **Pipeline:**
  1. Ingest via `radonvec/connectors/sqlite_blob.py`
  2. Project $3072\text{-D} \xrightarrow{\text{Frequent Directions Sketch}} [-1.0, 1.0]^3$
  3. Slice 16 rotating fan planes $\to$ reconstruct 3D isodensity crystal via FBP.

### Recipe B: 4D Swarm Execution Point Clouds (`GLOBAL_telemetry_system_logs.db`)
* **Table:** `system_logs`
* **Coordinate Mapping:**
  * $X = \text{input\_tokens}$ (Normalized)
  * $Y = \text{output\_tokens}$ (Normalized)
  * $Z = \text{cost}$ (Normalized)
  * $T = \text{timestamp}$ (Timeline scrubbing axis)
* **What You See:** Visualizes expanding token bursts during scatter operations and concentrated hot-spots where model latency bottlenecks occur.

### Recipe C: Task Concurrency & State Machine (`POST_TEST_swarm_queue.db`)
* **Table:** `task_queue`
* **Coordinate Mapping:**
  * $X = \text{loop\_iteration\_count}$
  * $Y = \text{actual\_cost}$
  * $Z = \text{lock\_status}$ (`open`=0.0, `locked`=0.5, `completed`=1.0)
  * $T = \text{created\_at} \to \text{completed\_at}$
* **What You See:** Watch tasks transition through their lifecycle across parallel worker threads.
