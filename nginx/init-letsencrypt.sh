#!/usr/bin/env bash
# One-time bootstrap for Let's Encrypt certs on a fresh host.
#
# nginx's 443 server block requires a certificate to exist just to start —
# but certbot's webroot challenge requires nginx to already be serving
# /.well-known/acme-challenge/ on port 80. This script breaks that chicken-
# and-egg problem the standard way: boot nginx with a throwaway self-signed
# cert, run the real ACME challenge through it, then swap in the real cert
# and reload. Re-run is safe (skips issuance if a cert already exists);
# actual renewal is handled by the long-running `certbot` service in
# docker-compose.prod.yml.
#
# Usage: DOMAIN=api.example.com EMAIL=admin@example.com ./nginx/init-letsencrypt.sh

set -euo pipefail

: "${DOMAIN:?Set DOMAIN, e.g. DOMAIN=api.example.com}"
: "${EMAIL:?Set EMAIL, e.g. EMAIL=admin@example.com}"

COMPOSE="docker compose -f docker-compose.prod.yml"
CERT_PATH="/etc/letsencrypt/live/${DOMAIN}"

if $COMPOSE run --rm certbot sh -c "[ -d '${CERT_PATH}' ]" 2>/dev/null; then
  echo "Certificate for ${DOMAIN} already exists — skipping issuance."
  echo "(To force reissuance, remove the certbot_conf volume first.)"
  exit 0
fi

echo "### Creating a temporary self-signed certificate so nginx can boot ..."
$COMPOSE run --rm --entrypoint sh certbot -c "
  mkdir -p '${CERT_PATH}' &&
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout '${CERT_PATH}/privkey.pem' \
    -out '${CERT_PATH}/fullchain.pem' \
    -subj '/CN=localhost'
"

echo "### Starting nginx ..."
$COMPOSE up -d nginx

echo "### Deleting the temporary certificate ..."
$COMPOSE run --rm --entrypoint sh certbot -c "rm -rf '${CERT_PATH}'"

echo "### Requesting the real certificate from Let's Encrypt ..."
$COMPOSE run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d "${DOMAIN}" \
  --email "${EMAIL}" \
  --rsa-key-size 2048 \
  --agree-tos \
  --non-interactive

echo "### Reloading nginx with the real certificate ..."
$COMPOSE exec nginx nginx -s reload

echo "Done. ${DOMAIN} is now serving a real Let's Encrypt certificate."
