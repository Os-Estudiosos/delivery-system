#!/usr/bin/env bash
# =============================================================================
# upload_glue_script.sh
# Faz upload do script PySpark para o S3 após o terraform apply.
#
# Uso:
#   cd analytics
#   bash glue/upload_glue_script.sh
#
# Pré-requisitos:
#   - AWS CLI configurado com credenciais válidas
#   - Bucket dijkfood-data-lake já criado (terraform apply concluído)
# =============================================================================

set -euo pipefail

BUCKET="dijkfood-data-lake"
SCRIPT_LOCAL="$(dirname "$0")/etl_rds_to_s3.py"
SCRIPT_S3="s3://${BUCKET}/glue/etl_rds_to_s3.py"

echo "📤  Fazendo upload do script Glue..."
echo "    origem : ${SCRIPT_LOCAL}"
echo "    destino: ${SCRIPT_S3}"

aws s3 cp "${SCRIPT_LOCAL}" "${SCRIPT_S3}"

echo ""
echo "✅  Upload concluído!"
echo ""
echo "Para disparar o Job manualmente (sem esperar o trigger diário):"
echo ""
echo "  aws glue start-job-run --job-name dijkfood-etl-rds-to-s3"
echo ""
echo "Para acompanhar o status:"
echo ""
echo "  aws glue get-job-runs --job-name dijkfood-etl-rds-to-s3 \\"
echo "    --query 'JobRuns[0].{Status:JobRunState,Start:StartedOn,Duration:ExecutionTime}' \\"
echo "    --output table"