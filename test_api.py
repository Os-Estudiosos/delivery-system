from utils.tools import make_ec2_client, get_latest_amazon_linux_ami

def test_connection():
    REGION = "us-east-1" # Região padrão do AWS Academy [cite: 97]
    
    print("--- Testando Conexão com AWS ---")
    try:
        # Tenta criar o cliente e buscar a AMI
        # Isso valida se o boto3 achou seu arquivo ~/.aws/credentials
        ami_id = get_latest_amazon_linux_ami(REGION)
        
        print(f"\n✅ SUCESSO!")
        print(f"Conexão estabelecida. O ID da imagem mais recente é: {ami_id}")
        print("Sua máquina está autorizada a comandar a AWS.")
        
    except Exception as e:
        print(f"\n❌ ERRO DE CONEXÃO:")
        print(str(e))
        print("\nVerifique se:")
        print("1. O 'Session Token' no arquivo credentials não expirou.")
        print("2. O nome do perfil no arquivo é [default].")

if __name__ == "__main__":
    test_connection()