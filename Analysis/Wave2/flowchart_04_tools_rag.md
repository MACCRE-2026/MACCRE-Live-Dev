# GRANULAR ARCHITECTURAL FLOWCHARTS: TOOL EXECUTION SUITE, SOVEREIGN RAG & MEDIA ENGINE

**Target Document:** `B:\EXO_GANS\Analysis\Wave2\flowchart_04_tools_rag.md`  
**System Architecture:** MACCREv2 / EXO_GANS Sovereign Edge Framework  
**Law Revision:** 19.0 Compliance  

---

## SECTION 1: TOOL MANIFEST REGISTRATION & DISPATCH PIPELINE (`tool_registry.py`)

```mermaid
flowchart TD
    subgraph Tool_Modules["Atomic Tool Modules (maccre_core/tools/*)"]
        TM1["text_tools.py<br/>(parse_json, truncate_history)"]
        TM2["finops_tools.py<br/>(estimate_cost, reconcile_finops)"]
        TM3["audio_tools.py<br/>(pack_wav, build_tts_config)"]
        TM4["media_tools.py<br/>(build_ffmpeg_cmd, save_manifest)"]
        TM5["storage_tools.py<br/>(read_file, write_dynamic_context)"]
        TM6["rag_tools.py<br/>(query_local_memory, ingest_doc)"]
        TM7["admin_tools.py<br/>(mint_agent, build_topology)"]
        TM8["design_tools.py<br/>(design_swarm, fill_swarm_sheet)"]
        TM9["render_executor.py<br/>(execute_render_pipeline)"]
        TM10["sync_tools.py<br/>(export_nugget, import_nugget)"]
        TM11["web_tools.py<br/>(search_web, cascade_search)"]
    end

    subgraph Registry_Engine["Tool Registry Engine (tool_registry.py)"]
        TR1["Master Dispatcher Map<br/>TOOL_DISPATCHER = Dict[str, Callable]"]
        TR2["Tier-Aware Tool Selector<br/>get_tools_for_tier(tier: str)"]
        TR3["Schema Generator<br/>generate_universal_json_schema()"]
        TR4["Docstring & Type Inspector<br/>(Enforces Google-style & Type Hints)"]
    end

    subgraph Router_Dispatch["Cognitive Router & Function Execution"]
        CR1["Cognitive Router<br/>(maccre_router.py)"]
        CR2["Tier Filter Switch<br/>['heavy' | 'fast' | 'all']"]
        CR3["Gemini Client API Call<br/>tools=[generated_schemas]"]
        CR4["Function Call Interceptor"]
        CR5["TOOL_DISPATCHER[func_name](**kwargs)"]
        CR6["Teardown & Error Handling<br/>(try / finally context management)"]
    end

    TM1 & TM2 & TM3 & TM4 & TM5 & TM6 & TM7 & TM8 & TM9 & TM10 & TM11 --> TR1
    TR1 --> TR2
    TR2 --> TR4
    TR4 --> TR3
    CR1 --> CR2
    CR2 -->|Query Available Tools| TR2
    TR3 -->|OpenAPI Tool Schemas| CR3
    CR3 -->|LLM Function Call Response| CR4
    CR4 -->|Dispatch Function Name & Args| CR5
    CR5 -->|Execute & Enforce Teardown| CR6
```

---

## SECTION 2: SOVEREIGN RAG VECTOR & FTS SEARCH PIPELINE (`rag_tools.py`, `hybrid_search.py`)

