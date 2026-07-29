# Wave 2 Architecture Analysis: Net & Client Subsystem (`maccre_core._net`)

**Target Output File Path:** `B:\EXO_GANS\Analysis\Wave2\flowchart_01_net_client.md`  
**Source Subsystem:** `B:\EXO_GANS\maccre_core\_net\`  
**Reference Ledger:** `B:\EXO_GANS\Analysis\Wave1\01_net_subsystem_ledger.md`  
**Status:** Deep Architectural Synthesis & Modular Flowchart Report Complete  

---

## 1. EXECUTIVE SUMMARY & SUBSYSTEM ARCHITECTURAL OVERVIEW

The `maccre_core._net` subsystem constitutes the zero-dependency networking, inference orchestration, hardware probing, model health sentinel, capability surface classification, and native document generation engine of the MACCREv2 sovereign edge architecture.

---

## 2. MASTER SUBSYSTEM ARCHITECTURE & TRANSPORT LOOP

```mermaid
flowchart TD
    subgraph Client_Call_Site["Caller / Swarm Agent"]
        A["OmniDaemon.generate(prompt, model_id, schema, compute_tier)"]
    end

    subgraph Schema_Transformation["Schema Extraction Engine"]
        B{"Schema Provided?"}
        C["_dataclass_to_json_schema(cls)"]
        D["JSON Schema Spec\n(type, properties, required)"]
    end

    subgraph Environment_Probing["Environment Probe Engine"]
        E["get_environment_matrix()"]
        F["GET http://localhost:11434/api/tags"]
        G["Check os.cpu_count() >= 8"]
        H["Matrix: {ollama_active: bool, high_compute: bool}"]
    end

    subgraph Compute_Tier_Routing["Multi-Tier Transport Router"]
        I{"Select Compute Tier"}
        J["_route_local()"]
        K["_route_edge()"]
        L["_route_cloud()"]
    end

    subgraph Local_Execution["Local Tier (Ollama)"]
        M["POST http://localhost:11434/api/generate"]
        N["Model: gemma\nFormat: JSON Schema"]
    end

    subgraph Edge_Execution["Edge Tier (Personal Cloud)"]
        O["POST MACCRE_EDGE_URL\nhttp://127.0.0.1:8080/v1/chat/completions"]
        P["OpenAI-Compatible Payload\nBearer edge-token"]
    end

    subgraph Cloud_Execution["Cloud Tier (Sovereign Gemini REST)"]
        Q["GeminiClient.generate_content()"]
        R["URLLib HTTP Request\nhttps://generativelanguage.googleapis.com/v1beta/"]
    end

    subgraph Output_Processing["Output & Schema Enforcement"]
        S{"Execution Success?"}
        T{"Compute Tier == hybrid & Local Failed?"}
        U["Log Warning & Fallback to Cloud"]
        V["Raw Output String"]
        W{"Schema Casting Needed?"}
        X["Strip Markdown (```json ... ```)"]
        Y["dict_to_dataclass(schema, raw_dict)"]
        Z["Return Dataclass Instance / String"]
    end

    A --> B
    B -- Yes --> C --> D --> E
    B -- No --> E
    E --> F & G --> H --> I

    I -- "tier == local OR (hybrid & ollama_active)" --> J --> M --> N --> S
    I -- "tier == edge" --> K --> O --> P --> S
    I -- "tier == cloud" --> L --> Q --> R --> S

    S -- No --> T
    T -- Yes --> U --> L
    T -- No --> ERROR["Raise URLError / Exception"]
    S -- Yes --> V --> W
    W -- Yes --> X --> Y --> Z
    W -- No --> Z
