<p align="center">
  <img src="docs/assets/order-of-the-sinking-star-store.jpg" width="560" alt="Order of the Sinking Star Steam artwork with a crowned character facing left">
</p>

<h1 align="center">Editor-of-the-Sinking-Star</h1>

<p align="center"><strong>In-game recorder and macro editor for Order of the Sinking Star</strong></p>

> **Preview notice**  
> This project is still in development and is not a stable release. Last local runnable check: **2026-10-30** (startup and related tool checks; not comprehensive game or second-PC acceptance).  
> If you encounter a problem, please report it through [Issues](https://github.com/scenesuki/Editor-of-the-Sinking-Star/issues), including the version and steps to reproduce.  
> *The repository is not public yet; the Issue page will become available after publication.*

`0.1.0-preview` · `Windows 10 / 11 x64` · `中文 / English` · `MIT`

[简体中文](README.md) · [Usage guide](docs/USAGE.en.md) · [License](licenses/LICENSE.md)

---

> **Play and record → Edit the timeline → Tune with checkpoints → Replay from the start**  

## Features

| Recording and editing | Saves and tuning |
| --- | --- |
| In-game two-column UI; short taps and live-state append | Fixed project start and isolated temporary campaigns |
| Insert, edit, delete, drag, and undo timeline edits | Repeatable checkpoint-based wait trials |
| Follow game bindings; configurable tool and mouse keys | In-project Pause, 0.25×, 1×, and 4× |
| Per-project intervals and extra waits | Independent full-save backup and restore |

## Quick start

1. Fully extract the ZIP into a writable folder. **Python and Frida are bundled.** Do not run inside the ZIP.
2. Close the game and editor. Use `SaveBackup.exe` to back up all saves first.
3. Start a supported game build. Run `SinkingStarEditor.exe` and select **Load in-game panel**.
4. Return to the game and press the **grave/tilde key** once to enable mouse mode. Create a project, play using short taps, then end recording and save.

> **Use short taps only. Do not hold keys.** The default interval is 250ms plus an optional 1000ms extra wait: 1250ms total. Both are configurable per project.

## Package contents

| Item | Purpose |
| --- | --- |
| `SinkingStarEditor.exe` | Start here: load the in-game editor |
| `SaveBackup.exe` | Independent full-save backup and restore; close the game and editor first |
| `README.md` / `README.en.md` | Chinese / English overview |
| `docs/` | Chinese / English usage guides and header artwork |
| `licenses/` | MIT and original third-party license texts |
| `metadata/` | Build information and file checksums |
| `_internal/`, `SSEKeyWorker.exe`, `portable.json` | Required runtime files; keep together, do not launch the helper manually |
| `data/` | Your projects, settings, logs and backups; created when first run |

**Preserve `data/` when updating.** Do not move an unfinished project session to another PC. See the [usage guide](docs/USAGE.en.md) for recovery rules.

## Current limits

- **Quick complete P is disabled in the portable Preview.** Experimental code remains in the development version without a usability guarantee.
- Only registered game builds are accepted. See the [usage guide](docs/USAGE.en.md) for full fingerprints, procedures, and recovery rules.
- Cross-PC project migration, playback speed control, direct Queen selection, held/combined inputs, and gamepad recording are unsupported.
- Related tool and local startup checks have been performed. Other PCs, game action effects, and routes still need user feedback.

## Next development step

The next development step is the P key, which will quickly complete levels from the overworld map to make recording overworld puzzle-solving easier. Relevant interfaces have been identified, but the implementation remains to be developed.

## Inspiration and acknowledgements

Thanks to [qiekn/ootss-cmd](https://github.com/qiekn/ootss-cmd). Its **Solution Player / Editor** informed this project's step-based editing, input playback, and use of native game undo/restart. Its game-memory-layout and speed-control material also provided technical references.

`ootss-cmd` is not a runtime dependency. Its original license is preserved in [ootss-cmd-LICENSE.txt](licenses/ootss-cmd-LICENSE.txt).

---

Own code uses [MIT](licenses/LICENSE.md); see the [third-party notices](licenses/THIRD_PARTY_NOTICES.md) for other terms. Header artwork is from the [Steam store](https://store.steampowered.com/app/499170/) and remains the property of its respective rights holders. No game executable or user saves are included. This project is unaffiliated with the game's developer.
