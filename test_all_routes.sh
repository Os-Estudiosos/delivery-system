#!/usr/bin/env bash
# =============================================================
# test_all_routes.sh — Testa todas as rotas da DijkFood API
# Uso: bash test_all_routes.sh
# =============================================================
set -euo pipefail

# Cores
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0

ok()   { echo -e "${GREEN}✅ PASS${NC} — $1"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}❌ FAIL${NC} — $1\n       ↳ $2"; FAIL=$((FAIL+1)); }
sep()  { echo -e "\n${YELLOW}══ $1 ══${NC}"; }

check() {
  local label="$1" expected_status="$2" actual_status="$3" body="$4"
  if [ "$actual_status" -eq "$expected_status" ]; then
    ok "$label (HTTP $actual_status)"
  else
    fail "$label" "esperado HTTP $expected_status, recebido HTTP $actual_status — $body"
  fi
}

BASE_REGION="http://localhost:4006"
BASE_CLIENT="http://localhost:4001"
BASE_COURIER="http://localhost:4002"
BASE_RESTAURANT="http://localhost:4005"
BASE_ORDER="http://localhost:4004"

# ─────────────────────────────────────────────
sep "HEALTH CHECKS"
# ─────────────────────────────────────────────
declare -A HEALTH_URLS=(
  ["region"]="http://localhost:4006/health"
  ["clients"]="http://localhost:4001/health"
  ["couriers"]="http://localhost:4002/health"
  ["restaurants"]="http://localhost:4005/health"
  ["orders"]="http://localhost:4004/health"
  ["matching"]="http://localhost:4003/health"
)
for name in region clients couriers restaurants orders matching; do
  r=$(curl -s -o /dev/null -w "%{http_code}" "${HEALTH_URLS[$name]}")
  check "Health: $name" 200 "$r" ""
done

# ─────────────────────────────────────────────
sep "REGION — CRUD"
# ─────────────────────────────────────────────

# Listar (São Paulo já deve existir pelo seed do DDL)
R=$(curl -s -w "\n%{http_code}" "$BASE_REGION/region/")
STATUS=$(echo "$R" | tail -1); BODY=$(echo "$R" | head -1)
check "GET /region/ (lista)" 200 "$STATUS" "$BODY"

# Criar nova região
R=$(curl -s -w "\n%{http_code}" -X POST "$BASE_REGION/region/" \
  -H "Content-Type: application/json" \
  -d '{"name":"Campinas, Brazil"}')
STATUS=$(echo "$R" | tail -1); BODY=$(echo "$R" | head -1)
check "POST /region/ (criar)" 201 "$STATUS" "$BODY"
REGION_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "2")

# GET by id
R=$(curl -s -w "\n%{http_code}" "$BASE_REGION/region/$REGION_ID")
STATUS=$(echo "$R" | tail -1)
check "GET /region/$REGION_ID" 200 "$STATUS" ""

# PATCH
R=$(curl -s -w "\n%{http_code}" -X PATCH "$BASE_REGION/region/$REGION_ID" \
  -H "Content-Type: application/json" \
  -d '{"name":"Campinas Updated"}')
STATUS=$(echo "$R" | tail -1)
check "PATCH /region/$REGION_ID" 200 "$STATUS" ""

# DELETE
R=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE_REGION/region/$REGION_ID")
STATUS=$(echo "$R" | tail -1)
check "DELETE /region/$REGION_ID" 204 "$STATUS" ""

# ─────────────────────────────────────────────
sep "KITCHEN TYPE — CRUD"
# ─────────────────────────────────────────────
R=$(curl -s -w "\n%{http_code}" -X POST "$BASE_RESTAURANT/kitchen/" \
  -H "Content-Type: application/json" \
  -d '{"type":"Italiana"}')
STATUS=$(echo "$R" | tail -1); BODY=$(echo "$R" | head -1)
check "POST /kitchen/" 200 "$STATUS" "$BODY"
KIT_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "1")

