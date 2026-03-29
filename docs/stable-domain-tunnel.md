# Stable Domain Tunnel Setup

This document captures the stable-domain setup for exposing the local FastAPI app through a named Cloudflare Tunnel instead of a temporary `trycloudflare.com` URL.

## Domain
- Root domain: `aqwerty321.me`
- Recommended app subdomain: `slack.aqwerty321.me`

## Current Status
- Cloudflare nameservers were entered in Namecheap.
- DNS propagation had not completed at the time this document was created.
- The domain was still delegated to:
  - `dns1.registrar-servers.com`
  - `dns2.registrar-servers.com`

## Verify Propagation
Run until the output changes to the Cloudflare nameservers:

```bash
dig NS aqwerty321.me +short
dig NS aqwerty321.me @1.1.1.1 +short
dig NS aqwerty321.me @8.8.8.8 +short
```

## Named Tunnel Commands
Once propagation is complete:

### 1. Login cloudflared to the Cloudflare account
```bash
cloudflared tunnel login
```

This will open a browser window to authorize `cloudflared` for the Cloudflare zone.

### 2. Create the named tunnel
```bash
cloudflared tunnel create k8swhisperer
```

This outputs a tunnel UUID and creates a credentials file under `~/.cloudflared/`.

### 3. Route DNS for the Slack subdomain
```bash
cloudflared tunnel route dns k8swhisperer slack.aqwerty321.me
```

### 4. Create a local tunnel config
Use the template stored in `deploy/cloudflared/config.template.yml` and replace:
- `<TUNNEL_ID>`
- `<HOME_DIR>`
- `localhost:8010` if the app runs on a different port

Example final config:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/<user>/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: slack.aqwerty321.me
    service: http://localhost:8010
  - service: http_status:404
```

### 5. Run the FastAPI app locally
```bash
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8010
```

### 6. Run the named tunnel
```bash
cloudflared tunnel --config deploy/cloudflared/config.yml run k8swhisperer
```

## App Configuration
Once the hostname resolves and the tunnel is running, set:

```env
PUBLIC_BASE_URL=https://slack.aqwerty321.me
```

Slack interactive callback URL:

```text
https://slack.aqwerty321.me/api/slack/actions
```

## Existing DNS Records
The zone import showed existing records that appear to be in active use:
- GitHub Pages style `A` records for the apex domain
- `www` CNAME
- Namecheap mail forwarding `MX` records
- SPF `TXT` record

Do not remove those unless you intentionally want to disable the existing site or mail setup.

## Why This Is Better Than Quick Tunnels
- Stable callback URL for Slack
- No manual callback URL updates on every restart
- Lower demo risk
- No Slack manifest-sync service required