```mermaid
flowchart TD
    subgraph Intake["Document Ingestion & Indexing Pipeline"]
        IN1["Ingest Request<br/>ingest_document(path, project_id)"]
        IN2["Document Loader & Text Chunking"]
        IN3["OS Vault Auth Check<br/>get_provider_credential('MACCRE_Sovereign')"]
        IN4["Gemini Embedding Generator<br/>get_gemini_embedding(256-dim)"]
        IN5["SovereignPinStore / ChromaDB<br/>(PinRecord Insertion)"]
        IN6["SQLite FTS5 Indexer<br/>(BM25 Full-Text Table)"]
    end

    subgraph Query_Engine["Multi-Tiered Retrieval Pipeline"]
        QR1["Search Trigger<br/>(query_local_memory / fts_search_memory)"]
        QR2["Tier Target Selector<br/>[L1 Session | L2 Project | L3 Global]"]
        
        subgraph Vector_Branch["Semantic Vector Path"]
            VB1["Embed Query Text<br/>get_gemini_embedding(task='RETRIEVAL_QUERY')"]
            VB2["Vector Similarity Search<br/>SovereignPinStore.query(n_results)"]
        end

        subgraph FTS_Branch["Lexical FTS5 Path"]
            FB1["BM25 Keyword Match<br/>SQLite FTS5 MATCH Query"]
        end
    end

    subgraph Hybrid_Synthesis["Hybrid Search & Rank Fusion (hybrid_search.py)"]
        HS1["Hybrid Request<br/>execute_hybrid_synthesis(query)"]
        HS2["ThreadPoolExecutor Concurrent Dispatch"]
        HS3["Parallel Path A:<br/>_query_local_sovereign()"]
        HS4["Parallel Path B:<br/>Brave Live Web Search (urllib)"]
        HS5["Reciprocal Rank Fusion (RRF)<br/>Context Synthesis & Deduplication"]
        HS6["Unified Context Block"]
    end

    IN1 --> IN2 --> IN3 --> IN4
    IN4 --> IN5 & IN6

    QR1 --> QR2
    QR2 -->|Semantic Query| VB1 --> VB2
    QR2 -->|Lexical Query| FB1

    HS1 --> HS2
    HS2 --> HS3 & HS4
    VB2 --> HS3
    HS3 & HS4 --> HS5 --> HS6
```

---

## SECTION 3: DUAL-PIPELINE MEDIA RENDER EXECUTOR (`render_executor.py`)

```mermaid
flowchart TD
    subgraph Manifest_Intake["Director Manifest Intake & Parse"]
        MI1["Director JSON Manifest"]
        MI2["CloudMediaPipeline.execute_render_pipeline()"]
        MI3["Parse Script Scenes & Scene Asset Requirements"]
    end

    subgraph Parallel_Pipeline["Concurrent Generation Sub-Pipelines"]
        subgraph TTS_Branch["TTS Audio Generation Branch"]
            TTS1["load_voice_roster()<br/>Voice Profile Mapping"]
            TTS2["build_tts_config_from_profile()"]
            TTS3["Gemini REST API Call<br/>generateContent (audio/wav)"]
            TTS4["pack_wav_bytes()<br/>PCM Headers & Storage"]
            TTS5["Audio Files (.wav)<br/>05_Rendered_Media/audio/"]
        end

        subgraph Image_Branch["Imagen Image Generation Branch"]
            IMG1["render_image_batch()<br/>Concurrent Request Queue"]
            IMG2["Gemini Imagen REST Call<br/>generateImages"]
            IMG3{"Success or Error?"}
            IMG4["Fallback Model Switch<br/>(imagen-3.0-generate-002)"]
            IMG5["Base64 Payload Decode & Storage"]
            IMG6["Image Files (.png)<br/>05_Rendered_Media/images/"]
        end
    end

    subgraph FFmpeg_Stitcher["Edge FFmpeg Synthesis Engine"]
        FF1["Binary Resolution<br/>(WinGet Glob / System PATH ffmpeg.exe)"]
        FF2["build_concat_manifest()<br/>Generate Slide Timings & Audio Sync"]
        FF3["build_ffmpeg_cmd()<br/>Construct Complex Filter Graph"]
        FF4["Subprocess Execution<br/>ffmpeg -f concat -i manifest.txt -i audio.wav"]
        FF5["Rendered Video File (.mp4)<br/>05_Rendered_Media/video/"]
    end

    subgraph Post_Render["FinOps & Telemetry Audit"]
        FO1["render_cost_report()<br/>Calculate Token & Render Cost"]
        FO2["03_Agent_Ledgers Audit Log<br/>JSON Export & Telemetry Sync"]
    end

    MI1 --> MI2 --> MI3
    MI3 -->|Audio Script| TTS1
    MI3 -->|Visual Prompts| IMG1

    TTS1 --> TTS2 --> TTS3 --> TTS4 --> TTS5
    IMG1 --> IMG2 --> IMG3
    IMG3 -->|Error| IMG4 --> IMG2
    IMG3 -->|Success| IMG5 --> IMG6

    TTS5 & IMG6 --> FF1
    FF1 --> FF2 --> FF3 --> FF4 --> FF5
    FF5 --> FO1 --> FO2
```

---

## SECTION 4: SWARM DESIGN ENGINE & DIAMOND LOOP ARCHITECTURE (`design_tools.py`)

