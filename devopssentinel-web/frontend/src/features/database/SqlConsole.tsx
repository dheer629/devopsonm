import { useState, type ReactNode } from "react";

import { useRunQuery, useSqlConsole } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { QueryResultPayload } from "@/types";

/** The bundled demo fixtures, so the console is one click from working. */
const DEMO = {
  port: "30432",
  database: "demo",
  username: "demo",
  password: "demo-not-a-real-credential",
};

const DEFAULT_SQL =
  "select table_schema, table_name\nfrom information_schema.tables\norder by 1, 2\nlimit 50";

/** Opt-in read-only SQL console.
 *
 *  Disabled unless the backend runs with `DSWEB_ENABLE_SQL_CONSOLE=1`. The
 *  credentials typed here live only in this component's state and in one request
 *  body; the backend never stores, logs or audits them.
 */
export function SqlConsole() {
  const status = useSqlConsole();
  const run = useRunQuery();

  const [host, setHost] = useState(() => window.location.hostname || "127.0.0.1");
  const [port, setPort] = useState(DEMO.port);
  const [database, setDatabase] = useState(DEMO.database);
  const [username, setUsername] = useState(DEMO.username);
  const [password, setPassword] = useState("");
  const [sql, setSql] = useState(DEFAULT_SQL);

  const enabled = Boolean(status.data?.data.enabled && status.data?.data.driverAvailable);
  const result = run.data?.data;

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
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            <Field label="Host">
              <Input
                aria-label="Database host"
                value={host}
                onChange={(event) => setHost(event.target.value)}
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
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setHost(window.location.hostname || "127.0.0.1");
                setPort(DEMO.port);
                setDatabase(DEMO.database);
                setUsername(DEMO.username);
                setPassword(DEMO.password);
              }}
            >
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

