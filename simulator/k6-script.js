import http from 'k6/http';
import { sleep, fail } from 'k6';
import { Trend, Counter } from 'k6/metrics';
import exec from 'k6/execution';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.2/index.js';

// Define the scenarios dynamically based on QUICK_TEST environment variable
let isQuick = __ENV.QUICK_TEST === 'true';

export let options = isQuick ? {
  scenarios: {
    quick: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '15s',
      preAllocatedVUs: 50,
      maxVUs: 150,
    }
  }
} : {
  scenarios: {
    normal: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '10s',
      preAllocatedVUs: 50,
      maxVUs: 150,
      startTime: '0s',
    },
    peak_50: {
      executor: 'constant-arrival-rate',
      rate: 50,
      timeUnit: '1s',
      duration: '180s',
      preAllocatedVUs: 150,
      maxVUs: 350,
      startTime: '10s',
    },
    warmup_100: {
      executor: 'constant-arrival-rate',
      rate: 100,
      timeUnit: '1s',
      duration: '120s',
      preAllocatedVUs: 250,
      maxVUs: 500,
      startTime: '190s',
    },
    warmup_150: {
      executor: 'constant-arrival-rate',
      rate: 150,
      timeUnit: '1s',
      duration: '120s',
      preAllocatedVUs: 350,
      maxVUs: 700,
      startTime: '310s',
    },
    stress_200: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '180s',
      preAllocatedVUs: 500,
      maxVUs: 1000,
      startTime: '430s',
    },
  }
};

// Custom metrics for each stage to mirror Python's statistics
const stageTrends = {
  'normal': new Trend('latency_normal'),
  'peak_50': new Trend('latency_peak_50'),
  'warmup_100': new Trend('latency_warmup_100'),
  'warmup_150': new Trend('latency_warmup_150'),
  'stress_200': new Trend('latency_stress_200'),
  'quick': new Trend('latency_quick'),
};

const stageCompleted = {
  'normal': new Counter('completed_normal'),
  'peak_50': new Counter('completed_peak_50'),
  'warmup_100': new Counter('completed_warmup_100'),
  'warmup_150': new Counter('completed_warmup_150'),
  'stress_200': new Counter('completed_stress_200'),
  'quick': new Counter('completed_quick'),
};

const stageScheduled = {
  'normal': new Counter('scheduled_normal'),
  'peak_50': new Counter('scheduled_peak_50'),
  'warmup_100': new Counter('scheduled_warmup_100'),
  'warmup_150': new Counter('scheduled_warmup_150'),
  'stress_200': new Counter('scheduled_stress_200'),
  'quick': new Counter('scheduled_quick'),
};

const STATUS_FLOW = ["CONFIRMED", "PREPARING", "READY_FOR_PICKUP", "PICKED_UP", "IN_TRANSIT", "DELIVERED"];

// Wrapper helper to measure and log HTTP latency
function customRequest(method, url, body, params, scenarioName) {
  let startTime = Date.now();
  let res;
  if (method === 'POST') {
    res = http.post(url, body, params);
  } else if (method === 'GET') {
    res = http.get(url, params);
  } else if (method === 'PUT') {
    res = http.put(url, body, params);
  } else if (method === 'PATCH') {
    res = http.patch(url, body, params);
  }
  let duration = Date.now() - startTime;

  if (stageTrends[scenarioName]) {
    stageTrends[scenarioName].add(duration);
  }
  return res;
}

