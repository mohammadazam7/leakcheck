import "@fontsource/schibsted-grotesk/400.css";
import "@fontsource/schibsted-grotesk/600.css";
import "@fontsource/schibsted-grotesk/800.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/600.css";
import "./styles.css";

import bridge from "./bridge.py?raw";
import {
  MEASURES,
  TITLES,
  createChecker,
  guessEntities,
  guessTarget,
  type Checker,
  type Choices,
  type Finding,
  type Loaded,
} from "./leak";
import { SAMPLES, type Sample } from "./samples";

type Source = Sample["id"] | "own";
type Table = Extract<Loaded, { ok: true }>;

const MAX_FILE_BYTES = 25 * 1024 * 1024;

const $ = <T extends HTMLElement>(id: string): T => {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing #${id}`);
  return node as T;
};

const el = (tag: string, className = "", text?: string): HTMLElement => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

const runtime = $("runtime");
const about = $("about");
const own = $("own");
const loadError = $("load-error");
const bench = $("bench");
const target = $<HTMLSelectElement>("target");
const time = $<HTMLSelectElement>("time");
const entities = $("entities");
const ignored = $("ignored");
const split = $("split");
const preview = $<HTMLTableElement>("preview");
const legend = $("legend");
const report = $("report");
const reportTitle = $("report-title");
const summary = $("summary");
const findings = $("findings");
const command = $("command");
const copy = $<HTMLButtonElement>("copy");
const trainFile = $<HTMLInputElement>("train-file");
const testFile = $<HTMLInputElement>("test-file");
const tabs: Record<Source, HTMLButtonElement> = {
  careless: $("pick-careless"),
  careful: $("pick-careful"),
  own: $("pick-own"),
};

const base = new URL(".", document.baseURI).href;
let checker: Checker | null = null;
let source: Source = "careless";
let table: Table | null = null;
let choices: Choices = { target: "", entities: [], time: "", ignore: [] };
let names = { train: "train.csv", test: "test.csv" };

const percent = (share: number): string => `${(share * 100).toFixed(share > 0.0995 ? 0 : 1)}%`;
const count = (n: number): string => n.toLocaleString("en-US");

function fail(message: string): void {
  loadError.textContent = message;
  loadError.hidden = false;
}

/** Describe the two files and reset the column choices for them. */
function open(trainCsv: string, testCsv: string, preset?: Choices): void {
  if (!checker) return;
  loadError.hidden = true;
  const loaded = checker.load(trainCsv, testCsv);
  if (!loaded.ok) {
    table = null;
    bench.hidden = report.hidden = true;
    fail(loaded.message);
    return;
  }
  table = loaded;
  const guess = guessTarget(loaded.columns);
  choices = preset
    ? { ...preset, entities: [...preset.entities], ignore: [] }
    : { target: guess, entities: guessEntities(loaded.columns, guess), time: "", ignore: [] };
  bench.hidden = report.hidden = false;
  drawRoles();
  check();
}

function drawRoles(): void {
  if (!table) return;
  target.replaceChildren(...table.columns.map((c) => new Option(c.name, c.name, false, c.name === choices.target)));
  const dates = table.columns.filter((c) => c.kind === "date" && c.name !== choices.target);
  time.replaceChildren(
    new Option(dates.length ? "Not split by date" : "No date columns in these files", "", false, !choices.time),
    ...dates.map((c) => new Option(c.name, c.name, false, c.name === choices.time)),
  );
  time.disabled = dates.length === 0;
  entities.replaceChildren(
    ...table.columns
      .filter((c) => c.name !== choices.target && c.name !== choices.time)
      .map((c) => {
        const label = el("label", "chip");
        const box = document.createElement("input");
        box.type = "checkbox";
        box.checked = choices.entities.includes(c.name);
        box.addEventListener("change", () => {
          choices.entities = box.checked
            ? [...choices.entities, c.name]
            : choices.entities.filter((name) => name !== c.name);
          check();
        });
        label.append(box, el("span", "", c.name));
        return label;
      }),
  );
}

function drawIgnored(): void {
  ignored.hidden = choices.ignore.length === 0;
  ignored.replaceChildren(el("p", "", "Left out of the check"));
  for (const name of choices.ignore) {
    const button = el("button", "restore", `Put ${name} back`) as HTMLButtonElement;
    button.type = "button";
    button.addEventListener("click", () => {
      choices.ignore = choices.ignore.filter((n) => n !== name);
      check();
    });
    ignored.append(button);
  }
}

