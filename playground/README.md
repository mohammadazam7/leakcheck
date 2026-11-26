# The leakcheck playground

A static page that runs the leakcheck package in the browser. There is no server: the
page starts Pyodide (Python compiled to WebAssembly), loads pyarrow and the leakcheck
wheel built from this checkout, and calls `leakcheck.checks.check` on the visitor's data.

```bash
pip install -r ../requirements-dev.lock
npm ci
npm run prepare-py   # Pyodide runtime, wheels and sample splits into public/
npm test             # the samples and the bridge, in Pyodide under Node
npm run dev
```

`src/bridge.py` is all the Python the page adds. `src/leak.test.ts` runs the same wheels,
bridge and sample files as the page, so a change to a check that alters what the samples
report fails here before it is deployed.
