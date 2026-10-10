import { useState, type ReactNode } from "react";

import { useDatabaseServices, useRunQuery, useSqlConsole } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fixtureSqlTarget, PLATFORM_DATABASE, suggestSqlTarget } from "@/lib/live";
import { useApp } from "@/state/AppContext";
import type { QueryResultPayload } from "@/types";

const DEFAULT_SQL =
  "select table_schema, table_name\nfrom information_schema.tables\norder by 1, 2\nlimit 50";

/** The endpoint in the fields, when it is not simply the discovered one. */
interface Endpoint {
  host: string;
  port: string;
  /** True when the values came from the optional E2E platform fixture. */
  fixture: boolean;
}

/** Opt-in read-only SQL console.
 *
 *  Off until the operator turns it on with the **Read-only SQL console** switch
 *  in Settings (or `DSWEB_ENABLE_SQL_CONSOLE=1` at start-up). The credentials
 *  typed here live only in this component's state and in one request body; the
 *  backend never stores, logs or audits them.
 *
 *  The endpoint prefills from the database Service the cluster actually reports
 *  for this scope -- never from a fixture address, because a cluster that has no
 *  such NodePort does not have that endpoint. The fixture button is explicit: it
 *  fills in a *complete* fixture endpoint and says where the values came from.
 */
export function SqlConsole() {
  const { scope } = useApp();
  const status = useSqlConsole();
  const services = useDatabaseServices(scope);
  const run = useRunQuery();

  const discovered = services.data?.envelope.data?.[0];
  const nodeAddress = status.data?.data.defaultHost;
  const target = suggestSqlTarget(discovered, nodeAddress, window.location.hostname);

  // What the operator (or the fixture button) put in the fields, if anything.
  //
  // Held as ONE object so the host and the port can never come from different
  // sources. They used to be two independent pieces of state plus an effect that
  // re-applied the discovered values, and a fixture click while that effect had
  // already settled left the discovered ClusterIP paired with the fixture's
  // NodePort -- an address that exists nowhere, which the page then reported as
  // fact. With no effect there is nothing to fall out of sync.
  const [endpoint, setEndpoint] = useState<Endpoint | null>(null);
  const [database, setDatabase] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [sql, setSql] = useState(DEFAULT_SQL);

  const host = endpoint?.host ?? target.host;
  const port = endpoint?.port ?? target.port;

  const enabled = Boolean(status.data?.data.enabled && status.data?.data.driverAvailable);
  const result = run.data?.data;

  /** The optional E2E platform fixture -- offered as a fixture, never as fact. */
  const fillPlatformFixture = () => {
    const fixture = fixtureSqlTarget(nodeAddress, window.location.hostname);
    setEndpoint({ host: fixture.host, port: fixture.port, fixture: true });
    setDatabase(PLATFORM_DATABASE.name);
    setUsername(PLATFORM_DATABASE.username);
    setPassword(PLATFORM_DATABASE.password);
  };

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle>Read-only SQL console</CardTitle>
          <Badge tone={enabled ? "info" : "unknown"}>{enabled ? "ENABLED" : "DISABLED"}</Badge>
        </CardHeader>
        <CardBody className="space-y-2">
          {!enabled ? (
            <p className="text-[12.5px] text-warning">
              {status.data?.data.reason ?? "checking the console status…"}
            </p>
          ) : null}
          <p className="text-[11.5px] text-text-muted">
            Credentials are used for this one request only — never stored, logged or audited. Exactly
            one read-only statement is accepted (SELECT / WITH / SHOW / EXPLAIN / TABLE / VALUES /
            &#92;d) and the session is forced read-only on the server, so it cannot mutate data.
          </p>
          <p className="text-[11.5px] text-text-faint">
            {endpoint?.fixture ? (
              <>
                Filled from the optional E2E platform fixture (
                <span className="mono">scripts/platform-resources.sh</span>):{" "}
                <span className="mono">
                  {endpoint.host}:{endpoint.port}
                </span>
                . Those values exist only where that fixture is deployed, and the statement runs on
                the server, so this address has to be reachable from there.
              </>
            ) : endpoint ? (
              <>
                Using the endpoint you entered:{" "}
                <span className="mono">
                  {endpoint.host}:{endpoint.port}
                </span>
                . The statement runs on the server, so this address has to be reachable from there.
              </>
            ) : target.source === "discovered" && discovered ? (
              <>
                Prefilled from the discovered Service{" "}
                <span className="mono">
                  {discovered.namespace}/{discovered.name}
                </span>{" "}
                (<span className="mono">{target.serviceType}</span>{" "}
                <span className="mono">
                  {target.host}:{target.port}
                </span>
                ). The statement runs on the server, so this address has to be reachable from there.
              </>
            ) : (
              <>
                No database Service is reported for{" "}
                <span className="mono">{scope.namespace || "this scope"}</span>, so no endpoint is
                prefilled. Enter the address the server should connect to.
              </>
            )}
          </p>
          {!endpoint && target.clusterOnly && discovered ? (
            <p className="text-[11.5px] text-text-faint">
              A <span className="mono">ClusterIP</span> only answers inside the cluster. To reach it
              from the server, forward it to the host —{" "}
              <span className="mono">
                kubectl -n {discovered.namespace} port-forward svc/{discovered.name} 15432:
                {target.port}
              </span>{" "}
              — then use <span className="mono">host.docker.internal:15432</span> from the container,
              or <span className="mono">127.0.0.1:15432</span> from a native run.
            </p>
          ) : null}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            <Field label="Host">
              <Input
                aria-label="Database host"
                value={host}
                onChange={(event) =>
                  setEndpoint({ host: event.target.value, port, fixture: false })
                }
              />
            </Field>
            <Field label="Port">
              <Input
                aria-label="Database port"
                value={port}
                onChange={(event) =>
                  setEndpoint({ host, port: event.target.value, fixture: false })
                }
              />
            </Field>
            <Field label="Database">
              <Input
                aria-label="Database name"
                value={database}
                onChange={(event) => setDatabase(event.target.value)}
              />
            </Field>
            <Field label="Username">
              <Input
                aria-label="Database username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </Field>
            <Field label="Password">
              <Input
                aria-label="Database password"
                type="password"
                autoComplete="off"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </Field>
          </div>
          <label className="block">
            <span className="text-[10.5px] uppercase tracking-wide text-text-faint">Statement</span>
            <textarea
              aria-label="Read-only SQL statement"
              rows={4}
              spellCheck={false}
              value={sql}
              onChange={(event) => setSql(event.target.value)}
              className="mono mt-1 w-full resize-y rounded-md border border-border bg-bg-elevated p-2 text-[12px] text-text focus-visible:border-accent"
            />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              disabled={!enabled || run.isPending}
              onClick={() =>
                run.mutate({
                  host,
                  port: Number(port),
                  database,
                  username,
                  password,
                  sql,
                })
              }
            >
              Run read-only query
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={fillPlatformFixture}
              title="Values from the optional E2E platform fixture (scripts/platform-resources.sh); they only exist when that fixture is deployed."
            >
              Fill E2E platform fixture
            </Button>
            {endpoint ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setEndpoint(null)}
                title="Go back to the endpoint the cluster reports for this scope."
              >
                Use the discovered endpoint
              </Button>
            ) : null}
            {run.isPending ? <span className="text-[11.5px] text-text-muted">running…</span> : null}
          </div>
          {run.isError ? (
            <p className="text-[12px] text-critical">{(run.error as Error).message}</p>
          ) : null}
        </CardBody>
      </Card>

      {result ? <ResultTable result={result} /> : null}
    </div>
  );
}

