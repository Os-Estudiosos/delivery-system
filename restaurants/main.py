from fastapi import FastAPI

from routes.kitchen import router as kitchen_router
from routes.restaurants import router as restaurant_router
from routes.items import router as item_router

app = FastAPI(title="restaurants-service")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "restaurants"
    }

app.include_router(kitchen_router)
app.include_router(restaurant_router)
app.include_router(item_router)