```

---

## 3. GEMINI REST API ENDPOINTS & REQUEST ARCHITECTURE

```mermaid
flowchart TD
    subgraph Key_Vault["Universal Vault & Key Lifecycle"]
        K1["key_provider() -> Raw API Key"]
        K2["x-goog-api-key HTTP Header"]
        K3["finally: wipe_string(raw_key)"]
    end

    subgraph API_Endpoints["Google Generative Language REST Surface"]
        EP1["generateContent\nPOST /v1beta/models/{model}:generateContent"]
        EP2["streamGenerateContent\nPOST /v1beta/models/{model}:streamGenerateContent?alt=sse"]
        EP3["embedContent\nPOST /v1beta/models/{model}:embedContent"]
        EP4["batchEmbedContents\nPOST /v1beta/models/{model}:batchEmbedContents"]
        EP5["File API Upload\nPOST /upload/v1beta/files"]
        EP6["File API Metadata / Delete\nGET|DELETE /v1beta/files/{name}"]
        EP7["Context Caching\nPOST /v1beta/cachedContents"]
        EP8["List Models\nGET /v1beta/models?pageSize=100"]
    end

    subgraph Request_Builders["Request Construction Engine"]
        B1["_build_request_body()"]
        B2["Contents, SystemInstruction, GenerationConfig"]
        B3{"Tools / Grounding / Thinking"}
        B4["Function Declarations\n(AUTO Mode)"]
        B5["Google Search Grounding"]
        B6["Thinking Config\n(includeThoughts: True)"]
        B7["_make_req() -> urllib.request.Request"]
    end

    subgraph HTTP_Execution["Pure Stdlib Transport Loop"]
        H1["_call(req, ssl_context, timeout)"]
        H2["urllib.request.urlopen()"]
        H3{"HTTP Status == 200?"}
        H4["Parse HTTPError Body (code, msg)"]
        H5["json.loads(raw_bytes)"]
        H6{"API Response Error Object?"}
        H7["Raise RuntimeError"]
    end

    subgraph Response_Parsing["Response Container Objects"]
        R1["GeminiResponse"]
        R2[".text (Candidate text + Search Grounding Sources)"]
        R3[".scratchpad_thought (Native Thinking blocks)"]
        R4[".function_call (name, args tuple)"]
        R5[".prompt_tokens / .candidate_tokens"]

        R6["EmbeddingResponse"]
        R7[".values (list[float])"]

        R8["FileMetadata"]
        R9[".name, .uri, .mime_type, .state (ACTIVE/PROCESSING)"]
    end

    K1 --> B1
    B1 --> B2 --> B3
    B3 -- Function Declarations --> B4
    B3 -- Search Grounding (No Tools) --> B5
    B3 -- Thinking Model --> B6
    B4 & B5 & B6 --> B7
    B7 --> K2 --> H1 --> H2 --> H3
    H3 -- No --> H4 --> H7
    H3 -- Yes --> H5 --> H6
    H6 -- Yes --> H7
    H6 -- No --> K3

    H5 --> EP1 & EP2 & EP3 & EP4 & EP5 & EP6 & EP7 & EP8

    EP1 --> R1 --> R2 & R3 & R4 & R5
    EP3 & EP4 --> R6 --> R7
    EP5 & EP6 --> R8 --> R9
