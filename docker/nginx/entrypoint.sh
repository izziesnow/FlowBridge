#!/bin/sh
# Use the certificate mounted at /etc/nginx/certs if there is one. Otherwise create a
# self-signed certificate so HTTPS works out of the box on a laptop or test server.
set -eu
CERT_DIR=/etc/nginx/certs
mkdir -p "$CERT_DIR"
if [ ! -f "$CERT_DIR/server.crt" ] || [ ! -f "$CERT_DIR/server.key" ]; then
  echo "No certificate mounted; generating a self-signed one for ${SERVER_NAME:-localhost}"
  openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -subj "/CN=${SERVER_NAME:-localhost}/O=Flowbridge demo (fictional ZTL)" \
    -keyout "$CERT_DIR/server.key" -out "$CERT_DIR/server.crt" >/dev/null 2>&1
fi
