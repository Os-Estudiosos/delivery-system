"""
dashboard_prod.py — CidadeX Analytics Dashboard (Produção)
Lê dados do Athena via boto3 em vez do PostgreSQL local.

Usage na EC2:
    streamlit run dashboard_prod.py --server.port 8501 --server.address 0.0.0.0
"""

import io
import os
import time

import boto3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── config ────────────────────────────────────────────────────────────────────
AWS_REGION    = os.getenv("AWS_REGION",    "us-east-1")
ATHENA_DB     = os.getenv("ATHENA_DB",     "dijkfood_analytics")
ATHENA_WG     = os.getenv("ATHENA_WG",     "dijkfood-analytics")
RESULTS_BUCKET = os.getenv("RESULTS_BUCKET", "dijkfood-athena-results")

st.set_page_config(
    page_title="CidadeX — Analytics",
    page_icon="🛵",
    layout="wide",
)


# ── cliente Athena (cached) ───────────────────────────────────────────────────
@st.cache_resource
def get_athena():
    return boto3.client("athena", region_name=AWS_REGION)


@st.cache_resource
def get_s3():
    return boto3.client("s3", region_name=AWS_REGION)


def run_query(sql: str) -> str:
    """Dispara uma query no Athena e retorna o QueryExecutionId."""
    resp = get_athena().start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": ATHENA_DB},
        WorkGroup=ATHENA_WG,
    )
    return resp["QueryExecutionId"]


def wait_query(execution_id: str, timeout: int = 60) -> None:
    """Aguarda a query terminar ou lança exceção."""
    athena = get_athena()
    for _ in range(timeout):
        resp   = athena.get_query_execution(QueryExecutionId=execution_id)
        status = resp["QueryExecution"]["Status"]
        state  = status["State"]
        if state == "SUCCEEDED":
            return
        if state in ("FAILED", "CANCELLED"):
            reason = status.get("StateChangeReason", "")
            raise RuntimeError(f"Query {state}: {reason}")
        time.sleep(1)
    raise TimeoutError(f"Query não terminou em {timeout}s")


def fetch_results(execution_id: str) -> pd.DataFrame:
    """Baixa os resultados do S3 como DataFrame."""
    athena   = get_athena()
    s3       = get_s3()
    resp     = athena.get_query_execution(QueryExecutionId=execution_id)
    s3_path  = resp["QueryExecution"]["ResultConfiguration"]["OutputLocation"]
    # s3://bucket/prefix/id.csv
    bucket   = s3_path.split("/")[2]
    key      = "/".join(s3_path.split("/")[3:])
    obj      = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(io.BytesIO(obj["Body"].read()))


@st.cache_data(ttl=300)
def query(sql: str) -> pd.DataFrame:
    """Executa SQL no Athena e retorna DataFrame. Cache de 5 minutos."""
    qid = run_query(sql)
    wait_query(qid)
    return fetch_results(qid)


# ── queries (sintaxe Athena/Presto) ──────────────────────────────────────────
SQL_KPIs = """
SELECT
    (SELECT COUNT(*) FROM orders)                         AS total_pedidos,
    (SELECT COUNT(*) FROM deliveries)                     AS total_entregas,
    (SELECT COUNT(DISTINCT courier_id) FROM deliveries)   AS entregadores_ativos,
    (SELECT COUNT(*) FROM restaurants)                    AS restaurantes
"""

SQL_VOLUME = """
SELECT
    DATE(created_at) AS dia,
    COUNT(*)         AS total_pedidos
FROM orders
GROUP BY DATE(created_at)
ORDER BY dia
"""

SQL_TEMPO_ESTADO = """
WITH eventos_com_anterior AS (
    SELECT
        status,
        updated_at,
        LAG(updated_at) OVER (
            PARTITION BY delivery_id
            ORDER BY updated_at
        ) AS ts_anterior
    FROM events
)
SELECT
    status,
    ROUND(AVG(date_diff('second', ts_anterior, updated_at)) / 60.0, 2) AS tempo_medio_minutos
FROM eventos_com_anterior
WHERE ts_anterior IS NOT NULL
GROUP BY status
ORDER BY MIN(updated_at)
"""

