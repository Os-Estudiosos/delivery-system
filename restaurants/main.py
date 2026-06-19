from fastapi import FastAPI
from anyio import to_thread

from routes.kitchen import router as kitchen_router
from routes.restaurants import router as restaurant_router
from routes.items import router as item_router

app = FastAPI(title="restaurants-service")


@app.on_event("startup")
async def startup_event():
    try:
        limiter = to_thread.current_default_thread_limiter()
        limiter.total_tokens = 500
        print(f"AnyIO thread pool limit set to {limiter.total_tokens}")
    except Exception as e:
        print(f"Failed to set AnyIO thread pool limit: {e}")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "restaurants"
    }

app.include_router(kitchen_router)
app.include_router(restaurant_router)
app.include_router(item_router)