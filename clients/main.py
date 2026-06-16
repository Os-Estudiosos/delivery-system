from fastapi import FastAPI

from routes.clients import router as client_router

app = FastAPI(title="clients-service")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "clients"}


app.include_router(client_router)
