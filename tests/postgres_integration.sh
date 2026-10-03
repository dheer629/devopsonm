#!/usr/bin/env bash
# Real libpq/authentication tests. Supply only an isolated test database.
# Usage: bash tests/postgres_integration.sh HOST PORT DATABASE USER PASSWORD_FILE
set -o pipefail
set +x
umask 077
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if (($# != 5)); then
    printf 'Usage: %s HOST PORT DATABASE USER PASSWORD_FILE\n' "$0" >&2
    exit 2
fi
test_host=$1 test_port=$2 test_database=$3 test_user=$4
export SENTINEL_TEST_PASSWORD_FILE=$5
[[ -r $SENTINEL_TEST_PASSWORD_FILE ]] || exit 2
export SENTINEL_TEST_REAL_PSQL
SENTINEL_TEST_REAL_PSQL=$(command -v psql) || { printf 'psql is required\n' >&2; exit 2; }
source "$ROOT/DevOps_K8s_Sentinel_FINAL_GP.sh"
test_scratch=$(mktemp -d "${TMPDIR:-/tmp}/sentinel-pg-test.XXXXXXXX") || exit 2
trap 'rm -rf -- "$test_scratch"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
RUN_DIR=$test_scratch/runtime
mkdir -p -- "$RUN_DIR" "$test_scratch/bin"
export SENTINEL_TEST_TRACE=$test_scratch/trace
export SENTINEL_TEST_PROBE=$test_scratch/probe
export SENTINEL_TEST_EXPECT_AUTH=good
export SENTINEL_TEST_TIMEOUT=$((API_TIMEOUT * 1000))
: > "$SENTINEL_TEST_TRACE"
: > "$SENTINEL_TEST_PROBE"

# Observe the actual child process, then delegate every query to real psql.
# No password, environment dump, or command line is written to the trace.
cat > "$test_scratch/bin/psql" <<'WRAPPER'
#!/usr/bin/env bash
set -o pipefail
fail() { printf 'WRAPPER_FAILURE %s\n' "$1" >> "$SENTINEL_TEST_TRACE"; exit 90; }
[[ -f ${PGPASSFILE:-} ]] || fail missing_passfile
[[ $(stat -c %a -- "$PGPASSFILE") == 600 ]] || fail passfile_permissions
[[ -z ${PGPASSWORD:-} ]] || fail inherited_password
[[ $PGPASSFILE != *prior-passfile ]] || fail inherited_passfile
if printf '%s\n' "$@" | grep -Fq -f "$SENTINEL_TEST_PASSWORD_FILE"; then fail password_in_arguments; fi
if env | grep -Fq -f "$SENTINEL_TEST_PASSWORD_FILE"; then fail password_in_environment; fi
printf 'PASSFILE_PRIVATE\n' >> "$SENTINEL_TEST_TRACE"
query= no_prompt=0
args=()
while (($#)); do
    case $1 in
        -c) query=$2; shift 2;;
        -w|--no-password) no_prompt=1; args+=("$1"); shift;;
        *) args+=("$1"); shift;;
    esac
done
((no_prompt == 1)) || fail password_retry_enabled
case $query in
    'SELECT current_database(), current_user, version();') kind=identity;;
    'SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size FROM pg_database ORDER BY pg_database_size(datname) DESC;') kind=sizes;;
    'SELECT state, count(*) FROM pg_stat_activity GROUP BY state ORDER BY 2 DESC;') kind=activity;;
    "SELECT pid, usename, datname, state, now()-query_start AS age, left(query,120) FROM pg_stat_activity WHERE query_start IS NOT NULL AND state <> 'idle' ORDER BY query_start LIMIT 50;") kind=long_running;;
    "SELECT table_schema, table_name, (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name), false, true, '')))[1]::text::bigint AS row_count FROM information_schema.tables WHERE table_type = 'BASE TABLE' AND table_schema NOT IN ('pg_catalog', 'information_schema') ORDER BY table_schema, table_name;") kind=schema;;
    *) fail unexpected_query;;
esac
if [[ $SENTINEL_TEST_EXPECT_AUTH == good ]]; then
    settings=$("$SENTINEL_TEST_REAL_PSQL" "${args[@]}" -At -c "SELECT current_setting('transaction_read_only'), current_setting('default_transaction_read_only'), current_setting('statement_timeout');" 2> "$SENTINEL_TEST_PROBE")
    [[ $? == 0 ]] || fail server_settings_query
    IFS='|' read -r transaction_read_only default_read_only statement_timeout <<< "$settings"
    [[ $transaction_read_only == on && $default_read_only == on ]] || fail server_not_readonly
    [[ $statement_timeout == "${SENTINEL_TEST_TIMEOUT}ms" || $statement_timeout == "$((SENTINEL_TEST_TIMEOUT / 1000))s" ]] || fail statement_timeout
    # The caller PGOPTIONS must survive the Sentinel append: the caller option is
    # still present AND the Sentinel's read-only option was appended.
    [[ $PGOPTIONS == *application_name=sentinel_pg_integration* && $PGOPTIONS == *default_transaction_read_only=on* ]] || fail inherited_options_lost
    if "$SENTINEL_TEST_REAL_PSQL" "${args[@]}" -c 'BEGIN; CREATE TABLE public.sentinel_readonly_probe (id integer); ROLLBACK;' > "$SENTINEL_TEST_PROBE" 2>&1; then
        fail write_was_permitted
    fi
    grep -q 'read-only transaction' "$SENTINEL_TEST_PROBE" || fail wrong_write_rejection
    printf 'SERVER_READONLY %s\n' "$kind" >> "$SENTINEL_TEST_TRACE"
