# QueueStorm Investigator — Architecture

## 1. System Overview

```mermaid
flowchart TB
    Judge["🧑‍⚖️ Judge Harness / Client"]

    subgraph Service["QueueStorm Investigator (FastAPI · uv · Python 3.12)"]
        direction TB

        subgraph HTTP["HTTP Layer — app/main.py"]
            Health["GET /health<br/>returns status ok"]
            Analyze["POST /analyze-ticket"]
            ErrH["Exception handlers<br/>400 malformed · 422 semantic · 500 safe"]
        end

        subgraph Validation["Schema Layer — app/models/"]
            ReqModel["TicketRequest<br/>(request.py)"]
            RespModel["TicketResponse<br/>+ Literal enums (response.py)"]
        end

        Orchestrator["investigate()<br/>app/services/investigator.py"]

        subgraph Engine["Rule-Based Reasoning Engine"]
            direction LR
            Matcher["transaction_matcher.py<br/>• amount/type/time scoring<br/>• duplicate detection<br/>• evidence_verdict"]
            Classifier["classifier.py<br/>• case_type (regex)<br/>• department routing<br/>• severity scoring"]
            Phishing["Phishing override<br/>(safety-first, non-bypassable)"]
        end

        subgraph TextGen["Text Generation"]
            Safety["safety.py<br/>customer_reply<br/>🔒 ALWAYS template<br/>(EN / BN)"]
            LLM["llm_client.py<br/>agent_summary +<br/>next_action (optional)"]
        end
    end

    subgraph LLMBackends["LLM Backends (optional · priority fallback)"]
        Custom["1️⃣ Custom local API<br/>CUSTOM_API_URL<br/>(Ollama/LM Studio/vLLM)"]
        Groq["2️⃣ Groq free API<br/>GROQ_API_KEY"]
        RuleFB["3️⃣ Rule-based templates<br/>(always available)"]
    end

    Judge -->|"JSON"| Health
    Judge -->|"JSON ticket"| Analyze
    Analyze --> ReqModel
    ReqModel -->|"valid"| Orchestrator
    ReqModel -.->|"invalid"| ErrH

    Orchestrator --> Matcher
    Orchestrator --> Classifier
    Orchestrator --> Phishing
    Orchestrator --> Safety
    Orchestrator --> LLM

    LLM -->|"try first"| Custom
    Custom -.->|"unavailable"| Groq
    Groq -.->|"unavailable"| RuleFB

    Orchestrator --> RespModel
    RespModel -->|"200 JSON"| Judge

    classDef safety fill:#ffe6e6,stroke:#c0392b,stroke-width:2px;
    classDef llm fill:#e6f0ff,stroke:#2980b9,stroke-width:1px;
    class Safety,Phishing safety;
    class Custom,Groq,LLM llm;
```

## 2. Request Processing Pipeline

```mermaid
sequenceDiagram
    autonumber
    participant C as Client / Judge
    participant API as FastAPI Router
    participant V as Pydantic (TicketRequest)
    participant I as investigate()
    participant TM as transaction_matcher
    participant CL as classifier
    participant LLM as llm_client
    participant SF as safety

    C->>API: POST /analyze-ticket {ticket, complaint, history}
    API->>V: validate body
    alt malformed / missing fields
        V-->>C: 400 (safe error)
    else empty complaint
        API-->>C: 422 (safe error)
    else valid
        API->>I: investigate(req)
        I->>TM: match_transaction()
        TM-->>I: relevant_transaction_id, evidence_verdict
        I->>CL: classify_case_type / route_department / score_severity
        CL-->>I: case_type, department, severity
        Note over I: Phishing override<br/>(forces fraud_risk, ignores injected text)
        I->>LLM: enhance_text_fields() [optional]
        LLM-->>I: agent_summary, next_action (or template fallback)
        I->>SF: build_safe_reply() 🔒 always template
        SF-->>I: customer_reply (safe, EN/BN)
        I-->>API: TicketResponse
        API-->>C: 200 {structured JSON}
    end
```

## 3. LLM Fallback Decision Flow

```mermaid
flowchart LR
    Start(["enhance_text_fields()"]) --> Q1{"CUSTOM_API_URL<br/>set?"}
    Q1 -->|yes| C1["Call custom API<br/>model=CUSTOM_MODEL (auto)"]
    C1 --> C1ok{"valid JSON<br/>response?"}
    C1ok -->|yes| Use["Use LLM text for<br/>agent_summary + next_action"]
    C1ok -->|no / error / timeout| Q2
    Q1 -->|no| Q2{"GROQ_API_KEY<br/>set?"}
    Q2 -->|yes| C2["Call Groq API<br/>model=GROQ_MODEL"]
    C2 --> C2ok{"valid JSON<br/>response?"}
    C2ok -->|yes| Use
    C2ok -->|no / error / timeout| FB
    Q2 -->|no| FB["Rule-based templates<br/>(deterministic, always works)"]
    Use --> End(["return text fields"])
    FB --> End

    classDef fb fill:#e8f5e9,stroke:#27ae60,stroke-width:2px;
    class FB fb;
```

## Design Principles

| Principle | How it shows up in the architecture |
|-----------|-------------------------------------|
| **Safety is non-negotiable** | `customer_reply` is **always** template-generated (`safety.py`), never from an LLM. Phishing detection overrides classification and cannot be bypassed by complaint text. |
| **Graceful degradation** | Three-tier LLM fallback ends in rule-based templates, so the service works fully offline with zero API keys. |
| **Evidence over text** | The complaint is investigated against `transaction_history` (`transaction_matcher.py`) — not just classified — producing `relevant_transaction_id` and `evidence_verdict`. |
| **Fail safe, never crash** | All malformed input returns controlled 400/422/500 with non-sensitive messages; no stack traces or secrets leak. |
| **Deterministic core** | The rule engine is pure/in-process: ~20ms p95, well under the 30s limit, and reproducible for automated judging. |
