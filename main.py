from fastapi import FastAPI
from routes import user_router, kitchen_router, restaurant_router, courier_router, delivery_router, item_router, order_router
from contextlib import asynccontextmanager

from database.connection import engine, initialize_dynamo_table
from database.models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
	Base.metadata.create_all(bind=engine)
	initialize_dynamo_table()
	yield


app = FastAPI(lifespan=lifespan)

app.include_router(user_router)
app.include_router(kitchen_router)
app.include_router(restaurant_router)
app.include_router(courier_router)
app.include_router(delivery_router)
app.include_router(item_router)
app.include_router(order_router)

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "DijkFood API is running!"}