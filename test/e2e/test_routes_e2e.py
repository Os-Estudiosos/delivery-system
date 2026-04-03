from fastapi.testclient import TestClient


def _create_kitchen(client: TestClient, kitchen_type: str = "Italian") -> dict:
    response = client.post("/kitchen/", json={"type": kitchen_type})
    assert response.status_code == 200
    return response.json()


def _create_restaurant(client: TestClient, kitchen_type_id: int, name: str = "Pasta House") -> dict:
    response = client.post(
        "/restaurant/",
        json={
            "name": name,
            "lat": -30.0284,
            "lon": -51.2287,
            "kitchen_type_id": kitchen_type_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_user_create(client: TestClient) -> None:
    response = client.post(
        "/user",
        json={
            "name": "Joao",
            "email": "joao@example.com",
            "house_lat": -30.12,
            "house_lon": -51.11,
            "phones": ["51999999999", "51888888888"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Joao"
    assert payload["email"] == "joao@example.com"
    assert set(payload["phones"]) == {"51999999999", "51888888888"}


def test_kitchen_create_get_list_patch(client: TestClient) -> None:
    created = _create_kitchen(client, "Japanese")

    get_response = client.get(f"/kitchen/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["type"] == "Japanese"

    patch_response = client.patch(
        f"/kitchen/{created['id']}",
        json={"type": "Korean"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["type"] == "Korean"

    list_response = client.get("/kitchen/")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_restaurant_crud(client: TestClient) -> None:
    kitchen = _create_kitchen(client, "Brazilian")

    create_response = client.post(
        "/restaurant/",
        json={
            "name": "Casa Sul",
            "lat": -30.0,
            "lon": -51.2,
            "kitchen_type_id": kitchen["id"],
        },
    )
    assert create_response.status_code == 201
    restaurant = create_response.json()
    restaurant_id = restaurant["id"]
    assert restaurant["kitchen_type"]["id"] == kitchen["id"]

    get_response = client.get(f"/restaurant/{restaurant_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Casa Sul"

    patch_response = client.patch(
        f"/restaurant/{restaurant_id}",
        json={"name": "Casa Sul Atualizada"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Casa Sul Atualizada"

    delete_response = client.delete(f"/restaurant/{restaurant_id}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/restaurant/{restaurant_id}")
    assert missing_response.status_code == 404


def test_restaurant_create_with_invalid_kitchen_returns_404(client: TestClient) -> None:
    response = client.post(
        "/restaurant/",
        json={
            "name": "No Kitchen",
            "lat": -30.0,
            "lon": -51.2,
            "kitchen_type_id": 999,
        },
    )

    assert response.status_code == 404


def test_courier_crud(client: TestClient) -> None:
    create_response = client.post(
        "/courier/",
        json={
            "name": "Rider One",
            "vehicle": "BIKE",
            "lat": -30.1,
            "lon": -51.1,
        },
    )
    assert create_response.status_code == 201
    courier = create_response.json()
    courier_id = courier["id"]
    assert courier["vehicle"] == "BIKE"

    get_response = client.get(f"/courier/{courier_id}")
    assert get_response.status_code == 200

    patch_response = client.patch(
        f"/courier/{courier_id}",
        json={"vehicle": "CAR"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["vehicle"] == "CAR"

    delete_response = client.delete(f"/courier/{courier_id}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/courier/{courier_id}")
    assert missing_response.status_code == 404


def test_item_crud(client: TestClient) -> None:
    kitchen = _create_kitchen(client)
    restaurant = _create_restaurant(client, kitchen["id"])

    create_response = client.post(
        "/item/",
        json={
            "name": "Spaghetti",
            "price": 35.5,
            "restaurant_id": restaurant["id"],
        },
    )
    assert create_response.status_code == 201
    item = create_response.json()
    item_id = item["id"]
    assert item["restaurant"]["id"] == restaurant["id"]

    get_response = client.get(f"/item/{item_id}")
    assert get_response.status_code == 200

    patch_response = client.patch(
        f"/item/{item_id}",
        json={"price": 39.9},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["price"] == 39.9

    delete_response = client.delete(f"/item/{item_id}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/item/{item_id}")
    assert missing_response.status_code == 404


def test_item_create_with_invalid_restaurant_returns_404(client: TestClient) -> None:
    response = client.post(
        "/item/",
        json={
            "name": "Orphan Item",
            "price": 20.0,
            "restaurant_id": 999,
        },
    )

    assert response.status_code == 404
