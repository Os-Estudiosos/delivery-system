from fastapi import FastAPI
from anyio import to_thread

from routes.couriers import router as courier_router

app = FastAPI(title="couriers-service")


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
    return {"status": "ok", "service": "couriers"}


app.include_router(courier_router)

