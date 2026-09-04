from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine
import models
from routes.auth import router as auth_router
from routes.deliveries import router as deliveries_router
from routes.riders import router as riders_router

# Creates any tables that don't already exist yet, based on the SQLAlchemy
# models. Safe to call on every startup — it never drops or alters existing
# tables, so seeded data is not affected.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Reflex Backend",
    description="Delivery management system for small Kenyan retailers",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://reflex-frontend-5q25.onrender.com",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(deliveries_router)
app.include_router(auth_router)
app.include_router(riders_router)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "Reflex API is running",
    }