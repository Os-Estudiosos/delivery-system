from fastapi import FastAPI
from routes import user_router, kitchen_router, restaurant_router
from contextlib import asynccontextmanager

from database.connection import engine
from database.models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
	Base.metadata.create_all(bind=engine)
	yield


app = FastAPI(lifespan=lifespan)

app.include_router(user_router)
app.include_router(kitchen_router)
app.include_router(restaurant_router)