```mermaid
flowchart TD
    subgraph Intake_Layer["Natural Language Request Intake"]
        NL1["User Request / Swarm Vision Narrative"]
        NL2["design_swarm(description, compute_tier)"]
    end

    subgraph Diamond_Loop["The Diamond Loop Architecture"]
        subgraph Leg1_Generator["Leg 1: Creative Generator (Swarm Ideation)"]
            GEN1["Gemini 2.5 Pro API Call"]
            GEN2["Configuration: temperature = 1.0"]
            GEN3["Generates Rich Swarm Narrative & Agent Roster Strategy"]
        end

        subgraph Leg2_Critic["Leg 2: Analytical Critic (Structured Synthesis)"]
            CRT1["Gemini 2.5 Pro API Call"]
            CRT2["Configuration: temperature = 0.1"]
            CRT3["Pydantic Response Schema:<br/>SwarmDesign(agents: List[AgentDesign], topology: List[NodeDesign])"]
            CRT4["JSON Response Validation & Parsing"]
        end
    end

    subgraph Materialization["Workspace & Topology Materialization"]
        MAT1["initialize_workspace(project_name)"]
        MAT2["Persona Card Generator<br/>create_persona_card() → .agent/personas/*.json"]
        MAT3["Topology DAG Compiler<br/>build_topology() → 04_Code_Artifacts/topology.json"]
        MAT4["Workbook Sync<br/>fill_swarm_sheet() → MACCRE_Swarm_Request.xlsx"]
        MAT5["Swarm Ready for Ignition<br/>(ignite_swarm / run_swarm)"]
    end

    NL1 --> NL2 --> GEN1
    GEN1 --> GEN2 --> GEN3
    GEN3 -->|Raw Creative Narrative| CRT1
    CRT1 --> CRT2 --> CRT3 --> CRT4
    CRT4 -->|Parsed Typed SwarmDesign| MAT1
    MAT1 --> MAT2 & MAT3 & MAT4
    MAT2 & MAT3 & MAT4 --> MAT5
```

---

## SECTION 5: EXCEL WORKBOOK SHEET PARSING & MATERIALIZATION PIPELINE (`sheet_parser.py`, `workbook_engine.py`)

```mermaid
flowchart TD
    subgraph Excel_Intake["Excel Workbook Intake & Library Resolution"]
        WB1["MACCRE_Swarm_Request.xlsx"]
        WB2["load_workbook(path)<br/>(openpyxl with _vendor fallback)"]
    end

    subgraph Sheet_Parser["Sheet Parser & Normalizer (sheet_parser.py)"]
        SP1["parse_workbook()"]
        SP2["Row 1 Ignored (Title Decorative)"]
        SP3["Row 2 Header Normalization (Strip '*' & Whitespace)"]
        
        subgraph Tab_Parsers["Tab-Specific Extraction"]
            TP1["SWARM_REQUEST Tab<br/>(Project Name, Start Node, Compute Tier)"]
            TP2["AGENTS Tab<br/>(AgentName, SystemPrompt, Tools, Model)"]
            TP3["TOPOLOGY Tab<br/>(NodeID, AgentName, NextNode, Overrides)"]
            TP4["CONFIG Tabs<br/>(PIPELINE_CONFIG, MEMORY_CONFIG, VAULT_KEYS)"]
        end
        
        SP4["Typed Struct Output<br/>ParsedWorkbook Object"]
    end

    subgraph Preflight_Engine["Completeness & FinOps Engine (workbook_engine.py)"]
        PF1["check_workbook_completeness()"]
        PF2["Section Readiness Audit<br/>[AGENTS | TOPOLOGY | CONFIG | VAULT]"]
        PF3["calculate_predicted_cost()<br/>Pre-Flight Token Estimator"]
        PF4{"Validation Passed?"}
        PF5["Abort Execution & Return Readiness Error Report"]
    end

    subgraph Materialization_Output["Swarm Materialization (materialise_from_sheet)"]
        MO1["initialize_workspace()"]
        MO2["Write Agent Roster & Personas<br/>02_Dynamic_Context/agent_roster.json"]
        MO3["Write Topology Graph<br/>04_Code_Artifacts/topology.json"]
        MO4["Write Dynamic Configs<br/>02_Dynamic_Context/pipeline_config.json"]
        MO5["Materialization Complete & Ready for Execution"]
    end

    WB1 --> WB2 --> SP1
    SP1 --> SP2 --> SP3 --> TP1 & TP2 & TP3 & TP4
    TP1 & TP2 & TP3 & TP4 --> SP4
    SP4 --> PF1
    PF1 --> PF2 --> PF3 --> PF4
    PF4 -->|No| PF5
    PF4 -->|Yes| MO1
    MO1 --> MO2 & MO3 & MO4 --> MO5
```
