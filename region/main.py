from fastapi import FastAPI

from routes.region import router as region_router
app = FastAPI(title="region-service")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "region"
    }

app.include_router(region_router)