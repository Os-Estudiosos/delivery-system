import os
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
CITY_NAMESPACE = ""  # Namespace K8s da cidade ativa (ex: city-2-russas-cear-brazil)
latencies = []
# STATUS_FLOW: estados que o simulador avança via PATCH /delivery/{id}/status.
STATUS_FLOW = ["CONFIRMED", "PREPARING", "READY_FOR_PICKUP", "PICKED_UP", "IN_TRANSIT", "DELIVERED"]

background_tasks = set()

# Coordenadas de fallback: Russas, Ceará, Brazil (cidade padrão de deploy)
# Em produção, as coords são geocodificadas dinamicamente a partir do nome da região.
_FALLBACK_LAT = -4.9416
_FALLBACK_LON = -37.9725

class LocalResolver(aiohttp.abc.AbstractResolver):
    def __init__(self):
        self._cache = {}

    async def resolve(self, host, port=0, family=socket.AF_INET):
        cache_key = (host, port, family)
        if cache_key in self._cache:
            return self._cache[cache_key]

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
                        resolved = [{
                            "hostname": host,
                            "host": item[4][0],
                            "port": item[4][1],
                            "family": item[0],
                            "proto": item[2],
                            "flags": 0
                        } for item in res]
                        self._cache[cache_key] = resolved
                        return resolved
                    except Exception as e:
                        print(f"Failed to resolve internal K8s host {k8s_host}: {e}")
            resolved = [{
                "hostname": host,
                "host": "127.0.0.1",
                "port": port,
                "family": family,
                "proto": 0,
                "flags": 0
            }]
            self._cache[cache_key] = resolved
            return resolved
        try:
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, socket.getaddrinfo, host, port, family)
            resolved = [{
                "hostname": host,
                "host": item[4][0],
                "port": item[4][1],
                "family": item[0],
                "proto": item[2],
                "flags": 0
            } for item in res]
            self._cache[cache_key] = resolved
            return resolved
        except Exception:
            resolved = [{
                "hostname": host,
                "host": "127.0.0.1",
                "port": port,
                "family": family,
                "proto": 0,
                "flags": 0
            }]
            self._cache[cache_key] = resolved
            return resolved

    async def close(self):
        pass

def _get_service_for_path(path: str) -> str:
    """Determina o microsserviço responsável com base no path da requisição."""
    p = path.strip("/")
    if p.startswith("kitchen") or p.startswith("restaurant") or p.startswith("item"):
        return "restaurants"
    elif p.startswith("user") or p.startswith("client"):
        return "clients"
    elif p.startswith("courier"):
        return "couriers"
    elif p.startswith("order") or p.startswith("delivery"):
        return "orders"
    elif p.startswith("region"):
        return "region"
    return "orders"


def get_url_and_host(url: str) -> tuple[str, str | None]:
    """Resolve a URL real e o header Host virtual para o microsserviço.
    Retorna (url_destino, host_header).
    - host_header=None significa usar o Host padrão (sem override).
    - Para AWS ALB com Ingress host-based, retorna o host virtual do serviço.
    """
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    if parsed.query:
        path += "?" + parsed.query

    service = _get_service_for_path(path)
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
        return f"{parsed.scheme}://{hostname}:{new_port}{path}", None

    # 2. Caso de Ingress com subdomínio dinâmico no Kubernetes local (ex: http://city-10-campinas.local)
    if hostname.endswith(".local") and not any(hostname.startswith(s + ".") for s in ["clients", "couriers", "orders", "restaurants", "region"]):
        new_hostname = f"{service}.{hostname}"
        port_str = f":{port}" if port else ""
        return f"{parsed.scheme}://{new_hostname}{port_str}{path}", None

    for s in ["clients", "couriers", "orders", "restaurants", "region"]:
        if hostname.startswith(s + "."):
            base_domain = hostname[len(s)+1:]
            new_hostname = f"{service}.{base_domain}"
            port_str = f":{port}" if port else ""
            return f"{parsed.scheme}://{new_hostname}{port_str}{path}", None

    # 3. Produção: ALB na AWS com Ingress nginx host-based routing.
    # O ALB encaminha pelo header Host. Precisamos enviar o Host virtual correto
    # (ex: orders.city-2-russas-cear-brazil.local) enquanto conectamos ao IP do ALB.
    if CITY_NAMESPACE:
        # Serviço do namespace da cidade
        if service in ("clients", "couriers", "orders", "restaurants", "region"):
            virtual_host = f"{service}.{CITY_NAMESPACE}.local"
        else:
            virtual_host = f"{service}.admin-namespace.local"
    else:
        # Fallback: admin namespace
        if service == "region":
            virtual_host = f"region.admin-namespace.local"
        else:
            virtual_host = f"{service}.admin-namespace.local"

    return url, virtual_host


