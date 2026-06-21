import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from context_manager import ContextManager
from models import ExecuteRequest, CreateContextRequest, ContextInfo

contexts = ContextManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    contexts.ensure_defaults()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return "OK"


@app.post("/execute")
async def execute(req: ExecuteRequest):
    if req.context_id and req.language:
        raise HTTPException(400, "Provide context_id or language, not both")

    if req.context_id:
        ctx = contexts.get(req.context_id)
        if not ctx:
            raise HTTPException(404, f"Context {req.context_id} not found")
    elif req.language:
        ctx = contexts.get_or_create_default(req.language)
    else:
        ctx = contexts.get_or_create_default("python")

    async def stream():
        async for item in await ctx.execute(req.code, req.env_vars):
            yield json.dumps(item) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.post("/contexts", response_model=ContextInfo)
async def create_context(req: CreateContextRequest):
    ctx = contexts.create(req.language, req.cwd)
    return ContextInfo(id=ctx.id, language=ctx.language, cwd=ctx.cwd)


@app.get("/contexts", response_model=list[ContextInfo])
async def list_contexts():
    return [ContextInfo(id=c.id, language=c.language, cwd=c.cwd) for c in contexts.list()]


@app.delete("/contexts/{context_id}", status_code=204)
async def delete_context(context_id: str):
    deleted = await contexts.delete(context_id)
    if not deleted:
        raise HTTPException(404, f"Context {context_id} not found")


@app.post("/contexts/{context_id}/restart", status_code=204)
async def restart_context(context_id: str):
    ctx = contexts.get(context_id)
    if not ctx:
        raise HTTPException(404, f"Context {context_id} not found")
    language = ctx.language
    cwd = ctx.cwd
    await contexts.delete(context_id)
    # Re-create with same ID is not straightforward; create new and replace
    new_ctx = contexts.create(language, cwd)
    contexts._contexts[context_id] = new_ctx
    del contexts._contexts[new_ctx.id]
    new_ctx.id = context_id
