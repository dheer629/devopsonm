#!/usr/bin/env bash
# DevOpsSentinel -- final single-file, read-only Kubernetes + GitOps + PKI/TLS + ETDP operations console.
# Runtime files are private, local, sanitized projections, never kubeconfig copies.
# No Git publishing, Flux reconciliation, Helm mutation, or Kubernetes mutation exists in this build.
# Changelog (compact):
#   1.1.1 Production hardening: DNS/TLS error classes, expanded credential
#         redaction, native-Linux developer validation, source/kubeconfig
#         hygiene checks, stronger deterministic security fixtures.
#   1.1.0 One-command triage (--triage, --triage-workload), capability report
#         (--capabilities), Sentinel doctor (--doctor), --json machine-readable
#         output, --quiet, exit code 4 for unavailable required data, next-check
#         guidance, triage/capability/doctor fixture self-tests.
#   1.0.0 Initial single-file read-only operations console.
set -o pipefail
set +x
export -n SPLUNK_TOKEN 2>/dev/null || :
umask 077

# 01 Constants and session state
APP_NAME="DevOpsSentinel"
APP_VERSION="4.2.1"
APP_BUILD="ADVANCED-UX-READ-ONLY-PRODUCTION"
APP_BUILD_DATE="2026-10-03"
SOURCE_FILE="${BASH_SOURCE[0]}"
SENTINEL_CONTEXT="${SNTL_CONTEXT:-}"
SENTINEL_NAMESPACE="${SNTL_NAMESPACE:-}"
REFRESH="${SNTL_REFRESH:-5}"
OUTPUT_DIR="${SNTL_OUTPUT_DIR:-${HOME}/.devopssentinel}"
RUN_DIR= CACHE_DIR= CURRENT_REPORT= CURRENT_TITLE= SELECTED_POD=
AUTH_STATUS=UNKNOWN API_STATUS=UNKNOWN API_LATENCY=UNKNOWN RBAC_STATUS=UNKNOWN
METRICS_STATUS=NOT_PROBED GITOPS_STATUS=NOT_PROBED CERT_STATUS=NOT_PROBED
KUBECTL_VERSION=UNKNOWN SERVER_VERSION=UNKNOWN API_FINGERPRINT=UNAVAILABLE
KUBECONFIG_MODE='KUBECTL DEFAULT'
[[ ${KUBECONFIG+x} ]] && KUBECONFIG_MODE=EXPLICIT
MODE=dashboard FORCE_REFRESH=0 NO_COLOR_FLAG=0 INTERACTIVE=0 SCOPE_READY=0
JSON_FLAG=0 QUIET_FLAG=0 TRIAGE_WORKLOAD= DOCTOR_BOOTSTRAP_RC=0
API_TIMEOUT=10 LOG_TIMEOUT=20 TLS_TIMEOUT=8 SPLUNK_TIMEOUT=20
CPU_WARN=80 CPU_CRIT=90 MEM_WARN=80 MEM_CRIT=90 CERT_WARN_DAYS=30 CERT_CRIT_DAYS=7
UI_COLS=120 UI_ROWS=30 UI_ACTIVE=0 UI_LAST_LINES=0 UI_STTY=
UI_COMPACT_FLAG=0 UI_SNAPSHOT_FLAG=0
FILTER= SORT_BY=name EVIDENCE_ID= EVIDENCE_MODE=9
declare -a ACTIVE_PIDS=()
declare -A DEPENDENCIES=()
C_RESET= C_GREEN= C_YELLOW= C_RED= C_CYAN= C_BLUE= C_DIM=

# 02 Terminal and input primitives
has() { command -v "$1" >/dev/null 2>&1; }
now_epoch() { printf '%(%s)T\n' -1; }
timestamp() { TZ=UTC printf '%(%Y-%m-%dT%H:%M:%SZ)T\n' -1; }
prompt() {
    REPLY=
    [[ -t 0 && $INTERACTIVE == 1 ]] || return 1
    printf '%s ' "$1" >&2
    IFS= read -r REPLY
}
choose() {
    local title=$1 item i=0 n
    shift
    (($#)) || return 1
    printf '\n%s\n' "$title" >&2
    for item in "$@"; do ((i+=1)); printf '[%3d] %s\n' "$i" "$item" | redact >&2; done
    prompt 'Select number (0 = back):' || return 1
    [[ $REPLY =~ ^[0-9]{1,6}$ ]] || return 1
    n=$((10#$REPLY))
    ((n>0 && n<=$#)) || return 1
    REPLY=${!n}
}

# 03 Central redaction. Conservative removal of the rest of a sensitive line
# intentionally favors confidentiality over preserving a log message verbatim.
redact() {
    if ! has awk; then
        local line low pem=0
        while IFS= read -r line || [[ -n $line ]]; do
            line=${line//[$'\001'-$'\010'$'\013'-$'\037'$'\177']/}
            low=${line,,}
            if [[ $low == *'-----begin '*'private key-----'* ]]; then pem=1; printf '[REDACTED PRIVATE KEY]\n'; continue; fi
            if ((pem)); then [[ $low == *'-----end '*'private key-----'* ]] && pem=0; continue; fi
            case $low in
                *authorization*|*bearer*|*token*|*password*|*passwd*|*secret=*|*apikey*|*api_key*|*client_secret*|*access_key*|*secret_access_key*|*session_token*|*private_key*|*client-key-data*|*://*@*|*eyj*|*ghp_*|*github_pat_*|*glpat-*|*xoxb-*|*xoxp-*) printf '[REDACTED]\n';;
                *) printf '%s\n' "$line";;
            esac
        done
        return
    fi
    LC_ALL=C awk '
    BEGIN { pem=0 }
    {
      gsub(/\033\[[0-9;?]*[ -\/]*[@-~]/, ""); gsub(/[\001-\010\013-\037\177]/, "")
      low=tolower($0)
      if (low ~ /-----begin .*private key-----/) {pem=1; print "[REDACTED PRIVATE KEY]"; next}
      if (pem) {if (low ~ /-----end .*private key-----/) pem=0; next}
      s=$0
      while (match(s, /[a-zA-Z][a-zA-Z0-9+.-]*:\/\/[^\/ @]*@/)) {
        p=substr(s,RSTART,RLENGTH); sub(/:\/\/.*/, "://[REDACTED]@",p)
        s=substr(s,1,RSTART-1) p substr(s,RSTART+RLENGTH)
        # Stop re-matching the replacement itself.
        sub(/\[REDACTED\]@/, "[REDACTED]_AT_",s)
      }
      gsub(/\[REDACTED\]_AT_/, "[REDACTED]@",s)
      low=tolower(s)
      if (match(low, /(authorization["\047 ]*[:=]|bearer[[:space:]]+|(^|[^a-z0-9_])(token|password|passwd|secret|apikey|api_key|client_secret|access_token|refresh_token|id_token|access_key|access_key_id|secret_access_key|session_token|aws_access_key_id|aws_secret_access_key|aws_session_token|private_key|client_key|client-key-data)["\047 ]*[:=])/))
        s=substr(s,1,RSTART-1) "[REDACTED]"
      if (match(s, /eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/))
        s=substr(s,1,RSTART-1) "[REDACTED]" substr(s,RSTART+RLENGTH)
      if (match(s, /(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})/))
        s=substr(s,1,RSTART-1) "[REDACTED]" substr(s,RSTART+RLENGTH)
      print s
    }'
}
sanitize_url() {
    local value=$1 scheme rest
    value=${value%%\?*}; value=${value%%\#*}
    if [[ $value == *://* ]]; then
        scheme=${value%%://*} rest=${value#*://}
        if [[ ${rest%%/*} == *@* ]]; then rest="[REDACTED]@${rest#*@}"; fi
        value="$scheme://$rest"
    fi
    printf '%s\n' "$value" | redact
}
safe_id() {
    local value=$1
    value=${value//[^a-zA-Z0-9._-]/_}; value=${value#.}; value=${value#.}
    [[ -n $value && $value != -* ]] || value="incident_${value}"
    printf '%.80s' "$value"
}
log_audit() {
    [[ -n $RUN_DIR && -d $RUN_DIR ]] || return 0
    printf '%s\tcontext=%s\tnamespace=%s\t%s\n' "$(timestamp)" "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE" "$*" | redact >> "$RUN_DIR/application.log"
}

# 04 Error classes, bounded processes and cleanup
classify_error() {
    local rc=$1 message=${2,,}
    case $rc in 124|137|143) printf 'API_TIMEOUT\n'; return;; 127) printf 'COMMAND_MISSING\n'; return;; esac
    case $message in
        *forbidden*|*'cannot list'*|*'cannot get'*|*'permission denied'*) printf 'RBAC_DENIED\n';;
        *unauthorized*|*'provide credentials'*|*'must be logged'*|*'token has expired'*|*'invalid_grant'*|*'credential'*|*'exec plugin'*|*'authentication'*) printf 'AUTH_ERROR\n';;
        *'no such host'*|*'could not resolve host'*|*'temporary failure in name resolution'*|*'name or service not known'*|*'server misbehaving'*) printf 'DNS_ERROR\n';;
        *'x509:'*|*'tls handshake'*|*'certificate verify failed'*|*'certificate signed by unknown authority'*|*'unable to get local issuer certificate'*|*'hostname mismatch'*|*'certificate has expired'*) printf 'TLS_ERROR\n';;
        *'connection refused'*|*'unable to connect'*|*'network is unreachable'*|*'connection reset'*|*'no route to host'*) printf 'NETWORK_ERROR\n';;
        *'timed out'*|*'deadline exceeded'*|*'timeout exceeded'*|*'i/o timeout'*|*'request timeout'*|*'timeout awaiting'*) printf 'API_TIMEOUT\n';;
        *'no matches for kind'*|*'not found'*|*'have a resource type'*|*'could not find the requested resource'*) printf 'RESOURCE_NOT_FOUND\n';;
        *'metrics api not available'*|*'metrics not available'*) printf 'METRICS_UNAVAILABLE\n';;
        *'parse'*|*'invalid character'*|*'cannot unmarshal'*) printf 'PARSE_ERROR\n';;
        *) if ((rc==0)); then printf 'OK\n'; else printf 'UNKNOWN\n'; fi;;
    esac
}
kill_tree() {
    local pid=$1 child
    [[ $pid =~ ^[0-9]+$ && $pid != $$ && $pid != "$BASHPID" ]] || return 0
    if has ps && has awk; then
        while IFS= read -r child; do [[ -n $child ]] && kill_tree "$child"; done < <(ps -eo pid=,ppid= 2>/dev/null | awk -v p="$pid" '$2==p {print $1}')
    fi
    kill -TERM "$pid" 2>/dev/null || :
}
run_bounded() {
    local seconds=$1 pid guard rc input_fd
    shift
    [[ $seconds =~ ^[1-9][0-9]*$ ]] || return 2
    # Keep exec credential plugin stdin connected for normal OIDC authentication.
    exec {input_fd}<&0
    if has timeout; then
        [[ ${1:-} == command ]] && shift
        command timeout --foreground --signal=TERM --kill-after=2 "${seconds}s" "$@" <&"$input_fd" &
    else
        "$@" <&"$input_fd" &
    fi
    pid=$! ACTIVE_PIDS+=("$!")
    exec {input_fd}<&-
    if ! has timeout; then
        (sleep "$seconds"; kill_tree "$pid"; sleep 2; kill -KILL "$pid" 2>/dev/null || :) &
        guard=$! ACTIVE_PIDS+=("$!")
    fi
    wait "$pid"; rc=$?
    if [[ -n ${guard:-} ]]; then kill_tree "$guard"; wait "$guard" 2>/dev/null || :; fi
    # Entries are removed to avoid killing a recycled PID during later cleanup.
    local -a keep=(); local p
    for p in "${ACTIVE_PIDS[@]}"; do [[ $p == "$pid" || $p == "${guard:-}" ]] || keep+=("$p"); done
    ACTIVE_PIDS=("${keep[@]}")
    return "$rc"
}

# 05 Dependencies and private local runtime

# 06 Scope engine: immutable within a session except explicit Change Scope.
scope_args_safe() {
    local arg
    for arg in "$@"; do
        case $arg in
            -A|-A?*|-n|-n?*|--all-namespaces*|--namespace*|--context*|--kube-context*|--kubeconfig*|--cache-dir*|--server*|--token*|--user*|--cluster*|--as*|--certificate-authority*|--client*|--insecure*|--request-timeout*|--raw*|--filename*|-f|-f?*|--kustomize*|-k|-k?*|--watch*|-w|-w?*)
                printf 'SCOPE_REJECTED: caller scope/transport/watch override\n' >&2; return 2;;
        esac
    done
}
kctl_dispatch() {
    local scope=$1 verb=$2; shift 2
    [[ -n $SENTINEL_CONTEXT ]] || { printf 'NOT_CONFIGURED: context\n' >&2; return 2; }
    scope_args_safe "$@" || return
    local -a argv=(kubectl --context "$SENTINEL_CONTEXT" "--request-timeout=${API_TIMEOUT}s" --cache-dir "$RUN_DIR/kubectl-cache")
    if [[ $scope == ns ]]; then
        [[ -n $SENTINEL_NAMESPACE ]] || { printf 'NOT_CONFIGURED: namespace\n' >&2; return 2; }
        argv+=(-n "$SENTINEL_NAMESPACE")
    fi
    case $verb in
        get) allowed_resource "$scope" "${1:-}" || return;;
        auth) [[ ${1:-} == can-i && ( ${2:-} == get || ${2:-} == list ) ]] || return 2;;
        logs) [[ $scope == ns && ${1:-} != -* && -n ${1:-} ]] || return 2;;
        top) [[ ( $scope == ns && ${1:-} == pods ) || ( $scope == cluster && ${1:-} == nodes ) ]] || return 2;;
        version|api-resources) [[ $scope == cluster ]] || return 2;;
        *) printf 'READ_ONLY: unsupported operation\n' >&2; return 2;;
    esac
    local seconds=$API_TIMEOUT
    [[ $verb == logs ]] && seconds=$LOG_TIMEOUT
    run_bounded "$seconds" command "${argv[@]}" "$verb" "$@"
}
kctl_ns() { kctl_dispatch ns "$@"; }
kctl_cluster() { kctl_dispatch cluster "$@"; }
helm_ns() {
    local verb=${1:-}; shift || return 2
    scope_args_safe "$@" || return
    case $verb in list|status|history) ;; *) return 2;; esac
    run_bounded "$API_TIMEOUT" command helm --kube-context "$SENTINEL_CONTEXT" -n "$SENTINEL_NAMESPACE" "$verb" "$@"
}
flux_read() {
    [[ ${1:-} == get ]] || return 2
    scope_args_safe "$@" || return
    run_bounded "$API_TIMEOUT" command flux --context "$SENTINEL_CONTEXT" -n "$SENTINEL_NAMESPACE" "$@"
}

# 07 Cache and safe collectors. No raw object JSON is ever persisted.
cache_file() { printf '%s/%s.json\n' "$CACHE_DIR" "$1"; }
cache_status() { if [[ -f $CACHE_DIR/$1.status ]]; then cat -- "$CACHE_DIR/$1.status"; else printf 'NOT_COLLECTED\n'; fi; }
cache_age() {
    local value=0
    [[ -f $CACHE_DIR/$1.time ]] && read -r value < "$CACHE_DIR/$1.time"
    printf '%s\n' "$(( $(now_epoch) - value ))"
}
cache_fresh() { [[ $FORCE_REFRESH == 0 && -f $CACHE_DIR/$1.status ]] && (( $(cache_age "$1") < $2 )); }
cache_record() {
    printf '%s\n' "$2" > "$CACHE_DIR/$1.status"
    now_epoch > "$CACHE_DIR/$1.time"
    log_audit "collector=$1 status=$2"
}
capture_command() {
    local error_file=$1 error_fd error_pid rc
    shift
    exec {error_fd}> >(redact > "$error_file")
    error_pid=$!
    "$@" 2>&"$error_fd"; rc=$?
    exec {error_fd}>&-
    wait "$error_pid" 2>/dev/null || :
    return "$rc"
}
json_sanitize() {
    # Applied AFTER module allow-list projections. Descriptions/messages may
    # contain credentials; sanitize strings without breaking JSON escaping.
    jq '
      def clean:
        if type=="object" then with_entries(select(.key | test("^(data|stringData|managedFields|password|passwd|token|access_token|refresh_token|id_token|client_secret|access_key|access_key_id|secret_access_key|session_token|aws_access_key_id|aws_secret_access_key|aws_session_token|privateKey|private_key|client_key|client-key-data|tls.key)$";"i")|not) | .value |= clean)
        elif type=="array" then map(clean)
        elif type=="string" then
          if test("BEGIN .*PRIVATE KEY|authorization[\" ]*[:=]|bearer[[:space:]]+|(^|[^a-z0-9_])(token|password|passwd|secret|apikey|api_key|client_secret|access_key|access_key_id|secret_access_key|session_token|aws_access_key_id|aws_secret_access_key|aws_session_token|private_key|client_key|client-key-data)[\" ]*[:=]";"i") then "[REDACTED]"
          else gsub("(?<s>[a-zA-Z][a-zA-Z0-9+.-]*://)[^/ @]*@";"\(.s)[REDACTED]@") |
               gsub("eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+";"[REDACTED]") |
               gsub("(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})";"[REDACTED]") |
               gsub("[\u0000-\u0008\u000b-\u001f\u007f]";"") end
        else . end; clean'
}
collect_json() {
    local key=$1 ttl=$2 scope=$3 resource=$4 projection=$5 fallback=${6:-}
    local raw rc err state path
    [[ $key =~ ^[a-zA-Z0-9_.-]+$ && $key != .* ]] || return 2
    if cache_fresh "$key" "$ttl"; then [[ $(cache_status "$key") == OK || $(cache_status "$key") == EMPTY_RESULT ]]; return; fi
    mkdir "$CACHE_DIR/$key.lock" 2>/dev/null || return 1
    path="$CACHE_DIR/$key.json"
    err="$CACHE_DIR/$key.error"
    rm -f -- "$path" "$CACHE_DIR/$key.txt"
    if ! has jq; then
        if [[ -n $fallback ]]; then
            raw=$(capture_command "$err" "kctl_$scope" get "$resource" -o "custom-columns=$fallback"); rc=$?
            if ((rc==0)); then printf '%s\n' "$raw" | redact > "$CACHE_DIR/$key.txt"; state=DEGRADED; else state=$(classify_error "$rc" "$(cat "$err")"); fi
        else state=COMMAND_MISSING; printf 'jq required for this collector\n' > "$err"; fi
        cache_record "$key" "$state"; rmdir "$CACHE_DIR/$key.lock"; return 1
    fi
    raw=$(capture_command "$err" "kctl_$scope" get "$resource" -o json); rc=$?
    if ((rc!=0)); then state=$(classify_error "$rc" "$(cat "$err")")
    elif ! printf '%s\n' "$raw" | jq -e 'type=="object" and (.items|type=="array")' >/dev/null 2>&1; then state=PARSE_ERROR
    elif printf '%s\n' "$raw" | jq "$projection" 2> >(redact >> "$err") | json_sanitize > "$path.new"; then
        if jq -e 'type=="object" and (.items|type=="array")' "$path.new" >/dev/null 2>&1; then
            mv -- "$path.new" "$path"; state=OK
            [[ $(jq '.items|length' "$path") == 0 ]] && state=EMPTY_RESULT
        else state=PARSE_ERROR; fi
    else state=PARSE_ERROR; fi
    unset raw
    rm -f -- "$path.new"
    cache_record "$key" "$state"
    rmdir "$CACHE_DIR/$key.lock"
    [[ $state == OK || $state == EMPTY_RESULT ]]
}
collect_text() {
    local key=$1 ttl=$2 raw rc state err
    shift 2
    [[ $key =~ ^[a-zA-Z0-9_.-]+$ && $key != .* ]] || return 2
    if cache_fresh "$key" "$ttl"; then [[ $(cache_status "$key") == OK || $(cache_status "$key") == EMPTY_RESULT ]]; return; fi
    mkdir "$CACHE_DIR/$key.lock" 2>/dev/null || return 1
    err="$CACHE_DIR/$key.error"
    raw=$(capture_command "$err" "$@"); rc=$?
    if ((rc==0)); then
        if has jq && printf '%s\n' "$raw" | jq -e 'type=="array" or type=="object"' >/dev/null 2>&1; then
            printf '%s\n' "$raw" | json_sanitize > "$CACHE_DIR/$key.txt"
        else printf '%s\n' "$raw" | redact > "$CACHE_DIR/$key.txt"; fi
        state=OK; [[ -n $raw ]] || state=EMPTY_RESULT
    else
        rm -f -- "$CACHE_DIR/$key.txt"
        state=$(classify_error "$rc" "$(cat "$err")")
    fi
    cache_record "$key" "$state"; rmdir "$CACHE_DIR/$key.lock"
    [[ $state == OK || $state == EMPTY_RESULT ]]
}

# 08 Kubeconfig, authentication and bootstrap
config_query() { run_bounded "$API_TIMEOUT" command kubectl config "$@"; }
rbac_probe() {
    local resource answer rc scope verb
    for resource in pods pods/log events deployments services secrets nodes; do
        scope=ns verb=list
        [[ $resource == pods/log ]] && verb=get
        [[ $resource == nodes ]] && scope=cluster
        answer=$("kctl_$scope" auth can-i "$verb" "$resource" 2>&1); rc=$?
        if [[ $answer == yes ]]; then printf '%s\t%s\tOK\n' "$resource" "$verb"
        elif [[ $answer == no* ]]; then printf '%s\t%s\tRBAC_DENIED\n' "$resource" "$verb"
        else printf '%s\t%s\t%s\n' "$resource" "$verb" "$(classify_error "$rc" "$answer")"; fi
    done
}
scope_report() {
    printf 'Application: %s %s (%s)\nTimestamp: %s\nHost: %s\n' "$APP_NAME" "$APP_VERSION" "$APP_BUILD" "$(timestamp)" "${HOSTNAME:-UNKNOWN}"
    printf 'Context: %s\nNamespace: %s\nMode: READ-ONLY SUPERVISION\n' "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE"
    printf 'KUBECONFIG MODE: %s\n' "$KUBECONFIG_MODE"
    [[ $KUBECONFIG_MODE == EXPLICIT ]] && printf 'KUBECONFIG: %s\n' "${KUBECONFIG:-}"
    printf 'API endpoint SHA256: %s\nkubectl: %s\nServer: %s\n' "$API_FINGERPRINT" "$KUBECTL_VERSION" "$SERVER_VERSION"
    printf 'Authentication: %s\nAPI: %s\nAPI latency: %s\nRBAC: %s\n' "$AUTH_STATUS" "$API_STATUS" "$API_LATENCY" "$RBAC_STATUS"
}
diagnostics_report() {
    scope_report
    printf '\nDEPENDENCIES\n'
    local cmd
    for cmd in kubectl helm flux jq openssl curl timeout sha256sum column tput base64 awk sed grep sort uniq date git shellcheck; do printf '%-18s %s\n' "$cmd" "${DEPENDENCIES[$cmd]:-UNKNOWN}"; done
    printf '\nRBAC (read capabilities only)\n'
    collect_text rbac 300 rbac_probe >/dev/null
    [[ -f $CACHE_DIR/rbac.txt ]] && cat "$CACHE_DIR/rbac.txt"
    printf '\nMETRICS: %s\nGITOPS: %s\nCERTIFICATES: %s\n' "$METRICS_STATUS" "$GITOPS_STATUS" "$CERT_STATUS"
    splunk_diagnostics
}

# Pure offline integration fixtures exercise the real wrappers/cache/bootstrap.
# Function overrides exist only inside this subshell; no mock tool is installed.
core_integration_tests() (
    has jq || { printf 'SKIP core JSON fixtures: jq unavailable\n'; return 0; }
    local fixture_dir saved_run=$RUN_DIR original_config=${KUBECONFIG-} original_set=${KUBECONFIG+x}
    fixture_dir=$(mktemp -d "$RUN_DIR/core-fixture.XXXXXXXX") || return 1
    RUN_DIR=$fixture_dir CACHE_DIR="$fixture_dir/cache"
    mkdir -- "$CACHE_DIR" || return 1
    : > "$fixture_dir/calls"
    SENTINEL_CONTEXT=fixture-context SENTINEL_NAMESPACE=fixture-namespace
    INTERACTIVE=0 FORCE_REFRESH=0 CORE_FIXTURE_MODE=healthy
    # This suite is explicitly offline. bootstrap_scope checks for kubectl before
    # reaching the mocked run_bounded wrapper, so advertise only the fixture's
    # mocked kubectl while still requiring the real jq gated above. This keeps
    # deterministic self-tests runnable on clean CI hosts without Kubernetes.
    has() {
        case $1 in
            kubectl|jq) return 0;;
            *) command -v "$1" >/dev/null 2>&1;;
        esac
    }
    run_bounded() {
        shift
        [[ ${1:-} == command ]] && shift
        [[ ${1:-} == kubectl ]] || return 127
        shift
        local context='' namespace='' verb resource output='' arg
        while (($#)); do
            case $1 in
                --context) context=$2; shift 2;;
                -n) namespace=$2; shift 2;;
                --request-timeout=*|--cache-dir=*) shift;;
                --cache-dir) shift 2;;
                *) break;;
            esac
        done
        verb=${1:-}; resource=${2:-}
        printf '%s|%s|%s|%s\n' "$context" "$namespace" "$verb" "$resource" >> "$fixture_dir/calls"
        case "$verb:$resource" in
            config:get-contexts) printf 'fixture-context\nother-context\n'; return;;
            config:current-context) printf 'fixture-context\n'; return;;
            config:view) printf 'https://fixture.invalid'; return;;
        esac
        [[ $context == fixture-context ]] || { printf 'context scope not injected\n' >&2; return 2; }
        case "$verb:$resource" in
            auth:can-i) printf 'yes\n'; return;;
            version:*) printf '{"clientVersion":{"gitVersion":"fixture"},"serverVersion":{"gitVersion":"fixture"}}\n'; return;;
            api-resources:*) printf 'pods\n'; return;;
            get:namespaces)
                case $CORE_FIXTURE_MODE in
                    namespace-denied) printf 'Forbidden: cannot list namespaces\n' >&2; return 1;;
                    expired) printf 'Unauthorized: token has expired\n' >&2; return 1;;
                    network) printf 'connection refused\n' >&2; return 1;;
                    *) printf 'fixture-namespace\n'; return;;
                esac;;
            get:pods)
                [[ $namespace == fixture-namespace ]] || return 2
                case $CORE_FIXTURE_MODE in
                    denied) printf 'Forbidden: cannot list pods\n' >&2; return 1;;
                    malformed) printf '{broken}\n'; return;;
                    empty) printf '{"items":[]}\n'; return;;
                esac
                for arg in "$@"; do [[ $arg == custom-columns=* ]] && { printf 'NAME PHASE\nfixture-pod Running\n'; return; }; done
                printf '%s\n' '{"kind":"PodList","items":[{"kind":"Pod","metadata":{"name":"fixture-pod","namespace":"fixture-namespace","annotations":{"private":"fixture-omit-annotation"}},"spec":{"containers":[{"name":"app","image":"example.invalid/app:v1","env":[{"name":"PASSWORD","value":"fixture-omit-env"}],"command":["fixture-omit-command"],"resources":{"requests":{"cpu":"250m","memory":"32Mi"}}}]},"status":{"phase":"Running"}}]}'
                return;;
            get:pods.metrics.k8s.io) printf 'Forbidden: cannot list pod metrics\n' >&2; return 1;;
            *) printf '{"items":[]}\n'; return;;
        esac
    }
    core_fixture_assert() { "$@" || { printf 'FAIL core fixture: %s\n' "$*" >&2; return 1; }; }
    collect_json testpods 30 ns pods "$JQ_SAFE_POD" || return 1
    [[ $(cache_status testpods) == OK ]] || return 1
    jq -e '.items[0].spec.containers[0].resources.requests.cpu=="250m" and (.items[0].spec.containers[0].env[0]|has("value")|not)' "$CACHE_DIR/testpods.json" >/dev/null || return 1
    ! grep -q 'fixture-omit' "$CACHE_DIR/testpods.json" || return 1
    local calls_before calls_after
    calls_before=$(wc -l < "$fixture_dir/calls")
    collect_json testpods 30 ns pods "$JQ_SAFE_POD" || return 1
    calls_after=$(wc -l < "$fixture_dir/calls")
    [[ $calls_before == "$calls_after" ]] || return 1
    FORCE_REFRESH=1 CORE_FIXTURE_MODE=denied
    collect_json testpods 30 ns pods "$JQ_SAFE_POD" && return 1
    [[ $(cache_status testpods) == RBAC_DENIED && ! -e $CACHE_DIR/testpods.json ]] || return 1
    CORE_FIXTURE_MODE=malformed
    collect_json testpods 30 ns pods "$JQ_SAFE_POD" && return 1
    [[ $(cache_status testpods) == PARSE_ERROR && ! -e $CACHE_DIR/testpods.json ]] || return 1
    CORE_FIXTURE_MODE=empty
    collect_json testpods 30 ns pods "$JQ_SAFE_POD" || return 1
    [[ $(cache_status testpods) == EMPTY_RESULT ]] || return 1
    CORE_FIXTURE_MODE=healthy FORCE_REFRESH=0
    mkdir "$CACHE_DIR/overlap.lock" || return 1
    collect_json overlap 5 ns pods "$JQ_SAFE_POD" && return 1
    local output
    output=$(printf '%s\n' '{"password":"fixture-omit-password","aws_secret_access_key":"fixture-omit-aws","nested":{"token":"fixture-omit-token","text":"Authorization: fixture-omit-auth","pat":"ghp_1234567890abcdefghijklmnopqrstuv"},"image":"safe"}' | json_sanitize) || return 1
    [[ $output != *fixture-omit* && $output != *ghp_1234567890* && $output == *safe* ]] || return 1
    export KUBECONFIG='/fixture/one config:/fixture/two'
    KUBECONFIG_MODE=EXPLICIT CORE_FIXTURE_MODE=namespace-denied
    bootstrap_scope >/dev/null 2>&1 || return 1
    [[ $KUBECONFIG == '/fixture/one config:/fixture/two' && $AUTH_STATUS == AUTHENTICATED && $SCOPE_READY == 1 ]] || return 1
    unset KUBECONFIG
    KUBECONFIG_MODE='KUBECTL DEFAULT' CORE_FIXTURE_MODE=healthy
    bootstrap_scope >/dev/null 2>&1 || return 1
    [[ ! ${KUBECONFIG+x} ]] || return 1
    CORE_FIXTURE_MODE=expired
    bootstrap_scope >/dev/null 2>&1; [[ $? == 3 && $AUTH_STATUS == AUTH_ERROR ]] || return 1
    CORE_FIXTURE_MODE=network
    bootstrap_scope >/dev/null 2>&1; [[ $? == 3 && $API_STATUS == NETWORK_ERROR ]] || return 1
    CORE_FIXTURE_MODE=healthy FORCE_REFRESH=1
    has() { [[ $1 != jq ]] && command -v "$1" >/dev/null 2>&1; }
    collect_json nojq 5 ns pods "$JQ_SAFE_POD" 'NAME:.metadata.name,PHASE:.status.phase' && return 1
    [[ $(cache_status nojq) == DEGRADED && -s $CACHE_DIR/nojq.txt && ! -e $CACHE_DIR/nojq.json ]] || return 1
    printf 'PASS core wrapper, cache, redaction, explicit/default kubeconfig, RBAC, auth, network and jq fallback integration fixtures\n'
)

# 10 Kubernetes collectors / 11 Metrics / 16 Findings
# Quantity and effective-request rules:
# https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
# https://kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/
# JSON projections intentionally omit literal environment values, commands, probe
# arguments, arbitrary annotations, and Secret payloads BEFORE entering the cache.
read -r -d '' JQ_SAFE_POD <<'JQ' || :
def smeta: {name,namespace,uid,creationTimestamp,deletionTimestamp,generation,ownerReferences,labels,
  annotations: ((.annotations // {}) | with_entries(select(.key == "meta.helm.sh/release-name" or .key == "meta.helm.sh/release-namespace")))};
def scon: {name,image,resources,restartPolicy,ports,volumeMounts,
  env: [(.env // [])[] | {name,valueFrom}],envFrom};
def svol: {name,persistentVolumeClaim,emptyDir,
  secret:(if .secret then (.secret | {secretName,optional}) else null end),
  configMap:(if .configMap then (.configMap | {name,optional}) else null end),
  projected:(if .projected then {sources:[.projected.sources[]? |
    {secret:(if .secret then (.secret | {name,optional}) else null end),
     configMap:(if .configMap then (.configMap | {name,optional}) else null end),
     serviceAccountToken:(if .serviceAccountToken then {path:.serviceAccountToken.path} else null end)}]} else null end)};
def sspec: {nodeName,serviceAccountName,restartPolicy,overhead,resources,schedulingGates,
  containers:[.containers[]? | scon],initContainers:[.initContainers[]? | scon],
  ephemeralContainers:[.ephemeralContainers[]? | scon],volumes:[.volumes[]? | svol]};
{apiVersion,kind,items:[.items[]? | {kind,metadata:(.metadata|smeta),spec:(.spec|sspec),status}]}
JQ

read -r -d '' JQ_QUANTITIES <<'JQ' || :
def quantity:
  if . == null then null else
  try (tostring | capture("^(?<v>[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+))(?<s>[eE][+-]?[0-9]+|[EPTGMK]i|[EPTGMkKmun]?)$") |
    (.v|tonumber) * (if .s == "" then 1 elif .s == "n" then 1e-9 elif .s == "u" then 1e-6 elif .s == "m" then 0.001
    elif .s == "k" or .s == "K" then 1000 elif .s == "M" then 1e6 elif .s == "G" then 1e9
    elif .s == "T" then 1e12 elif .s == "P" then 1e15 elif .s == "E" then 1e18
    elif .s == "Ki" then 1024 elif .s == "Mi" then 1048576 elif .s == "Gi" then 1073741824
    elif .s == "Ti" then 1099511627776 elif .s == "Pi" then 1125899906842624 elif .s == "Ei" then 1152921504606846976
    else ("1" + .s | tonumber) end)) catch null // null end;
def q($r): quantity | if . == null or . < 0 or (isfinite|not) then null elif $r == "cpu" then . * 1000 else . end;
def q_state($r): if . == null then "UNAVAILABLE" else q($r) // "PARSE_ERROR" end;
def round2: . * 100 | round / 100;
def cpu_fmt: if type == "number" then "\(round2)m" else (. // "N/A") end;
def mem_fmt: if type != "number" then (. // "N/A") elif . >= 1073741824 then "\((. / 1073741824)|round2) GiB" else "\((. / 1048576)|round2) MiB" end;
def pct($u;$d): if ($u|type) == "number" and ($d|type) == "number" and $d > 0 then (($u/$d*100)|round2|tostring)+"%" else "N/A" end;
def epoch: if . == null then null else try (sub("\\.[0-9]+Z$";"Z")|fromdateiso8601) catch null end;
def age: epoch | if . == null then "UNKNOWN" else (now - . | floor) as $s |
  if $s >= 86400 then "\(($s/86400)|floor)d" elif $s >= 3600 then "\(($s/3600)|floor)h" elif $s >= 60 then "\(($s/60)|floor)m" else "\($s)s" end end;
def activepod: .status.phase != "Succeeded" and .status.phase != "Failed";
def owner($w): (.metadata.ownerReferences // [] | map(select(.controller == true)) | .[0]) as $o |
  if $o == null then "Pod/"+.metadata.name elif $o.kind == "ReplicaSet" then
    ([$w.items[]? | select(.kind == "ReplicaSet" and .metadata.name == $o.name) | .metadata.ownerReferences[]? | select(.controller == true and .kind == "Deployment")][0]) as $d |
    if $d then "Deployment/"+$d.name else "ReplicaSet/"+$o.name end else $o.kind+"/"+$o.name end;
def effective($which;$r):
  . as $p | ((.spec.containers // []) + (.spec.initContainers // [])) as $all |
  if (.spec.resources[$which][$r] // null) != null then "UNSUPPORTED_POD_LEVEL"
  elif (.status.resize // "") != "" or any(.status.conditions[]?; (.type=="PodResizePending" or .type=="PodResizeInProgress") and .status=="True") then "RESIZE_NOT_VERIFIED"
  elif any($all[]; (.resources[$which][$r] // null) != null and (.resources[$which][$r] | q($r)) == null) then "PARSE_ERROR"
  elif (.spec.overhead[$r] // null) != null and (.spec.overhead[$r] | q($r)) == null then "PARSE_ERROR"
  elif $which == "limits" and any($all[]; (.resources.limits[$r] // null) == null) then "UNBOUNDED"
  elif all($all[]; (.resources[$which][$r] // null) == null) and (.spec.overhead[$r] // null) == null then "UNSET"
  else
    ([.spec.containers[]? | (.resources[$which][$r] | q($r)) // 0] | add // 0) as $apps |
    (reduce (.spec.initContainers // [])[] as $c ({side:0,peak:0};
      (($c.resources[$which][$r] | q($r)) // 0) as $v |
      if $c.restartPolicy == "Always" then .side += $v | .peak = ([.peak,.side]|max)
      else .peak = ([.peak,($v+.side)]|max) end)) as $init |
    ([($apps+$init.side),$init.peak]|max) + ((.spec.overhead[$r] | q($r)) // 0)
  end;
def statuslabel:
  if .metadata.deletionTimestamp then "Terminating" else
  ([.status.initContainerStatuses[]?,.status.containerStatuses[]? | .state.waiting.reason // empty][0]) //
  .status.reason // .status.phase // "UNKNOWN" end;
def usage($metric;$r):
  . as $pod |
  (if $pod.status.phase=="Running" then [$pod.spec.containers[]?.name] + [$pod.spec.initContainers[]?|select(.restartPolicy=="Always")|.name]
   else [] end) + [$pod.status.containerStatuses[]?,$pod.status.initContainerStatuses[]?,$pod.status.ephemeralContainerStatuses[]?|select(.state.running!=null)|.name] | unique as $expected |
  if $metric == null then "N/A" elif ($metric.containers|length) == 0 then "N/A"
  elif ([$metric.containers[].name]|length) != ([$metric.containers[].name]|unique|length) then "PARSE_ERROR"
  elif ($expected - [$metric.containers[].name] | length)>0 then "INCOMPLETE"
  elif any($metric.containers[]; (.usage[$r]|q($r)) == null) then "PARSE_ERROR"
  else ([$metric.containers[] | .usage[$r]|q($r)]|add) end;
JQ

json_cache_path() {
    local key=$1 state
    state=$(cache_status "$key")
    case $state in OK|EMPTY_RESULT)
        if [[ -s $CACHE_DIR/$key.json ]]; then printf '%s\n' "$CACHE_DIR/$key.json"; return; fi ;;
    esac
    [[ -s $RUN_DIR/empty-list.json ]] || printf '{"items":[]}\n' > "$RUN_DIR/empty-list.json"
    printf '%s\n' "$RUN_DIR/empty-list.json"
}

data_source() {
    local key=$1 updated=UNKNOWN stamp
    if [[ -s $CACHE_DIR/$key.time ]]; then
        read -r stamp < "$CACHE_DIR/$key.time"
        updated=$(date -u -d "@$stamp" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null) || updated="epoch:$stamp"
    fi
    printf 'SOURCE\t%s\tSTATUS\t%s\tUPDATED\t%s\tCACHE AGE\t%s sec\n' "$key" "$(cache_status "$key")" "$updated" "$(cache_age "$key")"
}

fallback_report() {
    local key=$1
    data_source "$key"
    if [[ -s $CACHE_DIR/$key.txt ]]; then cat -- "$CACHE_DIR/$key.txt"; else printf '%s\t%s\n' "$key" "$(cache_status "$key")"; fi
    printf 'INTERPRETATION\tStructured analysis requires jq; missing data is UNKNOWN.\n'
}

collect_pods() {
    collect_json pods 5 ns pods "$JQ_SAFE_POD" 'NAME:.metadata.name,PHASE:.status.phase,NODE:.spec.nodeName,IP:.status.podIP,CREATED:.metadata.creationTimestamp' || :
}

collect_workloads() {
    local projection
    projection=${JQ_SAFE_POD%\{apiVersion*}
    projection+=' {apiVersion,kind,items:[.items[]? | {kind,metadata:(.metadata|smeta),spec:{replicas:.spec.replicas,suspend:.spec.suspend,schedule:.spec.schedule,completions:.spec.completions,parallelism:.spec.parallelism,selector:.spec.selector,template:(if .spec.template then {metadata:(.spec.template.metadata|smeta),spec:(.spec.template.spec|sspec)} else null end)},status}]}'
    collect_json workloads 5 ns deployments,statefulsets,daemonsets,replicasets,jobs,cronjobs "$projection" 'KIND:.kind,NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas,AVAILABLE:.status.availableReplicas' || :
}

collect_metrics() {
    collect_json metrics 5 ns pods.metrics.k8s.io '{items:[.items[]? | {metadata:{name:.metadata.name,namespace:.metadata.namespace},timestamp,window,containers:[.containers[]?|{name,usage}]}]}' '' || :
    METRICS_STATUS=$(cache_status metrics)
    case $METRICS_STATUS in RESOURCE_NOT_FOUND|COMMAND_MISSING) METRICS_STATUS=METRICS_UNAVAILABLE ;; esac
}

collect_events() {
    collect_json events 10 ns events '{items:[.items[]?|{metadata:{name:.metadata.name,namespace:.metadata.namespace,creationTimestamp:.metadata.creationTimestamp},eventTime,firstTimestamp,lastTimestamp,type,reason,involvedObject:{kind:.involvedObject.kind,name:.involvedObject.name,namespace:.involvedObject.namespace,uid:.involvedObject.uid},message,count,series,source,reportingComponent}]}' 'TIME:.lastTimestamp,TYPE:.type,REASON:.reason,OBJECT:.involvedObject.name,COUNT:.count,MESSAGE:.message' || :
}

collect_network() {
    collect_json services 5 ns services '{items:[.items[]?|{kind,metadata:{name:.metadata.name,namespace:.metadata.namespace,creationTimestamp:.metadata.creationTimestamp},spec:{type:.spec.type,selector:.spec.selector,clusterIP:.spec.clusterIP,clusterIPs:.spec.clusterIPs,externalName:.spec.externalName,externalIPs:.spec.externalIPs,ports:.spec.ports,publishNotReadyAddresses:.spec.publishNotReadyAddresses},status}]}' 'NAME:.metadata.name,TYPE:.spec.type,CLUSTER-IP:.spec.clusterIP,EXTERNAL-IP:.status.loadBalancer.ingress[*].ip,PORTS:.spec.ports[*].port' || :
    collect_json endpointslices 5 ns endpointslices.discovery.k8s.io '{items:[.items[]?|{metadata:{name:.metadata.name,namespace:.metadata.namespace,labels:.metadata.labels},addressType,ports,endpoints:[.endpoints[]?|{addresses,conditions,hostname,nodeName,targetRef:{kind:.targetRef.kind,name:.targetRef.name,uid:.targetRef.uid}}]}]}' 'NAME:.metadata.name,ADDRESS-TYPE:.addressType,ADDRESSES:.endpoints[*].addresses[*],READY:.endpoints[*].conditions.ready' || :
    collect_json endpoints 5 ns endpoints '{items:[.items[]?|{metadata:{name:.metadata.name,namespace:.metadata.namespace},subsets:[.subsets[]?|{ports,addresses:[.addresses[]?|{ip,nodeName,targetRef:{kind:.targetRef.kind,name:.targetRef.name}}],notReadyAddresses:[.notReadyAddresses[]?|{ip,nodeName,targetRef:{kind:.targetRef.kind,name:.targetRef.name}}]}]}]}' 'NAME:.metadata.name,READY:.subsets[*].addresses[*].ip,NOT-READY:.subsets[*].notReadyAddresses[*].ip' || :
    collect_json ingresses 10 ns ingresses.networking.k8s.io '{items:[.items[]?|{metadata:{name:.metadata.name,namespace:.metadata.namespace},spec:{ingressClassName:.spec.ingressClassName,defaultBackend:.spec.defaultBackend,rules:.spec.rules,tls:.spec.tls},status}]}' 'NAME:.metadata.name,CLASS:.spec.ingressClassName,HOSTS:.spec.rules[*].host,TLS-SECRETS:.spec.tls[*].secretName' || :
}

collect_storage() {
    collect_json pvcs 5 ns persistentvolumeclaims '{items:[.items[]?|{metadata:{name:.metadata.name,namespace:.metadata.namespace,creationTimestamp:.metadata.creationTimestamp},spec:{volumeName:.spec.volumeName,storageClassName:.spec.storageClassName,accessModes:.spec.accessModes,resources:.spec.resources,volumeMode:.spec.volumeMode},status}]}' 'NAME:.metadata.name,STATUS:.status.phase,VOLUME:.spec.volumeName,CAPACITY:.status.capacity.storage,CLASS:.spec.storageClassName' || :
}

resource_rows_json() {
    local p m w
    p=$(json_cache_path pods); m=$(json_cache_path metrics); w=$(json_cache_path workloads)
    jq -c --slurpfile mx "$m" --slurpfile wx "$w" "$JQ_QUANTITIES"'
      ($mx[0].items // [] | map({key:.metadata.name,value:.})|from_entries) as $metrics |
      [.items[]? | . as $p | ($metrics[.metadata.name] // null) as $m |
       {pod:.metadata.name,uid:.metadata.uid,ready:((([.status.containerStatuses[]?|select(.ready==true)]|length)|tostring)+"/"+((.spec.containers|length)|tostring)),
        status:statuslabel,phase:(.status.phase // "UNKNOWN"),active:activepod,
        restarts:([.status.containerStatuses[]?,.status.initContainerStatuses[]?,.status.ephemeralContainerStatuses[]?|.restartCount // 0]|add // 0),
        created:.metadata.creationTimestamp,age:(.metadata.creationTimestamp|age),ip:(.status.podIP // "-"),
        owner:owner($wx[0]),node:(.spec.nodeName // "UNSCHEDULED"),
        cpu:usage($m;"cpu"),memory:usage($m;"memory"),cpu_request:effective("requests";"cpu"),
        cpu_limit:effective("limits";"cpu"),memory_request:effective("requests";"memory"),memory_limit:effective("limits";"memory"),
        metrics_timestamp:($m.timestamp // "UNAVAILABLE"),metrics_window:($m.window // "UNAVAILABLE"),
        containers:([.spec.containers[]?,.spec.initContainers[]?,.spec.ephemeralContainers[]?|.name]|join(",")),
        images:([.spec.containers[]?,.spec.initContainers[]?,.spec.ephemeralContainers[]?|.image]|join(","))}]
    ' "$p"
}

resources_report() {
    collect_pods; collect_workloads; collect_metrics
    data_source pods; data_source metrics
    if ! has jq; then fallback_report pods; return; fi
    if [[ $(cache_status pods) != OK && $(cache_status pods) != EMPTY_RESULT ]]; then return 1; fi
    local rows
    rows=$(mktemp "$RUN_DIR/resource-rows.XXXXXX") || return 1
    if ! resource_rows_json > "$rows"; then printf 'RESOURCES\tPARSE_ERROR\n'; rm -f -- "$rows"; return 1; fi
    printf 'POD\tREADY\tSTATUS\tRESTARTS\tAGE\tCPU USED\tCPU REQ\tCPU LIMIT\tMEM USED\tMEM REQ\tMEM LIMIT\tCPU/REQ\tCPU/LIMIT\tMEM/REQ\tMEM/LIMIT\tNODE\tIP\tOWNER\tCONTAINERS\tIMAGES\n'
    jq -r --arg filter "${RESOURCE_FILTER:-}" --arg sort "${RESOURCE_SORT:-name}" "$JQ_QUANTITIES"'
      map(select($filter == "" or ([.pod,.node,.owner,.status,.containers,.images]|join(" ")|test($filter;"i")))) |
      (if $sort == "cpu" then sort_by(if (.cpu|type)=="number" then -.cpu else 0 end)
       elif $sort == "memory" then sort_by(if (.memory|type)=="number" then -.memory else 0 end)
       elif $sort == "restarts" then sort_by(-.restarts) elif $sort == "age" then sort_by(.created)
       elif $sort == "status" then sort_by(.status) elif $sort == "node" then sort_by(.node) else sort_by(.pod) end)[] |
      [.pod,.ready,.status,.restarts,.age,(.cpu|cpu_fmt),(.cpu_request|cpu_fmt),(.cpu_limit|cpu_fmt),
       (.memory|mem_fmt),(.memory_request|mem_fmt),(.memory_limit|mem_fmt),pct(.cpu;.cpu_request),pct(.cpu;.cpu_limit),
       pct(.memory;.memory_request),pct(.memory;.memory_limit),.node,.ip,.owner,.containers,.images]|@tsv' "$rows" || printf 'FILTER/FORMAT\tPARSE_ERROR (check regular expression)\n'
    jq -r "$JQ_QUANTITIES"'
      def total($k): map(select(.active)) as $a | [$a[]|.[$k]] as $v |
       if ($a|length)==0 then 0 elif any($v[]; . == "PARSE_ERROR") then "PARSE_ERROR"
       elif any($v[]; type != "number") then "INCOMPLETE [known="+(([$v[]|select(type=="number")]|add // 0)|round2|tostring)+"]" else ($v|add) end;
      "TOTALS (active pods; requests include init/sidecar peak and overhead; quantities are CPU millicores / memory bytes)",
      (["CPU USED",(total("cpu")|cpu_fmt),"CPU REQUEST",(total("cpu_request")|cpu_fmt),"CPU LIMIT",(total("cpu_limit")|cpu_fmt)]|@tsv),
      (["MEM USED",(total("memory")|mem_fmt),"MEM REQUEST",(total("memory_request")|mem_fmt),"MEM LIMIT",(total("memory_limit")|mem_fmt)]|@tsv),
      (["MEM MiB/GiB"] + (["memory","memory_request","memory_limit"]|map(. as $k | $k))|@tsv),
      (["MEM TOTALS MiB/GiB",(total("memory")|if type=="number" then "\((./1048576)|round2) / \((./1073741824)|round2)" else . end),
       (total("memory_request")|if type=="number" then "\((./1048576)|round2) / \((./1073741824)|round2)" else . end),
       (total("memory_limit")|if type=="number" then "\((./1048576)|round2) / \((./1073741824)|round2)" else . end)]|@tsv),
      (["METRICS UPDATED",([.[].metrics_timestamp|select(.!="UNAVAILABLE")]|min // "UNAVAILABLE"),"WINDOW",([.[].metrics_window]|unique|join(","))]|@tsv)
    ' "$rows"
    printf 'LIMITATIONS\tUNSET is not zero; UNBOUNDED means one or more container limits are absent; pod-level resources and active resize reservations are explicitly not inferred.\n'
    rm -f -- "$rows"
}

containers_report() {
    local selected=${1:-} p m
    collect_pods; collect_metrics
    data_source pods; data_source metrics
    if ! has jq; then fallback_report pods; return; fi
    p=$(json_cache_path pods); m=$(json_cache_path metrics)
    printf 'POD\tCONTAINER\tTYPE\tSTATE\tREADY\tRESTARTS\tCPU USED\tCPU REQ\tCPU LIMIT\tMEM USED\tMEM REQ\tMEM LIMIT\tIMAGE\tIMAGE ID\tLAST TERMINATION\n'
    jq -r --arg pod "$selected" --slurpfile mx "$m" "$JQ_QUANTITIES"'
      ($mx[0].items // [] | map({key:.metadata.name,value:.})|from_entries) as $metrics |
      .items[]? | select($pod=="" or .metadata.name==$pod) | . as $p |
      (([.spec.containers[]?|.+{sentinel_type:"APP"}])+([.spec.initContainers[]?|.+{sentinel_type:(if .restartPolicy=="Always" then "SIDECAR" else "INIT" end)}])+([.spec.ephemeralContainers[]?|.+{sentinel_type:"EPHEMERAL"}]))[] | . as $c |
      ([$p.status.containerStatuses[]?,$p.status.initContainerStatuses[]?,$p.status.ephemeralContainerStatuses[]?|select(.name==$c.name)][0] // {}) as $s |
      ([$metrics[$p.metadata.name].containers[]?|select(.name==$c.name)][0] // {}) as $m |
      [$p.metadata.name,.name,.sentinel_type,($s.state.waiting.reason // $s.state.terminated.reason // (if $s.state.running then "Running" else "UNKNOWN" end)),
       (if $s.ready==null then "UNKNOWN" else ($s.ready|tostring) end),($s.restartCount // 0),
       ($m.usage.cpu|q("cpu")|cpu_fmt),(.resources.requests.cpu|if .==null then "UNSET" else q("cpu") // "PARSE_ERROR" end|cpu_fmt),
       (.resources.limits.cpu|if .==null then "UNSET" else q("cpu") // "PARSE_ERROR" end|cpu_fmt),
       ($m.usage.memory|q("memory")|mem_fmt),(.resources.requests.memory|if .==null then "UNSET" else q("memory") // "PARSE_ERROR" end|mem_fmt),
       (.resources.limits.memory|if .==null then "UNSET" else q("memory") // "PARSE_ERROR" end|mem_fmt),.image,($s.imageID // "UNKNOWN"),
       ($s.lastState.terminated|if . then "\(.reason // "UNKNOWN") exit=\(.exitCode) at=\(.finishedAt)" else "-" end)]|@tsv' "$p"
}

workloads_report() {
    collect_workloads; data_source workloads
    if ! has jq; then fallback_report workloads; return; fi
    printf 'KIND\tNAME\tDESIRED\tREADY\tAVAILABLE\tUPDATED/SUCCEEDED\tSTATUS\tDETAIL\n'
    jq -r '.items[]? | . as $x |
      (if .kind=="DaemonSet" then (.status.desiredNumberScheduled // "UNKNOWN") elif .kind=="Job" then (.spec.completions // 1) elif .kind=="CronJob" then "N/A" else (.spec.replicas // 1) end) as $desired |
      (if .kind=="DaemonSet" then (.status.numberReady // 0) elif .kind=="Job" then (.status.succeeded // 0) elif .kind=="CronJob" then (.status.active // []|length) else (.status.readyReplicas // 0) end) as $ready |
      (if .kind=="CronJob" then (if .spec.suspend then "SUSPENDED" else "INFO" end)
       elif any(.status.conditions[]?; .type=="Failed" and .status=="True") then "FAIL"
       elif .kind=="Job" then (if $ready >= $desired then "OK" else "ACTIVE" end)
       elif .kind=="ReplicaSet" and $desired==0 then "SCALED_ZERO"
       elif ($desired|type)!="number" then "UNKNOWN_DESIRED"
       elif $ready < $desired then "FAIL"
       elif ((.status.observedGeneration // 0) < (.metadata.generation // 0)) then "WARN_UNOBSERVED"
       else "OK" end) as $health |
      [.kind,.metadata.name,$desired,$ready,(.status.availableReplicas // .status.numberAvailable // "N/A"),
       (.status.updatedReplicas // .status.updatedNumberScheduled // .status.succeeded // "N/A"),$health,
       ([.status.conditions[]?|select(.status=="False" or .type=="Failed")|(.reason // .type)+": "+(.message // "")]|join("; "))]|@tsv' "$(json_cache_path workloads)"
}

events_report() {
    local mode=${1:-all}
    collect_events; [[ $mode == csv || $mode == raw ]] || data_source events
    if ! has jq; then fallback_report events; return; fi
    local p; p=$(json_cache_path events)
    if [[ $mode == raw ]]; then jq . "$p"; return; fi
    jq -r --arg mode "$mode" '
      def fields: [.eventTime // .series.lastObservedTime // .lastTimestamp // .firstTimestamp // .metadata.creationTimestamp,
       .type,.reason,((.involvedObject.kind // "Object")+"/"+(.involvedObject.name // "UNKNOWN")),
       .involvedObject.namespace // .metadata.namespace,.message,(.series.count // .count // 1),(.reportingComponent // .source.component // "UNKNOWN")];
      (["TIMESTAMP","TYPE","REASON","OBJECT","NAMESPACE","MESSAGE","COUNT","SOURCE"] | if $mode=="csv" then @csv else @tsv end),
      ([.items[]? | select($mode!="warnings" or .type=="Warning") | fields] | sort_by(.[0])[] | if $mode=="csv" then @csv else @tsv end)
    ' "$p"
}

images_report() {
    collect_pods; data_source pods
    if ! has jq; then fallback_report pods; return; fi
    printf 'POD\tCONTAINER\tDECLARED IMAGE\tRUNTIME IMAGE ID\tTAG\tDECLARED DIGEST\tMUTABLE TAG\tDIGEST EVIDENCE\n'
    jq -r '.items[]? | . as $p | (.spec.containers[]?,.spec.initContainers[]?,.spec.ephemeralContainers[]?) | . as $c |
      ([$p.status.containerStatuses[]?,$p.status.initContainerStatuses[]?,$p.status.ephemeralContainerStatuses[]?|select(.name==$c.name)][0] // {}) as $s |
      (.image|split("@")|.[1] // "-") as $digest |
      (.image|split("@")|.[0]|split("/")|last|if contains(":") then split(":")|last else "latest (implicit)" end) as $tag |
      (.image|(try capture("@(?<d>sha256:[a-fA-F0-9]{64})$").d catch null) // null) as $declared |
      ($s.imageID // ""|(try capture("(?:@|://)(?<d>sha256:[a-fA-F0-9]{64})$").d catch null) // null) as $runtime |
      [$p.metadata.name,.name,.image,($s.imageID // "UNKNOWN"),$tag,$digest,(if $digest=="-" then "YES" else "NO (digest pinned)" end),
       (if $declared==null or $runtime==null then "NOT_VERIFIED" elif $declared==$runtime then "DIGEST_MATCH" else "POTENTIAL_DRIFT: index/manifest representation not verified" end)]|@tsv' "$(json_cache_path pods)"
}

nodes_report() {
    collect_pods; collect_workloads
    collect_json nodes 10 cluster nodes '{items:[.items[]?|{metadata:{name:.metadata.name,labels:.metadata.labels},spec:{unschedulable:.spec.unschedulable,taints:.spec.taints},status:{capacity:.status.capacity,allocatable:.status.allocatable,conditions:.status.conditions,nodeInfo:{kubeletVersion:.status.nodeInfo.kubeletVersion,osImage:.status.nodeInfo.osImage,containerRuntimeVersion:.status.nodeInfo.containerRuntimeVersion}}}]}' 'NAME:.metadata.name,CPU:.status.capacity.cpu,CPU-ALLOC:.status.allocatable.cpu,MEM:.status.capacity.memory,MEM-ALLOC:.status.allocatable.memory,UNSCHEDULABLE:.spec.unschedulable' || :
    collect_json nodemetrics 5 cluster nodes.metrics.k8s.io '{items:[.items[]?|{metadata:{name:.metadata.name},timestamp,window,usage}]}' '' || :
    data_source nodes; data_source nodemetrics
    if ! has jq; then fallback_report nodes; return; fi
    local rows
    rows=$(mktemp "$RUN_DIR/node-pods.XXXXXX") || return 1
    resource_rows_json > "$rows" || { printf 'NODE RESERVATIONS\tPARSE_ERROR\n'; rm -f -- "$rows"; return 1; }
    printf 'SCOPE\tCapacity/actual usage: entire node. Requested/limits/pods: selected namespace only. Cluster reservation headroom: UNKNOWN.\n'
    printf 'NODE\tPOOL / ROLE\tZONE\tCPU CAPACITY\tCPU ALLOC\tNS CPU REQ\tNS CPU LIMIT\tCPU USED\tCPU/ALLOC\tCPU ACTUAL HEADROOM\tMEM CAPACITY\tMEM ALLOC\tNS MEM REQ\tNS MEM LIMIT\tMEM USED\tMEM/ALLOC\tMEM ACTUAL HEADROOM\tNS PODS\tSTATUS\n'
    jq -r --slurpfile px "$rows" --slurpfile mx "$(json_cache_path nodemetrics)" --arg pods_status "$(cache_status pods)" "$JQ_QUANTITIES"'
      def reservation($a;$k): if $pods_status!="OK" and $pods_status!="EMPTY_RESULT" then $pods_status
        elif any($a[]; (.[$k]|type)!="number") then "INCOMPLETE" else ([$a[]|.[$k]]|add // 0) end;
      ($mx[0].items // []|map({key:.metadata.name,value:.})|from_entries) as $metrics |
      .items[]? | . as $n | [(.metadata.labels // {})|to_entries[]?|select(.key|test("(^|/)(nodepool|agentpool|pool)$|node-role.kubernetes.io/|nodegroup|node-pool"))|.key+"="+.value] as $labels |
      [$px[0][]|select(.node==$n.metadata.name and .active)] as $pods |
      ($metrics[.metadata.name].usage.cpu|q_state("cpu")) as $cpu | ($metrics[.metadata.name].usage.memory|q_state("memory")) as $mem |
      (.status.allocatable.cpu|q_state("cpu")) as $ca | (.status.allocatable.memory|q_state("memory")) as $ma |
      [.metadata.name,($labels|if length==0 then "UNDISCOVERED" else join(",") end),(.metadata.labels["topology.kubernetes.io/zone"] // "-"),
       (.status.capacity.cpu|q_state("cpu")|cpu_fmt),($ca|cpu_fmt),(reservation($pods;"cpu_request")|cpu_fmt),(reservation($pods;"cpu_limit")|cpu_fmt),($cpu|cpu_fmt),pct($cpu;$ca),
       (if ($cpu|type)=="number" and ($ca|type)=="number" then ($ca-$cpu|cpu_fmt) else "N/A" end),
       (.status.capacity.memory|q_state("memory")|mem_fmt),($ma|mem_fmt),(reservation($pods;"memory_request")|mem_fmt),(reservation($pods;"memory_limit")|mem_fmt),($mem|mem_fmt),pct($mem;$ma),
       (if ($mem|type)=="number" and ($ma|type)=="number" then ($ma-$mem|mem_fmt) else "N/A" end),
       (if $pods_status=="OK" or $pods_status=="EMPTY_RESULT" then ($pods|length) else $pods_status end),
       (([.status.conditions[]?|select((.type=="Ready" and .status!="True") or (.type!="Ready" and .status=="True"))|.type+"="+.status] + (if any(.status.conditions[]?;.type=="Ready") then [] else ["Ready=UNKNOWN"] end) + (if .spec.unschedulable then ["SchedulingDisabled"] else [] end))|if length==0 then "OK" else join(",") end)]|@tsv' "$(json_cache_path nodes)"
    printf 'NODE POOL GROUPS\nPOOL / ROLE\tNODE COUNT\n'
    jq -r '[.items[]?|{pool:([(.metadata.labels // {})|to_entries[]?|select(.key|test("(^|/)(nodepool|agentpool|pool)$|node-role.kubernetes.io/|nodegroup|node-pool"))|.key+"="+.value]|sort|if length==0 then "UNDISCOVERED" else join(",") end)}]|group_by(.pool)[]|[.[0].pool,length]|@tsv' "$(json_cache_path nodes)"
    rm -f -- "$rows"
}

network_rows_json() {
    jq -c --slurpfile px "$(json_cache_path pods)" --slurpfile sx "$(json_cache_path endpointslices)" --slurpfile ex "$(json_cache_path endpoints)" \
      --arg slices_state "$(cache_status endpointslices)" --arg endpoints_state "$(cache_status endpoints)" --arg pods_state "$(cache_status pods)" '
      def available($s): $s=="OK" or $s=="EMPTY_RESULT";
      [.items[]? | . as $svc |
       [($svc.spec.selector // {})|to_entries[]] as $selector |
       [$px[0].items[]? | select(($selector|length)>0) | . as $pod | select(all($selector[]; $pod.metadata.labels[.key]==.value))] as $pods |
       [$sx[0].items[]?|select(.metadata.labels["kubernetes.io/service-name"]==$svc.metadata.name)] as $slices |
       [$slices[].endpoints[]? | select(.conditions.ready != false)] as $ready |
       [$ex[0].items[]?|select(.metadata.name==$svc.metadata.name)] as $ep |
       (if available($slices_state) and ($slices|length)>0 then "EndpointSlice"
        elif available($endpoints_state) then "Endpoints"
        elif available($slices_state) then "EndpointSlice" else "UNKNOWN" end) as $source |
       (if $source=="EndpointSlice" then ([$ready[].addresses[]?]|unique|length)
        elif $source=="Endpoints" then ([$ep[].subsets[]?.addresses[]?.ip]|unique|length) else null end) as $count |
       (if $source=="EndpointSlice" then ([$ready[].targetRef|select(.kind=="Pod")|.name]|unique)
        elif $source=="Endpoints" then ([$ep[].subsets[]?.addresses[]?.targetRef|select(.kind=="Pod")|.name]|unique) else [] end) as $represented |
       {name:.metadata.name,type:(.spec.type // "ClusterIP"),cluster_ip:(.spec.clusterIP // "-"),
        selector:($selector|map(.key+"="+.value)|join(",")),
        pods:(if available($pods_state) then ($pods|map(.metadata.name)) else null end),
        ready_endpoints:$count,endpoint_source:$source,
        addresses:(if $source=="EndpointSlice" then [$ready[].addresses[]?]|unique elif $source=="Endpoints" then [$ep[].subsets[]?.addresses[]?.ip]|unique else [] end),
        ports:(.spec.ports // []|map("\(.port):\(.targetPort // .port)/\(.protocol // "TCP")")|join(",")),
        endpoint_ports:([$slices[].ports[]?|"\(.port // "UNKNOWN")/\(.protocol // "TCP")"]|unique|join(",")),
        external:([.status.loadBalancer.ingress[]?|.ip // .hostname]|join(",")),
        selector_ready_missing:([$pods[]|select(any(.status.conditions[]?; .type=="Ready" and .status=="True"))|.metadata.name] - $represented),
        status:(if .spec.type=="ExternalName" then "N/A_EXTERNAL_NAME"
          elif ($selector|length)==0 then "INFO_MANUAL_ENDPOINTS"
          elif .spec.clusterIP=="None" and $count==0 then "INFO_HEADLESS_NO_READY_ENDPOINTS"
          elif $count==null then "UNKNOWN_ENDPOINTS"
          elif $count==0 then "WARN_NO_READY_ENDPOINTS"
          elif .spec.type=="LoadBalancer" and (.status.loadBalancer.ingress // []|length)==0 then "WARN_LB_PENDING"
          elif available($pods_state) and ([$pods[]|select(any(.status.conditions[]?; .type=="Ready" and .status=="True"))|.metadata.name] - $represented|length)>0 then "WARN_READY_POD_NOT_REPRESENTED"
          else "OK" end)}]' "$(json_cache_path services)"
}

network_report() {
    collect_pods; collect_network
    data_source services; data_source endpointslices; data_source endpoints; data_source ingresses
    if ! has jq; then fallback_report services; fallback_report endpointslices; fallback_report ingresses; return; fi
    printf 'SERVICE\tTYPE\tCLUSTER IP\tSELECTOR\tMATCHED PODS\tREADY ADDRESSES\tSOURCE\tADDRESSES\tSERVICE PORTS\tENDPOINT PORTS\tEXTERNAL\tSTATUS\tMISSING READY PODS\n'
    network_rows_json | jq -r '.[]|[.name,.type,.cluster_ip,.selector,(.pods|if .==null then "UNKNOWN" else join(",") end),(.ready_endpoints // "UNKNOWN"),.endpoint_source,(.addresses|join(",")),.ports,.endpoint_ports,.external,.status,(.selector_ready_missing|join(","))]|@tsv'
    printf 'INGRESS\tCLASS\tHOST\tPATH\tSERVICE\tPORT\tTLS SECRET\tLOADBALANCER\n'
    jq -r '.items[]? | . as $i | (.spec.rules // [{}])[] | . as $r | (.http.paths // [{}])[] |
      [$i.metadata.name,($i.spec.ingressClassName // "default"),($r.host // "*"),(.path // "/"),(.backend.service.name // $i.spec.defaultBackend.service.name // "NON_SERVICE/UNKNOWN"),
       (.backend.service.port.number // .backend.service.port.name // $i.spec.defaultBackend.service.port.number // "-"),
       ([$i.spec.tls[]?|.secretName]|join(",")),([$i.status.loadBalancer.ingress[]?|.ip // .hostname]|join(","))]|@tsv' "$(json_cache_path ingresses)"
    printf 'INTERPRETATION\tReady EndpointSlice addresses use ready != false; address count can differ from pod count on dual-stack clusters. Pod identity is used for missing-backend findings. Selectorless and headless services require intent review.\n'
}

storage_report() {
    collect_storage
    collect_json pvs 300 cluster persistentvolumes '{items:[.items[]?|{metadata:{name:.metadata.name},spec:{capacity:.spec.capacity,accessModes:.spec.accessModes,persistentVolumeReclaimPolicy:.spec.persistentVolumeReclaimPolicy,storageClassName:.spec.storageClassName,claimRef:{namespace:.spec.claimRef.namespace,name:.spec.claimRef.name}},status}]}' 'NAME:.metadata.name,STATUS:.status.phase,CLASS:.spec.storageClassName,CAPACITY:.spec.capacity.storage,CLAIM-NS:.spec.claimRef.namespace,CLAIM:.spec.claimRef.name' || :
    collect_json storageclasses 300 cluster storageclasses.storage.k8s.io '{items:[.items[]?|{metadata:{name:.metadata.name},provisioner,reclaimPolicy,volumeBindingMode,allowVolumeExpansion}]}' 'NAME:.metadata.name,PROVISIONER:.provisioner,BINDING:.volumeBindingMode,RECLAIM:.reclaimPolicy' || :
    collect_json volumeattachments 30 cluster volumeattachments.storage.k8s.io '{items:[.items[]?|{metadata:{name:.metadata.name},spec:{attacher:.spec.attacher,nodeName:.spec.nodeName,source:{persistentVolumeName:.spec.source.persistentVolumeName}},status:{attached:.status.attached,attachError:.status.attachError,detachError:.status.detachError}}]}' 'NAME:.metadata.name,NODE:.spec.nodeName,PV:.spec.source.persistentVolumeName,ATTACHED:.status.attached' || :
    data_source pvcs; data_source pvs; data_source storageclasses; data_source volumeattachments
    if ! has jq; then fallback_report pvcs; fallback_report pvs; fallback_report storageclasses; fallback_report volumeattachments; return; fi
    printf 'PVC\tSTATUS\tVOLUME\tREQUEST\tCAPACITY\tACCESS\tSTORAGE CLASS\tCONDITIONS\n'
    jq -r '.items[]?|[.metadata.name,(.status.phase // "UNKNOWN"),(.spec.volumeName // "-"),(.spec.resources.requests.storage // "UNSET"),(.status.capacity.storage // "UNKNOWN"),(.spec.accessModes // []|join(",")),(.spec.storageClassName // "default"),([.status.conditions[]?|.type+"="+.status]|join(","))]|@tsv' "$(json_cache_path pvcs)"
    printf 'PV (selected namespace claims plus unbound volumes)\tSTATUS\tCAPACITY\tCLASS\tRECLAIM\tCLAIM\n'
    jq -r --arg ns "$SENTINEL_NAMESPACE" '.items[]?|select(.spec.claimRef.namespace==$ns or .spec.claimRef.namespace==null)|[.metadata.name,.status.phase,.spec.capacity.storage,.spec.storageClassName,.spec.persistentVolumeReclaimPolicy,((.spec.claimRef.namespace // "-")+"/"+(.spec.claimRef.name // "-"))]|@tsv' "$(json_cache_path pvs)"
    printf 'STORAGE CLASS\tPROVISIONER\tRECLAIM\tBINDING MODE\tEXPANSION\n'
    jq -r '.items[]?|[.metadata.name,.provisioner,.reclaimPolicy,.volumeBindingMode,(.allowVolumeExpansion // false)]|@tsv' "$(json_cache_path storageclasses)"
    printf 'VOLUME ATTACHMENT (selected namespace claims)\tNODE\tPV\tATTACHED\tERROR\n'
    jq -r --slurpfile px "$(json_cache_path pvcs)" '[$px[0].items[]?|.spec.volumeName] as $volumes | .items[]?|. as $v|select($volumes|index($v.spec.source.persistentVolumeName))|[.metadata.name,.spec.nodeName,.spec.source.persistentVolumeName,.status.attached,([.status.attachError.message,.status.detachError.message]|map(select(.!=null))|join("; "))]|@tsv' "$(json_cache_path volumeattachments)"
}

select_pod() {
    collect_pods
    local -a names=()
    if has jq; then mapfile -t names < <(jq -r '.items[]?.metadata.name' "$(json_cache_path pods)")
    elif [[ -s $CACHE_DIR/pods.txt ]]; then mapfile -t names < <(awk 'NR>1 {print $1}' "$CACHE_DIR/pods.txt"); fi
    ((${#names[@]})) || { printf 'POD SELECTION\t%s\n' "$(cache_status pods)"; return 1; }
    choose 'Select pod' "${names[@]}" || return 1
    SELECTED_POD=$REPLY
}

inspector_report() {
    local pod=$1 p
    collect_pods; collect_workloads; collect_events; collect_network; collect_storage
    data_source pods
    if ! has jq; then fallback_report pods; return; fi
    p=$(json_cache_path pods)
    if ! jq -e --arg name "$pod" 'any(.items[]?; .metadata.name==$name)' "$p" >/dev/null; then printf 'POD\tRESOURCE_NOT_FOUND\n'; return 1; fi
    jq -r --arg pod "$pod" --slurpfile wx "$(json_cache_path workloads)" "$JQ_QUANTITIES"'
      .items[]?|select(.metadata.name==$pod)|
      (["POD",.metadata.name,"OWNER",owner($wx[0]),"NODE",(.spec.nodeName // "UNSCHEDULED")]|@tsv),
      (["PHASE",.status.phase,"QOS",.status.qosClass,"IP",(.status.podIP // "-"),"SERVICE ACCOUNT",(.spec.serviceAccountName // "default")]|@tsv),
      ("CONDITIONS\tSTATUS\tREASON\tMESSAGE"),
      (.status.conditions[]?|[.type,.status,.reason,.message]|@tsv),
      ("REFERENCES (names only; no Secret values)\tCONTAINER / VOLUME\tNAME\tMOUNT / KEY"),
      ((.spec.containers[]?,.spec.initContainers[]?,.spec.ephemeralContainers[]?)|. as $c|
        (.env[]?|select(.valueFrom.secretKeyRef)|["SECRET ENV",$c.name,.valueFrom.secretKeyRef.name,.valueFrom.secretKeyRef.key]|@tsv),
        (.env[]?|select(.valueFrom.configMapKeyRef)|["CONFIGMAP ENV",$c.name,.valueFrom.configMapKeyRef.name,.valueFrom.configMapKeyRef.key]|@tsv),
        (.envFrom[]?|select(.secretRef)|["SECRET ENVFROM",$c.name,.secretRef.name,"keys not retrieved"]|@tsv),
        (.envFrom[]?|select(.configMapRef)|["CONFIGMAP ENVFROM",$c.name,.configMapRef.name,"-"]|@tsv),
        (.volumeMounts[]?|["VOLUME MOUNT",$c.name,.name,.mountPath]|@tsv)),
      (.spec.volumes[]?|. as $v|
        (select(.secret)|["SECRET VOLUME",.name,.secret.secretName,"-"]|@tsv),
        (select(.configMap)|["CONFIGMAP VOLUME",.name,.configMap.name,"-"]|@tsv),
        (select(.persistentVolumeClaim)|["PVC",.name,.persistentVolumeClaim.claimName,"-"]|@tsv),
        (.projected.sources[]?|select(.secret)|["PROJECTED SECRET",$v.name,.secret.name,"-"]|@tsv),
        (.projected.sources[]?|select(.configMap)|["PROJECTED CONFIGMAP",$v.name,.configMap.name,"-"]|@tsv))' "$p"
    containers_report "$pod"
    printf 'RELATED EVENTS\nTIMESTAMP\tTYPE\tREASON\tMESSAGE\tCOUNT\n'
    jq -r --arg pod "$pod" '[.items[]?|select(.involvedObject.kind=="Pod" and .involvedObject.name==$pod)|[.eventTime // .lastTimestamp // .metadata.creationTimestamp,.type,.reason,.message,.series.count // .count // 1]]|sort_by(.[0])[]|@tsv' "$(json_cache_path events)"
    printf 'SERVICE RELATIONSHIPS\nSERVICE\tREADY ENDPOINT ADDRESSES\tSTATUS\n'
    network_rows_json | jq -r --arg pod "$pod" '.[]|select(.pods!=null and (.pods|index($pod)))|[.name,.ready_endpoints,.status]|@tsv'
    printf 'CERTIFICATE REFERENCES\tReferenced Secret names above can be correlated in Certificate/TLS Auditor; Secret payloads are never included in inspection.\n'
}

inspector_menu() {
    local out
    select_pod || return
    out=$(mktemp "$RUN_DIR/inspector.XXXXXX") || return
    inspector_report "$SELECTED_POD" > "$out"
    view_file "$out" "Pod inspector: $SELECTED_POD"
    rm -f -- "$out"
}

findings_add() {
    local severity=$1 category=$2 resource=$3 issue=$4 evidence=$5 field
    local -a fields=()
    for field in "$severity" "$category" "$resource" "$issue" "$evidence"; do
        field=${field//$'\t'/ }; field=${field//$'\n'/ }; field=${field//$'\r'/ }
        fields+=("$field")
    done
    printf '%s\t%s\t%s\t%s\t%s\n' "${fields[@]}" | redact >> "$RUN_DIR/findings.tsv"
}

findings_ingest() {
    local severity category resource issue evidence
    while IFS=$'\t' read -r severity category resource issue evidence; do
        [[ -n $severity ]] && findings_add "$severity" "$category" "$resource" "$issue" "${evidence:-OBSERVED API status}"
    done
}

health_pod_findings() {
    jq -r "$JQ_QUANTITIES"'
      .items[]? | . as $p | ("Pod/"+.metadata.name) as $name |
      (if .status.phase=="Failed" then ["FAIL","PODS",$name,"Pod failed: "+(.status.reason // "Failed"),"OBSERVED pod phase/reason"]
       elif .status.phase=="Pending" then ["WARN","PODS",$name,"Pod Pending","OBSERVED pod phase; scheduling events below"]
       elif .status.phase=="Running" and any(.status.conditions[]?;.type=="Ready" and .status!="True") then ["FAIL","PODS",$name,"Running pod is not Ready","OBSERVED Pod Ready condition"]
       elif .status.phase=="Running" and (any(.status.conditions[]?;.type=="Ready")|not) then ["UNKNOWN","PODS",$name,"Pod Ready condition is absent","Readiness NOT VERIFIED; Running phase alone does not prove readiness"]
       elif .status.phase==null or .status.phase=="Unknown" then ["UNKNOWN","PODS",$name,"Pod phase unavailable or Unknown","OBSERVED status.phase"] else empty end | @tsv),
      (.status.conditions[]?|select(.type=="PodScheduled" and .status=="False")|["WARN","SCHEDULING",$name,(.reason // "Unschedulable")+": "+(.message // ""),"OBSERVED PodScheduled=False"]|@tsv),
      ((.status.containerStatuses[]?,.status.initContainerStatuses[]?,.status.ephemeralContainerStatuses[]?)|. as $c |
        (if (.state.waiting.reason // "" | test("CrashLoopBackOff|ImagePullBackOff|ErrImagePull|CreateContainerConfigError|CreateContainerError|RunContainerError|InvalidImageName")) then
          ["FAIL","CONTAINERS",($name+"/"+.name),.state.waiting.reason+": "+(.state.waiting.message // ""),"OBSERVED waiting container status"]
         elif .state.waiting.reason=="ContainerCreating" and (now-($p.metadata.creationTimestamp|epoch // now))>300 then
          ["WARN","CONTAINERS",($name+"/"+.name),"ContainerCreating; pod older than 5 minutes","OBSERVED pod age; container wait start is not reported"] else empty end|@tsv),
        (if .state.terminated.reason=="OOMKilled" then ["FAIL","CONTAINERS",($name+"/"+.name),"Current termination OOMKilled","OBSERVED state.terminated.reason"]
         elif .lastState.terminated.reason=="OOMKilled" then ["WARN","CONTAINERS",($name+"/"+.name),"Previous termination OOMKilled","OBSERVED lastState; may be recovered"] else empty end|@tsv),
        (if .ready==false and $p.status.phase=="Running" and (([$p.spec.containers[]?.name]+[$p.spec.initContainers[]?|select(.restartPolicy=="Always")|.name]|index($c.name))!=null) then
          ["WARN","CONTAINERS",($name+"/"+.name),"Container is not ready","OBSERVED container ready=false; readiness timing/intent requires review"] else empty end|@tsv),
        (if (.restartCount // 0)>=5 then ["WARN","RESTARTS",($name+"/"+.name),"Restart count "+(.restartCount|tostring),"OBSERVED cumulative count; not a restart rate"] else empty end|@tsv)),
      (if .metadata.deletionTimestamp!=null then ["INFO","PODS",$name,"Pod terminating","OBSERVED deletionTimestamp"] else empty end|@tsv)
    ' "$(json_cache_path pods)" | findings_ingest
}

health_workload_findings() {
    jq -r '
      .items[]? | ("\(.kind)/\(.metadata.name)") as $name |
      (if .kind=="DaemonSet" then (.status.desiredNumberScheduled // null) else (.spec.replicas // 1) end) as $desired |
      (if .kind=="DaemonSet" then (.status.numberReady // 0) else (.status.readyReplicas // 0) end) as $ready |
      (if .kind=="DaemonSet" and $desired==null then ["UNKNOWN","WORKLOADS",$name,"Desired scheduled count is absent","DaemonSet availability NOT VERIFIED"] else empty end|@tsv),
      (if (.kind=="Deployment" or .kind=="StatefulSet" or .kind=="DaemonSet") and ($desired|type)=="number" and $ready < $desired then
        ["FAIL","WORKLOADS",$name,"Ready replicas \($ready)/\($desired)","OBSERVED desired and ready counts"] else empty end|@tsv),
      (if .kind=="Deployment" and (.status.availableReplicas // 0)<$desired then
        ["FAIL","WORKLOADS",$name,"Available replicas \(.status.availableReplicas // 0)/\($desired)","OBSERVED deployment availability"] else empty end|@tsv),
      (if .kind=="StatefulSet" and .status.currentRevision!=null and .status.updateRevision!=null and .status.currentRevision!=.status.updateRevision then
        ["WARN","WORKLOADS",$name,"Current and update revisions differ","OBSERVED rollout state; update strategy may intentionally partition"] else empty end|@tsv),
      (if .kind=="Job" and any(.status.conditions[]?;.type=="Failed" and .status=="True") then
        ["FAIL","JOBS",$name,"Job Failed",([.status.conditions[]?|select(.type=="Failed")|.reason // "Failed"]|join(","))] else empty end|@tsv),
      (if .kind=="CronJob" and .spec.suspend==true then ["INFO","CRONJOBS",$name,"CronJob suspended","OBSERVED spec.suspend; intent not inferred"] else empty end|@tsv),
      (if .kind!="Job" and .kind!="CronJob" and (.metadata.generation // 0)>(.status.observedGeneration // 0) then
        ["WARN","WORKLOADS",$name,"Controller has not observed latest generation","OBSERVED metadata.generation > status.observedGeneration"] else empty end|@tsv)
    ' "$(json_cache_path workloads)" | findings_ingest
}

health_network_findings() {
    network_rows_json | jq -r '.[]|select(.status|startswith("WARN"))|
      ["WARN","NETWORK",("Service/"+.name),.status,("OBSERVED "+.endpoint_source+" ready addresses="+(.ready_endpoints|tostring)+" missing ready pods="+(.selector_ready_missing|join(",")))]|@tsv' | findings_ingest
    jq -r '.items[]?|select(.status.phase=="Lost" or .status.phase=="Pending")|
      [(if .status.phase=="Lost" then "FAIL" else "WARN" end),"STORAGE",("PVC/"+.metadata.name),"PVC "+.status.phase,"OBSERVED PVC phase; Pending may be WaitForFirstConsumer"]|@tsv' "$(json_cache_path pvcs)" | findings_ingest
    jq -r --arg ns "$SENTINEL_NAMESPACE" '.items[]?|select(.spec.claimRef.namespace==$ns and (.status.phase=="Released" or .status.phase=="Failed"))|
      [(if .status.phase=="Failed" then "FAIL" else "WARN" end),"STORAGE",("PV/"+.metadata.name),"PV "+.status.phase,"OBSERVED PV phase; reclaim policy/intent require review"]|@tsv' "$(json_cache_path pvs)" | findings_ingest
    jq -r --slurpfile px "$(json_cache_path pvcs)" '[$px[0].items[]?|.spec.volumeName] as $volumes | .items[]?|. as $v|select($volumes|index($v.spec.source.persistentVolumeName))|
      select(.status.attachError!=null or .status.detachError!=null)|["FAIL","STORAGE",("VolumeAttachment/"+.metadata.name),([.status.attachError.message,.status.detachError.message]|map(select(.!=null))|join("; ")),"OBSERVED attach/detach error"]|@tsv' "$(json_cache_path volumeattachments)" | findings_ingest
}

health_event_findings() {
    jq -r '
      [.items[]?|select(.type=="Warning")]|group_by([.involvedObject.uid,.involvedObject.name,.reason,.message])[]|.[0] as $e|
      ["WARN","EVENTS",(($e.involvedObject.kind // "Object")+"/"+($e.involvedObject.name // "UNKNOWN")),
       ($e.reason // "Warning")+": "+($e.message // ""),
       ("OBSERVED retained event count="+([.[]|.series.count // .count // 1]|add|tostring)+" latest="+([.[]|.eventTime // .lastTimestamp // .metadata.creationTimestamp]|max // "UNKNOWN"))]|@tsv
    ' "$(json_cache_path events)" | findings_ingest
    # Exact object links only: no inference that a shared symptom proves causation.
    jq -r --slurpfile px "$(json_cache_path pods)" --slurpfile wx "$(json_cache_path workloads)" "$JQ_QUANTITIES"'
      .items[]?|select(.reason=="FailedScheduling" and .involvedObject.kind=="Pod")|. as $e|
      $px[0].items[]?|select(.metadata.name==$e.involvedObject.name and .status.phase=="Pending" and ($e.involvedObject.uid==null or .metadata.uid==$e.involvedObject.uid))|
      . as $p | owner($wx[0]) as $owner |
      ["INFO","CORRELATION",("Pod/"+.metadata.name),
       ($owner+" -> Pod Pending -> FailedScheduling -> "+($e.message // "reason unavailable")),
       "OBSERVED owner/event chain; root cause NOT VERIFIED"]|@tsv' "$(json_cache_path events)" | findings_ingest
}

health_pressure_findings() {
    resource_rows_json | jq -r --argjson cw "${CPU_WARN:-80}" --argjson cc "${CPU_CRIT:-90}" --argjson mw "${MEM_WARN:-80}" --argjson mc "${MEM_CRIT:-90}" '
      .[]|select(.active)|. as $p |
      (["cpu","memory","cpu_request","cpu_limit","memory_request","memory_limit"][] as $k|
        select($p[$k]=="PARSE_ERROR" or $p[$k]=="INCOMPLETE" or $p[$k]=="UNSUPPORTED_POD_LEVEL" or $p[$k]=="RESIZE_NOT_VERIFIED")|
        ["UNKNOWN","RESOURCE_PRESSURE",("Pod/"+$p.pod),($k+"="+$p[$k]),"Resource pressure NOT VERIFIED for this quantity"]|@tsv),
      ([{label:"CPU",used:.cpu,base:.cpu_request,denominator:"request",warn:$cw,critical:$cc},
        {label:"CPU",used:.cpu,base:.cpu_limit,denominator:"limit",warn:$cw,critical:$cc},
        {label:"MEM",used:.memory,base:.memory_request,denominator:"request",warn:$mw,critical:$mc},
        {label:"MEM",used:.memory,base:.memory_limit,denominator:"limit",warn:$mw,critical:$mc}][] |
       select((.used|type)=="number" and (.base|type)=="number" and .base>0)|(.used/.base*100) as $pc|select($pc>.warn)|
       [(if $pc>.critical and .denominator=="limit" then "FAIL" else "WARN" end),"RESOURCE_PRESSURE",("Pod/"+$p.pod),
        .label+"/"+.denominator+"="+(($pc*10|round/10)|tostring)+"%",
        "OBSERVED usage / "+.denominator+"; request saturation is not node pressure"]|@tsv)' | findings_ingest
    jq -r --slurpfile mx "$(json_cache_path nodemetrics)" --argjson cw "${CPU_WARN:-80}" --argjson cc "${CPU_CRIT:-90}" --argjson mw "${MEM_WARN:-80}" --argjson mc "${MEM_CRIT:-90}" "$JQ_QUANTITIES"'
      ($mx[0].items // []|map({key:.metadata.name,value:.})|from_entries) as $metrics |
      .items[]?|. as $n|($metrics[.metadata.name]) as $m|
      (if any(.status.conditions[]?;.type=="Ready") then empty else ["UNKNOWN","NODES",("Node/"+.metadata.name),"Node Ready condition is absent","Node readiness NOT VERIFIED"] end|@tsv),
      ([{r:"cpu",label:"CPU"},{r:"memory",label:"MEM"}][]|. as $d|
        ($n.status.allocatable[$d.r]|q_state($d.r)) as $alloc|($m.usage[$d.r]|q_state($d.r)) as $usage|
        select(($alloc|type)!="number" or $usage=="PARSE_ERROR")|
        ["UNKNOWN","NODE_PRESSURE",("Node/"+$n.metadata.name),($d.label+" allocatable="+($alloc|tostring)+" usage="+($usage|tostring)),"Node utilization NOT VERIFIED"]|@tsv),
      (.status.conditions[]?|select((.type=="Ready" and .status!="True") or (.type!="Ready" and .status=="True"))|
       ["FAIL","NODES",("Node/"+$n.metadata.name),(.type+"="+.status+": "+(.reason // "")),"OBSERVED node condition"]|@tsv),
      ([{r:"cpu",label:"CPU",warn:$cw,critical:$cc},{r:"memory",label:"MEM",warn:$mw,critical:$mc}][]|. as $d|
       ($m.usage[$d.r]|q($d.r)) as $used|($n.status.allocatable[$d.r]|q($d.r)) as $base|
       select($used!=null and $base!=null and $base>0)|($used/$base*100) as $pc|select($pc>$d.warn)|
       [(if $pc>$d.critical then "FAIL" else "WARN" end),"NODE_PRESSURE",("Node/"+$n.metadata.name),$d.label+"/allocatable="+(($pc*10|round/10)|tostring)+"%","OBSERVED node usage divided by allocatable"]|@tsv)
    ' "$(json_cache_path nodes)" | findings_ingest
}

health_report() {
    local key state overall=0 unknown=0 ok=0 failed=0 warnings=0 collector
    : > "$RUN_DIR/findings.tsv"
    collect_pods; collect_workloads; collect_metrics; collect_events
    # Reports here prime the same caches used by interactive views and evidence.
    network_report >/dev/null
    storage_report >/dev/null
    nodes_report >/dev/null
    if declare -F gitops_report >/dev/null; then gitops_report >/dev/null; fi
    if declare -F helm_report >/dev/null; then helm_report >/dev/null; fi
    if declare -F certificates_report >/dev/null; then certificates_report >/dev/null; fi
    printf 'KUBERNETES HEALTH & READINESS\nCONTEXT\t%s\nNAMESPACE\t%s\nTIME\t%s\n' "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf 'AUTHENTICATION\t%s\nAPI\t%s\nAPI LATENCY\t%s\nRBAC\t%s\n' "${AUTH_STATUS:-UNKNOWN}" "${API_STATUS:-UNKNOWN}" "${API_LATENCY:-UNKNOWN}" "${RBAC_STATUS:-UNKNOWN}"
    case ${AUTH_STATUS:-UNKNOWN}:${API_STATUS:-UNKNOWN} in *AUTH_ERROR*|*AUTH_REQUIRED*|*DNS_ERROR*|*TLS_ERROR*|*NETWORK_ERROR*|*API_TIMEOUT*) overall=3 ;; esac
    printf 'CATEGORY\tCOLLECTOR STATUS\tCACHE AGE (sec)\n'
    for key in pods workloads services endpointslices endpoints ingresses pvcs pvs storageclasses volumeattachments events nodes metrics nodemetrics flux_gitrepositories flux_kustomizations flux_helmrepositories flux_helmreleases helm cert_certificates cert_certificaterequests cert_issuers cert_clusterissuers tls_certificates; do
        state=$(cache_status "$key")
        printf '%s\t%s\t%s\n' "$key" "$state" "$(cache_age "$key")"
        case $state in
            OK|EMPTY_RESULT) ((ok+=1)) ;;
            RESOURCE_NOT_FOUND|NOT_CONFIGURED)
                case $key in flux_*|cert_*|endpointslices|endpoints) findings_add INFO CAPABILITY "$key" 'Not installed or not served' "$state" ;; *) ((unknown+=1)); findings_add UNKNOWN CAPABILITY "$key" 'Data unavailable' "$state" ;; esac ;;
            AUTH_ERROR|AUTH_REQUIRED|DNS_ERROR|TLS_ERROR|NETWORK_ERROR|API_TIMEOUT) overall=3; ((unknown+=1)); findings_add UNKNOWN API "$key" 'Collector unavailable' "$state" ;;
            *) ((unknown+=1)); findings_add UNKNOWN CAPABILITY "$key" 'Coverage unavailable; no healthy/zero claim' "$state" ;;
        esac
    done
    if has jq; then
        for collector in health_pod_findings health_workload_findings health_network_findings health_event_findings health_pressure_findings; do
            if ! "$collector"; then findings_add UNKNOWN ANALYSIS "$collector" 'PARSE_ERROR' 'Analysis incomplete; inspect collector diagnostics'; ((unknown+=1)); fi
        done
        if declare -F gitops_findings >/dev/null; then gitops_findings; fi
        if declare -F certificates_findings >/dev/null; then certificates_findings; fi
    else
        findings_add UNKNOWN ANALYSIS namespace 'Structured health analysis requires jq' 'Observed custom-column tables are available in resource views'
    fi
    if has awk; then
        awk '!seen[$0]++' "$RUN_DIR/findings.tsv" > "$RUN_DIR/findings-unique.tsv"
        mv -- "$RUN_DIR/findings-unique.tsv" "$RUN_DIR/findings.tsv"
        failed=$(awk -F '\t' '$1=="FAIL" || $1=="CRITICAL" {n++} END{print n+0}' "$RUN_DIR/findings.tsv")
        warnings=$(awk -F '\t' '$1=="WARN" {n++} END{print n+0}' "$RUN_DIR/findings.tsv")
    fi
    ((failed>0 && overall!=3)) && overall=1
    printf '\nFINDINGS\nSEVERITY\tCATEGORY\tRESOURCE\tISSUE\tEVIDENCE\n'
    cat -- "$RUN_DIR/findings.tsv"
    printf '\nCOUNTS\tFAIL %s\tWARN %s\tAVAILABLE COLLECTORS %s\tUNKNOWN COLLECTORS %s\n' "$failed" "$warnings" "$ok" "$unknown"
    printf 'INTERPRETATION\tCounts describe observed findings and evidence coverage; no percentage health score. Warning events may describe recovered historical conditions.\n'
    printf 'EXIT STATUS\t%s\t0=no observed FAIL (coverage may be incomplete); 1=operational FAIL; 3=authentication/API failure\n' "$overall"
    return "$overall"
}

summary_report() {
    local key
    collect_pods; collect_workloads; collect_metrics; collect_storage; collect_events
    if ! has jq; then fallback_report pods; return; fi
    printf 'LIVE SUMMARY\tSOURCE Kubernetes APIs / metrics.k8s.io\tPODS %s\tMETRICS %s\tCACHE %ss\n' "$(cache_status pods)" "$(cache_status metrics)" "$(cache_age pods)"
    if [[ $(cache_status pods) == OK || $(cache_status pods) == EMPTY_RESULT ]]; then
        jq -r '
          (["PODS",(.items|length),"READY",([.items[]?|select(any(.status.conditions[]?;.type=="Ready" and .status=="True"))]|length),
           "FAILED",([.items[]?|select(.status.phase=="Failed")]|length),"PENDING",([.items[]?|select(.status.phase=="Pending")]|length),
           "RESTARTS",([.items[]?|.status.containerStatuses[]?,.status.initContainerStatuses[]?|.restartCount // 0]|add // 0)]|@tsv)
        ' "$(json_cache_path pods)"
    fi
    for key in workloads pvcs events; do
        case $(cache_status "$key") in
            OK|EMPTY_RESULT)
                case $key in
                    workloads) jq -r '["Deployment","StatefulSet","DaemonSet"][] as $k | [.items[]?|select(.kind==$k)] as $w |
                      [$k,(if $k=="DaemonSet" and any($w[];.status.desiredNumberScheduled==null) then "UNKNOWN" else ([ $w[]|select((if $k=="DaemonSet" then (.status.numberReady // 0)>=(.status.desiredNumberScheduled // 0) else (.status.readyReplicas // 0)>=(.spec.replicas // 1) end))]|length|tostring) end)+"/"+($w|length|tostring)]|@tsv' "$(json_cache_path workloads)" ;;
                    pvcs) jq -r '["PVC BOUND",([.items[]?|select(.status.phase=="Bound")]|length|tostring)+"/"+(.items|length|tostring)]|@tsv' "$(json_cache_path pvcs)" ;;
                    events) jq -r '["WARNING EVENTS",([.items[]?|select(.type=="Warning")]|length)]|@tsv' "$(json_cache_path events)" ;;
                esac ;;
            *) printf '%s\t%s\n' "$key" "$(cache_status "$key")" ;;
        esac
    done
    if [[ $(cache_status pods) != OK && $(cache_status pods) != EMPTY_RESULT ]]; then
        printf 'RESOURCE TOTALS\t%s (pod inventory unavailable)\n' "$(cache_status pods)"
    else
      resource_rows_json | jq -r "$JQ_QUANTITIES"'
      map(select(.active)) as $a |
      def sumknown($k): [$a[]|.[$k]] as $v | if any($v[];type!="number") then "INCOMPLETE" else ($v|add // 0) end;
      (["CPU USED",(sumknown("cpu")|cpu_fmt),"CPU REQUEST",(sumknown("cpu_request")|cpu_fmt),"MEM USED",(sumknown("memory")|mem_fmt),"MEM REQUEST",(sumknown("memory_request")|mem_fmt)]|@tsv),
      "TOP CPU (active pods)",
      ($a|map(select((.cpu|type)=="number"))|sort_by(-.cpu)|.[:5][]|[.pod,(.cpu|cpu_fmt),(.cpu_request|cpu_fmt),(.cpu_limit|cpu_fmt),pct(.cpu;.cpu_request),.node]|@tsv),
      "TOP MEMORY (active pods)",
      ($a|map(select((.memory|type)=="number"))|sort_by(-.memory)|.[:5][]|[.pod,(.memory|mem_fmt),(.memory_request|mem_fmt),(.memory_limit|mem_fmt),pct(.memory;.memory_request),.node]|@tsv)'
    fi
    printf 'FLUX\t%s\tHELM\t%s\tCERTIFICATES\t%s\n' "$(cache_status flux_kustomizations)" "$(cache_status helm)" "$(cache_status cert_certificates)"
    if [[ -s $RUN_DIR/findings.tsv ]]; then printf 'RECENT FINDINGS (from last health audit; refresh Health for complete checks)\n'; awk 'NR<=5' "$RUN_DIR/findings.tsv"; fi
}

# 18 One-command triage, capability discovery and Sentinel doctor. These are
# orchestration layers over the shared collectors, findings engine and reports;
# they add no new cluster calls and no duplicated parsing.
next_check_hint() {
    case $1 in
        PODS|CONTAINERS|RESTARTS) printf 'Pod inspector + related events (dashboard 2) or --triage-workload NAME';;
        SCHEDULING) printf 'Node & capacity view (dashboard 3); compare requests with allocatable';;
        WORKLOADS|JOBS|CRONJOBS) printf 'Workload health (dashboard 4) and --triage-workload NAME';;
        NETWORK) printf 'Network relationships (dashboard 5); selector vs ready endpoints';;
        STORAGE) printf 'Storage view (dashboard 5 storage) and PVC/PV events';;
        NODES|NODE_PRESSURE) printf 'Node capacity (dashboard 3) and node conditions';;
        RESOURCE_PRESSURE) printf 'Live tracker sorted by cpu/memory (dashboard 1, key s)';;
        GITOPS) printf 'GitOps drift (dashboard 12) and deployment validation chain';;
        HELM) printf 'Helm status/history (dashboard 12)';;
        CERTIFICATES|TLS) printf 'Certificate/TLS auditor (dashboard 9); expiry + handshake';;
        EVENTS) printf 'Event timeline (dashboard 8) scoped to the affected object';;
        CORRELATION) printf 'Incident evidence bundle (dashboard 7 / --evidence ID)';;
        API|CAPABILITY|ANALYSIS) printf 'Diagnostics (dashboard 15); distinguish unavailable from failed';;
        *) printf 'Full health audit (--health) and diagnostics (dashboard 15)';;
    esac
}

triage_report() {
    local health_rc=0 overall=0 pods_state failed=0 warnings=0 unknown=0 info=0 total=0
    local severity category resource issue evidence
    # The health audit already collects every category, runs the findings engine
    # and deduplicates; triage renders the same evidence as a concise incident view.
    health_report >/dev/null || health_rc=$?
    pods_state=$(cache_status pods)
    printf 'KUBERNETES TRIAGE | one-command incident scope\nCONTEXT\t%s\nNAMESPACE\t%s\nTIME\t%s\n' \
        "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE" "$(timestamp)"
    printf 'AUTH\t%s\tAPI\t%s\tRBAC\t%s\tMETRICS\t%s\tGITOPS\t%s\tCERTIFICATES\t%s\n' \
        "${AUTH_STATUS:-UNKNOWN}" "${API_STATUS:-UNKNOWN}" "${RBAC_STATUS:-UNKNOWN}" "${METRICS_STATUS:-UNKNOWN}" "${GITOPS_STATUS:-UNKNOWN}" "${CERT_STATUS:-UNKNOWN}"
    printf 'COVERAGE\tpods=%s\tworkloads=%s\tevents=%s\tservices=%s\tstorage=%s\tgitops=%s\tcertificates=%s\n' \
        "$pods_state" "$(cache_status workloads)" "$(cache_status events)" "$(cache_status services)" "$(cache_status pvcs)" "$(cache_status flux_kustomizations)" "$(cache_status cert_certificates)"
    if ((health_rc==3)); then overall=3
    elif [[ $pods_state != OK && $pods_state != EMPTY_RESULT ]]; then overall=4
    fi
    if [[ -s $RUN_DIR/findings.tsv ]] && has awk; then
        failed=$(awk -F '\t' '$1=="FAIL"||$1=="CRITICAL"{n++} END{print n+0}' "$RUN_DIR/findings.tsv")
        warnings=$(awk -F '\t' '$1=="WARN"{n++} END{print n+0}' "$RUN_DIR/findings.tsv")
        unknown=$(awk -F '\t' '$1=="UNKNOWN"{n++} END{print n+0}' "$RUN_DIR/findings.tsv")
        info=$(awk -F '\t' '$1=="INFO"{n++} END{print n+0}' "$RUN_DIR/findings.tsv")
        total=$((failed+warnings))
        printf 'FINDINGS\tFAIL=%s\tWARN=%s\tUNKNOWN=%s\tINFO=%s (full detail: --health)\n' "$failed" "$warnings" "$unknown" "$info"
        printf 'SEVERITY\tCATEGORY\tRESOURCE\tISSUE\tEVIDENCE\tNEXT CHECK\n'
        { awk -F '\t' '$1=="FAIL"||$1=="CRITICAL"{print}' "$RUN_DIR/findings.tsv"
          awk -F '\t' '$1=="WARN"{print}' "$RUN_DIR/findings.tsv"; } | head -30 \
        | while IFS=$'\t' read -r severity category resource issue evidence; do
            printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$severity" "$category" "$resource" "$issue" "${evidence:-OBSERVED API status}" "$(next_check_hint "$category")"
        done
        ((total>30)) && printf 'TRUNCATED\t%s more FAIL/WARN findings; complete list in --health or dashboard 6\n' "$((total-30))"
        ((unknown>0)) && printf 'UNKNOWN\t%s findings are data gaps, not healthy states; inspect --health coverage table\n' "$unknown"
    else
        printf 'FINDINGS\tUNAVAILABLE (findings engine requires awk; jq gaps are listed by --health)\n'
    fi
    if ((QUIET_FLAG==0)); then
        if ! has jq; then
            printf 'TOP PRESSURE\tUNAVAILABLE (jq required for usage ranking)\n'
        elif [[ $pods_state != OK && $pods_state != EMPTY_RESULT ]]; then
            printf 'TOP PRESSURE\tUNAVAILABLE (pod inventory %s; never reported as zero)\n' "$pods_state"
        elif [[ ${METRICS_STATUS:-UNKNOWN} != OK && ${METRICS_STATUS:-UNKNOWN} != EMPTY_RESULT ]]; then
            printf 'TOP PRESSURE\tUNAVAILABLE (metrics %s; never reported as zero)\n' "${METRICS_STATUS:-UNKNOWN}"
        else
            printf 'TOP PRESSURE (active pods; usage vs request is not node pressure)\n'
            resource_rows_json | jq -r "$JQ_QUANTITIES"'
              map(select(.active and (.cpu|type)=="number"))|sort_by(-.cpu)|.[:3][]|[.pod,"CPU "+(.cpu|cpu_fmt),"vs request "+pct(.cpu;.cpu_request),.node]|@tsv' || :
            resource_rows_json | jq -r "$JQ_QUANTITIES"'
              map(select(.active and (.memory|type)=="number"))|sort_by(-.memory)|.[:3][]|[.pod,"MEM "+(.memory|mem_fmt),"vs request "+pct(.memory;.memory_request),.node]|@tsv' || :
        fi
    fi
    if ((QUIET_FLAG==0)) && has awk && [[ -s $RUN_DIR/findings.tsv ]]; then
        printf 'SUGGESTED NEXT CHECKS (derived from observed findings; not a diagnosis)\n'
        awk -F '\t' '$1=="FAIL"||$1=="CRITICAL"||$1=="WARN"{print $2}' "$RUN_DIR/findings.tsv" | awk '!seen[$0]++' \
        | while IFS= read -r category; do
            printf '%s\t%s\n' "$category" "$(next_check_hint "$category")"
        done
    fi
    printf 'NEXT\tfull audit --health | per-workload --triage-workload NAME | evidence bundle --evidence ID\n'
    printf 'TRIAGE EXIT\t0=no FAIL 1=observed FAIL 3=auth/API failure 4=required pod inventory unavailable\n'
    ((failed>0 && overall==0)) && overall=1
    return "$overall"
}

triage_workload_report() {
    local query=${1:-} kind='' name='' overall=0 health_rc=0
    local workloads_state pods_state full pod_rows pods_json='[]' wl_failed=0
    local severity category resource issue evidence mre part
    local -a matches=() pod_names=()
    [[ -n $query ]] || { printf 'WORKLOAD TRIAGE\tUNAVAILABLE: no workload specified\n'; return 2; }
    if [[ $query == */* ]]; then
        kind=${query%%/*} name=${query##*/}
        [[ $kind =~ ^[A-Za-z][A-Za-z0-9.-]*$ ]] || { printf 'WORKLOAD TRIAGE\tinvalid kind in query\n'; return 2; }
    else name=$query; fi
    # The health audit primes the shared caches and the findings engine once.
    health_report >/dev/null || health_rc=$?
    workloads_state=$(cache_status workloads); pods_state=$(cache_status pods)
    printf 'WORKLOAD TRIAGE | %s\nCONTEXT\t%s\nNAMESPACE\t%s\nTIME\t%s\n' "$query" "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE" "$(timestamp)"
    if [[ $workloads_state != OK && $workloads_state != EMPTY_RESULT ]]; then
        printf 'WORKLOAD INVENTORY\t%s\tworkload correlation NOT VERIFIED\n' "$workloads_state"
        return 4
    fi
    if [[ $pods_state != OK && $pods_state != EMPTY_RESULT ]]; then
        printf 'POD INVENTORY\t%s\tpod correlation NOT VERIFIED\n' "$pods_state"
        overall=4
    fi
    if ! has jq; then
        printf 'ANALYSIS\tCOMMAND_MISSING jq\tworkload correlation requires jq; inventory-only conclusion\n'
        [[ $overall == 0 ]] && overall=4
        return "$overall"
    fi
    if [[ -n $kind ]]; then
        mapfile -t matches < <(jq -r --arg k "$kind" --arg n "$name" '.items[]?|select(.kind==$k and .metadata.name==$n)|.kind+"/"+.metadata.name' "$(json_cache_path workloads)")
    else
        mapfile -t matches < <(jq -r --arg n "$name" '.items[]?|select(.metadata.name==$n)|.kind+"/"+.metadata.name' "$(json_cache_path workloads)")
    fi
    ((${#matches[@]})) || {
        printf 'WORKLOAD\tNOT FOUND\t%s\nNo fuzzy guessing: list candidates with --resources or dashboard 4.\n' "$query"
        return 2
    }
    ((${#matches[@]}==1)) || printf 'NOTE\t%s objects match this name; every match is shown\n' "${#matches[@]}"
    for full in "${matches[@]}"; do
        kind=${full%%/*} name=${full##*/}
        printf '\nWORKLOAD\t%s\n' "$full"
        jq -r --arg k "$kind" --arg n "$name" '
          .items[]?|select(.kind==$k and .metadata.name==$n)|. as $w|
          (["DESIRED",(if $w.kind=="DaemonSet" then ($w.status.desiredNumberScheduled // "UNKNOWN_DESIRED") else ($w.spec.replicas // 1) end|tostring),
            "READY",(if $w.kind=="DaemonSet" then ($w.status.numberReady // 0) else ($w.status.readyReplicas // 0) end|tostring),
            "AVAILABLE",($w.status.availableReplicas // 0|tostring)]|@tsv),
          (["GENERATION",($w.metadata.generation // 0|tostring),"OBSERVED",($w.status.observedGeneration // 0|tostring),
            "SUSPENDED",($w.spec.suspend // false|tostring)]|@tsv),
          ($w.spec.template.spec.containers[]?|["IMAGE",.image]|@tsv)' "$(json_cache_path workloads)"
        printf 'PODS (owner resolved through ReplicaSet where applicable)\nPOD\tPHASE\tREADY\tRESTARTS\tAGE\tNODE\tCPU\tMEMORY\n'
        pod_rows=$(resource_rows_json | jq -r --arg full "$full" "$JQ_QUANTITIES"'
          map(select(.owner==$full))|sort_by(.pod)[]|[.pod,.phase,.ready,(.restarts|tostring),.age,.node,(.cpu|cpu_fmt),(.memory|mem_fmt)]|@tsv' 2>/dev/null) || :
        if [[ -n $pod_rows ]]; then
            printf '%s\n' "$pod_rows"
            mapfile -t pod_names < <(printf '%s\n' "$pod_rows" | awk -F '\t' 'NF>0{print $1}')
        else
            printf 'NONE\tcontroller has not created observed pods for this owner; inventory-only conclusion\n'
            pod_names=()
        fi
        if ((${#pod_names[@]})); then
            pods_json=$(printf '%s\n' "${pod_names[@]}" | jq -R . | jq -s .)
        else pods_json='[]'; fi
        printf 'RELATED WARNING EVENTS (events cache: %s; retained window only)\nTIMESTAMP\tREASON\tOBJECT\tMESSAGE\tCOUNT\n' "$(cache_status events)"
        jq -r --arg k "$kind" --arg n "$name" --argjson pods "$pods_json" '
          .items[]?|select(.type=="Warning" and ((.involvedObject.kind==$k and .involvedObject.name==$n) or (.involvedObject.kind=="Pod" and (.involvedObject.name as $on | ($pods|index($on))))))|
          [(.eventTime // .lastTimestamp // .metadata.creationTimestamp // "UNKNOWN"),(.reason // "Warning"),((.involvedObject.kind // "Object")+"/"+(.involvedObject.name // "UNKNOWN")),.message // "",(.series.count // .count // 1|tostring)]|@tsv' "$(json_cache_path events)"
        printf 'SERVICE RELATIONSHIPS (services cache: %s)\nSERVICE\tREADY ENDPOINTS\tSTATUS\tSOURCE\n' "$(cache_status services)"
        network_rows_json | jq -r --argjson pods "$pods_json" '
          .[]|select(.pods and ([.pods[]|. as $p|select($pods|index($p))]|length)>0)|[.name,(.ready_endpoints|tostring),.status,.endpoint_source]|@tsv' 2>/dev/null || :
        printf 'STORAGE (PVCs referenced by these pods; pvcs cache: %s)\nPVC\tPV\tPHASE\tCAPACITY\tCLASS\n' "$(cache_status pvcs)"
        jq -r --argjson pods "$pods_json" --slurpfile vx "$(json_cache_path pvcs)" '
          [.items[]?|. as $pod|select($pods|index($pod.metadata.name))|.spec.volumes[]?|select(.persistentVolumeClaim)|.persistentVolumeClaim.claimName]|unique|.[] as $c|
          ($vx[0].items[]?|select(.metadata.name==$c)) as $pvc|
          [$c,($pvc.spec.volumeName // "-"),($pvc.status.phase // "UNKNOWN"),($pvc.status.capacity.storage // "UNKNOWN"),($pvc.spec.storageClassName // "-")]|@tsv' "$(json_cache_path pods)" 2>/dev/null || :
        printf 'GITOPS CORRELATION (exact name match only; Flux cache: %s)\nOBJECT\tREADY\tREASON\tREVISION\n' "$(cache_status flux_kustomizations)"
        for key in flux_kustomizations flux_helmreleases; do
            jq -r --arg n "$name" '
              .items[]?|select(.metadata.name==$n)|. as $o|
              ([.status.conditions[]?|select(.type=="Ready")][0] // {}) as $r|
              [($o.kind // "Object")+"/"+$o.metadata.name,($r.status // "UNKNOWN"),($r.reason // "-"),($o.status.artifact.revision // $o.status.lastAppliedRevision // "-")]|@tsv' "$(json_cache_path "$key")" 2>/dev/null || :
        done
        if [[ -s $CACHE_DIR/helm.txt ]]; then
            jq -r --arg n "$name" '.[]?|select(.name==$n)|["HELM/"+.name,(.status // "UNKNOWN"),(.chart // "-")]|@tsv' "$CACHE_DIR/helm.txt" 2>/dev/null || :
        fi
        printf 'FINDINGS FOR THIS WORKLOAD (from the shared findings engine)\nSEVERITY\tCATEGORY\tRESOURCE\tISSUE\tEVIDENCE\tNEXT CHECK\n'
        if [[ -s $RUN_DIR/findings.tsv ]] && has awk; then
            mre=${matches[0]}
            for part in "${matches[@]:1}" "${pod_names[@]}"; do mre+="|$part"; done
            awk -F '\t' -v re="^($mre)$" '$3 ~ re {print}' "$RUN_DIR/findings.tsv" \
            | while IFS=$'\t' read -r severity category resource issue evidence; do
                printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$severity" "$category" "$resource" "$issue" "${evidence:-OBSERVED API status}" "$(next_check_hint "$category")"
            done
            wl_failed=$(awk -F '\t' -v re="^($mre)$" '($3 ~ re) && ($1=="FAIL"||$1=="CRITICAL"){n++} END{print n+0}' "$RUN_DIR/findings.tsv")
        else
            printf 'FINDINGS\tUNAVAILABLE (findings engine requires awk)\n'
        fi
        printf 'NEXT\tinspect pods: dashboard 2 | logs: dashboard 13 | evidence bundle: --evidence ID\n'
        ((wl_failed>0 && overall==0)) && overall=1
    done
    if ((health_rc==3)); then overall=3; fi
    printf 'WORKLOAD TRIAGE EXIT\t0=no FAIL 1=observed FAIL 3=auth/API failure 4=inventory unavailable\n'
    return "$overall"
}

capabilities_report() {
    local cmd
    printf 'CAPABILITY REPORT | dynamically determined; menus adapt automatically\nCONTEXT\t%s\nNAMESPACE\t%s\nTIME\t%s\n' \
        "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE" "$(timestamp)"
    printf '\nLOCAL TOOLS\n'
    for cmd in kubectl helm flux jq openssl curl timeout sha256sum column tput base64 awk sed grep sort uniq date git shellcheck inotifywait flock less stat id uname file; do
        printf '%-14s %s\n' "$cmd" "${DEPENDENCIES[$cmd]:-UNKNOWN}"
    done
    printf '\nCLUSTER ACCESS\n'
    printf 'Authentication\t%s\nAPI\t%s\nAPI latency\t%s\nRBAC\t%s\n' \
        "${AUTH_STATUS:-UNKNOWN}" "${API_STATUS:-UNKNOWN}" "${API_LATENCY:-UNKNOWN}" "${RBAC_STATUS:-UNKNOWN}"
    printf 'kubectl client\t%s\nKubernetes server\t%s\n' "$KUBECTL_VERSION" "$SERVER_VERSION"
    printf '\nCLUSTER CAPABILITIES\n'
    printf 'Core resources (pods)\t%s\n' "$(cache_status pods)"
    printf 'Metrics API (usage)\t%s\n' "$METRICS_STATUS"
    printf 'Flux GitOps APIs\t%s\n' "$GITOPS_STATUS"
    if [[ $(cache_status helm) == NOT_COLLECTED && $SCOPE_READY == 1 ]] && declare -F helm_report >/dev/null; then
        helm_report >/dev/null || :
    fi
    printf 'Helm releases\t%s\n' "$(cache_status helm)"
    printf 'cert-manager\t%s\n' "$CERT_STATUS"
    if [[ -n ${SPLUNK_URL:-} && -n ${SPLUNK_TOKEN:-} ]]; then
        printf 'Splunk\tCONFIGURED\tindex=%s sourcetype=%s (token never displayed)\n' "${SPLUNK_INDEX:-default}" "${SPLUNK_SOURCETYPE:-default}"
    else printf 'Splunk\tNOT_CONFIGURED\tset SPLUNK_URL and SPLUNK_TOKEN for live discovery\n'; fi
    printf '\nRBAC READ MATRIX\n'
    if [[ -s $CACHE_DIR/rbac.txt ]]; then cat -- "$CACHE_DIR/rbac.txt"
    else printf 'NOT_PROBED (scope unavailable; see --doctor)\n'; fi
    printf '\nINTERPRETATION\n'
    printf 'NOT INSTALLED / NOT_CONFIGURED / NOT_PROBED are access or installation states, not failures.\n'
    printf 'Unavailable features stay visible in menus with explicit status instead of being hidden.\n'
    printf 'Splunk catalog generation works offline; discovery and validation require configuration.\n'
    return 0
}

doctor_source_hygiene() {
    local failed=0 mode hash
    if [[ ! -e $SOURCE_FILE ]]; then
        printf 'Source file\tFAIL\tmissing: %s\n' "$SOURCE_FILE"
        return 1
    fi
    if [[ -L $SOURCE_FILE ]]; then
        printf 'Source file\tWARN\tsymlink execution path; verify repository provenance\n'
    elif [[ -f $SOURCE_FILE ]]; then
        printf 'Source file\tOK\tregular file\n'
    else
        printf 'Source file\tFAIL\tnot a regular file\n'; failed=1
    fi
    if has stat; then
        mode=$(stat -Lc '%a' -- "$SOURCE_FILE" 2>/dev/null || true)
        if [[ $mode =~ ^[0-7]{3,4}$ ]]; then
            if (((8#$mode & 0022) != 0)); then
                printf 'Source permissions\tFAIL\tmode=%s is group/world writable\n' "$mode"; failed=1
            else
                printf 'Source permissions\tOK\tmode=%s\n' "$mode"
            fi
        else
            printf 'Source permissions\tUNKNOWN\tstat mode unavailable\n'
        fi
    else
        printf 'Source permissions\tUNKNOWN\tstat not installed\n'
    fi
    if has sha256sum; then
        hash=$(sha256sum -- "$SOURCE_FILE" 2>/dev/null | awk '{print $1}')
        if [[ $hash =~ ^[a-fA-F0-9]{64}$ ]]; then printf 'Source SHA256\tOK\t%s\n' "$hash"
        else printf 'Source SHA256\tUNKNOWN\tunable to calculate\n'; fi
    else
        printf 'Source SHA256\tUNAVAILABLE\tsha256sum not installed\n'
    fi
    return "$failed"
}

doctor_kubeconfig_hygiene() {
    local failed=0 entry mode seen=0
    local -a entries=()
    if [[ $KUBECONFIG_MODE != EXPLICIT ]]; then
        printf 'Kubeconfig hygiene\tDEFAULT\tkubectl default resolution; explicit file permissions not inspected\n'
        return 0
    fi
    if [[ -z ${KUBECONFIG:-} ]]; then
        printf 'Kubeconfig hygiene\tFAIL\texplicit mode with empty KUBECONFIG\n'
        return 1
    fi
    IFS=: read -r -a entries <<< "$KUBECONFIG"
    for entry in "${entries[@]}"; do
        [[ -n $entry ]] || { printf 'Kubeconfig entry\tWARN\tempty path component ignored\n'; continue; }
        ((seen+=1))
        if [[ ! -e $entry ]]; then
            printf 'Kubeconfig entry\tFAIL\t%s does not exist\n' "$entry"; failed=1; continue
        fi
        if [[ ! -f $entry || ! -r $entry ]]; then
            printf 'Kubeconfig entry\tFAIL\t%s must be a readable regular file\n' "$entry"; failed=1; continue
        fi
        if has stat; then
            mode=$(stat -Lc '%a' -- "$entry" 2>/dev/null || true)
            if [[ $mode =~ ^[0-7]{3,4}$ ]]; then
                if (((8#$mode & 0022) != 0)); then
                    printf 'Kubeconfig permissions\tFAIL\t%s mode=%s is group/world writable\n' "$entry" "$mode"; failed=1
                elif (((8#$mode & 0004) != 0)); then
                    printf 'Kubeconfig permissions\tWARN\t%s mode=%s is world-readable\n' "$entry" "$mode"
                elif (((8#$mode & 0040) != 0)); then
                    printf 'Kubeconfig permissions\tWARN\t%s mode=%s is group-readable\n' "$entry" "$mode"
                else
                    printf 'Kubeconfig permissions\tOK\t%s mode=%s\n' "$entry" "$mode"
                fi
            else
                printf 'Kubeconfig permissions\tUNKNOWN\t%s stat mode unavailable\n' "$entry"
            fi
        else
            printf 'Kubeconfig permissions\tUNKNOWN\t%s; stat not installed\n' "$entry"
        fi
    done
    ((seen>0)) || { printf 'Kubeconfig hygiene\tFAIL\tno usable explicit path entries\n'; return 1; }
    return "$failed"
}

doctor_report() {
    local failed=0 rc raw contexts=0 cmd core_missing=0 rc_ok=0 rc_bad=0 rc_res=0
    printf 'SENTINEL DOCTOR | diagnoses whether this tool can operate here\nTIME\t%s\nHOST\t%s\nSHELL\t%s\n' \
        "$(timestamp)" "${HOSTNAME:-UNKNOWN}" "$BASH_VERSION"
    printf '\nSHELL AND CORE\n'
    if ((BASH_VERSINFO[0]>4 || (BASH_VERSINFO[0]==4 && BASH_VERSINFO[1]>=4))); then
        printf 'Bash >= 4.4\tOK\t%s\n' "$BASH_VERSION"
    else printf 'Bash >= 4.4\tFAIL\t%s\n' "$BASH_VERSION"; failed=1; fi
    for cmd in mktemp mkdir rm cat awk sed grep sort uniq date; do
        has "$cmd" || { printf 'Core utility %s\tFAIL\tmissing\n' "$cmd"; core_missing=1; }
    done
    ((core_missing)) && failed=1
    ((core_missing)) || printf 'Core utilities\tOK\tmktemp mkdir rm cat awk sed grep sort uniq date present\n'
    printf '\nSOURCE INTEGRITY\n'
    doctor_source_hygiene || failed=1
    printf '\nOPTIONAL TOOLS (impact when missing)\n'
    if [[ ${DEPENDENCIES[jq]:-UNKNOWN} == AVAILABLE ]]; then printf 'jq\tOK\tJSON analysis, structured reports, --json output\n'
    else printf 'jq\tWARN\tstructured analysis and --json output unavailable\n'; fi
    if [[ ${DEPENDENCIES[openssl]:-UNKNOWN} == AVAILABLE ]]; then printf 'openssl\tOK\tcertificate and TLS auditing\n'
    else printf 'openssl\tWARN\tcertificate/TLS auditing unavailable\n'; fi
    if [[ ${DEPENDENCIES[curl]:-UNKNOWN} == AVAILABLE ]]; then printf 'curl\tOK\tSplunk live discovery/validation\n'
    else printf 'curl\tWARN\tSplunk live queries unavailable; offline catalog remains\n'; fi
    if [[ ${DEPENDENCIES[timeout]:-UNKNOWN} == AVAILABLE ]]; then printf 'timeout\tOK\tcommand deadline enforcement\n'
    else printf 'timeout\tWARN\tfallback watchdog deadlines; upgrade recommended\n'; fi
    if [[ ${DEPENDENCIES[sha256sum]:-UNKNOWN} == AVAILABLE ]]; then printf 'sha256sum\tOK\tevidence integrity manifests\n'
    else printf 'sha256sum\tWARN\tevidence integrity manifests unavailable\n'; fi
    if [[ ${DEPENDENCIES[git]:-UNKNOWN} == AVAILABLE ]]; then printf 'git\tOK\tdeveloper publishing workflow\n'
    else printf 'git\tWARN\tdeveloper publishing unavailable\n'; fi
    printf '\nKUBERNETES CLIENT AND CONFIGURATION\n'
    if [[ ${DEPENDENCIES[kubectl]:-UNKNOWN} == AVAILABLE ]]; then
        printf 'kubectl\tOK\t%s\n' "$(command -v kubectl)"
        raw=$(config_query get-contexts -o name 2>/dev/null); rc=$?
        if ((rc==0)); then
            contexts=$(grep -c . <<< "$raw" 2>/dev/null) || contexts=0
            if ((contexts>0)); then printf 'Kubeconfig contexts\tOK\t%s discovered\n' "$contexts"
            else printf 'Kubeconfig contexts\tNOT_CONFIGURED\tno contexts; kubectl config needed for cluster modes\n'; failed=1; fi
        else
            printf 'Kubeconfig contexts\t%s\tkubectl config get-contexts failed\n' "$(classify_error "$rc" "$raw")"
            failed=1
        fi
    else
        printf 'kubectl\tFAIL\tnot installed; every cluster feature is unavailable\n'
        failed=1
    fi
    printf 'KUBECONFIG MODE\t%s (never modified by this tool)\n' "$KUBECONFIG_MODE"
    doctor_kubeconfig_hygiene || failed=1
    printf '\nCLUSTER SCOPE\n'
    if [[ $SCOPE_READY == 1 ]]; then
        printf 'Scope bootstrap\tOK\tcontext=%s namespace=%s\n' "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE"
        printf 'Authentication\t%s\nAPI\t%s\nRBAC\t%s\nMetrics\t%s\nGitOps\t%s\ncert-manager\t%s\n' \
            "$AUTH_STATUS" "$API_STATUS" "$RBAC_STATUS" "$METRICS_STATUS" "$GITOPS_STATUS" "$CERT_STATUS"
    else
        case $DOCTOR_BOOTSTRAP_RC in
            2) printf 'Scope bootstrap\tFAIL\tconfiguration exit 2: context/namespace/kubeconfig\n'; failed=1;;
            3) printf 'Scope bootstrap\tFAIL\tauthentication or API failure (exit 3)\n';;
            *) printf 'Scope bootstrap\tUNKNOWN\texit %s; cluster-dependent checks NOT VERIFIED\n' "$DOCTOR_BOOTSTRAP_RC";;
        esac
    fi
    printf '\nRUNTIME AND TERMINAL\n'
    if [[ -n $RUN_DIR && -d $RUN_DIR && -w $RUN_DIR ]]; then printf 'Private runtime\tOK\t%s\n' "$RUN_DIR"
    else printf 'Private runtime\tFAIL\tmissing or not writable\n'; failed=1; fi
    if ((INTERACTIVE)); then printf 'Terminal\tOK\t%dx%d interactive\n' "$UI_COLS" "$UI_ROWS"
    else printf 'Terminal\tNONINTERACTIVE\tno controlling tty; dashboards require one\n'; fi
    if [[ -n ${SPLUNK_URL:-} && -n ${SPLUNK_TOKEN:-} ]]; then printf 'Splunk configuration\tOK\tURL configured (token never displayed)\n'
    else printf 'Splunk configuration\tNOT_CONFIGURED\toptional; offline catalog remains available\n'; fi
    printf '\nREAD-ONLY DISCIPLINE (live self-check of the pure scope guards)\n'
    scope_args_safe get pods -o json >/dev/null 2>&1 || rc_ok=1
    scope_args_safe --token=fixture >/dev/null 2>&1; rc=$?
    [[ $rc == 2 ]] || rc_bad=1
    scope_args_safe --server=https://fixture.invalid >/dev/null 2>&1; rc=$?
    [[ $rc == 2 ]] || rc_bad=1
    allowed_resource ns pods >/dev/null 2>&1 || rc_res=1
    allowed_resource ns arbitrary-fixture >/dev/null 2>&1; rc=$?
    [[ $rc == 2 ]] || rc_res=1
    if ((rc_ok==0 && rc_bad==0 && rc_res==0)); then
        printf 'Scope guards\tOK\tnormal reads allowed; token/server/all-namespaces escape rejected\n'
    else printf 'Scope guards\tFAIL\tguard self-check rejected an expected state\n'; failed=1; fi
    printf '\nPLATFORM\n'
    if dev_is_wsl 2>/dev/null; then printf 'WSL\tDETECTED\tdeveloper workflow usable\n'
    elif [[ $(uname -s 2>/dev/null) == Linux ]]; then printf 'Platform\tLinux native\n'
    else printf 'Platform\t%s\tbash-compatible shell required\n' "$(uname -s 2>/dev/null || printf UNKNOWN)"; fi
    printf '\nDOCTOR SUMMARY\n'
    case ${AUTH_STATUS:-UNKNOWN}:${API_STATUS:-UNKNOWN}:${DOCTOR_BOOTSTRAP_RC} in
        *AUTH_ERROR*|*AUTH_REQUIRED*|*:3) printf 'Result\tFAIL\tauthentication/API failure; fix access before operational use\n'; return 3;;
    esac
    if ((failed)); then printf 'Result\tFAIL\tat least one required capability is broken; details above\n'; return 1; fi
    printf 'Result\tOK\tSentinel can operate; optional gaps are explicitly classified above\n'
    return 0
}

resource_self_tests() {
    has jq || { printf 'SKIP resource arithmetic: jq unavailable\n'; return 0; }
    local result
    result=$(jq -n "$JQ_QUANTITIES"'
      [
       ("250m"|q("cpu"))==250, ("1"|q("cpu"))==1000, ("2.5"|q("cpu"))==2500,
       ("250000000n"|q("cpu"))==250, ("500000u"|q("cpu"))==500,
       ("512Mi"|q("memory"))==536870912, ("2Gi"|q("memory"))==2147483648,
       ("1Ti"|q("memory"))==1099511627776, ("1G"|q("memory"))==1000000000,
       ("1e3"|quantity)==1000, ("broken"|quantity)==null,
       ({spec:{containers:[{resources:{requests:{cpu:"500m"}}}],initContainers:[{resources:{requests:{cpu:"2"}}}],overhead:{cpu:"50m"}}}|effective("requests";"cpu"))==2050,
       ({spec:{containers:[{resources:{requests:{cpu:"1"}}}],initContainers:[{restartPolicy:"Always",resources:{requests:{cpu:"200m"}}},{resources:{requests:{cpu:"2"}}},{restartPolicy:"Always",resources:{requests:{cpu:"300m"}}}],overhead:{cpu:"50m"}}}|effective("requests";"cpu"))==2250,
       ({spec:{containers:[{resources:{requests:{cpu:"1"}}},{resources:{requests:{cpu:"broken"}}}]}}|effective("requests";"cpu"))=="PARSE_ERROR",
       ({spec:{containers:[{}]}}|effective("requests";"cpu"))=="UNSET",
       ({spec:{containers:[{}]}}|effective("limits";"cpu"))=="UNBOUNDED",
       ({spec:{containers:[{}],resources:{requests:{cpu:"1"}}}}|effective("requests";"cpu"))=="UNSUPPORTED_POD_LEVEL"
      ] | if all(.[]; .==true) then "PASS resource quantity/effective-request invariants" else error("resource arithmetic invariant failed: \(.)") end' -r) || return 1
    printf '%s\n' "$result"
}

# Offline report tests run in an isolated subshell. They never contact a cluster,
# change the caller's functions, or leave an application supporting source file.
resource_integration_tests() (
    has jq || { printf 'SKIP resource report fixtures: jq unavailable\n'; exit 0; }
    local test_root rc func errors=0
    test_root=$(mktemp -d "$RUN_DIR/resource-fixtures.XXXXXX") || exit 1
    trap 'rm -rf -- "$test_root"' EXIT
    RUN_DIR=$test_root CACHE_DIR=$test_root/cache
    mkdir -p "$CACHE_DIR" || exit 1
    SENTINEL_NAMESPACE=fixture-ns SENTINEL_CONTEXT=fixture-context
    AUTH_STATUS=AUTHENTICATED API_STATUS=OK API_LATENCY='fixture' RBAC_STATUS=OK
    FORCE_REFRESH=0 RESOURCE_FILTER= RESOURCE_SORT=name
    cache_status() { if [[ -f $CACHE_DIR/$1.status ]]; then cat "$CACHE_DIR/$1.status"; else printf 'NOT_COLLECTED\n'; fi; }
    cache_age() { printf '0\n'; }
    collect_json() {
        local key=$1 projection=$5 fixture="$RUN_DIR/$1.fixture.json"
        printf '%s\n' "$key" >> "$RUN_DIR/calls"
        if [[ ${FIXTURE_DENIED:-} == "$key" ]]; then
            rm -f -- "$CACHE_DIR/$key.json"
            printf 'RBAC_DENIED\n' > "$CACHE_DIR/$key.status"; return 1
        fi
        [[ -s $fixture ]] || printf '{"items":[]}\n' > "$fixture"
        if jq "$projection" "$fixture" > "$CACHE_DIR/$key.json"; then
            printf 'OK\n' > "$CACHE_DIR/$key.status"
        else printf 'PARSE_ERROR\n' > "$CACHE_DIR/$key.status"; return 1; fi
    }
    # Isolate optional modules: the focused fixture suite has no external CLI calls.
    gitops_report() { :; }; helm_report() { :; }; certificates_report() { :; }
    gitops_findings() { :; }; certificates_findings() { :; }
    cat > "$RUN_DIR/pods.fixture.json" <<'JSON'
{"items":[{"kind":"Pod","metadata":{"name":"fixture-pod","uid":"fixture-uid","namespace":"fixture-ns","creationTimestamp":"2026-01-01T00:00:00Z","labels":{"app":"fixture"},"ownerReferences":[{"kind":"ReplicaSet","name":"fixture-rs","controller":true}]},"spec":{"nodeName":"fixture-node","containers":[{"name":"app","image":"fixture/app:latest","env":[{"name":"CONFIG","value":"OMIT_LITERAL_VALUE"},{"name":"FROM_SECRET","valueFrom":{"secretKeyRef":{"name":"settings","key":"keyname"}}}],"command":["OMIT_COMMAND"],"resources":{"requests":{"cpu":"1","memory":"512Mi"},"limits":{"cpu":"2","memory":"1Gi"}},"volumeMounts":[{"name":"config","mountPath":"/etc/config"}]}],"initContainers":[{"name":"sidecar","restartPolicy":"Always","image":"fixture/sidecar:v1","resources":{"requests":{"cpu":"200m","memory":"10Mi"},"limits":{"cpu":"500m","memory":"100Mi"}}}],"volumes":[{"name":"config","secret":{"secretName":"settings"}}],"overhead":{"cpu":"50m","memory":"5Mi"}},"status":{"phase":"Running","qosClass":"Burstable","podIP":"192.0.2.1","conditions":[{"type":"Ready","status":"False"}],"containerStatuses":[{"name":"app","ready":false,"restartCount":8,"state":{"waiting":{"reason":"CrashLoopBackOff","message":"fixture failure"}},"lastState":{"terminated":{"reason":"OOMKilled","exitCode":137,"finishedAt":"2026-01-01T01:00:00Z"}}}],"initContainerStatuses":[{"name":"sidecar","ready":true,"restartCount":0,"state":{"running":{"startedAt":"2026-01-01T00:00:01Z"}}}]}}]}
JSON
    cat > "$RUN_DIR/workloads.fixture.json" <<'JSON'
{"items":[{"kind":"Deployment","metadata":{"name":"fixture","generation":2},"spec":{"replicas":2},"status":{"readyReplicas":0,"availableReplicas":0,"observedGeneration":1}},{"kind":"ReplicaSet","metadata":{"name":"fixture-rs","ownerReferences":[{"kind":"Deployment","name":"fixture","controller":true}]},"spec":{"replicas":2},"status":{"readyReplicas":0}}]}
JSON
    cat > "$RUN_DIR/metrics.fixture.json" <<'JSON'
{"items":[{"metadata":{"name":"fixture-pod"},"timestamp":"2026-01-01T02:00:00Z","window":"30s","containers":[{"name":"app","usage":{"cpu":"312000000n","memory":"600Mi"}},{"name":"sidecar","usage":{"cpu":"50000000n","memory":"20Mi"}}]}]}
JSON
    cat > "$RUN_DIR/services.fixture.json" <<'JSON'
{"items":[{"metadata":{"name":"fixture"},"spec":{"selector":{"app":"fixture"},"type":"ClusterIP","clusterIP":"192.0.2.10","ports":[{"port":80,"targetPort":8080}]}},{"metadata":{"name":"headless"},"spec":{"selector":{"app":"fixture"},"clusterIP":"None","ports":[{"port":80}]}},{"metadata":{"name":"external"},"spec":{"type":"ExternalName","externalName":"example.invalid"}}]}
JSON
    cat > "$RUN_DIR/endpointslices.fixture.json" <<'JSON'
{"items":[{"metadata":{"name":"fixture-1","labels":{"kubernetes.io/service-name":"fixture"}},"ports":[{"port":8080}],"endpoints":[{"addresses":["192.0.2.1"],"conditions":{"ready":true},"targetRef":{"kind":"Pod","name":"fixture-pod"}}]}]}
JSON
    printf '{"items":[{"metadata":{"name":"headless"}}]}\n' > "$RUN_DIR/endpoints.fixture.json"
    cat > "$RUN_DIR/events.fixture.json" <<'JSON'
{"items":[{"metadata":{"name":"warning","namespace":"fixture-ns","creationTimestamp":"2026-01-01T00:00:00Z"},"lastTimestamp":"2026-01-01T02:00:00Z","type":"Warning","reason":"BackOff","involvedObject":{"kind":"Pod","name":"fixture-pod","namespace":"fixture-ns","uid":"fixture-uid"},"message":"Back-off restarting failed container","count":8}]}
JSON
    cat > "$RUN_DIR/nodes.fixture.json" <<'JSON'
{"items":[{"metadata":{"name":"fixture-node","labels":{"topology.kubernetes.io/zone":"fixture-zone","nodepool":"workers"}},"status":{"capacity":{"cpu":"4","memory":"8Gi"},"allocatable":{"cpu":"3800m","memory":"7Gi"},"conditions":[{"type":"Ready","status":"True"}]}}]}
JSON
    printf '{"items":[{"metadata":{"name":"fixture-node"},"usage":{"cpu":"2","memory":"4Gi"}}]}\n' > "$RUN_DIR/nodemetrics.fixture.json"
    for func in resources_report containers_report workloads_report images_report nodes_report network_report storage_report events_report summary_report; do
        "$func" > "$RUN_DIR/$func.out" 2> "$RUN_DIR/$func.err"; rc=$?
        if ((rc!=0)) || [[ -s $RUN_DIR/$func.err ]]; then printf 'FAIL report %s rc=%s\n' "$func" "$rc"; cat "$RUN_DIR/$func.err"; ((errors+=1)); fi
    done
    inspector_report fixture-pod > "$RUN_DIR/inspector.out" 2> "$RUN_DIR/inspector.err"; rc=$?
    if ((rc!=0)) || [[ -s $RUN_DIR/inspector.err ]]; then printf 'FAIL inspector\n'; ((errors+=1)); fi
    health_report > "$RUN_DIR/health.out" 2> "$RUN_DIR/health.err"; rc=$?
    if ((rc!=1)) || [[ -s $RUN_DIR/health.err ]]; then printf 'FAIL health operational exit code\n'; ((errors+=1)); fi
    jq -e '.items[0].spec.containers[0].env[0].value==null and .items[0].spec.containers[0].command==null' "$CACHE_DIR/pods.json" >/dev/null || ((errors+=1))
    resource_rows_json | jq -e 'length==1 and .[0].cpu==362 and .[0].cpu_request==1250 and .[0].owner=="Deployment/fixture"' >/dev/null || ((errors+=1))
    grep -q 'fixture/app:latest' "$RUN_DIR/images_report.out" || ((errors+=1))
    network_rows_json | jq -e 'length==3 and .[0].ready_endpoints==1 and .[1].status=="INFO_HEADLESS_NO_READY_ENDPOINTS"' >/dev/null || ((errors+=1))
    resource_case() {
        local name=$1 input=$2 expected=$3 actual=$4 result=PASS
        if [[ $expected != "$actual" ]]; then result=FAIL; ((errors+=1)); fi
        printf '%s\t%s\tINPUT %s\tEXPECTED %s\tACTUAL %s\n' "$result" "$name" "$input" "$expected" "$actual"
    }
    cp "$CACHE_DIR/pods.json" "$RUN_DIR/saved-pods.json"
    cp "$CACHE_DIR/metrics.json" "$RUN_DIR/saved-metrics.json"
    jq '.items[0].status.conditions=[] | .items[0].status.containerStatuses=[]' "$RUN_DIR/saved-pods.json" > "$CACHE_DIR/pods.json"
    : > "$RUN_DIR/findings.tsv"; health_pod_findings
    resource_case POD_READY_ABSENT 'Running pod with no Ready condition' UNKNOWN "$(awk -F '\t' '$4=="Pod Ready condition is absent" {print $1}' "$RUN_DIR/findings.tsv")"
    jq '.items[0].containers |= map(select(.name=="sidecar"))' "$RUN_DIR/saved-metrics.json" > "$CACHE_DIR/metrics.json"
    resource_case METRIC_COVERAGE 'Running two-container pod; only sidecar has metrics; app status absent' INCOMPLETE "$(resource_rows_json | jq -r '.[0].cpu')"
    jq '.items[0].containers += [.items[0].containers[0]]' "$RUN_DIR/saved-metrics.json" > "$CACHE_DIR/metrics.json"
    resource_case DUPLICATE_METRICS 'duplicate metrics container names' PARSE_ERROR "$(resource_rows_json | jq -r '.[0].cpu')"
    jq '.items[0].containers[0].usage.cpu="not-a-quantity"' "$RUN_DIR/saved-metrics.json" > "$CACHE_DIR/metrics.json"
    resource_case MALFORMED_METRIC 'CPU not-a-quantity' PARSE_ERROR "$(resource_rows_json | jq -r '.[0].cpu')"
    resource_case NEGATIVE_RESOURCE 'CPU -500m' PARSE_ERROR "$(jq -nr "$JQ_QUANTITIES"'"-500m" | q_state("cpu")')"
    cp "$RUN_DIR/saved-pods.json" "$CACHE_DIR/pods.json"
    cp "$RUN_DIR/saved-metrics.json" "$CACHE_DIR/metrics.json"
    jq '.items[0].endpoints += [(.items[0].endpoints[0]|.addresses=["2001:db8::1"])]' "$CACHE_DIR/endpointslices.json" > "$RUN_DIR/dual-stack.json"
    cp "$RUN_DIR/dual-stack.json" "$CACHE_DIR/endpointslices.json"
    resource_case DUAL_STACK_SERVICE 'one backend pod with IPv4 and IPv6 addresses' '2 addresses;0 missing pods' "$(network_rows_json | jq -r '.[0]|"\(.ready_endpoints) addresses;\(.selector_ready_missing|length) missing pods"')"
    cp "$RUN_DIR/nodes.fixture.json" "$RUN_DIR/saved-nodes.json"
    jq 'del(.items[0].metadata.labels) | .items[0].status.capacity.cpu="broken" | .items[0].status.allocatable.memory=null | .items[0].status.conditions=[]' "$RUN_DIR/saved-nodes.json" > "$RUN_DIR/nodes.fixture.json"
    nodes_report > "$RUN_DIR/node-edge.out" 2> "$RUN_DIR/node-edge.err"
    resource_case NODE_LABELS_ABSENT 'node labels absent' 0 "$(wc -c < "$RUN_DIR/node-edge.err" | tr -d ' ')"
    resource_case NODE_CAPACITY_PARSE 'node CPU capacity broken; memory allocatable absent; Ready absent' 'PARSE_ERROR;UNAVAILABLE;Ready=UNKNOWN' "$(awk -F '\t' '$1=="fixture-node" {print $4";"$12";"$19}' "$RUN_DIR/node-edge.out")"
    cp "$RUN_DIR/saved-nodes.json" "$RUN_DIR/nodes.fixture.json"
    cp "$RUN_DIR/workloads.fixture.json" "$RUN_DIR/saved-workloads.json"
    jq '.items += [{kind:"DaemonSet",metadata:{name:"fixture-ds"},spec:{},status:{}}]' "$RUN_DIR/saved-workloads.json" > "$RUN_DIR/workloads.fixture.json"
    workloads_report > "$RUN_DIR/workload-edge.out"
    resource_case DAEMONSET_DESIRED_ABSENT 'DaemonSet status not populated yet' UNKNOWN_DESIRED "$(awk -F '\t' '$2=="fixture-ds" {print $7}' "$RUN_DIR/workload-edge.out")"
    cp "$RUN_DIR/saved-workloads.json" "$RUN_DIR/workloads.fixture.json"
    FIXTURE_DENIED=metrics
    collect_metrics
    resource_rows_json | jq -e '.[0].cpu=="N/A" and .[0].memory=="N/A"' >/dev/null || ((errors+=1))
    FIXTURE_DENIED=pods
    summary_report > "$RUN_DIR/denied.out" 2> "$RUN_DIR/denied.err"
    grep -q 'RESOURCE TOTALS.*RBAC_DENIED' "$RUN_DIR/denied.out" || ((errors+=1))
    FIXTURE_DENIED=
    collect_pods
    jq '.items[0] as $p | {items:[range(0;501) as $i | $p | .metadata.name=("fixture-pod-"+($i|tostring))]}' "$CACHE_DIR/pods.json" > "$RUN_DIR/pods.fixture.json"
    : > "$RUN_DIR/calls"
    resources_report > "$RUN_DIR/large.out" 2> "$RUN_DIR/large.err"
    if [[ $(wc -l < "$RUN_DIR/calls") != 3 || -s $RUN_DIR/large.err ]]; then printf 'FAIL bulk API collection\n'; ((errors+=1)); fi
    resource_rows_json | jq -e 'length==501' >/dev/null || ((errors+=1))
    printf '{"items":[]}\n' > "$RUN_DIR/pods.fixture.json"
    collect_pods
    resource_rows_json | jq -e 'length==0' >/dev/null || ((errors+=1))
    if ((errors)); then printf 'FAIL resource fixtures: %s failures\n' "$errors"; exit 1; fi
    printf 'PASS all resource report, redaction projection, health, denied, empty, and 501-pod fixtures\n'
)

# Offline triage/capability/doctor fixtures exercise the new orchestration layers
# over the same stubbed-collector pattern used by the resource fixtures.
triage_integration_tests() (
    has jq || { printf 'SKIP triage fixtures: jq unavailable\n'; exit 0; }
    local test_root hygiene_fixture='' rc errors=0
    test_root=$(mktemp -d "$RUN_DIR/triage-fixtures.XXXXXX") || exit 1
    trap 'rm -rf -- "$test_root"; [[ -z $hygiene_fixture ]] || rm -f -- "$hygiene_fixture"' EXIT
    RUN_DIR=$test_root CACHE_DIR=$test_root/cache
    mkdir -p -- "$CACHE_DIR" || exit 1
    SENTINEL_NAMESPACE=fixture-ns SENTINEL_CONTEXT=fixture-context
    AUTH_STATUS=AUTHENTICATED API_STATUS=OK API_LATENCY=fixture RBAC_STATUS=OK
    METRICS_STATUS=OK GITOPS_STATUS=NOT_INSTALLED CERT_STATUS=TLS_SECRETS
    KUBECTL_VERSION=fixture SERVER_VERSION=fixture SCOPE_READY=1 FORCE_REFRESH=0
    QUIET_FLAG=0 JSON_FLAG=0 DOCTOR_BOOTSTRAP_RC=0
    DEPENDENCIES[kubectl]=AVAILABLE DEPENDENCIES[jq]=AVAILABLE DEPENDENCIES[openssl]=AVAILABLE
    DEPENDENCIES[awk]=AVAILABLE DEPENDENCIES[timeout]=AVAILABLE DEPENDENCIES[sha256sum]=AVAILABLE
    DEPENDENCIES[git]=AVAILABLE DEPENDENCIES[curl]='NOT INSTALLED' DEPENDENCIES[helm]='NOT INSTALLED'
    cache_status() { if [[ -f $CACHE_DIR/$1.status ]]; then cat -- "$CACHE_DIR/$1.status"; else printf 'NOT_COLLECTED\n'; fi; }
    cache_age() { printf '0\n'; }
    collect_json() {
        local key=$1 projection=$5 fixture="$RUN_DIR/$1.fixture.json"
        printf '%s\n' "$key" >> "$RUN_DIR/calls"
        if [[ ${FIXTURE_DENIED:-} == "$key" ]]; then
            rm -f -- "$CACHE_DIR/$key.json"
            printf 'RBAC_DENIED\n' > "$CACHE_DIR/$key.status"; return 1
        fi
        [[ -s $fixture ]] || printf '{"items":[]}\n' > "$fixture"
        if jq "$projection" "$fixture" > "$CACHE_DIR/$key.json"; then
            printf 'OK\n' > "$CACHE_DIR/$key.status"
        else printf 'PARSE_ERROR\n' > "$CACHE_DIR/$key.status"; return 1; fi
    }
    config_query() { printf 'fixture-context\nother-context\n'; }
    gitops_report() { :; }; helm_report() { :; }; certificates_report() { :; }
    gitops_findings() { :; }; certificates_findings() { :; }
    cat > "$RUN_DIR/pods.fixture.json" <<'JSON'
{"items":[{"kind":"Pod","metadata":{"name":"fixture-pod","uid":"fixture-uid","namespace":"fixture-ns","creationTimestamp":"2026-01-01T00:00:00Z","labels":{"app":"fixture"},"ownerReferences":[{"kind":"ReplicaSet","name":"fixture-rs","controller":true}]},"spec":{"nodeName":"fixture-node","containers":[{"name":"app","image":"fixture/app:latest","env":[{"name":"CONFIG","value":"OMIT_LITERAL_VALUE"},{"name":"FROM_SECRET","valueFrom":{"secretKeyRef":{"name":"settings","key":"keyname"}}}],"command":["OMIT_COMMAND"],"resources":{"requests":{"cpu":"1","memory":"512Mi"},"limits":{"cpu":"2","memory":"1Gi"}},"volumeMounts":[{"name":"config","mountPath":"/etc/config"}]}],"initContainers":[{"name":"sidecar","restartPolicy":"Always","image":"fixture/sidecar:v1","resources":{"requests":{"cpu":"200m","memory":"10Mi"},"limits":{"cpu":"500m","memory":"100Mi"}}}],"volumes":[{"name":"config","secret":{"secretName":"settings"}}],"overhead":{"cpu":"50m","memory":"5Mi"}},"status":{"phase":"Running","qosClass":"Burstable","podIP":"192.0.2.1","conditions":[{"type":"Ready","status":"False"}],"containerStatuses":[{"name":"app","ready":false,"restartCount":8,"state":{"waiting":{"reason":"CrashLoopBackOff","message":"fixture failure"}},"lastState":{"terminated":{"reason":"OOMKilled","exitCode":137,"finishedAt":"2026-01-01T01:00:00Z"}}}],"initContainerStatuses":[{"name":"sidecar","ready":true,"restartCount":0,"state":{"running":{"startedAt":"2026-01-01T00:00:01Z"}}}]}}]}
JSON
    cat > "$RUN_DIR/workloads.fixture.json" <<'JSON'
{"items":[{"kind":"Deployment","metadata":{"name":"fixture","generation":2},"spec":{"replicas":2},"status":{"readyReplicas":0,"availableReplicas":0,"observedGeneration":1}},{"kind":"ReplicaSet","metadata":{"name":"fixture-rs","ownerReferences":[{"kind":"Deployment","name":"fixture","controller":true}]},"spec":{"replicas":2},"status":{"readyReplicas":0}}]}
JSON
    cat > "$RUN_DIR/metrics.fixture.json" <<'JSON'
{"items":[{"metadata":{"name":"fixture-pod"},"timestamp":"2026-01-01T02:00:00Z","window":"30s","containers":[{"name":"app","usage":{"cpu":"312000000n","memory":"600Mi"}},{"name":"sidecar","usage":{"cpu":"50000000n","memory":"20Mi"}}]}]}
JSON
    cat > "$RUN_DIR/services.fixture.json" <<'JSON'
{"items":[{"metadata":{"name":"fixture"},"spec":{"selector":{"app":"fixture"},"type":"ClusterIP","clusterIP":"192.0.2.10","ports":[{"port":80,"targetPort":8080}]}},{"metadata":{"name":"headless"},"spec":{"selector":{"app":"fixture"},"clusterIP":"None","ports":[{"port":80}]}},{"metadata":{"name":"external"},"spec":{"type":"ExternalName","externalName":"example.invalid"}}]}
JSON
    cat > "$RUN_DIR/endpointslices.fixture.json" <<'JSON'
{"items":[{"metadata":{"name":"fixture-1","labels":{"kubernetes.io/service-name":"fixture"}},"ports":[{"port":8080}],"endpoints":[{"addresses":["192.0.2.1"],"conditions":{"ready":true},"targetRef":{"kind":"Pod","name":"fixture-pod"}}]}]}
JSON
    printf '{"items":[{"metadata":{"name":"headless"}}]}\n' > "$RUN_DIR/endpoints.fixture.json"
    cat > "$RUN_DIR/events.fixture.json" <<'JSON'
{"items":[{"metadata":{"name":"warning","namespace":"fixture-ns","creationTimestamp":"2026-01-01T00:00:00Z"},"lastTimestamp":"2026-01-01T02:00:00Z","type":"Warning","reason":"BackOff","involvedObject":{"kind":"Pod","name":"fixture-pod","namespace":"fixture-ns","uid":"fixture-uid"},"message":"Back-off restarting failed container","count":8}]}
JSON
    cat > "$RUN_DIR/nodes.fixture.json" <<'JSON'
{"items":[{"metadata":{"name":"fixture-node","labels":{"topology.kubernetes.io/zone":"fixture-zone","nodepool":"workers"}},"status":{"capacity":{"cpu":"4","memory":"8Gi"},"allocatable":{"cpu":"3800m","memory":"7Gi"},"conditions":[{"type":"Ready","status":"True"}]}}]}
JSON
    printf '{"items":[{"metadata":{"name":"fixture-node"},"usage":{"cpu":"2","memory":"4Gi"}}]}\n' > "$RUN_DIR/nodemetrics.fixture.json"
    printf 'pods\tlist\tOK\ndeployments\tlist\tOK\n' > "$CACHE_DIR/rbac.txt"
    printf '[]\n' > "$CACHE_DIR/helm.txt"; printf 'OK\n' > "$CACHE_DIR/helm.status"
    # Namespace triage: FAIL findings expected (CrashLoop, unready, 0/2 deployment).
    triage_report > "$test_root/triage.out" 2> "$test_root/triage.err"; rc=$?
    [[ $rc == 1 ]] || { printf 'FAIL triage exit expected 1 observed %s\n' "$rc"; ((errors+=1)); }
    [[ -s $test_root/triage.err ]] && { printf 'FAIL triage stderr\n'; cat "$test_root/triage.err"; ((errors+=1)); }
    grep -q 'KUBERNETES TRIAGE' "$test_root/triage.out" || { printf 'FAIL triage header\n'; ((errors+=1)); }
    grep -q 'CrashLoopBackOff' "$test_root/triage.out" || { printf 'FAIL triage finding detail\n'; ((errors+=1)); }
    grep -q 'NEXT CHECK' "$test_root/triage.out" || { printf 'FAIL triage next-check guidance\n'; ((errors+=1)); }
    grep -q 'TOP PRESSURE' "$test_root/triage.out" || { printf 'FAIL triage top pressure\n'; ((errors+=1)); }
    grep -q 'SUGGESTED NEXT CHECKS' "$test_root/triage.out" || { printf 'FAIL triage next-check section\n'; ((errors+=1)); }
    grep -q $'fixture-pod\tCPU 362m' "$test_root/triage.out" || { printf 'FAIL triage top-pressure ranking row\n'; ((errors+=1)); }
    # Required pod inventory unavailable -> exit 4, explicit state, never zero.
    FIXTURE_DENIED=pods
    triage_report > "$test_root/triage4.out" 2> /dev/null; rc=$?
    [[ $rc == 4 ]] || { printf 'FAIL triage unavailable exit expected 4 observed %s\n' "$rc"; ((errors+=1)); }
    grep -q $'COVERAGE\tpods=RBAC_DENIED' "$test_root/triage4.out" || { printf 'FAIL triage unavailable coverage state\n'; ((errors+=1)); }
    FIXTURE_DENIED=
    # Authentication failure -> exit 3.
    AUTH_STATUS=AUTH_ERROR API_STATUS=AUTH_ERROR
    triage_report > "$test_root/triage3.out" 2> /dev/null; rc=$?
    [[ $rc == 3 ]] || { printf 'FAIL triage auth exit expected 3 observed %s\n' "$rc"; ((errors+=1)); }
    AUTH_STATUS=AUTHENTICATED API_STATUS=OK
    # Workload triage: correlation across pods, events, services, findings.
    triage_workload_report fixture > "$test_root/wl.out" 2> "$test_root/wl.err"; rc=$?
    [[ $rc == 1 ]] || { printf 'FAIL workload triage exit expected 1 observed %s\n' "$rc"; ((errors+=1)); }
    [[ -s $test_root/wl.err ]] && { printf 'FAIL workload triage stderr\n'; cat "$test_root/wl.err"; ((errors+=1)); }
    grep -q 'Deployment/fixture' "$test_root/wl.out" || { printf 'FAIL workload match\n'; ((errors+=1)); }
    grep -q 'fixture-pod' "$test_root/wl.out" || { printf 'FAIL workload pod rows\n'; ((errors+=1)); }
    grep -q 'BackOff' "$test_root/wl.out" || { printf 'FAIL workload related events\n'; ((errors+=1)); }
    grep -A3 'SERVICE RELATIONSHIPS' "$test_root/wl.out" | grep -q 'fixture' || { printf 'FAIL workload service mapping\n'; ((errors+=1)); }
    grep -q 'GITOPS CORRELATION' "$test_root/wl.out" || { printf 'FAIL workload gitops section\n'; ((errors+=1)); }
    grep -q 'FINDINGS FOR THIS WORKLOAD' "$test_root/wl.out" || { printf 'FAIL workload findings section\n'; ((errors+=1)); }
    triage_workload_report Deployment/fixture > "$test_root/wlk.out" 2>/dev/null; rc=$?
    [[ $rc == 1 ]] || { printf 'FAIL workload kind query exit expected 1 observed %s\n' "$rc"; ((errors+=1)); }
    grep -q 'Deployment/fixture' "$test_root/wlk.out" || { printf 'FAIL workload kind query match\n'; ((errors+=1)); }
    triage_workload_report nonexistent > "$test_root/wln.out" 2>/dev/null; rc=$?
    [[ $rc == 2 ]] || { printf 'FAIL workload not-found exit expected 2 observed %s\n' "$rc"; ((errors+=1)); }
    grep -q 'NOT FOUND' "$test_root/wln.out" || { printf 'FAIL workload not-found notice\n'; ((errors+=1)); }
    FIXTURE_DENIED=workloads
    triage_workload_report fixture > "$test_root/wl4.out" 2>/dev/null; rc=$?
    [[ $rc == 4 ]] || { printf 'FAIL workload triage unavailable exit expected 4 observed %s\n' "$rc"; ((errors+=1)); }
    FIXTURE_DENIED=
    # Capabilities: explicit states, never invented availability.
    capabilities_report > "$test_root/cap.out" 2> "$test_root/cap.err"; rc=$?
    [[ $rc == 0 ]] || { printf 'FAIL capabilities exit expected 0 observed %s\n' "$rc"; ((errors+=1)); }
    [[ -s $test_root/cap.err ]] && { printf 'FAIL capabilities stderr\n'; cat "$test_root/cap.err"; ((errors+=1)); }
    grep -q 'CAPABILITY REPORT' "$test_root/cap.out" || { printf 'FAIL capabilities header\n'; ((errors+=1)); }
    grep -q 'Metrics API' "$test_root/cap.out" || { printf 'FAIL capabilities metrics line\n'; ((errors+=1)); }
    grep -q 'NOT_INSTALLED' "$test_root/cap.out" || { printf 'FAIL capabilities flux state\n'; ((errors+=1)); }
    grep -q 'NOT_CONFIGURED' "$test_root/cap.out" || { printf 'FAIL capabilities splunk state\n'; ((errors+=1)); }
    grep -q $'pods\tlist\tOK' "$test_root/cap.out" || { printf 'FAIL capabilities rbac matrix\n'; ((errors+=1)); }
    grep -q $'Helm releases\tOK' "$test_root/cap.out" || { printf 'FAIL capabilities helm cache state\n'; ((errors+=1)); }
    # Doctor: healthy environment passes; missing kubectl is an explicit FAIL.
    # Permission checks need a native Linux fixture, independent of a DrvFS
    # checkout's synthetic modes and the caller's real kubeconfig.
    hygiene_fixture=$(mktemp "${SNTL_RUNTIME_DIR:-${HOME}/.devopssentinel/runtime}/devopssentinel-triage-hygiene.XXXXXXXX") || exit 1
    printf '%s\n' 'apiVersion: v1' > "$hygiene_fixture" || exit 1
    chmod 600 "$hygiene_fixture" || exit 1
    SOURCE_FILE=$hygiene_fixture KUBECONFIG=$hygiene_fixture KUBECONFIG_MODE=EXPLICIT
    doctor_report > "$test_root/doc.out" 2> "$test_root/doc.err"; rc=$?
    [[ $rc == 0 ]] || { printf 'FAIL doctor exit expected 0 observed %s\n' "$rc"; ((errors+=1)); }
    [[ -s $test_root/doc.err ]] && { printf 'FAIL doctor stderr\n'; cat "$test_root/doc.err"; ((errors+=1)); }
    grep -q 'SENTINEL DOCTOR' "$test_root/doc.out" || { printf 'FAIL doctor header\n'; ((errors+=1)); }
    grep -q 'Core utilities' "$test_root/doc.out" || { printf 'FAIL doctor core section\n'; ((errors+=1)); }
    grep -q 'Kubeconfig contexts' "$test_root/doc.out" || { printf 'FAIL doctor kubeconfig section\n'; ((errors+=1)); }
    grep -q 'READ-ONLY DISCIPLINE' "$test_root/doc.out" || { printf 'FAIL doctor discipline section\n'; ((errors+=1)); }
    grep -q 'Scope guards' "$test_root/doc.out" || { printf 'FAIL doctor scope guards\n'; ((errors+=1)); }
    grep -q 'PLATFORM' "$test_root/doc.out" || { printf 'FAIL doctor platform section\n'; ((errors+=1)); }
    DEPENDENCIES[kubectl]='NOT INSTALLED'
    doctor_report > "$test_root/docfail.out" 2>/dev/null; rc=$?
    [[ $rc == 1 ]] || { printf 'FAIL doctor no-kubectl exit expected 1 observed %s\n' "$rc"; ((errors+=1)); }
    grep -q 'not installed; every cluster feature is unavailable' "$test_root/docfail.out" || { printf 'FAIL doctor no-kubectl finding\n'; ((errors+=1)); }
    DEPENDENCIES[kubectl]=AVAILABLE
    # Quiet mode keeps findings, drops guidance sections.
    QUIET_FLAG=1
    triage_report > "$test_root/quiet.out" 2>/dev/null || :
    grep -q 'SUGGESTED NEXT CHECKS' "$test_root/quiet.out" && { printf 'FAIL quiet kept guidance section\n'; ((errors+=1)); }
    grep -q '^TOP PRESSURE' "$test_root/quiet.out" && { printf 'FAIL quiet kept top pressure section\n'; ((errors+=1)); }
    grep -q 'CrashLoopBackOff' "$test_root/quiet.out" || { printf 'FAIL quiet dropped findings\n'; ((errors+=1)); }
    QUIET_FLAG=0
    # JSON emitter: valid object, preamble as fields, numeric exit_status.
    printf 'TITLE | fixture-time\nContext: fixture-context | Namespace: fixture-ns\nBODY LINE 1\nBODY LINE 2\n' > "$test_root/json-source.txt"
    if ! json_report_emit "$test_root/json-source.txt" 'Triage' 1 | jq -e '.title=="Triage" and .exit_status==1 and (.lines|index("BODY LINE 1")!=null) and (.lines|index("TITLE | fixture-time")==null)' >/dev/null; then
        printf 'FAIL json emitter structure\n'; ((errors+=1))
    fi
    if ((errors)); then printf 'FAIL triage fixtures: %s failures\n' "$errors"; exit 1; fi
    printf 'PASS triage, workload correlation, capabilities, doctor, quiet and json emitter fixtures\n'
)

# 12 GitOps collectors and deployment validation
gitops_collect() {
    local resource key
    local projection='
      {items:[.items[] | {kind,metadata:{name:.metadata.name,namespace:.metadata.namespace,
        creationTimestamp:.metadata.creationTimestamp,generation:.metadata.generation,
        labels:(.metadata.labels // {})},
        spec:{suspend:(.spec.suspend // false),url:(.spec.url // "" | sub("://[^/@]*@";"://") | sub("[?#].*$";"")),
          ref:.spec.ref,path:.spec.path,interval:.spec.interval,sourceRef:.spec.sourceRef,
          releaseName:.spec.releaseName,targetNamespace:.spec.targetNamespace,
          chart:{spec:{chart:.spec.chart.spec.chart,version:.spec.chart.spec.version,sourceRef:.spec.chart.spec.sourceRef}}},
        status:{observedGeneration:.status.observedGeneration,conditions:(.status.conditions // []),
          artifact:{revision:.status.artifact.revision},lastAppliedRevision:.status.lastAppliedRevision,
          lastAttemptedRevision:.status.lastAttemptedRevision,lastHandledReconcileAt:.status.lastHandledReconcileAt,
          lastAttemptedReleaseAction:.status.lastAttemptedReleaseAction,failures:.status.failures,
          installFailures:.status.installFailures,upgradeFailures:.status.upgradeFailures,
          inventory:{entries:(.status.inventory.entries // [])},history:[.status.history[]? | {name,namespace,version,status,chartName,chartVersion}]}}]}'
    for resource in gitrepositories.source.toolkit.fluxcd.io kustomizations.kustomize.toolkit.fluxcd.io helmrepositories.source.toolkit.fluxcd.io helmreleases.helm.toolkit.fluxcd.io; do
        key="flux_${resource%%.*}"
        collect_json "$key" 15 ns "$resource" "$projection" 'NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,SUSPENDED:.spec.suspend,GENERATION:.metadata.generation,OBSERVED:.status.observedGeneration' || :
    done
}

gitops_report() {
    gitops_collect
    local key file report_rc=0 collection_rc
    printf 'GITOPS / FLUX | context=%s namespace=%s\n' "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE"
    printf 'SOURCE Kubernetes Flux APIs; TTL 15s. Readiness and revision evidence; desired manifests are not diffed.\n'
    for key in flux_gitrepositories flux_kustomizations flux_helmrepositories flux_helmreleases; do
        printf '\n%s | status=%s | cache age=%ss\n' "${key#flux_}" "$(cache_status "$key")" "$(cache_age "$key")"
        file="$(cache_file "$key")"
        if ! has jq || [[ ! -s "$file" ]]; then
            [[ -s "$CACHE_DIR/$key.txt" ]] && cat "$CACHE_DIR/$key.txt"
            continue
        fi
        jq -r '
          def ready: ([.status.conditions[]? | select(.type=="Ready")][0] // {});
          def gen: (.status.observedGeneration // ready.observedGeneration);
          def state:
            if .spec.suspend then "WARN SUSPENDED"
            elif any(.status.conditions[]?; .type=="Stalled" and .status=="True") then "FAIL RECONCILIATION_FAILED"
            elif any(.status.conditions[]?; .type=="Reconciling" and .status=="True") then "WARN RECONCILIATION_PENDING"
            elif ready.status=="False" then (if .kind=="HelmRelease" then "FAIL HELM_FAILURE" else "FAIL RECONCILIATION_FAILED" end)
            elif gen == null then "UNKNOWN OBSERVED_GENERATION"
            elif .metadata.generation!=gen then "WARN GENERATION_DRIFT / RECONCILIATION_PENDING"
            elif ready.status=="True" then "OK NO_DRIFT_EVIDENCE"
            else "UNKNOWN DRIFT_NOT_VERIFIABLE" end;
          "TOTAL \(.items|length) | READY \([.items[]|select(ready.status=="True")]|length) | SUSPENDED \([.items[]|select(.spec.suspend)]|length) | FAILED \([.items[]|select(ready.status=="False")]|length)",
          (.items[] | "\n\(.kind)/\(.metadata.name) [\(state)]",
            "  Ready=\(ready.status // "UNKNOWN") suspend=\(.spec.suspend) generation=\(.metadata.generation // "UNKNOWN") observed=\(gen // "UNKNOWN")",
            "  Created=\(.metadata.creationTimestamp // "UNKNOWN") transition=\(ready.lastTransitionTime // "UNKNOWN") handledReconcile=\(.status.lastHandledReconcileAt // "UNKNOWN")",
            (if .spec.url!="" then "  URL=\(.spec.url) branch/tag=\(.spec.ref.branch // .spec.ref.tag // .spec.ref.semver // .spec.ref.commit // "default")" else empty end),
            (if .spec.sourceRef!=null then "  Source=\(.spec.sourceRef.kind)/\(.spec.sourceRef.name) namespace=\(.spec.sourceRef.namespace // .metadata.namespace) path=\(.spec.path // "-") interval=\(.spec.interval // "-")" else empty end),
            (if .kind=="HelmRelease" then "  Chart=\(.spec.chart.spec.chart // "UNKNOWN") requestedVersion=\(.spec.chart.spec.version // "UNKNOWN") installedVersion=\(.status.history[0].chartVersion // "UNKNOWN") releaseRevision=\(.status.history[0].version // "UNKNOWN")" else empty end),
            "  Artifact=\(.status.artifact.revision // "-") applied=\(.status.lastAppliedRevision // "-") attempted=\(.status.lastAttemptedRevision // "-")",
            "  Reason=\(ready.reason // "UNKNOWN") message=\(ready.message // "-")")' "$file"
        if jq -e 'any(.items[]; .spec.suspend!=true and any(.status.conditions[]?; (.type=="Ready" and .status=="False") or (.type=="Stalled" and .status=="True")))' "$file" >/dev/null 2>&1; then report_rc=1; fi
    done
    gitops_revision_report
    gitops_certificate_collection_rc flux_gitrepositories flux_kustomizations flux_helmrepositories flux_helmreleases; collection_rc=$?
    ((collection_rc>report_rc)) && report_rc="$collection_rc"
    return "$report_rc"
}

gitops_certificate_collection_rc() {
    local key result=0 state
    for key in "$@"; do
        state="$(cache_status "$key")"
        case "$state" in
            AUTH_ERROR|API_TIMEOUT|DNS_ERROR|TLS_ERROR|NETWORK_ERROR) result=3 ;;
            RBAC_DENIED|PARSE_ERROR|COMMAND_MISSING|UNKNOWN) ((result<2)) && result=2 ;;
        esac
    done
    return "$result"
}

gitops_revision_report() {
    local source="$CACHE_DIR/flux_gitrepositories.json" target="$CACHE_DIR/flux_kustomizations.json"
    has jq && [[ -s "$source" && -s "$target" ]] || return 0
    printf '\nSOURCE / APPLIED REVISION COMPARISON (namespace-local observed relationships)\n'
    jq -r --slurpfile src "$source" '
      .items[] | select(.spec.sourceRef.kind=="GitRepository") | . as $k |
      [$src[0].items[] | select(.metadata.name==$k.spec.sourceRef.name and .metadata.namespace==($k.spec.sourceRef.namespace // $k.metadata.namespace))][0] as $s |
      "Kustomization/\(.metadata.name) -> GitRepository/\(.spec.sourceRef.name): " +
      (if $s==null then "DRIFT_NOT_VERIFIABLE (source outside visible scope or unavailable)"
       elif $s.status.artifact.revision==null or .status.lastAppliedRevision==null then "UNKNOWN (revision unavailable)"
       elif $s.status.artifact.revision==.status.lastAppliedRevision then "NO_DRIFT_EVIDENCE (revision matches)"
       else "REVISION_DRIFT / POTENTIAL_DRIFT (source revision differs from applied; reconciliation may be pending)" end)' "$target"
}

helm_list_project() {
    helm_ns list --all --output json | jq '[.[] | {name,namespace,revision,updated,status,chart,app_version}]'
}

helm_status_project() {
    helm_ns status "$1" --output json | jq '{name,namespace,version,info:{status:.info.status,
      first_deployed:.info.first_deployed,last_deployed:.info.last_deployed,deleted:.info.deleted,
      description:.info.description},chart:{name:.chart.metadata.name,version:.chart.metadata.version,appVersion:.chart.metadata.appVersion}}'
}

helm_history_project() {
    helm_ns history "$1" --max 50 --output json | jq '[.[] | {revision,updated,status,chart,app_version,description}]'
}

helm_secret_metadata() {
    kctl_ns get secrets -l owner=helm -o 'go-template={{range .items}}{{.metadata.name}}{{"\t"}}{{.type}}{{"\t"}}{{index .metadata.labels "name"}}{{"\t"}}{{index .metadata.labels "status"}}{{"\t"}}{{index .metadata.labels "version"}}{{"\t"}}{{.metadata.creationTimestamp}}{{"\n"}}{{end}}'
}

helm_report() {
    printf 'HELM | context=%s namespace=%s | TTL 15s\n' "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE"
    if has helm && has jq; then
        collect_text helm 15 helm_list_project || :
        printf 'SOURCE helm list | status=%s | cache age=%ss\n' "$(cache_status helm)" "$(cache_age helm)"
        if [[ -s "$CACHE_DIR/helm.txt" ]]; then
            jq -r '"NAME\tREVISION\tSTATUS\tCHART\tAPP VERSION\tUPDATED",(.[]|[.name,.revision,.status,.chart,.app_version,.updated]|@tsv)' "$CACHE_DIR/helm.txt" 2>/dev/null || cat "$CACHE_DIR/helm.txt"
        fi
    else
        printf 'Helm CLI=%s jq=%s; using release Secret metadata only.\n' "$(has helm && printf AVAILABLE || printf COMMAND_MISSING)" "$(has jq && printf AVAILABLE || printf COMMAND_MISSING)"
        collect_text helm_metadata 15 helm_secret_metadata || :
        printf 'SOURCE Kubernetes Secret metadata | status=%s | cache age=%ss\n' "$(cache_status helm_metadata)" "$(cache_age helm_metadata)"
        printf 'SECRET\tTYPE\tRELEASE\tSTATUS\tREVISION\tCREATED\n'
        [[ -s "$CACHE_DIR/helm_metadata.txt" ]] && cat "$CACHE_DIR/helm_metadata.txt"
    fi
}

helm_detail_report() {
    local release="$1" key="${1//./_}"
    [[ "$release" =~ ^[a-z0-9][a-z0-9.-]*$ ]] || { printf 'INVALID release name\n'; return 2; }
    has helm && has jq || { printf 'UNAVAILABLE: helm and jq are needed for safe detailed projection.\n'; return 0; }
    collect_text "helm_status_$key" 15 helm_status_project "$release" || :
    collect_text "helm_history_$key" 15 helm_history_project "$release" || :
    printf 'HELM STATUS | %s | %s\n' "$release" "$(cache_status "helm_status_$key")"
    [[ -s "$CACHE_DIR/helm_status_$key.txt" ]] && cat "$CACHE_DIR/helm_status_$key.txt"
    printf '\nHELM HISTORY | %s | %s\n' "$release" "$(cache_status "helm_history_$key")"
    [[ -s "$CACHE_DIR/helm_history_$key.txt" ]] && cat "$CACHE_DIR/helm_history_$key.txt"
    printf '\nRelease values, manifests, hooks and notes are excluded.\n'
}

deployment_chain_report() {
    local selected="${1:-}"
    gitops_collect
    collect_pods
    collect_workloads
    printf 'DEPLOYMENT VALIDATION | namespace=%s | SOURCE cached API metadata/status\n' "$SENTINEL_NAMESPACE"
    has jq || { printf 'DEGRADED: jq required for relationship analysis.\n'; return 0; }
    local pods workloads hrs kus
    pods="$(json_cache_path pods)"; workloads="$(json_cache_path workloads)"
    hrs="$(json_cache_path flux_helmreleases)"; kus="$(json_cache_path flux_kustomizations)"
    jq -r --arg selected "$selected" --arg ns "$SENTINEL_NAMESPACE" --slurpfile work "$workloads" --slurpfile hr "$hrs" --slurpfile ks "$kus" '
      def owner: ([.metadata.ownerReferences[]? | select(.controller==true)][0] // .metadata.ownerReferences[0]);
      .items[] | . as $pod | owner as $own |
      ([$work[0].items[] | select(.kind==$own.kind and .metadata.name==$own.name)][0]) as $direct |
      (if $own.kind=="ReplicaSet" and $direct!=null then $direct|owner else $own end) as $top |
      ([$work[0].items[] | select(.kind==$top.kind and .metadata.name==$top.name)][0] // $direct) as $w |
      select($selected=="" or .metadata.name==$selected or $top.name==$selected or (($top.kind // "")+"/"+($top.name // ""))==$selected) |
      ($w.metadata.annotations["meta.helm.sh/release-name"] // $w.metadata.labels["app.kubernetes.io/instance"]) as $release |
      ([$hr[0].items[] | select((.status.history[0].name // .spec.releaseName // (if .spec.targetNamespace!=null then .spec.targetNamespace+"-"+.metadata.name else .metadata.name end))==$release and (.spec.targetNamespace // .metadata.namespace)==$ns)][0]) as $h |
      ($w.metadata.labels["kustomize.toolkit.fluxcd.io/name"] // $h.metadata.labels["kustomize.toolkit.fluxcd.io/name"]) as $kn |
      ($w.metadata.labels["kustomize.toolkit.fluxcd.io/namespace"] // $h.metadata.labels["kustomize.toolkit.fluxcd.io/namespace"] // $ns) as $kns |
      ([$ks[0].items[] | select(.metadata.name==$kn and .metadata.namespace==$kns)][0]) as $k |
      "\nPod/\(.metadata.name) -> \($own.kind // "UNKNOWN")/\($own.name // "UNKNOWN") -> \($top.kind // "UNKNOWN")/\($top.name // "UNKNOWN")",
      "  Workload desired=\($w.spec.replicas // $w.status.desiredNumberScheduled // "UNKNOWN") available=\($w.status.availableReplicas // $w.status.numberAvailable // "UNKNOWN") generation=\($w.metadata.generation // "UNKNOWN") observed=\($w.status.observedGeneration // "UNKNOWN")",
      "  HelmRelease=\($h.metadata.name // "RELATIONSHIP_NOT_VERIFIED") releaseLabel=\($release // "-")",
      "  Kustomization=\($k.metadata.name // "RELATIONSHIP_NOT_VERIFIED") source=\($k.spec.sourceRef.kind // "UNKNOWN")/\($k.spec.sourceRef.name // "UNKNOWN") applied=\($k.status.lastAppliedRevision // "UNKNOWN")",
      (.spec.containers[] as $c |
       ([$pod.status.containerStatuses[]? | select(.name==$c.name)][0]) as $s |
       ([$w.spec.template.spec.containers[]? | select(.name==$c.name)][0].image) as $template |
       "  Container/\($c.name) declared=\($c.image) runtime=\($s.imageID // "UNKNOWN") ready=\($s.ready // false)",
       "    Image evidence: " +
       (if $template!=null and $template!=$c.image then "IMAGE_VARIANCE (workload template and pod differ; rollout may be active)"
        elif ($c.image|contains("@sha256:")) and (($s.imageID // "")|contains("sha256:")) then
          (if ($c.image|split("@")[-1])==($s.imageID|split("@")[-1]|sub("^docker-pullable://";"")|sub("^containerd://";"")) then "NO_DRIFT_EVIDENCE (digest matches)" else "RUNTIME_VARIANCE (digest differs; platform/index digest resolution NOT VERIFIED)" end)
        elif ($c.image|contains("@")) then "DRIFT_NOT_VERIFIABLE (runtime digest unavailable)"
        else "MUTABLE_TAG / DRIFT_NOT_VERIFIABLE (tag-to-digest desired mapping unavailable)" end))' "$pods"
    printf '\nRelationships use owner references and controller/release labels. Labels alone do not prove desired-state equality.\n'
}

gitops_menu() {
    local choice release
    while :; do
        printf '\nGITOPS: Flux APIs, namespace locked, 15s cache; status evidence does not establish manifest drift.\n'
        choose 'GitOps' 'Flux overview and revisions' 'Helm releases' 'Helm release status/history' 'Deployment validation chain' 'Back'
        choice="$REPLY"
        case "$choice" in
            'Flux overview and revisions') capture_report 'GitOps' gitops_report; view_file "$CURRENT_REPORT" 'GitOps' ;;
            'Helm releases') capture_report 'Helm' helm_report; view_file "$CURRENT_REPORT" 'Helm' ;;
            'Helm release status/history')
                has jq && has helm || { printf 'UNAVAILABLE: helm and jq required.\n'; continue; }
                collect_text helm 15 helm_list_project || :
                local -a releases=()
                mapfile -t releases < <(jq -r '.[].name' "$CACHE_DIR/helm.txt" 2>/dev/null)
                ((${#releases[@]})) || { printf 'No selectable releases (%s).\n' "$(cache_status helm)"; continue; }
                choose 'Release' "${releases[@]}" 'Back'; release="$REPLY"
                [[ "$release" == Back || -z "$release" ]] && continue
                capture_report 'Helm release' helm_detail_report "$release"; view_file "$CURRENT_REPORT" 'Helm release' ;;
            'Deployment validation chain') capture_report 'Deployment chain' deployment_chain_report; view_file "$CURRENT_REPORT" 'Deployment chain' ;;
            *) return ;;
        esac
    done
}

gitops_findings() {
    has jq || { findings_add UNKNOWN GITOPS namespace 'jq unavailable; GitOps conditions not analyzed' 'Dependency detection'; return; }
    local key file severity resource issue
    for key in flux_gitrepositories flux_kustomizations flux_helmrepositories flux_helmreleases; do
        file="$(cache_file "$key")"
        if [[ ! -s "$file" ]]; then
            findings_add UNKNOWN GITOPS "${key#flux_}" "$(cache_status "$key")" 'Flux API collector'; continue
        fi
        while IFS=$'\t' read -r severity resource issue; do
            [[ -n "$severity" ]] && findings_add "$severity" GITOPS "$resource" "$issue" 'Observed Flux conditions/generation'
        done < <(jq -r '.items[] | . as $o | ([.status.conditions[]? | select(.type=="Ready")][0] // {}) as $r |
          if .spec.suspend then ["WARN",(.kind+"/"+.metadata.name),"Reconciliation suspended"]
          elif any(.status.conditions[]?;.type=="Reconciling" and .status=="True") then ["WARN",(.kind+"/"+.metadata.name),"RECONCILIATION_PENDING"]
          elif $r.status=="False" or any(.status.conditions[]?;.type=="Stalled" and .status=="True") then ["FAIL",(.kind+"/"+.metadata.name),("Reconciliation failed: "+($r.reason // "Stalled"))]
          elif (.status.observedGeneration // $r.observedGeneration)==null then ["UNKNOWN",(.kind+"/"+.metadata.name),"Observed generation unavailable"]
          elif .metadata.generation!=(.status.observedGeneration // $r.observedGeneration) then ["WARN",(.kind+"/"+.metadata.name),"GENERATION_DRIFT / reconciliation pending"]
          elif $r.status=="True" then ["OK",(.kind+"/"+.metadata.name),"Ready with observed generation; no drift evidence"]
          else ["UNKNOWN",(.kind+"/"+.metadata.name),"Ready condition unavailable"] end | @tsv' "$file")
    done
    if [[ -s "$CACHE_DIR/helm.txt" ]]; then
        while IFS=$'\t' read -r resource issue; do
            [[ -n "$resource" ]] && findings_add FAIL HELM "$resource" "Release status: $issue" 'helm list status'
        done < <(jq -r '.[] | select(.status=="failed") | [.name,.status]|@tsv' "$CACHE_DIR/helm.txt" 2>/dev/null)
    fi
}

# 13 Certificate collectors and bounded TLS auditing
certificate_epoch() {
    local value="$1" result
    result="$(date -u -d "$value" +%s 2>/dev/null)" && { printf '%s\n' "$result"; return; }
    result="$(LC_ALL=C date -j -u -f '%b %e %T %Y %Z' "$value" +%s 2>/dev/null)" && { printf '%s\n' "$result"; return; }
    result="$(date -j -u -f '%Y-%m-%dT%H:%M:%SZ' "$value" +%s 2>/dev/null)" && { printf '%s\n' "$result"; return; }
    return 1
}

certificate_validity() {
    local before="$1" after="$2" now begin end remain
    CERT_DAYS=UNKNOWN; CERT_STATE=PARSE_ERROR
    now="$(date +%s)" || return
    begin="$(certificate_epoch "$before")" || return
    end="$(certificate_epoch "$after")" || return
    [[ "$now" =~ ^[0-9]+$ && "$begin" =~ ^-?[0-9]+$ && "$end" =~ ^-?[0-9]+$ ]] || return
    remain=$((end-now)); CERT_DAYS=$((remain/86400))
    if ((begin>now)); then CERT_STATE=NOT_YET_VALID
    elif ((remain<=0)); then CERT_STATE=EXPIRED
    elif ((remain<=CERT_CRIT_DAYS*86400)); then CERT_STATE=CRITICAL
    elif ((remain<=CERT_WARN_DAYS*86400)); then CERT_STATE=WARN
    else CERT_STATE=OK; fi
}

cert_self_tests() (
    CERT_WARN_DAYS=30 CERT_CRIT_DAYS=7
    [[ "$(certificate_epoch '2000-01-01T00:00:00Z')" == 946684800 ]] || return 1
    certificate_validity '2000-01-01T00:00:00Z' '2001-01-01T00:00:00Z'
    [[ "$CERT_STATE" == EXPIRED && "$CERT_DAYS" == -* ]] || return 1
    certificate_validity invalid invalid
    [[ "$CERT_STATE" == PARSE_ERROR && "$CERT_DAYS" == UNKNOWN ]] || return 1
    tls_valid_target 'example.invalid' 443 || return 1
    tls_valid_target '::1' 443 || return 1
    ! tls_valid_target '--context=escape' 443 || return 1
    ! tls_valid_target 'example.invalid' 65536 || return 1
    ! tls_valid_target 'example.invalid;id' 443 || return 1
    local cert_fixture_status=RBAC_DENIED
    cache_status() { printf '%s\n' "$cert_fixture_status"; }
    gitops_certificate_collection_rc fixture; [[ $? == 2 ]] || return 1
    cert_fixture_status=AUTH_ERROR
    gitops_certificate_collection_rc fixture; [[ $? == 3 ]] || return 1
    cert_fixture_status=EMPTY_RESULT
    gitops_certificate_collection_rc fixture; [[ $? == 0 ]] || return 1
    cert_fixture_status=COMMAND_MISSING
    gitops_certificate_collection_rc fixture; [[ $? == 2 ]] || return 1
)

gitops_certificate_self_tests() (
    # All collectors below are isolated mocks. No cluster, remote Git, network,
    # private key file or production credential is used by these fixtures.
    has jq || { printf 'SKIP GitOps JSON fixtures: jq unavailable\n'; return 0; }
    local fixture_dir
    fixture_dir="$(mktemp -d "$RUN_DIR/gitops-cert-fixtures.XXXXXXXX")" || return 1
    trap 'rm -rf -- "$fixture_dir"' EXIT
    local CACHE_DIR="$fixture_dir" SENTINEL_CONTEXT=fixture SENTINEL_NAMESPACE=fixture
    local CERT_WARN_DAYS=30 CERT_CRIT_DAYS=7 FORCE_REFRESH=0
    cache_status() { printf 'OK\n'; }
    cache_age() { printf '0\n'; }
    cache_file() { printf '%s/%s.json\n' "$CACHE_DIR" "$1"; }
    json_cache_path() {
        if [[ -s "$CACHE_DIR/$1.json" ]]; then printf '%s/%s.json\n' "$CACHE_DIR" "$1"
        else printf '%s/empty.json\n' "$CACHE_DIR"; fi
    }
    collect_json() { printf '%s\n' "$fixture" | jq "$5" > "$CACHE_DIR/$1.json"; }
    collect_pods() { :; }; collect_workloads() { :; }
    findings_add() { printf '%s|%s|%s|%s|%s\n' "$@"; }
    printf '{"items":[]}\n' > "$CACHE_DIR/empty.json"
    local fixture='{"items":[{"kind":"GitRepository","metadata":{"name":"source","namespace":"fixture","generation":2},"spec":{"url":"https://test-user:test-password@example.invalid/repo.git?token=fixture-only"},"status":{"observedGeneration":2,"artifact":{"revision":"main@sha1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"conditions":[{"type":"Ready","status":"True","observedGeneration":2}]}}]}'
    gitops_report > "$fixture_dir/gitops.txt" || return 1
    grep -q 'OK NO_DRIFT_EVIDENCE' "$fixture_dir/gitops.txt" || return 1
    ! grep -q 'test-password\|fixture-only' "$CACHE_DIR/flux_gitrepositories.json" || return 1
    jq '.items[0].metadata.generation=3' "$CACHE_DIR/flux_gitrepositories.json" > "$CACHE_DIR/change.json" || return 1
    mv -- "$CACHE_DIR/change.json" "$CACHE_DIR/flux_gitrepositories.json"
    gitops_findings > "$fixture_dir/findings.txt" || return 1
    grep -q 'GENERATION_DRIFT' "$fixture_dir/findings.txt" || return 1
    cat > "$CACHE_DIR/pods.json" <<'PODS_FIXTURE'
{"items":[{"metadata":{"name":"pod","namespace":"fixture","ownerReferences":[{"kind":"ReplicaSet","name":"rs","controller":true}]},"spec":{"containers":[{"name":"api","image":"example.invalid/image@sha256:abc","volumeMounts":[{"name":"cert","mountPath":"/cert"}]}],"volumes":[{"name":"cert","secret":{"secretName":"fixture-tls"}}]},"status":{"containerStatuses":[{"name":"api","ready":true,"imageID":"example.invalid/image@sha256:abc"}]}}]}
PODS_FIXTURE
    cat > "$CACHE_DIR/workloads.json" <<'WORKLOADS_FIXTURE'
{"items":[{"kind":"ReplicaSet","metadata":{"name":"rs","ownerReferences":[{"kind":"Deployment","name":"api","controller":true}]}},{"kind":"Deployment","metadata":{"name":"api","labels":{},"annotations":{},"generation":1},"spec":{"replicas":1,"template":{"spec":{"containers":[{"name":"api","image":"example.invalid/image@sha256:abc"}]}}},"status":{"availableReplicas":1,"observedGeneration":1}}]}
WORKLOADS_FIXTURE
    deployment_chain_report > "$fixture_dir/chain.txt" || return 1
    grep -q 'NO_DRIFT_EVIDENCE (digest matches)' "$fixture_dir/chain.txt" || return 1
    cert_mounts_report > "$fixture_dir/mounts.txt" || return 1
    grep -q 'CONFIGURED' "$fixture_dir/mounts.txt" || return 1
    cert_self_tests || return 1
    if has openssl; then
        local pem cert_fixture_b64
        pem="$(openssl req -x509 -newkey rsa:2048 -nodes -subj '/CN=sentinel-self-test.invalid' -days 5 -keyout /dev/null 2>/dev/null)" || return 1
        certificate_chain_metadata fixture fixture "$pem" > "$fixture_dir/certificate.txt" || return 1
        grep -q '\[CRITICAL\]' "$fixture_dir/certificate.txt" || return 1
        ! grep -q 'BEGIN.*KEY\|BEGIN CERTIFICATE' "$fixture_dir/certificate.txt" || return 1
        cert_fixture_b64="$(printf '%s\n' "$pem" | openssl base64 -A)" || return 1
        kctl_ns() { printf 'fixture\t%s\n' "$cert_fixture_b64"; }
        tls_secret_metadata_collect > "$fixture_dir/secret-certificate.txt" || return 1
        grep -q '\[CRITICAL\]' "$fixture_dir/secret-certificate.txt" || return 1
        ! grep -q 'BEGIN.*KEY\|BEGIN CERTIFICATE' "$fixture_dir/secret-certificate.txt" || return 1
        unset pem cert_fixture_b64
    else printf 'SKIP X.509 parsing fixture: openssl unavailable\n'; fi
    if declare -F dev_flux_source_wait >/dev/null; then
        local MODE=dev-flux-verify DEV_COMMIT_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        local DEV_FLUX_WAIT=1 DEV_FLUX_SELECTED_SOURCE=source DEV_FLUX_SELECTED_NAMESPACE=fixture API_TIMEOUT=1
        local DEV_FLUX_JSON DEV_FLUX_DEPENDENTS_OK
        dev_flux_query() { DEV_FLUX_JSON="$fixture"; }
        dev_flux_source_wait > "$fixture_dir/source-pass.txt" || return 1
        grep -q 'FLUX_SOURCE_SYNCHRONIZED' "$fixture_dir/source-pass.txt" || return 1
        fixture="$(printf '%s\n' "$fixture" | jq '.items[0].metadata.generation=3')" || return 1
        if dev_flux_source_wait > "$fixture_dir/source-generation.txt"; then return 1; fi
        grep -q 'TIMEOUT' "$fixture_dir/source-generation.txt" || return 1
        fixture="$(printf '%s\n' "$fixture" | jq '.items[0].metadata.generation=2 | .items[0].status.artifact.revision="main@sha1:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"')" || return 1
        if dev_flux_source_wait > "$fixture_dir/source-revision.txt"; then return 1; fi
        grep -q 'TIMEOUT' "$fixture_dir/source-revision.txt" || return 1
        local ks='{"items":[{"kind":"Kustomization","metadata":{"name":"apps","namespace":"fixture","generation":1},"spec":{"sourceRef":{"kind":"GitRepository","name":"source"},"suspend":false},"status":{"observedGeneration":1,"lastAppliedRevision":"main@sha1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","conditions":[{"type":"Ready","status":"True"}],"inventory":{"entries":[{"id":"fixture_api_helm.toolkit.fluxcd.io_HelmRelease","v":"v2"}]}}}]}'
        local hr='{"items":[{"kind":"HelmRelease","metadata":{"name":"api","namespace":"fixture","generation":1},"spec":{"suspend":false},"status":{"observedGeneration":1,"conditions":[{"type":"Ready","status":"True"},{"type":"Released","status":"True"}]}},{"kind":"HelmRelease","metadata":{"name":"unrelated","namespace":"fixture","generation":1},"spec":{"suspend":false},"status":{"observedGeneration":1,"conditions":[{"type":"Ready","status":"False"}]}}]}'
        dev_flux_query() { case "$1" in kustomizations.*) DEV_FLUX_JSON="$ks" ;; helmreleases.*) DEV_FLUX_JSON="$hr" ;; esac; }
        dev_flux_dependents_once > "$fixture_dir/dependents.txt" || return 1
        [[ "$DEV_FLUX_DEPENDENTS_OK" == 1 ]] || return 1
        grep -q 'HelmRelease/fixture/api' "$fixture_dir/dependents.txt" || return 1
        ! grep -q 'unrelated' "$fixture_dir/dependents.txt" || return 1
        hr="$(printf '%s\n' "$hr" | jq '.items[0].status.conditions[0].status="False"')" || return 1
        dev_flux_dependents_once > "$fixture_dir/dependents-failed.txt" || return 1
        [[ "$DEV_FLUX_DEPENDENTS_OK" == 0 ]] || return 1
        MODE=dashboard
        if dev_flux_reconcile_guarded >/dev/null 2>&1; then return 1; fi
    fi
)

certificate_pem_metadata() {
    local name="$1" source="$2" pem="$3" metadata line before='' after='' sans
    metadata="$(printf '%s\n' "$pem" | openssl x509 -noout -subject -issuer -serial -dates -fingerprint -sha256 2>/dev/null)" || {
        printf '[PARSE_ERROR] %s | source=%s | invalid or absent X.509 certificate\n' "$name" "$source"; return 1;
    }
    while IFS= read -r line; do
        case "$line" in notBefore=*) before="${line#*=}" ;; notAfter=*) after="${line#*=}" ;; esac
    done <<< "$metadata"
    certificate_validity "$before" "$after"
    printf '[%s] %s | namespace=%s | source=%s | daysLeft=%s\n' "$CERT_STATE" "$name" "$SENTINEL_NAMESPACE" "$source" "$CERT_DAYS"
    printf '%s\n' "$metadata"
    sans="$(printf '%s\n' "$pem" | openssl x509 -noout -ext subjectAltName 2>/dev/null)" || sans='SAN: UNAVAILABLE with this OpenSSL version'
    printf '%s\n\n' "$sans"
}

certificate_decode() {
    printf '%s' "$1" | openssl base64 -d -A
}

certificate_chain_metadata() {
    local name="$1" source="$2" chain="$3" line block='' inside=0 count=0
    while IFS= read -r line; do
        line="${line%$'\r'}"
        if [[ "$line" == '-----BEGIN CERTIFICATE-----' ]]; then inside=1; block=''; fi
        if ((inside)); then block+="$line"$'\n'; fi
        if [[ "$line" == '-----END CERTIFICATE-----' && "$inside" == 1 ]]; then
            ((count+=1))
            certificate_pem_metadata "$name" "$source certificate#$count" "$block" || :
            inside=0; block=''
        fi
    done <<< "$chain"
    if ((count==0 || inside)); then printf '[PARSE_ERROR] %s | source=%s | missing/incomplete PEM certificate\n' "$name" "$source"; fi
}

secret_metadata_collect() {
    kctl_ns get secrets -o 'go-template={{range .items}}{{.metadata.name}}{{"\t"}}{{.type}}{{"\t"}}{{.metadata.creationTimestamp}}{{"\t"}}{{len .data}}{{"\t"}}{{range $key,$value := .data}}{{$key}}{{" "}}{{end}}{{"\n"}}{{end}}'
}

tls_secret_metadata_collect() {
    local raw name encoded pem rc
    has openssl || { printf 'COMMAND_MISSING: openssl; certificate parsing unavailable.\n'; return 127; }
    raw="$(kctl_ns get secrets --field-selector type=kubernetes.io/tls -o 'go-template={{range .items}}{{.metadata.name}}{{"\t"}}{{index .data "tls.crt"}}{{"\n"}}{{end}}')"; rc=$?
    ((rc==0)) || return "$rc"
    [[ -n "$raw" ]] || { printf 'EMPTY_RESULT: no TLS Secrets in selected namespace.\n'; return 0; }
    while IFS=$'\t' read -r name encoded; do
        [[ -n "$name" ]] || continue
        pem="$(certificate_decode "$encoded" 2>/dev/null)" || { printf '[PARSE_ERROR] %s | certificate base64 decode failed\n' "$name"; continue; }
        certificate_chain_metadata "$name" 'Secret/tls.crt' "$pem"
        unset pem encoded
    done <<< "$raw"
    unset raw
}

cert_manager_collect() {
    local resource scope key
    local projection='{items:[.items[] | {kind,metadata:{name:.metadata.name,namespace:.metadata.namespace,creationTimestamp:.metadata.creationTimestamp,generation:.metadata.generation},spec:{secretName:.spec.secretName,issuerRef:.spec.issuerRef,dnsNames:.spec.dnsNames,duration:.spec.duration,renewBefore:.spec.renewBefore},status:{notBefore:.status.notBefore,notAfter:.status.notAfter,renewalTime:.status.renewalTime,revision:.status.revision,failureTime:.status.failureTime,conditions:(.status.conditions // [])}}]}'
    for resource in certificates.cert-manager.io certificaterequests.cert-manager.io issuers.cert-manager.io clusterissuers.cert-manager.io; do
        scope=ns; [[ "$resource" == clusterissuers.* ]] && scope=cluster
        key="cert_${resource%%.*}"
        collect_json "$key" 60 "$scope" "$resource" "$projection" 'NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,SECRET:.spec.secretName,NOTAFTER:.status.notAfter' || :
    done
}

cert_ingress_collect() {
    collect_json cert_ingresses 60 ns ingresses.networking.k8s.io '{items:[.items[]|{metadata:{name:.metadata.name,namespace:.metadata.namespace},spec:{tls:(.spec.tls // []),rules:[.spec.rules[]?|{host}]}}]}' 'NAME:.metadata.name,HOSTS:.spec.tls[*].hosts,SECRETS:.spec.tls[*].secretName' || :
}

cert_mounts_report() {
    collect_pods
    printf 'SECRET MOUNT REFERENCES | SOURCE Pod specifications | namespace=%s | cache age=%ss\n' "$SENTINEL_NAMESPACE" "$(cache_age pods)"
    printf 'CONFIGURED means a Pod spec reference; container filesystem contents are NOT VERIFIED.\n'
    has jq || { printf 'UNAVAILABLE: jq required for volume relationship analysis.\n'; return 0; }
    local file; file="$(json_cache_path pods)"
    printf 'SECRET\tPOD\tVOLUME\tCONTAINER\tMOUNT PATH\tSUBPATH\tSTATUS\n'
    jq -r '.items[] as $p | $p.spec.volumes[]? as $v |
      ([$v.secret.secretName, $v.projected.sources[]?.secret.name] | .[] | select(.!=null)) as $secret |
      ($p.spec.containers[]?, $p.spec.initContainers[]?, $p.spec.ephemeralContainers[]?) as $c |
      $c.volumeMounts[]? | select(.name==$v.name) |
      [$secret,$p.metadata.name,$v.name,$c.name,.mountPath,(.subPath // "-"),"CONFIGURED; secret type/certificate presence may be unknown"]|@tsv' "$file"
}

certificate_relationships_report() {
    cert_ingress_collect
    printf '\nINGRESS -> TLS SECRET -> CERTIFICATE -> ISSUER\n'
    has jq || { [[ -f "$CACHE_DIR/cert_ingresses.txt" ]] && cat "$CACHE_DIR/cert_ingresses.txt"; return 0; }
    local ingress certs; ingress="$(json_cache_path cert_ingresses)"; certs="$(json_cache_path cert_certificates)"
    jq -r --slurpfile cert "$certs" '.items[] as $i | $i.spec.tls[]? as $tls |
      [$cert[0].items[] | select(.spec.secretName==$tls.secretName)] as $matches |
      "Ingress/\($i.metadata.name) hosts=\($tls.hosts // [] | join(",")) -> Secret/\($tls.secretName // "UNKNOWN") -> " +
      (if ($matches|length)==0 then "Certificate/UNKNOWN -> Issuer/UNKNOWN"
       else ($matches | map("Certificate/"+.metadata.name+" -> "+(.spec.issuerRef.kind // "Issuer")+"/"+(.spec.issuerRef.name // "UNKNOWN")) | join("; ")) end)' "$ingress"
}

certificates_report() {
    local key file name before after condition report_rc=0 collection_rc
    printf 'CERTIFICATES | namespace=%s | TTL 60s | WARN <=%sd CRITICAL <=%sd\n' "$SENTINEL_NAMESPACE" "$CERT_WARN_DAYS" "$CERT_CRIT_DAYS"
    printf 'SOURCE cert-manager status and parsed TLS Secret certificate chains. Raw certificate/key values are not exported.\n'
    cert_manager_collect
    for key in cert_certificates cert_certificaterequests cert_issuers cert_clusterissuers; do
        printf '\n%s | %s | cache age=%ss\n' "${key#cert_}" "$(cache_status "$key")" "$(cache_age "$key")"
        file="$(cache_file "$key")"
        if has jq && [[ -s "$file" ]]; then
            jq -r '.items[] | "\(.kind)/\(.metadata.name) secret=\(.spec.secretName // "-") issuer=\(.spec.issuerRef.kind // "Issuer")/\(.spec.issuerRef.name // "-") renewal=\(.status.renewalTime // "UNKNOWN")",(.status.conditions[]? | "  \(.type)=\(.status) reason=\(.reason // "-") message=\(.message // "-")")' "$file"
            if [[ "$key" == cert_certificates ]]; then
                while IFS=$'\t' read -r name before after; do
                    [[ -n "$name" ]] || continue
                    certificate_validity "$before" "$after"
                    printf '[%s] Certificate/%s daysLeft=%s notBefore=%s notAfter=%s\n' "$CERT_STATE" "$name" "$CERT_DAYS" "$before" "$after"
                    case "$CERT_STATE" in EXPIRED|NOT_YET_VALID) report_rc=1 ;; esac
                done < <(jq -r '.items[] | [.metadata.name,(.status.notBefore // "UNKNOWN"),(.status.notAfter // "UNKNOWN")]|@tsv' "$file")
            fi
        elif [[ -s "$CACHE_DIR/$key.txt" ]]; then cat "$CACHE_DIR/$key.txt"; fi
    done
    collect_text secret_metadata 60 secret_metadata_collect || :
    printf '\nSECRET METADATA | %s | cache age=%ss\nNAME\tTYPE\tCREATED\tKEY COUNT\tKEY NAMES\n' "$(cache_status secret_metadata)" "$(cache_age secret_metadata)"
    [[ -s "$CACHE_DIR/secret_metadata.txt" ]] && cat "$CACHE_DIR/secret_metadata.txt"
    collect_text tls_certificates 60 tls_secret_metadata_collect || :
    printf '\nTLS CERTIFICATE METADATA | %s | cache age=%ss\n' "$(cache_status tls_certificates)" "$(cache_age tls_certificates)"
    [[ -s "$CACHE_DIR/tls_certificates.txt" ]] && cat "$CACHE_DIR/tls_certificates.txt"
    certificate_relationships_report
    cert_mounts_report
    if [[ -s "$CACHE_DIR/tls_certificates.txt" ]] && grep -Eq '^\[(EXPIRED|NOT_YET_VALID)\]' "$CACHE_DIR/tls_certificates.txt"; then report_rc=1; fi
    gitops_certificate_collection_rc cert_certificates cert_certificaterequests cert_issuers cert_clusterissuers secret_metadata tls_certificates cert_ingresses pods; collection_rc=$?
    ((collection_rc>report_rc)) && report_rc="$collection_rc"
    return "$report_rc"
}

certificates_findings() {
    local name before after severity line state
    if has jq && [[ -s "$CACHE_DIR/cert_certificates.json" ]]; then
        while IFS=$'\t' read -r name before after; do
            [[ -n "$name" ]] || continue
            certificate_validity "$before" "$after"
            case "$CERT_STATE" in EXPIRED|NOT_YET_VALID) severity=FAIL ;; CRITICAL|WARN) severity=WARN ;; OK) severity=OK ;; *) severity=UNKNOWN ;; esac
            findings_add "$severity" CERTIFICATE "Certificate/$name" "$CERT_STATE daysLeft=$CERT_DAYS" 'cert-manager notBefore/notAfter'
        done < <(jq -r '.items[]|[.metadata.name,(.status.notBefore // "UNKNOWN"),(.status.notAfter // "UNKNOWN")]|@tsv' "$CACHE_DIR/cert_certificates.json")
        while IFS=$'\t' read -r name state; do
            [[ -n "$name" ]] && findings_add WARN CERTIFICATE "Certificate/$name" "Ready=False: $state" 'cert-manager Ready condition'
        done < <(jq -r '.items[] | .metadata.name as $n | .status.conditions[]? | select(.type=="Ready" and .status=="False") | [$n,(.reason // "UNKNOWN")]|@tsv' "$CACHE_DIR/cert_certificates.json")
    fi
    if [[ -s "$CACHE_DIR/tls_certificates.txt" ]]; then
        while IFS= read -r line; do
            [[ "$line" == \[*\]* ]] || continue
            state="${line%%]*}"; state="${state#[}"
            name="${line#*] }"; name="${name%% |*}"
            case "$state" in EXPIRED|NOT_YET_VALID) severity=FAIL ;; CRITICAL|WARN) severity=WARN ;; OK) severity=OK ;; *) severity=UNKNOWN ;; esac
            findings_add "$severity" CERTIFICATE "Secret/$name" "$line" 'X.509 TLS certificate metadata'
        done < "$CACHE_DIR/tls_certificates.txt"
    else findings_add UNKNOWN CERTIFICATE 'TLS secrets' "$(cache_status tls_certificates)" 'Certificate collector'; fi
}

webhook_certificate_collect() {
    local resource raw name encoded pem rc
    resource="$1"
    raw="$(kctl_cluster get "$resource" -o 'go-template={{range .items}}{{$config := .metadata.name}}{{range .webhooks}}{{$config}}{{"/"}}{{.name}}{{"\t"}}{{.clientConfig.caBundle}}{{"\n"}}{{end}}{{end}}')"; rc=$?
    ((rc==0)) || return "$rc"
    [[ -n "$raw" ]] || { printf 'EMPTY_RESULT: no webhook CA bundles.\n'; return 0; }
    while IFS=$'\t' read -r name encoded; do
        [[ -n "$encoded" && "$encoded" != '<no value>' ]] || { printf '[UNKNOWN] %s: no explicit CA bundle\n' "$name"; continue; }
        pem="$(certificate_decode "$encoded" 2>/dev/null)" || { printf '[PARSE_ERROR] %s\n' "$name"; continue; }
        certificate_chain_metadata "$name" "$resource CA bundle" "$pem"
        unset pem encoded
    done <<< "$raw"
    unset raw
}

webhook_certificates_report() {
    local resource key
    has openssl || { printf 'COMMAND_MISSING: openssl\n'; return 0; }
    printf 'WEBHOOK CA CERTIFICATES | cluster scope | each PEM certificate in CA bundles is inspected.\n'
    printf 'A CA bundle is trust configuration; it does not reveal the serving endpoint certificate.\n'
    for resource in validatingwebhookconfigurations.admissionregistration.k8s.io mutatingwebhookconfigurations.admissionregistration.k8s.io; do
        key="cert_${resource%%.*}"
        collect_text "$key" 60 webhook_certificate_collect "$resource" || :
        printf '\n%s | %s | cache age=%ss\n' "$resource" "$(cache_status "$key")" "$(cache_age "$key")"
        [[ -s "$CACHE_DIR/$key.txt" ]] && cat "$CACHE_DIR/$key.txt"
    done
}

filesystem_certificate_report() {
    local path="$1" pem
    has openssl || { printf 'COMMAND_MISSING: openssl\n'; return 0; }
    [[ -f "$path" && -r "$path" && ! -L "$path" ]] || { printf 'UNAVAILABLE: select a readable regular certificate file (no symlinks).\n'; return 2; }
    case "$path" in *.crt|*.cer|*.pem) ;; *) printf 'UNSUPPORTED: use a .crt, .cer or .pem certificate.\n'; return 2 ;; esac
    if grep -q 'PRIVATE KEY' "$path"; then printf 'REFUSED: file contains private key material.\n'; return 2; fi
    pem="$(openssl x509 -in "$path" -outform PEM 2>/dev/null)" || pem="$(openssl x509 -inform DER -in "$path" -outform PEM 2>/dev/null)" || { printf 'PARSE_ERROR: not an X.509 PEM/DER certificate.\n'; return 2; }
    certificate_pem_metadata "${path##*/}" 'Explicitly selected filesystem certificate' "$pem"
    unset pem
}

tls_valid_target() {
    local host="$1" port="$2"
    [[ "$host" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ || "$host" =~ ^[[:xdigit:]:]+$ ]] || return 1
    [[ "$port" =~ ^[0-9]{1,5}$ ]] && ((10#$port>0 && 10#$port<=65535))
}

tls_report() {
    local host="$1" port="${2:-443}" target help output rc pem protocol label check flag local_support summary report_rc=0
    tls_valid_target "$host" "$port" || { printf 'INVALID target: provide DNS name/IP and port 1..65535.\n'; return 2; }
    printf 'TLS AUDIT | host=%s port=%s | SOURCE direct network handshake | per-probe timeout=%ss\n' "$host" "$port" "$TLS_TIMEOUT"
    printf 'Observed from this workstation; results can differ from Pod network paths.\n'
    if [[ "$host" == *:* || "$host" =~ ^[0-9.]+$ ]]; then printf 'DNS: N/A (IP target)\n'
    elif has getent; then
        output="$(run_bounded "$TLS_TIMEOUT" getent ahosts "$host" 2>&1)"; rc=$?
        if ((rc==0)) && [[ -n "$output" ]]; then printf 'DNS: RESOLVED\n%s\n' "$output"
        elif ((rc==124 || rc==137 || rc==143)); then printf 'DNS: API_TIMEOUT\n'; report_rc=3
        else printf 'DNS: RESOLUTION_FAILED\n'; fi
    else printf 'DNS: UNAVAILABLE (getent absent; TLS connection will resolve through OpenSSL)\n'; fi
    output="$(run_bounded "$TLS_TIMEOUT" bash -c 'exec 3<>"/dev/tcp/$1/$2"' sentinel-tcp "$host" "$port" 2>&1)"; rc=$?
    if ((rc==0)); then printf 'TCP: CONNECTED\n'
    elif ((rc==124 || rc==137 || rc==143)); then printf 'TCP: TIMEOUT\n'; report_rc=3
    else printf 'TCP: CONNECTION_FAILED_OR_LOCAL_UNAVAILABLE\n'; report_rc=1; fi
    has openssl || { printf 'TLS: COMMAND_MISSING (openssl)\n'; return 2; }
    target="$host:$port"; [[ "$host" == *:* ]] && target="[$host]:$port"
    help="$(openssl s_client -help 2>&1)"
    local -a args=(openssl s_client -connect "$target" -servername "$host" -showcerts)
    [[ "$help" == *-verify_return_error* ]] && args+=(-verify_return_error)
    if [[ "$host" == *:* || "$host" =~ ^[0-9.]+$ ]]; then
        if [[ "$help" == *-verify_ip* ]]; then args+=(-verify_ip "$host"); else printf 'HOSTNAME VERIFICATION: UNAVAILABLE in local OpenSSL\n'; fi
    elif [[ "$help" == *-verify_hostname* ]]; then args+=(-verify_hostname "$host")
    else printf 'HOSTNAME VERIFICATION: UNAVAILABLE in local OpenSSL\n'; fi
    output="$(run_bounded "$TLS_TIMEOUT" "${args[@]}" </dev/null 2>&1)"; rc=$?
    if ((rc==124 || rc==137 || rc==143)); then printf 'TLS HANDSHAKE: TIMEOUT\n'; report_rc=3
    elif ((rc==0)) && [[ "$output" == *'BEGIN CERTIFICATE'* ]]; then printf 'TLS HANDSHAKE: COMPLETED\n'
    else printf 'TLS HANDSHAKE: FAILED / CERTIFICATE_VERIFICATION_OR_NETWORK_ERROR (exit=%s)\n' "$rc"; ((report_rc<1)) && report_rc=1; fi
    printf '%s\n' "$output" | awk '/^[[:space:]]*(Protocol[[:space:]]*:|Cipher[[:space:]]*:|Cipher is |Verification:|Verify return code:|New,|Server Temp Key:|verify error:|Verification error:)/ {print}'
    pem="$(printf '%s\n' "$output" | awk '/-----BEGIN CERTIFICATE-----/{p=1} p{print} /-----END CERTIFICATE-----/{exit}')"
    [[ -n "$pem" ]] && certificate_pem_metadata "$host:$port" 'Remote TLS leaf' "$pem"
    unset output pem
    printf '\nPROTOCOL PROBES (independent actual handshakes; certificate trust assessed above)\n'
    for protocol in tls1 tls1_1 tls1_2 tls1_3; do
        case "$protocol" in tls1) label='TLS 1.0' ;; tls1_1) label='TLS 1.1' ;; tls1_2) label='TLS 1.2' ;; tls1_3) label='TLS 1.3' ;; esac
        if [[ "$help" != *"-$protocol "* && "$help" != *"-$protocol"$'\n'* ]]; then printf '%-8s LOCAL_UNAVAILABLE\n' "$label"; continue; fi
        output="$(run_bounded "$TLS_TIMEOUT" openssl s_client -connect "$target" -servername "$host" "-$protocol" </dev/null 2>&1)"; rc=$?
        summary="$(printf '%s\n' "$output" | awk '/Cipher is / && !/NONE/ {print} /Cipher[[:space:]]*:/ && !/0000|NONE/ {print}')"
        if ((rc==124 || rc==137 || rc==143)); then check=TIMEOUT
        elif [[ "$output" == *'no protocols available'* || "$output" == *'no ciphers available'* || "$output" == *'no suitable signature algorithm'* || "$output" == *'unknown option'* || "$output" == *'Unknown option'* ]]; then check=LOCAL_UNAVAILABLE
        elif [[ -n "$summary" && "$output" == *'BEGIN CERTIFICATE'* ]]; then check=SUPPORTED
        elif [[ "$output" == *'alert protocol version'* ]]; then check=REJECTED
        else check='NOT_VERIFIED (handshake failed; remote rejection not established)'; fi
        printf '%-8s %s\n' "$label" "$check"
        unset output
    done
    return "$report_rc"
}

tls_menu() {
    local host port choice
    printf '\nTLS: direct DNS/TCP/TLS probes, bounded per attempt; results apply to this workstation.\n'
    choose 'TLS target' 'Discovered ingress host' 'Enter host and port' 'Back'; choice="$REPLY"
    case "$choice" in
        'Discovered ingress host')
            cert_ingress_collect
            has jq || { printf 'UNAVAILABLE: jq required to select discovered host.\n'; return; }
            local -a hosts=()
            mapfile -t hosts < <(jq -r '[.items[]|(.spec.tls[]?.hosts[]?,.spec.rules[]?.host)|select(.!=null and .!="" and (startswith("*.")|not))]|unique[]' "$(json_cache_path cert_ingresses)")
            ((${#hosts[@]})) || { printf 'No concrete ingress hosts discovered.\n'; return; }
            choose 'Host' "${hosts[@]}" 'Back'; host="$REPLY"
            [[ "$host" == Back || -z "$host" ]] && return
            port=443 ;;
        'Enter host and port') prompt 'DNS host or IP (no URL scheme)'; host="$REPLY"; prompt 'Port [443]'; port="${REPLY:-443}" ;;
        *) return ;;
    esac
    capture_report 'TLS audit' tls_report "$host" "$port"; view_file "$CURRENT_REPORT" 'TLS audit'
}


# 14 Splunk Engine: catalog generation never requires a Splunk connection.
declare -a SP_CATEGORY=() SP_TERMS=() SP_DESCRIPTION=() SP_QUERY=()
declare -a SP_STATUS=() SP_COUNT=() SP_VALIDATED=() SP_NOTES=() SP_FIELDS=()
declare -A SP_MAP=() SP_VALUE=()
SP_INITIALIZED=0 SP_SIGNATURE='' SP_DISCOVERY_SCOPE='' SP_DISCOVERED_AT='' SP_KUBE_SCOPE=''
SP_GENERATION_STATUS=GENERATED_UNVALIDATED SP_GENERATION_DETAIL=''
SP_RESPONSE='' SP_REQUEST_STATUS='' SP_REQUEST_DETAIL='' SP_HTTP=''

splunk_init() {
    # Remove the inherited export attribute; children never inherit this token.
    export -n SPLUNK_TOKEN 2>/dev/null || :
    [[ $SP_INITIALIZED == 1 ]] && return 0
    SP_CATEGORY=( '' 'Authentication events' 'Authorization failures' 'Kubernetes changes'
      'Configuration changes' 'Deployment events' 'Pod failures' 'Container failures'
      'Kubernetes warnings' 'Flux failures' 'Helm failures' 'Certificate events'
      'TLS failures' 'Secret metadata events' 'RBAC events' 'Network failures'
      'Kafka failures' 'SNMP/alarm events' 'Syslog/log-transformer failures'
      'Application errors' 'Audit events' 'Security events' 'Resource pressure/OOM'
      'Storage/PVC failures' )
    SP_TERMS=( ''
      '("authentication" OR "login" OR "OIDC" OR "unauthenticated")'
      '("forbidden" OR "unauthorized" OR "access denied" OR "permission denied")'
      '("kubernetes" AND ("create" OR "update" OR "patch" OR "delete"))'
      '("configuration" OR "configmap" OR "configuration changed")'
      '("deployment" OR "rollout" OR "ReplicaSet")'
      '("CrashLoopBackOff" OR "ImagePullBackOff" OR "FailedScheduling" OR "Evicted")'
      '("container" AND ("failed" OR "terminated" OR "restart" OR "OOMKilled"))'
      '("Warning" AND ("kubernetes" OR "kubelet" OR "pod"))'
      '(("flux" OR "kustomize-controller" OR "source-controller") AND ("error" OR "failed"))'
      '(("helm" OR "helm-controller" OR "HelmRelease") AND ("failed" OR "error"))'
      '("certificate" OR "cert-manager" OR "CertificateRequest" OR "x509")'
      '("TLS handshake" OR "certificate verify failed" OR "unknown authority" OR "SSL error")'
      '("secret" AND ("created" OR "updated" OR "deleted" OR "metadata"))'
      '("RBAC" OR "RoleBinding" OR "ClusterRoleBinding" OR "ClusterRole")'
      '("connection refused" OR "connection timed out" OR "DNS" OR "NetworkPolicy")'
      '("kafka" AND ("error" OR "failed" OR "timeout" OR "under-replicated"))'
      '("SNMP" OR "trap" OR "alarm raised" OR "alarm cleared")'
      '(("syslog" OR "log-transformer" OR "log transformer") AND ("failed" OR "dropped" OR "error"))'
      '("exception" OR "fatal" OR "application error" OR "unhandled")'
      '("audit" OR "auditID" OR "AuditEvent")'
      '("security" OR "intrusion" OR "suspicious" OR "policy violation")'
      '("OOMKilled" OR "out of memory" OR "MemoryPressure" OR "DiskPressure" OR "Insufficient cpu")'
      '("FailedMount" OR "FailedAttachVolume" OR "FailedBinding" OR "PVC" OR "volume error")' )
    local i
    for ((i=1; i<=23; i++)); do
        SP_DESCRIPTION[i]='Keyword triage search; matches require investigation and do not establish root cause or audit coverage.'
        SP_STATUS[i]=GENERATED_UNVALIDATED SP_COUNT[i]='UNKNOWN' SP_VALIDATED[i]='NEVER'
    done
    SP_INITIALIZED=1
}

splunk_quote() {
    local value=$1
    value=${value//\\/\\\\}; value=${value//\"/\\\"}
    value=${value//$'\r'/ }; value=${value//$'\n'/ }; value=${value//$'\t'/ }
    printf '"%s"' "$value"
}

splunk_scope_signature() {
    printf '%s\034%s\034%s' "${SPLUNK_URL:-}" "${SPLUNK_INDEX:-}" "${SPLUNK_SOURCETYPE:-}"
}

splunk_field_safe() {
    local field=$1 lower=${1,,}
    [[ $field =~ ^[a-zA-Z_][a-zA-Z0-9_.:-]*$ ]] || return 1
    case $lower in *password*|*passwd*|*token*|*secret*|*private*key*|*authorization*|*credential*|*api_key*|*apikey*) return 1;; esac
}

splunk_has_field() {
    local field
    for field in "${SP_FIELDS[@]}"; do [[ $field == "$1" ]] && return 0; done
    return 1
}

splunk_base() {
    printf 'search'
    [[ -n ${SPLUNK_INDEX:-} ]] && printf ' index=%s' "$(splunk_quote "$SPLUNK_INDEX")"
    [[ -n ${SPLUNK_SOURCETYPE:-} ]] && printf ' sourcetype=%s' "$(splunk_quote "$SPLUNK_SOURCETYPE")"
    printf ' earliest=-15m latest=now'
}

splunk_catalog_inputs() {
    local role field value
    SP_GENERATION_STATUS=GENERATED_UNVALIDATED SP_GENERATION_DETAIL=''
    if [[ -n ${SPLUNK_INDEX:-} && ! $SPLUNK_INDEX =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$ ]]; then
        SP_GENERATION_STATUS=INVALID SP_GENERATION_DETAIL='Index must be an explicit name without wildcards or SPL operators'; return 1
    fi
    if [[ -n ${SPLUNK_SOURCETYPE:-} && ! $SPLUNK_SOURCETYPE =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.:/-]*$ ]]; then
        SP_GENERATION_STATUS=INVALID SP_GENERATION_DETAIL='Sourcetype must be an explicit name without wildcards or SPL operators'; return 1
    fi
    for role in "${!SP_MAP[@]}"; do
        field=${SP_MAP[$role]} value=${SP_VALUE[$role]:-}
        if ! splunk_field_safe "$field" || ! splunk_has_field "$field"; then
            SP_GENERATION_STATUS=FIELD_NOT_FOUND SP_GENERATION_DETAIL='A mapped field is not a safe member of the observed field set'; return 1
        fi
        if [[ ${#value} -gt 2048 || $value == *[$'\001'-$'\037'$'\177']* ]]; then
            SP_GENERATION_STATUS=INVALID SP_GENERATION_DETAIL='Filter values must contain at most 2048 characters and no control characters'; return 1
        fi
    done
}

splunk_generate() {
    splunk_init
    local i role base signature maptext='' required='' scope sig note
    scope=$(splunk_scope_signature)
    if [[ -n $SP_DISCOVERY_SCOPE && $SP_DISCOVERY_SCOPE != "$scope" ]]; then
        SP_FIELDS=(); SP_MAP=(); SP_VALUE=(); SP_DISCOVERY_SCOPE=''; SP_DISCOVERED_AT=''
    fi
    if [[ -n $SP_KUBE_SCOPE && $SP_KUBE_SCOPE != "${SENTINEL_CONTEXT:-}|${SENTINEL_NAMESPACE:-}" ]]; then
        # A scope switch invalidates semantic filter values, even when the
        # same Splunk source still exposes the previously discovered fields.
        SP_MAP=(); SP_VALUE=()
    fi
    SP_KUBE_SCOPE="${SENTINEL_CONTEXT:-}|${SENTINEL_NAMESPACE:-}"
    if ! splunk_catalog_inputs; then
        for ((i=1; i<=23; i++)); do
            SP_QUERY[i]='' SP_STATUS[i]=$SP_GENERATION_STATUS SP_COUNT[i]=UNKNOWN SP_VALIDATED[i]=NEVER SP_NOTES[i]=$SP_GENERATION_DETAIL
        done
        SP_REQUIRED_FIELDS=NONE SP_SIGNATURE=''
        return 1
    fi
    base=$(splunk_base)
    for role in cluster namespace pod container node host application severity message; do
        if [[ -n ${SP_MAP[$role]:-} && -n ${SP_VALUE[$role]:-} ]]; then
            # where equality treats values literally and is case-sensitive;
            # search field=value would interpret a user-entered * as wildcard.
            maptext+="${maptext:+ AND }'${SP_MAP[$role]}'=$(splunk_quote "${SP_VALUE[$role]}")"
            required+="${required:+,}${SP_MAP[$role]}"
        fi
    done
    signature="$scope|${SENTINEL_CONTEXT:-}|${SENTINEL_NAMESPACE:-}|$maptext"
    if [[ $SP_SIGNATURE != "$signature" ]]; then
        for ((i=1; i<=23; i++)); do
            SP_STATUS[i]=GENERATED_UNVALIDATED SP_COUNT[i]='UNKNOWN' SP_VALIDATED[i]='NEVER'
        done
        SP_SIGNATURE=$signature
    fi
    note='Keyword triage only; event fields and coverage are not assumed. Time window: last 15 minutes. Mapped values use exact case-sensitive comparisons; wildcard characters are literal.'
    [[ -z ${SPLUNK_INDEX:-} ]] && note+=' Index unspecified; offline query uses Splunk permitted defaults; connected searches require an explicit index.'
    if [[ -z ${SP_MAP[namespace]:-} || ${SP_VALUE[namespace]:-} != "${SENTINEL_NAMESPACE:-}" ]]; then
        note+=' Namespace scope UNVERIFIED: no observed namespace field mapped to the selected namespace.'
    else
        note+=' Namespace filter uses an observed field; field semantics are user-selected.'
    fi
    SP_REQUIRED_FIELDS=${required:-NONE}
    for ((i=1; i<=23; i++)); do
        SP_QUERY[i]="$base ${SP_TERMS[i]}${maptext:+ | where $maptext}"
        if [[ ${SP_STATUS[i]} == GENERATED_UNVALIDATED ]]; then SP_NOTES[i]=$note; fi
    done
}

splunk_connection_check() {
    SP_REQUEST_STATUS=SPLUNK_UNAVAILABLE SP_REQUEST_DETAIL='NOT_CONFIGURED'
    has curl || { SP_REQUEST_DETAIL='COMMAND_MISSING: curl'; return 1; }
    has jq || { SP_REQUEST_DETAIL='COMMAND_MISSING: jq; offline generation remains available'; return 1; }
    [[ -n ${SPLUNK_URL:-} && -n ${SPLUNK_TOKEN:-} && -n ${SPLUNK_INDEX:-} ]] || return 1
    # A management origin/base path only: no URL credentials, queries or fragments.
    [[ $SPLUNK_URL =~ ^https://([a-zA-Z0-9.-]+|\[[a-fA-F0-9:]+\])(:[0-9]{1,5})?(/[a-zA-Z0-9._~-]*)*$ ]] || {
        SP_REQUEST_DETAIL='INVALID: supply an HTTPS management URL without credentials, query or fragment'; return 1;
    }
    [[ $SPLUNK_INDEX =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$ ]] || {
        SP_REQUEST_DETAIL='INVALID: index must be an explicit index name, without wildcard'; return 1;
    }
    [[ -z ${SPLUNK_SOURCETYPE:-} || $SPLUNK_SOURCETYPE =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.:/-]*$ ]] || {
        SP_REQUEST_DETAIL='INVALID: sourcetype contains unsupported characters'; return 1;
    }
    [[ $SPLUNK_TOKEN != *[$'\001'-$'\037'$'\177']* ]] || {
        SP_REQUEST_DETAIL='INVALID: token contains a control character'; return 1;
    }
    SP_REQUEST_STATUS=OK SP_REQUEST_DETAIL='HTTPS certificate verification enabled'
}

splunk_request() {
    # This is a fixed, read-only search endpoint. The token is sent on stdin,
    # never as an argument, environment of a child process, or a temporary file.
    local search=$1 payload token_config rc limit=${SPLUNK_TIMEOUT:-20}
    SP_RESPONSE='' SP_HTTP=''
    splunk_init
    splunk_connection_check || return 1
    [[ $limit =~ ^[0-9]+$ && $limit -ge 1 && $limit -le 300 ]] || limit=20
    token_config=${SPLUNK_TOKEN//\\/\\\\}; token_config=${token_config//\"/\\\"}
    payload=$(printf 'header = "Authorization: Bearer %s"\n' "$token_config" |
      run_bounded "$((limit+2))" curl -q --config - --silent --show-error --globoff \
        --proto '=https' --proto-redir '=https' --max-redirs 0 --connect-timeout 5 \
        --max-time "$limit" --max-filesize 2097152 --request POST \
        --data-urlencode "search=$search" --data-urlencode 'output_mode=json' \
        --data-urlencode 'preview=false' \
        --data-urlencode 'auto_cancel=30' --write-out $'\nSENTINEL_HTTP:%{http_code}' \
        "${SPLUNK_URL%/}/services/search/v2/jobs/export" 2>/dev/null)
    rc=$?; token_config=''
    SP_HTTP=${payload##*$'\nSENTINEL_HTTP:'}
    SP_RESPONSE=${payload%$'\nSENTINEL_HTTP:'*}
    if ((rc != 0)); then
        SP_REQUEST_STATUS=SPLUNK_UNAVAILABLE
        case $rc in
          28|124|137) SP_REQUEST_DETAIL='API_TIMEOUT: no complete result was accepted';;
          60|51) SP_REQUEST_DETAIL='TLS_ERROR: server certificate verification failed';;
          63) SP_REQUEST_DETAIL='OUTPUT_LIMIT: response exceeded 2 MiB';;
          *) SP_REQUEST_DETAIL="NETWORK_ERROR: curl/transport exit $rc";;
        esac
        SP_RESPONSE=''; return 1
    fi
    case $SP_HTTP in
      200) ;;
      401) SP_REQUEST_DETAIL='AUTH_ERROR: HTTP 401'; SP_REQUEST_STATUS=SPLUNK_UNAVAILABLE; SP_RESPONSE=''; return 1;;
      403) SP_REQUEST_DETAIL='RBAC_DENIED: HTTP 403'; SP_REQUEST_STATUS=SPLUNK_UNAVAILABLE; SP_RESPONSE=''; return 1;;
      400|422) SP_REQUEST_DETAIL="Search rejected: HTTP $SP_HTTP"; SP_REQUEST_STATUS=INVALID; SP_RESPONSE=''; return 1;;
      *) SP_REQUEST_DETAIL="HTTP $SP_HTTP: no completed search result"; SP_REQUEST_STATUS=SPLUNK_UNAVAILABLE; SP_RESPONSE=''; return 1;;
    esac
    # Never consider an HTTP 200 alone sufficient. Reject malformed JSON and
    # both top-level and streamed messages, including partial-result warnings.
    if ! printf '%s' "$SP_RESPONSE" | jq -e -s 'length > 0 and all(.[]; type == "object")' >/dev/null 2>&1; then
        SP_REQUEST_STATUS=INVALID SP_REQUEST_DETAIL='PARSE_ERROR: response is not a JSON result stream'; SP_RESPONSE=''; return 1
    fi
    if ! printf '%s' "$SP_RESPONSE" | jq -e -s '
        def harmless_message:
          type == "object" and (.text|type) == "string" and
          (.type|type) == "string" and ((.type|ascii_upcase) == "INFO" or (.type|ascii_upcase) == "DEBUG");
        all(.[];
          (has("error") or has("errors") | not) and
          ((has("messages")|not) or ((.messages|type) == "array" and all(.messages[]; harmless_message))) and
          ((has("text") or has("type") | not) or harmless_message) and
          (has("result") or has("messages") or has("text")))
      ' >/dev/null 2>&1; then
        SP_REQUEST_STATUS=INVALID SP_REQUEST_DETAIL='Server returned an error, warning, or malformed message envelope; complete search coverage is not verified'; SP_RESPONSE=''; return 1
    fi
    if ! printf '%s' "$SP_RESPONSE" | jq -e -s '
        [ .[] | select(.result? != null) ] as $r |
        ($r|length) > 0 and all($r[]; .preview == false and (.result|type) == "object") and
        ($r[-1].lastrow == true) and all($r[0:-1][]; .lastrow != true)
      ' >/dev/null 2>&1; then
        SP_REQUEST_STATUS=INVALID SP_REQUEST_DETAIL='Incomplete, preview-only, or unrecognized export; final result marker required'; SP_RESPONSE=''; return 1
    fi
    SP_REQUEST_STATUS=OK SP_REQUEST_DETAIL='Completed JSON export, no error/warning messages'
}

splunk_discover() {
    splunk_generate || { printf '%s: %s\n' "$SP_GENERATION_STATUS" "$SP_GENERATION_DETAIL"; return 1; }
    local field list rc query
    query="$(splunk_base) | head 500 | fieldsummary maxvals=1 | fields field | head 500"
    printf 'Discovering field names from at most 500 events in the last 15 minutes...\n'
    if ! splunk_request "$query"; then
        printf '%s: %s\n' "$SP_REQUEST_STATUS" "$SP_REQUEST_DETAIL"
        return 1
    fi
    list=$(printf '%s' "$SP_RESPONSE" | jq -r -s '[.[] | .result.field? | select(type == "string")] | unique[]' 2>/dev/null)
    rc=$?; SP_RESPONSE=''
    ((rc == 0)) || { printf 'PARSE_ERROR: discovery fields unavailable\n'; return 1; }
    SP_FIELDS=(); SP_MAP=(); SP_VALUE=()
    while IFS= read -r field; do
        splunk_field_safe "$field" && SP_FIELDS+=("$field")
    done <<< "$list"
    SP_DISCOVERY_SCOPE=$(splunk_scope_signature)
    SP_DISCOVERED_AT=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    printf 'Observed selectable fields: %s. Sample coverage only; absent fields are not proven absent from the index.\n' "${#SP_FIELDS[@]}"
    printf 'Sensitive field names and names outside the safe identifier grammar are excluded.\n'
    ((${#SP_FIELDS[@]})) && printf '  %s\n' "${SP_FIELDS[@]}"
}

splunk_map_fields() {
    local role selection field
    ((${#SP_FIELDS[@]})) || { printf 'FIELD_NOT_FOUND: run field discovery first.\n'; return 1; }
    choose 'Map observed field to semantic role' cluster namespace pod container node host application severity message || return
    role=$REPLY
    [[ $role =~ ^[0-9]+$ ]] && {
        local -a roles=(cluster namespace pod container node host application severity message)
        role=${roles[$((role-1))]:-}
    }
    case $role in cluster|namespace|pod|container|node|host|application|severity|message) ;; *) return 1;; esac
    choose 'Choose an observed field' "${SP_FIELDS[@]}" || return
    field=$REPLY
    [[ $field =~ ^[0-9]+$ ]] && field=${SP_FIELDS[$((field-1))]:-}
    splunk_has_field "$field" || { printf 'FIELD_NOT_FOUND\n'; return 1; }
    local value
    if [[ $role == namespace ]]; then
        value=${SENTINEL_NAMESPACE:-}
    else
        prompt "Value for $role (blank leaves the filter unset)" || return
        value=$REPLY
    fi
    [[ ${#value} -le 2048 && $value != *[$'\001'-$'\037'$'\177']* ]] || {
        printf 'INVALID: filter values must be short single-line strings without control characters.\n'; return 1;
    }
    SP_MAP[$role]=$field SP_VALUE[$role]=$value
    SP_SIGNATURE=''
    splunk_generate
    printf 'Mapped %s to observed field %s.\n' "$role" "$field"
}

splunk_validate() {
    local i=$1 role count rc
    splunk_generate || return 1
    [[ $i =~ ^[0-9]+$ && $i -ge 1 && $i -le 23 ]] || return 2
    SP_COUNT[i]=UNKNOWN SP_VALIDATED[i]=NEVER
    for role in "${!SP_MAP[@]}"; do
        if ! splunk_has_field "${SP_MAP[$role]}"; then
            SP_STATUS[i]=FIELD_NOT_FOUND SP_NOTES[i]="Mapped $role field is not in the observed field set"
            return 1
        fi
    done
    if ! splunk_request "${SP_QUERY[i]} | stats count"; then
        SP_STATUS[i]=$SP_REQUEST_STATUS SP_NOTES[i]=$SP_REQUEST_DETAIL
        return 1
    fi
    count=$(printf '%s' "$SP_RESPONSE" | jq -e -r -s '
      [.[] | select(.result? != null) | .result] as $r |
      if ($r|length) == 1 and ($r[0].count|type) == "string" and ($r[0].count|test("^(0|[1-9][0-9]*)$"))
      then $r[0].count else error("count result missing or ambiguous") end' 2>/dev/null)
    rc=$?; SP_RESPONSE=''
    if ((rc != 0)); then
        SP_STATUS[i]=INVALID SP_NOTES[i]='PARSE_ERROR: exactly one non-negative count result is required'
        return 1
    fi
    SP_COUNT[i]=$count SP_VALIDATED[i]=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    if [[ $count == 0 ]]; then SP_STATUS[i]=NO_MATCH; else SP_STATUS[i]=VALIDATED; fi
    SP_NOTES[i]='Observed completed search count for the displayed query and last 15 minutes; keyword matches do not prove coverage or cause.'
    return 0
}

splunk_report() {
    splunk_generate
    local i selected=${1:-all}
    printf 'SPLUNK AUDIT QUERY CATALOG\nCONTEXT %s  NAMESPACE %s\n' "${SENTINEL_CONTEXT:-UNSELECTED}" "${SENTINEL_NAMESPACE:-UNSELECTED}"
    printf 'SOURCE locally generated SPL; last discovery %s; validation is per query\n' "${SP_DISCOVERED_AT:-NEVER}"
    printf 'INDEX %s  SOURCETYPE %s\n' "${SPLUNK_INDEX:-UNSPECIFIED}" "${SPLUNK_SOURCETYPE:-UNSPECIFIED}"
    printf 'No field semantics, event coverage or source matches are inferred.\n'
    for ((i=1; i<=23; i++)); do
        [[ $selected == all || $selected == "$i" ]] || continue
        printf '\nID AUD-K8S-%03d\nCATEGORY %s\nSTATUS %s\n' "$i" "${SP_CATEGORY[i]}" "${SP_STATUS[i]}"
        printf 'QUERY\n%s\nREQUIRED_FIELDS %s\nMATCHES %s\nVALIDATED %s\nNOTES %s\n' \
          "${SP_QUERY[i]}" "$SP_REQUIRED_FIELDS" "${SP_COUNT[i]}" "${SP_VALIDATED[i]}" "${SP_NOTES[i]}"
    done
}

splunk_csv_cell() {
    local value=$1
    value=${value//\"/\"\"}
    printf '"%s"' "$value"
}

splunk_catalog_csv() {
    local i cell first id
    splunk_generate
    printf 'ID,CATEGORY,DESCRIPTION,SPL,REQUIRED_FIELDS,VALIDATION_STATUS,MATCH_COUNT,LAST_VALIDATED,NOTES\n'
    for ((i=1; i<=23; i++)); do
        printf -v id 'AUD-K8S-%03d' "$i"
        first=1
        for cell in "$id" "${SP_CATEGORY[i]}" "${SP_DESCRIPTION[i]}" "${SP_QUERY[i]}" "$SP_REQUIRED_FIELDS" \
          "${SP_STATUS[i]}" "${SP_COUNT[i]}" "${SP_VALIDATED[i]}" "${SP_NOTES[i]}"; do
            ((first)) || printf ','
            splunk_csv_cell "$cell"; first=0
        done
        printf '\n'
    done
}

splunk_export() {
    # Accept a basename only; arbitrary filesystem paths are deliberately absent.
    local name=${1:-splunk-catalog-$(date -u '+%Y%m%dT%H%M%SZ').csv} path
    [[ $name =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*\.csv$ ]] || { printf 'INVALID: export name must be a CSV basename.\n'; return 2; }
    path="$OUTPUT_DIR/$name"
    [[ ! -e $path && ! -L $path ]] || { printf 'Export already exists: %s\n' "$name"; return 1; }
    (set -o noclobber; splunk_catalog_csv | redact > "$path") || return 1
    printf 'EXPORTED %s\n' "$path"
}

splunk_configure() {
    prompt 'Splunk HTTPS management URL (blank keeps current)' || return
    [[ -z $REPLY ]] || SPLUNK_URL=$REPLY
    prompt 'Splunk index (blank keeps current)' || return
    [[ -z $REPLY ]] || SPLUNK_INDEX=$REPLY
    prompt 'Splunk sourcetype (blank leaves unchanged; - clears)' || return
    if [[ $REPLY == - ]]; then SPLUNK_SOURCETYPE=''; elif [[ -n $REPLY ]]; then SPLUNK_SOURCETYPE=$REPLY; fi
    if [[ -t 0 ]]; then
        printf 'Splunk token (silent; blank keeps current): '
        local entered=''
        IFS= read -r -s entered || { printf '\n'; return 1; }
        printf '\n'
        [[ -z $entered ]] || SPLUNK_TOKEN=$entered
        entered=''; export -n SPLUNK_TOKEN 2>/dev/null || :
    fi
    SP_SIGNATURE=''; splunk_generate
}

splunk_diagnostics() {
    splunk_init
    if splunk_connection_check; then
        printf 'SPLUNK CONFIGURED_UNTESTED; HTTPS verification enabled; token held only in memory\n'
    else
        printf 'SPLUNK %s: %s\n' "$SP_REQUEST_STATUS" "$SP_REQUEST_DETAIL"
    fi
    printf 'Offline catalog AVAILABLE (23 categories); connected operations are on demand.\n'
}

splunk_menu() {
    local action selected
    while :; do
        printf '\nSPLUNK AUDIT\n[1] Generate Queries Only  [2] Discover Fields  [3] Validate Generated Query\n'
        printf '[4] Audit Query Catalog  [5] Export SPL Catalog  [6] Configuration  [7] Map Fields\n[8] Help  [0] Back\n'
        prompt 'Selection' || return
        action=$REPLY
        case $action in
          1|4) capture_report 'Splunk Audit Catalog' splunk_report; view_file "$CURRENT_REPORT" 'Splunk Audit Catalog';;
          2) splunk_discover;;
          3)
            splunk_generate
            choose 'Select catalog query to validate' "${SP_CATEGORY[@]:1}" || continue
            selected=$REPLY
            if [[ ! $selected =~ ^[0-9]+$ ]]; then
                local i
                for ((i=1; i<=23; i++)); do [[ ${SP_CATEGORY[i]} == "$selected" ]] && { selected=$i; break; }; done
            fi
            splunk_validate "$selected"
            capture_report 'Splunk Query Validation' splunk_report "$selected"
            view_file "$CURRENT_REPORT" 'Splunk Query Validation';;
          5) splunk_export;;
          6) splunk_configure;;
          7) splunk_map_fields;;
          8) printf '%s\n' 'Purpose: generate 23 keyword triage searches; optional count-only validation.' \
             'Source: user-selected Splunk index/sourcetype; fields come from a bounded observed sample.' \
             'Scope: namespace filtering requires a discovered field mapping; otherwise scope is UNVERIFIED.' \
             'Refresh: manual only; queries search the last 15 minutes, discovery samples 500 events.' \
             'Limitations: keyword matches do not prove cause or coverage; TLS verification cannot be disabled.' \
             'Validation requires a completed export with a numeric count; errors and previews are never VALIDATED.';;
          0|q) return;;
          *) printf 'Choose a listed number.\n';;
        esac
    done
}

# Isolated response fixtures replace only the transport, never contact Splunk,
# and assert that the credential remains absent from process arguments and env.
splunk_self_tests() (
    dev_test_equal() {
        ((DEV_TEST_TOTAL+=1))
        if [[ $2 == "$3" ]]; then ((DEV_TEST_PASSED+=1))
        else ((DEV_TEST_FAILED+=1)); printf 'FAIL %s expected=%s actual=%s\n' "$1" "$2" "$3"; fi
    }
    has jq || { printf 'SKIP: jq unavailable for Splunk response fixtures\n'; return 77; }
    SP_INITIALIZED=0 SP_SIGNATURE='' SP_DISCOVERY_SCOPE=''
    SP_FIELDS=() SP_MAP=() SP_VALUE=()
    SENTINEL_CONTEXT=fixture-context SENTINEL_NAMESPACE=fixture-namespace
    SPLUNK_URL=https://splunk.example.invalid:8089 SPLUNK_INDEX=fixture_index SPLUNK_SOURCETYPE=fixture_type
    SPLUNK_TOKEN='fixture-secret-"quoted"-\token'
    export SPLUNK_TOKEN
    local fixture_body='{"preview":false,"result":{"count":"7"},"lastrow":true}'
    local fixture_http=200 fixture_rc=0 fixture_category
    DEV_TEST_TOTAL=0 DEV_TEST_PASSED=0 DEV_TEST_FAILED=0
    run_bounded() { shift; "$@"; }
    curl() {
        local argument line
        for argument in "$@"; do
            [[ $argument != *fixture-secret* && $argument != --insecure && $argument != --location ]] || return 99
            [[ $argument != exec_mode=* ]] || return 99
        done
        [[ -z $(printenv SPLUNK_TOKEN) ]] || return 99
        IFS= read -r line
        [[ $line == 'header = "Authorization: Bearer '* ]] || return 99
        printf '%s\nSENTINEL_HTTP:%s' "$fixture_body" "$fixture_http"
        return "$fixture_rc"
    }
    splunk_validate 1
    dev_test_equal SPLUNK_COMPLETED_COUNT VALIDATED "${SP_STATUS[1]}"
    dev_test_equal SPLUNK_COUNT_VALUE 7 "${SP_COUNT[1]}"
    fixture_body='{"preview":false,"result":{"count":"0"},"lastrow":true}'
    splunk_validate 1
    dev_test_equal SPLUNK_ZERO_COUNT NO_MATCH "${SP_STATUS[1]}"
    for fixture_body in '{"messages":[{"type":"ERROR","text":"bad query"}]}' \
      '{"preview":false,"result":{"count":"4"},"lastrow":true,"messages":[{"type":"WARN","text":"partial"}]}' \
      '{"preview":true,"result":{"count":"4"},"lastrow":true}' \
      '{"preview":false,"result":{"count":"4"}}' \
      '{"preview":false,"result":{"count":"invalid"},"lastrow":true}' \
      '{"preview":false,"result":{"count":7},"lastrow":true}' \
      '{"preview":false,"result":{"count":"00"},"lastrow":true}' \
      '{"preview":false,"result":{"count":"7"},"lastrow":true,"messages":"ERROR"}' \
      '{"preview":false,"result":{"count":"7"},"lastrow":true,"messages":["ERROR"]}' \
      '{"preview":false,"result":{"count":"7"},"lastrow":true,"messages":[{"type":123,"text":"malformed"}]}' \
      '{"preview":false,"result":{"count":"7"},"lastrow":true,"messages":null}' \
      '{"preview":false,"result":{"count":"4"},"lastrow":true' \
      $'{"preview":false,"result":{"count":"4"},"lastrow":true}\n{"preview":false,"result":{"count":"2"},"lastrow":true}'; do
        splunk_validate 1
        dev_test_equal SPLUNK_REJECT_INVALID INVALID "${SP_STATUS[1]}"
    done
    fixture_body='{"preview":false,"result":{"count":"7"},"lastrow":true}'
    fixture_http=400
    splunk_validate 1
    dev_test_equal SPLUNK_HTTP_BAD_REQUEST INVALID "${SP_STATUS[1]}"
    fixture_http=403
    splunk_validate 1
    dev_test_equal SPLUNK_HTTP_FORBIDDEN SPLUNK_UNAVAILABLE "${SP_STATUS[1]}"
    fixture_http=302
    splunk_validate 1
    dev_test_equal SPLUNK_REDIRECT_REFUSED SPLUNK_UNAVAILABLE "${SP_STATUS[1]}"
    fixture_http=401
    splunk_validate 1
    dev_test_equal SPLUNK_AUTH SPLUNK_UNAVAILABLE "${SP_STATUS[1]}"
    fixture_http=200 fixture_rc=28
    splunk_validate 1
    dev_test_equal SPLUNK_TIMEOUT SPLUNK_UNAVAILABLE "${SP_STATUS[1]}"
    fixture_rc=0
    SPLUNK_TOKEN=$'unsafe\nheader = evil'
    splunk_validate 1
    dev_test_equal SPLUNK_HEADER_INJECTION SPLUNK_UNAVAILABLE "${SP_STATUS[1]}"
    SPLUNK_TOKEN=fixture-secret SPLUNK_URL=https://fixture-secret@splunk.example.invalid
    splunk_validate 1
    dev_test_equal SPLUNK_URL_CREDENTIALS SPLUNK_UNAVAILABLE "${SP_STATUS[1]}"
    SPLUNK_URL=https://splunk.example.invalid
    SP_FIELDS=(observed.namespace)
    SP_MAP[namespace]=observed.namespace SP_VALUE[namespace]=fixture-namespace
    SP_DISCOVERY_SCOPE=$(splunk_scope_signature)
    splunk_generate
    dev_test_equal SPLUNK_OBSERVED_MAPPING 1 "$( [[ ${SP_QUERY[1]} == *observed.namespace* ]] && printf 1 || printf 0 )"
    dev_test_equal SPLUNK_EXACT_NAMESPACE_FILTER 1 "$( [[ ${SP_QUERY[1]} == *" | where 'observed.namespace'=\"fixture-namespace\"" ]] && printf 1 || printf 0 )"
    SP_FIELDS+=(observed.pod)
    SP_MAP[pod]=observed.pod SP_VALUE[pod]='literal*pod'
    splunk_generate
    dev_test_equal SPLUNK_WILDCARD_IS_LITERAL 1 "$( [[ ${SP_QUERY[1]} == *"'observed.pod'=\"literal*pod\"" ]] && printf 1 || printf 0 )"
    SP_VALUE[pod]='x" OR 1=1 | stats count `untrusted`'
    splunk_generate
    dev_test_equal SPLUNK_VALUE_QUOTE_ESCAPED 1 "$( [[ ${SP_QUERY[1]} == *"'observed.pod'=\"x\\\" OR 1=1 | stats count \`untrusted\`\"" ]] && printf 1 || printf 0 )"
    SP_VALUE[pod]=$'line1\nline2'
    splunk_generate
    dev_test_equal SPLUNK_CONTROL_VALUE_REJECT INVALID "${SP_STATUS[1]}"
    SP_VALUE[pod]=somepod
    SP_MAP[pod]=missing.field SP_VALUE[pod]=somepod
    splunk_validate 1
    dev_test_equal SPLUNK_ABSENT_FIELD FIELD_NOT_FOUND "${SP_STATUS[1]}"
    SP_MAP[pod]=observed.pod
    SENTINEL_NAMESPACE=next-namespace
    splunk_generate
    dev_test_equal SPLUNK_SCOPE_SWITCH_RESETS_MAP 0 "${#SP_MAP[@]}"
    SP_MAP=() SP_VALUE=()
    SPLUNK_URL='' SPLUNK_INDEX='' SPLUNK_SOURCETYPE=''
    splunk_generate
    dev_test_equal SPLUNK_OFFLINE_STATUS GENERATED_UNVALIDATED "${SP_STATUS[1]}"
    dev_test_equal SPLUNK_CATEGORY_COUNT 23 "$(( ${#SP_CATEGORY[@]} - 1 ))"
    dev_test_equal SPLUNK_CSV_ROWS 24 "$(splunk_catalog_csv | wc -l)"
    dev_test_equal SPLUNK_CSV_QUOTING '"a,""b"""' "$(splunk_csv_cell 'a,"b"')"
    for ((fixture_category=1; fixture_category<=23; fixture_category++)); do
        dev_test_equal "SPLUNK_OFFLINE_CATEGORY_$fixture_category" GENERATED_UNVALIDATED "${SP_STATUS[fixture_category]}"
    done
    SPLUNK_INDEX='*'
    splunk_generate
    dev_test_equal SPLUNK_INDEX_WILDCARD_REJECT INVALID "${SP_STATUS[1]}"
    dev_test_equal SPLUNK_INVALID_HAS_NO_QUERY '' "${SP_QUERY[1]}"
    SPLUNK_INDEX=fixture_index SPLUNK_SOURCETYPE='" OR index=*'
    splunk_generate
    dev_test_equal SPLUNK_SOURCETYPE_INJECTION_REJECT INVALID "${SP_STATUS[1]}"
    printf 'SPLUNK FIXTURES %s/%s PASS\n' "$DEV_TEST_PASSED" "$DEV_TEST_TOTAL"
    ((DEV_TEST_FAILED == 0))
)


# 15 Shared output, exports and evidence
declare -a REPORT_HISTORY=()
capture_report() {
    local title=$1 text rc path
    shift
    # Failed captures must not leave an older report selected or publish a
    # partial file as a successful observation.
    CURRENT_REPORT= CURRENT_TITLE=
    path=$(mktemp "$RUN_DIR/report.XXXXXXXX") || return 2
    text=$("$@" 2>&1); rc=$?
    if ! { printf '%s | %s\nContext: %s | Namespace: %s\n' "$title" "$(timestamp)" "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE"; printf '%s\n' "$text"; } | redact > "$path"; then
        rm -f -- "$path"
        printf 'Report capture failed; incomplete output discarded\n' >&2
        return 2
    fi
    CURRENT_REPORT=$path CURRENT_TITLE=$title
    REPORT_HISTORY+=("$path")
    if ((${#REPORT_HISTORY[@]}>50)); then
        rm -f -- "${REPORT_HISTORY[0]}"
        REPORT_HISTORY=("${REPORT_HISTORY[@]:1}")
    fi
    log_audit "report=$title exit=$rc"
    return "$rc"
}
json_report_emit() {
    # Machine-readable projection of a captured report for --json. The two
    # capture preamble lines are represented as fields, not repeated inline.
    local file=$1 title=$2 status=$3
    [[ -f $file ]] || return 2
    [[ $status =~ ^[0-9]+$ ]] || status=0
    if ! has jq; then
        printf 'UNAVAILABLE: --json requires jq; no plain-text fallback emitted\n' >&2
        return 2
    fi
    tail -n +3 -- "$file" | redact | jq -Rs \
        --arg application "$APP_NAME" --arg version "$APP_VERSION" --arg title "$title" \
        --arg context "$SENTINEL_CONTEXT" --arg namespace "$SENTINEL_NAMESPACE" \
        --arg collected "$(timestamp)" --argjson status "$status" \
        '{application:$application,version:$version,title:$title,context:$context,namespace:$namespace,collected:$collected,exit_status:$status,lines:split("\n")}'
}
cli_report_output() {
    # Shared noninteractive emitter: default full text, --quiet without the
    # two-line capture preamble, --json as one machine-readable object.
    local title=$1 rc=$2
    if ((JSON_FLAG)); then
        json_report_emit "$CURRENT_REPORT" "$title" "$rc"
    elif ((QUIET_FLAG)); then
        tail -n +3 -- "$CURRENT_REPORT"
    else
        cat -- "$CURRENT_REPORT"
    fi
}
output_center() {
    local action file
    local -a files=()
    while choose 'FULL OUTPUT / LOG CENTER' 'Full current report' 'Raw sanitized cache' Summary Search 'Application audit log' 'Pod logs' Export; do
        action=$REPLY
        case $action in
            'Full current report') [[ -f $CURRENT_REPORT ]] && view_file "$CURRENT_REPORT" "$CURRENT_TITLE";;
            'Raw sanitized cache')
                files=()
                for file in "$CACHE_DIR"/*.json "$CACHE_DIR"/*.txt; do [[ -f $file ]] && files+=("$file"); done
                choose 'Select a cached safe projection (raw credentials are never retained)' "${files[@]}" && view_file "$REPLY" 'Raw sanitized projection';;
            Summary) show_report Summary summary_report;;
            Search) global_search;;
            'Application audit log') view_file "$RUN_DIR/application.log" 'Application audit';;
            'Pod logs') logs_capture; [[ -f $CURRENT_REPORT ]] && view_file "$CURRENT_REPORT" 'Pod logs';;
            Export) export_center;;
        esac
    done
}
evidence_metadata() {
    local category=$1 status=$2
    scope_report
    printf 'Collector category: %s\nCollector status: %s\n\n' "$category" "$status"
}
evidence_section() {
    local directory=$1 filename=$2 category=$3 text rc status
    shift 3
    text=$("$@" 2>&1); rc=$?
    status=COMPLETED_WITH_PER_COLLECTOR_STATUS
    ((rc==0)) || status="PARTIAL_EXIT_$rc"
    { evidence_metadata "$category" "$status"; printf '%s\n' "$text"; } | redact > "$directory/$filename"
    printf '%s\t%s\n' "$filename" "$status" >> "$directory/collection.tsv"
}
evidence_manifest() {
    local directory=$1 file
    if has sha256sum; then
        (cd -- "$directory" || exit; for file in *.txt *.csv *.tsv 15_LOGS/*.txt; do [[ -f $file ]] && sha256sum -- "$file"; done) > "$directory/MANIFEST.sha256"
        printf 'Evidence integrity manifest generated: YES\n'
    else printf 'Evidence integrity manifest: UNAVAILABLE (sha256sum not installed)\n'; fi
}
logs_capture() {
    local destination=${1:-$RUN_DIR} pod=${2:-} container tail=500 since=1h previous=0 file text rc
    local -a containers=() args=()
    [[ -n $pod ]] || { select_pod || return 2; pod=$SELECTED_POD; }
    collect_pods
    if has jq && [[ -f $CACHE_DIR/pods.json ]]; then
        mapfile -t containers < <(jq -r --arg p "$pod" '.items[]|select(.metadata.name==$p)|(.spec.containers[],.spec.initContainers[]?,.spec.ephemeralContainers[]?)|.name' "$CACHE_DIR/pods.json")
    else printf 'UNAVAILABLE: jq required for discovered container selection\n'; return 2; fi
    choose "Container in $pod" "${containers[@]}" || return 2; container=$REPLY
    choose 'Log stream' current previous || return 2
    [[ $REPLY == previous ]] && previous=1
    prompt 'Tail lines [500], or type FULL LOG (may be large; transfer remains time bounded):' || return 2
    if [[ $REPLY == 'FULL LOG' ]]; then tail=-1
    elif [[ -n $REPLY ]]; then [[ $REPLY =~ ^[1-9][0-9]{0,6}$ ]] || return 2; tail=$REPLY; fi
    prompt 'Since duration [1h; e.g. 30m, 2h, 24h; FULL for no time limit]:' || return 2
    [[ -n $REPLY ]] && since=$REPLY
    [[ $since == FULL || $since =~ ^[1-9][0-9]{0,5}(s|m|h)$ ]] || return 2
    args=(logs "$pod" -c "$container" "--tail=$tail" --timestamps=true)
    [[ $since != FULL ]] && args+=("--since=$since")
    ((previous)) && args+=(--previous=true)
    [[ $destination == "$RUN_DIR" || $destination == "$OUTPUT_DIR/"* ]] || return 2
    file=$(mktemp "$destination/$(safe_id "$pod-$container").XXXXXXXX.txt") || return 2
    # Stream straight through redaction: unlimited logs never accumulate in memory.
    evidence_metadata 'pod logs' "REQUESTED tail=$tail since=$since previous=$previous" > "$file"
    kctl_ns "${args[@]}" 2>&1 | redact >> "$file"; rc=${PIPESTATUS[0]}
    printf '\nCollector exit: %s; status: %s\n' "$rc" "$(classify_error "$rc" "$(tail -n 3 "$file")")" >> "$file"
    printf 'Log evidence: %s\n' "$file"
    CURRENT_REPORT=$file CURRENT_TITLE='Redacted pod logs'
    log_audit "logs pod=$pod container=$container exit=$rc"
    return "$rc"
}
executive_report() {
    printf 'EXECUTIVE SUMMARY\n'
    scope_report
    printf '\nCollection time: %s\nGitOps: %s\nCertificate capability: %s\nMetrics: %s\n' "$(timestamp)" "$GITOPS_STATUS" "$CERT_STATUS" "$METRICS_STATUS"
    printf 'Evidence completeness: see collection.tsv and per-source statuses; denied/unavailable sources are unknown.\n'
    health_report
}
evidence_menu() {
    local selection id
    choose 'INCIDENT EVIDENCE COLLECTOR' 'Quick Evidence' 'Full Namespace Evidence' 'Pod/Workload Evidence' 'Network/Service Evidence' 'GitOps Evidence' 'Certificate/TLS Evidence' 'Resource/Capacity Evidence' 'Event Timeline' 'Complete Incident Bundle' || return
    case $REPLY in Quick*) selection=1;; Full*) selection=2;; Pod*) selection=3;; Network*) selection=4;; GitOps*) selection=5;; Certificate*) selection=6;; Resource*) selection=7;; Event*) selection=8;; Complete*) selection=9;; esac
    prompt 'Incident / Change ID:' || return; id=$REPLY
    [[ $selection != 3 ]] || select_pod || return
    evidence_create "$id" "$selection"
    prompt 'Enter to return:' || :
}
export_center() {
    local selected
    choose 'EXPORT & EVIDENCE CENTER' 'Current complete report' 'Health report' 'Resource snapshot' 'GitOps snapshot' 'Certificate inventory' 'Splunk catalog' 'Incident evidence' 'Create snapshot' 'Compare snapshots' || return
    selected=$REPLY
    case $selected in
        'Current complete report') [[ -f $CURRENT_REPORT ]] || { printf 'No report yet\n'; return; };;
        'Health report') capture_report Health health_report;;
        'Resource snapshot') capture_report Resources resources_report;;
        'GitOps snapshot') capture_report GitOps gitops_report;;
        'Certificate inventory') capture_report Certificates certificates_report;;
        'Splunk catalog') splunk_export; return;;
        'Incident evidence') evidence_menu; return;;
        'Create snapshot') snapshot_create; return;;
        'Compare snapshots') snapshot_compare; return;;
    esac
    choose 'Export format' TXT CSV JSON || return
    export_file "$CURRENT_REPORT" "$CURRENT_TITLE" "${REPLY,,}"
}

# 17 Stable terminal painting. The frame/menu is drawn once per screen; only
# changed rows in the dynamic region are replaced between refreshes.
declare -a UI_PREVIOUS=()
ui_enter() {
    if [[ -t 1 && ${TERM:-dumb} != dumb ]]; then printf '\033[?1049h\033[?25l'; UI_ACTIVE=1; fi
    terminal_size
}
ui_leave() {
    if ((UI_ACTIVE)); then printf '\033[0m\033[?25h\033[?1049l'; UI_ACTIVE=0; fi
    UI_PREVIOUS=()
}
filter_sort_report() {
    local source=$1 destination=$2
    # The resource engine receives SORT_BY/FILTER; this generic view additionally
    # supports literal matches in every projected report without API requests.
    if [[ -z $FILTER ]]; then cat -- "$source" > "$destination"
    elif has grep; then
        printf '%s\n' "FILTER regex: $FILTER" > "$destination"
        grep -E -- "$FILTER" "$source" >> "$destination"; local rc=$?
        ((rc==2)) && printf 'PARSE_ERROR: invalid regular expression\n' >> "$destination"
    else printf 'UNAVAILABLE: regex filtering requires grep\n' > "$destination"; fi
}
live_resources() {
    local key paused=0 repaint=1 filtered width=$UI_COLS
    local -a intervals=(0 2 5 10 15 30 60)
    filtered=$(mktemp "$RUN_DIR/live.XXXXXXXX") || return
    ui_enter
    paint_frame 'LIVE RESOURCE TRACKER' '[p] pause [r] refresh [+/-] interval [/] filter [s] sort [i] inspect [e] export [f] full [q] back'
    while :; do
        terminal_size
        if [[ $width != "$UI_COLS" ]]; then width=$UI_COLS; UI_PREVIOUS=(); paint_frame 'LIVE RESOURCE TRACKER' '[p] pause [r] refresh [+/-] rate [/] filter [s] sort [i] inspect [e] export [f] full [q] back'; fi
        if ((repaint)); then
            RESOURCE_FILTER=$FILTER RESOURCE_SORT=$SORT_BY
            capture_report 'Live Resources' resources_report
            cat -- "$CURRENT_REPORT" > "$filtered"
            paint_report "$filtered"
            FORCE_REFRESH=0 repaint=0
        fi
        key=
        if ((paused || REFRESH==0)); then IFS= read -r -s -n 1 key || break
        elif ! IFS= read -r -s -n 1 -t "$REFRESH" key; then
            [[ -t 0 ]] || break
            repaint=1; continue
        fi
        case $key in
            q|0) break;;
            p) paused=$((1-paused)); paint_line 4 "PAUSED=$paused | Pods cache age $(cache_age pods)s";;
            r) FORCE_REFRESH=1 repaint=1;;
            +) case $REFRESH in 0|60) REFRESH=30;;30) REFRESH=15;;15) REFRESH=10;;10) REFRESH=5;;5|2) REFRESH=2;;esac; repaint=1;;
            -) case $REFRESH in 2) REFRESH=5;;5) REFRESH=10;;10) REFRESH=15;;15) REFRESH=30;;30) REFRESH=60;;60|0) REFRESH=0;;esac; repaint=1;;
            /) ui_leave; prompt 'Filter [regex; empty clears]:' && FILTER=$REPLY; ui_enter; repaint=1;;
            s) ui_leave; choose 'Sort by' name cpu memory restarts age status node && SORT_BY=$REPLY; ui_enter; repaint=1;;
            f) ui_leave; view_file "$CURRENT_REPORT" 'Full resource output'; ui_enter; repaint=1;;
            e) ui_leave; export_file "$CURRENT_REPORT" resources txt; prompt 'Enter:' || :; ui_enter; repaint=1;;
            i) ui_leave; component_triage; ui_enter; repaint=1;;
        esac
        paint_frame 'LIVE RESOURCE TRACKER' '[p] pause [r] refresh [+/-] interval [/] filter [s] sort [i] inspect [e] export [f] full [q] back'
    done
    ui_leave
}
component_triage() {
    local action
    select_pod || return
    while choose "TRIAGE: $SELECTED_POD" Inspect Events Resources Containers Images Services Storage GitOps Certificates Logs Evidence; do
        action=$REPLY
        case $action in
            Inspect) show_report 'Pod inspector' inspector_report "$SELECTED_POD";;
            Events) show_report 'Related events and relationships' inspector_report "$SELECTED_POD";;
            Resources|Containers) show_report 'Container resources' containers_report "$SELECTED_POD";;
            Images) show_report 'Runtime images' images_report;;
            Services) show_report 'Service relationships' inspector_report "$SELECTED_POD";;
            Storage) show_report 'Storage' storage_report;;
            GitOps) show_report 'Deployment validation' deployment_chain_report "$SELECTED_POD";;
            Certificates) show_report 'Certificate references' cert_mounts_report;;
            Logs) logs_capture "$RUN_DIR" "$SELECTED_POD"; [[ -f $CURRENT_REPORT ]] && view_file "$CURRENT_REPORT" 'Logs';;
            Evidence) prompt 'Incident / Change ID:' && evidence_create "$REPLY" 3;;
        esac
    done
}
module_help() {
    cat <<'HELP'
OPERATIONS HELP
Scope: every namespaced read is locked to the displayed context and namespace.
Sources: Kubernetes resource APIs; metrics.k8s.io; Flux/cert-manager when installed.
Refresh: pods/metrics 5s, events 10s, Flux/Helm 15s, certificates 60s, discovery 300s.
Live keys: p pause, r force, +/- rate, / regex filter, s sort, i triage, e export, f full.
Tables hide lower-priority columns at narrow widths. Full output wraps and pages all data.
Readiness counts observed OK/WARN/FAIL/UNKNOWN findings; it is not a health percentage.
Triage: --triage is a concise namespace incident scope; --triage-workload NAME
correlates one workload with pods, events, services, storage and GitOps.
--capabilities shows what this environment supports; --doctor diagnoses the tool itself.
--json emits machine-readable report objects (requires jq); --quiet trims guidance.
Missing permissions, API errors and missing metrics are explicit, never interpreted as zero.
GitOps: generation/revision differences can be reconciliation lag. Desired manifests are
not downloaded; runtime variance is not proof of Git desired-state drift.
Certificates: only public certificate metadata is parsed; mount configuration does not
prove that a file exists in a running container. TLS probes are explicit and bounded.
Splunk: offline keywords are GENERATED_UNVALIDATED. Fields must be discovered before use.
Evidence: local private sanitized projections, opt-in bounded logs, SHA256 when installed.
Snapshots are sequential observations, not a transactionally consistent cluster state.
Node requests/limits represent this namespace only; total node reservations are unknown.
No application mode runs arbitrary shell commands or arbitrary kubectl arguments.
HELP
}


# ==============================================================================
# DevOpsSentinel FINAL overlay: hardened HOME-local runtime, expanded read-only
# operations, unified rendering, exports and evidence. Later definitions
# intentionally replace the smaller KubeOps defaults while preserving its
# collectors, parsers, redaction, bounded execution and report engines.
# ==============================================================================

SNTL_HOME="${SNTL_HOME:-${OUTPUT_DIR:-${HOME}/.devopssentinel}}"
SNTL_CACHE_ROOT=''
SNTL_RUNTIME_DIR=''
SNTL_EXPORT_DIR=''
SNTL_EVIDENCE_DIR=''
SNTL_HISTORY_DIR=''
SNTL_REPORT_DIR=''
SNTL_BACKUP_DIR=''
SNTL_LOG_DIR=''
CERT_ATTENTION_DAYS="${CERT_ATTENTION_DAYS:-60}"
EXPLAIN_TOPIC='overview'
VALIDATION_LIVE=0

home_safe_path() {
    local path=$1 home
    home=$(cd -- "$HOME" 2>/dev/null && pwd -P) || return 1
    [[ $path == "$home" || $path == "$home/"* ]]
}

init_runtime() {
    local root
    umask 077
    root=${OUTPUT_DIR:-${HOME}/.devopssentinel}
    case $root in /*) ;; *) root="$HOME/$root";; esac
    [[ $root != *$'\n'* && $root != *$'\r'* && $root != *'/../'* ]] || { printf 'Invalid runtime root\n' >&2; return 2; }
    mkdir -p -- "$root" || return 2
    root=$(cd -- "$root" 2>/dev/null && pwd -P) || return 2
    home_safe_path "$root" || { printf 'Runtime root must remain under HOME: %s\n' "$HOME" >&2; return 2; }
    [[ ! -L $root ]] || { printf 'Runtime root may not be a symlink\n' >&2; return 2; }
    SNTL_HOME=$root OUTPUT_DIR=$root
    SNTL_CACHE_ROOT="$root/cache"
    SNTL_RUNTIME_DIR="$root/runtime"
    SNTL_EXPORT_DIR="$root/exports"
    SNTL_EVIDENCE_DIR="$root/evidence"
    SNTL_HISTORY_DIR="$root/history"
    SNTL_REPORT_DIR="$root/reports"
    SNTL_BACKUP_DIR="$root/backups"
    SNTL_LOG_DIR="$root/logs"
    mkdir -p -- "$SNTL_CACHE_ROOT" "$SNTL_RUNTIME_DIR" "$SNTL_EXPORT_DIR" "$SNTL_EVIDENCE_DIR" \
        "$SNTL_HISTORY_DIR" "$SNTL_REPORT_DIR" "$SNTL_BACKUP_DIR" "$SNTL_LOG_DIR" || return 2
    chmod 700 -- "$root" "$SNTL_CACHE_ROOT" "$SNTL_RUNTIME_DIR" "$SNTL_EXPORT_DIR" "$SNTL_EVIDENCE_DIR" \
        "$SNTL_HISTORY_DIR" "$SNTL_REPORT_DIR" "$SNTL_BACKUP_DIR" "$SNTL_LOG_DIR" 2>/dev/null || :
    chmod g-s -- "$root" "$SNTL_CACHE_ROOT" "$SNTL_RUNTIME_DIR" "$SNTL_EXPORT_DIR" "$SNTL_EVIDENCE_DIR" \
        "$SNTL_HISTORY_DIR" "$SNTL_REPORT_DIR" "$SNTL_BACKUP_DIR" "$SNTL_LOG_DIR" 2>/dev/null || :
    RUN_DIR=$(mktemp -d "$SNTL_RUNTIME_DIR/session.XXXXXXXX") || return 2
    chmod 700 "$RUN_DIR" 2>/dev/null || :
    CACHE_DIR="$RUN_DIR/cache"
    mkdir -p -- "$CACHE_DIR" || return 2
    printf '{"items":[]}\n' > "$RUN_DIR/empty.json"
    : > "$RUN_DIR/findings.tsv"
    : > "$RUN_DIR/application.log"
    # Directories need search permission; chmod 600 on the cache directory
    # silently prevented every collector from writing as a normal user.
    chmod 700 "$CACHE_DIR" || return 2
    chmod 600 "$RUN_DIR/empty.json" "$RUN_DIR/findings.tsv" "$RUN_DIR/application.log" || return 2
    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    trap terminal_size WINCH
    [[ -t 0 && -t 1 ]] && INTERACTIVE=1 || INTERACTIVE=0
    if [[ -t 0 ]] && has stty; then UI_STTY=$(stty -g 2>/dev/null); fi
    log_audit 'session started final-read-only-build'
}

dependency_detect() {
    local cmd
    DEPENDENCIES=()
    for cmd in kubectl helm flux jq openssl curl timeout sha256sum column tput base64 awk sed grep sort uniq date less \
        psql kafka-topics.sh kafka-topics kafka-consumer-groups.sh kafka-consumer-groups ip ss getent nc flock stat id uname file diff; do
        if has "$cmd"; then DEPENDENCIES[$cmd]=AVAILABLE; else DEPENDENCIES[$cmd]='NOT INSTALLED'; fi
    done
}

allowed_resource() {
    local scope=$1 resources=$2 res
    local -a entries
    IFS=, read -r -a entries <<< "$resources"
    for res in "${entries[@]}"; do
        case "$scope:$res" in
            ns:pods|ns:pod|ns:deployments|ns:deployment|ns:statefulsets|ns:statefulset|ns:daemonsets|ns:daemonset|ns:replicasets|ns:replicaset|ns:jobs|ns:job|ns:cronjobs|ns:cronjob|ns:services|ns:service|ns:endpoints|ns:endpointslices*|ns:persistentvolumeclaims|ns:pvc|ns:events|ns:ingresses*|ns:configmaps|ns:configmap|ns:secrets|ns:secret|ns:serviceaccounts|ns:serviceaccount|ns:networkpolicies*|ns:horizontalpodautoscalers*|ns:poddisruptionbudgets*|ns:pods.metrics.k8s.io|ns:gitrepositories.source.toolkit.fluxcd.io|ns:ocirepositories.source.toolkit.fluxcd.io|ns:helmrepositories.source.toolkit.fluxcd.io|ns:buckets.source.toolkit.fluxcd.io|ns:kustomizations.kustomize.toolkit.fluxcd.io|ns:helmreleases.helm.toolkit.fluxcd.io|ns:helmcharts.source.toolkit.fluxcd.io|ns:certificates.cert-manager.io|ns:certificaterequests.cert-manager.io|ns:issuers.cert-manager.io|ns:orders.acme.cert-manager.io|ns:challenges.acme.cert-manager.io) ;;
            cluster:namespaces|cluster:namespace|cluster:nodes|cluster:node|cluster:persistentvolumes|cluster:pv|cluster:storageclasses*|cluster:csidrivers*|cluster:csinodes*|cluster:volumeattachments*|cluster:customresourcedefinitions*|cluster:crds|cluster:clusterissuers.cert-manager.io|cluster:validatingwebhookconfigurations*|cluster:mutatingwebhookconfigurations*) ;;
            *) printf 'RESOURCE_REJECTED: %s/%s\n' "$scope" "$res" >&2; return 2;;
        esac
    done
}


_export_file_core() {
    local file=$1 label=${2:-report} format=${3:-txt} path line text count
    [[ -f $file && $file == "$RUN_DIR/"* ]] || { printf 'Export source unavailable\n'; return 2; }
    case $format in txt|csv|json|ndjson|prometheus) ;; *) printf 'Unsupported export format: %s\n' "$format"; return 2;; esac
    path=$(mktemp "$SNTL_EXPORT_DIR/$(safe_id "$label")-$(date -u +%Y%m%dT%H%M%SZ).XXXXXX.$format") || return 2
    case $format in
        txt) redact < "$file" > "$path";;
        csv)
            printf 'LINE,TEXT\n' > "$path"; count=0
            while IFS= read -r line || [[ -n $line ]]; do ((count+=1)); text=${line//\"/\"\"}; printf '%s,"%s"\n' "$count" "$text"; done < <(redact < "$file") >> "$path";;
        json)
            has jq || { rm -f -- "$path"; printf 'UNAVAILABLE: JSON export requires jq\n'; return 2; }
            redact < "$file" | jq -Rs --arg title "$label" --arg context "$SENTINEL_CONTEXT" --arg namespace "$SENTINEL_NAMESPACE" --arg collected "$(timestamp)" '{title:$title,context:$context,namespace:$namespace,collected:$collected,lines:(split("\n")[:-1])}' > "$path";;
        ndjson)
            has jq || { rm -f -- "$path"; printf 'UNAVAILABLE: NDJSON export requires jq\n'; return 2; }
            count=0; while IFS= read -r line || [[ -n $line ]]; do ((count+=1)); printf '%s\n' "$line" | jq -Rc --argjson line_no "$count" --arg title "$label" '{line:$line_no,title:$title,text:.}'; done < <(redact < "$file") > "$path";;
        prometheus)
            count=$(redact < "$file" | wc -l | awk '{print $1}')
            printf '# HELP devopssentinel_report_lines Number of lines in the exported report.\n# TYPE devopssentinel_report_lines gauge\n' > "$path"
            printf 'devopssentinel_report_lines{report="%s",context="%s",namespace="%s"} %s\n' "$(safe_id "$label")" "$(safe_id "$SENTINEL_CONTEXT")" "$(safe_id "$SENTINEL_NAMESPACE")" "$count" >> "$path";;
    esac
    chmod 600 "$path" 2>/dev/null || :
    printf 'EXPORTED %s\n' "$path"
    log_audit "export=$path status=OK format=$format"
}

snapshot_create() {
    local target
    target="$SNTL_REPORT_DIR/snapshot-$(date -u +%Y%m%dT%H%M%SZ)-$(safe_id "$SENTINEL_NAMESPACE").txt"
    {
        scope_report
        printf '\nSnapshot counts, resource states, images and allocation\n'
        summary_report; resources_report; images_report; network_report; storage_report
        gitops_report; helm_report; certificates_report; events_report warnings
    } | redact > "$target"
    chmod 600 "$target" 2>/dev/null || :
    printf 'Snapshot: %s\n' "$target"
    log_audit "snapshot=$target"
}

snapshot_compare() {
    local before after file
    local -a snapshots=()
    for file in "$SNTL_REPORT_DIR"/snapshot-*.txt; do [[ -f $file && ! -L $file ]] && snapshots+=("$file"); done
    ((${#snapshots[@]}>1)) || { printf 'Create at least two snapshots first.\n'; return; }
    choose 'BEFORE snapshot' "${snapshots[@]}" || return; before=$REPLY
    choose 'AFTER snapshot' "${snapshots[@]}" || return; after=$REPLY
    if has diff; then show_report 'BEFORE / AFTER / CHANGE' diff -u -- "$before" "$after"; else printf 'UNAVAILABLE: diff not installed\n'; fi
}

_evidence_write() {
    local path=$1 title=$2; shift 2
    local rc text
    text=$("$@" 2>&1); rc=$?
    { printf '%s\nCollected: %s\nContext: %s\nNamespace: %s\nStatus: %s\n\n' "$title" "$(timestamp)" "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE" "$(classify_error "$rc" "$text")"; printf '%s\n' "$text"; } | redact > "$path"
    chmod 600 "$path" 2>/dev/null || :
    return 0
}

evidence_create() {
    local id=$1 mode=${2:-9} directory stamp selected=${SELECTED_POD:-} file
    id=$(safe_id "$id"); stamp=$(date -u +%Y%m%dT%H%M%SZ)
    directory="$SNTL_EVIDENCE_DIR/${stamp}_$(safe_id "$SENTINEL_NAMESPACE")_${id}"
    mkdir -p -- "$directory"/{pods,events,services,storage,gitops,certificates,network,logs} || return 2
    chmod 700 "$directory" "$directory"/* 2>/dev/null || :
    printf 'Collecting evidence in %s\n' "$directory" >&2
    _evidence_write "$directory/summary.txt" 'DEVOPSSENTINEL INCIDENT SUMMARY' executive_report
    _evidence_write "$directory/pods/inventory.txt" 'PODS / RESOURCES' resources_report
    _evidence_write "$directory/pods/workloads.txt" 'WORKLOADS' workloads_report
    _evidence_write "$directory/events/events.txt" 'EVENT RADAR' events_report all
    _evidence_write "$directory/services/topology.txt" 'SERVICES / ENDPOINTS' network_report
    _evidence_write "$directory/storage/storage.txt" 'STORAGE' storage_report
    _evidence_write "$directory/gitops/flux.txt" 'GITOPS / FLUX' gitops_report
    _evidence_write "$directory/gitops/helm.txt" 'HELM' helm_report
    _evidence_write "$directory/certificates/inventory.txt" 'CERTIFICATES' certificates_report
    _evidence_write "$directory/network/host.txt" 'HOST NETWORK' host_network_report
    if [[ -n $selected ]]; then _evidence_write "$directory/pods/selected-pod.txt" "POD $selected" pod_forensics_report "$selected"; fi
    if has jq; then
        redact < "$RUN_DIR/findings.tsv" | jq -Rsc 'split("\n") | map(split("\t") | select(length>=5) | {severity:.[0],domain:.[1],resource:.[2],finding:.[3],evidence:.[4]})' > "$directory/findings.json" 2>/dev/null || printf '[]\n' > "$directory/findings.json"
    else printf '[]\n' > "$directory/findings.json"; fi
    {
        printf 'DevOpsSentinel evidence manifest\nVersion: %s\nCollected: %s\nContext: %s\nNamespace: %s\nMode: SUPERVISION [READ ONLY]\n' "$APP_VERSION" "$(timestamp)" "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE"
        printf 'Collection is sequential and may be partial when RBAC/API/tooling is unavailable.\nNo Kubernetes Secret payload, private key, kubeconfig credential, Git mutation, Flux reconcile or cluster write is intentionally collected/performed.\n'
    } > "$directory/manifest.txt"
    if ((INTERACTIVE)) && [[ $mode == 3 || $mode == 9 ]]; then
        prompt 'Capture selected bounded/redacted pod logs? [y/N]:' && [[ $REPLY == y || $REPLY == Y ]] && logs_capture "$directory/logs" "$selected" || :
    fi
    if has sha256sum; then
        (cd -- "$directory" && find . -type f ! -name checksums.sha256 -print0 | sort -z | xargs -0 sha256sum) > "$directory/checksums.sha256" 2>/dev/null || :
    else printf 'sha256sum unavailable\n' > "$directory/checksums.sha256"; fi
    find "$directory" -type f -exec chmod 600 {} + 2>/dev/null || :
    log_audit "evidence=$directory mode=$mode status=COMPLETE_WITH_PARTIAL_TOLERANCE"
    printf 'Evidence bundle: %s\n' "$directory"
}

# ==============================================================================
# Resource, dependency, GitOps, certificate, network, storage and ETDP engines.
# ==============================================================================

resource_catalog() {
    cat <<'CAT'
Pod|pods|ns
Deployment|deployments|ns
StatefulSet|statefulsets|ns
DaemonSet|daemonsets|ns
ReplicaSet|replicasets|ns
Job|jobs|ns
CronJob|cronjobs|ns
Service|services|ns
EndpointSlice|endpointslices.discovery.k8s.io|ns
ConfigMap|configmaps|ns
Secret|secrets|ns
ServiceAccount|serviceaccounts|ns
PVC|persistentvolumeclaims|ns
PV|persistentvolumes|cluster
StorageClass|storageclasses.storage.k8s.io|cluster
Ingress|ingresses.networking.k8s.io|ns
NetworkPolicy|networkpolicies.networking.k8s.io|ns
HPA|horizontalpodautoscalers.autoscaling|ns
PDB|poddisruptionbudgets.policy|ns
Node|nodes|cluster
Namespace|namespaces|cluster
Certificate|certificates.cert-manager.io|ns
CertificateRequest|certificaterequests.cert-manager.io|ns
Issuer|issuers.cert-manager.io|ns
ClusterIssuer|clusterissuers.cert-manager.io|cluster
GitRepository|gitrepositories.source.toolkit.fluxcd.io|ns
Kustomization|kustomizations.kustomize.toolkit.fluxcd.io|ns
HelmRelease|helmreleases.helm.toolkit.fluxcd.io|ns
CAT
}

resource_lookup() {
    local wanted=${1,,} row kind api scope
    while IFS='|' read -r kind api scope; do
        if [[ ${kind,,} == "$wanted" || ${api,,} == "$wanted" ]]; then printf '%s|%s|%s\n' "$kind" "$api" "$scope"; return 0; fi
    done < <(resource_catalog)
    return 1
}

resource_names() {
    local scope=$1 api=$2
    if [[ $scope == ns ]]; then kctl_ns get "$api" -o 'jsonpath={range .items[*]}{.metadata.name}{"\n"}{end}'
    else kctl_cluster get "$api" -o 'jsonpath={range .items[*]}{.metadata.name}{"\n"}{end}'; fi
}

resource_select_name() {
    local scope=$1 api=$2 input pattern item
    local -a names=() matches=()
    mapfile -t names < <(resource_names "$scope" "$api" 2>/dev/null | sed '/^$/d' | sort -u)
    ((${#names[@]})) || { printf 'No resources visible for %s\n' "$api" >&2; return 1; }
    printf '\nRESOURCE SELECTION (%s)\n' "$api"
    local i=0; for item in "${names[@]}"; do ((i+=1)); printf '[%3d] %s\n' "$i" "$item"; done
    prompt 'Select number, exact/partial name, or /regex (0=back):' || return 1; input=$REPLY
    [[ $input != 0 && $input != q ]] || return 1
    if [[ $input =~ ^[0-9]+$ ]] && ((10#$input>=1 && 10#$input<=${#names[@]})); then REPLY=${names[$((10#$input-1))]}; return 0; fi
    if [[ $input == /* ]]; then
        pattern=${input#/}
        while IFS= read -r item; do [[ $item =~ $pattern ]] && matches+=("$item"); done < <(printf '%s\n' "${names[@]}") 2>/dev/null || { printf 'Invalid regex\n'; return 1; }
    else
        for item in "${names[@]}"; do [[ ${item,,} == *"${input,,}"* ]] && matches+=("$item"); done
    fi
    ((${#matches[@]})) || { printf 'No match\n'; return 1; }
    if ((${#matches[@]}==1)); then REPLY=${matches[0]}; return 0; fi
    choose 'MATCHES' "${matches[@]}" || return 1
}

resource_detail_safe() {
    local kind=$1 api=$2 scope=$3 name=$4 raw rc
    render_header "RESOURCE: $kind/$name"
    if [[ $kind == Secret ]]; then
        printf 'Secret payload display is prohibited. Metadata only.\n'
        if [[ $scope == ns ]]; then
            kctl_ns get secrets -o 'go-template={{range .items}}{{if eq .metadata.name "'"$name"'"}}{{.metadata.name}}{{"\t"}}{{.type}}{{"\t"}}{{.metadata.creationTimestamp}}{{"\t"}}{{range $k,$v := .data}}{{$k}}{{" "}}{{end}}{{"\n"}}{{end}}{{end}}' | redact
        fi
        resource_consumers Secret "$SENTINEL_NAMESPACE" "$name"
        return
    fi
    if [[ $scope == ns ]]; then raw=$(kctl_ns get "$api" "$name" -o json 2>&1); rc=$?; else raw=$(kctl_cluster get "$api" "$name" -o json 2>&1); rc=$?; fi
    if ((rc!=0)); then printf '%s\n' "$raw" | redact; return "$rc"; fi
    if has jq; then
        printf '%s\n' "$raw" | jq '
          del(.metadata.managedFields,.data,.stringData) |
          walk(if type=="object" and has("name") and has("value") then del(.value) else . end) |
          walk(if type=="object" then with_entries(select(.key|test("password|passwd|token|secret_access_key|client_secret|private[_-]?key";"i")|not)) else . end)' | json_sanitize
    else printf '%s\n' "$raw" | redact; fi
    unset raw
    printf '\nDEPENDENCIES / CONSUMERS\n'
    resource_dependencies "$kind" "$SENTINEL_NAMESPACE" "$name" || :
}

resource_explorer_menu() {
    local kind api scope row
    local -a choices=()
    while IFS='|' read -r kind api scope; do choices+=("$kind"); done < <(resource_catalog)
    while choose 'KUBERNETES RESOURCE EXPLORER' "${choices[@]}" 'Back'; do
        kind=$REPLY; [[ $kind == Back ]] && return
        row=$(resource_lookup "$kind") || continue
        IFS='|' read -r kind api scope <<< "$row"
        resource_select_name "$scope" "$api" || continue
        show_report "$kind/$REPLY" resource_detail_safe "$kind" "$api" "$scope" "$REPLY"
    done
}

_pod_top_owner_jq='def ctrl: ([.metadata.ownerReferences[]? | select(.controller==true)][0] // .metadata.ownerReferences[0]);'

resource_dependencies() {
    local type=${1:-} namespace=${2:-$SENTINEL_NAMESPACE} name=${3:-}
    [[ -n $type && -n $name ]] || { printf 'Usage: resource_dependencies TYPE NAMESPACE NAME\n'; return 2; }
    collect_pods; collect_workloads; collect_network; collect_storage; gitops_collect; cert_manager_collect
    has jq || { printf 'UNAVAILABLE: jq required for dependency graph.\n'; return 0; }
    local pods workloads services slices ingresses pvcs
    pods=$(json_cache_path pods); workloads=$(json_cache_path workloads); services=$(json_cache_path services)
    slices=$(json_cache_path endpointslices); ingresses=$(json_cache_path ingresses); pvcs=$(json_cache_path pvcs)
    printf 'DEPENDENCY GRAPH | %s/%s | namespace=%s\n' "$type" "$name" "$namespace"
    case ${type,,} in
        pod)
            jq -r --arg n "$name" '
              .items[]|select(.metadata.name==$n) as $p |
              "Pod/"+$p.metadata.name,
              "├── Node: "+($p.spec.nodeName // "UNSCHEDULED"),
              "├── ServiceAccount: "+($p.spec.serviceAccountName // "default"),
              ($p.spec.containers[]? | "├── Container: "+.name+" -> Image: "+.image),
              ($p.spec.initContainers[]? | "├── InitContainer: "+.name+" -> Image: "+.image),
              ($p.spec.volumes[]? | if .secret.secretName then "├── SecretRef/"+.secret.secretName elif .configMap.name then "├── ConfigMap: "+.configMap.name elif .persistentVolumeClaim.claimName then "├── PVC: "+.persistentVolumeClaim.claimName else empty end)' "$pods"
            ;;
        deployment|statefulset|daemonset|replicaset|job|cronjob)
            jq -r --arg kind "$type" --arg n "$name" --slurpfile w "$workloads" '
              def ctrl: ([.metadata.ownerReferences[]? | select(.controller==true)][0] // .metadata.ownerReferences[0]);
              .items[] | . as $p | ctrl as $o |
              ([$w[0].items[] | select(.kind==$o.kind and .metadata.name==$o.name)][0]) as $direct |
              (if $o.kind=="ReplicaSet" and $direct!=null then ($direct|ctrl) else $o end) as $top |
              select(($top.kind|ascii_downcase)==($kind|ascii_downcase) and $top.name==$n) |
              "├── Pod: "+.metadata.name+" phase="+(.status.phase // "UNKNOWN")+" node="+(.spec.nodeName // "UNSCHEDULED"),
              (.spec.containers[]? | "│   ├── Container: "+.name+" image="+.image),
              (.spec.volumes[]? | if .secret.secretName then "│   ├── SecretRef/"+.secret.secretName elif .configMap.name then "│   ├── ConfigMap: "+.configMap.name elif .persistentVolumeClaim.claimName then "│   ├── PVC: "+.persistentVolumeClaim.claimName else empty end)' "$pods"
            ;;
        secret|configmap|pvc|service|certificate|serviceaccount|pv)
            resource_consumers "$type" "$namespace" "$name"; return;;
        helmrelease|kustomization|gitrepository)
            gitops_dependency_report "$type" "$name"; return;;
        *) printf 'Dependency parser: support for %s is metadata-only.\n' "$type";;
    esac
    printf '\nSERVICE RELATIONSHIPS\n'
    jq -r --arg n "$name" --arg kind "$type" --slurpfile svc "$services" '
      def ctrl: ([.metadata.ownerReferences[]? | select(.controller==true)][0] // .metadata.ownerReferences[0]);
      .items[] | . as $p | ctrl as $o | select(.metadata.name==$n or $o.name==$n or ($kind|ascii_downcase)=="pod" and .metadata.name==$n) |
      $p.metadata.labels as $lbl |
      $svc[0].items[] | select(.spec.selector!=null) | . as $s |
      select([.spec.selector|to_entries[] | ($lbl[.key] // "") == .value] | all) |
      "├── Service: "+.metadata.name+" type="+(.spec.type // "ClusterIP")+" clusterIP="+(.spec.clusterIP // "-")' "$pods" 2>/dev/null || :
    printf '\nGITOPS CORRELATION\n'
    deployment_chain_report "$name" 2>/dev/null || :
}

resource_consumers() {
    local type=${1:-} namespace=${2:-$SENTINEL_NAMESPACE} name=${3:-}
    collect_pods; collect_workloads; collect_network; collect_storage; cert_manager_collect
    has jq || { printf 'UNAVAILABLE: jq required for reverse dependencies.\n'; return 0; }
    local pods services ingresses pvcs certs
    pods=$(json_cache_path pods); services=$(json_cache_path services); ingresses=$(json_cache_path ingresses); pvcs=$(json_cache_path pvcs); certs=$(json_cache_path cert_certificates)
    printf 'REVERSE DEPENDENCIES | %s/%s\n' "$type" "$name"
    case ${type,,} in
        secret)
            jq -r --arg n "$name" '.items[] as $p |
              ([ $p.spec.volumes[]? | .secret.secretName, .projected.sources[]?.secret.name ] +
               [ $p.spec.containers[]?, $p.spec.initContainers[]? | .envFrom[]?.secretRef.name, .env[]?.valueFrom.secretKeyRef.name ]) as $refs |
              select(any($refs[]?; .==$n)) | "├── Pod: "+$p.metadata.name' "$pods"
            jq -r --arg n "$name" '.items[] as $i | $i.spec.tls[]? | select(.secretName==$n) | "├── Ingress: "+$i.metadata.name' "$ingresses" 2>/dev/null || :
            if [[ -s $certs ]]; then jq -r --arg n "$name" '.items[]|select(.spec.secretName==$n)|"├── Certificate: "+.metadata.name+" issuer="+(.spec.issuerRef.kind // "Issuer")+"/"+(.spec.issuerRef.name // "UNKNOWN")' "$certs"; fi
            ;;
        configmap)
            jq -r --arg n "$name" '.items[] as $p |
              ([ $p.spec.volumes[]? | .configMap.name, .projected.sources[]?.configMap.name ] +
               [ $p.spec.containers[]?, $p.spec.initContainers[]? | .envFrom[]?.configMapRef.name, .env[]?.valueFrom.configMapKeyRef.name ]) as $refs |
              select(any($refs[]?; .==$n)) | "├── Pod: "+$p.metadata.name' "$pods";;
        pvc)
            jq -r --arg n "$name" '.items[]|select(any(.spec.volumes[]?;.persistentVolumeClaim.claimName==$n))|"├── Pod: "+.metadata.name' "$pods"
            jq -r --arg n "$name" '.items[]|select(.metadata.name==$n)|"├── PV: "+(.spec.volumeName // "UNBOUND")+" class="+(.spec.storageClassName // "-")' "$pvcs";;
        pv)
            jq -r --arg n "$name" '.items[]|select(.spec.volumeName==$n)|"├── PVC: "+.metadata.name' "$pvcs";;
        service)
            jq -r --arg n "$name" --slurpfile svc "$services" '.items[] as $p | $p.metadata.labels as $lbl |
              ($svc[0].items[]|select(.metadata.name==$n)) as $s | select($s.spec.selector!=null) |
              select([$s.spec.selector|to_entries[] | ($lbl[.key] // "") == .value] | all) |
              "├── Pod: "+$p.metadata.name+" ip="+($p.status.podIP // "-")' "$pods" 2>/dev/null || :
            jq -r --arg n "$name" '.items[] as $i | .spec.rules[]?.http.paths[]?.backend.service | select(.name==$n) | "├── Ingress: "+$i.metadata.name' "$ingresses" 2>/dev/null || :;;
        certificate)
            if [[ -s $certs ]]; then
                local secret; secret=$(jq -r --arg n "$name" '.items[]|select(.metadata.name==$n)|.spec.secretName // empty' "$certs" | head -1)
                printf '├── SecretRef/%s\n' "${secret:-UNKNOWN}"
                [[ -n $secret ]] && resource_consumers Secret "$namespace" "$secret" | sed '1d;s/^/│   /'
            fi;;
        serviceaccount)
            jq -r --arg n "$name" '.items[]|select((.spec.serviceAccountName // "default")==$n)|"├── Pod: "+.metadata.name' "$pods";;
        *) printf 'Consumer mapping not implemented for %s\n' "$type";;
    esac
}

dependency_menu() {
    local kind api scope row name
    choose 'DEPENDENCY EXPLORER' Deployment StatefulSet DaemonSet Pod Secret ConfigMap PVC Service Certificate ServiceAccount GitRepository Kustomization HelmRelease 'Back' || return
    kind=$REPLY; [[ $kind == Back ]] && return
    row=$(resource_lookup "$kind") || return; IFS='|' read -r kind api scope <<< "$row"
    resource_select_name "$scope" "$api" || return; name=$REPLY
    show_report "Dependencies $kind/$name" resource_dependencies "$kind" "$SENTINEL_NAMESPACE" "$name"
}

configuration_dependency_menu() {
    local kind api scope row name
    choose 'CONFIGURATION DEPENDENCIES' Deployment StatefulSet DaemonSet Pod Secret ConfigMap PVC ServiceAccount 'Back' || return
    kind=$REPLY; [[ $kind == Back ]] && return
    row=$(resource_lookup "$kind") || return; IFS='|' read -r kind api scope <<< "$row"
    resource_select_name "$scope" "$api" || return; name=$REPLY
    show_report "Configuration dependencies $kind/$name" resource_dependencies "$kind" "$SENTINEL_NAMESPACE" "$name"
}

gitops_dependency_report() {
    local selected_type=${1:-} selected_name=${2:-}
    gitops_collect
    has jq || { printf 'UNAVAILABLE: jq required.\n'; return 0; }
    local src ks hr
    src=$(json_cache_path flux_gitrepositories); ks=$(json_cache_path flux_kustomizations); hr=$(json_cache_path flux_helmreleases)
    printf 'GITOPS DEPENDENCY GRAPH | namespace=%s\n' "$SENTINEL_NAMESPACE"
    jq -r --slurpfile ks "$ks" --slurpfile hr "$hr" --arg st "$selected_type" --arg sn "$selected_name" '
      .items[] as $s | select($sn=="" or (($st|ascii_downcase)=="gitrepository" and $s.metadata.name==$sn)) |
      "GitRepository/"+$s.metadata.name+" revision="+($s.status.artifact.revision // "UNKNOWN"),
      ($ks[0].items[] | select(.spec.sourceRef.kind=="GitRepository" and .spec.sourceRef.name==$s.metadata.name) as $k |
        "├── Kustomization/"+$k.metadata.name+" ready="+(([ $k.status.conditions[]?|select(.type=="Ready")][0].status)//"UNKNOWN")+" applied="+($k.status.lastAppliedRevision // "UNKNOWN"),
        ($k.status.inventory.entries[]? | select(.id|contains("_helm.toolkit.fluxcd.io_HelmRelease")) | .id as $id |
          ($id|split("_")[1]) as $hn | "│   └── HelmRelease/"+$hn))' "$src" 2>/dev/null || :
    printf '\nHELM RELEASE SOURCES\n'
    jq -r '.items[]|"HelmRelease/"+.metadata.name+" chart="+(.spec.chart.spec.chart // "UNKNOWN")+" source="+(.spec.chart.spec.sourceRef.kind // "UNKNOWN")+"/"+(.spec.chart.spec.sourceRef.name // "UNKNOWN")+" ready="+(([.status.conditions[]?|select(.type=="Ready")][0].status)//"UNKNOWN")' "$hr" 2>/dev/null || :
    printf '\nConfidence: CONFIRMED where Flux sourceRef/status.inventory explicitly links objects; otherwise UNKNOWN.\n'
}

workload_git_revision_report() {
    local name=${1:-}
    [[ -n $name ]] || { printf 'Workload name required\n'; return 2; }
    printf 'WORKLOAD -> GIT REVISION CORRELATION\n'
    deployment_chain_report "$name"
}

gitops_drift_report() {
    gitops_report
    printf '\nDRIFT INTERPRETATION\n'
    printf 'Ready=False, Stalled, suspended, generation lag and source/applied revision differences are reported as observed reconciliation evidence.\n'
    printf 'No desired manifests are fetched; runtime difference alone is not called proven Git drift.\n'
}

image_dependency_report() {
    images_report
    printf '\nIMAGE POLICY INTERPRETATION\n'
    printf 'Mutable tags and missing runtime digests reduce drift verifiability. Vulnerability status is UNKNOWN unless a scanner provides evidence.\n'
}

host_network_report() {
    render_header 'HOST NETWORK INSPECTOR'
    local title cmd rc
    while IFS='|' read -r title cmd; do
        render_section "$title"
        case $cmd in
            'ip addr') has ip && run_bounded 5 ip -brief address || printf 'TOOL_MISSING: ip\n';;
            'ip route') has ip && run_bounded 5 ip route show || printf 'TOOL_MISSING: ip\n';;
            'ip link') has ip && run_bounded 5 ip -brief link || printf 'TOOL_MISSING: ip\n';;
            'ss tcp') has ss && run_bounded 5 ss -lntup || printf 'TOOL_MISSING: ss\n';;
            'ss udp') has ss && run_bounded 5 ss -lnup || printf 'TOOL_MISSING: ss\n';;
        esac 2>&1 | redact
        rc=${PIPESTATUS[0]}; ((rc==0)) || printf 'STATUS: %s\n' "$(classify_error "$rc" "$title")"
    done <<'NETCMDS'
ADDRESSES|ip addr
ROUTES|ip route
LINKS|ip link
TCP/UDP LISTENERS|ss tcp
UDP LISTENERS|ss udp
NETCMDS
    printf '\nRead-only host inspection only. No interface, route, firewall or namespace state is changed.\n'
}

service_topology_report() {
    collect_network; collect_pods
    printf 'SERVICE / NETWORK TOPOLOGY | namespace=%s\n' "$SENTINEL_NAMESPACE"
    has jq || { network_report; return; }
    local svc ep pods ing
    svc=$(json_cache_path services); ep=$(json_cache_path endpointslices); pods=$(json_cache_path pods); ing=$(json_cache_path ingresses)
    jq -r --slurpfile ep "$ep" --slurpfile pods "$pods" --slurpfile ing "$ing" '
      .items[] as $s |
      ([ $ep[0].items[] | select(.metadata.labels["kubernetes.io/service-name"]==$s.metadata.name) ]) as $eps |
      "Service/"+$s.metadata.name+" type="+($s.spec.type // "ClusterIP")+" clusterIP="+($s.spec.clusterIP // "-")+" ports="+([$s.spec.ports[]?|((.port|tostring)+":"+((.targetPort//"-")|tostring))]|join(",")),
      ([$ing[0].items[] as $i | $i.spec.rules[]?.http.paths[]?.backend.service | select(.name==$s.metadata.name) | $i.metadata.name] | unique[]? | "├── Ingress: "+.),
      ($eps[]? | "├── EndpointSlice: "+.metadata.name+" ready="+([.endpoints[]?|select(.conditions.ready!=false)]|length|tostring)+"/"+(.endpoints|length|tostring),
        (.endpoints[]? | "│   └── "+(.addresses|join(","))+" -> "+(.targetRef.kind // "UNKNOWN")+"/"+(.targetRef.name // "UNKNOWN")))' "$svc"
}

storage_dependency_report() {
    collect_storage; collect_pods
    printf 'STORAGE DEPENDENCY GRAPH | namespace=%s\n' "$SENTINEL_NAMESPACE"
    has jq || { storage_report; return; }
    local pvc pods pvjson
    pvc=$(json_cache_path pvcs); pods=$(json_cache_path pods)
    pvjson=$(kctl_cluster get persistentvolumes -o json 2>/dev/null || printf '{"items":[]}')
    jq -r --slurpfile pods "$pods" --argjson pv "$pvjson" '
      .items[] as $c |
      ([$pv.items[]? | select(.metadata.name==$c.spec.volumeName)][0] // {}) as $v |
      "PVC/"+$c.metadata.name+" phase="+($c.status.phase // "UNKNOWN")+" requested="+($c.spec.resources.requests.storage // "UNKNOWN")+" capacity="+($c.status.capacity.storage // "UNKNOWN"),
      "├── PV: "+($c.spec.volumeName // "UNBOUND")+" class="+($c.spec.storageClassName // "-")+" reclaim="+($v.spec.persistentVolumeReclaimPolicy // "UNKNOWN")+" csi="+($v.spec.csi.driver // "UNKNOWN"),
      ($pods[0].items[] | select(any(.spec.volumes[]?;.persistentVolumeClaim.claimName==$c.metadata.name)) | "└── Pod: "+.metadata.name+" node="+(.spec.nodeName // "UNSCHEDULED"))' "$pvc" 2>/dev/null || :
}

pod_forensics_report() {
    local pod=${1:-}
    [[ -n $pod ]] || { printf 'Pod required\n'; return 2; }
    inspector_report "$pod"
    printf '\nDEPENDENCY GRAPH\n'
    resource_dependencies Pod "$SENTINEL_NAMESPACE" "$pod"
    printf '\nNETWORK / STORAGE / GITOPS CORRELATION\n'
    service_topology_report | grep -F "$pod" -B2 -A2 2>/dev/null || :
    deployment_chain_report "$pod" 2>/dev/null || :
    printf '\nLogs/current and previous logs are available only through explicit bounded/redacted log capture.\n'
}

failed_pod_intelligence_report() {
    collect_pods; collect_events
    printf 'FAILED / ALERT POD INTELLIGENCE\n'
    health_report
    if has jq; then
        printf '\nTARGETED POD STATES\n'
        jq -r '.items[] | . as $p |
          ([.status.containerStatuses[]?,.status.initContainerStatuses[]? | .state.waiting.reason // .lastState.terminated.reason // empty] | unique) as $r |
          ([.status.containerStatuses[]?,.status.initContainerStatuses[]? | .restartCount // 0] | add // 0) as $x |
          select(.status.phase!="Running" or ($r|length)>0 or $x>=5 or .metadata.deletionTimestamp!=null) |
          [.metadata.name,(.status.phase // "UNKNOWN"),($r|join(",")),($x|tostring),(.status.reason // "-")]|@tsv' "$(json_cache_path pods)"
    fi
}

smart_health_report() {
    printf 'SMART HEALTH CORRELATION\n'
    triage_report
    printf '\nCORRELATION POLICY\n'
    printf 'Evidence is classified as CONFIRMED only for explicit object relationships/status fields; cross-domain associations are LIKELY/POSSIBLE/UNKNOWN and are not labeled root cause without direct proof.\n'
    printf '\nGITOPS SIGNALS\n'; gitops_findings 2>/dev/null || :
    printf '\nCERTIFICATE SIGNALS\n'; certificates_findings 2>/dev/null || :
}

# ==============================================================================
# PKI/TLS command center extensions.
# ==============================================================================

cert_status_from_dates() {
    local before=$1 after=$2
    certificate_validity "$before" "$after"
    case $CERT_STATE in
        EXPIRED|NOT_YET_VALID) CERT_DISPLAY_STATE=$CERT_STATE;;
        CRITICAL) CERT_DISPLAY_STATE=CRITICAL;;
        WARN) CERT_DISPLAY_STATE=WARNING;;
        OK) if [[ $CERT_DAYS =~ ^-?[0-9]+$ ]] && ((CERT_DAYS<=CERT_ATTENTION_DAYS)); then CERT_DISPLAY_STATE=ATTENTION; else CERT_DISPLAY_STATE=HEALTHY; fi;;
        *) CERT_DISPLAY_STATE=UNKNOWN;;
    esac
}

cert_expiry_audit() {
    local raw name encoded pem before after subject issuer cn sans expiry days state rc
    printf 'CERTIFICATE EXPIRY AUDIT | namespace=%s | CRITICAL<=%sd WARNING<=%sd ATTENTION<=%sd\n' "$SENTINEL_NAMESPACE" "$CERT_CRIT_DAYS" "$CERT_WARN_DAYS" "$CERT_ATTENTION_DAYS"
    printf 'NAMESPACE\tOBJECT\tCN/SAN\tISSUER\tEXPIRY\tDAYS\tSTATUS\n'
    has openssl || { printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$SENTINEL_NAMESPACE" '-' '-' '-' '-' '-' 'TOOL_MISSING'; return 0; }
    raw=$(kctl_ns get secrets --field-selector type=kubernetes.io/tls -o 'go-template={{range .items}}{{.metadata.name}}{{"\t"}}{{index .data "tls.crt"}}{{"\n"}}{{end}}' 2>/dev/null); rc=$?
    if ((rc!=0)); then printf '%s\n' "TLS secret collection: $(classify_error "$rc" "$raw")"; return "$rc"; fi
    while IFS=$'\t' read -r name encoded; do
        [[ -n $name && -n $encoded ]] || continue
        pem=$(certificate_decode "$encoded" 2>/dev/null) || { printf '%s\tSecret/%s\t-\t-\t-\t-\tUNKNOWN\n' "$SENTINEL_NAMESPACE" "$name"; continue; }
        before=$(printf '%s\n' "$pem" | openssl x509 -noout -startdate 2>/dev/null | sed 's/^notBefore=//')
        after=$(printf '%s\n' "$pem" | openssl x509 -noout -enddate 2>/dev/null | sed 's/^notAfter=//')
        subject=$(printf '%s\n' "$pem" | openssl x509 -noout -subject -nameopt RFC2253 2>/dev/null | sed 's/^subject=//')
        issuer=$(printf '%s\n' "$pem" | openssl x509 -noout -issuer -nameopt RFC2253 2>/dev/null | sed 's/^issuer=//')
        cn=$(printf '%s\n' "$subject" | sed -n 's/.*CN=\([^,]*\).*/\1/p')
        sans=$(printf '%s\n' "$pem" | openssl x509 -noout -ext subjectAltName 2>/dev/null | tail -n +2 | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g;s/^ //;s/ $//')
        [[ -n $cn ]] || cn=${sans:-UNKNOWN}
        cert_status_from_dates "$before" "$after"; days=$CERT_DAYS; state=$CERT_DISPLAY_STATE; expiry=${after:-UNKNOWN}
        printf '%s\tSecret/%s\t%s\t%s\t%s\t%s\t%s\n' "$SENTINEL_NAMESPACE" "$name" "$cn" "${issuer:-UNKNOWN}" "$expiry" "$days" "$state"
        unset pem encoded
    done <<< "$raw"
    cert_manager_collect
    if has jq && [[ -s $CACHE_DIR/cert_certificates.json ]]; then
        while IFS=$'\t' read -r name before after issuer; do
            cert_status_from_dates "$before" "$after"
            printf '%s\tCertificate/%s\t%s\t%s\t%s\t%s\t%s\n' "$SENTINEL_NAMESPACE" "$name" "$name" "$issuer" "$after" "$CERT_DAYS" "$CERT_DISPLAY_STATE"
        done < <(jq -r '.items[]|[.metadata.name,(.status.notBefore//"UNKNOWN"),(.status.notAfter//"UNKNOWN"),((.spec.issuerRef.kind//"Issuer")+"/"+(.spec.issuerRef.name//"UNKNOWN"))]|@tsv' "$CACHE_DIR/cert_certificates.json")
    fi
}

cert_manager_extended_report() {
    local resource scope raw rc
    printf 'CERT-MANAGER EXTENDED AUDIT | namespace=%s\n' "$SENTINEL_NAMESPACE"
    for resource in certificates.cert-manager.io certificaterequests.cert-manager.io issuers.cert-manager.io orders.acme.cert-manager.io challenges.acme.cert-manager.io; do
        scope=ns
        printf '\n%s\n' "$resource"
        raw=$(kctl_ns get "$resource" -o json 2>&1); rc=$?
        if ((rc!=0)); then printf 'STATUS: %s\n' "$(classify_error "$rc" "$raw")"; continue; fi
        if has jq; then
            printf '%s\n' "$raw" | jq -r '.items[]? | [.kind,.metadata.name,([.status.conditions[]?|select(.type=="Ready")][0].status // .status.state // "UNKNOWN"),(.spec.secretName // .spec.issuerRef.name // .spec.dnsName // "-"),(.status.reason // ([.status.conditions[]?|select(.type=="Ready")][0].reason) // "-"),(.status.message // ([.status.conditions[]?|select(.type=="Ready")][0].message) // "-")]|@tsv' 2>/dev/null || :
        else printf 'jq unavailable; structured cert-manager view unavailable.\n'; fi
    done
    printf '\nclusterissuers.cert-manager.io\n'
    raw=$(kctl_cluster get clusterissuers.cert-manager.io -o json 2>&1); rc=$?
    if ((rc==0)) && has jq; then printf '%s\n' "$raw" | jq -r '.items[]?|[.kind,.metadata.name,([.status.conditions[]?|select(.type=="Ready")][0].status//"UNKNOWN"),([.status.conditions[]?|select(.type=="Ready")][0].reason//"-")]|@tsv'; else printf 'STATUS: %s\n' "$(classify_error "$rc" "$raw")"; fi
}

certificate_dependency_report() {
    cert_manager_collect; cert_ingress_collect; collect_pods; gitops_collect
    printf 'CERTIFICATE DEPENDENCY GRAPH | namespace=%s\n' "$SENTINEL_NAMESPACE"
    has jq || { cert_mounts_report; certificate_relationships_report; return; }
    local certs pods ing hr ks
    certs=$(json_cache_path cert_certificates); pods=$(json_cache_path pods); ing=$(json_cache_path cert_ingresses); hr=$(json_cache_path flux_helmreleases); ks=$(json_cache_path flux_kustomizations)
    jq -r --slurpfile pods "$pods" --slurpfile ing "$ing" --slurpfile hr "$hr" --slurpfile ks "$ks" '
      .items[] as $c | ($c.spec.secretName // "UNKNOWN") as $s |
      "Certificate/"+$c.metadata.name+" ready="+(([ $c.status.conditions[]?|select(.type=="Ready")][0].status)//"UNKNOWN")+" expires="+($c.status.notAfter // "UNKNOWN"),
      "├── SecretRef/"+$s,
      "├── Issuer: "+($c.spec.issuerRef.kind // "Issuer")+"/"+($c.spec.issuerRef.name // "UNKNOWN"),
      ($ing[0].items[] as $i | $i.spec.tls[]? | select(.secretName==$s) | "├── Ingress: "+$i.metadata.name+" hosts="+((.hosts//[])|join(","))),
      ($pods[0].items[] as $p | select(any($p.spec.volumes[]?; .secret.secretName==$s or any(.projected.sources[]?;.secret.name==$s))) | "├── Pod: "+$p.metadata.name),
      ($pods[0].items[] as $p | select(any($p.spec.volumes[]?; .secret.secretName==$s)) | ($p.metadata.labels["app.kubernetes.io/instance"] // "") as $rel | select($rel!="") | "└── Helm release label: "+$rel)' "$certs" 2>/dev/null || :
    printf '\nGitOps ownership is shown only where explicit labels/source relationships exist. Unproven ownership remains UNKNOWN.\n'
}

certificate_trust_secret_report() {
    local secret=$1 row cert64 ca64 certfile cafile chain_count rc verify subject issuer
    [[ $secret =~ ^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$ ]] || { printf 'Invalid Secret name\n'; return 2; }
    has openssl || { printf 'TOOL_MISSING: openssl\n'; return 0; }
    row=$(kctl_ns get secret "$secret" -o 'go-template={{index .data "tls.crt"}}{{"\t"}}{{index .data "ca.crt"}}' 2>&1); rc=$?
    ((rc==0)) || { printf 'STATUS: %s\n' "$(classify_error "$rc" "$row")"; return "$rc"; }
    IFS=$'\t' read -r cert64 ca64 <<< "$row"
    [[ -n $cert64 ]] || { printf 'Certificate tls.crt not present\n'; return 1; }
    certfile=$(mktemp "$RUN_DIR/trust-cert.XXXXXXXX.pem") || return 2
    cafile=$(mktemp "$RUN_DIR/trust-ca.XXXXXXXX.pem") || return 2
    chmod 600 "$certfile" "$cafile" 2>/dev/null || :
    certificate_decode "$cert64" > "$certfile" 2>/dev/null || { printf 'PARSE_ERROR: tls.crt base64\n'; rm -f "$certfile" "$cafile"; return 1; }
    [[ -n $ca64 ]] && certificate_decode "$ca64" > "$cafile" 2>/dev/null || :
    chain_count=$(grep -c 'BEGIN CERTIFICATE' "$certfile" 2>/dev/null || printf 0)
    subject=$(openssl x509 -in "$certfile" -noout -subject -nameopt RFC2253 2>/dev/null | sed 's/^subject=//')
    issuer=$(openssl x509 -in "$certfile" -noout -issuer -nameopt RFC2253 2>/dev/null | sed 's/^issuer=//')
    printf 'TRUST CHAIN ANALYZER | Secret/%s\n' "$secret"
    printf 'CHAIN LENGTH       : %s\nLEAF SUBJECT       : %s\nLEAF ISSUER        : %s\n' "$chain_count" "${subject:-UNKNOWN}" "${issuer:-UNKNOWN}"
    openssl x509 -in "$certfile" -noout -dates -serial -fingerprint -sha256 2>/dev/null | redact
    if [[ -s $cafile ]]; then
        verify=$(run_bounded "$TLS_TIMEOUT" openssl verify -CAfile "$cafile" "$certfile" 2>&1); rc=$?
        printf 'VERIFY RESULT      : %s\n' "$verify" | redact
        ((rc==0)) && printf 'CHAIN STATUS       : VERIFIED AGAINST ca.crt\n' || printf 'CHAIN STATUS       : VERIFY_FAILED\n'
    else
        printf 'VERIFY RESULT      : UNKNOWN (ca.crt not present in Secret)\nCHAIN STATUS       : UNKNOWN\n'
    fi
    if [[ $subject == "$issuer" ]]; then printf 'SELF-SIGNED         : YES\n'; else printf 'SELF-SIGNED         : NO/UNKNOWN\n'; fi
    rm -f -- "$certfile" "$cafile"
}

certificate_trust_menu() {
    local raw name
    raw=$(kctl_ns get secrets --field-selector type=kubernetes.io/tls -o 'jsonpath={range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null) || { printf 'TLS Secret list unavailable\n'; return; }
    local -a names=(); mapfile -t names < <(printf '%s\n' "$raw" | sed '/^$/d' | sort -u)
    ((${#names[@]})) || { printf 'No TLS Secrets found\n'; return; }
    choose 'TLS SECRET TRUST CHAIN' "${names[@]}" 'Back' || return; name=$REPLY; [[ $name == Back ]] && return
    show_report "Trust chain Secret/$name" certificate_trust_secret_report "$name"
}

certificate_health_summary() {
    local tmp total expired crit warn attention healthy unknown cmerr
    tmp=$(mktemp "$RUN_DIR/cert-summary.XXXXXXXX") || return 2
    cert_expiry_audit > "$tmp" 2>&1 || :
    total=$(grep -Ec $'\t(Secret|Certificate)/' "$tmp" 2>/dev/null || :)
    expired=$(grep -Ec $'\tEXPIRED$' "$tmp" 2>/dev/null || :)
    crit=$(grep -Ec $'\tCRITICAL$' "$tmp" 2>/dev/null || :)
    warn=$(grep -Ec $'\tWARNING$' "$tmp" 2>/dev/null || :)
    attention=$(grep -Ec $'\tATTENTION$' "$tmp" 2>/dev/null || :)
    healthy=$(grep -Ec $'\tHEALTHY$' "$tmp" 2>/dev/null || :)
    unknown=$(grep -Ec $'\tUNKNOWN$' "$tmp" 2>/dev/null || :)
    cmerr=0; [[ $(cache_status cert_certificates) =~ (RBAC|ERROR|FAIL|PARSE) ]] && cmerr=1 || :
    printf 'CERTIFICATES        : %s\nEXPIRED             : %s\nCRITICAL <= %sd     : %s\nWARNING <= %sd      : %s\nATTENTION <= %sd    : %s\nHEALTHY             : %s\nUNKNOWN             : %s\nCERT-MANAGER ERROR  : %s\n' "$total" "$expired" "$CERT_CRIT_DAYS" "$crit" "$CERT_WARN_DAYS" "$warn" "$CERT_ATTENTION_DAYS" "$attention" "$healthy" "$unknown" "$cmerr"
}

certificates_menu() {
    local choice path warning critical attention
    while :; do
        choose 'PKI / CERTIFICATE / TLS OPERATIONS COMMAND CENTER' \
          'Certificate health summary' 'Certificate inventory' 'Certificate expiry audit' 'cert-manager audit' \
          'Mounted certificate discovery' 'Certificate dependency graph' 'Trust chain analyzer' 'Live TLS endpoint inspector' \
          'Webhook CA certificates' 'Selected filesystem certificate' 'Expiry thresholds' 'Back' || return
        choice=$REPLY
        case $choice in
            'Certificate health summary') show_report 'Certificate health summary' certificate_health_summary;;
            'Certificate inventory') show_report 'Certificates' certificates_report;;
            'Certificate expiry audit') show_report 'Certificate expiry audit' cert_expiry_audit;;
            'cert-manager audit') show_report 'cert-manager audit' cert_manager_extended_report;;
            'Mounted certificate discovery') show_report 'Certificate mounts' cert_mounts_report;;
            'Certificate dependency graph') show_report 'Certificate dependencies' certificate_dependency_report;;
            'Trust chain analyzer') certificate_trust_menu;;
            'Live TLS endpoint inspector') tls_menu;;
            'Webhook CA certificates') show_report 'Webhook CA certificates' webhook_certificates_report;;
            'Selected filesystem certificate') prompt 'Explicit certificate file (.crt/.cer/.pem; metadata only):' || continue; path=$REPLY; [[ -n $path ]] && show_report 'Filesystem certificate' filesystem_certificate_report "$path";;
            'Expiry thresholds')
                prompt "Critical days [$CERT_CRIT_DAYS]:"; critical=${REPLY:-$CERT_CRIT_DAYS}
                prompt "Warning days [$CERT_WARN_DAYS]:"; warning=${REPLY:-$CERT_WARN_DAYS}
                prompt "Attention days [$CERT_ATTENTION_DAYS]:"; attention=${REPLY:-$CERT_ATTENTION_DAYS}
                if [[ $critical =~ ^[0-9]+$ && $warning =~ ^[0-9]+$ && $attention =~ ^[0-9]+$ ]] && ((critical>0 && warning>=critical && attention>=warning)); then CERT_CRIT_DAYS=$critical CERT_WARN_DAYS=$warning CERT_ATTENTION_DAYS=$attention; FORCE_REFRESH=1; else printf 'Invalid threshold order\n'; fi;;
            *) return;;
        esac
    done
}

# ==============================================================================
# PostgreSQL / Generic DB read-only operations.
# ==============================================================================

pg_discover_report() {
    local raw eps rc
    printf 'POSTGRESQL / GENERIC DB DISCOVERY | namespace=%s\n' "$SENTINEL_NAMESPACE"
    raw=$(kctl_ns get services -o json 2>&1); rc=$?
    ((rc==0)) || { printf 'Service discovery: %s\n' "$(classify_error "$rc" "$raw")"; return "$rc"; }
    has jq || { printf 'UNAVAILABLE: jq required for Generic DB discovery\n'; return 0; }
    printf 'SERVICE\tTYPE\tPORT\tCLUSTER IP\tEXTERNAL IP\tREADY ENDPOINT\tDATABASE\tUSERNAME\n'
    eps=$(kctl_ns get endpoints -o json 2>/dev/null || printf '{"items":[]}')
    printf '%s\n' "$raw" | jq -r --argjson ep "$eps" '
      .items[] | select((.metadata.name|test("genericdb|postgres|pgsql|database";"i")) or ((.metadata.labels//{})|tostring|test("postgres|genericdb";"i"))) as $s |
      ([ $ep.items[] | select(.metadata.name==$s.metadata.name) | .subsets[]?.addresses[]?.ip ][0] // "UNKNOWN") as $ready |
      [$s.metadata.name,($s.spec.type//"ClusterIP"),([$s.spec.ports[]?.port|tostring]|join(",")),($s.spec.clusterIP//"-"),([$s.status.loadBalancer.ingress[]?|(.ip//.hostname)]|join(",") // "-"),$ready,"UNKNOWN (safe metadata only)","UNKNOWN (credential not read)"]|@tsv'
    printf '\nDatabase/user values are intentionally not extracted from Secret payloads. Connection credentials are requested only for explicit read-only checks.\n'
}

pg_validate_field() { [[ $1 =~ ^[A-Za-z0-9._:-]+$ && $1 != -* ]]; }

pg_readonly_session() {
    local host port db user password pgpass choice query rc
    has psql || { printf 'TOOL_MISSING: psql\n'; return 0; }
    prompt 'PostgreSQL host/IP:' || return; host=$REPLY
    prompt 'Port [5432]:' || return; port=${REPLY:-5432}
    prompt 'Database:' || return; db=$REPLY
    prompt 'Username:' || return; user=$REPLY
    pg_validate_field "$host" && [[ $port =~ ^[0-9]{1,5}$ ]] && pg_validate_field "$db" && pg_validate_field "$user" || { printf 'Invalid connection field\n'; return 2; }
    printf 'Password (input hidden): ' >&2; IFS= read -r -s password; printf '\n' >&2
    pgpass=$(mktemp "$RUN_DIR/pgpass.XXXXXXXX") || return 2
    chmod 600 "$pgpass" || return 2
    printf '%s:%s:%s:%s:%s\n' "$host" "$port" "$db" "$user" "$password" > "$pgpass"
    unset password
    choose 'READ-ONLY POSTGRESQL CHECK' 'Connection / server identity' 'Database sizes' 'Active sessions summary' 'Long-running sessions' 'Back' || { rm -f "$pgpass"; return; }
    choice=$REPLY
    case $choice in
        'Connection / server identity') query='SELECT current_database(), current_user, version();';;
        'Database sizes') query='SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size FROM pg_database ORDER BY pg_database_size(datname) DESC;';;
        'Active sessions summary') query="SELECT state, count(*) FROM pg_stat_activity GROUP BY state ORDER BY 2 DESC;";;
        'Long-running sessions') query="SELECT pid, usename, datname, state, now()-query_start AS age, left(query,120) FROM pg_stat_activity WHERE query_start IS NOT NULL AND state <> 'idle' ORDER BY query_start LIMIT 50;";;
        *) rm -f "$pgpass"; return;;
    esac
    PGPASSFILE=$pgpass; export PGPASSFILE
    run_bounded "$API_TIMEOUT" psql -X --no-psqlrc -v ON_ERROR_STOP=1 -h "$host" -p "$port" -U "$user" -d "$db" -P pager=off -c "$query" 2>&1 | redact
    rc=${PIPESTATUS[0]}
    unset PGPASSFILE; rm -f -- "$pgpass"
    printf 'STATUS: %s\n' "$(classify_error "$rc" 'psql read-only query')"
    log_audit "postgres read-only check host=$host port=$port db=$db user=$user rc=$rc"
    return "$rc"
}

postgres_menu() {
    while choose 'POSTGRESQL / GENERIC DB' 'Auto-discovery' 'Explicit read-only session' 'Back'; do
        case $REPLY in 'Auto-discovery') show_report 'Generic DB discovery' pg_discover_report;; 'Explicit read-only session') pg_readonly_session;; *) return;; esac
    done
}

# ==============================================================================
# Kafka read-only diagnostics.
# ==============================================================================

kafka_topics_bin() { command -v kafka-topics.sh 2>/dev/null || command -v kafka-topics 2>/dev/null || :; }
kafka_groups_bin() { command -v kafka-consumer-groups.sh 2>/dev/null || command -v kafka-consumer-groups 2>/dev/null || :; }
kafka_valid_bootstrap() { [[ $1 =~ ^[A-Za-z0-9._:-]+(,[A-Za-z0-9._:-]+)*$ && $1 != -* ]]; }

kafka_discovery_report() {
    local raw rc kt kg
    kt=$(kafka_topics_bin); kg=$(kafka_groups_bin)
    printf 'KAFKA DIAGNOSTICS DISCOVERY | namespace=%s\n' "$SENTINEL_NAMESPACE"
    printf 'kafka-topics          : %s\nkafka-consumer-groups : %s\n' "${kt:-TOOL_MISSING}" "${kg:-TOOL_MISSING}"
    raw=$(kctl_ns get services -o json 2>&1); rc=$?
    if ((rc==0)) && has jq; then
        printf '\nSERVICE\tTYPE\tCLUSTER IP\tPORTS\n'
        printf '%s\n' "$raw" | jq -r '.items[]|select((.metadata.name|test("kafka";"i")) or ((.metadata.labels//{})|tostring|test("kafka";"i")))|[.metadata.name,(.spec.type//"ClusterIP"),(.spec.clusterIP//"-"),([.spec.ports[]?|((.name//"-")+":"+(.port|tostring))]|join(","))]|@tsv'
    else printf 'Kafka service discovery: %s\n' "$(classify_error "$rc" "$raw")"; fi
}

kafka_config_visibility() {
    local file=$1
    [[ -z $file ]] && { printf 'TLS/CLIENT CONFIG: not supplied\n'; return; }
    [[ -f $file && -r $file && ! -L $file ]] || { printf 'TLS/CLIENT CONFIG: INVALID/UNREADABLE\n'; return 2; }
    printf 'TLS/CLIENT CONFIG KEYS (values suppressed)\n'
    awk -F= '/^[[:space:]]*[A-Za-z0-9._-]+[[:space:]]*=/{k=$1;gsub(/[[:space:]]/,"",k);print k"=[SUPPRESSED]"}' "$file" | sort -u
}

kafka_connectivity_report() {
    local bootstrap=$1 first host port out rc
    kafka_valid_bootstrap "$bootstrap" || { printf 'Invalid bootstrap server list\n'; return 2; }
    first=${bootstrap%%,*}; host=${first%:*}; port=${first##*:}
    [[ $port =~ ^[0-9]{1,5}$ ]] || { printf 'Invalid bootstrap port\n'; return 2; }
    out=$(run_bounded 5 bash -c 'exec 3<>"/dev/tcp/$1/$2"' sentinel-kafka "$host" "$port" 2>&1); rc=$?
    printf 'BOOTSTRAP: %s\nTCP: %s\n' "$bootstrap" "$(classify_error "$rc" "$out")"
}

kafka_topics_report() {
    local bootstrap=$1 config=${2:-} bin rc; bin=$(kafka_topics_bin)
    [[ -n $bin ]] || { printf 'TOOL_MISSING: kafka-topics\n'; return 0; }
    kafka_valid_bootstrap "$bootstrap" || { printf 'Invalid bootstrap server list\n'; return 2; }
    local -a args=("$bin" --bootstrap-server "$bootstrap")
    [[ -n $config ]] && args+=(--command-config "$config")
    args+=(--list)
    kafka_config_visibility "$config" || :
    run_bounded "$API_TIMEOUT" "${args[@]}" 2>&1 | redact; rc=${PIPESTATUS[0]}
    printf 'STATUS: %s\n' "$(classify_error "$rc" 'kafka topics')"
}

kafka_groups_report() {
    local bootstrap=$1 config=${2:-} bin rc; bin=$(kafka_groups_bin)
    [[ -n $bin ]] || { printf 'TOOL_MISSING: kafka-consumer-groups\n'; return 0; }
    kafka_valid_bootstrap "$bootstrap" || { printf 'Invalid bootstrap server list\n'; return 2; }
    local -a args=("$bin" --bootstrap-server "$bootstrap")
    [[ -n $config ]] && args+=(--command-config "$config")
    args+=(--list)
    run_bounded "$API_TIMEOUT" "${args[@]}" 2>&1 | redact; rc=${PIPESTATUS[0]}
    printf 'STATUS: %s\n' "$(classify_error "$rc" 'kafka groups')"
}

kafka_menu() {
    local bootstrap config=''
    while choose 'KAFKA DIAGNOSTICS' 'Auto-discovery' 'Connectivity check' 'List topics' 'List consumer groups' 'Back'; do
        case $REPLY in
            'Auto-discovery') show_report 'Kafka discovery' kafka_discovery_report;;
            'Connectivity check'|'List topics'|'List consumer groups')
                local action=$REPLY
                prompt 'Bootstrap server(s) host:port[,host:port]:' || continue; bootstrap=$REPLY
                prompt 'Optional client properties path (Enter for none):' || continue; config=$REPLY
                [[ -z $config || ( -f $config && -r $config && ! -L $config ) ]] || { printf 'Invalid config file\n'; continue; }
                case $action in
                    'Connectivity check') show_report 'Kafka connectivity' kafka_connectivity_report "$bootstrap";;
                    'List topics') show_report 'Kafka topics' kafka_topics_report "$bootstrap" "$config";;
                    'List consumer groups') show_report 'Kafka consumer groups' kafka_groups_report "$bootstrap" "$config";;
                esac;;
            *) return;;
        esac
    done
}

# ==============================================================================
# ETDP-aware inspector. Generic labels/patterns are used and no cluster writes.
# ==============================================================================

etdp_platform_report() {
    collect_pods; collect_workloads; collect_network; gitops_collect
    render_header 'ETDP PLATFORM INSPECTOR'
    printf 'ETDP DETECTION: %s\n' "$( [[ ${SENTINEL_NAMESPACE,,} == *etdp* || ${SENTINEL_NAMESPACE,,} == *ecev* ]] && printf LIKELY || printf GENERIC_CLUSTER_MODE )"
    if ! has jq; then printf 'jq unavailable; ETDP categorization degraded.\n'; return; fi
    local pods; pods=$(json_cache_path pods)
    printf '\nCATEGORY\tPODS\tNOT RUNNING\tRESTARTS\n'
    while IFS='|' read -r category regex; do
        jq -r --arg c "$category" --arg r "$regex" '[.items[]|select(.metadata.name|test($r;"i"))] as $x | [$c,($x|length),([$x[]|select(.status.phase!="Running")]|length),([$x[].status.containerStatuses[]?.restartCount//0]|add//0)]|@tsv' "$pods"
    done <<'ETDPCATS'
Mediation / Application|eric-bss-em|mediation|online|manager
Generic DB|genericdb|postgres
Kafka|kafka
Log Transformer|transformer|log-transformer
Alarms / Fault|alarm|fault|fh-
Syslog / Logging|syslog|logship|filebeat
IAM / Identity|iam|keycloak|dex|oidc
KMS / Security|kms|key-management
Reporter / PM|reporter|pm-|prometheus|metrics
CNOM|cnom
Notification / File Server|fileserver|notification|file-mediation|sftp
Backup|backup|bragent|bro
ETDPCATS
    printf '\nGENERIC DB\n'; pg_discover_report 2>/dev/null || :
    printf '\nKAFKA\n'; kafka_discovery_report 2>/dev/null || :
    printf '\nGITOPS\n'; gitops_revision_report 2>/dev/null || :
    printf '\nCERTIFICATE HEALTH\n'; certificate_health_summary 2>/dev/null || :
}

etdp_menu() {
    while choose 'ETDP PLATFORM OPERATIONS' 'Platform overview' 'Generic DB' 'Kafka' 'GitOps' 'Certificates / TLS' 'Storage' 'Network' 'Event radar' 'Back'; do
        case $REPLY in
            'Platform overview') show_report 'ETDP Platform' etdp_platform_report;;
            'Generic DB') postgres_menu;; 'Kafka') kafka_menu;; 'GitOps') gitops_menu;;
            'Certificates / TLS') certificates_menu;; 'Storage') show_report 'Storage dependencies' storage_dependency_report;;
            'Network') show_report 'Service topology' service_topology_report;; 'Event radar') show_report 'Event Radar' events_report all;;
            *) return;;
        esac
    done
}

# ==============================================================================
# Fast scope bootstrap, doctor/explain/self-test/live validation/performance.
# ==============================================================================

AUTH_USER='UNKNOWN'


bootstrap_scope() {
    local raw rc current nsread answer
    local -a contexts=() namespaces=()
    has kubectl || { printf 'TOOL_MISSING: kubectl\n' >&2; return 2; }
    raw=$(capture_command "$RUN_DIR/config.error" config_query get-contexts -o name); rc=$?
    ((rc==0)) || { printf 'KUBECONFIG: %s\n' "$(classify_error "$rc" "$(cat "$RUN_DIR/config.error")")" >&2; return 2; }
    mapfile -t contexts < <(printf '%s\n' "$raw" | sed '/^$/d')
    ((${#contexts[@]})) || { printf 'NOT_CONFIGURED: no Kubernetes contexts\n' >&2; return 2; }
    if [[ -z $SENTINEL_CONTEXT ]]; then
        if ((INTERACTIVE)); then scope_select_list 'KUBERNETES CONTEXT SELECTION' "${contexts[@]}" || return 2; SENTINEL_CONTEXT=$REPLY
        else SENTINEL_CONTEXT=$(config_query current-context 2>/dev/null) || return 2; fi
    fi
    local found=0; for current in "${contexts[@]}"; do [[ $current == "$SENTINEL_CONTEXT" ]] && found=1; done
    ((found)) || { printf 'NOT_CONFIGURED: context does not exist\n' >&2; return 2; }
    [[ $SENTINEL_CONTEXT != -* && $SENTINEL_CONTEXT != *$'\n'* ]] || return 2

    AUTH_USER=$(run_bounded "$API_TIMEOUT" command kubectl --context "$SENTINEL_CONTEXT" config view --minify -o 'jsonpath={.contexts[0].context.user}' 2>/dev/null || printf UNKNOWN)
    raw=$(capture_command "$RUN_DIR/auth.error" kctl_cluster get namespaces -o 'jsonpath={range .items[*]}{.metadata.name}{"\n"}{end}'); rc=$?
    if ((rc==0)); then AUTH_STATUS=AUTHENTICATED API_STATUS=OK nsread=OK; mapfile -t namespaces < <(printf '%s\n' "$raw" | sed '/^$/d')
    else
        nsread=$(classify_error "$rc" "$(cat "$RUN_DIR/auth.error")")
        if [[ $nsread == RBAC_DENIED ]]; then AUTH_STATUS=UNKNOWN API_STATUS=OK
        else AUTH_STATUS=$nsread API_STATUS=$nsread; printf 'Authentication/API: %s\n' "$nsread" >&2; return 3; fi
    fi
    printf '%s\n' "$nsread" > "$CACHE_DIR/namespaces.status"
    if [[ -z $SENTINEL_NAMESPACE ]]; then
        if ((INTERACTIVE)) && ((${#namespaces[@]})); then scope_select_list 'NAMESPACE SELECTION' "${namespaces[@]}" || return 2; SENTINEL_NAMESPACE=$REPLY
        elif ((INTERACTIVE)); then prompt 'Namespace (enumeration not permitted):' || return 2; SENTINEL_NAMESPACE=$REPLY
        else printf 'A namespace is required in noninteractive mode: --namespace NAME\n' >&2; return 2; fi
    fi
    [[ $SENTINEL_NAMESPACE =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ && ${#SENTINEL_NAMESPACE} -le 63 ]] || { printf 'Invalid namespace\n' >&2; return 2; }
    if [[ $nsread == OK ]]; then
        found=0
        for current in "${namespaces[@]}"; do [[ $current == "$SENTINEL_NAMESPACE" ]] && found=1; done
        ((found)) || { printf 'RESOURCE_NOT_FOUND: namespace does not exist\n' >&2; return 2; }
    fi
    answer=$(kctl_ns auth can-i list pods 2>&1); rc=$?
    if [[ $answer == yes ]]; then RBAC_STATUS=OK AUTH_STATUS=AUTHENTICATED
    elif [[ $answer == no* ]]; then RBAC_STATUS=PARTIAL
    else RBAC_STATUS=$(classify_error "$rc" "$answer"); fi
    SCOPE_READY=1
    GITOPS_STATUS=NOT_PROBED CERT_STATUS=NOT_PROBED METRICS_STATUS=NOT_PROBED
    log_audit "scope locked user=$AUTH_USER startup=lazy"
    return 0
}

devopssentinel_doctor_report() {
    render_header 'ENVIRONMENT DOCTOR'
    render_kv 'Application' "$APP_NAME $APP_VERSION ($APP_BUILD)"
    render_kv 'Build date' "$APP_BUILD_DATE"
    render_kv 'Runtime root' "$SNTL_HOME"
    render_kv 'Runtime session' "$RUN_DIR"
    render_kv 'Kubeconfig mode' "$KUBECONFIG_MODE"
    render_kv 'Context' "${SENTINEL_CONTEXT:-UNSET}"
    render_kv 'Namespace' "${SENTINEL_NAMESPACE:-UNSET}"
    render_kv 'Authenticated user ref' "${AUTH_USER:-UNKNOWN}"
    render_kv 'Authentication' "$AUTH_STATUS"
    render_kv 'API' "$API_STATUS"
    render_kv 'RBAC' "$RBAC_STATUS"
    render_section 'TOOLING'
    local cmd
    for cmd in kubectl jq openssl helm flux curl psql kafka-topics.sh kafka-topics kafka-consumer-groups.sh kafka-consumer-groups ip ss timeout sha256sum; do printf '%-28s %s\n' "$cmd" "${DEPENDENCIES[$cmd]:-NOT INSTALLED}"; done
    render_section 'LAZY CAPABILITY PROBES'
    if [[ $SCOPE_READY == 1 ]]; then
        collect_text discovery 300 kctl_cluster api-resources --verbs=list -o name >/dev/null || :
        printf 'API discovery               %s\n' "$(cache_status discovery)"
        if [[ -s $CACHE_DIR/discovery.txt ]]; then
            grep -q 'gitrepositories.source.toolkit.fluxcd.io' "$CACHE_DIR/discovery.txt" && printf 'Flux CRDs                   AVAILABLE\n' || printf 'Flux CRDs                   OPTIONAL/UNAVAILABLE\n'
            grep -q 'certificates.cert-manager.io' "$CACHE_DIR/discovery.txt" && printf 'cert-manager CRDs           AVAILABLE\n' || printf 'cert-manager CRDs           OPTIONAL/UNAVAILABLE\n'
            grep -q 'pods.metrics.k8s.io' "$CACHE_DIR/discovery.txt" && printf 'Metrics API                 AVAILABLE\n' || printf 'Metrics API                 OPTIONAL/UNAVAILABLE\n'
        fi
    else printf 'Cluster scope not established; cluster capability probes skipped.\n'; fi
    render_section 'SAFETY'
    printf 'Cluster mutation commands   ABSENT BY DESIGN\nGit/Flux publishing          ABSENT BY DESIGN\nRuntime persistence          HOME-LOCAL ONLY\nSecret payload export        PROHIBITED\nPrivate-key display          PROHIBITED\nExternal calls               TIMEOUT BOUNDED\n'
    [[ $SCOPE_READY == 1 && $API_STATUS == OK && $RBAC_STATUS == OK ]] || return 4
}

explain_report() {
    local topic=${1:-overview}
    render_header "EXPLAIN: ${topic^^}"
    case ${topic,,} in
        overview)
            cat <<'TXT'
PURPOSE       Unified read-only Kubernetes, GitOps, PKI/TLS and ETDP troubleshooting console.
DATA SOURCE   Kubernetes APIs, metrics API, Flux/cert-manager APIs, Helm metadata, local host networking, explicit TLS/DB/Kafka targets.
COMMANDS      All external operations pass through bounded wrappers; mutation commands are not exposed.
RBAC          Namespace list/get plus optional cluster read permissions for nodes/PV/storage classes/CRDs.
INTERPRETATION Missing/denied data remains UNKNOWN/PARTIAL; no missing source is treated as healthy.
LIMITATIONS   Sequential API observations are not an atomic cluster snapshot. Git desired manifests are not downloaded.
TXT
            ;;
        certificates|certs|tls)
            cat <<'TXT'
PURPOSE       Inventory, expiry, cert-manager state, mounts, trust-chain evidence and bounded live TLS.
DATA SOURCE   TLS Secret public certificate bytes only, cert-manager status, Ingress/Pod references and explicit endpoint handshakes.
COMMANDS      kubectl get, openssl x509/verify/s_client with timeouts.
RBAC          get/list Secrets metadata/certificate field, Pods, Ingresses and cert-manager resources.
INTERPRETATION Mount references prove configuration, not filesystem presence. ca.crt verification is explicit when available.
LIMITATIONS   Private keys are never read/displayed. Unknown CA without a visible trust anchor remains UNKNOWN.
TXT
            ;;
        gitops|flux)
            cat <<'TXT'
PURPOSE       Show Flux readiness, source/applied revisions, generation lag and ownership relationships.
DATA SOURCE   Flux custom resources and status/inventory fields; optional Helm read-only metadata.
COMMANDS      kubectl get Flux CRDs, flux get, helm list/status/history only.
RBAC          list/get Flux CRDs and Helm release metadata.
INTERPRETATION Ready=False/suspended/generation lag are reconciliation signals, not automatically proven manifest drift.
LIMITATIONS   No reconcile, suspend/resume, Helm upgrade, Git commit or Git push exists in this build.
TXT
            ;;
        dependencies|dependency)
            cat <<'TXT'
PURPOSE       Trace forward and reverse relationships among workloads, Pods, Services, storage, config, certificates and GitOps.
DATA SOURCE   ownerReferences, selectors, volume/env references, EndpointSlices, Ingress backends, cert-manager secretName and Flux sourceRef/inventory.
COMMANDS      Read-only kubectl get plus local jq correlation.
RBAC          list/get relevant resources in the selected namespace; cluster reads for PV/StorageClass where available.
INTERPRETATION CONFIRMED is used for explicit references/selectors; label-only associations are not promoted to certainty.
LIMITATIONS   Application-level connections that are not represented in Kubernetes metadata remain UNKNOWN.
TXT
            ;;
        postgres|db)
            cat <<'TXT'
PURPOSE       Discover PostgreSQL/Generic DB endpoints and run a small fixed set of read-only diagnostic SELECT statements.
DATA SOURCE   Service/Endpoint metadata and an explicit operator-provided connection.
COMMANDS      psql with fixed SELECT-only queries and a temporary mode-600 pgpass file under the session runtime.
RBAC          Kubernetes Service/Endpoint list access; database permissions depend on the supplied DB account.
INTERPRETATION Connection failure is classified without exposing the password.
LIMITATIONS   Database name/user are not extracted from Kubernetes Secret payloads.
TXT
            ;;
        kafka)
            cat <<'TXT'
PURPOSE       Discover Kafka endpoints, test TCP reachability and list topics/consumer groups where client tools permit.
DATA SOURCE   Kubernetes Service metadata and explicit bootstrap/client-properties input.
COMMANDS      kafka-topics --list and kafka-consumer-groups --list only, timeout bounded.
RBAC          Kubernetes Service list access; Kafka ACLs apply to client operations.
INTERPRETATION Client property values are suppressed; only property keys are displayed.
LIMITATIONS   No producer, delete-topic, alter-config or consumer offset mutation is exposed.
TXT
            ;;
        *) printf 'Unknown topic. Use: overview, certificates, gitops, dependencies, postgres, kafka\n';;
    esac
}

_selftest_case() {
    local name=$1; shift
    ((SELFTEST_TOTAL+=1))
    if "$@"; then ((SELFTEST_PASS+=1)); printf '%-44s PASS\n' "$name"; else ((SELFTEST_FAIL+=1)); printf '%-44s FAIL\n' "$name"; fi
}

selftest_static_safety() {
    local bad=0
    if grep -En '^[[:space:]]*(kubectl|oc)[[:space:]].*(apply|create|delete|patch|edit|replace|scale|rollout[[:space:]]+(restart|undo))\b' "$SOURCE_FILE" | grep -v 'grep -E' >/dev/null; then bad=1; fi
    if grep -En '^[[:space:]]*flux[[:space:]].*(reconcile|suspend|resume)\b' "$SOURCE_FILE" >/dev/null; then bad=1; fi
    if grep -En '^[[:space:]]*helm[[:space:]].*(upgrade|rollback|uninstall|install)\b' "$SOURCE_FILE" >/dev/null; then bad=1; fi
    if grep -En '^[[:space:]]*git[[:space:]].*(push|commit|merge|rebase)\b' "$SOURCE_FILE" >/dev/null; then bad=1; fi
    if grep -En '(^|[;&|[:space:]])eval[[:space:]]' "$SOURCE_FILE" >/dev/null; then bad=1; fi
    ((bad==0))
}

selftest_redaction() { local out; out=$(printf '%s\n' 'password=supersecret' 'Authorization: Bearer abc.def.ghi' | redact); [[ $out != *supersecret* && $out != *abc.def.ghi* ]]; }
selftest_timeout() { local rc; run_bounded 1 bash -c 'sleep 2' >/dev/null 2>&1; rc=$?; ((rc!=0)); }
selftest_error_class() { [[ $(classify_error 1 'forbidden: cannot list') == RBAC_DENIED && $(classify_error 1 'x509: certificate signed by unknown authority') == TLS_ERROR ]]; }
selftest_home_runtime() {
    [[ $RUN_DIR == "$HOME/"* && $CACHE_DIR == "$HOME/"* && $SNTL_EXPORT_DIR == "$HOME/"* ]] || return 1
    [[ -x $CACHE_DIR ]] || return 1
    local probe="$CACHE_DIR/runtime-write-test"
    printf 'cache is writable\n' > "$probe" && [[ -s $probe ]] || return 1
    rm -f -- "$probe"
}
selftest_allowed_resources() { allowed_resource ns 'pods,services,networkpolicies.networking.k8s.io,certificates.cert-manager.io' >/dev/null && allowed_resource cluster 'nodes,persistentvolumes,storageclasses.storage.k8s.io' >/dev/null; }
selftest_rendering() { render_header SELFTEST >/dev/null && render_section TEST >/dev/null && render_footer >/dev/null; }
selftest_json_handling() { has jq || return 0; ! printf '{broken}\n' | jq -e . >/dev/null 2>&1; }
selftest_cert_category() { certificate_validity '2000-01-01T00:00:00Z' '2001-01-01T00:00:00Z'; [[ $CERT_STATE == EXPIRED ]]; }
selftest_export() { local f; f=$(mktemp "$RUN_DIR/selftest-report.XXXXXXXX"); printf 'alpha\tbeta\n' > "$f"; export_file "$f" selftest txt >/dev/null; ls "$SNTL_EXPORT_DIR"/selftest-*.txt >/dev/null 2>&1; }
selftest_function_contracts() { local f; for f in resource_dependencies resource_consumers cert_expiry_audit certificate_dependency_report gitops_dependency_report pg_discover_report kafka_discovery_report host_network_report evidence_create; do declare -F "$f" >/dev/null || return 1; done; }

sentinel_self_test() {
    SELFTEST_TOTAL=0 SELFTEST_PASS=0 SELFTEST_FAIL=0
    printf 'DEVOPSSENTINEL SELF-TEST | %s\n' "$(timestamp)"
    _selftest_case 'bash -n' bash -n "$SOURCE_FILE"
    _selftest_case 'static read-only safety' selftest_static_safety
    _selftest_case 'central redaction' selftest_redaction
    _selftest_case 'bounded timeout' selftest_timeout
    _selftest_case 'error classification' selftest_error_class
    _selftest_case 'HOME-local runtime' selftest_home_runtime
    _selftest_case 'resource allow-list' selftest_allowed_resources
    _selftest_case 'rendering engine' selftest_rendering
    _selftest_case 'malformed JSON handling' selftest_json_handling
    _selftest_case 'certificate expiry category' selftest_cert_category
    _selftest_case 'export engine' selftest_export
    _selftest_case 'feature function contracts' selftest_function_contracts
    if declare -F resource_self_tests >/dev/null; then _selftest_case 'Kubernetes parser fixtures' resource_self_tests; fi
    if declare -F cert_self_tests >/dev/null; then _selftest_case 'certificate parser fixtures' cert_self_tests; fi
    if declare -F ui_process_self_tests >/dev/null; then _selftest_case 'navigation/process fixtures' ui_process_self_tests; fi
    if declare -F advanced_ui_self_tests >/dev/null; then _selftest_case 'advanced operator workspace fixtures' advanced_ui_self_tests; fi
    _selftest_case 'core collector integration fixtures' core_integration_tests
    _selftest_case 'resource integration fixtures' resource_integration_tests
    _selftest_case 'triage integration fixtures' triage_integration_tests
    _selftest_case 'GitOps and certificate fixtures' gitops_certificate_self_tests
    _selftest_case 'Splunk response fixtures (offline)' splunk_self_tests
    printf '\nTOTAL=%s PASS=%s FAIL=%s\n' "$SELFTEST_TOTAL" "$SELFTEST_PASS" "$SELFTEST_FAIL"
    ((SELFTEST_FAIL==0))
}

validation_cache_result() {
    local optional=$1 key state missing=0 failed=0
    shift
    for key in "$@"; do
        state=$(cache_status "$key")
        case $state in
            OK|EMPTY_RESULT) ;;
            RESOURCE_NOT_FOUND) if [[ $optional == 1 ]]; then missing=1; else failed=1; fi;;
            *) failed=1;;
        esac
        printf '%s=%s ' "$key" "$state"
    done
    if ((failed)); then printf 'PARTIAL/FAIL\n'; return 4
    elif ((missing)); then printf 'OPTIONAL_UNAVAILABLE\n'
    else printf 'PASS\n'; fi
}

live_validation_report() {
    printf 'LIVE READ-ONLY VALIDATION | context=%s namespace=%s\n' "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE"
    local name fn optional keys rc failed=0
    local -a cache_keys=()
    while IFS='|' read -r name fn optional keys; do
        printf '%-34s ' "$name"
        "$fn" >/dev/null 2>&1
        # Collectors intentionally tolerate partial data. Their persisted source
        # states, rather than the wrapper exit code, establish availability.
        read -r -a cache_keys <<< "$keys"
        validation_cache_result "$optional" "${cache_keys[@]}" || failed=1
    done <<'VALIDATIONS'
Pod inventory|collect_pods|0|pods
Workloads|collect_workloads|0|workloads
Events|collect_events|0|events
Services/Endpoints|collect_network|0|services endpointslices endpoints ingresses
Storage|collect_storage|0|pvcs
GitOps inventory|gitops_collect|1|flux_gitrepositories flux_kustomizations flux_helmrepositories flux_helmreleases
Certificate inventory|cert_manager_collect|1|cert_certificates cert_certificaterequests cert_issuers cert_clusterissuers
VALIDATIONS
    printf '%-34s ' 'TLS Secret metadata'
    tls_secret_metadata_collect >/dev/null 2>&1; rc=$?
    if ((rc==0)); then printf 'PASS\n'; else printf 'PARTIAL/FAIL rc=%s\n' "$rc"; failed=1; fi
    printf 'No mutation operation is executed by live validation. Optional/denied sources may report PARTIAL.\n'
    ((failed==0)) || return 4
}

measure_ms() {
    local label=$1; shift
    local start end rc
    start=$(date +%s%3N 2>/dev/null); [[ $start =~ ^[0-9]+$ ]] || start=$(($(date +%s)*1000))
    "$@" >/dev/null 2>&1; rc=$?
    end=$(date +%s%3N 2>/dev/null); [[ $end =~ ^[0-9]+$ ]] || end=$(($(date +%s)*1000))
    printf '%-34s %8s ms  rc=%s\n' "$label" "$((end-start))" "$rc"
}

performance_report() {
    printf 'PERFORMANCE VALIDATION | context=%s namespace=%s\n' "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE"
    FORCE_REFRESH=1; measure_ms 'Pod grid / inventory' collect_pods
    FORCE_REFRESH=1; measure_ms 'Events' collect_events
    FORCE_REFRESH=1; measure_ms 'GitOps inventory' gitops_collect
    FORCE_REFRESH=1; measure_ms 'Certificate inventory' cert_manager_collect
    FORCE_REFRESH=1; measure_ms 'Network topology inputs' collect_network
    FORCE_REFRESH=1; measure_ms 'Storage inputs' collect_storage
    FORCE_REFRESH=0
    printf 'Startup itself performs only context/auth/namespace selection and a minimal RBAC probe. Domain scans are lazy.\n'
}

# ==============================================================================
# Professional 30-domain operations dashboard.
# ==============================================================================


change_scope() {
    SENTINEL_CONTEXT= SENTINEL_NAMESPACE= SCOPE_READY=0 AUTH_STATUS=UNKNOWN API_STATUS=UNKNOWN RBAC_STATUS=UNKNOWN AUTH_USER=UNKNOWN
    rm -f -- "$CACHE_DIR"/*.json "$CACHE_DIR"/*.txt "$CACHE_DIR"/*.status "$CACHE_DIR"/*.time "$CACHE_DIR"/*.error 2>/dev/null || :
    bootstrap_scope
}


# ==============================================================================
# 19 Enterprise terminal UI/UX modernization layer (v4.1)
# Presentation-only overrides. Backend collectors, safety wrappers and read-only
# behavior remain unchanged. Later Bash function definitions intentionally
# override earlier compatibility renderers.
# ==============================================================================

UI_LAYOUT="STANDARD"
UI_LABEL_WIDTH=22
UI_PAGE_SIZE=20
UI_COMPACT_FLAG=${UI_COMPACT_FLAG:-0}
UI_SNAPSHOT_FLAG=${UI_SNAPSHOT_FLAG:-0}
UI_BREADCRUMB='DEVOPSSENTINEL'
UI_SCREEN_TITLE='OPERATIONS COMMAND CENTER'
UI_SOURCE='CACHE/LIVE AS REPORTED'
UI_QUERY_MS='-'
UI_RECORDS='-'
UI_UPDATED='-'
UI_VIEW_MODE='SUMMARY'
UI_FILTER_TEXT='none'
UI_SORT_TEXT='default'
UI_EXIT_REQUESTED=0
UI_MAIN_REQUESTED=0
UI_ASCII=1
UI_TREE_MID='|--'
UI_TREE_END='`--'
UI_TREE_VERT='|'
UI_TREE_DOWN='v'
C_MAGENTA= C_WHITE= C_BOLD=

ui_detect_unicode() {
    local mode=${DEVOPSSENTINEL_UNICODE:-auto} locale_text
    case ${mode,,} in
        off|0|false|no) UI_ASCII=1 ;;
        on|1|true|yes) UI_ASCII=0 ;;
        *)
            locale_text=${LC_ALL:-${LC_CTYPE:-${LANG:-C}}}
            if [[ $locale_text == *UTF-8* || $locale_text == *utf8* || $locale_text == *UTF8* ]]; then UI_ASCII=0; else UI_ASCII=1; fi
            ;;
    esac
    if ((UI_ASCII)); then
        UI_TREE_MID='|--'; UI_TREE_END='`--'; UI_TREE_VERT='|'; UI_TREE_DOWN='v'
    else
        UI_TREE_MID='├─'; UI_TREE_END='└─'; UI_TREE_VERT='│'; UI_TREE_DOWN='▼'
    fi
}

terminal_size() {
    local c=${COLUMNS:-120} r=${LINES:-30}
    if has tput && [[ ${TERM:-dumb} != dumb && -t 1 ]]; then
        c=$(tput cols 2>/dev/null || printf '%s' "$c")
        r=$(tput lines 2>/dev/null || printf '%s' "$r")
    fi
    [[ $c =~ ^[0-9]+$ ]] || c=120
    [[ $r =~ ^[0-9]+$ ]] || r=30
    ((c < 40)) && c=40
    ((r < 12)) && r=12
    UI_COLS=$c UI_ROWS=$r
    if ((UI_COMPACT_FLAG)); then UI_LAYOUT=COMPACT
    elif ((c < 100)); then UI_LAYOUT=COMPACT
    elif ((c < 140)); then UI_LAYOUT=STANDARD
    elif ((c < 180)); then UI_LAYOUT=WIDE
    else UI_LAYOUT=ULTRAWIDE
    fi
    if ((r <= 22)); then UI_PAGE_SIZE=$((r-9)); else UI_PAGE_SIZE=$((r-10)); fi
    ((UI_PAGE_SIZE < 5)) && UI_PAGE_SIZE=5
    case $UI_LAYOUT in COMPACT) UI_LABEL_WIDTH=17;; STANDARD) UI_LABEL_WIDTH=21;; *) UI_LABEL_WIDTH=24;; esac
    ui_detect_unicode
}

color_init() {
    C_RESET= C_GREEN= C_YELLOW= C_RED= C_CYAN= C_BLUE= C_DIM= C_MAGENTA= C_WHITE= C_BOLD=
    if [[ -t 1 && ${TERM:-dumb} != dumb && ! ${NO_COLOR+x} && $NO_COLOR_FLAG == 0 ]]; then
        C_RESET=$'\033[0m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'
        C_CYAN=$'\033[36m'; C_BLUE=$'\033[34m'; C_MAGENTA=$'\033[35m'; C_WHITE=$'\033[37m'
        C_DIM=$'\033[2m'; C_BOLD=$'\033[1m'
    fi
}

ui_status_kind() {
    case ${1^^} in
        OK|PASS|PASSED|AUTHENTICATED|AVAILABLE|HEALTHY|READY) printf 'OK' ;;
        INFO|RUNNING|ACTIVE|NOT_PROBED|NOT\ SCANNED) printf 'INFO' ;;
        NOTICE|NOTE|EMPTY|EMPTY_RESULT|SKIPPED) printf 'NOTICE' ;;
        WARN|WARNING|DEGRADED|PARTIAL|PENDING|ATTENTION) printf 'WARNING' ;;
        CRIT|CRITICAL|EXPIRED) printf 'CRITICAL' ;;
        FAIL|FAILED|ERROR|AUTH_ERROR|RBAC_DENIED|DNS_ERROR|TLS_ERROR|NETWORK_ERROR|API_TIMEOUT|PARSE_ERROR|COMMAND_MISSING|RESOURCE_NOT_FOUND|UNAVAILABLE|TOOL_MISSING) printf 'FAILED' ;;
        *) printf 'UNKNOWN' ;;
    esac
}

status_label() {
    local kind short color
    kind=$(ui_status_kind "${1:-UNKNOWN}")
    case $kind in
        OK) short=' OK '; color=$C_GREEN;;
        INFO) short='INFO'; color=$C_CYAN;;
        NOTICE) short='NOTE'; color=$C_BLUE;;
        WARNING) short='WARN'; color=$C_YELLOW;;
        CRITICAL) short='CRIT'; color=$C_RED;;
        FAILED) short='FAIL'; color=$C_RED;;
        *) short='UNKN'; color=$C_YELLOW;;
    esac
    printf '%s[%s]%s' "$color" "$short" "$C_RESET"
}

ui_repeat() {
    local ch=${1:--} count=${2:-1} out
    ((count < 1)) && { printf '\n'; return; }
    printf -v out '%*s' "$count" ''
    printf '%s' "${out// /$ch}"
}

rule() { ui_repeat '=' "$UI_COLS"; printf '\n'; }
ui_subrule() { ui_repeat '-' "$UI_COLS"; printf '\n'; }

truncate_text() {
    local text=$1 width=$2
    ((width < 4)) && { printf '%.*s' "$width" "$text"; return; }
    if ((${#text} > width)); then printf '%s...' "${text:0:width-3}"; else printf '%s' "$text"; fi
}

ui_time_local() {
    date '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || timestamp
}

ui_global_health() {
    local fails=0 warns=0
    [[ ${AUTH_STATUS:-UNKNOWN} == AUTHENTICATED && ${API_STATUS:-UNKNOWN} == OK ]] || { printf 'FAILED'; return; }
    [[ ${RBAC_STATUS:-UNKNOWN} == OK ]] || warns=1
    if [[ -s ${RUN_DIR:-/nonexistent}/findings.tsv ]]; then
        fails=$(awk -F '\t' '$1=="FAIL" || $1=="CRITICAL"{n++} END{print n+0}' "$RUN_DIR/findings.tsv" 2>/dev/null)
        [[ $fails =~ ^[0-9]+$ ]] || fails=0
        ((fails>0)) && { printf 'CRITICAL'; return; }
        warns=$(awk -F '\t' '$1=="WARN" || $1=="WARNING"{n++} END{print n+0}' "$RUN_DIR/findings.tsv" 2>/dev/null)
        [[ $warns =~ ^[0-9]+$ ]] || warns=0
    fi
    ((warns>0)) && printf 'WARNING' || printf 'OK'
}

ui_breadcrumb() {
    local path=${1:-DEVOPSSENTINEL}
    printf ' %s%s%s\n' "$C_CYAN" "$path" "$C_RESET"
}

ui_section() {
    local title=${1:-SECTION}
    printf '\n %s%s%s\n' "$C_BLUE$C_BOLD" "$title" "$C_RESET"
    ui_repeat '-' "$UI_COLS"; printf '\n'
}

ui_kv() {
    local label=$1 value=${2:-}
    if [[ $UI_LAYOUT == COMPACT ]]; then printf ' %-*s : %s\n' "$UI_LABEL_WIDTH" "$label" "$value"
    else printf ' %-*s : %s\n' "$UI_LABEL_WIDTH" "$label" "$value"; fi
}

ui_status() { ui_kv "$1" "$(status_label "$2") ${3:-}"; }
ui_tree() { printf ' %s\n' "$*"; }

ui_progress() {
    local step=${1:-INFO} text=${2:-} state=${3:-}
    if [[ -n $state ]]; then printf ' %-8s %-*s %s\n' "[$step]" "$((UI_COLS-24))" "$text" "$state" >&2
    else printf ' [%s] %s\n' "$step" "$text" >&2; fi
}

ui_empty_state() {
    local title=${1:-NO DATA FOUND} detail=${2:-'No records match the current criteria.'}
    printf '\n %s\n' "$title"; ui_subrule; printf ' %s\n' "$detail"
}

ui_error() {
    local message=$1 reason=${2:-UNKNOWN} impact=${3:-'Requested data is incomplete.'} next=${4:-'Continue with available evidence.'}
    printf '\n %s %s\n' "$(status_label FAILED)" "$message"
    ui_kv 'Reason' "$reason"; ui_kv 'Impact' "$impact"; ui_kv 'Next action' "$next"
}

# Backward-compatible rendering API used by backend report functions.
render_header() { ui_header "${1:-DEVOPSSENTINEL}" "DEVOPSSENTINEL > ${1:-OVERVIEW}"; }
render_section() { ui_section "$1"; }
render_kv() { ui_kv "$1" "$2"; }
render_status() { ui_status "$1" "$2"; }
render_tree() { ui_tree "$*"; }
render_progress() { ui_progress "${1:-INFO}" "${2:-}" "${3:-}"; }
render_footer() { ui_footer; }
render_table() { if has column; then column -t -s $'\t' 2>/dev/null || cat; else cat; fi; }

format_table() {
    local width=${1:-$UI_COLS}
    if ! has awk; then
        local line
        while IFS= read -r line; do truncate_text "${line//$'\t'/ }" "$((width-1))"; printf '\n'; done
        return
    fi
    awk -F '\t' -v w="$((width-1))" '
    function clip(s,n) {return length(s)>n ? substr(s,1,n-3) "..." : s}
    NF<2 { print clip($0,w); next }
    NF>=20 {
      if(w<100) line=sprintf("%-30s %-7s %-16s %5s %10s",clip($1,30),clip($2,7),clip($3,16),clip($4,5),clip($9,10))
      else if(w<140) line=sprintf("%-34s %-7s %-18s %5s %10s %10s %12s",clip($1,34),clip($2,7),clip($3,18),clip($4,5),clip($6,10),clip($9,10),clip($10,12))
      else line=sprintf("%-42s %-7s %-20s %6s %10s %10s %10s %13s %13s %-20s",clip($1,42),clip($2,7),clip($3,20),clip($4,6),clip($6,10),clip($7,10),clip($8,10),clip($9,13),clip($10,13),clip($16,20))
      print clip(line,w); next
    }
    {
      first=(w>=150?46:(w>=110?36:30)); rest=(w>=140?16:13); max=1+int((w-first)/(rest+1))
      line=sprintf("%-*s",first,clip($1,first)); n=NF<max?NF:max
      for(i=2;i<=n;i++) line=line " " sprintf("%-*s",rest,clip($i,rest))
      print clip(line,w)
    }'
}

ui_clear_transition() {
    [[ -t 1 && ${TERM:-dumb} != dumb ]] && printf '\033[H\033[2J'
}

ui_view_help() {
    local title=${1:-REPORT}
    ui_header "$title HELP" "DEVOPSSENTINEL > HELP > ${title^^}"
    ui_section 'NAVIGATION'
    ui_kv 'N / P' 'Next / previous page'
    ui_kv 'G / Shift+G' 'First / last page'
    ui_kv '/' 'Filter current report (case-insensitive literal)'
    ui_kv 'V' 'Cycle SUMMARY -> DETAIL -> RAW'
    ui_kv 'E' 'Export full, untruncated sanitized report'
    ui_kv 'B / 0' 'Back'
    ui_kv 'M' 'Return to main dashboard'
    ui_kv 'Q' 'Exit DevOpsSentinel'
    ui_footer 'LOCAL REPORT' '-'
}

view_file() {
    local file=$1 title=${2:-'Full Output'} page=0 key search='' i start count line page_size total_pages
    local view_mode=SUMMARY source='LOCAL REPORT'
    local -a raw=() formatted=() shown=()
    [[ -f $file ]] || { ui_error 'Report file unavailable' NOT_FOUND 'The requested report cannot be rendered.' 'Return and refresh the source.'; return 1; }
    CURRENT_REPORT=$file CURRENT_TITLE=$title
    if (( ! INTERACTIVE )); then redact < "$file"; return; fi
    terminal_size; page_size=$UI_PAGE_SIZE
    mapfile -t raw < <(tail -n +3 -- "$file" | redact)
    while :; do
        terminal_size; page_size=$UI_PAGE_SIZE
        formatted=()
        case $view_mode in
            SUMMARY)
                mapfile -t formatted < <(printf '%s\n' "${raw[@]}" | format_table "$UI_COLS")
                ;;
            DETAIL)
                for line in "${raw[@]}"; do
                    line=${line//$'\t'/  }
                    while ((${#line}>UI_COLS-2)); do formatted+=("${line:0:UI_COLS-2}"); line=${line:UI_COLS-2}; done
                    formatted+=("$line")
                done
                ;;
            RAW) formatted=("${raw[@]}");;
        esac
        shown=(); page=0
        if [[ -z $search ]]; then shown=("${formatted[@]}")
        else for line in "${formatted[@]}"; do [[ ${line,,} == *"${search,,}"* ]] && shown+=("$line"); done; fi
        while :; do
            count=${#shown[@]}; ((count==0)) && total_pages=1 || total_pages=$(((count+page_size-1)/page_size))
            ((page>=total_pages)) && page=$((total_pages-1)); ((page<0)) && page=0
            start=$((page*page_size))
            UI_VIEW_MODE=$view_mode UI_FILTER_TEXT=${search:-none} UI_RECORDS=$count UI_UPDATED=$(ui_time_local)
            ui_clear_transition
            ui_header "$title" "DEVOPSSENTINEL > ${title^^}"
            if ((count==0)); then ui_empty_state 'NO MATCHING RECORDS' "Filter '${search:-none}' returned no display rows."
            else
                printf ' Showing %d-%d of %d | Page %d/%d\n' "$((start+1))" "$(( start+page_size<count ? start+page_size : count ))" "$count" "$((page+1))" "$total_pages"
                ui_subrule
                for ((i=start;i<start+page_size && i<count;i++)); do
                    if [[ $view_mode == RAW ]]; then printf '%s\n' "${shown[i]}"; else truncate_text "${shown[i]}" "$((UI_COLS-1))"; printf '\n'; fi
                done
            fi
            ui_subrule
            printf ' [N] Next [P] Prev [G] First [Shift+G] Last [/] Filter [V] View [E] Export [T] Triage [F] Findings [H] Help [B] Back [M] Main [Q] Exit\n'
            printf ' Source: %s | View: %s | Filter: %s | Records: %s | Updated: %s\n' "$source" "$view_mode" "${search:-none}" "$count" "$UI_UPDATED"
            prompt 'ACTION >' || return
            key=${REPLY,,}
            case $REPLY in
                N|n) ((start+page_size<count)) && ((page+=1));;
                P|p) ((page>0)) && ((page-=1));;
                g) page=0;; G) page=$((total_pages-1));;
                /) prompt 'FILTER >' || continue; search=$REPLY; break;;
                V|v) case $view_mode in SUMMARY) view_mode=DETAIL;; DETAIL) view_mode=RAW;; RAW) view_mode=SUMMARY;; esac; break;;
                E|e) choose 'EXPORT FORMAT' TXT CSV JSON NDJSON PROMETHEUS || continue; export_file "$file" "$title" "${REPLY,,}"; prompt 'Enter to continue:' || :;;
                H|h) ui_clear_transition; ui_view_help "$title"; prompt 'Enter to return:' || :;;
                T|t) UI_PENDING_ACTION=t; UI_MAIN_REQUESTED=1; return 0;;
                F|f) UI_PENDING_ACTION=f; UI_MAIN_REQUESTED=1; return 0;;
                B|b|0) return 0;;
                M|m) UI_MAIN_REQUESTED=1; return 0;;
                Q|q) UI_EXIT_REQUESTED=1; return 0;;
            esac
        done
    done
}

show_report() {
    local title=$1 rc
    shift
    capture_report "$title" "$@"; rc=$?
    [[ -f $CURRENT_REPORT ]] && view_file "$CURRENT_REPORT" "$title"
    return "$rc"
}

# Professional local export wrapper. The core implementation remains unchanged.
export_file() {
    local file=$1 label=${2:-report} format=${3:-txt} before path sha records core_out
    before=$(find "$SNTL_EXPORT_DIR" -maxdepth 1 -type f 2>/dev/null | wc -l | awk '{print $1}')
    core_out=$(_export_file_core "$file" "$label" "$format") || { printf '%s\n' "$core_out"; return 2; }
    path=$(printf '%s\n' "$core_out" | awk '/^EXPORTED /{sub(/^EXPORTED /,""); print; exit}')
    [[ -n $path && -f $path ]] || { printf '%s\n' "$core_out"; return 0; }
    records=$(wc -l < "$path" | awk '{print $1}')
    if has sha256sum; then sha=$(sha256sum "$path" | awk '{print $1}'); else sha='UNAVAILABLE'; fi
    printf '\nEXPORT COMPLETE\n'; ui_subrule
    ui_kv 'Format' "${format^^}"
    ui_kv 'Records/lines' "$records"
    ui_kv 'File' "$path"
    ui_kv 'SHA256' "$sha"
    return 0
}

scope_select_list() {
    local title=$1 input item pattern page=0 page_size start end i total search='' key
    shift
    local -a items=("$@") matches=() visible=()
    ((${#items[@]})) || return 1
    while :; do
        terminal_size; page_size=$UI_PAGE_SIZE
        visible=()
        if [[ -z $search ]]; then visible=("${items[@]}")
        elif [[ $search == /* ]]; then
            pattern=${search#/}; for item in "${items[@]}"; do [[ $item =~ $pattern ]] 2>/dev/null && visible+=("$item"); done
        else
            for item in "${items[@]}"; do [[ ${item,,} == *"${search,,}"* ]] && visible+=("$item"); done
        fi
        total=${#visible[@]}; ((total==0)) && page=0
        start=$((page*page_size)); ((start>=total && page>0)) && { ((page-=1)); continue; }
        end=$((start+page_size)); ((end>total)) && end=$total
        ui_clear_transition
        ui_header "$title" "DEVOPSSENTINEL > SCOPE > ${title^^}"
        printf ' %-5s %s\n' '#' 'RESOURCE / SCOPE'; ui_subrule
        if ((total==0)); then ui_empty_state 'NO MATCHES' "Filter '${search}' matched no entries."
        else for ((i=start;i<end;i++)); do printf ' %-5d %s\n' "$((i+1))" "${visible[i]}"; done; fi
        ui_subrule
        printf ' Showing %d-%d of %d | [N] Next [P] Prev [/] Filter [R] Reset [0] Back\n' "$((total?start+1:0))" "$end" "$total"
        prompt 'SELECT number / partial / /regex >' || return 1; input=$REPLY
        case ${input,,} in
            q) UI_EXIT_REQUESTED=1; return 1;; 0|b) return 1;; n) ((end<total)) && ((page+=1)); continue;; p) ((page>0)) && ((page-=1)); continue;; r) search=''; page=0; continue;;
        esac
        if [[ $input == /* ]]; then search=$input; page=0; continue; fi
        if [[ $input =~ ^[0-9]+$ ]] && ((10#$input>=1 && 10#$input<=total)); then REPLY=${visible[$((10#$input-1))]}; return 0; fi
        matches=(); for item in "${items[@]}"; do [[ ${item,,} == *"${input,,}"* ]] && matches+=("$item"); done
        if ((${#matches[@]}==1)); then REPLY=${matches[0]}; return 0
        elif ((${#matches[@]}>1)); then search=$input; page=0
        else search=$input; page=0; fi
    done
}

ui_menu_pair() {
    local left_num=$1 left_text=$2 right_num=$3 right_text=$4 leftw
    leftw=$((UI_COLS/2-2))
    printf ' [%2s] %-*s [%2s] %s\n' "$left_num" "$((leftw-7))" "$left_text" "$right_num" "$right_text"
}

ui_all_commands_report() {
    cat <<'COMMANDS'
PRIMARY / WORKLOADS
  1  All Pods / Resource Grid
  2  Live Pod Search / Filter
  3  Failed / Alert Pods
  4  Event Radar
  5  Container / Pod Deep Dive
  6  Performance & Observability
  9  Smart Health Inspector
 10  Resource Dependency Explorer

TOPOLOGY / PLATFORM
  7  Service & Network Topology
  8  Storage Dependency Audit
 21  Host Network Operations
 22  PostgreSQL / Generic DB
 23  Kafka Diagnostics
 24  Namespace / Context
 25  ETDP Platform Inspector

GITOPS / CONFIGURATION
 11  GitOps Command Center
 12  Revision / Drift Analyzer
 13  GitOps Dependency Graph
 14  Configuration Dependency Graph
 15  Image / Registry Audit

SECURITY / PKI / TLS
 16  Certificate Inventory
 17  Certificate Expiry Audit
 18  Trust Chain Analyzer
 19  Live TLS Inspector
 20  Certificate Dependency Graph

FORENSICS / OPERATIONS
 26  Incident Triage
 27  Evidence Collector
 28  Export Center
 29  Environment Doctor
 30  Self-Test
COMMANDS
}

paint_line() {
    local row=$1 line=$2
    line=$(truncate_text "$line" "$((UI_COLS-1))")
    if [[ ${UI_PREVIOUS[$row]:-__unset__} != "$line" ]]; then
        if ((UI_ACTIVE)); then printf '\033[%s;1H\033[2K%s' "$row" "$line"; else printf '%s\n' "$line"; fi
        UI_PREVIOUS[$row]=$line
    fi
}

paint_frame() {
    local title=$1 footer=$2 health
    terminal_size; health=$(ui_global_health)
    paint_line 1 "$(ui_repeat '=' "$((UI_COLS-1))")"
    if [[ $UI_LAYOUT == COMPACT ]]; then
        paint_line 2 "$APP_NAME v$APP_VERSION | $title"
        paint_line 3 "CTX $SENTINEL_CONTEXT | NS $SENTINEL_NAMESPACE"
        paint_line 4 "USER $AUTH_USER | MODE READ ONLY | HEALTH $health"
    else
        paint_line 2 "$APP_NAME v$APP_VERSION | KUBERNETES / GITOPS / PKI OPERATIONS CONSOLE | $UI_LAYOUT"
        paint_line 3 "CONTEXT $SENTINEL_CONTEXT | NAMESPACE $SENTINEL_NAMESPACE | USER $AUTH_USER | MODE SUPERVISION [READ ONLY]"
        paint_line 4 "HEALTH $health | AUTH $AUTH_STATUS | API $API_STATUS | RBAC $RBAC_STATUS"
    fi
    paint_line 5 "$(ui_repeat '-' "$((UI_COLS-1))")"
    paint_line "$((UI_ROWS-2))" "$(ui_repeat '-' "$((UI_COLS-1))")"
    paint_line "$((UI_ROWS-1))" "$footer"
    paint_line "$UI_ROWS" "Source: cached/lazy | Layout: $UI_LAYOUT | Updated: $(ui_time_local)"
}

paint_report() {
    local file=$1 line row=6 last=$((UI_ROWS-3))
    while IFS= read -r line; do
        ((row<=last)) || break
        paint_line "$row" "$line"; ((row+=1))
    done < <(tail -n +3 -- "$file" | format_table "$UI_COLS")
    while ((row<=last)); do paint_line "$row" ''; ((row+=1)); done
    ((UI_ACTIVE)) && printf '\033[%s;1H' "$((UI_ROWS-1))"
}

# Dashboard content does not invoke cluster scans. It reflects only already cached
# information and preserves the fast-startup/lazy-collection contract.
ui_snapshot_report() {
    render_header 'ONE-SHOT OPERATIONS SNAPSHOT'
    render_section 'CURRENT SCOPE'
    render_kv 'Context' "$SENTINEL_CONTEXT"; render_kv 'Namespace' "$SENTINEL_NAMESPACE"; render_kv 'User' "$AUTH_USER"
    render_section 'CORRELATED TRIAGE'
    triage_report
    render_footer
}

# Deterministic UI process tests: width modes, no-color, ASCII/Unicode, critical
# layout width, status vocabulary and copy/paste safety.
ui_process_self_tests() (
    local old_cols=${COLUMNS-} old_lines=${LINES-} old_no=$NO_COLOR_FLAG old_unicode=${DEVOPSSENTINEL_UNICODE-auto} width out maxlen
    NO_COLOR_FLAG=1 TERM=dumb LINES=40
    for width in 80 120 160; do
        COLUMNS=$width; terminal_size; color_init
        case $width in 80) [[ $UI_LAYOUT == COMPACT ]] || return 1;; 120) [[ $UI_LAYOUT == STANDARD ]] || return 1;; 160) [[ $UI_LAYOUT == WIDE ]] || return 1;; esac
        out=$(dashboard_report)
        maxlen=$(printf '%s\n' "$out" | awk '{if(length($0)>m)m=length($0)} END{print m+0}')
        ((maxlen <= width+5)) || { printf 'UI width overflow at %s: %s\n' "$width" "$maxlen" >&2; return 1; }
    done
    COLUMNS=120 DEVOPSSENTINEL_UNICODE=off; terminal_size; [[ $UI_ASCII == 1 && $UI_TREE_MID == '|--' ]] || return 1
    DEVOPSSENTINEL_UNICODE=on; terminal_size; [[ $UI_ASCII == 0 ]] || return 1
    out=$(status_label CRITICAL); [[ $out == *'[CRIT]'* && $out != *$'\033'* ]] || return 1
    out=$(render_header UI-TEST); [[ $out != *$'\033'* ]] || return 1
    printf 'PASS UI widths 80/120/160, NO_COLOR, Unicode/ASCII fallback, status language and redirected output\n'
)

# ==============================================================================
# 20 Advanced operator workspace layer (v4.2)
# Adds universal search, history/pins, findings, relationship navigation,
# timelines, change detection, incident sessions, API-load protection and
# deterministic advanced UI tests. All state remains local under SNTL_HOME.
# ==============================================================================

UI_DEBUG_FLAG=${UI_DEBUG_FLAG:-0}
INCIDENT_ID=${INCIDENT_ID:-}
INCIDENT_DIR=''
SESSION_STARTED_EPOCH=0
UI_HISTORY_FILE=''
UI_PIN_FILE=''
UI_FAVORITE_NS_FILE=''
UI_SEARCH_INDEX=''
UI_RELATION_INDEX=''
UI_CHANGE_PREV=''
UI_CHANGE_CURR=''
UI_SESSION_SUMMARY_DONE=0
UI_LAST_RESOURCE_TYPE=''
UI_LAST_RESOURCE_NAME=''
UI_LAST_RESOURCE_NS=''
UI_LAST_QUERY_CALLS=0
UI_LAST_QUERY_MS=0
UI_LIVE_INTERVAL=${UI_LIVE_INTERVAL:-10}
UI_LIVE_MIN_INTERVAL=5
UI_PERSONA=${DEVOPSSENTINEL_PERSONA:-STANDARD}
UI_FINDINGS_REFRESHED=0
UI_PENDING_ACTION=''
UI_ACTIVE_FILTER='none'
UI_ACTIVE_SORT='severity'

advanced_runtime_init() {
    SESSION_STARTED_EPOCH=$(now_epoch)
    UI_HISTORY_FILE="$SNTL_HISTORY_DIR/recent.tsv"
    UI_PIN_FILE="$SNTL_HISTORY_DIR/pinned.tsv"
    UI_FAVORITE_NS_FILE="$SNTL_HISTORY_DIR/favorite_namespaces.tsv"
    UI_SEARCH_INDEX="$RUN_DIR/resource-index.tsv"
    UI_RELATION_INDEX="$RUN_DIR/relationships.tsv"
    UI_CHANGE_PREV="$RUN_DIR/change.previous.tsv"
    UI_CHANGE_CURR="$RUN_DIR/change.current.tsv"
    touch "$UI_HISTORY_FILE" "$UI_PIN_FILE" "$UI_FAVORITE_NS_FILE" || return 2
    chmod 600 "$UI_HISTORY_FILE" "$UI_PIN_FILE" "$UI_FAVORITE_NS_FILE" 2>/dev/null || :
    if [[ -n $INCIDENT_ID ]]; then
        INCIDENT_ID=$(safe_id "$INCIDENT_ID")
        INCIDENT_DIR="$SNTL_EVIDENCE_DIR/$INCIDENT_ID"
        mkdir -p "$INCIDENT_DIR"/{exports,notes,session} || return 2
        chmod 700 "$INCIDENT_DIR" "$INCIDENT_DIR"/* 2>/dev/null || :
        chmod g-s "$INCIDENT_DIR" "$INCIDENT_DIR"/* 2>/dev/null || :
        SNTL_EXPORT_DIR="$INCIDENT_DIR/exports"
        log_audit "incident_session=$INCIDENT_ID"
    fi
}

advanced_session_summary() {
    ((UI_SESSION_SUMMARY_DONE==0)) || return 0
    UI_SESSION_SUMMARY_DONE=1
    [[ -n $INCIDENT_DIR && -d $INCIDENT_DIR ]] || return 0
    local now duration inspected findings exports out
    now=$(now_epoch); duration=$((now-SESSION_STARTED_EPOCH)); ((duration<0)) && duration=0
    inspected=$(awk -F '\t' -v c="$SENTINEL_CONTEXT" -v n="$SENTINEL_NAMESPACE" '$2==c && $3==n {k=$4"/"$5; seen[k]=1} END{for(k in seen)x++; print x+0}' "$UI_HISTORY_FILE" 2>/dev/null)
    findings=$(wc -l < "$RUN_DIR/findings.tsv" 2>/dev/null | awk '{print $1+0}')
    exports=$(find "$INCIDENT_DIR/exports" -maxdepth 1 -type f 2>/dev/null | wc -l | awk '{print $1+0}')
    out="$INCIDENT_DIR/session/session-summary.txt"
    {
        printf 'DEVOPSSENTINEL INCIDENT SESSION SUMMARY\n'
        printf 'Incident       : %s\n' "$INCIDENT_ID"
        printf 'Context        : %s\n' "$SENTINEL_CONTEXT"
        printf 'Namespace      : %s\n' "$SENTINEL_NAMESPACE"
        printf 'Duration       : %ss\n' "$duration"
        printf 'Resources seen : %s\n' "$inspected"
        printf 'Findings       : %s\n' "$findings"
        printf 'Exports        : %s\n' "$exports"
        printf 'Ended          : %s\n' "$(timestamp)"
        if [[ -s $RUN_DIR/findings.tsv ]]; then
            printf '\nFINDINGS\n'; ui_findings_report
        fi
    } | redact > "$out"
    chmod 600 "$out" 2>/dev/null || :
}

# Preserve terminal restoration and child cleanup while adding optional incident summary.
cleanup() {
    local rc=$? p log_target
    trap - EXIT INT TERM HUP
    advanced_session_summary 2>/dev/null || :
    for p in "${ACTIVE_PIDS[@]}"; do kill_tree "$p"; done
    if [[ -t 1 && ${TERM:-dumb} != dumb ]]; then
        printf '\033[0m\033[?25h'
        ((UI_ACTIVE)) && printf '\033[?1049l'
    fi
    if [[ -n ${UI_STTY:-} ]] && has stty; then stty "$UI_STTY" 2>/dev/null || :; fi
    if [[ -n ${RUN_DIR:-} && -d ${RUN_DIR:-} && $RUN_DIR == "$SNTL_RUNTIME_DIR/"* && ! -L $RUN_DIR ]]; then
        if [[ -s $RUN_DIR/application.log ]]; then
            log_target="$SNTL_LOG_DIR/application-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
            cp -- "$RUN_DIR/application.log" "$log_target" 2>/dev/null || :
            chmod 600 "$log_target" 2>/dev/null || :
        fi
        rm -rf -- "$RUN_DIR"
    fi
    unset SPLUNK_TOKEN PGPASSWORD PGPASSFILE KAFKA_OPTS
    return "$rc"
}

ui_history_add() {
    local type=$1 name=$2 ns=${3:-$SENTINEL_NAMESPACE} tmp
    [[ -n ${UI_HISTORY_FILE:-} && -f $UI_HISTORY_FILE && -n $type && -n $name ]] || return 0
    printf '%s\t%s\t%s\t%s\t%s\n' "$(timestamp)" "$SENTINEL_CONTEXT" "$ns" "$type" "$name" | redact >> "$UI_HISTORY_FILE"
    tmp=$(mktemp "$RUN_DIR/history.XXXXXXXX") || return 0
    awk -F '\t' 'NF>=5 {key=$2 FS $3 FS $4 FS $5; if(!seen[key]++){row[key]=$0; order[++n]=key}} END{start=n-199; if(start<1)start=1; for(i=start;i<=n;i++) print row[order[i]]}' "$UI_HISTORY_FILE" > "$tmp" 2>/dev/null || :
    mv "$tmp" "$UI_HISTORY_FILE" 2>/dev/null || :
    chmod 600 "$UI_HISTORY_FILE" 2>/dev/null || :
}

ui_history_report() {
    printf 'RECENT RESOURCES | context=%s namespace=%s\n' "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE"
    printf '#\tTYPE\tNAME\tLAST OPENED\n'
    awk -F '\t' -v c="$SENTINEL_CONTEXT" -v n="$SENTINEL_NAMESPACE" '$2==c && $3==n {rows[++x]=$0} END{start=x-29;if(start<1)start=1; idx=0; for(i=x;i>=start;i--){split(rows[i],a,FS); printf "%d\t%s\t%s\t%s\n",++idx,a[4],a[5],a[1]}}' "$UI_HISTORY_FILE" 2>/dev/null
}

ui_pin_add() {
    local type=$1 name=$2 ns=${3:-$SENTINEL_NAMESPACE}
    grep -Fqx "$SENTINEL_CONTEXT"$'\t'"$ns"$'\t'"$type"$'\t'"$name" "$UI_PIN_FILE" 2>/dev/null || printf '%s\t%s\t%s\t%s\n' "$SENTINEL_CONTEXT" "$ns" "$type" "$name" >> "$UI_PIN_FILE"
    chmod 600 "$UI_PIN_FILE" 2>/dev/null || :
}

ui_pin_remove() {
    local type=$1 name=$2 ns=${3:-$SENTINEL_NAMESPACE} tmp
    tmp=$(mktemp "$RUN_DIR/pins.XXXXXXXX") || return 1
    awk -F '\t' -v c="$SENTINEL_CONTEXT" -v n="$ns" -v t="$type" -v x="$name" '!(NF>=4 && $1==c && $2==n && $3==t && $4==x)' "$UI_PIN_FILE" > "$tmp"
    mv "$tmp" "$UI_PIN_FILE"; chmod 600 "$UI_PIN_FILE" 2>/dev/null || :
}

ui_pins_report() {
    printf 'PINNED RESOURCES | context=%s namespace=%s\n' "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE"
    printf '#\tTYPE\tNAME\tSTATUS\n'
    local i=0 type name
    while IFS=$'\t' read -r _c _n type name; do
        [[ $_c == "$SENTINEL_CONTEXT" && $_n == "$SENTINEL_NAMESPACE" ]] || continue
        ((i+=1)); printf '%d\t%s\t%s\t%s\n' "$i" "$type" "$name" "$(ui_resource_cached_status "$type" "$name")"
    done < "$UI_PIN_FILE"
    ((i)) || printf -- '-\t-\tNo pinned resources for current scope\tNOTICE\n'
}

favorite_namespace_toggle() {
    local ns=${1:-$SENTINEL_NAMESPACE} tmp
    if grep -Fqx "$SENTINEL_CONTEXT"$'\t'"$ns" "$UI_FAVORITE_NS_FILE" 2>/dev/null; then
        tmp=$(mktemp "$RUN_DIR/favns.XXXXXXXX") || return 1
        awk -F '\t' -v c="$SENTINEL_CONTEXT" -v n="$ns" '!($1==c && $2==n)' "$UI_FAVORITE_NS_FILE" > "$tmp"
        mv "$tmp" "$UI_FAVORITE_NS_FILE"
        printf 'Favorite removed: %s\n' "$ns"
    else
        printf '%s\t%s\n' "$SENTINEL_CONTEXT" "$ns" >> "$UI_FAVORITE_NS_FILE"
        printf 'Favorite added: %s\n' "$ns"
    fi
    chmod 600 "$UI_FAVORITE_NS_FILE" 2>/dev/null || :
}

ui_resource_cached_status() {
    local type=${1,,} name=$2 f
    has jq || { printf 'UNKNOWN'; return; }
    case $type in
        pod)
            f=$(json_cache_path pods); jq -r --arg n "$name" '[.items[]|select(.metadata.name==$n)][0] as $x | if $x==null then "UNKNOWN" else (($x.status.containerStatuses[]?.state.waiting.reason // empty) // $x.status.reason // $x.status.phase // "UNKNOWN") end' "$f" 2>/dev/null || printf 'UNKNOWN';;
        deployment|statefulset|daemonset|replicaset|job|cronjob)
            f=$(json_cache_path workloads); jq -r --arg n "$name" '[.items[]|select(.metadata.name==$n)][0] as $x | if $x==null then "UNKNOWN" elif any($x.status.conditions[]?;.type=="Available" and .status=="False") then "WARNING" else "READY" end' "$f" 2>/dev/null || printf 'UNKNOWN';;
        pvc) f=$(json_cache_path pvcs); jq -r --arg n "$name" '[.items[]|select(.metadata.name==$n)][0].status.phase // "UNKNOWN"' "$f" 2>/dev/null || printf 'UNKNOWN';;
        helmrelease) f=$(json_cache_path flux_helmreleases); jq -r --arg n "$name" '[.items[]|select(.metadata.name==$n)][0] | ([.status.conditions[]?|select(.type=="Ready")][0].status // "UNKNOWN")' "$f" 2>/dev/null || printf 'UNKNOWN';;
        kustomization) f=$(json_cache_path flux_kustomizations); jq -r --arg n "$name" '[.items[]|select(.metadata.name==$n)][0] | ([.status.conditions[]?|select(.type=="Ready")][0].status // "UNKNOWN")' "$f" 2>/dev/null || printf 'UNKNOWN';;
        gitrepository) f=$(json_cache_path flux_gitrepositories); jq -r --arg n "$name" '[.items[]|select(.metadata.name==$n)][0] | ([.status.conditions[]?|select(.type=="Ready")][0].status // "UNKNOWN")' "$f" 2>/dev/null || printf 'UNKNOWN';;
        certificate) f=$(json_cache_path cert_certificates); jq -r --arg n "$name" '[.items[]|select(.metadata.name==$n)][0] | ([.status.conditions[]?|select(.type=="Ready")][0].status // "UNKNOWN")' "$f" 2>/dev/null || printf 'UNKNOWN';;
        *) printf 'INFO';;
    esac
}

ui_severity_rank() {
    case $(ui_status_kind "$1") in CRITICAL) printf 1;; FAILED) printf 2;; WARNING) printf 3;; UNKNOWN) printf 4;; NOTICE) printf 5;; INFO) printf 6;; OK) printf 7;; *) printf 8;; esac
}

ui_findings_report() {
    printf 'SESSION FINDINGS | context=%s namespace=%s\n' "$SENTINEL_CONTEXT" "$SENTINEL_NAMESPACE"
    printf 'ID\tSEVERITY\tDOMAIN\tRESOURCE\tFINDING\tEVIDENCE\n'
    if [[ ! -s $RUN_DIR/findings.tsv ]]; then printf -- '-\tNOTICE\t-\t-\tNo findings collected in this session\tRun Incident Triage\n'; return; fi
    awk -F '\t' '
      function rank(s){s=toupper(s); if(s=="CRITICAL")return 1;if(s=="FAIL"||s=="FAILED")return 2;if(s=="WARN"||s=="WARNING")return 3;if(s=="UNKNOWN")return 4;if(s=="INFO")return 6;return 5}
      NF>=4 {sev=$1; dom=$2; res=$3; msg=$4; ev=(NF>=5?$5:"-"); rows[++n]=sprintf("%d\t%s\t%s\t%s\t%s\t%s",rank(sev),sev,dom,res,msg,ev)}
      END{for(i=1;i<=n;i++)for(j=i+1;j<=n;j++){split(rows[i],a,"\t");split(rows[j],b,"\t");if((a[1]+0)>(b[1]+0)){t=rows[i];rows[i]=rows[j];rows[j]=t}};for(i=1;i<=n;i++){sub(/^[^\t]+\t/,"",rows[i]);printf "F-%03d\t%s\n",i,rows[i]}}' "$RUN_DIR/findings.tsv"
}

ui_findings_refresh() {
    ((UI_FINDINGS_REFRESHED==0)) || return 0
    triage_report >/dev/null 2>&1 || :
    UI_FINDINGS_REFRESHED=1
}

ui_findings_menu() {
    ui_findings_refresh
    show_report 'FINDINGS — SESSION QUEUE' ui_findings_report
}

advanced_collect_search_sources() {
    local start end
    start=$(date +%s%3N 2>/dev/null); [[ $start =~ ^[0-9]+$ ]] || start=$(($(date +%s)*1000))
    UI_LAST_QUERY_CALLS=0
    collect_pods; ((UI_LAST_QUERY_CALLS+=1))
    collect_workloads; ((UI_LAST_QUERY_CALLS+=1))
    collect_network; ((UI_LAST_QUERY_CALLS+=4))
    collect_storage; ((UI_LAST_QUERY_CALLS+=1))
    collect_json adv_configmaps 15 ns configmaps '{items:[.items[]?|{kind,metadata:{name:.metadata.name,namespace:.metadata.namespace,creationTimestamp:.metadata.creationTimestamp}}]}' 'NAME:.metadata.name' || :; ((UI_LAST_QUERY_CALLS+=1))
    collect_json adv_secrets 15 ns secrets '{items:[.items[]?|{kind,metadata:{name:.metadata.name,namespace:.metadata.namespace,creationTimestamp:.metadata.creationTimestamp},type}]}' 'NAME:.metadata.name,TYPE:.type' || :; ((UI_LAST_QUERY_CALLS+=1))
    gitops_collect; ((UI_LAST_QUERY_CALLS+=4))
    cert_manager_collect; ((UI_LAST_QUERY_CALLS+=1))
    collect_json adv_namespaces 60 cluster namespaces '{items:[.items[]?|{kind,metadata:{name:.metadata.name,creationTimestamp:.metadata.creationTimestamp},status:{phase:.status.phase}}]}' 'NAME:.metadata.name,STATUS:.status.phase' || :; ((UI_LAST_QUERY_CALLS+=1))
    end=$(date +%s%3N 2>/dev/null); [[ $end =~ ^[0-9]+$ ]] || end=$(($(date +%s)*1000))
    UI_LAST_QUERY_MS=$((end-start))
}

ui_build_resource_index() {
    : > "$UI_SEARCH_INDEX"
    has jq || { printf 'jq is required for universal resource indexing.\n' >&2; return 2; }
    advanced_collect_search_sources
    local ns=$SENTINEL_NAMESPACE f
    f=$(json_cache_path pods)
    jq -r '.items[]?|["Pod",.metadata.name,.metadata.namespace,((.status.containerStatuses[]?.state.waiting.reason // empty) // .status.reason // .status.phase // "UNKNOWN"),"Kubernetes API"]|@tsv' "$f" >> "$UI_SEARCH_INDEX"
    f=$(json_cache_path workloads)
    jq -r '.items[]?|[.kind,.metadata.name,.metadata.namespace,(if any(.status.conditions[]?;.status=="False" and (.type=="Available" or .type=="Ready" or .type=="Complete")) then "WARNING" else "READY" end),"Kubernetes API"]|@tsv' "$f" >> "$UI_SEARCH_INDEX"
    f=$(json_cache_path services); jq -r '.items[]?|["Service",.metadata.name,.metadata.namespace,(.spec.type // "Active"),"Kubernetes API"]|@tsv' "$f" >> "$UI_SEARCH_INDEX"
    f=$(json_cache_path adv_configmaps); jq -r '.items[]?|["ConfigMap",.metadata.name,.metadata.namespace,"INFO","Kubernetes API"]|@tsv' "$f" >> "$UI_SEARCH_INDEX"
    f=$(json_cache_path adv_secrets); jq -r '.items[]?|["Secret",.metadata.name,.metadata.namespace,"INFO","Kubernetes API (name only)"]|@tsv' "$f" >> "$UI_SEARCH_INDEX"
    f=$(json_cache_path pvcs); jq -r '.items[]?|["PVC",.metadata.name,.metadata.namespace,(.status.phase // "UNKNOWN"),"Kubernetes API"]|@tsv' "$f" >> "$UI_SEARCH_INDEX"
    for fkey in flux_gitrepositories flux_kustomizations flux_helmreleases; do
        f=$(json_cache_path "$fkey")
        jq -r '.items[]?|[.kind,.metadata.name,.metadata.namespace,(([.status.conditions[]?|select(.type=="Ready")][0].status)//"UNKNOWN"),"Flux status"]|@tsv' "$f" >> "$UI_SEARCH_INDEX" 2>/dev/null || :
    done
    f=$(json_cache_path cert_certificates)
    jq -r '.items[]?|["Certificate",.metadata.name,.metadata.namespace,(([.status.conditions[]?|select(.type=="Ready")][0].status)//"UNKNOWN"),"cert-manager status"]|@tsv' "$f" >> "$UI_SEARCH_INDEX" 2>/dev/null || :
    f=$(json_cache_path adv_namespaces); jq -r '.items[]?|["Namespace",.metadata.name,"-",(.status.phase // "UNKNOWN"),"Kubernetes API"]|@tsv' "$f" >> "$UI_SEARCH_INDEX"
    cat >> "$UI_SEARCH_INDEX" <<'ACTIONS'
Action	Incident Triage	-	COMMAND	Menu
Action	Session Findings	-	COMMAND	Menu
Action	GitOps Command Center	-	COMMAND	Menu
Action	Certificate Expiry	-	COMMAND	Menu
Action	Network Topology	-	COMMAND	Menu
Action	Storage Audit	-	COMMAND	Menu
Action	Environment Doctor	-	COMMAND	Menu
ACTIONS
    sort -t $'\t' -k1,1 -k2,2 "$UI_SEARCH_INDEX" -o "$UI_SEARCH_INDEX"
    chmod 600 "$UI_SEARCH_INDEX" 2>/dev/null || :
}

ui_search_matches() {
    local term=$1 out=$2 regex=0 pattern
    : > "$out"
    if [[ $term == /* ]]; then regex=1; pattern=${term#/}; else pattern=$term; fi
    if ((regex)); then
        awk -F '\t' -v q="$pattern" 'BEGIN{IGNORECASE=1} $1~q || $2~q || $3~q || $4~q {print}' "$UI_SEARCH_INDEX" > "$out" 2>/dev/null || return 2
    else
        awk -F '\t' -v q="${pattern,,}" 'BEGIN{IGNORECASE=1} index(tolower($1),q)||index(tolower($2),q)||index(tolower($3),q)||index(tolower($4),q){print}' "$UI_SEARCH_INDEX" > "$out"
    fi
}

ui_action_dispatch() {
    local label=${1,,}
    case $label in
        *incident*triage*) show_report 'INCIDENT — TRIAGE' triage_report;;
        *findings*) ui_findings_menu;;
        *gitops*) gitops_menu;;
        *certificate*expiry*) show_report 'PKI/TLS — CERTIFICATE EXPIRY' cert_expiry_audit;;
        *network*) show_report 'NETWORK — SERVICE TOPOLOGY' service_topology_report;;
        *storage*) show_report 'STORAGE — DEPENDENCY AUDIT' storage_dependency_report;;
        *doctor*) show_report 'PLATFORM — ENVIRONMENT DOCTOR' devopssentinel_doctor_report;;
    esac
}

ui_resource_overview_report() {
    local type=$1 name=$2 ns=${3:-$SENTINEL_NAMESPACE}
    printf '%s — RESOURCE DETAIL\n' "${type^^}"
    printf 'TYPE\t%s\nNAME\t%s\nNAMESPACE\t%s\nSTATUS\t%s\n' "$type" "$name" "$ns" "$(ui_resource_cached_status "$type" "$name")"
    printf '\nRELATED / DEPENDENCIES\n'
    resource_dependencies "$type" "$ns" "$name" 2>/dev/null || :
}

ui_certificate_detail_report() {
    local name=$1
    cert_manager_collect; tls_secret_metadata_collect; cert_ingress_collect
    printf 'PKI/TLS — CERTIFICATE DETAIL\n'
    printf 'Certificate\t%s\nNamespace\t%s\n' "$name" "$SENTINEL_NAMESPACE"
    if has jq; then
        jq -r --arg n "$name" '.items[]?|select(.metadata.name==$n)|
          ["Ready",(([.status.conditions[]?|select(.type=="Ready")][0].status)//"UNKNOWN")],
          ["Secret",(.spec.secretName // "UNKNOWN")],
          ["Issuer",((.spec.issuerRef.kind // "Issuer")+"/"+(.spec.issuerRef.name // "UNKNOWN"))],
          ["Renewal",(.status.renewalTime // "UNKNOWN")],
          ["Not After",(.status.notAfter // "UNKNOWN")],
          ["DNS names",((.spec.dnsNames // [])|length|tostring)] | @tsv' "$(json_cache_path cert_certificates)" 2>/dev/null || :
    fi
    printf '\nCONSUMERS\n'; resource_consumers Certificate "$SENTINEL_NAMESPACE" "$name" 2>/dev/null || :
}

ui_gitops_detail_report() {
    local type=$1 name=$2 key
    case ${type,,} in gitrepository) key=flux_gitrepositories;; kustomization) key=flux_kustomizations;; helmrelease) key=flux_helmreleases;; *) return 2;; esac
    gitops_collect
    printf 'GITOPS — %s DETAIL\n' "${type^^}"
    jq -r --arg n "$name" '.items[]?|select(.metadata.name==$n)|
      ["Name",.metadata.name],
      ["Ready",(([.status.conditions[]?|select(.type=="Ready")][0].status)//"UNKNOWN")],
      ["Reason",(([.status.conditions[]?|select(.type=="Ready")][0].reason)//"UNKNOWN")],
      ["Last transition",(([.status.conditions[]?|select(.type=="Ready")][0].lastTransitionTime)//"UNKNOWN")],
      ["Artifact revision",(.status.artifact.revision // "-")],
      ["Applied revision",(.status.lastAppliedRevision // "-")],
      ["Attempted revision",(.status.lastAttemptedRevision // "-")],
      ["Observed generation",((.status.observedGeneration // "UNKNOWN")|tostring)] | @tsv' "$(json_cache_path "$key")" 2>/dev/null || :
    printf '\nSTATUS PATH / DEPENDENCIES\n'; gitops_dependency_report "$type" "$name" 2>/dev/null || :
}

event_timeline_report() {
    local type=$1 name=$2
    collect_events
    printf 'EVENTS — RESOURCE TIMELINE\nResource\t%s/%s\n\nTIME\tTYPE\tREASON\tMESSAGE\tCOUNT\n' "$type" "$name"
    has jq || { fallback_report events; return; }
    jq -r --arg k "$type" --arg n "$name" '[.items[]?|select((.involvedObject.kind|ascii_downcase)==($k|ascii_downcase) and .involvedObject.name==$n)|
      [(.eventTime // .lastTimestamp // .metadata.creationTimestamp // "UNKNOWN"),(.type // "UNKNOWN"),(.reason // "-"),(.message // "-"),((.series.count // .count // 1)|tostring)]] | sort_by(.[0])[] | @tsv' "$(json_cache_path events)"
}

incident_timeline_report() {
    collect_events; collect_workloads; gitops_collect
    local tmp="$RUN_DIR/incident-timeline.tsv"; : > "$tmp"
    if has jq; then
        jq -r '.items[]?|[(.eventTime // .lastTimestamp // .metadata.creationTimestamp // "UNKNOWN"),"KubernetesEvent",((.involvedObject.kind // "Object")+"/"+(.involvedObject.name // "UNKNOWN")),(.reason // "Event"),(.message // "-")]|@tsv' "$(json_cache_path events)" >> "$tmp" 2>/dev/null || :
        jq -r '.items[]?|[.metadata.creationTimestamp,"Workload",(.kind+"/"+.metadata.name),"Created","generation="+((.metadata.generation // 0)|tostring)]|@tsv' "$(json_cache_path workloads)" >> "$tmp" 2>/dev/null || :
        for key in flux_gitrepositories flux_kustomizations flux_helmreleases; do
            jq -r '.items[]? as $x | $x.status.conditions[]? | select(.lastTransitionTime!=null) | [.lastTransitionTime,"Flux",($x.kind+"/"+$x.metadata.name),(.reason // .type),(.message // "-")]|@tsv' "$(json_cache_path "$key")" >> "$tmp" 2>/dev/null || :
        done
    fi
    printf 'INCIDENT — EVIDENCE TIMELINE\n'
    printf 'Only timestamped evidence is shown; temporal proximity does not prove causation.\n\n'
    printf 'TIME\tSOURCE\tRESOURCE\tEVENT\tDETAIL\n'
    sort -t $'\t' -k1,1 "$tmp" | tail -n 200
}

ui_relationship_index_build() {
    : > "$UI_RELATION_INDEX"
    collect_pods; collect_workloads; collect_network; collect_storage; gitops_collect; cert_manager_collect
    has jq || return 2
    local pods services
    pods=$(json_cache_path pods); services=$(json_cache_path services)
    jq -r '
      def ctrl: ([.metadata.ownerReferences[]?|select(.controller==true)][0] // .metadata.ownerReferences[0]);
      .items[]? as $p |
      (ctrl | select(.!=null) | [$p.metadata.namespace,(.kind+"/"+.name),("Pod/"+$p.metadata.name),"OWNER"]|@tsv),
      ($p.spec.volumes[]? | if .secret.secretName then [$p.metadata.namespace,("Pod/"+$p.metadata.name),("Secret/"+.secret.secretName),"USES"]|@tsv elif .configMap.name then [$p.metadata.namespace,("Pod/"+$p.metadata.name),("ConfigMap/"+.configMap.name),"USES"]|@tsv elif .persistentVolumeClaim.claimName then [$p.metadata.namespace,("Pod/"+$p.metadata.name),("PVC/"+.persistentVolumeClaim.claimName),"USES"]|@tsv else empty end)' "$pods" >> "$UI_RELATION_INDEX" 2>/dev/null || :
    jq -r --slurpfile sx "$services" '.items[]? as $p | $p.metadata.labels as $lbl | $sx[0].items[]? | select(.spec.selector!=null) as $s | select([$s.spec.selector|to_entries[]|($lbl[.key]//"")==.value]|all) | [$p.metadata.namespace,("Service/"+$s.metadata.name),("Pod/"+$p.metadata.name),"SELECTS"]|@tsv' "$pods" >> "$UI_RELATION_INDEX" 2>/dev/null || :
    local src ks hr
    src=$(json_cache_path flux_gitrepositories); ks=$(json_cache_path flux_kustomizations); hr=$(json_cache_path flux_helmreleases)
    jq -r '.items[]? | select(.spec.sourceRef.kind=="GitRepository") | [.metadata.namespace,("GitRepository/"+.spec.sourceRef.name),("Kustomization/"+.metadata.name),"SOURCE"]|@tsv' "$ks" >> "$UI_RELATION_INDEX" 2>/dev/null || :
    jq -r '.items[]? | select(.spec.sourceRef.kind=="Kustomization") | [.metadata.namespace,("Kustomization/"+.spec.sourceRef.name),("HelmRelease/"+.metadata.name),"DEPENDS"]|@tsv' "$hr" >> "$UI_RELATION_INDEX" 2>/dev/null || :
    # Helm ownership labels/annotations are explicit evidence where projected.
    jq -r '.items[]?|select(.metadata.labels["helm.toolkit.fluxcd.io/name"]!=null)|[.metadata.namespace,("HelmRelease/"+.metadata.labels["helm.toolkit.fluxcd.io/name"]),(.kind+"/"+.metadata.name),"OWNS_LABEL"]|@tsv' "$(json_cache_path workloads)" >> "$UI_RELATION_INDEX" 2>/dev/null || :
    jq -r '.items[]?|select(.spec.secretName!=null)|[.metadata.namespace,("Certificate/"+.metadata.name),("Secret/"+.spec.secretName),"ISSUES"]|@tsv' "$(json_cache_path cert_certificates)" >> "$UI_RELATION_INDEX" 2>/dev/null || :
    chmod 600 "$UI_RELATION_INDEX" 2>/dev/null || :
}

ui_blast_radius_report() {
    local type=$1 name=$2 target="$type/$name" count
    [[ -s ${UI_RELATION_INDEX:-/nonexistent} && $FORCE_REFRESH == 0 ]] || ui_relationship_index_build || :
    printf 'DEPENDENCIES — REFERENCED BY\nResource\t%s\n\nTYPE\tCOUNT\n' "$target"
    awk -F '\t' -v t="$target" '$3==t {split($2,a,"/"); c[a[1]]++} END{for(k in c) printf "%s\t%d\n",k,c[k]}' "$UI_RELATION_INDEX" | sort
    printf '\nDIRECT REFERENCES\nSOURCE\tRELATION\n'
    awk -F '\t' -v t="$target" '$3==t {print $2"\t"$4}' "$UI_RELATION_INDEX" | sort -u
    count=$(awk -F '\t' -v t="$target" '$3==t{n++} END{print n+0}' "$UI_RELATION_INDEX")
    printf '\nConfirmed direct references: %s\n' "$count"
}

ui_dependency_path_report() {
    local from=$1 to=$2
    [[ -s ${UI_RELATION_INDEX:-/nonexistent} && $FORCE_REFRESH == 0 ]] || ui_relationship_index_build || return 2
    printf 'DEPENDENCY PATH FINDER\nFrom\t%s\nTo\t%s\n\n' "$from" "$to"
    awk -F '\t' -v start="$from" -v goal="$to" '
      {a=$2;b=$3; edge[a SUBSEP b]=$4; adj[a]=adj[a] "\034" b; radj[b]=radj[b] "\034" a}
      BEGIN{found=0}
      END{
        q[1]=start; head=1;tail=1; seen[start]=1
        while(head<=tail){u=q[head++]; if(u==goal){found=1;break}; n=split(adj[u],v,"\034"); for(i=1;i<=n;i++) if(v[i]!=""&&!seen[v[i]]){seen[v[i]]=1;prev[v[i]]=u;rel[v[i]]=edge[u SUBSEP v[i]];q[++tail]=v[i]}; n=split(radj[u],v,"\034"); for(i=1;i<=n;i++) if(v[i]!=""&&!seen[v[i]]){seen[v[i]]=1;prev[v[i]]=u;rel[v[i]]="REVERSE:" edge[v[i] SUBSEP u];q[++tail]=v[i]}}
        if(!found){print "No confirmed path in current local relationship index."; exit}
        n=0;x=goal; while(x!=""){path[++n]=x;if(x==start)break;x=prev[x]}; if(path[n]!=start){print "No confirmed path.";exit};
        for(i=n;i>=1;i--){printf "%s",path[i]; if(i>1) printf "\n  -> [%s]\n",rel[path[i-1]]; else printf "\n"}
      }' "$UI_RELATION_INDEX"
}

ui_change_capture() {
    local out=$1
    : > "$out"
    collect_pods; collect_workloads; gitops_collect; cert_manager_collect
    has jq || return 2
    jq -r '.items[]?|["Pod/"+.metadata.name,(.status.phase // "UNKNOWN"),([.status.containerStatuses[]?.restartCount // 0]|add // 0|tostring),([.spec.containers[]?.image]|join(","))]|@tsv' "$(json_cache_path pods)" >> "$out"
    jq -r '.items[]?|[.kind+"/"+.metadata.name,((.metadata.generation // 0)|tostring),((.status.observedGeneration // 0)|tostring),([.spec.template.spec.containers[]?.image]|join(","))]|@tsv' "$(json_cache_path workloads)" >> "$out"
    for key in flux_gitrepositories flux_kustomizations flux_helmreleases; do jq -r '.items[]?|[.kind+"/"+.metadata.name,(.status.artifact.revision // .status.lastAppliedRevision // .status.lastAttemptedRevision // "-"),((.status.observedGeneration // 0)|tostring),(([.status.conditions[]?|select(.type=="Ready")][0].status)//"UNKNOWN")]|@tsv' "$(json_cache_path "$key")" >> "$out" 2>/dev/null || :; done
    jq -r '.items[]?|["Certificate/"+.metadata.name,(.status.notAfter // "-"),(.spec.secretName // "-"),(([.status.conditions[]?|select(.type=="Ready")][0].status)//"UNKNOWN")]|@tsv' "$(json_cache_path cert_certificates)" >> "$out" 2>/dev/null || :
    sort -o "$out" "$out"
}

ui_change_report() {
    ui_change_capture "$UI_CHANGE_CURR" || { printf 'Change detection requires jq and available cached APIs.\n'; return 2; }
    printf 'SESSION — CHANGE DETECTION\n'
    if [[ ! -s $UI_CHANGE_PREV ]]; then cp "$UI_CHANGE_CURR" "$UI_CHANGE_PREV"; printf 'Baseline captured. Run again after refresh to detect session changes.\n'; return 0; fi
    printf 'RESOURCE\tPREVIOUS\tCURRENT\n'
    awk -F '\t' 'NR==FNR{old[$1]=$0;next}{cur[$1]=$0;if(old[$1]!=$0){printf "%s\t%s\t%s\n",$1,(old[$1]!=""?old[$1]:"<new>"),$0};seen[$1]=1} END{for(k in old)if(!seen[k])printf "%s\t%s\t<removed>\n",k,old[k]}' "$UI_CHANGE_PREV" "$UI_CHANGE_CURR"
    cp "$UI_CHANGE_CURR" "$UI_CHANGE_PREV"
}

ui_log_pattern_summary() {
    local file=$1
    [[ -f $file ]] || return 2
    printf 'LOGS — PATTERN SUMMARY\nPATTERN\tCOUNT\n'
    awk 'BEGIN{IGNORECASE=1}
      /connection refused/{c["Connection refused"]++}
      /certificate verify failed|x509:|unknown authority/{c["TLS/certificate verification"]++}
      /broken pipe|EPIPE/{c["Broken pipe"]++}
      /timed out|timeout/{c["Timeout"]++}
      /permission denied|forbidden/{c["Permission/RBAC"]++}
      /error/{c["Other ERROR lines"]++}
      END{for(k in c)print k"\t"c[k]}' "$file" | sort -t $'\t' -k2,2nr
    printf '\nFrequency is evidence of repetition, not proof of root cause.\n'
}

ui_log_context_report() {
    local file=$1 pattern=$2 before=${3:-10} after=${4:-10}
    [[ -f $file ]] || return 2
    printf 'LOGS — CONTEXT VIEW\nFilter\t%s\nContext\t%s before / %s after\n\n' "$pattern" "$before" "$after"
    awk -v q="$pattern" -v b="$before" -v a="$after" 'BEGIN{IGNORECASE=1}{line[NR]=$0;if($0~q){for(i=NR-b;i<=NR+a;i++)want[i]=1}}END{for(i=1;i<=NR;i++)if(want[i])print line[i]}' "$file" | redact
}

ui_logs_workspace() {
    local requested_pod=${1:-}
    if [[ -n $requested_pod ]]; then logs_capture "$RUN_DIR" "$requested_pod" || :; else logs_capture || :; fi
    [[ -f $CURRENT_REPORT ]] || return
    local log_file=$CURRENT_REPORT action pattern
    while choose 'LOG WORKSPACE' 'View captured logs' 'Search with context' 'Pattern summary' 'Export current logs' 'Back'; do
        action=$REPLY
        case $action in
            'View captured logs') view_file "$log_file" 'LOGS — CAPTURE';;
            'Search with context') prompt 'LOG REGEX >' || continue; pattern=$REPLY; capture_report 'LOGS — CONTEXT' ui_log_context_report "$log_file" "$pattern" 10 10; view_file "$CURRENT_REPORT" 'LOGS — CONTEXT';;
            'Pattern summary') show_report 'LOGS — PATTERN SUMMARY' ui_log_pattern_summary "$log_file";;
            'Export current logs') export_file "$log_file" logs txt;;
            Back) break;;
        esac
    done
}

ui_related_resources_report() {
    local type=$1 name=$2 target="$type/$name"
    [[ -s ${UI_RELATION_INDEX:-/nonexistent} && $FORCE_REFRESH == 0 ]] || ui_relationship_index_build || :
    printf 'RELATED — %s\n' "$target"
    printf 'DIRECTION\tRELATION\tRESOURCE\n'
    awk -F '\t' -v t="$target" '$2==t{print "OUT\t"$4"\t"$3} $3==t{print "IN\t"$4"\t"$2}' "$UI_RELATION_INDEX" | sort -u
}

ui_related_jump_menu() {
    local type=$1 name=$2 target="$type/$name" tmp="$RUN_DIR/related.tsv" total choice line direction relation resource rtype rname
    [[ -s ${UI_RELATION_INDEX:-/nonexistent} && $FORCE_REFRESH == 0 ]] || ui_relationship_index_build || return
    awk -F '\t' -v t="$target" '$2==t{print "OUT\t"$4"\t"$3} $3==t{print "IN\t"$4"\t"$2}' "$UI_RELATION_INDEX" | sort -u > "$tmp"
    total=$(wc -l < "$tmp" | awk '{print $1+0}')
    ((total)) || { printf 'No confirmed adjacent relationship in current local index.\n'; prompt 'Enter to return:' || :; return; }
    ui_clear_transition; ui_header 'RELATED RESOURCES' "DEVOPSSENTINEL > ${type^^} > RELATED"
    printf '#\tDIRECTION\tRELATION\tRESOURCE\n'; awk -F '\t' '{printf "%d\t%s\t%s\t%s\n",NR,$1,$2,$3}' "$tmp" | format_table "$UI_COLS"
    prompt 'JUMP TO # / 0 Back >' || return; choice=$REPLY
    [[ $choice =~ ^[0-9]+$ && 10#$choice -ge 1 && 10#$choice -le total ]] || return
    line=$(sed -n "${choice}p" "$tmp"); IFS=$'\t' read -r direction relation resource <<< "$line"
    rtype=${resource%%/*}; rname=${resource#*/}; [[ $rtype != "$rname" ]] || return
    ui_resource_native_open "$rtype" "$rname" "$SENTINEL_NAMESPACE"
}

ui_show_readonly_command() {
    local type=$1 name=$2 ns=${3:-$SENTINEL_NAMESPACE} api scope row
    case ${type,,} in
        pod) printf 'kubectl --context %q -n %q describe pod %q\n' "$SENTINEL_CONTEXT" "$ns" "$name";;
        helmrelease) printf 'kubectl --context %q -n %q get helmrelease.helm.toolkit.fluxcd.io %q -o yaml\n' "$SENTINEL_CONTEXT" "$ns" "$name";;
        kustomization) printf 'kubectl --context %q -n %q get kustomization.kustomize.toolkit.fluxcd.io %q -o yaml\n' "$SENTINEL_CONTEXT" "$ns" "$name";;
        gitrepository) printf 'kubectl --context %q -n %q get gitrepository.source.toolkit.fluxcd.io %q -o yaml\n' "$SENTINEL_CONTEXT" "$ns" "$name";;
        certificate) printf 'kubectl --context %q -n %q get certificate.cert-manager.io %q -o yaml\n' "$SENTINEL_CONTEXT" "$ns" "$name";;
        secret) printf 'kubectl --context %q -n %q get secret %q -o name\n' "$SENTINEL_CONTEXT" "$ns" "$name";;
        *)
            row=$(resource_lookup "$type" 2>/dev/null || :); IFS='|' read -r _ api scope <<< "$row"
            if [[ -n $api && $scope == ns ]]; then printf 'kubectl --context %q -n %q get %q %q -o yaml\n' "$SENTINEL_CONTEXT" "$ns" "$api" "$name"
            elif [[ -n $api ]]; then printf 'kubectl --context %q get %q %q -o yaml\n' "$SENTINEL_CONTEXT" "$api" "$name"
            else printf 'No canonical read-only command mapping is available for %s/%s.\n' "$type" "$name"; fi;;
    esac
}

ui_resource_workspace() {
    local type=$1 name=$2 ns=${3:-$SENTINEL_NAMESPACE} action
    UI_LAST_RESOURCE_TYPE=$type UI_LAST_RESOURCE_NAME=$name UI_LAST_RESOURCE_NS=$ns
    ui_history_add "$type" "$name" "$ns"
    log_audit "resource_open=$type/$name namespace=$ns"
    while :; do
        case ${type,,} in
            pod) choose "POD WORKSPACE — $name" Overview Logs Events Dependencies 'Referenced By' 'Related Jump' 'Show Command' 'Pin / Unpin' Back || return;;
            certificate) choose "CERTIFICATE WORKSPACE — $name" Details Expiry 'Trust / Relationships' Consumers 'GitOps / Dependencies' 'Related Jump' 'Show Command' 'Pin / Unpin' Back || return;;
            helmrelease|kustomization|gitrepository) choose "GITOPS WORKSPACE — $type/$name" Details Dependencies Timeline 'Related Jump' 'Show Command' 'Pin / Unpin' Back || return;;
            *) choose "RESOURCE WORKSPACE — $type/$name" Overview Dependencies 'Referenced By' Timeline 'Related Jump' 'Show Command' 'Pin / Unpin' Back || return;;
        esac
        action=$REPLY
        case $action in
            Overview) show_report "${type^^} — OVERVIEW" ui_resource_overview_report "$type" "$name" "$ns";;
            Details)
                case ${type,,} in certificate) show_report 'PKI/TLS — CERTIFICATE DETAIL' ui_certificate_detail_report "$name";; helmrelease|kustomization|gitrepository) show_report 'GITOPS — RESOURCE DETAIL' ui_gitops_detail_report "$type" "$name";; esac;;
            Logs) ui_logs_workspace "$name";;
            Events|Timeline) show_report "EVENTS — TIMELINE $type/$name" event_timeline_report "$type" "$name";;
            Dependencies|'GitOps / Dependencies') show_report "DEPENDENCIES — $type/$name" resource_dependencies "$type" "$ns" "$name";;
            'Referenced By'|Consumers) show_report "DEPENDENCIES — REFERENCED BY $type/$name" ui_blast_radius_report "$type" "$name";;
            'Related Jump') ui_related_jump_menu "$type" "$name";;
            'Show Command') ui_clear_transition; ui_header 'READ-ONLY COMMAND' "DEVOPSSENTINEL > ${type^^} > COMMAND"; ui_show_readonly_command "$type" "$name" "$ns"; prompt 'Enter to continue:' || :;;
            Expiry) show_report 'PKI/TLS — CERTIFICATE EXPIRY' cert_expiry_audit;;
            'Trust / Relationships') show_report 'PKI/TLS — CERTIFICATE RELATIONSHIPS' certificate_relationships_report;;
            'Pin / Unpin')
                if grep -Fqx "$SENTINEL_CONTEXT"$'\t'"$ns"$'\t'"$type"$'\t'"$name" "$UI_PIN_FILE" 2>/dev/null; then ui_pin_remove "$type" "$name" "$ns"; printf 'Unpinned %s/%s\n' "$type" "$name"; else ui_pin_add "$type" "$name" "$ns"; printf 'Pinned %s/%s\n' "$type" "$name"; fi
                prompt 'Enter to continue:' || :;;
            Back) return;;
        esac
        ((UI_MAIN_REQUESTED||UI_EXIT_REQUESTED)) && return
    done
}

ui_resource_native_open() {
    local type=$1 name=$2 ns=${3:-$SENTINEL_NAMESPACE}
    case ${type,,} in
        action) ui_action_dispatch "$name";;
        namespace)
            [[ $name == "$SENTINEL_NAMESPACE" ]] && return 0
            SENTINEL_NAMESPACE=$name
            rm -f -- "$CACHE_DIR"/*.json "$CACHE_DIR"/*.txt "$CACHE_DIR"/*.status "$CACHE_DIR"/*.time "$CACHE_DIR"/*.error 2>/dev/null || :
            GITOPS_STATUS=NOT_PROBED CERT_STATUS=NOT_PROBED METRICS_STATUS=NOT_PROBED UI_FINDINGS_REFRESHED=0
            log_audit "namespace_switch=$name"
            ;;
        *) ui_resource_workspace "$type" "$name" "$ns";;
    esac
}

global_search() {
    local term matches="$RUN_DIR/search.matches.tsv" i=0 line type name ns status source choice total
    prompt 'SEARCH >' || return
    term=$REPLY; [[ -n $term ]] || return
    ui_progress '1/2' 'Building sanitized resource index' '...'
    ui_build_resource_index || { ui_error 'Universal search unavailable' COMMAND_MISSING 'jq or required API data is unavailable.' 'Use domain-specific views.'; prompt 'Enter to return:' || :; return; }
    ui_progress '2/2' 'Filtering resources' 'DONE'
    ui_search_matches "$term" "$matches" || :
    total=$(wc -l < "$matches" | awk '{print $1+0}')
    ui_clear_transition
    ui_header 'GLOBAL SEARCH' 'DEVOPSSENTINEL > SEARCH'
    printf ' Query: %s | Matches: %s\n' "$term" "$total"
    ((UI_DEBUG_FLAG)) && printf ' Scope: Namespace | Calls(max/cached): %s | Time: %sms\n' "$UI_LAST_QUERY_CALLS" "$UI_LAST_QUERY_MS"
    ui_subrule
    printf ' #\tTYPE\tNAME\tNAMESPACE\tSTATUS\n'
    while IFS=$'\t' read -r type name ns status source; do ((i+=1)); printf '%d\t%s\t%s\t%s\t%s\n' "$i" "$type" "$name" "$ns" "$status"; done < "$matches" | format_table "$UI_COLS"
    ((total)) || { ui_empty_state 'NO MATCHES' "No indexed resource/action matched '$term'."; prompt 'Enter to return:' || :; return; }
    prompt 'SELECT # / 0 Back >' || return
    choice=$REPLY; [[ $choice == 0 || ${choice,,} == b ]] && return
    [[ $choice =~ ^[0-9]+$ && 10#$choice -ge 1 && 10#$choice -le total ]] || return
    line=$(sed -n "${choice}p" "$matches")
    IFS=$'\t' read -r type name ns status source <<< "$line"
    ui_resource_native_open "$type" "$name" "$ns"
}

ui_history_menu() {
    local tmp="$RUN_DIR/history-view.tsv" choice line _i type name ts total
    awk -F '\t' -v c="$SENTINEL_CONTEXT" -v n="$SENTINEL_NAMESPACE" '$2==c&&$3==n{rows[++x]=$0}END{j=0;for(i=x;i>=1&&j<30;i--){split(rows[i],a,FS);printf "%s\t%s\t%s\t%s\n",++j,a[4],a[5],a[1]}}' "$UI_HISTORY_FILE" > "$tmp"
    show_report 'SESSION — RECENT HISTORY' ui_history_report
    total=$(wc -l < "$tmp" | awk '{print $1+0}'); ((total)) || return
    prompt 'Open recent # / 0 Back >' || return; choice=$REPLY
    [[ $choice =~ ^[0-9]+$ && 10#$choice -ge 1 && 10#$choice -le total ]] || return
    line=$(sed -n "${choice}p" "$tmp"); IFS=$'\t' read -r _i type name ts <<< "$line"
    ui_resource_native_open "$type" "$name" "$SENTINEL_NAMESPACE"
}

ui_pins_menu() {
    local tmp="$RUN_DIR/pins-view.tsv" choice line _i type name status total
    awk -F '\t' -v c="$SENTINEL_CONTEXT" -v n="$SENTINEL_NAMESPACE" '$1==c&&$2==n{printf "%s\t%s\t%s\n",$3,$4,"PINNED"}' "$UI_PIN_FILE" > "$tmp"
    show_report 'SESSION — PINNED RESOURCES' ui_pins_report
    total=$(wc -l < "$tmp" | awk '{print $1+0}'); ((total)) || return
    prompt 'Open pinned # / 0 Back >' || return; choice=$REPLY
    [[ $choice =~ ^[0-9]+$ && 10#$choice -ge 1 && 10#$choice -le total ]] || return
    line=$(sed -n "${choice}p" "$tmp"); IFS=$'\t' read -r type name status <<< "$line"
    ui_resource_native_open "$type" "$name" "$SENTINEL_NAMESPACE"
}

ui_notes_add() {
    [[ -n $INCIDENT_DIR ]] || { printf 'Start with --incident ID to attach operator notes to an incident session.\n'; return 2; }
    local note file
    prompt 'NOTE >' || return 1; note=$REPLY; [[ -n $note ]] || return 1
    file="$INCIDENT_DIR/notes/operator-notes.txt"
    printf '%s\t%s\n' "$(timestamp)" "$note" | redact >> "$file"; chmod 600 "$file" 2>/dev/null || :
    printf 'Note added locally: %s\n' "$file"
}

ui_live_report() {
    local title=$1 fn=$2 interval=${3:-$UI_LIVE_INTERVAL} key rc=0
    [[ $interval =~ ^[0-9]+$ ]] || interval=10
    ((interval<UI_LIVE_MIN_INTERVAL)) && interval=$UI_LIVE_MIN_INTERVAL
    while :; do
        FORCE_REFRESH=1; capture_report "$title" "$fn"; rc=$?; FORCE_REFRESH=0
        ui_clear_transition; ui_header "$title — LIVE" "DEVOPSSENTINEL > LIVE > ${title^^}"
        tail -n +3 "$CURRENT_REPORT" | format_table "$UI_COLS" | head -n "$((UI_ROWS-10))"
        ui_subrule; printf ' LIVE: ON | Refresh: %ss | Last update: %s | [B] Stop [Q] Exit\n' "$interval" "$(ui_time_local)"
        key=''; IFS= read -r -t "$interval" -n 1 key || :; printf '\n'
        case ${key,,} in b|0) break;; q) UI_EXIT_REQUESTED=1; break;; esac
    done
    return "$rc"
}

ui_debug_report() {
    terminal_size
    printf 'UI DEBUG\n'
    printf 'Width\t%s\nHeight\t%s\nLayout\t%s\nPage size\t%s\nColor\t%s\nUnicode\t%s\nPersona\t%s\nIncident\t%s\n' "$UI_COLS" "$UI_ROWS" "$UI_LAYOUT" "$UI_PAGE_SIZE" "$([[ -n $C_RESET ]]&&printf ON||printf OFF)" "$([[ $UI_ASCII == 0 ]]&&printf ON||printf ASCII)" "$UI_PERSONA" "${INCIDENT_ID:-none}"
    printf 'Last query calls\t%s\nLast query duration\t%sms\n' "$UI_LAST_QUERY_CALLS" "$UI_LAST_QUERY_MS"
}

ui_dashboard_attention() {
    local critical=0 failed=0 warning=0
    if [[ -s ${RUN_DIR:-/nonexistent}/findings.tsv ]]; then
        critical=$(awk -F '\t' 'toupper($1)=="CRITICAL"{n++}END{print n+0}' "$RUN_DIR/findings.tsv")
        failed=$(awk -F '\t' 'toupper($1)=="FAIL"||toupper($1)=="FAILED"{n++}END{print n+0}' "$RUN_DIR/findings.tsv")
        warning=$(awk -F '\t' 'toupper($1)=="WARN"||toupper($1)=="WARNING"{n++}END{print n+0}' "$RUN_DIR/findings.tsv")
    fi
    printf ' ATTENTION REQUIRED\n'
    if ((critical+failed+warning==0)); then
        printf ' %s No cached abnormal finding yet. [T] runs fresh triage.\n' "$(status_label INFO)"
    else
        ((critical)) && printf ' %s %s critical finding(s)\n' "$(status_label CRITICAL)" "$critical"
        ((failed)) && printf ' %s %s failed finding(s)\n' "$(status_label FAILED)" "$failed"
        ((warning)) && printf ' %s %s warning finding(s)\n' "$(status_label WARNING)" "$warning"
    fi
}

# Problem-first dashboard. Cached badges never trigger API calls.
dashboard_report() {
    local pods='-' failed='-' pins=0 recent=0 state
    state=$(cache_status pods)
    if [[ $state == OK || $state == EMPTY_RESULT ]] && has jq && [[ -s $CACHE_DIR/pods.json ]]; then
        pods=$(jq '.items|length' "$CACHE_DIR/pods.json" 2>/dev/null || printf '-')
        failed=$(jq '[.items[]?|select(.status.phase!="Running" and .status.phase!="Succeeded")]|length' "$CACHE_DIR/pods.json" 2>/dev/null || printf '-')
    fi
    [[ -f ${UI_PIN_FILE:-/none} ]] && pins=$(awk -F '\t' -v c="$SENTINEL_CONTEXT" -v n="$SENTINEL_NAMESPACE" '$1==c&&$2==n{x++}END{print x+0}' "$UI_PIN_FILE")
    [[ -f ${UI_HISTORY_FILE:-/none} ]] && recent=$(awk -F '\t' -v c="$SENTINEL_CONTEXT" -v n="$SENTINEL_NAMESPACE" '$2==c&&$3==n{x++}END{print x+0}' "$UI_HISTORY_FILE")
    ui_dashboard_attention
    printf '\n DOMAIN STATE (cached only)\n'
    if [[ $UI_LAYOUT == COMPACT ]]; then
        printf ' WORKLOADS %s | GITOPS %s | CERTS %s\n' "${state:-NOT_PROBED}" "$GITOPS_STATUS" "$CERT_STATUS"
        printf ' PODS %s | ABNORMAL %s | PINNED %s | RECENT %s\n' "$pods" "$failed" "$pins" "$recent"
        printf '\n PRIMARY TROUBLESHOOTING\n'
        printf ' [26] Incident Triage\n [31] Session Findings\n [ 1] Pods / Resource Grid\n [32] Recent Resources\n [ 9] Smart Health\n [33] Pinned Resources\n [ 4] Event Radar\n [34] Incident Timeline\n [10] Dependencies\n [35] Session Changes / Diff\n [11] GitOps\n [16] Certificates\n [17] Certificate Expiry\n [21] Network\n [ 8] Storage\n [29] Doctor\n'
    else
        if ((UI_COLS < 115)); then
            printf ' WORKLOADS %-8s  GITOPS %-8s  CERTIFICATES %-8s\n' "${state:-NOT_PROBED}" "$GITOPS_STATUS" "$CERT_STATUS"
            printf ' NETWORK %-8s  STORAGE %-8s  PODS %-6s  ABNORMAL %-6s\n' "$(cache_status services)" "$(cache_status pvcs)" "$pods" "$failed"
            printf ' PINNED %-5s  RECENT %-5s  INCIDENT %s\n' "$pins" "$recent" "${INCIDENT_ID:-none}"
        else
            printf ' WORKLOADS %-8s  GITOPS %-8s  CERTIFICATES %-8s  NETWORK %-8s  STORAGE %-8s\n' "${state:-NOT_PROBED}" "$GITOPS_STATUS" "$CERT_STATUS" "$(cache_status services)" "$(cache_status pvcs)"
            printf ' PODS %-6s  ABNORMAL %-6s  PINNED %-5s  RECENT %-5s  INCIDENT %s\n' "$pods" "$failed" "$pins" "$recent" "${INCIDENT_ID:-none}"
        fi
        printf '\n PRIMARY TROUBLESHOOTING                              CORRELATION / CONTROL\n'
        ui_menu_pair 26 'Incident Triage' 31 'Session Findings'
        ui_menu_pair 1 'Pods / Resource Grid' 32 'Recent Resources'
        ui_menu_pair 9 'Smart Health Inspector' 33 'Pinned Resources'
        ui_menu_pair 4 'Event Radar' 34 'Incident Timeline'
        ui_menu_pair 10 'Dependency Explorer' 35 'Session Changes / Diff'
        ui_menu_pair 11 'GitOps Command Center' 16 'Certificate Inventory'
        ui_menu_pair 17 'Certificate Expiry' 21 'Host Network Operations'
        ui_menu_pair 8 'Storage Dependency Audit' 29 'Environment Doctor'
        printf '\n SECONDARY DOMAINS\n'
        ui_menu_pair 2 'Pod Search / Filter' 12 'Revision / Drift Analyzer'
        ui_menu_pair 3 'Failed / Alert Pods' 13 'GitOps Dependency Graph'
        ui_menu_pair 5 'Pod Deep Dive' 14 'Configuration Dependencies'
        ui_menu_pair 6 'Performance & Observability' 15 'Image / Registry Audit'
        ui_menu_pair 7 'Service & Network Topology' 18 'Trust Chain Analyzer'
        ui_menu_pair 19 'Live TLS Inspector' 20 'Certificate Dependencies'
        ui_menu_pair 22 'PostgreSQL / Generic DB' 23 'Kafka Diagnostics'
        ui_menu_pair 25 'ETDP Platform Inspector' 27 'Evidence Collector'
        ui_menu_pair 24 'Namespace / Context' 28 'Export Center'
        ui_menu_pair 30 'Self-Test' 36 'UI Debug / Explain'
    fi
}

ui_footer() {
    local source=${1:-$UI_SOURCE} records=${2:-$UI_RECORDS} cache_age='-'
    ui_subrule
    local footer_line meta_line
    footer_line=' [B] Back [M] Main [T] Triage [F] Findings [/] Search [[] History [R] Refresh [E] Export [H] Help [Q] Exit'
    meta_line=" CTX:${SENTINEL_CONTEXT:-UNSET} | NS:${SENTINEL_NAMESPACE:-UNSET} | Source:$source | Records:$records | Filter:$UI_FILTER_TEXT | Sort:$UI_SORT_TEXT | ${UI_QUERY_MS}ms"
    truncate_text "$footer_line" "$UI_COLS"; printf '\n'
    truncate_text "$meta_line" "$UI_COLS"; printf '\n'
    rule
}

ui_header() {
    local title=${1:-$UI_SCREEN_TITLE} crumb=${2:-$UI_BREADCRUMB} health auth api rbac incident=''
    terminal_size
    health=$(ui_global_health); auth=$(ui_status_kind "${AUTH_STATUS:-UNKNOWN}"); api=$(ui_status_kind "${API_STATUS:-UNKNOWN}"); rbac=$(ui_status_kind "${RBAC_STATUS:-UNKNOWN}")
    [[ -n $INCIDENT_ID ]] && incident=" | INC:$INCIDENT_ID"
    rule
    if [[ $UI_LAYOUT == COMPACT ]]; then
        truncate_text " $APP_NAME v$APP_VERSION | $title$incident" "$UI_COLS"; printf '\n'
        truncate_text " CTX:$SENTINEL_CONTEXT | NS:$SENTINEL_NAMESPACE | USER:${AUTH_USER:-UNKNOWN}" "$UI_COLS"; printf '\n'
        printf ' HEALTH %s | MODE READ ONLY\n' "$(status_label "$health")"
    else
        truncate_text " $APP_NAME v$APP_VERSION | $title | $UI_LAYOUT$incident" "$UI_COLS"; printf '\n'
        ui_subrule
        truncate_text " CONTEXT:$SENTINEL_CONTEXT | NAMESPACE:$SENTINEL_NAMESPACE | OPERATOR:${AUTH_USER:-UNKNOWN} | MODE:SUPERVISION [READ ONLY]" "$UI_COLS"; printf '\n'
        printf ' HEALTH %s | AUTH %s | API %s | RBAC %s\n' "$(status_label "$health")" "$(status_label "$auth")" "$(status_label "$api")" "$(status_label "$rbac")"
    fi
    ui_subrule
    [[ -n $crumb ]] && { truncate_text " $crumb" "$UI_COLS"; printf '\n'; }
}

ui_command_palette() {
    local query entry num label
    local -a entries=(
        '26|incident triage' '31|session findings problems queue' '32|recent history' '33|pinned bookmarks' '34|incident timeline'
        '35|change detection diff changed resources' '1|pods resource grid' '2|live pod search filter' '3|failed alert pods' '4|events event radar'
        '9|smart health' '10|dependency explorer' '11|gitops command center' '12|gitops drift revision' '13|gitops dependencies'
        '16|certificate inventory' '17|certificate expiry' '18|trust chain' '19|live tls' '20|certificate dependencies'
        '21|network host' '8|storage' '6|performance' '22|postgres database' '23|kafka' '25|etdp' '29|doctor' '27|evidence' '28|export'
        '36|ui debug explain' '37|operator note' '38|favorite namespace' '39|live triage refresh watch' '40|dependency path finder relationship path'
    ) matches=()
    prompt 'COMMAND >' || return 1; query=${REPLY,,}; [[ -n $query ]] || return 1
    for entry in "${entries[@]}"; do num=${entry%%|*}; label=${entry#*|}; [[ $label == *"$query"* ]] && matches+=("$entry"); done
    ((${#matches[@]})) || { printf 'No command match.\n'; return 1; }
    if ((${#matches[@]}==1)); then REPLY=${matches[0]%%|*}; return 0; fi
    local -a labels=(); for entry in "${matches[@]}"; do labels+=("${entry%%|*}  ${entry#*|}"); done
    choose 'COMMAND MATCHES' "${labels[@]}" || return 1
    REPLY=${REPLY%% *}
}

ui_dashboard_help() { show_report 'COMMANDS — HELP / INDEX' ui_all_commands_report; }

# Advanced dashboard navigation: 0/B back semantics are reserved inside domain views; Q exits.
dashboard() {
    local selection last_report='' rc=0 from to
    UI_EXIT_REQUESTED=0 UI_MAIN_REQUESTED=0
    ui_enter
    while :; do
        paint_frame 'OPERATIONS COMMAND CENTER' '[T] Triage [F] Findings [/] Search [[] History [:] Palette [NS] Namespace [H] Help [Q] Exit'
        capture_report Dashboard dashboard_report
        paint_report "$CURRENT_REPORT"
        [[ -n $last_report ]] && CURRENT_REPORT=$last_report
        selection=
        if ((UI_ACTIVE)); then printf '\033[%s;1H\033[2KSELECT [1-40 / hotkey] > \033[?25h' "$((UI_ROWS-1))"; fi
        IFS= read -r selection || break
        ui_leave
        case $selection in :) if ui_command_palette; then selection=$REPLY; else selection=''; fi;; esac
        selection=${selection,,}; log_audit "menu=$selection"
        case $selection in
            q) break;;
            h|help|'?') ui_dashboard_help;;
            1|p) show_report 'WORKLOADS — POD GRID' resources_report;;
            2) live_resources;;
            3) show_report 'WORKLOADS — FAILED / ALERT PODS' failed_pod_intelligence_report;;
            4|e) show_report 'EVENTS — RADAR' events_report all;;
            5) select_pod && ui_resource_workspace Pod "$SELECTED_POD" "$SENTINEL_NAMESPACE";;
            6) show_report 'PLATFORM — PERFORMANCE & OBSERVABILITY' resources_report;;
            7) show_report 'NETWORK — SERVICE TOPOLOGY' service_topology_report;;
            8|s) show_report 'STORAGE — DEPENDENCY AUDIT' storage_dependency_report;;
            9) show_report 'TRIAGE — SMART HEALTH' smart_health_report;;
            10) dependency_menu;;
            11|g) gitops_menu;;
            12) show_report 'GITOPS — REVISION / DRIFT' gitops_drift_report;;
            13) show_report 'GITOPS — DEPENDENCY GRAPH' gitops_dependency_report;;
            14) configuration_dependency_menu;;
            15) show_report 'WORKLOADS — IMAGE / REGISTRY AUDIT' image_dependency_report;;
            16|c) show_report 'PKI/TLS — CERTIFICATE INVENTORY' certificates_report;;
            17) show_report 'PKI/TLS — CERTIFICATE EXPIRY' cert_expiry_audit;;
            18) certificate_trust_menu;;
            19) tls_menu;;
            20) show_report 'PKI/TLS — CERTIFICATE DEPENDENCIES' certificate_dependency_report;;
            21|n) show_report 'NETWORK — HOST INSPECTOR' host_network_report;;
            22) postgres_menu;; 23) kafka_menu;;
            24|ns) change_scope || { rc=$?; break; }; advanced_runtime_init;;
            25) etdp_menu;;
            26|t) show_report 'INCIDENT — TRIAGE' triage_report;;
            27) evidence_menu;; 28|o) export_center;; 29) show_report 'PLATFORM — ENVIRONMENT DOCTOR' devopssentinel_doctor_report;; 30) show_report 'PLATFORM — SELF TEST' sentinel_self_test;;
            31|f) ui_findings_menu;;
            32|'[') ui_history_menu;;
            33) ui_pins_menu;;
            34) show_report 'INCIDENT — TIMELINE' incident_timeline_report;;
            35) show_report 'SESSION — CHANGE DETECTION' ui_change_report;;
            36) show_report 'UI — DEBUG / EXPLAIN' ui_debug_report;;
            37) ui_notes_add; prompt 'Enter to continue:' || :;;
            38) favorite_namespace_toggle; prompt 'Enter to continue:' || :;;
            39) ui_live_report 'INCIDENT — TRIAGE' triage_report "$UI_LIVE_INTERVAL";;
            40|path)
                prompt 'FROM type/name >' || :; from=$REPLY; prompt 'TO type/name >' || :; to=$REPLY; [[ -n $from && -n $to ]] && show_report 'DEPENDENCIES — PATH FINDER' ui_dependency_path_report "$from" "$to";;
            /) global_search;;
            x) show_report 'EXPLAIN — OVERVIEW' explain_report overview;;
            r|m|0|b) :;;
        esac
        ((UI_EXIT_REQUESTED)) && break
        case $UI_PENDING_ACTION in
            t) UI_PENDING_ACTION=''; show_report 'INCIDENT — TRIAGE' triage_report;;
            f) UI_PENDING_ACTION=''; ui_findings_menu;;
        esac
        ((UI_EXIT_REQUESTED)) && break
        UI_MAIN_REQUESTED=0; last_report=$CURRENT_REPORT; ui_enter
    done
    ui_leave; advanced_session_summary || :
    return "$rc"
}

advanced_ui_self_tests() (
    local tmp root old_run=$RUN_DIR old_cache=$CACHE_DIR old_hist=$UI_HISTORY_FILE old_pin=$UI_PIN_FILE old_ctx=$SENTINEL_CONTEXT old_ns=$SENTINEL_NAMESPACE out width maxlen
    root=$(mktemp -d "${TMPDIR:-/tmp}/devopssentinel-advanced-ui.XXXXXXXX") || exit 1
    trap 'rm -rf "$root"' EXIT
    RUN_DIR=$root; CACHE_DIR=$root/cache; mkdir -p "$CACHE_DIR"; printf '{"items":[]}\n' > "$RUN_DIR/empty-list.json"; : > "$RUN_DIR/findings.tsv"
    UI_HISTORY_FILE=$root/history.tsv; UI_PIN_FILE=$root/pins.tsv; UI_FAVORITE_NS_FILE=$root/fav.tsv; UI_SEARCH_INDEX=$root/index.tsv; UI_RELATION_INDEX=$root/rel.tsv; UI_CHANGE_PREV=$root/prev.tsv; UI_CHANGE_CURR=$root/cur.tsv
    touch "$UI_HISTORY_FILE" "$UI_PIN_FILE" "$UI_FAVORITE_NS_FILE"
    SENTINEL_CONTEXT=test-context SENTINEL_NAMESPACE=test-ns AUTH_STATUS=AUTHENTICATED API_STATUS=OK RBAC_STATUS=OK AUTH_USER=tester
    ui_history_add Deployment very-long-transformer-name-near-kubernetes-practical-limit test-ns
    grep -q 'Deployment' "$UI_HISTORY_FILE" || exit 1
    ui_pin_add Certificate syslog-output-cert test-ns; grep -q 'syslog-output-cert' "$UI_PIN_FILE" || exit 1
    ui_pin_remove Certificate syslog-output-cert test-ns; ! grep -q 'syslog-output-cert' "$UI_PIN_FILE" || exit 1
    printf 'CRITICAL\tWORKLOAD\tPod/a\tCrashLoopBackOff\tEvents\nWARN\tPKI\tCertificate/b\t5 days remaining\tExpiry\n' > "$RUN_DIR/findings.tsv"
    out=$(ui_findings_report); [[ $out == *F-001* && $out == *F-002* ]] || exit 1
    printf 'Pod\ta\ttest-ns\tRunning\tKubernetes API\nDeployment\ttransformer\ttest-ns\tREADY\tKubernetes API\nSecret\ttransformer-tls\ttest-ns\tINFO\tKubernetes API (name only)\n' > "$UI_SEARCH_INDEX"
    ui_search_matches transformer "$root/matches.tsv"; [[ $(wc -l < "$root/matches.tsv") -eq 2 ]] || exit 1
    ui_search_matches '/^Secret' "$root/matches2.tsv"; [[ $(wc -l < "$root/matches2.tsv") -eq 1 ]] || exit 1
    printf 'test-ns\tDeployment/a\tPod/p\tOWNER\ntest-ns\tPod/p\tSecret/s\tUSES\n' > "$UI_RELATION_INDEX"
    out=$(ui_dependency_path_report Deployment/a Secret/s); [[ $out == *'Deployment/a'* && $out == *'Secret/s'* ]] || exit 1
    NO_COLOR_FLAG=1 TERM=dumb LINES=24
    for width in 80 100 120 160; do COLUMNS=$width; terminal_size; out=$(dashboard_report); maxlen=$(printf '%s\n' "$out"|awk '{if(length($0)>m)m=length($0)}END{print m+0}'); ((maxlen<=width+5)) || exit 1; done
    # 500-row / very-long-name renderer fixture: no border/line overflow and deterministic row count.
    : > "$root/large.tsv"; for i in $(seq 1 500); do printf 'pod-%04d-very-long-kubernetes-resource-name-for-layout-regression-%060d\t1/1\tRunning\t%d\tworker-node-with-long-name-%03d\t31d\n' "$i" 0 "$i" "$((i%17))" >> "$root/large.tsv"; done
    for width in 80 120 160; do COLUMNS=$width; terminal_size; out=$(format_table "$UI_COLS" < "$root/large.tsv"); [[ $(printf '%s\n' "$out"|wc -l) -eq 500 ]] || exit 1; maxlen=$(printf '%s\n' "$out"|awk '{if(length($0)>m)m=length($0)}END{print m+0}'); ((maxlen<=width)) || exit 1; done
    # Release UI functions must be unique in source.
    if [[ -f ${SOURCE_FILE:-} ]]; then
      local dups; dups=$(awk '/^[A-Za-z_][A-Za-z0-9_]*\(\) \{/{n=$1;sub(/\(\).*/,"",n);c[n]++} END{for(n in c)if(c[n]>1)print n}' "$SOURCE_FILE"); [[ -z $dups ]] || exit 1
    fi
    printf 'PASS advanced search, history, pins, findings, cross-domain path/jump primitives, long-name/500-row renderer, unique UI source and golden widths 80/100/120/160\n'
)


# ==============================================================================
# Final read-only CLI. No developer publishing or reconciliation modes exist.
# ==============================================================================

usage() {
    cat <<'HELP'
DevOpsSentinel FINAL -- single-file read-only Kubernetes/GitOps/PKI/TLS/ETDP console

Interactive:
  ./DevOps_K8s_Sentinel_FINAL.sh

Reports:
  --health | --resources | --gitops | --gitops-graph | --certificates | --cert-expiry
  --triage | --triage-workload NAME | --network | --storage | --etdp
  --postgres-discovery | --kafka-discovery | --doctor | --capabilities
  --dependency TYPE/NAME | --explain [TOPIC]
Validation:
  --self-test | --live-validate | --performance
Evidence:
  --evidence INCIDENT_ID
Scope:
  --kubeconfig FILE --context CONTEXT --namespace NAMESPACE
Runtime:
  --output DIR   HOME-local DevOpsSentinel root; default $HOME/.devopssentinel
  --api-timeout SEC --log-timeout SEC --tls-timeout SEC
  --cert-critical-days N --cert-warn-days N --cert-attention-days N
UI:
  --compact       Force compact terminal layout
  --snapshot      One-shot correlated operations snapshot
  --ui-debug      One-shot terminal/render diagnostics (no cluster access required)
  --incident ID   Local incident session; exports/evidence stay under ~/.devopssentinel/evidence/ID
  --persona MODE  STANDARD|SRE|PKI|GITOPS menu emphasis only
  DEVOPSSENTINEL_UNICODE=auto|on|off controls tree glyphs
Output:
  --json --quiet --no-color --version --help

Safety contract: no sudo, no Git commit/push, no Flux reconcile/suspend/resume,
no Helm mutation, no kubectl apply/create/delete/patch/edit/scale/replace, and no
remote persistence. Kubernetes Secret payloads/private keys are never exported.
HELP
}

cli_need_value() { (($#>=2)) && [[ -n $2 ]] || { printf 'Missing value for %s\n' "$1" >&2; return 2; }; }

parse_cli() {
    local mode_set=0 opt value
    while (($#)); do
        opt=$1
        case $opt in
            --help|-h) usage; return 10;;
            --version) printf '%s %s (%s, %s)\n' "$APP_NAME" "$APP_VERSION" "$APP_BUILD" "$APP_BUILD_DATE"; return 10;;
            --no-color) NO_COLOR_FLAG=1;;
            --compact) UI_COMPACT_FLAG=1;;
            --ui-debug) UI_DEBUG_FLAG=1; ((mode_set==0)) || { printf "Select exactly one command mode\n" >&2; return 2; }; MODE=ui-debug; mode_set=1;;
            --incident) cli_need_value "$@" || return; INCIDENT_ID=$2; shift;;
            --persona) cli_need_value "$@" || return; UI_PERSONA=${2^^}; case $UI_PERSONA in STANDARD|SRE|PKI|GITOPS) :;; *) printf "Invalid persona: %s\n" "$2" >&2; return 2;; esac; shift;;
            --snapshot) ((mode_set==0)) || { printf 'Select exactly one command mode\n' >&2; return 2; }; MODE=snapshot; mode_set=1;;
            --health|--resources|--gitops|--gitops-graph|--certificates|--cert-expiry|--triage|--network|--storage|--etdp|--postgres-discovery|--kafka-discovery|--doctor|--capabilities|--self-test|--live-validate|--performance)
                ((mode_set==0)) || { printf 'Select exactly one command mode\n' >&2; return 2; }; MODE=${opt#--}; mode_set=1;;
            --triage-workload) cli_need_value "$@" || return; ((mode_set==0)) || return 2; MODE=triage-workload TRIAGE_WORKLOAD=$2 mode_set=1; shift;;
            --evidence) cli_need_value "$@" || return; ((mode_set==0)) || return 2; MODE=evidence EVIDENCE_ID=$2 mode_set=1; shift;;
            --dependency) cli_need_value "$@" || return; ((mode_set==0)) || return 2; MODE=dependency value=$2; DEP_TYPE=${value%%/*}; DEP_NAME=${value#*/}; [[ $DEP_TYPE != "$DEP_NAME" && -n $DEP_TYPE && -n $DEP_NAME ]] || { printf 'Use --dependency TYPE/NAME\n' >&2; return 2; }; mode_set=1; shift;;
            --explain)
                ((mode_set==0)) || return 2; MODE=explain mode_set=1
                if (($#>=2)) && [[ $2 != --* ]]; then EXPLAIN_TOPIC=$2; shift; fi;;
            --json) JSON_FLAG=1;; --quiet) QUIET_FLAG=1;;
            --kubeconfig) cli_need_value "$@" || return; export KUBECONFIG=$2; KUBECONFIG_MODE=EXPLICIT; shift;;
            --context) cli_need_value "$@" || return; SENTINEL_CONTEXT=$2; shift;;
            --namespace) cli_need_value "$@" || return; SENTINEL_NAMESPACE=$2; shift;;
            --output) cli_need_value "$@" || return; OUTPUT_DIR=$2; shift;;
            --refresh) cli_need_value "$@" || return; REFRESH=$2; shift;;
            --api-timeout|--log-timeout|--tls-timeout|--cert-warn-days|--cert-critical-days|--cert-attention-days|--cpu-warn|--cpu-critical|--mem-warn|--mem-critical)
                cli_need_value "$@" || return; [[ $2 =~ ^[1-9][0-9]{0,4}$ ]] || return 2
                case $opt in --api-timeout) API_TIMEOUT=$2;; --log-timeout) LOG_TIMEOUT=$2;; --tls-timeout) TLS_TIMEOUT=$2;; --cert-warn-days) CERT_WARN_DAYS=$2;; --cert-critical-days) CERT_CRIT_DAYS=$2;; --cert-attention-days) CERT_ATTENTION_DAYS=$2;; --cpu-warn) CPU_WARN=$2;; --cpu-critical) CPU_CRIT=$2;; --mem-warn) MEM_WARN=$2;; --mem-critical) MEM_CRIT=$2;; esac; shift;;
            *) printf 'Unknown option: %s\n' "$opt" >&2; return 2;;
        esac
        shift
    done
    [[ $REFRESH =~ ^[0-9]+$ ]] || return 2
    ((CERT_CRIT_DAYS<=CERT_WARN_DAYS && CERT_WARN_DAYS<=CERT_ATTENTION_DAYS && CPU_WARN<CPU_CRIT && MEM_WARN<MEM_CRIT && CPU_CRIT<=100 && MEM_CRIT<=100)) || return 2
    return 0
}

main() {
    if ((BASH_VERSINFO[0]<4 || (BASH_VERSINFO[0]==4 && BASH_VERSINFO[1]<4))); then printf 'Bash 4.4+ required\n' >&2; return 2; fi
    local rc=0 title fn
    parse_cli "$@"; rc=$?; ((rc==10)) && return 0; ((rc==0)) || return "$rc"
    dependency_detect; color_init; terminal_size
    SOURCE_FILE=$(cd -- "$(dirname -- "$SOURCE_FILE")" && printf '%s/%s' "$(pwd -P)" "${SOURCE_FILE##*/}") || return 2
    init_runtime || return
    advanced_runtime_init || return

    case $MODE in
        self-test) sentinel_self_test; return $?;;
        explain) explain_report "$EXPLAIN_TOPIC"; return 0;;
        ui-debug) ui_debug_report; return 0;;
    esac

    if [[ $MODE == dashboard && $INTERACTIVE == 0 ]]; then printf 'Dashboard needs a terminal; use a report option for noninteractive output.\n' >&2; return 2; fi
    if [[ $MODE == doctor || $MODE == capabilities ]]; then bootstrap_scope || rc=$?; else bootstrap_scope || return; fi

    case $MODE in
        dashboard) dashboard; return $?;;
        health) title='Health'; fn=health_report;;
        resources) title='Resources'; fn=resources_report;;
        gitops) title='GitOps'; fn=gitops_report;;
        gitops-graph) title='GitOps Dependency Graph'; fn=gitops_dependency_report;;
        certificates) title='Certificates'; fn=certificates_report;;
        cert-expiry) title='Certificate Expiry'; fn=cert_expiry_audit;;
        triage) title='Incident Triage'; fn=triage_report;;
        triage-workload) capture_report 'Workload Triage' triage_workload_report "$TRIAGE_WORKLOAD"; rc=$?; cli_report_output 'Workload Triage' "$rc" || return $?; return "$rc";;
        network) title='Network'; fn=service_topology_report;;
        storage) title='Storage'; fn=storage_dependency_report;;
        etdp) title='ETDP Platform'; fn=etdp_platform_report;;
        postgres-discovery) title='PostgreSQL / Generic DB'; fn=pg_discover_report;;
        kafka-discovery) title='Kafka'; fn=kafka_discovery_report;;
        doctor) title='Doctor'; fn=devopssentinel_doctor_report;;
        capabilities) title='Capabilities'; fn=capabilities_report;;
        live-validate) title='Live Validation'; fn=live_validation_report;;
        performance) title='Performance'; fn=performance_report;;
        snapshot) title='Operations Snapshot'; fn=ui_snapshot_report;;
        dependency) capture_report "Dependency $DEP_TYPE/$DEP_NAME" resource_dependencies "$DEP_TYPE" "$SENTINEL_NAMESPACE" "$DEP_NAME"; rc=$?; cli_report_output "Dependency $DEP_TYPE/$DEP_NAME" "$rc" || return $?; return "$rc";;
        evidence) evidence_create "$EVIDENCE_ID" 9; return $?;;
        *) printf 'Unknown mode\n' >&2; return 2;;
    esac
    capture_report "$title" "$fn"; rc=$?
    cli_report_output "$title" "$rc" || return $?
    return "$rc"
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; exit $?; fi