def get_url_for_path(url: str) -> str:
    """Compatibilidade retroativa — retorna apenas a URL destino."""
    resolved_url, _ = get_url_and_host(url)
    return resolved_url

async def fetch(session, method, url, payload=None):
    """Executa a requisição HTTP, resolve a URL correta e mede a latência exata.
    Quando o Ingress usa host-based routing (AWS ALB), injeta o header Host virtual.
    """
    resolved_url, virtual_host = get_url_and_host(url)
    headers = {"Host": virtual_host} if virtual_host else {}
    start_time = time.perf_counter()
    data = None
    try:
        response = None
        if method == 'POST':
            response = session.post(resolved_url, json=payload, headers=headers)
        elif method == 'PUT':
            response = session.put(resolved_url, json=payload, headers=headers)
        elif method == 'PATCH':
            response = session.patch(resolved_url, json=payload, headers=headers)
        elif method == 'GET':
            response = session.get(resolved_url, headers=headers)

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
        error_msg = str(e)
        if not error_msg:
            error_msg = "Timeout (O serviço demorou mais que o limite para responder)"
        
        # Avoid printing thousands of errors
        if not hasattr(fetch, "error_count"):
            fetch.error_count = 0
        fetch.error_count += 1
        
        if fetch.error_count <= 5:
            print(f"\n[ERRO DE CONEXÃO REAL] Falha ao tentar {method} em {resolved_url} (Host: {virtual_host}) -> {error_msg}")
        elif fetch.error_count == 6:
            print(f"\n[ERRO DE CONEXÃO REAL] (Silenciando próximos erros idênticos de timeout/conexão para não floodar a tela...)")
            
        status = 0
        data = None

    end_time = time.perf_counter()
    latency_ms = (end_time - start_time) * 1000
    latencies.append(latency_ms)
    return status, data

async def _discover_region(session) -> tuple[int, str]:
    """Descobre o region_id e o nome da cidade ativa consultando a API.
    Aguarda até a região existir (o admin-service pode demorar para criar via K8s).
    Retorna (region_id, city_name).
    """
    parsed = urllib.parse.urlparse(BASE_URL)
    hostname = parsed.hostname or ""
    target_region_id = None
    if hostname.startswith("city-"):
        parts = hostname.split("-")
        if len(parts) > 1 and parts[1].isdigit():
            target_region_id = int(parts[1])

    for attempt in range(20):
        status_code, regions = await fetch(session, 'GET', f"{BASE_URL}/region/")
        if status_code in (200, 201) and isinstance(regions, list) and regions:
            if target_region_id is not None:
                for r in regions:
                    if r.get("id") == target_region_id:
                        region_id = r.get("id")
                        city_name = r.get("name", "")
                        print(f"[Seed] Região correspondente encontrada: id={region_id}, name='{city_name}'")
                        return region_id, city_name
            first = regions[0]
            region_id = first.get("id", 1)
            city_name = first.get("name", "")
            print(f"[Seed] Região padrão encontrada: id={region_id}, name='{city_name}'")
            return region_id, city_name
        print(f"[Seed] Aguardando região disponível... (tentativa {attempt + 1}/20)")
        await asyncio.sleep(3)
    print("[Seed] AVISO: nenhuma região encontrada após 20 tentativas. Usando fallback Russas/CE.")
    return 1, "Russas, Ceará, Brazil"


