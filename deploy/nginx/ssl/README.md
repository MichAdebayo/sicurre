# Sicurre Origin Certificate

This directory is a local staging location only. It must contain no committed
certificate or private key.

Create a Cloudflare Origin CA certificate for `sicurre.com` and `*.sicurre.com`
in the Cloudflare dashboard, then place the files locally as:

```text
sicurre-origin.pem
sicurre-origin-key.pem
```

Copy them to the shared host proxy as:

```text
/opt/nginx-proxy/ssl/sicurre-origin.pem
/opt/nginx-proxy/ssl/sicurre-origin-key.pem
```

Set the key file to mode `600`, keep the directory restricted to server
administrators, then validate and reload `nginx-proxy`. The parent Nginx
README contains the complete proxy commands.