/** The first training rows, with every column a finding names dyed. */
function drawTable(found: Finding[]): void {
  if (!table) return;
  const dyed = new Set(found.map((f) => f.column).filter((c): c is string => c !== null));
  const role = (name: string): string =>
    name === choices.target
      ? "predicted"
      : name === choices.time
        ? "split date"
        : choices.entities.includes(name)
          ? "who"
          : choices.ignore.includes(name)
            ? "left out"
            : "";
  const head = el("tr");
  table.columns.forEach((c) => {
    const th = el("th", dyed.has(c.name) ? "dyed" : "");
    th.setAttribute("scope", "col");
    th.append(el("span", "name", c.name));
    const tag = role(c.name);
    th.append(el("span", tag ? "role" : "kind", tag || c.kind));
    head.append(th);
  });
  const body = table.preview.map((row) => {
    const tr = el("tr");
    row.forEach((value, i) => {
      const name = table!.columns[i].name;
      const td = el("td", dyed.has(name) ? "dyed" : "", value.replace(/ 00:00:00(\.0+)?$/, ""));
      if (value === "") td.append(el("span", "empty", "empty"));
      tr.append(td);
    });
    return tr;
  });
  const thead = el("thead");
  thead.append(head);
  const tbody = el("tbody");
  tbody.append(...body);
  preview.replaceChildren(thead, tbody);

  const total = table.train_rows + table.test_rows;
  const train = el("div", "side train", `${names.train}: ${count(table.train_rows)} rows to learn from`);
  const test = el("div", "side test", `${names.test}: ${count(table.test_rows)} rows to score on`);
  train.style.flexGrow = String(Math.max(table.train_rows / total, 0.3));
  test.style.flexGrow = String(Math.max(table.test_rows / total, 0.4));
  split.replaceChildren(train, test);
  legend.textContent = dyed.size
    ? "The first six training rows. Marked columns are named in a finding below."
    : "The first six training rows.";
}

function meter(f: Finding): HTMLElement {
  const box = el("div", "measure");
  const figure = f.check === "single_feature" ? f.value.toFixed(3) : percent(f.value);
  box.append(el("span", "figure", figure), el("span", "what", MEASURES[f.check]));
  const bar = el("div", "meter");
  bar.setAttribute("role", "img");
  bar.setAttribute("aria-label", `${figure} ${MEASURES[f.check]}`);
  const fill = el("div", "fill");
  fill.style.width = `${Math.max(f.value * 100, 1.5)}%`;
  bar.append(fill);
  box.append(bar);
  return box;
}

function drawFinding(f: Finding): HTMLElement {
  const item = el("li", "finding");
  const heading = el("h3", "", TITLES[f.check]);
  if (f.column) heading.append(" ", el("code", "", f.column));
  // The sentence is the package's own; a column name at its start keeps its spelling.
  item.append(heading, meter(f), el("p", "detail", `${f.detail}.`));
  if (f.column && f.column !== choices.time && (f.check === "single_feature" || f.check === "time")) {
    const column = f.column;
    const button = el("button", "leave-out", `${column} is known in advance: leave it out`) as HTMLButtonElement;
    button.type = "button";
    button.addEventListener("click", () => {
      choices.ignore = [...choices.ignore, column];
      check();
    });
    item.append(button);
  }
  return item;
}

function commandLine(): string {
  const quote = (name: string): string => (/^[\w.-]+$/.test(name) ? name : `'${name.replace(/'/g, "'\\''")}'`);
  const parts = ["leakcheck", quote(names.train), quote(names.test), "--target", quote(choices.target)];
  for (const name of choices.entities) parts.push("--entity", quote(name));
  if (choices.time) parts.push("--time", quote(choices.time));
  for (const name of choices.ignore) parts.push("--ignore", quote(name));
  return parts.join(" ");
}

