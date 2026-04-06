import os
import logging
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any, Dict
try:
    from .rag_query import answer_question, retrieve_context, build_prompt, call_gemini
except ImportError:
    from rag_query import answer_question, retrieve_context, build_prompt, call_gemini

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("ragfolio")


app = FastAPI(
    title="Ragfolio RAG API",
    description="An orchestration layer for querying resume data using RAG.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS Configuration for development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware to log request start and end with latency.
    """
    import time
    start_time = time.time()
    logger.debug(f"Request start: {request.method} {request.url}")
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception(f"Exception during request: {request.method} {request.url}")
        raise
    process_time = (time.time() - start_time) * 1000
    logger.debug(f"Request end: {request.method} {request.url} - Status: {response.status_code} - Latency: {process_time:.2f}ms")
    return response

class AskRequest(BaseModel):
    """
    Schema for the RAG query request.
    """
    question: str


class AskResponse(BaseModel):
    """
    Schema for the RAG query response.
    """
    answer: str



@app.get("/api/health")
async def health() -> dict:
    """
    Simple health check endpoint.
    """
    logger.debug("Health check requested.")
    return {"status": "ok"}



@app.post("/api/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    """
    Primary RAG endpoint that takes a user question, retrieves context,
    and returns an AI-generated answer.
    """
    logger.debug(f"/api/ask called with question: {request.question!r}")
    if not request.question or not request.question.strip():
        logger.debug("Validation failed: Question is empty or whitespace only.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty or whitespace only.",
        )
    try:
        answer = answer_question(request.question)
        logger.debug(f"Generated answer: {answer}")
        return AskResponse(answer=answer)
    except Exception as e:
        logger.exception("An error occurred during RAG processing.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during RAG processing: {str(e)}",
        )


# --- DEBUG-CAPABLE RAG ENDPOINT ---
@app.post("/api/ask-debug")
async def ask_debug(request: AskRequest) -> dict:
    """
    Debug-capable RAG endpoint. Returns answer and detailed debug info for observability.
    """
    logger.debug(f"/api/ask-debug called with question: {request.question!r}")
    if not request.question or not request.question.strip():
        logger.debug("Validation failed: Question is empty or whitespace only.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty or whitespace only.",
        )
    try:
        # Retrieve context with ChromaDB compatibility (no include=["ids"])
        try:
            context_chunks = retrieve_context(request.question, top_k=3)
            debug_retrieved = []
            # Defensive: try to get more info if possible
            collection = None
            try:
                collection = retrieve_context.__globals__.get('_get_chroma_collection')()
            except Exception:
                pass
            if collection:
                model = retrieve_context.__globals__.get('_get_embedding_model')()
                query_embedding = next(model.embed([request.question]))
                try:
                    result = collection.query(query_embeddings=[query_embedding.tolist()], n_results=3, include=["documents", "metadatas", "distances"])
                except (TypeError, ValueError):
                    result = collection.query(query_embeddings=[query_embedding.tolist()], n_results=3)
                docs = result.get("documents", [[]])[0]
                metadatas = result.get("metadatas", [[]])[0]
                distances = result.get("distances", [[]])[0]
                ids = result.get("ids", [[]])[0] if "ids" in result else [None]*len(docs)
                for i, doc in enumerate(docs):
                    debug_retrieved.append({
                        "id": ids[i],
                        "metadata": metadatas[i] if i < len(metadatas) else None,
                        "distance": distances[i] if i < len(distances) else None,
                        "preview": doc[:120] + ("..." if len(doc) > 120 else "")
                    })
            else:
                debug_retrieved = [
                    {"id": None, "metadata": None, "distance": None, "preview": chunk[:120] + ("..." if len(chunk) > 120 else "")} for chunk in context_chunks
                ]
        except Exception as e:
            logger.exception("Error during context retrieval for debug endpoint.")
            context_chunks = []
            debug_retrieved = []

        gemini_prompt = build_prompt(request.question, context_chunks)
        logger.debug(f"Gemini input prompt: {gemini_prompt!r}")
        gemini_output = None
        try:
            gemini_output = call_gemini(gemini_prompt)
        except Exception as e:
            logger.exception("Error during Gemini call in debug endpoint.")
            gemini_output = f"Error: {str(e)}"

        logger.debug(
            f"/api/ask-debug observability:\n"
            f"  Incoming question: {request.question!r}\n"
            f"  Retrieved context items: {debug_retrieved}\n"
            f"  Gemini input prompt: {gemini_prompt!r}\n"
            f"  Gemini output: {gemini_output!r}\n"
            f"  Model params: model='gemini-2.5-flash-lite'"
        )
        return {
            "answer": gemini_output,
            "debug": {
                "question": request.question,
                "retrieved": debug_retrieved,
                "gemini_prompt": gemini_prompt,
                "gemini_output": gemini_output,
                "model": "gemini-2.5-flash-lite"
            }
        }
    except Exception as e:
        logger.exception("An error occurred during debug RAG processing.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during debug RAG processing: {str(e)}",
        )


# Serve Frontend Static Files (only in production)
FRONTEND_DIST_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.exists(FRONTEND_DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST_DIR, "assets")), name="static")

    @app.get("/{full_path:path}")
    async def serve_react_app(request: Request, full_path: str):
        # Allow /api to pass through
        if full_path.startswith("api"):
            raise HTTPException(status_code=404)
        
        # Look for the file in the frontend/dist folder
        file_path = os.path.join(FRONTEND_DIST_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
            
        # Default to React's index.html
        return FileResponse(os.path.join(FRONTEND_DIST_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

