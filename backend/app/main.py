from fastapi import FastAPI

import app
from app.api.v1 import health

api = FastAPI(
    title="OmniCorp Knowledge Base Assistant",
    version=app.__version__,
    description="RAG chatbot that answers questions from OmniCorp's internal documentation.",
)
api.include_router(health.router, prefix="/api/v1")
