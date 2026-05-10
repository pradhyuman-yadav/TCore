# Deploying TradeCore via GitHub Actions + Portainer

## How it works

```
git push main
    │
    ▼
GitHub Actions (ci.yml)
    ├─ Run pytest against TimescaleDB service container
    ├─ Build backend image → ghcr.io/YOU/tradecore-backend:latest
    ├─ Build frontend image → ghcr.io/YOU/tradecore-frontend:latest
    └─ POST to Portainer webhook
                │
                ▼
        Portainer pulls new images
        docker compose up -d  (zero-downtime rolling restart)
```

---

## One-time setup

### 1. Push to GitHub

```powershell
cd C:\Users\pradh\Downloads\colaberry\Finance
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 2. Make GHCR packages public (so Portainer can pull without credentials)

1. Go to `https://github.com/YOUR_USERNAME?tab=packages`
2. Click `tradecore-backend` → Settings → Change visibility → **Public**
3. Repeat for `tradecore-frontend`

Alternatively keep them private and add a GHCR credential in Portainer:  
`Portainer → Registries → Add registry → GitHub Container Registry`

### 3. Create Portainer stack

In Portainer:

1. **Stacks → Add stack → Repository**
2. Set:
   | Field | Value |
   |-------|-------|
   | Repository URL | `https://github.com/YOUR_USERNAME/YOUR_REPO` |
   | Repository reference | `refs/heads/main` |
   | Compose path | `tradecore/docker-compose.prod.yml` |
   | Auth (if private repo) | GitHub PAT with `repo` scope |
3. **Enable GitOps updates** → toggle ON  
   → Portainer will poll the repo every few minutes for changes (or rely on webhook below)

### 4. Set environment variables in Portainer

In the stack's **Environment variables** section, add:

| Variable | Example value |
|----------|--------------|
| `GHCR_OWNER` | `your-github-username` |
| `DB_USER` | `tradecore` |
| `DB_PASSWORD` | `a-strong-password` |
| `DB_NAME` | `tradecore` |
| `CLAUDE_ACCESS_TOKEN` | *(from `make auth` output)* |
| `CLAUDE_REFRESH_TOKEN` | *(from `make auth` output)* |
| `CLAUDE_TOKEN_EXPIRES_AT` | *(from `make auth` output)* |
| `TRADING_MODE` | `paper` |
| `CCXT_EXCHANGE` | `binance` |
| `FRONTEND_PORT` | `3000` *(or 80 if no reverse proxy)* |

### 5. Get the Portainer webhook URL

1. In your stack → **GitOps updates** → copy the **Webhook URL**
2. In GitHub → repo → **Settings → Secrets and variables → Actions**
3. Add secret: `PORTAINER_WEBHOOK_URL` = the copied URL

### 6. Add GitHub secret for the webhook

That's all. Now every `git push main` will:
- Run tests (fails fast if broken)
- Push new images to GHCR
- Trigger Portainer to pull and redeploy

---

## Refreshing Claude tokens

Claude OAuth tokens expire. Refresh them locally and update Portainer env vars:

```powershell
# Run locally — updates tradecore/.env with fresh tokens
make auth

# Copy the 3 CLAUDE_* values from tradecore/.env
# Paste them into Portainer stack → Environment variables → Update
```

Or automate token refresh: add a Portainer scheduled task that runs  
`docker exec tradecore-backend-1 python -c "import asyncio; from app.services.claude_auth import get_access_token; asyncio.run(get_access_token())"` — the auto-refresh in `claude_auth.py` will renew the token and update the in-process env.

---

## Checking deployment health

```bash
# On server or via Portainer console:
curl http://localhost:8000/health
# {"status":"ok","db":"connected","scheduler":"running",...}

# Portainer → Containers → tradecore-backend → Logs
```