function check(): void {
  if (!checker || !table) return;
  drawIgnored();
  command.textContent = commandLine();
  const result = checker.run(choices);
  if (!result.ok) {
    report.dataset.state = "error";
    reportTitle.textContent = "These files could not be checked";
    summary.textContent = result.message;
    findings.replaceChildren();
    drawTable([]);
    return;
  }
  const n = result.findings.length;
  report.dataset.state = n ? "leaks" : "clean";
  reportTitle.textContent = n ? `${n} ${n === 1 ? "finding" : "findings"} in this split` : "Nothing found in this split";
  summary.textContent = n
    ? "A score measured on these test rows would be higher than the model deserves. Each finding says what was measured, so you can judge it."
    : "None of the checks fired on these columns. That is not proof the split is clean, only that these leaks are not in it.";
  findings.replaceChildren(...result.findings.map(drawFinding));
  drawTable(result.findings);
}

async function pick(next: Source): Promise<void> {
  source = next;
  for (const [id, button] of Object.entries(tabs)) button.setAttribute("aria-pressed", String(id === next));
  own.hidden = next !== "own";
  loadError.hidden = true;
  if (next === "own") {
    about.textContent = "Two files with the same columns: the rows a model learns from and the rows it is scored on.";
    await readOwn();
    return;
  }
  const sample = SAMPLES.find((s) => s.id === next)!;
  about.textContent = sample.about;
  names = { train: "train.csv", test: "test.csv" };
  if (!checker) return;
  const [train, test] = await Promise.all(
    ["train", "test"].map(async (side) => (await fetch(`${base}samples/${sample.id}/${side}.csv`)).text()),
  );
  if (source === next) open(train, test, sample.choices);
}

async function readOwn(): Promise<void> {
  const train = trainFile.files?.[0];
  const test = testFile.files?.[0];
  if (!train || !test) {
    table = null;
    bench.hidden = report.hidden = true;
    return;
  }
  const large = [train, test].find((file) => file.size > MAX_FILE_BYTES);
  if (large) {
    bench.hidden = report.hidden = true;
    fail(`${large.name} is larger than 25 MB. Install leakcheck to check files of any size.`);
    return;
  }
  names = { train: train.name, test: test.name };
  const [trainCsv, testCsv] = await Promise.all([train.text(), test.text()]);
  if (source === "own") open(trainCsv, testCsv);
}

for (const [id, button] of Object.entries(tabs)) button.addEventListener("click", () => void pick(id as Source));
trainFile.addEventListener("change", () => void readOwn());
testFile.addEventListener("change", () => void readOwn());
target.addEventListener("change", () => {
  choices.target = target.value;
  choices.entities = choices.entities.filter((name) => name !== target.value);
  if (choices.time === target.value) choices.time = "";
  drawRoles();
  check();
});
time.addEventListener("change", () => {
  choices.time = time.value;
  choices.entities = choices.entities.filter((name) => name !== time.value);
  drawRoles();
  check();
});
copy.addEventListener("click", () => {
  void navigator.clipboard.writeText(command.textContent ?? "").then(() => {
    copy.textContent = "Copied";
    window.setTimeout(() => (copy.textContent = "Copy command"), 1600);
  });
});

async function start(): Promise<void> {
  about.textContent = SAMPLES[0].about;
  const { loadPyodide } = (await import(/* @vite-ignore */ `${base}pyodide/pyodide.mjs`)) as typeof import("pyodide");
  // pyarrow prints a harmless line about signal handlers on every CSV read.
  const py = await loadPyodide({ indexURL: `${base}pyodide/`, stderr: () => undefined });
  runtime.textContent = "Loading pyarrow, about 14 MB the first time";
  const manifest = (await (await fetch(`${base}py/manifest.json`)).json()) as { native: string[]; pure: string[] };
  await py.loadPackage(
    manifest.native.map((name) => `${base}py/${name}`),
    { checkIntegrity: false, messageCallback: () => undefined },
  );
  for (const name of manifest.pure) {
    py.unpackArchive(await (await fetch(`${base}py/${name}`)).arrayBuffer(), "wheel");
  }
  checker = createChecker(py as never, bridge);
  runtime.textContent = `leakcheck ${checker.version} running in this tab`;
  runtime.dataset.ready = "true";
  await pick(source);
}

start().catch((error: unknown) => {
  runtime.textContent = "Python could not start in this browser";
  runtime.dataset.ready = "failed";
  fail(`The page needs WebAssembly to run leakcheck. ${error instanceof Error ? error.message : String(error)}`);
});
