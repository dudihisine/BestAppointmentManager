"""
FastAPI main application for WhatsApp-first appointment assistant.
"""
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from app.config import get_settings
from app.routes.whatsapp import router as whatsapp_router
from app.routes.web import router as web_router
from app.routes.messages import router as messages_router
from app.db import test_db_connection, test_redis_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="WhatsApp Appointment Assistant",
    description="AI-powered appointment management via WhatsApp",
    version="1.0.0"
)

settings = get_settings()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(web_router)  # Web interface (no prefix for main routes)
app.include_router(messages_router)  # Messages interface (no prefix)
app.include_router(whatsapp_router, prefix="/webhooks")


@app.get("/health")
async def health_check():
    """Health check endpoint with database and Redis status."""
    db_status = test_db_connection()
    redis_status = test_redis_connection()
    
    return {
        "status": "healthy" if db_status and redis_status else "degraded",
        "service": "whatsapp-appointment-assistant",
        "database": "connected" if db_status else "disconnected",
        "redis": "connected" if redis_status else "disconnected"
    }


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info("Starting WhatsApp Appointment Assistant...")
    
    # Test connections
    db_ok = test_db_connection()
    redis_ok = test_redis_connection()
    
    if not db_ok:
        logger.error("Database connection failed!")
    if not redis_ok:
        logger.error("Redis connection failed!")
    
    if db_ok and redis_ok:
        logger.info("All connections successful. Application ready!")
    else:
        logger.warning("Some connections failed. Application may not work properly.")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("Shutting down WhatsApp Appointment Assistant...")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
