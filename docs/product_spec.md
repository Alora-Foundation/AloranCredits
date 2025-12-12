# Aloran Treasury Console - Product Specification

## Platform & Packaging
- **Supported OS:** Windows desktop is required. Secondary support for macOS/Linux can be added, but Windows packaging (e.g., MSIX or PyInstaller-based installer) is in scope.
- **Runtime:** Python desktop application with GPU-accelerated/modern UI toolkit (e.g., Qt/PySide6) to deliver a clean, responsive experience.
- **Offline considerations:** Application should allow wallet interactions to be locked or paused if RPC endpoints are unreachable.

## Network Modes
- **Cluster switching:** Built-in selector for **Mainnet**, **Testnet**, and **Devnet** to enable experimentation before using real funds.
- **RPC configuration:** Allow setting primary and fallback RPC URLs per cluster with 2025-era Solana features enabled (compute budget tuning, priority fees, and transaction versioning).

## Wallet & Key Management
- **Built-in treasury wallet:** Native Solana wallet inside the app to hold SOL for fees and SPL tokens. Supports creating, importing (seed phrase), and exporting encrypted backups.
- **Security:** Passphrase/PIN lock, idle auto-lock, and encryption at rest (OS keychain where available). Optional hardware-wallet support can be staged later.
- **Multisig:** Optional integration with SPL Token Multisig for high-value operations.

## SPL Token Control (2025-ready)
- **Token lifecycle:** Create new SPL mints or manage existing ones. Full control over mint authority, freeze authority, and supply (mint/burn).
- **Transfers & accounts:** Transfer tokens, manage associated token accounts, batch/airdrop via CSV, and close empty accounts to reclaim rent.
- **Token-2022 extensions:** Support latest features such as transfer hooks, default account state, mint close authority, interest-bearing/metadata updates, and required memo/transfer fees where applicable.
- **Simulation & safety:** Preflight simulations, fee estimation, rate-limit and spend-limit guards, and transaction review before signing.

## Theme & UX
- **Dark mode first** with the following palette:
  - Dark Blue: `#078D70`
  - Teal: `#26CEAA`
  - Light Teal: `#99E8C2`
  - White (Center): `#FFFFFF`
  - Light Green: `#7BADE2`
  - Medium Blue: `#5049CC`
  - Dark Blue/Purple: `#3D1A78`
- Modern, minimal layouts with high-contrast typography and clear action hierarchies.
- Explorer links, activity timeline, and balance summaries for SOL and the managed SPL token.

## Treasury Operations
- **Batch tools:** CSV-driven airdrops, scheduled distributions, and batched burns/mints with progress tracking.
- **History & auditing:** Exportable logs of transactions and role-based access (operators vs. administrators) in a future phase.
- **Cluster-aware safeguards:** Require explicit confirmation when operating on Mainnet versus test clusters.

## Update & Observability
- **Updates:** In-app update checks with release notes; optional auto-download for Windows builds.
- **Logging:** Structured logs with redaction of secrets; user export for support. Optional Sentry/telemetry toggle.

## Open Questions / Next Decisions
- Final choice of UI toolkit (e.g., PySide6 vs. Tauri/Electron front-end with Python backend).
- Packaging preference for Windows (MSIX vs. installer executable) and code-signing requirements.
- Required hardware-wallet support at launch.
- Whether to ship a built-in devnet faucet helper for quick SOL top-ups during testing.

## Milestones (proposed)
1. **Foundations:** Project scaffolding, theme, wallet creation/import, network switching, RPC config.
2. **Token Control:** Mint management UI, transfers, burns, authority management, and simulations.
3. **Advanced Features:** Token-2022 extensions, batch tools, logs/export, multisig, and update mechanism.
