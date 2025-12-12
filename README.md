# AloranCredits

Product notes and prototype code for the **Aloran Treasury Console**, a desktop Python application for full lifecycle control of an SPL token.

## Current Scope
- Windows desktop support is required; Mac/Linux can be optional follow-ons.
- Dark-mode first UI using the palette:
  - Dark Blue `#078D70`
  - Teal `#26CEAA`
  - Light Teal `#99E8C2`
  - White `#FFFFFF`
  - Light Green `#7BADE2`
  - Medium Blue `#5049CC`
  - Dark Blue/Purple `#3D1A78`
- Supports Mainnet, Testnet, and Devnet switching to experiment safely.
- Aims to incorporate 2025-era Solana features (priority fees, transaction versioning, token-2022 extensions).

See [`docs/product_spec.md`](docs/product_spec.md) for the detailed specification, open questions, and proposed milestones.

## Prototype UI (local run)
The PySide6 prototype now includes a richer layout with network selection, wallet lock/unlock simulation, session key
generation/import, balance refresh, RPC health checks with endpoint failover, and associated token account helpers
to create or close treasury ATAs. The activity list captures each action for quick auditing while iterating on token
flows.

1. Install dependencies (ideally in a virtual environment):
   ```bash
   pip install -r requirements.txt
   ```
2. Launch the prototype window:
   ```bash
   python -m aloran_treasury
   ```

> The prototype now exercises Solana RPCs for balance lookups, endpoint health checks, and ATA lifecycle actions. Production authority flows and mint controls remain to be wired in.
