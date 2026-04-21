import asyncio
import aiohttp
import time
import json
import statistics
import random
from pathlib import Path

# Armazena as latências para calcular o P95 no final
BASE_URL = ""
latencies = []

async def fetch(session, method, url, payload=None):
    """Executa a requisição HTTP e mede a latência exata."""
    start_time = time.perf_counter()
    data = None
    try:
        response = None
        if method == 'POST':
            response = session.post(url, json=payload)
        elif method == 'PUT':
            response = session.put(url, json=payload)
        elif method == 'PATCH':
            response = session.patch(url, json=payload)
        elif method == 'GET':
            response = session.get(url)

        if response is None:
            raise ValueError(f"Unsupported method: {method}")

        async with response as req_response:
            raw = await req_response.text()
            status = req_response.status

            if raw:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = None
    except Exception as e:
        status = 500
        data = None

    end_time = time.perf_counter()
    latency_ms = (end_time - start_time) * 1000
    latencies.append(latency_ms)
    return status, data

async def seed_data(session):
    """Fase 1: Popula o RDS com dados iniciais antes do teste."""
    print("Semeando dados iniciais...")
    
    # 1. Cozinha e Restaurante
    kitchen_status, kitchen_data = await fetch(session, 'POST', f"{BASE_URL}/kitchen/", {"type": "Italiana"})
    kitchen_id = kitchen_data.get("id", 1) if kitchen_status in (200, 201) and kitchen_data else 1

    restaurant_status, restaurant_data = await fetch(session, 'POST', f"{BASE_URL}/restaurant/", {
        "name": "Dijkstra Pasta", "lat": -23.5505, "lon": -46.6333, "kitchen_type_id": kitchen_id
    })
    restaurant_id = restaurant_data.get("id", 1) if restaurant_status in (200, 201) and restaurant_data else 1
    
    # 2. Item
    item_status, item_data = await fetch(session, 'POST', f"{BASE_URL}/item/", {
        "name": "Spaghetti O(V+E)", "price": 45.50, "restaurant_id": restaurant_id
    })
    item_id = item_data.get("id", 1) if item_status in (200, 201) and item_data else 1
    
    # 3. Usuário e Entregador
    user_status, user_data = await fetch(session, 'POST', f"{BASE_URL}/user", {
        "name": "Cliente Teste", "email": "cliente@fgv.br", "house_lat": -23.5510, "house_lon": -46.6340, "phones": ["11999999999"]
    })
    user_id = user_data.get("id", 1) if user_status in (200, 201) and user_data else 1

    print("Seed concluído.")

    return {
        "kitchen_id": kitchen_id,
        "restaurant_id": restaurant_id,
        "item_id": item_id,
        "user_id": user_id,
    }

async def simulate_courier_movement(session, courier_id, delivery_id):
    """Simula o entregador enviando posição a cada 100ms para o DynamoDB."""
    for _ in range(10): # Envia 10 atualizações rápidas por pedido
        payload = {
            "delivery_id": str(delivery_id),
            "lat_courier": -23.5505 + (random.uniform(-0.001, 0.001)),
            "lon_courier": -46.6333 + (random.uniform(-0.001, 0.001))
        }
        await fetch(session, 'PUT', f"{BASE_URL}/courier/{courier_id}/position", payload)
        await asyncio.sleep(0.1) # Requisito: 100ms

