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


def _create_user(client: TestClient, email: str = "user@example.com") -> dict:
    response = client.post(
        "/user",
        json={
            "name": "User Name",
            "email": email,
            "house_lat": -30.12,
            "house_lon": -51.11,
            "phones": ["51999999999"],
        },
    )
    assert response.status_code == 200
    return response.json()


def _create_item(client: TestClient, restaurant_id: int, name: str = "Dish", price: float = 10.0) -> dict:
    response = client.post(
        "/item/",
        json={
            "name": name,
            "price": price,
            "restaurant_id": restaurant_id,
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
    assert isinstance(payload["id"], int)
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


def test_order_crud(client: TestClient) -> None:
    kitchen = _create_kitchen(client, "Thai")
    restaurant = _create_restaurant(client, kitchen["id"], "Thai House")
    user = _create_user(client, "order-user@example.com")
    item_one = _create_item(client, restaurant["id"], "Pad Thai", 45.9)
    item_two = _create_item(client, restaurant["id"], "Curry", 39.5)

    create_response = client.post(
        "/order/",
        json={
            "restaurant_id": restaurant["id"],
            "user_id": user["id"],
            "items": [
                {"item_id": item_one["id"], "quantity": 2},
                {"item_id": item_two["id"], "quantity": 1},
            ],
        },
    )
    assert create_response.status_code == 201
    order = create_response.json()
    order_id = order["id"]
    assert order["restaurant"]["id"] == restaurant["id"]
    assert order["user"]["id"] == user["id"]
    assert order["user"]["email"] == user["email"]
    assert order["created_at"]
    assert len(order["items"]) == 2

    get_response = client.get(f"/order/{order_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == order_id
    assert get_response.json()["created_at"]

    patch_response = client.patch(
        f"/order/{order_id}",
        json={
            "items": [
                {"item_id": item_one["id"], "quantity": 5},
            ],
        },
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()
    assert len(updated["items"]) == 1
    assert updated["items"][0]["quantity"] == 5

    get_after_patch = client.get(f"/order/{order_id}")
    assert get_after_patch.status_code == 200


def test_order_create_with_invalid_user_returns_404(client: TestClient) -> None:
    kitchen = _create_kitchen(client, "Greek")
    restaurant = _create_restaurant(client, kitchen["id"], "Greek House")

    response = client.post(
        "/order/",
        json={
            "restaurant_id": restaurant["id"],
            "user_id": 999,
            "items": [],
        },
    )

    assert response.status_code == 404


def test_order_create_with_item_from_another_restaurant_returns_404(client: TestClient) -> None:
    kitchen = _create_kitchen(client, "Indian")
    restaurant_one = _create_restaurant(client, kitchen["id"], "India One")
    restaurant_two = _create_restaurant(client, kitchen["id"], "India Two")
    user = _create_user(client, "cross-item@example.com")
    wrong_item = _create_item(client, restaurant_two["id"], "Biryani", 42.0)

    response = client.post(
        "/order/",
        json={
            "restaurant_id": restaurant_one["id"],
            "user_id": user["id"],
            "items": [
                {"item_id": wrong_item["id"], "quantity": 1},
            ],
        },
    )

    assert response.status_code == 404


def test_user_orders_list_and_get_by_id(client: TestClient) -> None:
    kitchen = _create_kitchen(client, "French")
    restaurant = _create_restaurant(client, kitchen["id"], "Maison")
    user = _create_user(client, "user-orders@example.com")
    item = _create_item(client, restaurant["id"], "Crepe", 25.0)

    first_order_response = client.post(
        "/order/",
        json={
            "restaurant_id": restaurant["id"],
            "user_id": user["id"],
            "items": [{"item_id": item["id"], "quantity": 1}],
        },
    )
    assert first_order_response.status_code == 201
    first_order = first_order_response.json()

    second_order_response = client.post(
        "/order/",
        json={
            "restaurant_id": restaurant["id"],
            "user_id": user["id"],
            "items": [{"item_id": item["id"], "quantity": 3}],
        },
    )
    assert second_order_response.status_code == 201
    second_order = second_order_response.json()

    list_response = client.get(f"/user/{user['id']}/order")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    returned_order_ids = {order["id"] for order in list_payload}
    assert returned_order_ids == {first_order["id"], second_order["id"]}
    assert all(order["created_at"] for order in list_payload)

    get_response = client.get(f"/user/{user['id']}/order/{first_order['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == first_order["id"]
    assert get_response.json()["created_at"]


def test_user_order_by_id_from_another_user_returns_404(client: TestClient) -> None:
    kitchen = _create_kitchen(client, "Mexican")
    restaurant = _create_restaurant(client, kitchen["id"], "Casa Mex")
    owner_user = _create_user(client, "owner@example.com")
    another_user = _create_user(client, "other@example.com")
    item = _create_item(client, restaurant["id"], "Taco", 18.0)

    order_response = client.post(
        "/order/",
        json={
            "restaurant_id": restaurant["id"],
            "user_id": owner_user["id"],
            "items": [{"item_id": item["id"], "quantity": 2}],
        },
    )
    assert order_response.status_code == 201
    order_id = order_response.json()["id"]

    response = client.get(f"/user/{another_user['id']}/order/{order_id}")
    assert response.status_code == 404


def test_delivery_crud_without_delete(client: TestClient) -> None:
    kitchen = _create_kitchen(client, "Peruvian")
    restaurant = _create_restaurant(client, kitchen["id"], "Andes")
    user = _create_user(client, "delivery-user@example.com")

    item = _create_item(client, restaurant["id"], "Lomo Saltado", 44.0)

    order_response = client.post(
        "/order/",
        json={
            "restaurant_id": restaurant["id"],
            "user_id": user["id"],
            "items": [{"item_id": item["id"], "quantity": 1}],
        },
    )
    assert order_response.status_code == 201
    order_id = order_response.json()["id"]

    courier_one_response = client.post(
        "/courier/",
        json={
            "name": "Courier One",
            "vehicle": "BIKE",
            "lat": -30.1,
            "lon": -51.1,
        },
    )
    assert courier_one_response.status_code == 201
    courier_one_id = courier_one_response.json()["id"]

    courier_two_response = client.post(
        "/courier/",
        json={
            "name": "Courier Two",
            "vehicle": "CAR",
            "lat": -30.2,
            "lon": -51.2,
        },
    )
    assert courier_two_response.status_code == 201
    courier_two_id = courier_two_response.json()["id"]

    create_response = client.post(
        "/delivery/",
        json={
            "order_id": order_id,
            "courier_id": courier_one_id,
        },
    )
    assert create_response.status_code == 201
    delivery = create_response.json()
    delivery_id = delivery["id"]
    assert delivery["order"]["id"] == order_id
    assert delivery["courier"]["id"] == courier_one_id

    get_response = client.get(f"/delivery/{delivery_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == delivery_id

    list_response = client.get("/delivery/")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    patch_response = client.patch(
        f"/delivery/{delivery_id}",
        json={"courier_id": courier_two_id},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["courier"]["id"] == courier_two_id

    delete_response = client.delete(f"/delivery/{delivery_id}")
    assert delete_response.status_code == 405
