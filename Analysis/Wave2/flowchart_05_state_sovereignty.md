# Comprehensive Architecture Report: MACCREv2 State Sovereignty, Security & Storage Topology

**Engineering Standard**: MACCREv2 Doctrine (Law Rev 19.0)  
**Scope**: 3-Tier Access Control, Federated Vault, 4-Silo SQLite WAL Telemetry Matrix, SovereignPinStore FTS5 Memory, Root Path Resolution, and CLI/MCP Entrypoint Orchestration.

---

## 1. Master System Control Plane Architecture

```mermaid
graph TD
    subgraph Entrypoints ["1. Entrypoint Layer"]
        RUN["run.py (TUI Launcher)"]
        SETUP["setup_mcp.py (Configurator)"]
        MCP["maccre_mcp.py (FastMCP Server)"]
        CLI["maccre.py (Master CLI Engine)"]
    end

    subgraph Security ["2. Access Control & Security Layer"]
        AC["access_control.py"]
        T1["Tier 1: Read-Only Baseline"]
        T2["Tier 2: Conditional Release (PIN Required)"]
        T3["Tier 3: MCP Token Bypass"]
        TRASH["trash_file() -> _archive/trash/"]
    end

    subgraph Vault ["3. Federated Vault Layer"]
        UV["universal_vault.py"]
        WV["windows_vault.py (DPAPI / CredReadW)"]
        FV["Fernet AES-128 (auth_vault.bin)"]
        KI["key_ingestor.py (Regex Fingerprinting)"]
        RAM["RAM Wiping (ctypes.memset)"]
    end

    subgraph MemoryPath ["4. Path & Data Sovereignty"]
        PR["path_resolver.py (get_maccre_root)"]
        DC["5-Tier Datacenter Tree (__DATACENTER/$projectName)"]
    end

    subgraph Persistence ["5. Memory & Telemetry Engine"]
        SPS["sovereign_store.py (SovereignPinStore FTS5)"]
        TDB["telemetry_db.py (4-Silo SQLite WAL Matrix)"]
        LOG["logger.py (Dual-Channel JSON Exhaust)"]
    end

    RUN --> CLI
    SETUP --> MCP
    CLI --> AC
    MCP --> AC
    AC --> T1
    AC --> T2
    AC --> T3
    AC --> TRASH

    CLI --> UV
    MCP --> UV
    UV --> WV
    UV --> FV
    KI --> UV
    UV --> RAM

    CLI --> PR
    MCP --> PR
    PR --> DC

    CLI --> SPS
    MCP --> SPS
    CLI --> TDB
    MCP --> TDB
    TDB --> LOG
```

---

## 2. Subsystem 1: 3-Tier Access Control & Deletion Safety Protocol

```mermaid
flowchart TD
    Start["File Operation Request"] --> CheckOp{"Is Read Operation?"}
    CheckOp -- Yes --> Tier1["Tier 1: Read-Only Access Granted"]
    CheckOp -- No --> CheckDel{"Is Deletion Operation?"}

    CheckDel -- Yes --> TrashProto["trash_file() Executed"]
    TrashProto --> GenTS["Generate UTC Timestamp Prefix"]
    GenTS --> MoveTrash["Move File to _archive/trash/"]
    MoveTrash --> LogTrash["Log FILE_TRASHED to telemetry_db"]
    LogTrash --> FinishTrash["Return [TRASH_SUCCESS]"]

    CheckDel -- No --> CheckPath{"Target Inside __DATACENTER?"}
    CheckPath -- Yes --> DatacenterWrite["Write Approved (Sandbox Zone)"]

    CheckPath -- No --> CheckMCP{"MCP Bypass Active?"}
    CheckMCP -- Yes --> Tier3["Tier 3: Write Approved under MCP Bypass"]
    CheckMCP -- No --> ElevReq["request_elevation(justification)"]

    ElevReq --> ReturnToken["Return [ELEVATION_PIN_REQUIRED]"]
    ReturnToken --> PromptUser["TUI Prompts User for PIN"]
    PromptUser --> SHA256["Salted SHA-256 Hashing"]
    SHA256 --> CheckPIN{"Hash Matches Vault PIN?"}

    CheckPIN -- Yes --> Tier2["Tier 2: Elevation Granted (Session Scoped)"]
    CheckPIN -- No --> Deny["Elevation Denied & Logged to Telemetry"]
```

