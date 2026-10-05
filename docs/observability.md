# OpenTelemetry Observability Guide

This document explains how to use the distributed tracing and observability features in the RAG system.

## Architecture Overview

The system uses **OpenTelemetry** for comprehensive observability across all services:

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Frontend  │────▶│   Backend    │────▶│  PostgreSQL │
│   (Next.js) │     │  (FastAPI)   │     │  (pgvector) │
└─────────────┘     └──────┬───────┘     └─────────────┘
                          │
                          ▼
                   ┌──────────────┐     ┌─────────────┐
                   │    Celery    │────▶│    Redis    │
                   │   Worker     │     │   Broker    │
                   └──────┬───────┘     └─────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  DashScope   │
                   │  (Qwen API)  │
                   └──────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │    Jaeger    │
                   │  (Tracing)   │
                   └──────────────┘
```

## Components Instrumented

### Backend (FastAPI)
- HTTP request/response cycles
- Database queries (SQLAlchemy)
- Redis operations
- LLM API calls (HTTPX)
- Custom business logic spans

### Celery Workers
- Task publishing (producer spans)
- Task execution (consumer spans)
- Task retry and failure tracking

### Database
- Query execution time
- Connection pool metrics
- Transaction boundaries

## Viewing Traces

### Jaeger UI

Access the Jaeger dashboard at: **http://localhost:16686**

1. Select service: `rag-backend` or `rag-celery-worker`
2. Search by:
   - Operation name (e.g., `POST /api/v1/chat`)
   - Trace ID (from `X-Trace-ID` header)
   - Tags (e.g., `user.id`, `organization.id`)
3. View detailed span waterfall diagram

### Trace Example

A typical chat request trace includes:
```
POST /api/v1/chat/stream [2.3s]
├── Authentication [5ms]
├── Guardrails Check [50ms]
├── Query Rewriting [200ms]
│   └── LLM Call (Qwen) [195ms]
├── Embedding Generation [30ms]
├── Hybrid Retrieval [80ms]
│   ├── Vector Search [40ms]
│   ├── Keyword Search [20ms]
│   └── Reciprocal Rank Fusion [20ms]
├── Reranking [100ms]
└── LLM Generation [1.8s]
    └── Streaming Response [1.8s]
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OTEL_EXPORTER_ENDPOINT` | OTLP gRPC endpoint for Jaeger | `http://jaeger:4317` |
| `OTEL_SERVICE_NAME` | Service identifier in traces | `rag-backend` |
| `OTEL_AUTH_TOKEN` | Optional auth token for OTLP | - |
| `ENVIRONMENT` | Deployment environment | `development` |
| `INSTANCE_ID` | Unique instance identifier | Auto-generated |

### Custom Spans

Add custom instrumentation to your code:

```python
from app.core.observability import get_tracer

tracer = get_tracer()

with tracer.start_as_current_span("custom_operation") as span:
    span.set_attribute("custom.attribute", "value")
    span.set_attribute("user.id", user_id)
    
    # Your operation here
    result = perform_operation()
    
    span.set_attribute("result.count", len(result))
```

### Context Propagation

For downstream service calls, inject trace context:

```python
from app.core.observability import otel_config

carrier = {}
otel_config.inject_context(carrier)

# Pass carrier headers to downstream HTTP request
async with httpx.AsyncClient() as client:
    await client.post(url, headers=carrier, json=data)
```

## Metrics to Monitor

### Latency Benchmarks (P95)

| Operation | Target | Warning | Critical |
|-----------|--------|---------|----------|
| Document Upload | <5s | 10s | 30s |
| Chat Response | <3s | 5s | 10s |
| Hybrid Retrieval | <200ms | 500ms | 1s |
| LLM Generation | <2s | 5s | 10s |

### Error Rates

Monitor these error categories:
- **HTTP 5xx errors**: Backend failures
- **Task retries**: Celery task failures
- **LLM timeouts**: DashScope API issues
- **Database errors**: Connection/query failures

## Troubleshooting

### Missing Traces

1. Verify Jaeger is running: `docker ps | grep jaeger`
2. Check backend logs for OTLP connection errors
3. Ensure `OTEL_EXPORTER_ENDPOINT` is correct
4. Validate network connectivity between services

### High Latency

1. Search Jaeger for slow traces (>P95)
2. Identify bottleneck spans
3. Check database query plans
4. Review LLM API response times
5. Consider caching strategies

### Task Failures

1. Filter traces by `error=true` tag
2. Examine exception details in spans
3. Check Celery worker logs
4. Review retry counts and backoff

## Production Deployment

### Scaling Considerations

- **Sampling**: Enable probabilistic sampling for high-traffic deployments
  ```python
  from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
  
  provider = TracerProvider(
      sampler=ParentBasedTraceIdRatio(0.1)  # 10% sampling
  )
  ```

- **Batch Export**: Adjust batch size and interval based on load
  ```python
  BatchSpanProcessor(
      exporter,
      max_queue_size=2048,
      schedule_delay_millis=5000,
      max_export_batch_size=512
  )
  ```

### Security

- Use TLS for OTLP export in production
- Rotate `OTEL_AUTH_TOKEN` regularly
- Redact sensitive data from span attributes
- Implement access controls for Jaeger UI

## Integration with Other Tools

### Grafana Tempo

Replace Jaeger with Tempo for Grafana integration:

```yaml
tempo:
  image: grafana/tempo:latest
  command: ["-config.file=/etc/tempo.yaml"]
  volumes:
    - ./tempo-config.yaml:/etc/tempo.yaml
  ports:
    - "4317:4317"  # OTLP gRPC
```

### Prometheus Metrics

Combine traces with metrics:

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.exporter.prometheus import PrometheusMetricReader

# Add Prometheus exporter alongside OTLP
```

## Best Practices

1. **Use meaningful span names**: Include operation type and resource
2. **Add relevant attributes**: User IDs, document IDs, query types
3. **Record exceptions**: Always call `span.record_exception(exc)`
4. **Set status codes**: Mark spans as OK/ERROR appropriately
5. **Avoid PII**: Never log passwords, tokens, or personal data
6. **Correlate logs**: Include `trace_id` in all log entries

## Resources

- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [OTLP Protocol Specification](https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/protocol/otlp.md)