fi
printf 'QUERY %s\n' "$kind" >> "$SENTINEL_TEST_TRACE"
exec "$SENTINEL_TEST_REAL_PSQL" "${args[@]}" -c "$query"
WRAPPER
chmod 700 "$test_scratch/bin/psql"
PATH=$test_scratch/bin:$PATH
export PATH
prompt() {
    case $prompt_index in
        0) REPLY=$test_host;; 1) REPLY=$test_port;;
        2) REPLY=$test_database;; 3) REPLY=$test_user;;
        *) return 1;;
    esac
    ((prompt_index += 1))
}
choose() { [[ $test_choice != CANCEL ]] || return 1; REPLY=$test_choice; }
failed=0 checks=0
check() {
    local label=$1; shift
    ((checks += 1))
    if "$@"; then printf 'PASS %s\n' "$label"; else printf 'FAIL %s\n' "$label"; failed=1; fi
}
no_passfiles() { ! compgen -G "$RUN_DIR/pgpass.*" >/dev/null; }
no_password_leaks() {
    local secret_path
    for secret_path in "$SENTINEL_TEST_PASSWORD_FILE" "$test_scratch/wrong-password"; do
        [[ -f $secret_path ]] || continue
        grep -RFq -f "$secret_path" "$RUN_DIR" "$SENTINEL_TEST_TRACE" "$SENTINEL_TEST_PROBE"
        [[ $? == 1 ]] || return 1
    done
}
prior_passfile=$test_scratch/prior-passfile
prior_options='-c application_name=sentinel_pg_integration -c default_transaction_read_only=off'
export PGPASSFILE=$prior_passfile PGOPTIONS=$prior_options PGPASSWORD=inherited-must-not-win
environment_preserved() {
    [[ ${PGPASSFILE:-} == "$prior_passfile" && ${PGOPTIONS:-} == "$prior_options" && ${PGPASSWORD:-} == inherited-must-not-win ]] &&
        [[ $(declare -p PGPASSFILE PGOPTIONS PGPASSWORD) != *'declare --'* ]]
}
run_choice() {
    local label=$1 expected=$2 password_file=${3:-$SENTINEL_TEST_PASSWORD_FILE}
    prompt_index=0
    pg_readonly_session < "$password_file" > "$RUN_DIR/$label.out" 2>&1
    session_rc=$?
    check "$label exit status" test "$session_rc" -eq "$expected"
    check "$label restores caller environment" environment_preserved
    check "$label removes temporary password file" no_passfiles
    check "$label does not disclose the password" no_password_leaks
}
test_choice='Connection / server identity'
run_choice identity 0
check 'identity response includes the test database' grep -q "$test_database" "$RUN_DIR/identity.out"
check 'identity response includes PostgreSQL server version' grep -q PostgreSQL "$RUN_DIR/identity.out"
test_choice='Database sizes'
run_choice sizes 0
check 'database sizes response has actual data' grep -q "$test_database" "$RUN_DIR/sizes.out"
test_choice='Active sessions summary'
run_choice activity 0
check 'active sessions response has actual data' grep -q active "$RUN_DIR/activity.out"
test_choice='Long-running sessions'
run_choice long_running 0
check 'long-running response includes the connected test user' grep -q "$test_user" "$RUN_DIR/long_running.out"
test_choice='Schema / row counts'
run_choice schema 0
check 'schema inventory lists the audit table' grep -q 'e2e_audit' "$RUN_DIR/schema.out"
check 'schema inventory reports the real audit row count' grep -qE 'e2e_audit[[:space:]]*\|[[:space:]]*3([[:space:]]|$)' "$RUN_DIR/schema.out"
for kind in identity sizes activity long_running schema; do
    check "$kind is read-only on the server and rejects writes" grep -q "^SERVER_READONLY $kind$" "$SENTINEL_TEST_TRACE"
done

printf 'incorrect-%s\n' "$RANDOM-$RANDOM" > "$test_scratch/wrong-password"
SENTINEL_TEST_EXPECT_AUTH=bad
test_choice='Connection / server identity'
run_choice wrong_password 2 "$test_scratch/wrong-password"
check 'wrong password reaches real PostgreSQL authentication' grep -q 'authentication failed' "$RUN_DIR/wrong_password.out"
check 'wrong password is classified as authentication failure' grep -q 'STATUS: AUTH_ERROR' "$RUN_DIR/wrong_password.out"
saved_database=$test_database
test_database=ds_e2e_database_does_not_exist
run_choice invalid_database 2
check 'invalid database is rejected by PostgreSQL' grep -q 'does not exist' "$RUN_DIR/invalid_database.out"
test_database=$saved_database
saved_host=$test_host saved_port=$test_port
test_host=127.0.0.1 test_port=1
run_choice unreachable 2
check 'unreachable port is classified as network failure' grep -q 'STATUS: NETWORK_ERROR' "$RUN_DIR/unreachable.out"
test_host=$saved_host test_port=$saved_port
SENTINEL_TEST_EXPECT_AUTH=good
test_choice=Back
run_choice back 0
test_choice=CANCEL
run_choice cancel 0
check 'all executed psql calls observed private passfiles' test "$(grep -c '^PASSFILE_PRIVATE$' "$SENTINEL_TEST_TRACE")" -eq 8
check 'wrapper found no credential or connection safety errors' test "$(grep -c '^WRAPPER_FAILURE ' "$SENTINEL_TEST_TRACE")" -eq 0
if ((failed)); then grep '^WRAPPER_FAILURE ' "$SENTINEL_TEST_TRACE" || :; fi
printf 'PostgreSQL integration: %s checks, result=%s\n' "$checks" "$([[ $failed == 0 ]] && printf PASS || printf FAIL)"
exit "$failed"