R=$(curl -s -w "\n%{http_code}" "$BASE_RESTAURANT/kitchen/")
check "GET /kitchen/" 200 "$(echo "$R" | tail -1)" ""

R=$(curl -s -w "\n%{http_code}" "$BASE_RESTAURANT/kitchen/$KIT_ID")
check "GET /kitchen/$KIT_ID" 200 "$(echo "$R" | tail -1)" ""

R=$(curl -s -w "\n%{http_code}" -X PATCH "$BASE_RESTAURANT/kitchen/$KIT_ID" \
  -H "Content-Type: application/json" \
  -d '{"type":"Italiana Updated"}')
check "PATCH /kitchen/$KIT_ID" 200 "$(echo "$R" | tail -1)" ""

# ─────────────────────────────────────────────
sep "RESTAURANT — CRUD"
# ─────────────────────────────────────────────
R=$(curl -s -w "\n%{http_code}" -X POST "$BASE_RESTAURANT/restaurant/" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Trattoria\",\"lat\":-23.5505,\"lon\":-46.6333,\"kitchen_type_id\":$KIT_ID}")
STATUS=$(echo "$R" | tail -1); BODY=$(echo "$R" | head -1)
check "POST /restaurant/" 201 "$STATUS" "$BODY"
REST_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "1")

R=$(curl -s -w "\n%{http_code}" "$BASE_RESTAURANT/restaurant/")
check "GET /restaurant/" 200 "$(echo "$R" | tail -1)" ""

R=$(curl -s -w "\n%{http_code}" "$BASE_RESTAURANT/restaurant/$REST_ID")
check "GET /restaurant/$REST_ID" 200 "$(echo "$R" | tail -1)" ""

R=$(curl -s -w "\n%{http_code}" -X PATCH "$BASE_RESTAURANT/restaurant/$REST_ID" \
  -H "Content-Type: application/json" \
  -d '{"name":"Trattoria Updated"}')
check "PATCH /restaurant/$REST_ID" 200 "$(echo "$R" | tail -1)" ""

# ─────────────────────────────────────────────
sep "ITEM — CRUD"
# ─────────────────────────────────────────────
R=$(curl -s -w "\n%{http_code}" -X POST "$BASE_RESTAURANT/item/" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Lasanha\",\"price\":45.90,\"restaurant_id\":$REST_ID}")
STATUS=$(echo "$R" | tail -1); BODY=$(echo "$R" | head -1)
check "POST /item/" 201 "$STATUS" "$BODY"
ITEM_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "1")

R=$(curl -s -w "\n%{http_code}" "$BASE_RESTAURANT/item/")
check "GET /item/" 200 "$(echo "$R" | tail -1)" ""

R=$(curl -s -w "\n%{http_code}" "$BASE_RESTAURANT/item/$ITEM_ID")
check "GET /item/$ITEM_ID" 200 "$(echo "$R" | tail -1)" ""

R=$(curl -s -w "\n%{http_code}" -X PATCH "$BASE_RESTAURANT/item/$ITEM_ID" \
  -H "Content-Type: application/json" \
  -d '{"price":49.90}')
check "PATCH /item/$ITEM_ID" 200 "$(echo "$R" | tail -1)" ""

# ─────────────────────────────────────────────
sep "CLIENT — CRUD"
# ─────────────────────────────────────────────
R=$(curl -s -w "\n%{http_code}" -X POST "$BASE_CLIENT/client" \
  -H "Content-Type: application/json" \
  -d '{"email":"joao@test.com","name":"João Silva","house_lat":-23.551,"house_lon":-46.634,"region_id":1}')
STATUS=$(echo "$R" | tail -1); BODY=$(echo "$R" | head -1)
check "POST /client" 201 "$STATUS" "$BODY"
CLIENT_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "1")

R=$(curl -s -w "\n%{http_code}" "$BASE_CLIENT/client")
check "GET /client" 200 "$(echo "$R" | tail -1)" ""

R=$(curl -s -w "\n%{http_code}" "$BASE_CLIENT/client/$CLIENT_ID")
check "GET /client/$CLIENT_ID" 200 "$(echo "$R" | tail -1)" ""

