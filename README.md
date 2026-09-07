# apgmera+ (apgluxe)

A high-performance C++ search program for Conway's Game of Life and other cellular automata. It searches random initial configurations ("soups") and periodically uploads discoveries to [Catagolue](https://catagolue.hatsya.com/).

> **Note:** This repository is a maintained fork of Adam P. Goucher's original [GitLab repository](https://gitlab.com/apgoucher/apgmera.git), featuring an interactive terminal dashboard, libcurl upload support, and build improvements.

---

## Quick Start

### 1. Prerequisites (Linux / WSL)

Ensure you have a C++ compiler (`gcc` or `clang`), `make`, `pkg-config`, and `libcurl` development headers installed:

```bash
# Debian / Ubuntu / WSL:
sudo apt update && sudo apt install -y build-essential pkg-config libcurl4-openssl-dev python3

# Fedora / RHEL:
sudo dnf install -y gcc-c++ make pkgconf libcurl-devel python3

# Arch Linux:
sudo pacman -S --needed base-devel curl python
```

*(Optional: `pip install pillow` for animated GIF exports in the dashboard.)*

### 2. Clone & Compile

```bash
git clone https://github.com/Trizlet/apgmera-plus.git
cd apgmera-plus
./recompile.sh
```

By default, this configures and compiles for standard Life (`b3s23`) and asymmetric soups (`C1`).

### 3. Run

```bash
./apgluxe -n 20000000 -p 8 -k mykey
```

Replace `mykey` with your [payosha256 key](https://catagolue.hatsya.com/payosha256) (case-sensitive) to attribute uploaded hauls to your account, or omit `-k` to search anonymously.

---

## Live Terminal Dashboard (`apg_dashboard.py`)

This fork includes an interactive terminal dashboard and pattern visualizer that runs alongside `apgluxe` to monitor search progress, display haul statistics, and render newly discovered patterns in real time.

```bash
python3 apg_dashboard.py [options]

# Example:
python3 apg_dashboard.py -n 20000000 -p 8 -k mykey
```

### Dashboard Controls

| Key | Action |
|---|---|
| `Tab` | Toggle between side-by-side (logs + viewer) and fullscreen viewer |
| `c` | Cycle color palettes (Age Heatmap, Phosphor Green, Cyan, Amber, Rainbow) |
| `g` | Export current pattern animation as an animated GIF to `exports/` |
| `n` / `p` | Step forward / backward through patterns discovered in the current haul |
| `Space` | Pause or resume pattern animation |
| `r` | Reset animation back to generation 0 |
| `q` | Graceful shutdown (safely stops `apgluxe` and finalizes in-progress hauls) |

---

## Command-Line Options

Pass any of these options directly to `./apgluxe` or through `apg_dashboard.py`:

| Option | Description | Example |
|---|---|---|
| `-n <count>` | Number of soups per haul | `-n 20000000` |
| `-p <threads>` | Number of CPU worker threads | `-p 8` |
| `-k <key>` | Your Catagolue payosha256 key | `-k yourkey` |
| `-L 1` | Save hauls to local log files | `-L 1` |
| `-t 1` | Test mode (disables uploading to Catagolue) | `-t 1` |
| `-i <count>` | Run a fixed number of hauls, then exit | `-i 5` |
| `-v <ratio>` | Peer-verify hauls alongside searching | `-v 5` |
| `--rule <rule>` | Target a specific rule (requires recompile) | `--rule b36s245` |
| `--symmetry <sym>` | Target a specific symmetry (requires recompile) | `--symmetry D2_+1` |

To change the rule or symmetry, pass the flags to `recompile.sh` first:
```bash
./recompile.sh --rule b36s245 --symmetry D2_+1
```

---

## Performance & Acceleration

### GPU Searching (CUDA)

If you have an NVIDIA GPU (≥1.5 GB VRAM), it can be used as a preprocessor to discard uninteresting soups before CPU processing:

```bash
./recompile.sh --cuda
```

*(Note: `recompile.sh` automatically locates `nvcc` in standard CUDA directories if it is not already in your `$PATH`. CUDA searches upload to `b3s23/G1`.)*

Run with your desired CPU census threads:
```bash
./apgluxe -n 1000000000 -p 8 -k mykey
```

For multi-GPU systems, select a specific device via `CUDA_VISIBLE_DEVICES=<id>` or launch one process per GPU.

### Profile-Guided Optimization (PGO)

For CPU-only search on GCC/Clang:
```bash
./recompile.sh --profile
```

---

## Platform Notes

- **Linux**: Supported natively (x86-64).
- **macOS (Apple Silicon / M1+)**: Requires Rosetta 2 due to x86-64 assembly. Compile with:
  ```bash
  arch -x86_64 ./recompile.sh
  ```
- **Windows**: [WSL (Windows Subsystem for Linux)](https://learn.microsoft.com/windows/wsl/install) is strongly recommended for optimal performance. Cygwin is also supported (though `-p` multithreading is unavailable under Cygwin).

---

## Credits & License

- **apgluxe** and **lifelib** are written by Adam P. Goucher and licensed under the [MIT License](LICENCE.txt).
- Upstream repository: [gitlab.com/apgoucher/apgmera](https://gitlab.com/apgoucher/apgmera).
- Includes third-party components: CRYSTALS-Dilithium (CC-BY 4.0), SHA3/Keccak (MIT), SHA-256 (BSD 3-clause), and MD5.
