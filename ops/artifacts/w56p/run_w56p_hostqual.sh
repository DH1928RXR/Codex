#!/usr/bin/env bash
set -euo pipefail

: "${REF:?Set REF to the exact immutable Git commit SHA containing this handoff.}"
REPO="DH1928RXR/Codex"
BASE="https://raw.githubusercontent.com/${REPO}/${REF}/ops/artifacts/w56p"
QUAL_SHA="9bba6d03890254fab829b37bec6e39d5f3f34837200f61102589089b372fb81d"
QUAL_SIZE="51496"
OBS_SHA="69bba65085e43bd0b5c8b49dc923ada345e1609f2e867931b2b51c2514736cb4"
OBS_SIZE="2605"

TMP="$(mktemp -d /tmp/eor_w56p_transport.XXXXXX)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

for f in q00.b64 q01.b64 q02.b64 q03a.b64 q03b1.b64 q03b2.b64 q03c.b64 q03d.b64 o00.b64; do
  curl -fLsS --retry 3 --connect-timeout 10 --max-time 60 "${BASE}/${f}" -o "${TMP}/${f}"
done

cat "${TMP}/q00.b64" "${TMP}/q01.b64" "${TMP}/q02.b64" \
    "${TMP}/q03a.b64" "${TMP}/q03b1.b64" "${TMP}/q03b2.b64" "${TMP}/q03c.b64" "${TMP}/q03d.b64" \
    | base64 -d > "${TMP}/eor_w56p_host_qualification_v1.pyz.zip"
base64 -d < "${TMP}/o00.b64" > "${TMP}/eor_w56p_host_qualification_observer_v1.pyz.zip"

verify() {
  local file="$1" want_size="$2" want_sha="$3" label="$4"
  local got_size got_sha
  got_size="$(wc -c < "$file" | tr -d '[:space:]')"
  got_sha="$(sha256sum "$file" | awk '{print $1}')"
  printf '%s size=%s sha256=%s\n' "$label" "$got_size" "$got_sha"
  [[ "$got_size" == "$want_size" ]] || { echo "${label}_SIZE_MISMATCH" >&2; exit 1; }
  [[ "$got_sha" == "$want_sha" ]] || { echo "${label}_SHA256_MISMATCH" >&2; exit 1; }
}

QUAL="${TMP}/eor_w56p_host_qualification_v1.pyz.zip"
OBS="${TMP}/eor_w56p_host_qualification_observer_v1.pyz.zip"
verify "$QUAL" "$QUAL_SIZE" "$QUAL_SHA" W56P_QUALIFIER_TRANSPORT
verify "$OBS" "$OBS_SIZE" "$OBS_SHA" W56P_OBSERVER_TRANSPORT

OUT="/tmp/eor_w56p_target_host_qualification_$(date -u +%Y%m%dT%H%M%SZ).log"
(
  echo "=== W56p target-host qualification start $(date -Is) ==="
  echo "transport_ref=${REF}"
  echo "qualifier_sha256=${QUAL_SHA}"
  echo "observer_sha256=${OBS_SHA}"
  echo
  echo "=== qualifier ==="
  /usr/bin/python3 -B "$QUAL"
  echo
  echo "=== independent observer ==="
  /usr/bin/python3 -B "$OBS"
  echo
  echo "=== W56p target-host qualification complete $(date -Is) ==="
) 2>&1 | tee "$OUT"

echo "W56P_HANDOFF_COMPLETE"
echo "log=$OUT"
echo "qualification_receipt=/tmp/eor_w56p_hostqual_v1_bacea23b868dcc6b0.receipt.json"
