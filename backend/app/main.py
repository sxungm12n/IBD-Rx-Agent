import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.filtering import router as eligibility_router
from app.rag.errors import GuideNotReady
from app.rag.pipeline import guide_service
from app.rag.router import router as guide_router
from app.rag.stage_router import router as stage_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async def warm() -> None:
        try:
            await asyncio.to_thread(guide_service.warm)
        except GuideNotReady:
            logger.exception("guide warmup failed")

    task = asyncio.create_task(warm())
    yield
    task.cancel()


app = FastAPI(
    title="IBD Rx Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(eligibility_router)
app.include_router(guide_router)
app.include_router(stage_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ibd-rx-agent"}
