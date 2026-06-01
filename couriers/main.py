from fastapi import FastAPI

app = FastAPI(title="couriers-service")


@app.get("/health")
def health():
    return {"status": "ok", "service": "couriers"}