```

---

## 4. MODEL SENTINEL ACTIVE HEALTH PROBING & TELEMETRY

```mermaid
flowchart TD
    subgraph Sentinel_Lifecycle["ModelSentinel Daemon Initialization"]
        S1["get_sentinel(key_provider, probe_interval_s=1800)"]
        S2["_load_cache() -> Cold-Start Recovery\n(scripts/model_capability_map.json)"]
        S3["start() -> Launch Thread('ModelSentinel', daemon=True)"]
    end

    subgraph Background_Probe_Loop["Background Probe Thread Loop (_run_loop)"]
        P1["Sleep probe_interval_s (1800s)"]
        P2["_probe_cycle()"]
        P3["_fetch_all_models()\nGET /v1beta/models?pageSize=100"]
        P4{"Models Returned > 0?"}
        P5["Diff snapshot against previous catalog"]
        P6{"Catalog Changes Detected?"}
        E1["MODEL_ADDED Event"]
        E2["MODEL_DIED Event"]
        P7["_save_cache() -> Write snapshot to JSON"]
    end

    subgraph Live_Telemetry["Call Site Telemetry Engine"]
        T1["Call Site Execution"]
        T2["record_success(model, latency_ms)"]
        T3["record_error(model, error_str, latency_ms)"]
        T4["ModelHealth.record(success, latency_ms)"]
        T5["Sliding Window deque(maxlen=20)"]
        T6["Compute error_rate = errors / window_len"]
        T7{"Evaluate Health State"}
        H1["error_rate >= 0.30 -> MODEL_DEGRADED"]
        H2["error_rate == 1.00 -> MODEL_DIED / is_live = False"]
        H3["error_rate < 0.30 -> MODEL_RECOVERED"]
        H4["429 / RESOURCE_EXHAUSTED -> QUOTA_EXHAUSTED"]
    end

    subgraph Sentinel_Queries["Thread-Safe Health Queries (with _lock)"]
        Q1["is_healthy(model) -> in_catalogue AND is_live AND NOT is_degraded"]
        Q2["is_live(model) -> in_catalogue AND is_live"]
        Q3["report() -> Snapshot stats (healthy, degraded, dead counts)"]
    end

    S1 --> S2 --> S3 --> P1
    P1 --> P2 --> P3 --> P4
    P4 -- No --> P1
    P4 -- Yes --> P5 --> P6
    P6 -- New Model Discovered --> E1
    P6 -- Model Removed from API --> E2
    P5 --> P7 --> P1

    T1 -- API Success --> T2 --> T4
    T1 -- API Error --> T3 --> T4
    T4 --> T5 --> T6 --> T7
    T7 --> H1 & H2 & H3 & H4

    Q1 & Q2 & Q3 <--> Sentinel_Lifecycle
```

---

## 5. MODEL SURFACE CLASSIFICATION & CAPABILITY FAILOVER

```mermaid
flowchart TD
    subgraph Live_Probe["Model Discovery & Classification"]
        M1["ModelRegistry._probe()"]
        M2["GET /v1beta/models"]
        M3["classify_surface(name, supportedMethods)"]
    end

    subgraph Method_Classification["Primary Method Classification"]
        C1{"Check supportedGenerationMethods"}
        M_LIVE["bidiGenerateContent only -> ModelSurface.LIVE"]
        M_EMB["embedContent / asyncBatchEmbedContent -> ModelSurface.EMBEDDING"]
        M_VID["predictLongRunning -> ModelSurface.VIDEO"]
        M_IMG["predict only -> ModelSurface.IMAGEN"]
        M_AQA["generateAnswer -> ModelSurface.AQA"]
    end

    subgraph Name_Classification["Secondary Name-Pattern Match"]
        C2{"Match Name Pattern"}
        N_RES["'deep-research' -> DEEP_RESEARCH"]
        N_IMG["'imagen-' -> IMAGEN"]
        N_VEO["'veo-' -> VIDEO"]
        N_LYR["'lyria-' -> AUDIO_GEN"]
        N_GEM["'gemma-' -> EDGE"]
        N_EMB["'gemini-embedding' -> EMBEDDING"]
        N_ROB["'gemini-robotics' -> ROBOTICS"]
        N_CPU["'gemini-2.5-computer-use' -> COMPUTER_USE"]
        N_TTS["'-tts' / 'native-audio' -> TTS"]
        N_IGN["'-image' -> IMAGE_GENERATION"]
        N_TXT["Default -> TEXT_GENERATION"]
    end

    subgraph Surface_Taxonomy["13 Model Surface Surfaces"]
        S_TXT["TEXT_GENERATION (22 models)"]
        S_TTS["TTS"]
        S_IMG["IMAGE_GENERATION"]
        S_LIV["LIVE (4 models)"]
        S_EMB["EMBEDDING (3 models)"]
        S_VEO["VIDEO (6 models)"]
        S_OTH["DEEP_RESEARCH / EDGE / ROBOTICS / COMPUTER_USE / AUDIO_GEN / IMAGEN / AQA"]
    end

    subgraph Failover_Construction["Intra-Surface Failover Engine"]
        F1["get_failover_chain(model_name)"]
        F2{"Surface == TEXT_GENERATION?"}
        F3["_build_text_chain(model_name)"]
        F4["Classify Tier: pro (0) -> flash (1) -> lite (2) -> experimental (3)"]
        F5["Build Chain: Requested Model -> Same-Tier Peers -> Next Lower Tier"]
        F6["Non-Text Surface Chain: Requested Model -> Surface Peers"]
        F7{"ModelSentinel Wired?"}
        F8["Filter / Sort Degraded & Dead Models to Back of Chain"]
        F9["Return Healthy Failover Chain List"]
    end

    M1 --> M2 --> M3 --> C1
    C1 -- Match --> M_LIVE & M_EMB & M_VID & M_IMG & M_AQA
    C1 -- generateContent --> C2
    C2 --> N_RES & N_IMG & N_VEO & N_LYR & N_GEM & N_EMB & N_ROB & N_CPU & N_TTS & N_IGN & N_TXT

    M_LIVE --> S_LIV
    M_EMB & N_EMB --> S_EMB
    M_VID & N_VEO --> S_VEO
    N_TTS --> S_TTS
    N_IGN --> S_IMG
    N_TXT --> S_TXT
    N_RES & N_IMG & N_LYR & N_GEM & N_ROB & N_CPU & M_IMG & M_AQA --> S_OTH

    F1 --> F2
    F2 -- Yes --> F3 --> F4 --> F5 --> F7
    F2 -- No --> F6 --> F7
    F7 -- Yes --> F8 --> F9
    F7 -- No --> F9
