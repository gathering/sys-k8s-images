#!/bin/sh
# The web client answers on IPv4 and IPv6, with a read-only root filesystem
# as on the cluster. Usage: test.sh <image>
set -eu

image=$1
name=test-shlink-web-client-$$

docker run -d --name "$name" --read-only --tmpfs /tmp "$image" >/dev/null
trap 'docker rm -f "$name" >/dev/null' EXIT

for url in http://127.0.0.1:8080/ "http://[::1]:8080/"; do
    ok=
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        if docker exec "$name" wget -qO- "$url" | grep -q 'id="root"'; then
            ok=1
            break
        fi
        sleep 1
    done
    if [ -z "$ok" ]; then
        echo "FAIL: no index.html on $url" >&2
        docker logs "$name" >&2
        exit 1
    fi
    echo "ok: $url"
done
