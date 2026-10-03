#!/usr/bin/env bash
# Local TLS integration checks. No Kubernetes access or existing credentials.
set -o pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd) || exit 1
source "$ROOT/DevOps_K8s_Sentinel_FINAL_GP.sh"
for tool in openssl python3; do
    command -v "$tool" >/dev/null 2>&1 || { printf 'ERROR: %s is required\n' "$tool" >&2; exit 2; }
done
fixture_dir=$(mktemp -d "$HOME/.devopsonm-tls-tests.XXXXXXXX") || exit 2
server_pid=
finish() {
    if [[ -n $server_pid ]]; then
        kill "$server_pid" 2>/dev/null || :
        wait "$server_pid" 2>/dev/null || :
    fi
    case $fixture_dir in "$HOME"/.devopsonm-tls-tests.*) rm -rf -- "$fixture_dir";; esac
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
RUN_DIR="$fixture_dir/runtime"
mkdir -p -- "$RUN_DIR" "$fixture_dir/empty-trust" || exit 2
SENTINEL_CONTEXT=fixture SENTINEL_NAMESPACE=fixture TLS_TIMEOUT=3
passed=0 failed=0
check() {
    local label=$1; shift
    if "$@"; then
        printf 'PASS %s\n' "$label"; ((passed+=1))
    else
        printf 'FAIL %s\n' "$label"; ((failed+=1))
    fi
}
not_contains() { ! grep -Eq -- "$1" "$2"; }

# All keys are generated here, used only for local signing/server fixtures, and
# removed by the EXIT trap. OpenSSL diagnostics stay in the private directory.
make_certificates() {
    openssl req -x509 -newkey rsa:2048 -nodes -days 3 \
        -subj /CN=Sentinel-Test-Root -keyout "$fixture_dir/root.key" \
        -out "$fixture_dir/root.pem" \
        -addext 'basicConstraints=critical,CA:TRUE' \
        -addext 'keyUsage=critical,keyCertSign,cRLSign' || return
    openssl req -new -newkey rsa:2048 -nodes \
        -subj /CN=Sentinel-Test-Intermediate -keyout "$fixture_dir/intermediate.key" \
        -out "$fixture_dir/intermediate.csr" || return
    printf '%s\n' 'basicConstraints=critical,CA:TRUE,pathlen:0' \
        'keyUsage=critical,keyCertSign,cRLSign' 'subjectKeyIdentifier=hash' \
        'authorityKeyIdentifier=keyid,issuer' > "$fixture_dir/intermediate.ext"
    openssl x509 -req -in "$fixture_dir/intermediate.csr" \
        -CA "$fixture_dir/root.pem" -CAkey "$fixture_dir/root.key" \
        -CAcreateserial -days 2 -extfile "$fixture_dir/intermediate.ext" \
        -out "$fixture_dir/intermediate.pem" || return
    openssl req -new -newkey rsa:2048 -nodes -subj /CN=localhost \
        -keyout "$fixture_dir/leaf.key" -out "$fixture_dir/leaf.csr" || return
    printf '%s\n' 'basicConstraints=critical,CA:FALSE' \
        'keyUsage=critical,digitalSignature,keyEncipherment' \
        'extendedKeyUsage=serverAuth' 'subjectAltName=DNS:localhost' \
        'subjectKeyIdentifier=hash' 'authorityKeyIdentifier=keyid,issuer' > "$fixture_dir/leaf.ext"
    openssl x509 -req -in "$fixture_dir/leaf.csr" \
        -CA "$fixture_dir/intermediate.pem" -CAkey "$fixture_dir/intermediate.key" \
        -CAcreateserial -days 1 -extfile "$fixture_dir/leaf.ext" \
        -out "$fixture_dir/leaf.pem" || return
    openssl req -x509 -newkey rsa:2048 -nodes -days 3 \
        -subj /CN=Sentinel-Unrelated-Root -keyout "$fixture_dir/unrelated.key" \
        -out "$fixture_dir/unrelated.pem" \
        -addext 'basicConstraints=critical,CA:TRUE' || return
    cat "$fixture_dir/leaf.pem" "$fixture_dir/intermediate.pem" > "$fixture_dir/chain.pem"
}
if ! make_certificates > "$fixture_dir/generation.log" 2>&1; then
    printf 'ERROR: generating local certificate fixtures failed\n' >&2
    exit 2
