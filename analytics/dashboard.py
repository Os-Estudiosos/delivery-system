"""
dashboard.py — CidadeX Analytics Dashboard
Visualiza os 6 indicadores operacionais a partir do PostgreSQL local.

Usage:
    cd analytics
    uv run streamlit run dashboard.py
    # ou com DB_URL customizado:
    DB_URL=postgresql://user:pass@localhost:5432/dijkfood uv run streamlit run dashboard.py
"""

import os
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, text

# ── config ───────────────────────────────────────────────────────────────────
DB_URL = os.getenv(
    "DB_URL",
    "postgresql://postgres:postgres@localhost:5432/dijkfood",
)

st.set_page_config(
    page_title="CidadeX — Analytics",
    page_icon="🛵",
    layout="wide",
)

# ── conexão (cached) ──────────────────────────────────────────────────────────
@st.cache_resource
def get_engine():
    return create_engine(DB_URL)


@st.cache_data(ttl=60)
def query(sql: str) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn)


# ── queries ───────────────────────────────────────────────────────────────────
SQL_VOLUME = """
SELECT
    DATE(o.created_at AT TIME ZONE 'America/Sao_Paulo') AS dia,
    COUNT(*) AS total_pedidos
FROM orders o
GROUP BY dia
ORDER BY dia;
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
    FROM event
)
SELECT
    status,
    ROUND(AVG(EXTRACT(EPOCH FROM (updated_at - ts_anterior)) / 60.0)::numeric, 2) AS tempo_medio_minutos
FROM eventos_com_anterior
WHERE ts_anterior IS NOT NULL
GROUP BY status
ORDER BY MIN(updated_at);
"""

SQL_REGIAO = """
SELECT
    r.name AS regiao,
    COUNT(o.id) AS total_pedidos,
    ROUND(COUNT(o.id) * 100.0 / SUM(COUNT(o.id)) OVER (), 2) AS percentual
FROM orders o
JOIN users u  ON u.id = o.user_id
JOIN region r ON r.id = u.region_id
GROUP BY r.name
ORDER BY total_pedidos DESC;
"""

SQL_HEATMAP = """
SELECT
    TO_CHAR(o.created_at AT TIME ZONE 'America/Sao_Paulo', 'Day') AS dia_semana,
    EXTRACT(DOW  FROM o.created_at AT TIME ZONE 'America/Sao_Paulo')::int AS dow_ordem,
    EXTRACT(HOUR FROM o.created_at AT TIME ZONE 'America/Sao_Paulo')::int AS hora,
    COUNT(*) AS total_pedidos
FROM orders o
GROUP BY dia_semana, dow_ordem, hora
ORDER BY dow_ordem, hora;
"""

SQL_TOP10 = """
SELECT
    r.name      AS restaurante,
    reg.name    AS regiao,
    kt.type     AS cozinha,
    COUNT(o.id) AS total_pedidos
FROM orders o
JOIN restaurant   r   ON r.id   = o.restaurant_id
JOIN region       reg ON reg.id = r.region_id
JOIN kitchen_type kt  ON kt.id  = r.kitchen_type_id
GROUP BY r.name, reg.name, kt.type
ORDER BY total_pedidos DESC
LIMIT 10;
"""

SQL_HISTOGRAMA = """
WITH tempos AS (
    SELECT
        d.id AS delivery_id,
        MIN(e.updated_at) FILTER (WHERE e.status = 'CONFIRMED') AS ts_confirmed,
        MAX(e.updated_at) FILTER (WHERE e.status = 'DELIVERED') AS ts_delivered
    FROM delivery d
    JOIN event e ON e.delivery_id = d.id
    GROUP BY d.id
    HAVING
        MIN(e.updated_at) FILTER (WHERE e.status = 'CONFIRMED') IS NOT NULL
        AND MAX(e.updated_at) FILTER (WHERE e.status = 'DELIVERED') IS NOT NULL
),
duracoes AS (
    SELECT
        ROUND(EXTRACT(EPOCH FROM (ts_delivered - ts_confirmed)) / 60.0)::int AS minutos
    FROM tempos
)
SELECT
    (minutos / 10) * 10     AS bucket_inicio,
    (minutos / 10) * 10 + 9 AS bucket_fim,
    COUNT(*)                AS total_entregas
FROM duracoes
GROUP BY bucket_inicio
ORDER BY bucket_inicio;
"""

SQL_KPIs = """
SELECT
    (SELECT COUNT(*) FROM orders)                                        AS total_pedidos,
    (SELECT COUNT(*) FROM delivery)                                      AS total_entregas,
    (SELECT COUNT(DISTINCT courier_id) FROM delivery)                    AS entregadores_ativos,
    (SELECT COUNT(*) FROM restaurant)                                    AS restaurantes
"""

# ── ordem canônica dos status ─────────────────────────────────────────────────
STATUS_ORDER = [
    "PREPARING",
    "READY_FOR_PICKUP",
    "PICKED_UP",
    "IN_TRANSIT",
    "DELIVERED",
]

DIAS_PT = {
    0: "Dom", 1: "Seg", 2: "Ter", 3: "Qua", 4: "Qui", 5: "Sex", 6: "Sáb"
}

# ── layout ────────────────────────────────────────────────────────────────────
st.title("🛵 CidadeX — Analytics Dashboard")
st.caption(f"Banco: `{DB_URL.split('@')[-1]}`  •  Atualização a cada 60s")

