/** Types and helpers shared by the page and its tests. The checking itself is Python. */

export interface Column {
  name: string;
  kind: "date" | "number" | "yes/no" | "text";
}

export type Loaded =
  | { ok: true; train_rows: number; test_rows: number; columns: Column[]; test_columns: string[]; preview: string[][] }
  | { ok: false; message: string };

export interface Finding {
  check: "single_feature" | "row_overlap" | "entity_overlap" | "time";
  column: string | null;
  value: number;
  detail: string;
}

export type Report =
  | { ok: true; train_rows: number; test_rows: number; findings: Finding[] }
  | { ok: false; message: string };

export interface Choices {
  target: string;
  entities: string[];
  time: string;
  ignore: string[];
}

export interface Checker {
  version: string;
  load(trainCsv: string, testCsv: string): Loaded;
  run(choices: Choices): Report;
}

interface PyGlobals {
  get(name: string): (...args: string[]) => string;
}

/** Wrap the bridge functions of a Pyodide that already has the wheels installed. */
export function createChecker(py: { runPython(code: string): unknown; globals: PyGlobals }, bridge: string): Checker {
  py.runPython(bridge);
  const load = py.globals.get("load");
  const run = py.globals.get("run");
  return {
    version: py.globals.get("version")(),
    load: (trainCsv, testCsv) => JSON.parse(load(trainCsv, testCsv)) as Loaded,
    run: (choices) => JSON.parse(run(JSON.stringify(choices))) as Report,
  };
}

/** A first guess at the column being predicted: a common name, else the last column. */
export function guessTarget(columns: Column[]): string {
  const names = columns.map((c) => c.name);
  const common = ["target", "label", "y", "churned", "outcome", "class"];
  return names.find((n) => common.includes(n.toLowerCase())) ?? names[names.length - 1] ?? "";
}

/** Columns that look like the ID of a person or thing: text, named like an ID. */
export function guessEntities(columns: Column[], target: string): string[] {
  return columns
    .filter((c) => c.name !== target && /(^|_)(id|key|uuid)$|customer|patient|user|account/i.test(c.name))
    .filter((c) => c.kind === "text" || c.kind === "number")
    .map((c) => c.name);
}

export const TITLES: Record<Finding["check"], string> = {
  single_feature: "One column gives the answer away",
  row_overlap: "The same rows are on both sides",
  entity_overlap: "The same entities are on both sides",
  time: "Training data comes from after the test period",
};

/** How to read `value` for each check, for the meter under a finding. */
export const MEASURES: Record<Finding["check"], string> = {
  single_feature: "scored by this column alone, where 1.000 is a perfect prediction",
  row_overlap: "of test rows are copies of training rows",
  entity_overlap: "of the entities in test also appear in training",
  time: "of training rows are dated in the test period",
};
