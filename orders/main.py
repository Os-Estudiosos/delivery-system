from fastapi import FastAPI
from anyio import to_thread
from routes.orders import router as orders_router
from routes.deliveries import router as deliveries_router

app = FastAPI(title="orders-service")

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
    return {"status": "ok", "service": "orders"}

app.include_router(orders_router)
app.include_router(deliveries_router)

