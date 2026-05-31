from fastapi import FastAPI

from routes.kitchen import router as kitchen_router
from routes.restaurants import router as restaurant_router

app = FastAPI(title="restaurants-service")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "restaurants"
    }

app.include_router(kitchen_router)
app.include_router(restaurant_router)