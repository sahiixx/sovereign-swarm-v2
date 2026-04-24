"""Optional dependency compatibility layer."""

aiohttp = None
BaseModel = None
ValidationError = Exception
PromCounter = Histogram = Gauge = start_http_server = None
AioWeb = None

try:
    import aiohttp
except ImportError:
    pass

try:
    from pydantic import BaseModel, Field, ValidationError
except ImportError:
    pass

try:
    from prometheus_client import Counter as PromCounter, Histogram, Gauge, start_http_server
except ImportError:
    pass

try:
    from aiohttp import web as AioWeb
except ImportError:
    pass
