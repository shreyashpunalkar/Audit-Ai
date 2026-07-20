# routers package
from app.routers.upload import router as upload_router
from app.routers.process import router as process_router
from app.routers.document import router as document_router

__all__ = ["upload_router", "process_router", "document_router"]
