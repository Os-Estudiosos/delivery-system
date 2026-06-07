#!/bin/bash

caminho_atual=$(pwd)
echo "Lendo arquivos em: $caminho_atual"
echo "-------------------------------------------"

# Encontra arquivos iterando recursivamente pelos subdiretórios
find . -type f ! -name "list-content.sh" | while read -r item; do
    echo "=== Arquivo: $item ==="
    cat "$item"
    echo ""
done
