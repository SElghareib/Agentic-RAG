"""Rate limiting middleware using SlowAPI"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


# Create rate limiter instance
limiter = Limiter(key_func=get_remote_address)


def setup_rate_limiter(app):
    """
    Configure rate limiting for the FastAPI application.
    
    Default limit: 60 requests per minute per IP address.
    Can be overridden on specific routes with @limiter.limit decorator.
    """
    app.state.limiter = limiter
    
    # Add rate limit header to all responses
    @app.middleware("http")
    async def add_rate_limit_headers(request, call_next):
        response = await call_next(request)
        
        # Add rate limit info headers (if available from slowapi)
        if hasattr(request.scope, "rate_limit"):
            response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT_PER_MINUTE)
        
        return response


def rate_limit_requests(per_minute: int = None):
    """
    Decorator for applying rate limits to specific endpoints.
    
    Usage:
        @router.get("/endpoint")
        @rate_limit_requests(per_minute=10)
        async def endpoint():
            ...
    """
    limit_value = per_minute or settings.RATE_LIMIT_PER_MINUTE
    
    def decorator(func):
        return limiter.limit(f"{limit_value}/minute")(func)
    
    return decorator
