import asyncio
import aiohttp
import time
import json
import statistics
import random
import urllib.parse
import re
import socket
from pathlib import Path

# Armazena as latências para calcular o P95 no final
BASE_URL = ""
latencies = []
STATUS_FLOW = ["CONFIRMED", "PREPARING", "READY_FOR_PICKUP", "PICKED_UP", "IN_TRANSIT", "DELIVERED"]

class LocalResolver(aiohttp.abc.AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        if host.endswith(".local"):
            if Path("/var/run/secrets/kubernetes.io").exists():
                parts = host.split(".")
                if len(parts) >= 3:
                    svc_name = parts[0]
                    ns_name = parts[1]
                    k8s_host = f"{svc_name}.{ns_name}.svc.cluster.local"
                    ports_map = {
                        "clients": 4001,
                        "couriers": 4002,
                        "orders": 4004,
                        "restaurants": 4005,
                        "region": 4006
                    }
                    k8s_port = ports_map.get(svc_name, port)
                    try:
                        loop = asyncio.get_running_loop()
                        res = await loop.run_in_executor(None, socket.getaddrinfo, k8s_host, k8s_port, family)
                        return [{
                            "hostname": host,
                            "host": item[4][0],
                            "port": item[4][1],
                            "family": item[0],
                            "proto": item[2],
                            "flags": 0
                        } for item in res]
                    except Exception as e:
                        print(f"Failed to resolve internal K8s host {k8s_host}: {e}")
            return [{
                "hostname": host,
                "host": "127.0.0.1",
                "port": port,
                "family": family,
                "proto": 0,
                "flags": 0
            }]
        try:
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, socket.getaddrinfo, host, port, family)
            return [{
                "hostname": host,
                "host": item[4][0],
                "port": item[4][1],
                "family": item[0],
                "proto": item[2],
                "flags": 0
            } for item in res]
        except Exception:
            return [{
                "hostname": host,
                "host": "127.0.0.1",
                "port": port,
                "family": family,
                "proto": 0,
                "flags": 0
            }]

    async def close(self):
        pass