// Seeding phase: runs once, prepares DB, and returns IDs to all VUs
export function setup() {
  let targetUrl = __ENV.TARGET_URL || 'http://localhost';
  let cityNamespace = __ENV.CITY_NAMESPACE || '';

  console.log(`--- DijkFood Load Simulator ---`);
  console.log(`Semeando dados iniciais...`);
  console.log(`[Seed] Usando namespace '${cityNamespace}' para host-based routing.`);

  // 1. Discover Region
  let headers = { 'Content-Type': 'application/json' };
  if (cityNamespace) {
    headers['Host'] = `region.${cityNamespace}.local`;
  }

  let regionRes = http.get(`${targetUrl}/region/`, { headers: headers });
  let regionId = 1;
  let cityName = "São Paulo, Brazil";
  if (regionRes.status === 200 && regionRes.body) {
    try {
      let regions = JSON.parse(regionRes.body);
      if (regions && regions.length > 0) {
        regionId = regions[0].id;
        cityName = regions[0].name;
      }
    } catch(e) {}
  }

  console.log(`[Seed] Região padrão encontrada: id=${regionId}, name='${cityName}'`);

  // geocoding fallback
  let cityLat = -23.5505;
  let cityLon = -46.6333;
  let nameLower = cityName.toLowerCase();
  if (nameLower.includes("russas")) {
    cityLat = -4.9416;
    cityLon = -37.9725;
    console.log(`[Seed] Usando coordenadas estáticas para Russas: lat=${cityLat}, lon=${cityLon}`);
  } else {
    console.log(`[Seed] Usando coordenadas estáticas para São Paulo: lat=${cityLat}, lon=${cityLon}`);
  }

  // 2. Create Kitchen Type
  let kitchenHeaders = { 'Content-Type': 'application/json' };
  if (cityNamespace) {
    kitchenHeaders['Host'] = `restaurants.${cityNamespace}.local`;
  }
  let kitchenRes = http.post(`${targetUrl}/kitchen/`, JSON.stringify({ type: "Variada" }), { headers: kitchenHeaders });
  let kitchenId = 1;
  if (kitchenRes.status === 200 || kitchenRes.status === 201) {
    try {
      kitchenId = JSON.parse(kitchenRes.body).id;
    } catch(e) {}
  }

  // 3. Create 8 Restaurants and Items
  let restaurantNames = [
    "Dijkstra Pasta", "Prim Pizza", "Kruskal Burger", "Bellman Bistro",
    "Floyd Grill", "Turing Tacos", "Lovelace Lasagna", "Knuth Kabob"
  ];
  let itemNames = [
    "Spaghetti O(V+E)", "Pizza Graph-Marguerita", "MST Double Burger", "Shortest Path Steak",
    "Matrix Ribs", "Halting Quesadilla", "Ada Lasagna Special", "B-Tree Beef"
  ];

  let restaurantIds = [];
  let itemIds = [];

  for (let i = 0; i < restaurantNames.length; i++) {
    let rPayload = JSON.stringify({
      name: restaurantNames[i],
      lat: cityLat + (Math.random() * 0.016 - 0.008),
      lon: cityLon + (Math.random() * 0.016 - 0.008),
      kitchen_type_id: kitchenId
    });
    let rRes = http.post(`${targetUrl}/restaurant/`, rPayload, { headers: kitchenHeaders });
    let rId = i + 1;
    if (rRes.status === 200 || rRes.status === 201) {
      try { rId = JSON.parse(rRes.body).id; } catch(e) {}
    }
    restaurantIds.push(rId);

    let itemPayload = JSON.stringify({
      name: itemNames[i],
      price: parseFloat((Math.random() * 30 + 15).toFixed(2)),
      restaurant_id: rId
    });
    let itemRes = http.post(`${targetUrl}/item/`, itemPayload, { headers: kitchenHeaders });
    let itemId = i + 1;
    if (itemRes.status === 200 || itemRes.status === 201) {
      try { itemId = JSON.parse(itemRes.body).id; } catch(e) {}
    }
    itemIds.push(itemId);
  }

  // 4. Create User / Client
  let clientHeaders = { 'Content-Type': 'application/json' };
  if (cityNamespace) {
    clientHeaders['Host'] = `clients.${cityNamespace}.local`;
  }
  let userPayload = JSON.stringify({
    email: `k6-user-${Date.now()}@dijkfood.br`,
    name: "K6 Cliente Teste",
    house_lat: cityLat + 0.001,
    house_lon: cityLon - 0.001,
    phones: ["11999999999"]
  });
  let userRes = http.post(`${targetUrl}/user/`, userPayload, { headers: clientHeaders });
  let userId = 1;
  if (userRes.status === 200 || userRes.status === 201) {
    try { userId = JSON.parse(userRes.body).id; } catch(e) {}
  }

  // 5. Seed 60 Couriers
  let courierHeaders = { 'Content-Type': 'application/json' };
  if (cityNamespace) {
    courierHeaders['Host'] = `couriers.${cityNamespace}.local`;
  }
  for (let i = 0; i < 60; i++) {
    let cPayload = JSON.stringify({
      name: `K6 Entregador ${i}`,
      vehicle: "MOTORCYCLE",
      lat: cityLat + (Math.random() * 0.03 - 0.015),
      lon: cityLon + (Math.random() * 0.03 - 0.015)
    });
    http.post(`${targetUrl}/courier/`, cPayload, { headers: courierHeaders });
  }

  console.log(`[Seed] 60 entregadores criados com sucesso.`);
  console.log(`Seed concluído.`);

  return {
    restaurant_ids: restaurantIds,
    item_ids: itemIds,
    user_id: userId,
    city_lat: cityLat,
    city_lon: cityLon,
    region_id: regionId
  };
}

