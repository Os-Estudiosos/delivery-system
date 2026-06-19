$env:TF_VAR_db_password = "12345678"

uv run deploy.py --only-destroy

uv run deploy.py --no-destroy