async def _geocode_city_center(city_name: str) -> tuple[float, float]:
    """Geocodifica o nome da cidade usando a API pública do Nominatim (OpenStreetMap).
    Retorna (lat, lon) do centroide da cidade.
    Fallback para Russas/CE se o Nominatim não responder ou não encontrar.
    """
    if not city_name:
        return _FALLBACK_LAT, _FALLBACK_LON

    # Hardcoded coordinates for major cities to bypass external Nominatim queries and rate-limiting
    city_lower = city_name.lower()
    if "são paulo" in city_lower or "sao paulo" in city_lower:
        print(f"[Seed] Usando coordenadas estáticas para São Paulo: lat=-23.5505, lon=-46.6333")
        return -23.5505, -46.6333
    elif "russas" in city_lower:
        print(f"[Seed] Usando coordenadas estáticas para Russas: lat=-4.9416, lon=-37.9725")
        return -4.9416, -37.9725

    try:
        encoded = urllib.parse.quote(city_name)
        url = f"https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as geo_session:
            async with geo_session.get(url, headers={"User-Agent": "DijkFood-Simulator/1.0"}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        lat = float(data[0]["lat"])
                        lon = float(data[0]["lon"])
                        print(f"[Seed] Geocodificação OK: '{city_name}' → lat={lat:.4f}, lon={lon:.4f}")
                        return lat, lon
                    else:
                        print(f"[Seed] Nominatim não retornou resultados para '{city_name}'. Usando fallback.")
    except Exception as e:
        print(f"[Seed] Falha na geocodificação de '{city_name}': {e}. Usando fallback.")

    return _FALLBACK_LAT, _FALLBACK_LON


async def seed_data(session):
    """Fase 1: Popula o RDS com dados iniciais antes do teste."""
    global CITY_NAMESPACE
    print("Semeando dados iniciais...")

    # 0. Descobre o namespace da cidade para host-based routing no ALB.
    # Prioridade: deploy_context.json (gerado pelo deploy.py) > kubectl subprocess > fallback.
    if not CITY_NAMESPACE:
        try:
            ctx = json.loads(Path("deploy_context.json").read_text())
            ns = ctx.get("city_namespace", "")
            if ns.startswith("city-"):
                CITY_NAMESPACE = ns
                print(f"[Seed] Namespace lido do deploy_context.json: {CITY_NAMESPACE}")
        except Exception as e:
            print(f"[Seed] Não foi possível ler deploy_context.json: {e}")

    if not CITY_NAMESPACE:
        # Fallback: tenta via kubectl subprocess
        try:
            import subprocess
            result = subprocess.run(
                ["kubectl", "get", "ingress", "-A", "-o",
                 "jsonpath={range .items[*]}{.metadata.namespace}{'\\n'}{end}"],
                capture_output=True, text=True, timeout=10
            )
            namespaces = [ns.strip() for ns in result.stdout.splitlines() if ns.strip().startswith("city-")]
            if namespaces:
                CITY_NAMESPACE = namespaces[0]
                print(f"[Seed] Namespace detectado via kubectl: {CITY_NAMESPACE}")
        except Exception as e:
            print(f"[Seed] kubectl também falhou: {e}")

    if not CITY_NAMESPACE:
        print("[Seed] AVISO: namespace não detectado. Header Host usará admin-namespace como fallback.")
    else:
        print(f"[Seed] Usando namespace '{CITY_NAMESPACE}' para host-based routing.")

    # 1. Descobre region_id e nome da cidade ativos na API
    region_id, city_name = await _discover_region(session)

    # 1. Geocodifica o centro geográfico da cidade (via Nominatim / OSM)
    #    Isso garante que restaurante, usuário e entregadores estejam DENTRO
    #    do grafo viário daquela cidade, independente de qual cidade for registrada.
    city_lat, city_lon = await _geocode_city_center(city_name)

    # 2. Cozinha
    kitchen_status, kitchen_data = await fetch(session, 'POST', f"{BASE_URL}/kitchen/", {"type": "Variada"})
    kitchen_id = kitchen_data.get("id", 1) if kitchen_status in (200, 201) and kitchen_data else 1

    restaurant_names = [
        "Dijkstra Pasta", "Prim Pizza", "Kruskal Burger", "Bellman Bistro",
        "Floyd Grill", "Turing Tacos", "Lovelace Lasagna", "Knuth Kabob"
    ]
    item_names = [
        "Spaghetti O(V+E)", "Pizza Graph-Marguerita", "MST Double Burger", "Shortest Path Steak",
        "Matrix Ribs", "Halting Quesadilla", "Ada Lasagna Special", "B-Tree Beef"
    ]
    
    restaurant_ids = []
    item_ids = []
    
    for i, name in enumerate(restaurant_names):
        restaurant_status, restaurant_data = await fetch(session, 'POST', f"{BASE_URL}/restaurant/", {
            "name": name,
            "lat": city_lat + random.uniform(-0.008, 0.008),
            "lon": city_lon + random.uniform(-0.008, 0.008),
            "kitchen_type_id": kitchen_id,
        })
        r_id = restaurant_data.get("id", i+1) if restaurant_status in (200, 201) and restaurant_data else i+1
        restaurant_ids.append(r_id)
        
        item_status, item_data = await fetch(session, 'POST', f"{BASE_URL}/item/", {
            "name": item_names[i], "price": random.uniform(25.0, 75.0), "restaurant_id": r_id
        })
        it_id = item_data.get("id", i+1) if item_status in (200, 201) and item_data else i+1
        item_ids.append(it_id)

    # 4. Usuário — casa a ~500m do restaurante principal
    user_status, user_data = await fetch(session, 'POST', f"{BASE_URL}/user", {
        "name": "Cliente Teste",
        "email": "cliente@dijkfood.br",
        "house_lat": city_lat + 0.005,
        "house_lon": city_lon + 0.005,
        "phones": ["88999999999"],
    })
    user_id = user_data.get("id", 1) if user_status in (200, 201) and user_data else 1

    # 5. Pré-cria pool de entregadores espalhados pela cidade ativa
    #    Requisito: proporção 3 entregadores : 1 cliente. 60 garante cobertura até 50 RPS.
    #    Raio de ±0.015° ≈ ±1,5 km — entregadores distribuídos dentro da cidade.
    NUM_COURIERS = 60
    print(f"[Seed] Criando {NUM_COURIERS} entregadores em '{city_name}' (region_id={region_id})...")
    courier_ids = []
    for i in range(NUM_COURIERS):
        c_status, c_data = await fetch(session, 'POST', f"{BASE_URL}/courier/", {
            "name": f"Entregador-Seed-{i+1}",
            "vehicle": "MOTORCYCLE",
            "lat": city_lat + random.uniform(-0.015, 0.015),
            "lon": city_lon + random.uniform(-0.015, 0.015),
        })
        if c_status in (200, 201) and c_data:
            courier_ids.append(c_data.get("id"))
    print(f"[Seed] {len(courier_ids)} entregadores criados com sucesso.")

    print("Seed concluído.")

    return {
        "kitchen_id": kitchen_id,
        "restaurant_ids": restaurant_ids,
        "item_ids": item_ids,
        "user_id": user_id,
        "region_id": region_id,
        "city_lat": city_lat,
        "city_lon": city_lon,
        "city_name": city_name,
    }

async def simulate_courier_movement(session, courier_id, delivery_id, city_lat: float, city_lon: float):
    """Simula o entregador enviando posição GPS a cada 100ms para o DynamoDB.
    As coordenadas são geradas em torno do centro da cidade ativa (geocodificado no seed).
    Raio de ±0.010° ≈ ±1 km, representando movimento real de entrega.
    """
    for _ in range(10):  # Envia 10 atualizações rápidas por pedido (100ms cada)
        payload = {
            "delivery_id": str(delivery_id),
            "lat_courier": city_lat + random.uniform(-0.010, 0.010),
            "lon_courier": city_lon + random.uniform(-0.010, 0.010),
        }
        await fetch(session, 'PUT', f"{BASE_URL}/courier/{courier_id}/position", payload)
        await asyncio.sleep(0.1)  # Requisito: 100ms


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
    region_id = seed_ids.get("region_id", 1)
    try:
        # 1. Cria Pedido — o matching-service já encontra o melhor entregador via Dijkstra
        # Choose a random restaurant and its corresponding item from the seed pool
        restaurant_ids = seed_ids.get("restaurant_ids", [seed_ids.get("restaurant_id", 1)])
        item_ids = seed_ids.get("item_ids", [seed_ids.get("item_id", 1)])
        idx = random.randint(0, len(restaurant_ids) - 1)
        r_id = restaurant_ids[idx]
        it_id = item_ids[idx]

        order_payload = {
            "restaurant_id": r_id,
            "user_id": seed_ids["user_id"],
            "items": [{"item_id": it_id, "quantity": random.randint(1, 4)}],
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

        # Se o matching-service não encontrou entregador (pool esgotado), cria um novo
        # com coordenadas da cidade ativa e region_id correto.
        if selected_courier_id is None:
            c_lat = seed_ids.get("city_lat", _FALLBACK_LAT)
            c_lon = seed_ids.get("city_lon", _FALLBACK_LON)
            courier_payload = {
                "name": f"Entregador-{time.perf_counter_ns()}",
                "vehicle": "MOTORCYCLE",
                "lat": c_lat + random.uniform(-0.010, 0.010),
                "lon": c_lon + random.uniform(-0.010, 0.010),
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
        c_lat = seed_ids.get("city_lat", _FALLBACK_LAT)
        c_lon = seed_ids.get("city_lon", _FALLBACK_LON)
        task = asyncio.create_task(simulate_courier_movement(session, selected_courier_id, delivery_id, c_lat, c_lon))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

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
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
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
            
        # Ignora o backlog da fila para terminar exatamente no tempo previsto.
        # Um stress test real (ex: wrk/hey) não espera a fila esvaziar.
        
        elapsed_seconds = max(time.time() - start_time, 1e-9)
        
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        current_bg_tasks = list(background_tasks)
        for t in current_bg_tasks:
            t.cancel()
        if current_bg_tasks:
            await asyncio.gather(*current_bg_tasks, return_exceptions=True)
        background_tasks.clear()

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

async def main(url: str, rps: int = None, duration: int = None):
    global BASE_URL, CITY_NAMESPACE
    BASE_URL = url
    CITY_NAMESPACE = os.environ.get("CITY_NAMESPACE", "")

    print("--- DijkFood Load Simulator ---")
    connector = aiohttp.TCPConnector(limit=0, resolver=LocalResolver())
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        seed_ids = await seed_data(session)
    is_quick = os.environ.get("QUICK_TEST") == "true"
    
    if is_quick or rps is not None or duration is not None:
        target_rps = rps if rps is not None else 10
        target_duration = duration if duration is not None else 15
        print(f"[Quick/Custom Mode] Running only a single load test: {target_rps} RPS for {target_duration} seconds.")
        await run_load_test(rps=target_rps, duration=target_duration, seed_ids=seed_ids, debug_first=False)
        return

    # Cenário 1: Operação Normal (silenciado para não floodar)
    await run_load_test(rps=10, duration=10, seed_ids=seed_ids, debug_first=False)
    
    # Cenário 2: Pico (Almoço/Jantar)
    print("\nIniciando teste de pico intermediário: 50 RPS por 180 segundos (3 Minutos)...")
    await run_load_test(rps=50, duration=180, seed_ids=seed_ids, debug_first=False)
    
    # Warm-up (100 RPS)
    print("\n[Warm-up] Subindo para 100 RPS por 120 segundos para permitir que o HPA e o Cluster Autoscaler preparem as EC2s...")
    await run_load_test(rps=100, duration=120, seed_ids=seed_ids, debug_first=False)

    # Warm-up (150 RPS)
    print("\n[Warm-up] Subindo para 150 RPS por 120 segundos...")
    await run_load_test(rps=150, duration=120, seed_ids=seed_ids, debug_first=False)

    # Cenário 3: Evento Especial (Requisito Máximo)
    print("\nAguardando 5s antes do teste de estresse máximo (200 RPS)...")
    await asyncio.sleep(5)
    
    async def simulate_driver_influx():
        """Simula adição repentina de motoristas (Escassez/Saturação) no meio do teste"""
        await asyncio.sleep(15) # Espera 15s de carga rolando
        print("\n[Simulação Regional] INJETANDO 30 NOVOS ENTREGADORES NO GRAFO PARA ALIVIAR CARGA...")
        connector = aiohttp.TCPConnector(limit=0, resolver=LocalResolver())
        async with aiohttp.ClientSession(connector=connector) as local_session:
            city_lat = seed_ids.get("city_lat", _FALLBACK_LAT)
            city_lon = seed_ids.get("city_lon", _FALLBACK_LON)
            region_id = seed_ids.get("region_id", 1)
            for i in range(30):
                await fetch(local_session, "POST", f"{BASE_URL}/courier/", {
                    "name": f"Rescue Driver {i}",
                    "vehicle": "MOTORCYCLE",
                    "lat": city_lat + random.uniform(-0.015, 0.015),
                    "lon": city_lon + random.uniform(-0.015, 0.015)
                })
        print("[Simulação Regional] 30 motoristas de resgate adicionados!")

    influx_task = asyncio.create_task(simulate_driver_influx())
    
    print("\nIniciando Teste Final: 200 RPS por 180 Segundos (3 Minutos) com Cluster preparado!")
    await run_load_test(rps=200, duration=180, seed_ids=seed_ids, debug_first=False) 
    
    await influx_task


if __name__ == "__main__":
    import sys
    url = None
    rps = None
    duration = None
    
    if len(sys.argv) > 1:
        if not sys.argv[1].startswith("-"):
            url = sys.argv[1]
            
    for i in range(1, len(sys.argv)):
        if sys.argv[i] == "--rps" and i + 1 < len(sys.argv):
            try:
                rps = int(sys.argv[i + 1])
            except ValueError:
                pass
        elif sys.argv[i] == "--duration" and i + 1 < len(sys.argv):
            try:
                duration = int(sys.argv[i + 1])
            except ValueError:
                pass
                
    if not url:
        try:
            ctx = json.loads(Path("deploy_context.json").read_text())
            url = f"http://{ctx['alb_dns']}"
        except Exception:
            url = "http://localhost"
            
    asyncio.run(main(url, rps, duration))