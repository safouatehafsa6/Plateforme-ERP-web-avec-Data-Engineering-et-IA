#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT_DIR/secrets/postgres"
mkdir -p "$OUT"
umask 077

openssl genrsa -out "$OUT/ca.key" 4096
openssl req -x509 -new -nodes -key "$OUT/ca.key" -sha256 -days 3650 \
  -subj "/CN=BENJEDDOU ERP PostgreSQL Local CA" -out "$OUT/ca.crt"

openssl genrsa -out "$OUT/server.key" 2048
openssl req -new -key "$OUT/server.key" -subj "/CN=postgres-erp" -out "$OUT/server.csr"
cat > "$OUT/server.ext" <<'EOF'
subjectAltName=DNS:postgres-erp
extendedKeyUsage=serverAuth
keyUsage=digitalSignature,keyEncipherment
EOF
openssl x509 -req -in "$OUT/server.csr" -CA "$OUT/ca.crt" -CAkey "$OUT/ca.key" \
  -CAcreateserial -out "$OUT/server.crt" -days 825 -sha256 -extfile "$OUT/server.ext"

chmod 644 "$OUT/ca.crt" "$OUT/server.crt"
chmod 600 "$OUT/server.key"
# Image officielle PostgreSQL Debian : utilisateur postgres généralement UID/GID 999.
if [ "$(id -u)" -eq 0 ]; then
  chown 999:999 "$OUT/server.key"
elif command -v sudo >/dev/null 2>&1; then
  sudo chown 999:999 "$OUT/server.key"
else
  echo "ATTENTION : exécutez sudo chown 999:999 $OUT/server.key pour que PostgreSQL puisse lire la clé." >&2
fi
rm -f "$OUT/server.csr" "$OUT/server.ext" "$OUT/ca.srl"
echo "Certificats créés dans $OUT"
echo "Ne partagez jamais ca.key ni server.key. Ajoutez secrets/postgres/ au .gitignore."
