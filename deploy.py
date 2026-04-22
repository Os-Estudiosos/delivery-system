#!/usr/bin/env python3
import asyncio
import simulator
import destroy
import json
import time
import urllib.request
from urllib.error import URLError, HTTPError
from pathlib import Path

# Importando os módulos da nossa infraestrutura
from infranova import network, databases, compute

# Arquivo para salvar as saídas
CTX_FILE = Path("deploy_context.json")

def wait_for_healthcheck(url: str, max_retries: int = 60, wait_seconds: int = 10):
    """Fica testando a rota /health até ela retornar 200 OK"""
    health_url = f"{url}/health"
    print(f"\nAguardando a API inicializar em {health_url}...")
    print("Isso pode levar de 2 a 5 minutos na primeira vez devido ao download do mapa de São Paulo (OSMnx).")
    
    for i in range(max_retries):
        try:
            # Tenta acessar a rota /health com timeout de 5 segundos
            response = urllib.request.urlopen(health_url, timeout=5)
            if response.getcode() == 200:
                print("\nAPI está 100% pronta e operante!\n")
                return True
        except (URLError, HTTPError) as e:
            print(f"\rTentativa {i+1}/{max_retries}: API ainda ligando... ({e})", end="", flush=True)
        except Exception as e:
            print(f"\rTentativa {i+1}/{max_retries}: Erro de conexão... ({e})", end="", flush=True)
        
        time.sleep(wait_seconds)
        
    raise Exception("\nTimeout: A API não ficou pronta a tempo.")

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
        api_url = f"http://{ctx['alb_dns']}"
        print(f" URL da API: {api_url}")
        
        # 4. AGUARDA A API SUBIR (A correção mágica)
        wait_for_healthcheck(api_url)
        
        # 5. Executa o Simulador de Carga
        print("==================================================")
        print("INICIANDO EXPERIMENTO DE CARGA AUTOMÁTICO")
        print("==================================================")
        asyncio.run(simulator.main(api_url))
        
        return ctx
        
    except Exception as e:
        print(f"\nErro durante o deploy ou simulação: {e}")
        raise e 
        
    finally:
        # 6. Destruição Obrigatória
        print("\n==================================================")
        print("INICIANDO DESTRUIÇÃO DOS RECURSOS")
        print("==================================================")
        destroy.destroy_all()

if __name__ == "__main__":
    deploy()