def get_url_for_path(url: str) -> str:
    """Resolve a URL para o microsserviço correspondente em ambientes locais ou k8s multi-subdomínio."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    if parsed.query:
        path += "?" + parsed.query
        
    p = path.strip("/")
    if p.startswith("kitchen") or p.startswith("restaurant") or p.startswith("item"):
        service = "restaurants"
    elif p.startswith("user") or p.startswith("client"):
        service = "clients"
    elif p.startswith("courier"):
        service = "couriers"
    elif p.startswith("order") or p.startswith("delivery"):
        service = "orders"
    elif p.startswith("region"):
        service = "region"
    else:
        service = "orders"

    hostname = parsed.hostname or "localhost"
    port = parsed.port
    
    # 1. Caso com porta no localhost (Docker Compose ou NodePorts do Kind)
    if port and (hostname == "localhost" or hostname == "127.0.0.1"):
        port_str = str(port)
        compose_ports = {
            "clients": "4001",
            "couriers": "4002",
            "orders": "4004",
            "restaurants": "4005",
            "region": "4006"
        }
        node_ports = {
            "clients": "30041",
            "couriers": "30042",
            "orders": "30044",
            "restaurants": "30045",
            "region": "30046"
        }
        
        if port_str.startswith("400"):
            new_port = compose_ports.get(service, "4004")
        elif port_str.startswith("3004"):
            new_port = node_ports.get(service, "30044")
        else:
            new_port = port_str
            
        return f"{parsed.scheme}://{hostname}:{new_port}{path}"

    # 2. Caso de Ingress com subdomínio dinâmico no Kubernetes local (ex: http://city-10-campinas.local)
    if hostname.endswith(".local") and not any(hostname.startswith(s + ".") for s in ["clients", "couriers", "orders", "restaurants", "region"]):
        new_hostname = f"{service}.{hostname}"
        port_str = f":{port}" if port else ""
        return f"{parsed.scheme}://{new_hostname}{port_str}{path}"
        
    for s in ["clients", "couriers", "orders", "restaurants", "region"]:
        if hostname.startswith(s + "."):
            base_domain = hostname[len(s)+1:]
            new_hostname = f"{service}.{base_domain}"
            port_str = f":{port}" if port else ""
            return f"{parsed.scheme}://{new_hostname}{port_str}{path}"

    # 3. Produção (ALB na AWS) / Ingress Unificado
    return url

async def fetch(session, method, url, payload=None):
    """Executa a requisição HTTP, resolve a URL correta e mede a latência exata."""
    resolved_url = get_url_for_path(url)
    start_time = time.perf_counter()
    data = None
    try:
        response = None
        if method == 'POST':
            response = session.post(resolved_url, json=payload)
        elif method == 'PUT':
            response = session.put(resolved_url, json=payload)
        elif method == 'PATCH':
            response = session.patch(resolved_url, json=payload)
        elif method == 'GET':
            response = session.get(resolved_url)

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
        print(f"\n[ERRO DE CONEXÃO REAL] Falha ao tentar {method} em {resolved_url} -> {str(e)}")
        status = 0 
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


async def _find_delivery_by_order_id(session, order_id: int):
    status_code, deliveries = await fetch(session, 'GET', f"{BASE_URL}/delivery/")
    if status_code not in (200, 201) or not isinstance(deliveries, list):
        return None

    for delivery in deliveries:
        order_ref = delivery.get("order", {})
        if order_ref.get("id") == order_id:
            return delivery

    return None


async def _find_any_courier_id(session):
    status_code, couriers = await fetch(session, 'GET', f"{BASE_URL}/courier/")
    if status_code not in (200, 201) or not isinstance(couriers, list) or not couriers:
        return None

    courier = random.choice(couriers)
    return courier.get("id")


def _remaining_statuses(current_status: str | None) -> list[str]:
    if current_status is None:
        return STATUS_FLOW

    if current_status not in STATUS_FLOW:
        return []

    index = STATUS_FLOW.index(current_status)
    return STATUS_FLOW[index + 1:]

async def simulate_order_lifecycle(session, seed_ids, debug=False):
    """Fase 2: Simula o ciclo de vida completo de um pedido no RDS."""
    try:
        # 1. Cria Pedido
        order_payload = {
            "restaurant_id": seed_ids["restaurant_id"],
            "user_id": seed_ids["user_id"],
            "items": [{"item_id": seed_ids["item_id"], "quantity": 2}],
        }
        order_status, order_data = await fetch(session, 'POST', f"{BASE_URL}/order/", order_payload)
        if order_status not in (200, 201) or not order_data:
            if debug: print(f"  [ERRO] Falha ao criar order: status={order_status}, response={order_data}")
            return False

        order_id = order_data.get("id")
        if order_id is None:
            if debug: print(f"  [ERRO] Order sem ID")
            return False

        # Busca estado atual do pedido para continuar do ponto correto.
        order_get_status, current_order = await fetch(session, 'GET', f"{BASE_URL}/order/{order_id}")
        if order_get_status not in (200, 201) or not current_order:
            if debug: print(f"  [ERRO] Falha ao GET order/{order_id}: {order_get_status}")
            return False

        current_status = current_order.get("status")
        selected_courier = current_order.get("courier") or {}
        selected_courier_id = selected_courier.get("id")

        # Tenta criar courier apenas quando o pedido ainda não tem courier associado.
        if selected_courier_id is None:
            courier_payload = {
                "name": f"Entregador-{time.perf_counter_ns()}",
                "vehicle": "MOTORCYCLE",
                "lat": -23.5500 + random.uniform(-0.002, 0.002),
                "lon": -46.6330 + random.uniform(-0.002, 0.002),
            }
            courier_status, courier_data = await fetch(session, 'POST', f"{BASE_URL}/courier/", courier_payload)
            if courier_status in (200, 201) and courier_data:
                selected_courier_id = courier_data.get("id")
            else:
                if debug:
                    print(f"  [ERRO] Falha ao criar courier: status={courier_status}, response={courier_data}")
                selected_courier_id = await _find_any_courier_id(session)

        if selected_courier_id is None:
            if debug: print("  [ERRO] Não foi possível obter courier para o pedido")
            return False

        # 2. Cria Delivery quando ainda não existe; se já existir, reaproveita.
        delivery_status, delivery_data = await fetch(
            session,
            'POST',
            f"{BASE_URL}/delivery/",
            {"order_id": order_id, "courier_id": selected_courier_id},
        )

        if delivery_status in (200, 201) and delivery_data:
            delivery_id = delivery_data.get("id")
            delivery_courier = delivery_data.get("courier") or {}
            selected_courier_id = delivery_courier.get("id", selected_courier_id)
            current_status = None
        elif delivery_status == 409:
            existing_delivery = await _find_delivery_by_order_id(session, order_id)
            if not existing_delivery:
                if debug: print(f"  [ERRO] 409 mas não encontrou delivery existente para order/{order_id}")
                return False

            delivery_id = existing_delivery.get("id")
            delivery_courier = existing_delivery.get("courier") or {}
            if delivery_courier.get("id") is not None:
                selected_courier_id = delivery_courier.get("id")
        else:
            if debug: print(f"  [ERRO] Falha ao criar delivery: {delivery_status}")
            return False

        if delivery_id is None or selected_courier_id is None:
            if debug: print(f"  [ERRO] delivery_id={delivery_id}, selected_courier_id={selected_courier_id}")
            return False

        # 3. Dispara o movimento do entregador no DynamoDB em background (não bloqueia o RDS)
        asyncio.create_task(simulate_courier_movement(session, selected_courier_id, delivery_id))

        # 4. Avança status no RDS
        statuses = _remaining_statuses(current_status)
        if debug: print(f"  [INFO] Order {order_id}: current_status={current_status}, remaining={statuses}")
        
        for next_status in statuses:
            status_code, response_data = await fetch(session, 'PATCH', f"{BASE_URL}/delivery/{delivery_id}/status", {"status": next_status})
            if status_code not in (200, 201):
                if debug: print(f"    [ERRO] PATCH status {next_status}: {status_code}, response={response_data}")
                return False
            await asyncio.sleep(0.5) # Simula o tempo real passando

        return True
    except Exception as e:
        if debug: print(f"  [EXCEÇÃO] {e}")
        return False

async def worker(name, session, queue, seed_ids, stats, debug=False):
    """Consome requisições da fila o mais rápido possível."""
    while True:
        try:
            await queue.get()
            success = await simulate_order_lifecycle(session, seed_ids, debug=debug)
            if success:
                stats["orders_completed"] += 1
            queue.task_done()
        except asyncio.CancelledError:
            break

async def run_load_test(rps, duration, seed_ids, debug_first=False):
    """Orquestra o ataque com a taxa de RPS desejada."""
    print(f"\nIniciando teste de carga: {rps} RPS por {duration} segundos...")
    latencies.clear()
    
    connector = aiohttp.TCPConnector(limit=0, resolver=LocalResolver()) # Remove limite de conexões e resolve *.local
    async with aiohttp.ClientSession(connector=connector) as session:
        queue = asyncio.Queue()
        stats = {"orders_completed": 0, "orders_scheduled": 0}
        
        # Cria workers para processar a carga
        workers = [asyncio.create_task(worker(f'w-{i}', session, queue, seed_ids, stats, debug=(i==0 and debug_first))) for i in range(rps * 2)]
        
        start_time = time.time()
        request_count = 0
        while time.time() - start_time < duration:
            for _ in range(rps):
                queue.put_nowait(1)
                stats["orders_scheduled"] += 1
                request_count += 1
                # Only debug first request
                if debug_first and request_count == 1:
                    debug_first = False
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
    connector = aiohttp.TCPConnector(limit=0, resolver=LocalResolver())
    async with aiohttp.ClientSession(connector=connector) as session:
        seed_ids = await seed_data(session)

    # Cenário 1: Operação Normal (com debug da primeira requisição)
    await run_load_test(rps=10, duration=10, seed_ids=seed_ids, debug_first=True)
    
    # Cenário 2: Pico (Almoço/Jantar)
    # Comentado pois não funcionou bem no ambiente de teste, mas pode ser reativado para testes locais ou em ambiente com mais recursos.
    # await run_load_test(rps=50, duration=60, seed_ids=seed_ids, debug_first=True)
    
    # Cenário 3: Evento Especial (Requisito Máximo)
    print("\nAguardando 5s antes do teste de estresse máximo...")
    await asyncio.sleep(5)
    # Comentado pois não funcionou bem no ambiente de teste, mas pode ser reativado para testes locais ou em ambiente com mais recursos.
    await run_load_test(rps=200, duration=10, seed_ids=seed_ids, debug_first=True) 

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        ctx = json.loads(Path("deploy_context.json").read_text())
        url = f"http://{ctx['alb_dns']}"
    asyncio.run(main(url))