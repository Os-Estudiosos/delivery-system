#!/usr/bin/env bash
# =============================================================================
# upload_dashboard.sh
# Faz upload do dashboard_prod.py para o S3 antes do terraform apply.
# Também pode ser usado para atualizar o dashboard sem recriar a EC2.
#
# Uso:
#   cd analytics
#   bash upload_dashboard.sh
#
#   # Para atualizar o dashboard na EC2 sem recriar:
#   bash upload_dashboard.sh --restart
# =============================================================================

set -euo pipefail

BUCKET="dijkfood-data-lake"
KEY="glue-scripts/dashboard_prod.py"
SCRIPT_LOCAL="$(dirname "$0")/dashboard_prod.py"
INSTANCE_NAME="dijkfood-dashboard"

echo "📤  Fazendo upload do dashboard..."
aws s3 cp "$SCRIPT_LOCAL" "s3://$BUCKET/$KEY"
echo "✅  Upload concluído: s3://$BUCKET/$KEY"

# se --restart, baixa na EC2 e reinicia o serviço
if [[ "${1:-}" == "--restart" ]]; then
  echo ""
  echo "🔄  Buscando instância EC2..."
  INSTANCE_ID=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text)

  if [[ "$INSTANCE_ID" == "None" || -z "$INSTANCE_ID" ]]; then
    echo "⚠️   Instância não encontrada. Sobe a EC2 com terraform apply primeiro."
    exit 1
  fi

  echo "   Instância: $INSTANCE_ID"
  echo "   Atualizando dashboard via SSM..."

  aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters '{"commands":[
      "aws s3 cp s3://dijkfood-data-lake/glue-scripts/dashboard_prod.py /opt/dijkfood/dashboard_prod.py",
      "systemctl restart streamlit"
    ]}' \
    --output table \
    --query 'Command.{Status:StatusDetails,CommandId:CommandId}'

  echo ""
  echo "✅  Dashboard atualizado na EC2!"
fi