async def simulate_order_lifecycle(session, seed_ids):
    """Fase 2: Simula o ciclo de vida completo de um pedido no RDS."""
    # 1. Cria Pedido
    order_payload = {
        "restaurant_id": seed_ids["restaurant_id"],
        "user_id": seed_ids["user_id"],
        "items": [{"item_id": seed_ids["item_id"], "quantity": 2}],
    }
    order_status, order_data = await fetch(session, 'POST', f"{BASE_URL}/order/", order_payload)
    if order_status not in (200, 201) or not order_data:
        return False

    order_id = order_data.get("id")
    if order_id is None:
        return False

    courier_payload = {
        "name": f"Entregador-{time.perf_counter_ns()}",
        "vehicle": "MOTORCYCLE",
        "lat": -23.5500 + random.uniform(-0.002, 0.002),
        "lon": -46.6330 + random.uniform(-0.002, 0.002),
    }
    courier_status, courier_data = await fetch(session, 'POST', f"{BASE_URL}/courier/", courier_payload)
    if courier_status not in (200, 201) or not courier_data:
        return False

    courier_id = courier_data.get("id")
    if courier_id is None:
        return False
    
    # 2. Cria Delivery
    delivery_status, delivery_data = await fetch(session, 'POST', f"{BASE_URL}/delivery/", {"order_id": order_id, "courier_id": courier_id})
    if delivery_status not in (200, 201) or not delivery_data:
        return False

    delivery_id = delivery_data.get("id")
    if delivery_id is None:
        return False

    # 3. Dispara o movimento do entregador no DynamoDB em background (não bloqueia o RDS)
    asyncio.create_task(simulate_courier_movement(session, courier_id, delivery_id))

    # 4. Avança status no RDS
    statuses = ["CONFIRMED", "PREPARING", "READY_FOR_PICKUP", "PICKED_UP", "IN_TRANSIT", "DELIVERED"]
    for delivery_status in statuses:
        status_code, _ = await fetch(session, 'PATCH', f"{BASE_URL}/delivery/{delivery_id}/status", {"status": delivery_status})
        if status_code not in (200, 201):
            return False
        await asyncio.sleep(0.5) # Simula o tempo real passando

    return True

async def worker(name, session, queue, seed_ids, stats):
    """Consome requisições da fila o mais rápido possível."""
    while True:
        try:
            await queue.get()
            success = await simulate_order_lifecycle(session, seed_ids)
            if success:
                stats["orders_completed"] += 1
            queue.task_done()
        except asyncio.CancelledError:
            break

async def run_load_test(rps, duration):
    """Orquestra o ataque com a taxa de RPS desejada."""
    print(f"\nIniciando teste de carga: {rps} RPS por {duration} segundos...")
    latencies.clear()
    
    connector = aiohttp.TCPConnector(limit=0) # Remove limite de conexões
    async with aiohttp.ClientSession(connector=connector) as session:
        seed_ids = {}
        # Se for o primeiro teste, faz o seed
        if rps == 10:
            seed_ids = await seed_data(session)
        else:
            # Fallback caso o teste seja executado isoladamente.
            seed_ids = {
                "restaurant_id": 1,
                "user_id": 1,
                "item_id": 1,
            }
            
        queue = asyncio.Queue()
        stats = {"orders_completed": 0, "orders_scheduled": 0}
        
        # Cria workers para processar a carga
        workers = [asyncio.create_task(worker(f'w-{i}', session, queue, seed_ids, stats)) for i in range(rps * 2)]
        
        start_time = time.time()
        while time.time() - start_time < duration:
            for _ in range(rps):
                queue.put_nowait(1)
                stats["orders_scheduled"] += 1
            await asyncio.sleep(1) # Aguarda 1 segundo e injeta mais carga
            
        await queue.join()
        elapsed_seconds = max(time.time() - start_time, 1e-9)
        
        for w in workers:
            w.cancel()

        if latencies:
            p95 = statistics.quantiles(latencies, n=100)[94]
            avg = statistics.mean(latencies)
            print(f"Resultados para {rps} RPS:")
            print(f"Total de Requisições: {len(latencies)}")
            print(f"Latência Média: {avg:.2f} ms")
            print(f"Latência P95: {p95:.2f} ms")
            print(f"Pedidos agendados: {stats['orders_scheduled']}")
            print(f"Pedidos completos: {stats['orders_completed']}")
            print(f"Throughput efetivo de pedidos: {stats['orders_completed'] / elapsed_seconds:.2f} pedidos/s")
            
            if p95 < 500:
                print("SUCESSO: P95 abaixo de 500ms!")
            else:
                print("AVISO: P95 acima de 500ms. ECS pode estar precisando de mais containers.")

async def main(url: str):
    global BASE_URL
    BASE_URL = url
    
    print("--- DijkFood Load Simulator ---")
    # Cenário 1: Operação Normal
    await run_load_test(rps=10, duration=10)
    
    # Cenário 2: Pico (Almoço/Jantar)
    await run_load_test(rps=50, duration=10)
    
    # Cenário 3: Evento Especial (Requisito Máximo)
    print("\nAguardando 5s antes do teste de estresse máximo...")
    await asyncio.sleep(5)
    await run_load_test(rps=200, duration=10)

if __name__ == "__main__":
    # Fallback se rodar o simulador solto
    ctx = json.loads(Path("deploy_context.json").read_text())
    asyncio.run(main(f"http://{ctx['alb_dns']}"))