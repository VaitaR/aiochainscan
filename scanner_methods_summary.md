# aiochainscan Scanner Methods Test Summary

**Test Date:** 2025-07-27 00:42:52
**Total Scanners:** 12
**Working Scanners:** 10

## Scanner Status Overview

| Scanner | Name | API Key | Methods | Success Rate | Status |
|---------|------|---------|---------|--------------|--------|
| `eth` | Etherscan | 🔑 ✅ | 21/44 | 47.7% | ✅ |
| `gnosis` | GnosisScan | 🔑 ✅ | 12/22 | 54.5% | ✅ |
| `linea` | LineaScan | 🔑 ✅ | 12/22 | 54.5% | ✅ |
| `polygon` | PolygonScan | 🔑 ✅ | 12/22 | 54.5% | ✅ |
| `arbitrum` | Arbiscan | 🔑 ✅ | 11/22 | 50.0% | ✅ |
| `base` | BaseScan | 🔑 ✅ | 10/22 | 45.5% | ✅ |
| `blast` | BlastScan | 🔑 ✅ | 10/22 | 45.5% | ✅ |
| `flare` | Flare Explorer | 🆓 N/A | 10/22 | 45.5% | ✅ |
| `optimism` | Optimism Etherscan | 🔑 ✅ | 10/22 | 45.5% | ✅ |
| `bsc` | BscScan | 🔑 ✅ | 9/22 | 40.9% | ✅ |
| `fantom` | FtmScan | 🔑 ✅ | 0/22 | 0.0% | ❌ |
| `xlayer` | OKLink X Layer | 🔑 ❌ | 0/0 | 0.0% | ❌ |

## Method Success by Module

- **account**: 29/40 (72.5%)
- **block**: 0/30 (0.0%)
- **contract**: 8/20 (40.0%)
- **gas_tracker**: 4/20 (20.0%)
- **logs**: 1/10 (10.0%)
- **proxy**: 28/30 (93.3%)
- **stats**: 16/30 (53.3%)
- **token**: 0/20 (0.0%)
- **transaction**: 20/20 (100.0%)

## Key Findings

- **10/12** scanners have working methods
- **10** scanners have API keys configured
- **1** scanners need API key setup

## Recommendations

### API Keys Needed:
- `xlayer` → Set `OKLINK_X_LAYER_KEY`

### Working Scanners:
- `arbitrum` (Arbiscan): 11 working methods
- `base` (BaseScan): 10 working methods
- `blast` (BlastScan): 10 working methods
- `bsc` (BscScan): 9 working methods
- `eth` (Etherscan): 21 working methods
- `flare` (Flare Explorer): 10 working methods
- `gnosis` (GnosisScan): 12 working methods
- `linea` (LineaScan): 12 working methods
- `optimism` (Optimism Etherscan): 10 working methods
- `polygon` (PolygonScan): 12 working methods
