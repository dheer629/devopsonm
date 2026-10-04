import { useEffect, useState, type ReactNode } from "react";

import { useRunQuery, useSqlConsole } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { DEMO_DATABASE, DEMO_DATABASE_PORT, resolveLiveHost } from "@/lib/live";
import type { QueryResultPayload } from "@/types";

const DEFAULT_SQL =
  "select table_schema, table_name\nfrom information_schema.tables\norder by 1, 2\nlimit 50";

/** Opt-in read-only SQL console.
 *
 *  Disabled unless the backend runs with `DSWEB_ENABLE_SQL_CONSOLE=1`. The
 *  credentials typed here live only in this component's state and in one request
 *  body; the backend never stores, logs or audits them.
 *
 *  The host prefills with the node address the backend reports, because the
 *  bundled demo endpoint is a NodePort: it answers on a *node*, never on
 *  `127.0.0.1` (inside a vcluster only the API port is published to the host).
 */
export function SqlConsole() {
  const status = useSqlConsole();
  const run = useRunQuery();

  const suggestedHost = resolveLiveHost(status.data?.data.defaultHost, window.location.hostname);

  const [host, setHost] = useState(suggestedHost);
  const [hostTouched, setHostTouched] = useState(false);
  const [port, setPort] = useState(DEMO_DATABASE_PORT);
  const [database, setDatabase] = useState(DEMO_DATABASE.name);
  const [username, setUsername] = useState(DEMO_DATABASE.username);
  const [password, setPassword] = useState("");
  const [sql, setSql] = useState(DEFAULT_SQL);

  // The node address arrives with the console status; adopt it until the
  // operator types a host of their own.
  useEffect(() => {
    if (!hostTouched) setHost(suggestedHost);
  }, [hostTouched, suggestedHost]);

  const enabled = Boolean(status.data?.data.enabled && status.data?.data.driverAvailable);
  const result = run.data?.data;

  const fillDemo = () => {
    setHost(suggestedHost);
    setHostTouched(false);
    setPort(DEMO_DATABASE_PORT);
    setDatabase(DEMO_DATABASE.name);
    setUsername(DEMO_DATABASE.username);
    setPassword(DEMO_DATABASE.password);
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
              {status.data?.data.reason ?? "checking the console status…"} — restart the backend with{" "}
              <span className="mono">DSWEB_ENABLE_SQL_CONSOLE=1</span> to turn it on.
            </p>
          ) : null}
          <p className="text-[11.5px] text-text-muted">
            Credentials are used for this one request only — never stored, logged or audited. Exactly
            one read-only statement is accepted (SELECT / WITH / SHOW / EXPLAIN / TABLE / VALUES /
            &#92;d) and the session is forced read-only on the server, so it cannot mutate data.
          </p>
          <p className="text-[11.5px] text-text-faint">
            Host prefills with the cluster node address
            {status.data?.data.defaultHost ? (
              <>
                {" "}
                (<span className="mono">{status.data.data.defaultHost}</span>)
              </>
            ) : null}
            , because a NodePort answers on a node — not on <span className="mono">127.0.0.1</span>.
            The bundled demo database is <span className="mono">{suggestedHost}:{DEMO_DATABASE_PORT}</span>{" "}
            (user/db/password <span className="mono">demo</span>).
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            <Field label="Host">
              <Input
                aria-label="Database host"
                value={host}
                onChange={(event) => {
                  setHostTouched(true);
                  setHost(event.target.value);
                }}
              />
            </Field>
            <Field label="Port">
              <Input
                aria-label="Database port"
                value={port}
                onChange={(event) => setPort(event.target.value)}
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
            <Button variant="outline" size="sm" onClick={fillDemo}>
              Fill demo credentials
            </Button>
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

