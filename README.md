# Production-Grade RAG System

A enterprise-ready Retrieval-Augmented Generation (RAG) system built with FastAPI, Next.js, PostgreSQL/pgvector, and Qwen LLM. This implementation follows Domain-Driven Design (DDD) principles for maintainability and scalability.

## Why This Architecture?

### Hybrid Search Over Pure Vector Search
Vector search alone fails on:
- **Exact error codes** (e.g., "ERR-504")
- **Acronyms and abbreviations** (e.g., "API", "SDK")
- **Product names and version numbers**

Our hybrid approach combines:
1. **Dense retrieval** (pgvector) for semantic similarity
2. **Sparse retrieval** (PostgreSQL tsvector/BM25) for exact matching
3. **Reciprocal Rank Fusion (RRF)** to merge results without tuning weights

### Key Technical Decisions

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Task Queue | Celery + Redis | Production-grade async processing with retries |
| Embeddings | BGE-M3 (local) | Best balance of quality, speed, and cost |
| LLM | Qwen via DashScope API | Strong performance, no GPU management |
| Observability | OpenTelemetry + Jaeger | Industry-standard distributed tracing |
| Auth | JWT + Multi-tenancy | Enterprise security from day one |
| Streaming | Native SSE | Zero dependencies, full control |

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Next.js   │────▶│   FastAPI    │────▶│   Celery    │
│  Frontend   │◀────│   Backend    │◀────│   Worker    │
└─────────────┘     └──────────────┘     └─────────────┘
                           │                    │
                           ▼                    ▼
                    ┌──────────────┐     ┌─────────────┐
                    │  PostgreSQL  │     │    Redis    │
                    │  + pgvector  │     │   Broker    │
                    └──────────────┘     └─────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   Jaeger     │
                    │   Tracing    │
                    └──────────────┘
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Make (optional but recommended)
- Qwen API key (DashScope)

### Environment Setup

```bash
cp .env.example .env
# Edit .env with your Qwen API key and other settings
```

### Start All Services

```bash
make up          # Start all containers
make migrate     # Run database migrations
make logs        # View logs
```

### Access Points
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Jaeger UI**: http://localhost:16686

## Project Structure

```
qwen-rag-assistant/
├── backend/
│   ├── app/
│   │   ├── api/routes/       # REST endpoints
│   │   ├── core/             # Config, DB, security
│   │   ├── models/           # SQLAlchemy ORM
│   │   ├── schemas/          # Pydantic validation
│   │   ├── services/         # Business logic
│   │   │   ├── generation/   # RAG orchestration
│   │   │   ├── guardrails/   # Safety checks
│   │   │   ├── ingestion/    # Parsing, chunking, embedding
│   │   │   ├── llm/          # Qwen provider
│   │   │   ├── memory/       # Conversation history
│   │   │   └── retrieval/    # Hybrid search
│   │   ├── tasks/            # Celery workers
│   │   └── evals/            # Evaluation framework
│   ├── tests/
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/              # Next.js routes
│   │   ├── components/       # React components
│   │   ├── hooks/            # Custom hooks
│   │   └── services/         # API client
│   └── Dockerfile
├── docker-compose.yml
└── Makefile
```

## Available Commands

```bash
make up              # Start dev environment
make down            # Stop all services
make migrate         # Run DB migrations
make celery          # Start Celery worker
make test            # Run tests
make lint            # Run linters
make eval            # Run evaluation suite
make logs            # Follow all logs
```

## Evaluation Framework

The system includes a comprehensive evaluation pipeline:

```bash
# Run evaluation against golden dataset
python -m app.evals.runner

# Sample metrics output:
{
  "retrieval": {
    "recall_at_5": 0.85,
    "precision_at_5": 0.72,
    "mrr": 0.78,
    "ndcg": 0.81
  },
  "generation": {
    "avg_relevance": 4.2,
    "avg_groundedness": 4.5,
    "avg_citation_accuracy": 4.3
  }
}
```

## Security Features

- **JWT Authentication**: Secure user sessions
- **Multi-tenancy**: Organization-level data isolation
- **Guardrails**: Pre/post-LLM safety checks
  - Prompt injection detection
  - PII redaction
  - Toxic content filtering
- **Rate Limiting**: Per-user API throttling

## Observability

Every request is traced with:
- Unique trace IDs
- Latency breakdown (DB, retrieval, LLM)
- Token usage tracking
- Retrieval scores

View traces in Jaeger at http://localhost:16686

## API Examples

### Upload Document

```bash
curl -X POST http://localhost:8000/api/documents \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf"
```

### Chat (Streaming)

```bash
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "How does hybrid search work?"}'
```

## Portfolio Highlights

This project demonstrates:

1. **Production Architecture**: DDD, async I/O, proper separation of concerns
2. **Advanced RAG**: Hybrid search, query rewriting, citation parsing
3. **Enterprise Ready**: Multi-tenancy, auth, guardrails, observability
4. **Evaluation-Driven**: Golden datasets, IR metrics, LLM-as-judge
5. **Modern Stack**: FastAPI, Next.js, PostgreSQL/pgvector, Celery

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request
"# RAG-main" 
"# RAG-main" 
"# RAG-main" 
