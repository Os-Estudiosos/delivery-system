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
    assert order["courier"] is None
    assert order["status"] is None

    get_response = client.get(f"/order/{order_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == order_id
    assert get_response.json()["created_at"]
    assert get_response.json()["courier"] is None
    assert get_response.json()["status"] is None

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
    assert updated["courier"] is None
    assert updated["status"] is None

    get_after_patch = client.get(f"/order/{order_id}")
    assert get_after_patch.status_code == 200
    assert get_after_patch.json()["courier"] is None
    assert get_after_patch.json()["status"] is None


def test_order_create_with_invalid_user_returns_404(client: TestClient) -> None:
    kitchen = _create_kitchen(client, "Greek")
    restaurant = _create_restaurant(client, kitchen["id"], "Greek House")
    item = _create_item(client, restaurant["id"], "Gyros", 33.0)

    response = client.post(
        "/order/",
        json={
            "restaurant_id": restaurant["id"],
            "user_id": 999,
            "items": [{"item_id": item["id"], "quantity": 1}],
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
    assert all(order["courier"] is None for order in list_payload)
    assert all(order["status"] is None for order in list_payload)

    get_response = client.get(f"/user/{user['id']}/order/{first_order['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == first_order["id"]
    assert get_response.json()["created_at"]
    assert get_response.json()["courier"] is None
    assert get_response.json()["status"] is None


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


def test_delivery_status_flow_creates_events_in_order(client: TestClient) -> None:
    kitchen = _create_kitchen(client, "Argentine")
    restaurant = _create_restaurant(client, kitchen["id"], "Pampa")
    user = _create_user(client, "status-flow@example.com")
    item = _create_item(client, restaurant["id"], "Asado", 55.0)

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

    courier_response = client.post(
        "/courier/",
        json={
            "name": "Status Courier",
            "vehicle": "MOTORCYCLE",
            "lat": -30.3,
            "lon": -51.3,
        },
    )
    assert courier_response.status_code == 201
    courier_id = courier_response.json()["id"]

    delivery_response = client.post(
        "/delivery/",
        json={"order_id": order_id, "courier_id": courier_id},
    )
    assert delivery_response.status_code == 201
    delivery_id = delivery_response.json()["id"]

    for expected_status in [
        "CONFIRMED",
        "PREPARING",
        "READY_FOR_PICKUP",
        "PICKED_UP",
        "IN_TRANSIT",
        "DELIVERED",
    ]:
        response = client.patch(
            f"/delivery/{delivery_id}/status",
            json={"status": expected_status},
        )
        assert response.status_code == 201
        assert response.json()["status"] == expected_status
        assert response.json()["delivery_id"] == delivery_id


def test_delivery_status_flow_rejects_skipping_step(client: TestClient) -> None:
    kitchen = _create_kitchen(client, "Venezuelan")
    restaurant = _create_restaurant(client, kitchen["id"], "Caracas")
    user = _create_user(client, "status-skip@example.com")
    item = _create_item(client, restaurant["id"], "Arepa", 14.0)

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

    courier_response = client.post(
        "/courier/",
        json={
            "name": "Skip Courier",
            "vehicle": "BIKE",
            "lat": -30.4,
            "lon": -51.4,
        },
    )
    assert courier_response.status_code == 201
    courier_id = courier_response.json()["id"]

    delivery_response = client.post(
        "/delivery/",
        json={"order_id": order_id, "courier_id": courier_id},
    )
    assert delivery_response.status_code == 201
    delivery_id = delivery_response.json()["id"]

    response = client.patch(
        f"/delivery/{delivery_id}/status",
        json={"status": "PREPARING"},
    )

    assert response.status_code == 409


def test_order_events_with_delivery(client: TestClient) -> None:
    kitchen = _create_kitchen(client, "Spanish")
    restaurant = _create_restaurant(client, kitchen["id"], "Iberia")
    user = _create_user(client, "events-user@example.com")
    item = _create_item(client, restaurant["id"], "Paella", 48.0)

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

    courier_response = client.post(
        "/courier/",
        json={
            "name": "Events Courier",
            "vehicle": "BIKE",
            "lat": -30.5,
            "lon": -51.5,
        },
    )
    assert courier_response.status_code == 201
    courier_id = courier_response.json()["id"]

    delivery_response = client.post(
        "/delivery/",
        json={"order_id": order_id, "courier_id": courier_id},
    )
    assert delivery_response.status_code == 201
    delivery_id = delivery_response.json()["id"]

    # Transition through states and collect event count
    expected_statuses = [
        "CONFIRMED",
        "PREPARING",
        "READY_FOR_PICKUP",
        "PICKED_UP",
        "IN_TRANSIT",
        "DELIVERED",
    ]

    for expected_status in expected_statuses:
        response = client.patch(
            f"/delivery/{delivery_id}/status",
            json={"status": expected_status},
        )
        assert response.status_code == 201

    # Get events for order
    events_response = client.get(f"/order/{order_id}/event")
    assert events_response.status_code == 200
    events = events_response.json()
    assert len(events) == 6
    assert events[0]["status"] == "DELIVERED"
    assert events[5]["status"] == "CONFIRMED"
    assert all("id" in event for event in events)
    assert all("updated_at" in event for event in events)
    assert all(event["delivery_id"] == delivery_id for event in events)

    order_response = client.get(f"/order/{order_id}")
    assert order_response.status_code == 200
    order_payload = order_response.json()
    assert order_payload["courier"]["id"] == courier_id
    assert order_payload["courier"]["name"] == "Events Courier"
    assert order_payload["courier"]["vehicle"] == "BIKE"
    assert order_payload["status"] == "DELIVERED"


def test_order_events_without_delivery(client: TestClient) -> None:
    kitchen = _create_kitchen(client, "Portuguese")
    restaurant = _create_restaurant(client, kitchen["id"], "Lisboa")
    user = _create_user(client, "no-delivery@example.com")
    item = _create_item(client, restaurant["id"], "Bacalao", 52.0)

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

    # Get events for order without delivery
    events_response = client.get(f"/order/{order_id}/event")
    assert events_response.status_code == 200
    events = events_response.json()
    assert events == []


def test_order_events_404_for_missing_order(client: TestClient) -> None:
    response = client.get("/order/999/event")
    assert response.status_code == 404


def test_user_orders_include_courier_and_latest_status(client: TestClient) -> None:
    kitchen = _create_kitchen(client, "Moroccan")
    restaurant = _create_restaurant(client, kitchen["id"], "Atlas")
    user = _create_user(client, "user-order-status@example.com")
    item = _create_item(client, restaurant["id"], "Couscous", 41.0)

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

    courier_response = client.post(
        "/courier/",
        json={
            "name": "User Status Courier",
            "vehicle": "CAR",
            "lat": -30.6,
            "lon": -51.6,
        },
    )
    assert courier_response.status_code == 201
    courier_id = courier_response.json()["id"]

    delivery_response = client.post(
        "/delivery/",
        json={"order_id": order_id, "courier_id": courier_id},
    )
    assert delivery_response.status_code == 201
    delivery_id = delivery_response.json()["id"]

    status_response = client.patch(
        f"/delivery/{delivery_id}/status",
        json={"status": "CONFIRMED"},
    )
    assert status_response.status_code == 201

    list_response = client.get(f"/user/{user['id']}/order")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload) == 1
    assert list_payload[0]["id"] == order_id
    assert list_payload[0]["courier"]["id"] == courier_id
    assert list_payload[0]["courier"]["name"] == "User Status Courier"
    assert list_payload[0]["courier"]["vehicle"] == "CAR"
    assert list_payload[0]["status"] == "CONFIRMED"

    get_response = client.get(f"/user/{user['id']}/order/{order_id}")
    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["courier"]["id"] == courier_id
    assert get_payload["courier"]["name"] == "User Status Courier"
    assert get_payload["courier"]["vehicle"] == "CAR"
    assert get_payload["status"] == "CONFIRMED"