---

## 3. Subsystem 2: Federated OS / Fernet Vault & Key Ingestion

```mermaid
flowchart TD
    subgraph KeyIngestion ["Key Ingestion Pipeline (key_ingestor.py)"]
        RawInput["Raw Input / Clipboard Monitor"] --> RegexEngine{"Regex Vendor Pattern Match"}
        RegexEngine -- "Matched (Gemini/Claude/OpenAI/etc)" --> StoreVault["Store API Key in Vault"]
        StoreVault --> WipeClip["Sanitize Clipboard / Input Buffer"]
    end

    subgraph Retrieval ["Credential Retrieval Flow (universal_vault.py)"]
        ReqKey["Request Key: get_provider_credential(service)"] --> CheckKeyring{"Keyring / Windows DPAPI Available?"}
        
        CheckKeyring -- Yes --> CallDPAPI["CredReadW / CryptUnprotectData"]
        CheckKeyring -- No --> LoadFernet["Load auth_vault.bin"]
        LoadFernet --> DecryptFernet["Decrypt via AES-128 Fernet Key"]
        
        CallDPAPI --> ReturnBuffer["Return Plaintext Key Buffer"]
        DecryptFernet --> ReturnBuffer

        ReturnBuffer --> UseKey["Execute Provider API Call"]
        UseKey --> PurgeRAM["ctypes.memset(buffer, 0, len)"]
        PurgeRAM --> EndKey["Zero-Leak Memory State Restored"]
    end
```

---

## 4. Subsystem 3: 4-Silo SQLite WAL Telemetry & Operations Logging Matrix

```mermaid
flowchart TD
    subgraph LogSources ["Log Sources & Events"]
        SysEvents["System Lifecycle & Operations"]
        UserPrompts["User Prompts & PIN Approvals"]
        TermOutputs["TUI Stdio & Render Engine"]
        Defs["Configuration & Schema Metadata"]
    end

    subgraph TelemetryMatrix ["4-Silo SQLite WAL Matrix (telemetry_db.py)"]
        DB1[("system_logs.db\n[WAL Mode]")]
        DB2[("user_interactions.db\n[WAL Mode]")]
        DB3[("terminal_logs.db\n[WAL Mode]")]
        DB4[("definitions.db\n[WAL Mode]")]
    end

    subgraph ExhaustLedgers ["Dual-Channel Operations Logger (logger.py)"]
        FlowChat["FlowChat JSONL Stream"]
        FlowSystem["FlowSystem JSONL Stream"]
        LedgerDir["03_Agent_Ledgers/*.json"]
        BuildLog["build_pipeline.log"]
    end

    SysEvents --> DB1
    UserPrompts --> DB2
    TermOutputs --> DB3
    Defs --> DB4

    DB1 & DB2 & DB3 & DB4 --> LoggerDispatcher["Dual-Channel Dispatcher"]
    LoggerDispatcher --> FlowChat & FlowSystem
    FlowChat --> LedgerDir
    FlowSystem --> BuildLog
```

---

## 5. Subsystem 4: Zero-Dependency Vector Memory & FTS5 Store (`SovereignPinStore`)

