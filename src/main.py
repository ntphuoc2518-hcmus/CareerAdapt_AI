"""CareerAdapt AI - FastAPI Main Application (TV3 / Tech Lead).

FastAPI + Python implementation fulfilling F01 to F10 backend requirements.
"""
from __future__ import annotations
import sys
import os

# Add src to sys.path so modules can import directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.v1.auth import router as auth_router
from api.v1.profiles import router as profiles_router
from api.v1.skills import router as skills_router
from api.v1.submissions import router as submissions_router
from api.v1.assessments import router as assessments_router
from api.v1.evaluation import router as evaluation_router
from api.v1.roadmap import router as roadmap_router
from api.v1.progress import router as progress_router
from api.v1.reassessment import router as reassessment_router
from api.v1.admin import router as admin_router
from api.v1.reminders import router as reminders_router


app = FastAPI(
    title="CareerAdapt AI - Backend API",
    description="FastAPI Backend for CareerAdapt AI MVP (Data Analyst v3.0)",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# 1. CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. Standardized Error Handling
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail,
                "details": None
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Dữ liệu đầu vào không hợp lệ theo schema yêu cầu.",
                "details": errors
            }
        },
    )


# 3. Mount API Routers
API_V1_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_V1_PREFIX)
app.include_router(profiles_router, prefix=API_V1_PREFIX)
app.include_router(skills_router, prefix=API_V1_PREFIX)
app.include_router(submissions_router, prefix=API_V1_PREFIX)
app.include_router(assessments_router, prefix=API_V1_PREFIX)
app.include_router(evaluation_router, prefix=API_V1_PREFIX)
app.include_router(roadmap_router, prefix=API_V1_PREFIX)
app.include_router(progress_router, prefix=API_V1_PREFIX)
app.include_router(reassessment_router, prefix=API_V1_PREFIX)
app.include_router(admin_router, prefix=API_V1_PREFIX)
app.include_router(reminders_router, prefix=API_V1_PREFIX)


# 4. Root & Health Check Endpoints
@app.get("/health", tags=["Health"])
def health_check():
    """Service health status check."""
    return {
        "status": "healthy",
        "service": "CareerAdapt AI Backend",
        "version": "3.0.0",
        "tech_lead": "Hà Xuân Tỉnh (TV3)"
    }


@app.get("/", tags=["Root"])
def root_info():
    """Root info pointing to interactive Swagger documentation."""
    return {
        "message": "Chào mừng đến với API CareerAdapt AI v3.0 (Data Analyst MVP)",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
