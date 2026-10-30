# Run and build from source

Windows 10/11 x64, Python 3.11 x64 with Tkinter. **The source ZIP contains no EXEs or third-party runtime.** Reading the documentation requires no dependencies.

## Run

Open PowerShell in the source root:

```powershell
python -m pip install --target .deps -r requirements.txt
$env:PYTHONPATH=".;.deps"
python -B release/entry.py
```

Check startup dependencies without connecting to the game:

```powershell
python -B release/entry.py --diagnostics diagnostics.json
```

Independent backup window: `python -B release/entry.py --backup`. See the [usage guide](USAGE.en.md); EXE names there refer to the packaged entry points.

## Build

```powershell
python -m pip install --target .build-deps -r release/requirements-build.txt
python -B release/build.py
```

Intermediate files go to `.build/`; deliverables go to `deliverables/`. The portable ZIP, source ZIP and `SHA256SUMS.txt` are generated together. Preview restrictions apply by default, including disabled P.

## Source contents

| Item | Purpose |
| --- | --- |
| `solution_editor/`, `research/` | Required Python and JS runtime source |
| `locales/` | Chinese and English translations |
| `release/` | Build entry points, documentation templates and license originals |
| `tests/` | Related release/backup tool checks, not game-route acceptance |
| `assets/`, `docs/`, `licenses/`, `metadata/` | Artwork, guides, licenses and integrity records |
| `portable.json`, `release_profile.json` | Portable data and Preview configuration; keep in place |
| `data/` | Personal data created at runtime; preserve on updates |

No game executable, user saves or developer-machine data is included. See the [usage guide](USAGE.en.md) for save protection, native-loading semantics and known limits.
