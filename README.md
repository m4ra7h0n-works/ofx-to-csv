# ofx-to-csv

Convert a single bank or credit-card OFX statement into a transaction CSV.

## Install

Python 3.10 or newer. From this repository:

```sh
python -m venv .venv
# Activate .venv using your shell's activation command, then:
python -m pip install .
```

No runtime dependencies beyond Python’s standard library. You can also run directly from the repository after installing its dependencies.

## Usage

```sh
python -m ofx_to_csv examples/statement.ofx transactions.csv
```

The output path must be new. Existing files are never overwritten. All conversion runs locally; the CLI makes no network requests. Conversion/validation errors exit with code 2. Run `python -m ofx_to_csv --help` for arguments.

Importable API (returns the number of exported rows):

```python
from ofx_to_csv import convert

convert("examples/statement.ofx", "transactions.csv")
```

Files under `examples/` are entirely fictional. Expected output:

```csv
date,name,memo,amount,fitid,type
2026-01-02,Sample supplies,Notebook & pen,-12.50,fictional-001,DEBIT
2026-01-03,Sample refund,,100.00,fictional-002,CREDIT
```

## Capabilities and limits

- Accepts a UTF-8 (optional BOM) `.ofx` file, up to 15 MiB. Supports bank/card OFX XML, including namespaced XML, and basic OFX 1.x SGML with explicitly closed containers and `OFXHEADER` / `DATA:OFXSGML` headers.
- Requires exactly one statement, an account ID, one three-letter currency and successful status codes when present. QFX/QBO paths, investments, correction records and transaction-level currency fields are rejected. Renaming a QFX/QBO file does not establish support: these formats share OFX syntax and cannot always be distinguished by contents.
- Exports only posted `STMTTRN` records as `date,name,memo,amount,fitid,type`. Pending `STMTTRNP` records are not exported: mixed files emit a warning with the skipped pending count; a pending-only file fails with an explanatory error and creates no CSV. A genuinely empty statement produces a header-only CSV. Account metadata and balance snapshots are not exported.
- Dates use the first eight OFX date digits, without timezone conversion; original timestamps are not retained. Amounts accept an optional minus sign, integers or dot-decimal values with one or two fractional digits, and up to 13 integer digits; no leading plus, separators or currency symbols. Output always has two decimal places (e.g. `-12` becomes `-12.00`). Each posted transaction requires exactly one nonempty `DTPOSTED`, `TRNAMT`, `FITID` and `TRNTYPE`. Dates and any supplied time must be valid. Types must be one of `CREDIT`, `DEBIT`, `INT`, `DIV`, `FEE`, `SRVCHG`, `DEP`, `ATM`, `POS`, `XFER`, `CHECK`, `PAYMENT`, `CASH`, `DIRECTDEP`, `DIRECTDEBIT`, `REPEATPMT`, `HOLD`, `OTHER`. Invalid transactions block the entire export; this is not full OFX schema validation.
- No deduplication, correction application, exchange-rate conversion, categories or direct bank connection. Spreadsheet-formula-leading text is prefixed with an apostrophe; numeric amounts remain numeric. Spreadsheet applications can still reinterpret identifiers: import those columns as text.

This independent project is not affiliated with, endorsed by or sponsored by Intuit or Quicken. Product names and trademarks belong to their respective owners.

## This CLI vs Online version

| Feature | This CLI | Online version |
| --- | --- | --- |
| Input | One UTF-8 `.ofx` bank/card statement | OFX, QFX, QBO; SGML or XML |
| Accounts and currencies | One statement, one account currency | Multiple accounts and currencies, kept separate |
| Output | Transactions CSV | Transactions CSV; XLSX with Transactions, Accounts, Validation |
| Account and balance snapshots | No | XLSX Accounts sheet, including empty accounts |
| Correction records | Rejects | Retains records; does not apply delete/replace actions |
| Preview and validation | CLI errors; no preview | Preview, validation and skipped-row CSV |

## Online version

[OFXcsv online](https://ofxcsv.pivlu.com/?utm_source=github&utm_medium=readme&utm_campaign=ofx-to-csv) is a separate online version by the same author, Zijian Xiao. The online version includes an installation-free preview and validation of accounts and transactions. Balances are retained as snapshots; it does not promise statement reconciliation or apply correction actions.

Free allowance, based on the supplied product information dated November 10, 2026:

Free after registration, no card: 2 complete files per account, up to 200 source transactions per file, including preview and all supported download formats. Each site allows 12 successful free files per network address in a rolling 30 days, shared across accounts. Free uploads allow 20 requests per account and network address per hour, including failures and date-order retries. Repeated downloads of the same result and failed conversions use no file allowance. When the free size or allowance is exceeded, buy an existing one-time pack and upload in paid mode. Normal supported-format limits and validation still apply; no free row truncation.

The local MIT-licensed CLI has no online quota. Visiting the link is optional; uploaded online files are processed by the online service.

## Tests

```sh
python -m pip install ".[test]"
python -m pytest
```

## License

MIT. Copyright (c) 2026 Zijian Xiao. See [LICENSE](LICENSE).