```

---

## 6. SOVEREIGN OOXML WORKBOOK ZIP PACKAGING ENGINE

```mermaid
flowchart TD
    subgraph Object_Model["In-Memory Workbook Object Model"]
        WB["Workbook"]
        WS["Worksheet(title)"]
        CELL["Cell(row, col, value, font, fill, alignment, border)"]
        VAL["DataValidation(sqref, formula1, show_dropdown)"]
        WB --> WS
        WS --> CELL
        WS --> VAL
    end

    subgraph Style_Deduplication["StyleRegistry & xf Map Engine"]
        SR["StyleRegistry"]
        F_IDF["get_font_id(font) -> fonts table index"]
        F_IDFILL["get_fill_id(fill) -> fills table index"]
        F_IDBRD["get_border_id(border) -> borders table index"]
        XF_KEY["XfKey = (font_id, fill_id, border_id, halign, valign, wrap)"]
        XF_MAP["_xf_map: dict[XfKey, int] -> cellXfs table index"]

        CELL --> SR
        SR --> F_IDF & F_IDFILL & F_IDBRD --> XF_KEY --> XF_MAP
    end

    subgraph XML_Serialization["ECMA-376 XML Rendering Loop"]
        WS_XML["Worksheet.to_xml(registry)"]
        O1["1. <cols> (column widths)"]
        O2["2. <sheetData> (rows & cells with inlineStr / v)"]
        O3["3. <mergeCells> (merged ranges ref)"]
        O4["4. <dataValidations> (dropdown lists)"]
        
        WS_XML --> O1 --> O2 --> O3 --> O4
    end

    subgraph ZIP_Packaging["Workbook.save(filepath) ZIP Assembly"]
        Z0["zipfile.ZipFile(buf, 'w', ZIP_DEFLATED)"]
        Z1["[Content_Types].xml\n(Default rels/xml, Overrides for workbook/styles/sheets)"]
        Z2["_rels/.rels\n(Target: xl/workbook.xml)"]
        Z3["xl/workbook.xml\n(<sheets> list with sheetId and rId)"]
        Z4["xl/_rels/workbook.xml.rels\n(Relationships to styles, sharedStrings, sheets)"]
        Z5["xl/styles.xml\n(<fonts>, <fills>, <borders>, <cellStyleXfs>, <cellXfs>, <cellStyles>)"]
        Z6["xl/sharedStrings.xml\n(Minimal SST container)"]
        Z7["xl/worksheets/sheet1.xml, sheet2.xml...\n(Remaps temp style tags to cell 's' attributes)"]
        
        Z0 --> Z1 --> Z2 --> Z3 --> Z4 --> Z5 --> Z6 --> Z7
        Z7 --> DISK["Path(filepath).write_bytes(buf.read())"]
    end
```
