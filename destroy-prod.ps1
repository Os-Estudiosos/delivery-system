# destroy-prod.ps1
$credPath = "$env:USERPROFILE\.aws\credentials"

if (-not (Test-Path $credPath)) {
    Write-Error "Arquivo $credPath não encontrado. Cole as credenciais do Learner Lab lá."
    exit 1
}

$credentials = Get-Content $credPath

function Get-CredValue($key) {
    $line = $credentials | Where-Object { $_ -match "^\s*$key\s*=" }
    if (-not $line) {
        Write-Error "Chave '$key' não encontrada no credentials."
        exit 1
    }
    return ($line -split "=", 2)[1].Trim()
}

$accessKey    = Get-CredValue "aws_access_key_id"
$secretKey    = Get-CredValue "aws_secret_access_key"
$sessionToken = Get-CredValue "aws_session_token"

Write-Host "Credenciais carregadas. Iniciando destroy..."

$dbPassword = Read-Host "Digite a senha do banco de dados RDS" -AsSecureString
$dbPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($dbPassword)
)

terraform -chdir="infra/terraform-aws" destroy `
  -var-file="prod.tfvars" `
  -var="aws_access_key_id=$accessKey" `
  -var="aws_secret_access_key=$secretKey" `
  -var="aws_session_token=$sessionToken" `
  -var="db_password=$dbPasswordPlain"