// Order Lifecycle flow run by Virtual Users
export default function(data) {
  let targetUrl = __ENV.TARGET_URL || 'http://localhost';
  let cityNamespace = __ENV.CITY_NAMESPACE || '';
  let scenarioName = exec.scenario.name;

  if (stageScheduled[scenarioName]) {
    stageScheduled[scenarioName].add(1);
  }

  // Host header routing
  let orderHeaders = { 'Content-Type': 'application/json' };
  if (cityNamespace) {
    orderHeaders['Host'] = `orders.${cityNamespace}.local`;
  }

  // 1. Create random order
  let idx = Math.floor(Math.random() * data.restaurant_ids.length);
  let rId = data.restaurant_ids[idx];
  let itId = data.item_ids[idx];

  let orderPayload = JSON.stringify({
    restaurant_id: rId,
    user_id: data.user_id,
    items: [{ item_id: itId, quantity: Math.floor(Math.random() * 4) + 1 }]
  });

  let orderRes = customRequest('POST', `${targetUrl}/order/`, orderPayload, { headers: orderHeaders }, scenarioName);
  if (orderRes.status !== 200 && orderRes.status !== 201) {
    fail(`Failed to create order: ${orderRes.status}`);
  }

  let orderData;
  try {
    orderData = JSON.parse(orderRes.body);
  } catch(e) {
    fail(`Failed to parse order response: ${orderRes.body}`);
  }
  let orderId = orderData.id;

  // 2. GET /order/{id}
  let getOrderRes = customRequest('GET', `${targetUrl}/order/${orderId}`, null, { headers: orderHeaders }, scenarioName);
  if (getOrderRes.status !== 200 && getOrderRes.status !== 201) {
    fail(`Failed to fetch order: ${getOrderRes.status}`);
  }

  let currentOrder = JSON.parse(getOrderRes.body);
  let selectedCourierId = currentOrder.courier ? currentOrder.courier.id : null;
  let currentStatus = currentOrder.status;

  // 3. Fallback: Assign courier if matching service didn't pick one
  if (!selectedCourierId) {
    let courierHeaders = { 'Content-Type': 'application/json' };
    if (cityNamespace) {
      courierHeaders['Host'] = `couriers.${cityNamespace}.local`;
    }

    // Create a dynamic courier
    let courierPayload = JSON.stringify({
      name: `K6-Entregador-${Date.now()}-${Math.floor(Math.random()*10000)}`,
      vehicle: "MOTORCYCLE",
      lat: data.city_lat + (Math.random() * 0.02 - 0.01),
      lon: data.city_lon + (Math.random() * 0.02 - 0.01)
    });

    let courierRes = customRequest('POST', `${targetUrl}/courier/`, courierPayload, { headers: courierHeaders }, scenarioName);
    if (courierRes.status === 200 || courierRes.status === 201) {
      selectedCourierId = JSON.parse(courierRes.body).id;
    } else {
      // Find any courier as a fallback
      let getCouriersRes = customRequest('GET', `${targetUrl}/courier/`, null, { headers: courierHeaders }, scenarioName);
      if (getCouriersRes.status === 200) {
        let couriers = JSON.parse(getCouriersRes.body);
        if (couriers && couriers.length > 0) {
          selectedCourierId = couriers[Math.floor(Math.random() * couriers.length)].id;
        }
      }
    }
  }

  if (!selectedCourierId) {
    fail("Could not resolve courier ID for delivery simulation.");
  }

  // 4. Create Delivery
  let deliveryRes = customRequest('POST', `${targetUrl}/delivery/`, JSON.stringify({
    order_id: orderId,
    courier_id: selectedCourierId
  }), { headers: orderHeaders }, scenarioName);

  let deliveryId = orderId;
  if (deliveryRes.status === 200 || deliveryRes.status === 201) {
    let deliveryData = JSON.parse(deliveryRes.body);
    deliveryId = deliveryData.id;
    selectedCourierId = deliveryData.courier ? deliveryData.courier.id : selectedCourierId;
    currentStatus = null;
  } else if (deliveryRes.status === 409) {
    // fetch existing delivery
    let getDeliveryRes = customRequest('GET', `${targetUrl}/delivery/?order_id=${orderId}`, null, { headers: orderHeaders }, scenarioName);
    if (getDeliveryRes.status === 200) {
      let deliveries = JSON.parse(getDeliveryRes.body);
      if (deliveries && deliveries.length > 0) {
        deliveryId = deliveries[0].id;
        selectedCourierId = deliveries[0].courier ? deliveries[0].courier.id : selectedCourierId;
      }
    }
  } else {
    fail(`Failed to create delivery status=${deliveryRes.status}`);
  }

  // 5. Courier Position updates (10 sequential updates, 100ms interval)
  let posHeaders = { 'Content-Type': 'application/json' };
  if (cityNamespace) {
    posHeaders['Host'] = `couriers.${cityNamespace}.local`;
  }
  for (let i = 0; i < 10; i++) {
    let posPayload = JSON.stringify({
      delivery_id: String(deliveryId),
      lat_courier: data.city_lat + (Math.random() * 0.02 - 0.01),
      lon_courier: data.city_lon + (Math.random() * 0.02 - 0.01)
    });
    customRequest('PUT', `${targetUrl}/courier/${selectedCourierId}/position`, posPayload, { headers: posHeaders }, scenarioName);
    sleep(0.1);
  }

  // 6. Transition through delivery statuses
  let nextStatuses = getRemainingStatuses(currentStatus);
  for (let nextStatus of nextStatuses) {
    customRequest('PATCH', `${targetUrl}/delivery/${deliveryId}/status`, JSON.stringify({ status: nextStatus }), { headers: orderHeaders }, scenarioName);
    sleep(0.5);
  }

  if (stageCompleted[scenarioName]) {
    stageCompleted[scenarioName].add(1);
  }
}

