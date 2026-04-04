from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from database.connection import get_session
from database.models import Base
from routes.courier import router as courier_router
from routes.item import router as item_router
from routes.kitchen import router as kitchen_router
from routes.order import router as order_router
from routes.restaurant import router as restaurant_router
from routes.user import router as user_router


TEST_DB_PATH = Path(__file__).resolve().parent / "test_e2e.db"
TEST_DB_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"

engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def override_get_session() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def reset_db() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(user_router)
    app.include_router(kitchen_router)
    app.include_router(restaurant_router)
    app.include_router(courier_router)
    app.include_router(item_router)
    app.include_router(order_router)
    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as test_client:
        yield test_client