R=$(curl -s -w "\n%{http_code}" -X PATCH "$BASE_CLIENT/client/$CLIENT_ID" \
  -H "Content-Type: application/json" \
  -d '{"name":"João Updated"}')
check "PATCH /client/$CLIENT_ID" 200 "$(echo "$R" | tail -1)" ""

# ─────────────────────────────────────────────
sep "COURIER — CRUD + POSIÇÃO"
# ─────────────────────────────────────────────
R=$(curl -s -w "\n%{http_code}" -X POST "$BASE_COURIER/courier/" \
  -H "Content-Type: application/json" \
  -d '{"name":"Carlos Moto","vehicle":"MOTORCYCLE","lat":-23.550,"lon":-46.633,"region_id":1}')
STATUS=$(echo "$R" | tail -1); BODY=$(echo "$R" | head -1)
check "POST /courier/" 201 "$STATUS" "$BODY"
COURIER_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "1")

R=$(curl -s -w "\n%{http_code}" "$BASE_COURIER/courier/")
check "GET /courier/" 200 "$(echo "$R" | tail -1)" ""

R=$(curl -s -w "\n%{http_code}" "$BASE_COURIER/courier/$COURIER_ID")
check "GET /courier/$COURIER_ID" 200 "$(echo "$R" | tail -1)" ""

R=$(curl -s -w "\n%{http_code}" -X PATCH "$BASE_COURIER/courier/$COURIER_ID" \
  -H "Content-Type: application/json" \
  -d '{"name":"Carlos Updated"}')
check "PATCH /courier/$COURIER_ID" 200 "$(echo "$R" | tail -1)" ""

R=$(curl -s -w "\n%{http_code}" -X PUT "$BASE_COURIER/courier/$COURIER_ID/position" \
  -H "Content-Type: application/json" \
  -d "{\"delivery_id\":\"test-delivery-1\",\"lat_courier\":-23.5505,\"lon_courier\":-46.6335}")
check "PUT /courier/$COURIER_ID/position" 200 "$(echo "$R" | tail -1)" ""

# ─────────────────────────────────────────────
sep "ORDER — CICLO COMPLETO"
# ─────────────────────────────────────────────
R=$(curl -s -w "\n%{http_code}" -X POST "$BASE_ORDER/order/" \
  -H "Content-Type: application/json" \
  -d "{\"restaurant_id\":$REST_ID,\"user_id\":$CLIENT_ID,\"items\":[{\"item_id\":$ITEM_ID,\"quantity\":2}]}")
STATUS=$(echo "$R" | tail -1); BODY=$(echo "$R" | head -1)
check "POST /order/" 201 "$STATUS" "$BODY"
ORDER_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "1")

R=$(curl -s -w "\n%{http_code}" "$BASE_ORDER/order/")
check "GET /order/" 200 "$(echo "$R" | tail -1)" ""

R=$(curl -s -w "\n%{http_code}" "$BASE_ORDER/order/$ORDER_ID")
check "GET /order/$ORDER_ID" 200 "$(echo "$R" | tail -1)" ""

R=$(curl -s -w "\n%{http_code}" "$BASE_ORDER/order/$ORDER_ID/event")
check "GET /order/$ORDER_ID/event" 200 "$(echo "$R" | tail -1)" ""

# ─────────────────────────────────────────────
sep "DELIVERY — CRIAR E MÁQUINA DE ESTADOS"
# ─────────────────────────────────────────────
R=$(curl -s -w "\n%{http_code}" "$BASE_ORDER/delivery/")
check "GET /delivery/" 200 "$(echo "$R" | tail -1)" ""

# Criar delivery manualmente (caso matching não tenha encontrado courier)
R=$(curl -s -w "\n%{http_code}" -X POST "$BASE_ORDER/delivery/" \
  -H "Content-Type: application/json" \
  -d "{\"order_id\":$ORDER_ID,\"courier_id\":$COURIER_ID}")
