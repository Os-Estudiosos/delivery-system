from fastapi import FastAPI

app = FastAPI(title="restaurants-service")


@app.get("/health")
def health():
    return {"status": "ok", "service": "restaurants"}
