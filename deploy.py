#!/usr/bin/env python3
import asyncio
import simulator
import destroy
import json
from pathlib import Path

# Importando os módulos da nossa infraestrutura
from infranova import network, databases, compute

# Arquivo para salvar as saídas (o simulador de carga vai precisar ler isso depois)
CTX_FILE = Path("deploy_context.json")

def deploy():
    print("Iniciando o Deploy Automático - DijkFood\n")
    ctx = {}
    
    try:
        # 1. Configura a Rede
        network_ctx = network.setup_network()
        ctx.update(network_ctx)
        
        # 2. Configura os Bancos de Dados e Storage
        db_ctx = databases.setup_databases(network_ctx)
        ctx.update(db_ctx)
        
        # 3. Faz o Build, Push e sobe os Containers no ECS
        compute_ctx = compute.setup_compute(network_ctx, db_ctx)
        ctx.update(compute_ctx)
        
        # Salva o contexto
        CTX_FILE.write_text(json.dumps(ctx, indent=4))
        print(f"URL da API: http://{ctx['alb_dns']}")
        
        # 4. Executa o Simulador de Carga
        print("INICIANDO EXPERIMENTO DE CARGA AUTOMÁTICO")
        api_url = f"http://{ctx['alb_dns']}"
        asyncio.run(simulator.main(api_url))
        
        return ctx
        
    except Exception as e:
        print(f"\nErro durante o deploy ou simulação: {e}")
        # Se der erro no meio, ele também deve destruir o que já criou
        raise e 
        
    finally:
        # 5. Destruição Obrigatória (Independente de sucesso ou erro)
        print("INICIANDO DESTRUIÇÃO DOS RECURSOS")
        destroy.destroy_all()

if __name__ == "__main__":
    deploy()