STATUS=$(echo "$R" | tail -1); BODY=$(echo "$R" | head -1)
# 201 = criado agora; 409 = já existe (matching já criou)
if [ "$STATUS" -eq 201 ] || [ "$STATUS" -eq 409 ]; then
  ok "POST /delivery/ (HTTP $STATUS — criado ou já existia via matching)"
else
  fail "POST /delivery/" "esperado 201 ou 409, recebeu $STATUS"
fi

# Buscar delivery_id
R=$(curl -s "$BASE_ORDER/delivery/")
DELIVERY_ID=$(echo "$R" | python3 -c "
import sys,json
deliveries=json.load(sys.stdin)
for d in deliveries:
    if d['order']['id'] == $ORDER_ID:
        print(d['id']); break
" 2>/dev/null || echo "1")

R=$(curl -s -w "\n%{http_code}" "$BASE_ORDER/delivery/$DELIVERY_ID")
check "GET /delivery/$DELIVERY_ID" 200 "$(echo "$R" | tail -1)" ""

# Verificar status atual antes de avançar
CURRENT=$(curl -s "$BASE_ORDER/order/$ORDER_ID/event" | \
  python3 -c "import sys,json; evs=json.load(sys.stdin); print(evs[0]['status'] if evs else 'NONE')" 2>/dev/null || echo "NONE")

TRANSITIONS=("CONFIRMED" "PREPARING" "READY_FOR_PICKUP" "PICKED_UP" "IN_TRANSIT" "DELIVERED")
ORDER_STATES=("CONFIRMED" "PREPARING" "READY_FOR_PICKUP" "PICKED_UP" "IN_TRANSIT" "DELIVERED")

# Encontra a posição do status atual e avança dali
START=0
for i in "${!ORDER_STATES[@]}"; do
  if [ "${ORDER_STATES[$i]}" == "$CURRENT" ]; then
    START=$((i+1))
    break
  fi
done

i=$START
while [ "$i" -lt "${#TRANSITIONS[@]}" ]; do
  ST="${TRANSITIONS[$i]}"
  R=$(curl -s -w "\n%{http_code}" -X PATCH "$BASE_ORDER/delivery/$DELIVERY_ID/status" \
    -H "Content-Type: application/json" \
    -d "{\"status\":\"$ST\"}")
  STATUS=$(echo "$R" | tail -1)
  check "PATCH /delivery/$DELIVERY_ID/status → $ST" 201 "$STATUS" "$(echo "$R" | head -1)"
  i=$((i+1))
done

# ─────────────────────────────────────────────
sep "KITCHEN DELETE (cobertura CRUD completa)"
# ─────────────────────────────────────────────
# KITCHEN DELETE (pode ser 204 se sem restaurantes, ou 409 se tiver restaurante associado)
R=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_RESTAURANT/kitchen/$KIT_ID")
if [ "$R" -eq 204 ] || [ "$R" -eq 409 ]; then
  ok "DELETE /kitchen/$KIT_ID (HTTP $R)"
else
  fail "DELETE /kitchen/$KIT_ID" "esperado 204 ou 409, recebeu $R"
fi

# CLIENT DELETE (pode ser 204 se sem pedidos, ou 409 se tiver orders associadas)
R=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_CLIENT/client/$CLIENT_ID")
if [ "$R" -eq 204 ] || [ "$R" -eq 409 ]; then
  ok "DELETE /client/$CLIENT_ID (HTTP $R)"
else
  fail "DELETE /client/$CLIENT_ID" "esperado 204 ou 409, recebeu $R"
fi

# ─────────────────────────────────────────────
sep "RESULTADO FINAL"
# ─────────────────────────────────────────────
TOTAL=$((PASS+FAIL))
echo -e "\nTotal: $TOTAL | ${GREEN}Passou: $PASS${NC} | ${RED}Falhou: $FAIL${NC}"
[ "$FAIL" -eq 0 ] && echo -e "${GREEN}🎉 Todas as rotas passaram!${NC}" || exit 1