```mermaid
flowchart TD
    subgraph Ingestion ["Ingestion & Indexing"]
        Document["Document / Memory Triplet"] --> Vectorize["Generate Embedding Vector"]
        Vectorize --> SlotStruct["Instantiate PinRecord Dataclass"]
        SlotStruct --> VecBlob["_vec_to_blob(vector) -> BLOB"]
        VecBlob --> SQLiteStore[("SQLite SQLite WAL\nFTS5 Table (memory_pins.db)")]
    end

    subgraph Query ["Query Execution Pipeline"]
        SearchQuery["Search Query (Text + Query Vector)"] --> DirectFTS{"Query Type"}
        
        DirectFTS -- FTS Keyword Search --> FTSMatch["SQLite FTS5 MATCH Query"]
        DirectFTS -- Vector Hybrid Search --> FetchBlobs["Fetch Stored Vector BLOBs"]
        
        FetchBlobs --> BlobVec["_blob_to_vec(blob) -> float list"]
        BlobVec --> CosineCalc["_cosine_distance(q_vec, d_vec)"]
        
        FTSMatch --> Combine["Combine & Rank Results"]
        CosineCalc --> Combine
        Combine --> TopK["Return Top-K PinRecords"]
    end
```

---

## 6. Subsystem 5: Datacenter Root Anchoring & 5-Tier Path Resolution

```mermaid
flowchart TD
    subgraph Anchor ["Root Anchor Resolution (get_maccre_root)"]
        EnvCheck{"Is MACCRE_ROOT set in OS Env?"}
        EnvCheck -- Yes --> UseEnv["Return Path(env['MACCRE_ROOT'])"]
        EnvCheck -- No --> Fallback["__file__.resolve().parent.parent.parent"]
        UseEnv --> RootPath["Canonical MACCRE_ROOT Path"]
        Fallback --> RootPath
    end

    subgraph TieredDC ["5-Tier Data Sovereignty Resolution (get_datacenter_path)"]
        RootPath --> CheckProj{"Read MACCRE_ACTIVE_PROJECT"}
        CheckProj --> ProjName["__DATACENTER/$projectName/"]
        
        ProjName --> T1["01_Raw_Source (Immutable Ingestion)"]
        ProjName --> T2["02_Dynamic_Context (RAG & Active Context)"]
        ProjName --> T3["03_Agent_Ledgers (Telemetry & Audit Logs)"]
        ProjName --> T4["04_Code_Artifacts (Sandbox Generation)"]
        ProjName --> T5["05_Rendered_Media (Diagrams & Audio Exhaust)"]
    end
```

---

## 7. Subsystem 6: CLI, MCP Server & Entrypoint Execution Flows

```mermaid
flowchart TD
    subgraph ControlPlane ["Multi-Modal Control Plane Entrypoints"]
        E1["run.py"] --> Launcher["NexusPlex TUI Bootstrap"]
        E2["setup_mcp.py"] --> ConfigGen["Machine Probe & mcp_config.json Writer"]
        E3["maccre_mcp.py"] --> FastMCPServer["FastMCP stdio Server (27 Tools / 8 Groups)"]
        E4["maccre.py"] --> MasterCLI["Master CLI Engine & Headless Orchestrator"]
    end

    subgraph MCPFlow ["FastMCP Server Execution Flow (maccre_mcp.py)"]
        FastMCPServer --> StdioPipe["stdio JSON-RPC Pipe Protocol"]
        StdioPipe --> CheckToken{"Check MACCRE_ELEVATION_TOKEN"}
        CheckToken -- Valid --> ActivateBypass["activate_mcp_bypass(token)"]
        CheckToken -- Absent/Invalid --> StdSandbox["Enforce Standard Access Control"]
        ActivateBypass & StdSandbox --> ExecTool["Execute MCP Tool (System/Swarm/Storage/etc)"]
    end

    subgraph CLIFlow ["Master CLI Execution Flow (maccre.py)"]
        MasterCLI --> ArgParse["Parse Arguments / Swarm Commands"]
        ArgParse --> CheckPID["PID Registry Hygiene & Stale Lock Purge"]
        CheckPID --> PathResolve["Anchor Paths via get_maccre_root()"]
        PathResolve --> SwarmLaunch["Ignite Swarm / Materialize Workbook"]
    end
```
