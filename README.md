# Phantom Sniper (paper trading)

This repository is a local, deterministic **paper-trading simulator** for
exploring a simple token-screening and staged-exit workflow. It does not trade
cryptocurrency and is not investment advice.

The repository originally contained only print-only placeholders. Their
descriptions imply live wallet rotation, token sniping, reinvestment, and social
posting, but do not define safe live-trading requirements. This implementation
therefore uses invented, configurable educational defaults and deliberately
does not connect to a blockchain, sign transactions, access private keys, call
Telegram, or post to TikTok. The uploaded starter archive is retained unchanged.

## Run a simulation

Requires Python 3.10 or newer; no third-party packages are needed.

On Windows, initialize and verify the project with:

```powershell
.\setup.ps1
```

This checks the Python version, runs the tests, and creates a sample run in
`paper_runs`. To create another run:

```powershell
.\run_paper.ps1
```

You can pass a different snapshot file, config, and output directory:

```powershell
.\run_paper.ps1 -MarketData .\my_snapshots.json -Config .\paper_config.json -OutputDirectory .\paper_runs
```

The setup and run scripts only invoke local Python code. They do not install
packages, create a persistent background task, use credentials, execute
transactions, or send notifications.

```powershell
py -3 sniper_ai.py market_data.example.json
```

To save the report:

```powershell
py -3 sniper_ai.py market_data.example.json --output report.json
```

For a scheduled one-shot run that archives each report and generates local
Telegram/TikTok **drafts**:

```powershell
py -3 daily_loop.py market_data.example.json --output-dir paper_runs
```

`daily_loop.py` is designed to be invoked by an external scheduler at the
desired cadence. Each invocation reads the supplied snapshot file and writes a
timestamped JSON report and message drafts; it does not run an always-on polling
loop. Review the drafts manually. It never connects to or posts to either
platform.

The program prints a JSON report to standard output by default. Input or
configuration errors are reported on standard error with a nonzero exit code.
No report or account state is saved unless `--output` is provided.
The scheduled runner is the exception: it writes its timestamped run artifacts
to `paper_runs` unless `--output-dir` is specified.

## Input format

Provide a JSON array of token snapshots. Each snapshot requires a unique
`mint`, a `symbol`, nonnegative `liquidity_units` and `volume_units`, and a
`price_path` containing positive prices. The first price is the simulated
entry-time price; later prices are observations in chronological order. The
example file is synthetic and is not connected to a market feed.

## Paper-trading rules

`paper_config.json` contains all simulator defaults. They are examples, not
validated trading rules:

- Start with 0.97 **abstract units**; this is not USD or SOL.
- Rank eligible tokens by their volume-to-liquidity ratio, subject to the
  minimum liquidity and ratio filters.
- Allocate a fraction of the remaining virtual balance to each trade, charge
  a simulated fee on entry and each exit, and rotate through named virtual
  wallets. Virtual wallets do not contain or represent real keys or funds.
- Sell configured portions of the initial position when observed prices reach
  configured gains, stop the remaining position at the configured loss, and
  close any remainder at the final supplied price.
- Transfer the configured share of positive realized profit to a virtual
  reserve; losses are not replenished.
- Produce clearly labeled, local-only Telegram alerts and TikTok caption
  drafts. They contain no mint addresses and are never sent automatically.

These simplified rules do not model slippage, liquidity changes, failed
transactions, taxes, malicious tokens, or real-world execution. Historical
price paths are used only after screening the first observation; this is a
toy simulator, not a predictor of future returns.

## Tests

```powershell
py -3 -m unittest discover -s tests -v
```