# ── KPIs ──────────────────────────────────────────────────────────────────────
kpis = query(SQL_KPIs).iloc[0]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total de Pedidos",    f"{int(kpis['total_pedidos']):,}".replace(",", "."))
k2.metric("Total de Entregas",   f"{int(kpis['total_entregas']):,}".replace(",", "."))
k3.metric("Entregadores Ativos", f"{int(kpis['entregadores_ativos']):,}".replace(",", "."))
k4.metric("Restaurantes",        f"{int(kpis['restaurantes']):,}".replace(",", "."))

st.divider()

# ── 1. Volume de pedidos no tempo ─────────────────────────────────────────────
st.subheader("1 · Volume de Pedidos no Tempo")
df_vol = query(SQL_VOLUME)
df_vol["dia"] = pd.to_datetime(df_vol["dia"])
fig_vol = px.area(
    df_vol,
    x="dia",
    y="total_pedidos",
    labels={"dia": "Data", "total_pedidos": "Pedidos"},
    color_discrete_sequence=["#FF6B35"],
)
fig_vol.update_layout(margin=dict(t=10, b=10))
st.plotly_chart(fig_vol, use_container_width=True)

st.divider()

# ── 2 e 3 lado a lado ────────────────────────────────────────────────────────
col_a, col_b = st.columns(2)

# 2. Tempo médio por estado
with col_a:
    st.subheader("2 · Tempo Médio por Estado")
    df_tempo = query(SQL_TEMPO_ESTADO)
    df_tempo["status"] = pd.Categorical(
        df_tempo["status"], categories=STATUS_ORDER, ordered=True
    )
    df_tempo = df_tempo.sort_values("status")
    fig_tempo = px.bar(
        df_tempo,
        x="tempo_medio_minutos",
        y="status",
        orientation="h",
        labels={"tempo_medio_minutos": "Minutos (média)", "status": "Estado"},
        color="tempo_medio_minutos",
        color_continuous_scale="Oranges",
        text="tempo_medio_minutos",
    )
    fig_tempo.update_traces(texttemplate="%{text:.1f} min", textposition="outside")
    fig_tempo.update_layout(coloraxis_showscale=False, margin=dict(t=10, b=10))
    st.plotly_chart(fig_tempo, use_container_width=True)

# 3. Distribuição por região
with col_b:
    st.subheader("3 · Distribuição por Região")
    df_reg = query(SQL_REGIAO)
    fig_reg = px.pie(
        df_reg,
        names="regiao",
        values="total_pedidos",
        hole=0.45,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_reg.update_traces(textinfo="label+percent", pull=[0.03] * len(df_reg))
    fig_reg.update_layout(margin=dict(t=10, b=10), showlegend=False)
    st.plotly_chart(fig_reg, use_container_width=True)

st.divider()

# ── 4. Heatmap de demanda ─────────────────────────────────────────────────────
st.subheader("4 · Heatmap de Demanda por Horário e Dia da Semana")
df_heat = query(SQL_HEATMAP)
df_heat["dia_label"] = df_heat["dow_ordem"].map(DIAS_PT)

pivot = (
    df_heat.pivot_table(
        index="dia_label",
        columns="hora",
        values="total_pedidos",
        aggfunc="sum",
        fill_value=0,
    )
    .reindex([DIAS_PT[i] for i in sorted(DIAS_PT)])
)

fig_heat = go.Figure(
    go.Heatmap(
        z=pivot.values,
        x=[f"{h:02d}h" for h in pivot.columns],
        y=pivot.index.tolist(),
        colorscale="YlOrRd",
        hoverongaps=False,
        hovertemplate="Dia: %{y}<br>Hora: %{x}<br>Pedidos: %{z}<extra></extra>",
    )
)
fig_heat.update_layout(
    xaxis_title="Hora do dia",
    yaxis_title="Dia da semana",
    margin=dict(t=10, b=10),
    height=320,
)
st.plotly_chart(fig_heat, use_container_width=True)

st.divider()

# ── 5 e 6 lado a lado ────────────────────────────────────────────────────────
col_c, col_d = st.columns(2)

# 5. Top 10 restaurantes
with col_c:
    st.subheader("5 · Top 10 Restaurantes por Volume")
    df_top = query(SQL_TOP10)
    df_top["label"] = df_top["restaurante"].str.split("—").str[0].str.strip()
    fig_top = px.bar(
        df_top.sort_values("total_pedidos"),
        x="total_pedidos",
        y="label",
        orientation="h",
        color="regiao",
        labels={"total_pedidos": "Pedidos", "label": "", "regiao": "Região"},
        color_discrete_sequence=px.colors.qualitative.Set2,
        text="total_pedidos",
    )
    fig_top.update_traces(textposition="outside")
    fig_top.update_layout(margin=dict(t=10, b=10), legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig_top, use_container_width=True)

# 6. Histograma tempo total de entrega
with col_d:
    st.subheader("6 · Histograma do Tempo Total de Entrega")
    df_hist = query(SQL_HISTOGRAMA)
    df_hist["bucket_label"] = df_hist["bucket_inicio"].astype(str) + "–" + df_hist["bucket_fim"].astype(str) + " min"
    fig_hist = px.bar(
        df_hist,
        x="bucket_label",
        y="total_entregas",
        labels={"bucket_label": "Tempo de entrega", "total_entregas": "Entregas"},
        color="total_entregas",
        color_continuous_scale="Blues",
        text="total_entregas",
    )
    fig_hist.update_traces(textposition="outside")
    fig_hist.update_layout(
        coloraxis_showscale=False,
        margin=dict(t=10, b=10),
        xaxis_tickangle=-35,
    )
    st.plotly_chart(fig_hist, use_container_width=True)
