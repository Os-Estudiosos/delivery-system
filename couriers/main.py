from fastapi import FastAPI

from routes.couriers import router as courier_router

app = FastAPI(title="couriers-service")


@app.get("/health")
def health():
    return {"status": "ok", "service": "couriers"}


app.include_router(courier_router)