fi
openssl verify -CAfile "$fixture_dir/root.pem" -untrusted "$fixture_dir/intermediate.pem" \
    "$fixture_dir/leaf.pem" > "$fixture_dir/fixture-verify.txt" 2>&1
check 'generated root/intermediate/leaf chain is valid' test "$?" -eq 0

# Mock the exact public certificate projection. No kubectl command is executed.
fixture_cert="$fixture_dir/chain.pem" fixture_ca="$fixture_dir/root.pem"
kctl_ns() {
    [[ $# == 5 && $1 == get && $2 == secret && $3 == fixture-tls && $4 == -o && $5 == go-template=* ]] || return 2
    openssl base64 -A -in "$fixture_cert" || return
    printf '\t'
    [[ -z $fixture_ca ]] || openssl base64 -A -in "$fixture_ca" || return
    printf '\n'
}

certificate_trust_secret_report fixture-tls > "$fixture_dir/chain-report.txt" 2>&1; rc=$?
check 'complete chain succeeds' test "$rc" -eq 0
check 'intermediate from tls.crt participates in trust verification' grep -Fq 'VERIFIED AGAINST ca.crt' "$fixture_dir/chain-report.txt"
check 'chain count includes leaf and intermediate' grep -Eq 'CHAIN LENGTH[[:space:]]*:[[:space:]]*2$' "$fixture_dir/chain-report.txt"
check 'signed leaf is not reported self-issued or self-signed' not_contains 'SELF-(SIGNED|ISSUED)[[:space:]]*:[[:space:]]*YES' "$fixture_dir/chain-report.txt"
check 'trust report contains metadata only' not_contains 'BEGIN .*KEY|BEGIN CERTIFICATE' "$fixture_dir/chain-report.txt"

fixture_ca="$fixture_dir/unrelated.pem"
certificate_trust_secret_report fixture-tls > "$fixture_dir/mismatch-report.txt" 2>&1; rc=$?
check 'mismatched CA returns finding failure' test "$rc" -eq 1
check 'mismatched CA is reported as verification failure' grep -Fq 'VERIFY_FAILED' "$fixture_dir/mismatch-report.txt"

printf 'This is not an X.509 certificate.\n' > "$fixture_dir/malformed.pem"
fixture_cert="$fixture_dir/malformed.pem" fixture_ca="$fixture_dir/root.pem"
certificate_trust_secret_report fixture-tls > "$fixture_dir/malformed-report.txt" 2>&1; rc=$?
check 'malformed certificate returns finding failure' test "$rc" -eq 1
check 'malformed certificate is a parse error' grep -Fq PARSE_ERROR "$fixture_dir/malformed-report.txt"
check 'missing subject/issuer cannot imply self-issuance' not_contains 'SELF-(SIGNED|ISSUED)[[:space:]]*:[[:space:]]*YES' "$fixture_dir/malformed-report.txt"

: > "$fixture_dir/empty.pem"
fixture_cert="$fixture_dir/empty.pem" fixture_ca="$fixture_dir/root.pem"
certificate_trust_secret_report fixture-tls > "$fixture_dir/missing-cert-report.txt" 2>&1; rc=$?
check 'missing tls.crt with ca.crt present fails' test "$rc" -eq 1
check 'ca.crt does not substitute for absent tls.crt' grep -Fq 'Certificate tls.crt not present' "$fixture_dir/missing-cert-report.txt"
check 'absent tls.crt cannot imply self-issuance' not_contains 'SELF-(SIGNED|ISSUED)[[:space:]]*:[[:space:]]*YES' "$fixture_dir/missing-cert-report.txt"

fixture_cert="$fixture_dir/root.pem" fixture_ca="$fixture_dir/root.pem"
certificate_trust_secret_report fixture-tls > "$fixture_dir/selfsigned-report.txt" 2>&1; rc=$?
check 'explicitly trusted self-signed fixture succeeds' test "$rc" -eq 0
check 'self-issued fixture is recognized without asserting its signature' grep -Eq 'SELF-ISSUED[[:space:]]*:[[:space:]]*YES' "$fixture_dir/selfsigned-report.txt"

fixture_cert="$fixture_dir/chain.pem" fixture_ca=
certificate_trust_secret_report fixture-tls > "$fixture_dir/no-ca-report.txt" 2>&1; rc=$?
check 'missing ca.crt returns unavailable trust evidence' test "$rc" -eq 4
check 'missing ca.crt keeps trust unknown' grep -Eq 'CHAIN STATUS[[:space:]]*:[[:space:]]*UNKNOWN' "$fixture_dir/no-ca-report.txt"
check 'missing ca.crt cannot imply self-signature' not_contains 'SELF-(SIGNED|ISSUED)[[:space:]]*:[[:space:]]*YES' "$fixture_dir/no-ca-report.txt"
check 'trust analyzer removes temporary certificate files' test -z "$(find "$RUN_DIR" -maxdepth 1 -name 'trust-*' -print -quit)"

# The server binds only loopback and serves no application. Select an ephemeral
# port, then require the spawned server itself to remain alive and become ready.
port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()') || exit 2
openssl s_server -accept "127.0.0.1:$port" -cert "$fixture_dir/leaf.pem" \
    -key "$fixture_dir/leaf.key" -cert_chain "$fixture_dir/intermediate.pem" \
    -www -quiet > "$fixture_dir/server.log" 2>&1 &
server_pid=$!
ready=0
for attempt in {1..30}; do
    kill -0 "$server_pid" 2>/dev/null || break
    if python3 -c 'import socket,sys; s=socket.create_connection(("127.0.0.1",int(sys.argv[1])),0.1); s.close()' "$port" >/dev/null 2>&1; then ready=1; break; fi
    sleep 0.1
done
if ((ready!=1)) || ! kill -0 "$server_pid" 2>/dev/null; then
    printf 'ERROR: local TLS server did not become ready\n' >&2
    exit 2
fi

SSL_CERT_FILE="$fixture_dir/root.pem" SSL_CERT_DIR="$fixture_dir/empty-trust" \
    tls_report localhost "$port" > "$fixture_dir/tls-trusted.txt" 2>&1; rc=$?
check 'trusted localhost endpoint succeeds' test "$rc" -eq 0
check 'trusted endpoint completes verified handshake' grep -Fq 'TLS HANDSHAKE: COMPLETED' "$fixture_dir/tls-trusted.txt"
check 'real TLS 1.2 probe succeeds' grep -Eq '^TLS 1\.2[[:space:]]+SUPPORTED$' "$fixture_dir/tls-trusted.txt"
check 'real TLS 1.3 probe succeeds' grep -Eq '^TLS 1\.3[[:space:]]+SUPPORTED$' "$fixture_dir/tls-trusted.txt"
check 'TLS report excludes certificate/key payloads' not_contains 'BEGIN .*KEY|BEGIN CERTIFICATE' "$fixture_dir/tls-trusted.txt"

SSL_CERT_FILE="$fixture_dir/root.pem" SSL_CERT_DIR="$fixture_dir/empty-trust" \
    tls_report 127.0.0.1 "$port" > "$fixture_dir/tls-hostname.txt" 2>&1; rc=$?
check 'IP target absent from SAN fails verification' test "$rc" -eq 1
check 'identity mismatch is reported as handshake failure' grep -Fq 'TLS HANDSHAKE: FAILED' "$fixture_dir/tls-hostname.txt"

SSL_CERT_FILE="$fixture_dir/unrelated.pem" SSL_CERT_DIR="$fixture_dir/empty-trust" \
    tls_report localhost "$port" > "$fixture_dir/tls-untrusted.txt" 2>&1; rc=$?
check 'untrusted endpoint fails verification' test "$rc" -eq 1
check 'untrusted CA is reported as handshake failure' grep -Fq 'TLS HANDSHAKE: FAILED' "$fixture_dir/tls-untrusted.txt"

printf 'TLS integration: %s passed, %s failed\n' "$passed" "$failed"
((failed==0))
