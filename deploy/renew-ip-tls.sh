#!/bin/sh
# devtest operator hook: never copy the ACME account or parent private directory.
set -eu
instance=/opt/juanzhan-dev/test-instance
source="$instance/tls/config/live/8.153.19.221"
target="$instance/tls-serving"
install -d -m 0750 -o 101 -g 101 "$target"
install -m 0644 -o 101 -g 101 "$source/fullchain.pem" "$target/fullchain.pem.new"
install -m 0600 -o 101 -g 101 "$source/privkey.pem" "$target/privkey.pem.new"
mv "$target/fullchain.pem.new" "$target/fullchain.pem"
mv "$target/privkey.pem.new" "$target/privkey.pem"
if docker inspect juanzhan-test-ip-gateway-1 >/dev/null 2>&1; then
  docker exec juanzhan-test-ip-gateway-1 nginx -t
  docker exec juanzhan-test-ip-gateway-1 nginx -s reload
fi
