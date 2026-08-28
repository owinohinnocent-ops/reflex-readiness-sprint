from fastapi import FastAPI
from database import Base, engine
import models
from routes.deliveries import router as deliveries_router
from routes.auth import router as auth_router

# Create database tables in SQLite
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Reflex Backend",
    description="Delivery management system for small Kenyan retailers",
    version="0.1.0",
)

# Register routes
app.include_router(deliveries_router)
app.include_router(auth_router)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "Reflex API is running",
    }
