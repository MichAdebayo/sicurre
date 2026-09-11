# Nginx Reverse Proxy

The shared server runs one host-network `nginx-proxy` container from `/opt/nginx-proxy`.
Sicurre itself binds only to loopback port `8002`; nginx is the public entrypoint.

## Server Files

Create these folders on the server:

```bash
sudo mkdir -p /opt/nginx-proxy/conf.d /opt/nginx-proxy/ssl /opt/nginx-proxy/logs
```

Copy the vhost files:

```bash
sudo cp deploy/nginx/conf.d/*.conf /opt/nginx-proxy/conf.d/
```

Cloudflare Origin CA files must be installed as:

```text
/opt/nginx-proxy/ssl/sicurre-origin.pem
/opt/nginx-proxy/ssl/sicurre-origin-key.pem
```

Start or reload the proxy:

```bash
docker compose -f deploy/nginx/nginx-proxy.compose.yml up -d
docker exec nginx-proxy nginx -t
docker exec nginx-proxy nginx -s reload
```