SQL_REGIAO = """
SELECT
    r.name                                                      AS regiao,
    COUNT(o.id)                                                 AS total_pedidos,
    ROUND(COUNT(o.id) * 100.0 / SUM(COUNT(o.id)) OVER (), 2)  AS percentual
FROM orders o
JOIN users      u ON u.id = o.user_id
JOIN regions    r ON r.id = u.region_id
GROUP BY r.name
ORDER BY total_pedidos DESC
"""

SQL_HEATMAP = """
SELECT
    day_of_week(created_at)  AS dow_ordem,
    hour(created_at)         AS hora,
    COUNT(*)                 AS total_pedidos
FROM orders
GROUP BY day_of_week(created_at), hour(created_at)
ORDER BY dow_ordem, hora
"""

SQL_TOP10 = """
SELECT
    r.name       AS restaurante,
    reg.name     AS regiao,
    kt.type      AS cozinha,
    COUNT(o.id)  AS total_pedidos
FROM orders o
JOIN restaurants  r   ON r.id   = o.restaurant_id
JOIN regions      reg ON reg.id = r.region_id
JOIN kitchen_types kt ON kt.id  = r.kitchen_type_id
GROUP BY r.name, reg.name, kt.type
ORDER BY total_pedidos DESC
LIMIT 10
"""

SQL_HISTOGRAMA = """
WITH tempos AS (
    SELECT
        d.id AS delivery_id,
        MIN(CASE WHEN e.status = 'CONFIRMED' THEN e.updated_at END) AS ts_confirmed,
        MAX(CASE WHEN e.status = 'DELIVERED' THEN e.updated_at END) AS ts_delivered
    FROM deliveries d
    JOIN events e ON e.delivery_id = d.id
    GROUP BY d.id
    HAVING
        MIN(CASE WHEN e.status = 'CONFIRMED' THEN e.updated_at END) IS NOT NULL
        AND MAX(CASE WHEN e.status = 'DELIVERED' THEN e.updated_at END) IS NOT NULL
),
duracoes AS (
    SELECT
        CAST(date_diff('minute', ts_confirmed, ts_delivered) AS INTEGER) AS minutos
    FROM tempos
)
SELECT
    (minutos / 10) * 10      AS bucket_inicio,
    (minutos / 10) * 10 + 9  AS bucket_fim,
    COUNT(*)                 AS total_entregas
FROM duracoes
GROUP BY (minutos / 10) * 10
ORDER BY bucket_inicio
"""

# ── constantes de UI ──────────────────────────────────────────────────────────
STATUS_ORDER = ["PREPARING", "READY_FOR_PICKUP", "PICKED_UP", "IN_TRANSIT", "DELIVERED"]
DIAS_PT      = {1: "Dom", 2: "Seg", 3: "Ter", 4: "Qua", 5: "Qui", 6: "Sex", 7: "Sáb"}

# ── layout ────────────────────────────────────────────────────────────────────
st.title("🛵 CidadeX — Analytics Dashboard")
st.caption(f"Fonte: Athena `{ATHENA_DB}` • Workgroup: `{ATHENA_WG}` • Cache: 5min")

# ── KPIs ──────────────────────────────────────────────────────────────────────
kpis = query(SQL_KPIs).iloc[0]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total de Pedidos",    f"{int(kpis['total_pedidos']):,}".replace(",", "."))
k2.metric("Total de Entregas",   f"{int(kpis['total_entregas']):,}".replace(",", "."))
k3.metric("Entregadores Ativos", f"{int(kpis['entregadores_ativos']):,}".replace(",", "."))
k4.metric("Restaurantes",        f"{int(kpis['restaurantes']):,}".replace(",", "."))

st.divider()

# ── 1. Volume no tempo ────────────────────────────────────────────────────────
st.subheader("1 · Volume de Pedidos no Tempo")
df_vol = query(SQL_VOLUME)
df_vol["dia"] = pd.to_datetime(df_vol["dia"])
fig_vol = px.area(df_vol, x="dia", y="total_pedidos",
    labels={"dia": "Data", "total_pedidos": "Pedidos"},
    color_discrete_sequence=["#FF6B35"])
fig_vol.update_layout(margin=dict(t=10, b=10))
st.plotly_chart(fig_vol, width="stretch")

