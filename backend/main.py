from __future__ import annotations

import sys
from pathlib import Path

# Add src/ to path so ppa_engine is importable before any router is loaded.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import config, preview, profiles, simulation, solver, valuation

app = FastAPI(
    title="PPA Valuation Engine API",
    description="Dutch renewable energy PPA valuation and asset optimisation",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(profiles.router, prefix="/api", tags=["profiles"])
app.include_router(preview.router, prefix="/api", tags=["preview"])
app.include_router(valuation.router, prefix="/api/valuation", tags=["valuation"])
app.include_router(simulation.router, prefix="/api", tags=["simulation"])
app.include_router(solver.router, prefix="/api/solver", tags=["solver"])


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}