function ResultTable({ result }: { result: QueryResultPayload }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Result</CardTitle>
        <div className="flex items-center gap-2">
          <Badge tone="neutral">{result.rowCount} rows</Badge>
          {result.truncated ? <Badge tone="warning">truncated</Badge> : null}
          <span className="mono text-[11px] text-text-muted">{result.target}</span>
        </div>
      </CardHeader>
      <CardBody className="p-0">
        {result.rows.length === 0 ? (
          <p className="p-3 text-[12.5px] text-text-muted">The statement returned no rows.</p>
        ) : (
          <div className="max-h-[460px] overflow-auto scroll-thin">
            <table className="w-full border-collapse text-[12px]">
              <thead className="sticky top-0 bg-panel-2">
                <tr>
                  {result.columns.map((column) => (
                    <th
                      key={column}
                      scope="col"
                      className="border-b border-border px-3 py-1.5 text-left text-[10.5px] uppercase tracking-wide text-text-muted"
                    >
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, rowIndex) => (
                  <tr key={rowIndex} className="border-b border-border/50">
                    {row.map((cell, cellIndex) => (
                      <td
                        key={cellIndex}
                        className="mono max-w-[380px] truncate px-3 py-1 align-top"
                        title={cell === null ? "NULL" : String(cell)}
                      >
                        {cell === null ? (
                          <span className="text-text-faint">NULL</span>
                        ) : (
                          String(cell)
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-[10.5px] uppercase tracking-wide text-text-faint">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

