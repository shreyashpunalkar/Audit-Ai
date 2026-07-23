import sys
import os

# Add 'backend' directory to sys.path so app modules resolve correctly
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Default to /tmp for serverless file storage and database if not explicitly set
os.environ.setdefault("UPLOAD_DIR", "/tmp/uploads")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:////tmp/auditai.db")

from app.main import app
