#!/usr/bin/env bash
set -euo pipefail
: "${REF:?REF must be an immutable Git commit SHA}"
BASE="https://raw.githubusercontent.com/DH1928RXR/Codex/${REF}/ops/artifacts/c03_t05/v2"
D="$(mktemp -d /tmp/eor_c03_t05_transport_v2.XXXXXX)"
trap 'rm -rf "$D"' EXIT
B64="$D/carrier.b64"
PYZ="$D/eor_c03_t05_observed_genesis_v1.pyz"
: > "$B64"
for i in 00 01 02 03; do
  curl -fLsS --retry 3 "$BASE/carrier.part${i}.b64" >> "$B64"
done
echo "1ee0a4b586529df62f74b62d03eeb848fc9616f78d010f0ad85c4ea866a2a02a  $B64" | sha256sum -c -
base64 -d "$B64" > "$PYZ"
[ "$(wc -c < "$PYZ")" -eq 46064 ]
echo "14adc592cea2e7c11c462a2b09acab0d1420a0ec1ba174c03d11cb7b7f446cab  $PYZ" | sha256sum -c -
sudo /usr/bin/python3 -B "$PYZ"
