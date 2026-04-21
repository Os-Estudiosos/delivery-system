import asyncio
import aiohttp
import time
import json
import statistics
from pathlib import Path

# Configurações Base
CTX_FILE = Path("deploy_context.json")
try:
    ctx = json.loads(CTX_FILE.read_text())
    BASE_URL = f"http://{ctx['alb_dns']}"
except Exception:
    print("Erro: deploy_context.json não encontrado. Rode o deploy.py primeiro.")
    exit(1)

# Armazena as latências para calcular o P95 no final
latencies = []

async def fetch(session, method, url, payload=None):
    """Executa a requisição HTTP e mede a latência exata."""
    start_time = time.perf_counter()
    try:
        if method == 'POST':
            async with session.post(url, json=payload) as response:
                await response.read()
                status = response.status
        elif method == 'PUT':
            async with session.put(url, json=payload) as response:
                await response.read()
                status = response.status
        elif method == 'PATCH':
            async with session.patch(url, json=payload) as response:
                await response.read()
                status = response.status
    except Exception as e:
        status = 500

    end_time = time.perf_counter()
    latency_ms = (end_time - start_time) * 1000
    latencies.append(latency_ms)
    return status

async def seed_data(session):
    """Fase 1: Popula o RDS com dados iniciais antes do teste."""
    print("🌱 Semeando dados iniciais...")
    
    # 1. Cozinha e Restaurante
    await fetch(session, 'POST', f"{BASE_URL}/kitchen/", {"type": "Italiana"})
    await fetch(session, 'POST', f"{BASE_URL}/restaurant/", {
        "name": "Dijkstra Pasta", "lat": -23.5505, "lon": -46.6333, "kitchen_type_id": 1
    })
    
    # 2. Item
    await fetch(session, 'POST', f"{BASE_URL}/item/", {
        "name": "Spaghetti O(V+E)", "price": 45.50, "restaurant_id": 1
    })
    
    # 3. Usuário e Entregador
    await fetch(session, 'POST', f"{BASE_URL}/user/user", {
        "name": "Cliente Teste", "email": "cliente@fgv.br", "house_lat": -23.5510, "house_lon": -46.6340, "phones": ["11999999999"]
    })
    await fetch(session, 'POST', f"{BASE_URL}/courier/", {
        "name": "Entregador Veloz", "vehicle": "MOTORCYCLE", "lat": -23.5500, "lon": -46.6330
    })
    print("✅ Seed concluído.")

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

async def simulate_order_lifecycle(session):
    """Fase 2: Simula o ciclo de vida completo de um pedido no RDS."""
    # 1. Cria Pedido
    order_payload = {"restaurant_id": 1, "user_id": 1, "items": [{"item_id": 1, "quantity": 2}]}
    await fetch(session, 'POST', f"{BASE_URL}/order/", order_payload)
    
    # Para simplificar o ID neste script de stress, assumimos IDs fixos do seed para simulação rápida
    order_id = 1 
    courier_id = 1
    
    # 2. Cria Delivery
    await fetch(session, 'POST', f"{BASE_URL}/delivery/", {"order_id": order_id, "courier_id": courier_id})
    delivery_id = 1

    # 3. Dispara o movimento do entregador no DynamoDB em background (não bloqueia o RDS)
    asyncio.create_task(simulate_courier_movement(session, courier_id, delivery_id))

    # 4. Avança status no RDS
    statuses = ["PREPARING", "READY_FOR_PICKUP", "PICKED_UP", "IN_TRANSIT", "DELIVERED"]
    for status in statuses:
        await fetch(session, 'PATCH', f"{BASE_URL}/delivery/{delivery_id}/status", {"status": status})
        await asyncio.sleep(0.5) # Simula o tempo real passando

async def worker(name, session, queue):
    """Consome requisições da fila o mais rápido possível."""
    while True:
        try:
            await queue.get()
            await simulate_order_lifecycle(session)
            queue.task_done()
        except asyncio.CancelledError:
            break

async def run_load_test(rps, duration):
    """Orquestra o ataque com a taxa de RPS desejada."""
    print(f"\n🚀 Iniciando teste de carga: {rps} RPS por {duration} segundos...")
    latencies.clear()
    
    connector = aiohttp.TCPConnector(limit=0) # Remove limite de conexões
    async with aiohttp.ClientSession(connector=connector) as session:
        # Se for o primeiro teste, faz o seed
        if rps == 10:
            await seed_data(session)
            
        queue = asyncio.Queue()
        
        # Cria workers para processar a carga
        workers = [asyncio.create_task(worker(f'w-{i}', session, queue)) for i in range(rps * 2)]
        
        start_time = time.time()
        while time.time() - start_time < duration:
            for _ in range(rps):
                queue.put_nowait(1)
            await asyncio.sleep(1) # Aguarda 1 segundo e injeta mais carga
            
        await queue.join()
        
        for w in workers:
            w.cancel()

        if latencies:
            p95 = statistics.quantiles(latencies, n=100)[94]
            avg = statistics.mean(latencies)
            print(f"📊 Resultados para {rps} RPS:")
            print(f"   Total de Requisições: {len(latencies)}")
            print(f"   Latência Média: {avg:.2f} ms")
            print(f"   Latência P95: {p95:.2f} ms")
            
            if p95 < 500:
                print("   ✅ SUCESSO: P95 abaixo de 500ms!")
            else:
                print("   ⚠️ AVISO: P95 acima de 500ms. ECS pode estar precisando de mais containers.")

import random
async def main():
    print("--- DijkFood Load Simulator ---")
    # Cenário 1: Operação Normal
    await run_load_test(rps=10, duration=10)
    
    # Cenário 2: Pico (Almoço/Jantar)
    await run_load_test(rps=50, duration=10)
    
    # Cenário 3: Evento Especial (Requisito Máximo)
    # Aguarda um pouco para o ECS escalar se necessário
    print("\nAguardando 5s antes do teste de estresse máximo...")
    time.sleep(5)
    await run_load_test(rps=200, duration=10)

if __name__ == "__main__":
    asyncio.run(main())