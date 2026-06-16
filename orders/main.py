from fastapi import FastAPI
from routes.orders import router as orders_router
from routes.deliveries import router as deliveries_router

app = FastAPI(title="orders-service")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "orders"}

app.include_router(orders_router)
app.include_router(deliveries_router)
