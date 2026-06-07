#!/bin/bash
set -euxo pipefail

# ── variáveis injetadas pelo Terraform ───────────────────────────────────────
AWS_REGION="${aws_region}"
ATHENA_DB="${athena_db}"
ATHENA_WG="${athena_workgroup}"
RESULTS_BUCKET="${results_bucket}"
DATA_LAKE_BUCKET="${data_lake_bucket}"
DASHBOARD_S3_KEY="${dashboard_s3_key}"

# ── sistema ───────────────────────────────────────────────────────────────────
dnf update -y
dnf install -y python3 python3-pip

# ── dependências Python
# --ignore-installed evita conflito com pacotes instalados pelo rpm
pip3 install --ignore-installed \
  streamlit \
  plotly \
  pandas \
  boto3 \
  pyarrow

# ── baixa o dashboard do S3 ───────────────────────────────────────────────────
mkdir -p /opt/dijkfood
aws s3 cp "s3://$DATA_LAKE_BUCKET/$DASHBOARD_S3_KEY" /opt/dijkfood/dashboard_prod.py

# ── serviço systemd ───────────────────────────────────────────────────────────
cat > /etc/systemd/system/streamlit.service << EOF
[Unit]
Description=CidadeX Analytics Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/dijkfood
Environment="AWS_REGION=$AWS_REGION"
Environment="ATHENA_DB=$ATHENA_DB"
Environment="ATHENA_WG=$ATHENA_WG"
Environment="RESULTS_BUCKET=$RESULTS_BUCKET"
ExecStart=/usr/local/bin/streamlit run /opt/dijkfood/dashboard_prod.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.headless true \
  --browser.gatherUsageStats false
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable streamlit
systemctl start streamlit