function getRemainingStatuses(currentStatus) {
  if (!currentStatus) {
    return STATUS_FLOW;
  }
  let index = STATUS_FLOW.indexOf(currentStatus);
  if (index === -1) {
    return [];
  }
  return STATUS_FLOW.slice(index + 1);
}

// Build the textual console output format
function formatStage(data, name, rps, durationSeconds) {
  let trendKey = `latency_${name}`;
  let completedKey = `completed_${name}`;
  let scheduledKey = `scheduled_${name}`;

  let trend = data.metrics[trendKey];
  let completed = data.metrics[completedKey];
  let scheduled = data.metrics[scheduledKey];

  if (!trend || trend.values.count === 0) {
    return '';
  }

  let totalReqs = trend.values.count;
  let avg = trend.values.avg;
  let p95 = trend.values['p(95)'];
  let compCount = completed ? completed.values.count : 0;
  let schedCount = scheduled ? scheduled.values.count : 0;
  let throughput = compCount / durationSeconds;

  let successMsg = p95 < 500
    ? "SUCESSO: P95 abaixo de 500ms!"
    : "AVISO: P95 acima de 500ms. ECS pode estar precisando de mais containers.";

  return `
Resultados para ${rps} RPS:
Total de Requisições: ${totalReqs}
Latência Média: ${avg.toFixed(2)} ms
Latência P95: ${p95.toFixed(2)} ms
Pedidos agendados: ${schedCount}
Pedidos completos: ${compCount}
Throughput efetivo de pedidos: ${throughput.toFixed(2)} pedidos/s
${successMsg}
`;
}

export function handleSummary(data) {
  let customText = `\n=== DIJKFOOD CUSTOM LOAD TEST REPORT ===\n`;
  if (isQuick) {
    customText += formatStage(data, 'quick', 10, 15);
  } else {
    customText += formatStage(data, 'normal', 10, 10);
    customText += formatStage(data, 'peak_50', 50, 180);
    customText += formatStage(data, 'warmup_100', 100, 120);
    customText += formatStage(data, 'warmup_150', 150, 120);
    customText += formatStage(data, 'stress_200', 200, 180);
  }
  customText += `\n========================================\n`;

  return {
    'stdout': customText + '\n' + textSummary(data, { indent: ' ', enableColors: true }),
  };
}
