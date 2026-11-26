import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { loadPyodide } from "pyodide";
import { beforeAll, describe, expect, it } from "vitest";

import { createChecker, guessEntities, guessTarget, type Checker, type Column } from "./leak";
import { SAMPLES } from "./samples";

// The same wheels, bridge and sample files the page uses, in the same Python runtime,
// started from Node instead of a browser. Run `npm run prepare-py` first.
const here = dirname(fileURLToPath(import.meta.url));
const pub = resolve(here, "../public");
const sample = (id: string, side: string) => readFileSync(resolve(pub, "samples", id, `${side}.csv`), "utf-8");
let checker: Checker;

beforeAll(async () => {
  const manifest = JSON.parse(readFileSync(resolve(pub, "py/manifest.json"), "utf-8")) as {
    native: string[];
    pure: string[];
  };
  // pyarrow prints a harmless line about signal handlers on every CSV read.
  const py = await loadPyodide({ indexURL: resolve(here, "../node_modules/pyodide"), stderr: () => undefined });
  await py.loadPackage(
    manifest.native.map((name) => resolve(pub, "py", name)),
    { checkIntegrity: false, messageCallback: () => undefined },
  );
  for (const name of manifest.pure) py.unpackArchive(new Uint8Array(readFileSync(resolve(pub, "py", name))), "wheel");
  checker = createChecker(py as never, readFileSync(resolve(here, "bridge.py"), "utf-8"));
});

describe("the real package, running in Pyodide", () => {
  it("reports its version", () => {
    expect(checker.version).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it.each(SAMPLES.map((s) => [s.label, s] as const))("sample: %s", (_label, s) => {
    const loaded = checker.load(sample(s.id, "train"), sample(s.id, "test"));
    expect(loaded.ok).toBe(true);
    const report = checker.run(s.choices);
    expect(report.ok && report.findings.map((f) => f.check)).toEqual(s.expect);
  });

  it("describes the files it read", () => {
    const loaded = checker.load(sample("careless", "train"), sample("careless", "test"));
    if (!loaded.ok) throw new Error(loaded.message);
    expect(loaded).toMatchObject({ train_rows: 1600, test_rows: 400 });
    expect(loaded.columns).toContainEqual({ name: "month", kind: "date" });
    expect(loaded.columns).toContainEqual({ name: "customer_id", kind: "text" });
    expect(loaded.preview).toHaveLength(6);
  });

  it("measures each finding as a share between 0 and 1", () => {
    checker.load(sample("careless", "train"), sample("careless", "test"));
    const report = checker.run(SAMPLES[0].choices);
    if (!report.ok) throw new Error(report.message);
    for (const f of report.findings) expect(f.value).toBeGreaterThan(0), expect(f.value).toBeLessThanOrEqual(1);
    expect(report.findings.find((f) => f.check === "entity_overlap")?.value).toBeCloseTo(0.937, 3);
  });

  it("leaves an ignored column out", () => {
    checker.load(sample("careless", "train"), sample("careless", "test"));
    const report = checker.run({ ...SAMPLES[0].choices, ignore: ["cancel_reason"] });
    expect(report.ok && report.findings.map((f) => f.check)).toEqual(["entity_overlap", "time"]);
  });

  it("finds copied rows", () => {
    const train = "id,score,label\na,1,0\nb,2,1\nc,3,0\nd,4,1\n";
    const test = "id,score,label\nb,2,1\ne,9,0\n";
    checker.load(train, test);
    const report = checker.run({ target: "label", entities: [], time: "", ignore: ["score"] });
    if (!report.ok) throw new Error(report.message);
    expect(report.findings).toMatchObject([{ check: "row_overlap", column: null, value: 0.5 }]);
  });

  it("says what is wrong instead of failing", () => {
    expect(checker.load("a,b\n1,2\n", "a,b\n1,2,3\n")).toMatchObject({ ok: false });
    checker.load("a,b\n1,2\n", "a,c\n1,2\n");
    const report = checker.run({ target: "b", entities: [], time: "", ignore: [] });
    expect(report).toMatchObject({ ok: false });
    expect(!report.ok && report.message).toContain("b");
  });
});

describe("first guesses for a visitor's own files", () => {
  const columns: Column[] = [
    { name: "patient_id", kind: "text" },
    { name: "visit", kind: "date" },
    { name: "age", kind: "number" },
    { name: "outcome", kind: "yes/no" },
  ];

  it("picks a column with a usual target name, else the last one", () => {
    expect(guessTarget(columns)).toBe("outcome");
    expect(guessTarget(columns.slice(0, 3))).toBe("age");
    expect(guessTarget([])).toBe("");
  });

  it("offers ID-like columns as entities, never the target", () => {
    expect(guessEntities(columns, "outcome")).toEqual(["patient_id"]);
    expect(guessEntities([{ name: "user_id", kind: "number" }], "user_id")).toEqual([]);
  });
});
