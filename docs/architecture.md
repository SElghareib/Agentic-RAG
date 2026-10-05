# System Architecture

## Overview

This RAG system follows Domain-Driven Design (DDD) with clear separation between infrastructure, domain logic, and interface layers.

## Core Components

### 1. Document Ingestion Pipeline

```
Upload → Parser → Chunker → Embedder → PostgreSQL/pgvector
           │         │          │
           ▼         ▼          ▼
        pypdf    Semantic    BGE-M3
        markdown Fixed-size  Normalized
        docx     Overlap     Vectors
```

**Files:**
- `backend/app/services/ingestion/parser.py` - Document parsing
- `backend/app/services/ingestion/chunker.py` - Text chunking strategies
- `backend/app/services/ingestion/embedder.py` - Embedding generation

### 2. Hybrid Retrieval System

```
Query → Embedder → Vector Search ─┐
            │                      ├→ RRF Fusion → Ranked Results
            └→ Keyword Search ────┘
```

**Algorithm: Reciprocal Rank Fusion (RRF)**
```
score(d) = Σ 1 / (k + rank_i(d))
```

Where k=60 (dampening constant)

**Files:**
- `backend/app/services/retrieval/vector_search.py` - pgvector cosine similarity
- `backend/app/services/retrieval/keyword_search.py` - PostgreSQL tsvector
- `backend/app/services/retrieval/hybrid_search.py` - RRF implementation

### 3. RAG Generation Pipeline

```
Query → [Safety Check] → [Query Rewrite] → Retrieve → Build Prompt → Qwen LLM → Parse Citations → Response
          │                    │              │            │             │              │
          ▼                    ▼              ▼            ▼             ▼              ▼
      Guardrails          Conversation    Hybrid       Templates    Streaming     Validation
                         History Mgmt     Search
```

**Files:**
- `backend/app/services/generation/rag_service.py` - Orchestration
- `backend/app/services/llm/provider.py` - Qwen API client
- `backend/app/services/llm/prompts.py` - Prompt templates
- `backend/app/services/guardrails/safety.py` - Safety checks

### 4. Multi-Turn Conversation Management

```
User Query → History Retrieval → Query Rewriter → Standalone Query
                │
                ▼
        Message Storage ← LLM Response
```

**Files:**
- `backend/app/services/memory/history.py` - Conversation state
- `backend/app/services/memory/query_rewriter.py` - Contextual rewriting

## Data Flow

### Document Upload Flow

1. User uploads file via `POST /api/documents`
2. File stored temporarily, metadata saved to DB
3. Celery task triggered for async processing
4. Task: Parse → Chunk → Embed → Store chunks with vectors
5. Document status updated (processing → ready/failed)

### Query Flow

1. User sends query via `POST /api/chat/stream`
2. Guardrails check input for injection attempts
3. If multi-turn: rewrite query using conversation history
4. Generate query embedding with BGE-M3
5. Run hybrid search (vector + keyword)
6. Apply RRF to merge results
7. Build prompt with context chunks
8. Stream response from Qwen LLM
9. Parse citations and validate
10. Save conversation to history
11. Return SSE stream to client

## Database Schema

### Key Tables

- **organizations**: Multi-tenant isolation
- **users**: JWT-authenticated users
- **documents**: File metadata, processing status
- **chunks**: Text segments with pgvector embeddings + tsvector
- **conversations**: Multi-turn session tracking
- **messages**: Individual Q&A pairs with citations
- **request_traces**: Observability data (latency, scores, tokens)

## Security Model

```
Request → API Key/JWT → Organization Scope → Row-Level Access
              │
              ▼
         Rate Limiting
              │
              ▼
         Guardrails Check
```

## Observability Stack

Every request generates:
- Unique trace ID (X-Trace-ID header)
- Span for each phase (DB, retrieval, LLM)
- Metrics: latency, token count, retrieval scores

Exported to Jaeger via OpenTelemetry collector.