st.divider()

# ── 2 e 3 lado a lado ────────────────────────────────────────────────────────
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("2 · Tempo Médio por Estado")
    df_tempo = query(SQL_TEMPO_ESTADO)
    df_tempo["status"] = pd.Categorical(df_tempo["status"], categories=STATUS_ORDER, ordered=True)
    df_tempo = df_tempo.sort_values("status")
    fig_tempo = px.bar(df_tempo, x="tempo_medio_minutos", y="status", orientation="h",
        labels={"tempo_medio_minutos": "Minutos (média)", "status": "Estado"},
        color="tempo_medio_minutos", color_continuous_scale="Oranges", text="tempo_medio_minutos")
    fig_tempo.update_traces(texttemplate="%{text:.1f} min", textposition="outside")
    fig_tempo.update_layout(coloraxis_showscale=False, margin=dict(t=10, b=10))
    st.plotly_chart(fig_tempo, width="stretch")

with col_b:
    st.subheader("3 · Distribuição por Região")
    df_reg = query(SQL_REGIAO)
    fig_reg = px.pie(df_reg, names="regiao", values="total_pedidos", hole=0.45,
        color_discrete_sequence=px.colors.qualitative.Set2)
    fig_reg.update_traces(textinfo="label+percent", pull=[0.03] * len(df_reg))
    fig_reg.update_layout(margin=dict(t=10, b=10), showlegend=False)
    st.plotly_chart(fig_reg, width="stretch")

st.divider()

# ── 4. Heatmap ────────────────────────────────────────────────────────────────
st.subheader("4 · Heatmap de Demanda por Horário e Dia da Semana")
df_heat = query(SQL_HEATMAP)
df_heat["dia_label"] = df_heat["dow_ordem"].map(DIAS_PT)
pivot = (
    df_heat.pivot_table(index="dia_label", columns="hora",
        values="total_pedidos", aggfunc="sum", fill_value=0)
    .reindex([DIAS_PT[i] for i in sorted(DIAS_PT)])
)
fig_heat = go.Figure(go.Heatmap(
    z=pivot.values,
    x=[f"{h:02d}h" for h in pivot.columns],
    y=pivot.index.tolist(),
    colorscale="YlOrRd",
    hovertemplate="Dia: %{y}<br>Hora: %{x}<br>Pedidos: %{z}<extra></extra>",
))
fig_heat.update_layout(xaxis_title="Hora do dia", yaxis_title="Dia da semana",
    margin=dict(t=10, b=10), height=320)
st.plotly_chart(fig_heat, width="stretch")

st.divider()

# ── 5 e 6 lado a lado ────────────────────────────────────────────────────────
col_c, col_d = st.columns(2)

with col_c:
    st.subheader("5 · Top 10 Restaurantes por Volume")
    df_top = query(SQL_TOP10)
    df_top["label"] = df_top["restaurante"].str.split("—").str[0].str.strip()
    fig_top = px.bar(df_top.sort_values("total_pedidos"),
        x="total_pedidos", y="label", orientation="h", color="regiao",
        labels={"total_pedidos": "Pedidos", "label": "", "regiao": "Região"},
        color_discrete_sequence=px.colors.qualitative.Set2, text="total_pedidos")
    fig_top.update_traces(textposition="outside")
    fig_top.update_layout(margin=dict(t=10, b=10), legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig_top, width="stretch")

with col_d:
    st.subheader("6 · Histograma do Tempo Total de Entrega")
    df_hist = query(SQL_HISTOGRAMA)
    df_hist["bucket_label"] = df_hist["bucket_inicio"].astype(str) + "–" + df_hist["bucket_fim"].astype(str) + " min"
    fig_hist = px.bar(df_hist, x="bucket_label", y="total_entregas",
        labels={"bucket_label": "Tempo de entrega", "total_entregas": "Entregas"},
        color="total_entregas", color_continuous_scale="Blues", text="total_entregas")
    fig_hist.update_traces(textposition="outside")
    fig_hist.update_layout(coloraxis_showscale=False, margin=dict(t=10, b=10), xaxis_tickangle=-35)
    st.plotly_chart(fig_hist, width="stretch")