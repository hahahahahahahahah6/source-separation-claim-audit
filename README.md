# Documentation claim auditor

An offline static checker comparing documentation statements with Python AST evidence.
It reads the root README.md and Markdown files beneath any docs directory.
Fenced blocks are excluded; inline code counts. It never executes audited source,
uses the network, or collects telemetry.

Install and run with Python 3.9 or later:

```sh
python3 -m pip install .
python3 -m source_separation_claim_audit . --json
source-separation-claim-audit . --verbose
python3 -m unittest discover
```

Use repeatable `--ignore PATH` to exclude a relative path and its descendants.
`--fail-on LOW|MEDIUM|HIGH` sets the failure threshold (default HIGH).
`--version` prints 0.1.0. Exit status is 0 below threshold, 2 for qualifying
findings, and 1 for usage or I/O errors. JSON includes verdict, findings,
production_evidence and test_evidence. Each finding has id, severity and message.
A verdict of FAIL can still exit 0 when all findings fall below the threshold.

The checker recognizes these finding identifiers:

```text
documented-source-separation-claim-false
documented-no-source-separation-claim-false
```

Evidence is confined to each module. Test evidence is reported separately.
Fixtures, documentation examples, symbolic links and invalid syntax provide no
production evidence. Static patterns do not establish runtime correctness.

MIT licensed. No services or credentials are required.
