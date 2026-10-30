# Usage guide

[Back to README](../README.en.md) · [简体中文](使用细则.md)

For `0.1.0-preview`. Covers the portable package and the portable data layout of the included standalone source. **Use short taps only. Back up saves before editing.**

## 1. Startup and interface

- Fully extract into a writable folder; do not run inside the ZIP. Start the game, then load the panel through `SinkingStarEditor.exe`. Do not start `SSEKeyWorker.exe` manually.
- Press the grave/tilde key once to toggle mouse mode and again to return to gameplay; **no holding or Shift required**. Panel interactions are not recorded as gameplay.
- Recording, playback, and trials exit mouse mode after successful startup; failed requests keep the UI available. Opening mouse mode during playback stops sending. Losing focus exits mouse mode and stops automated input.
- Initial language follows Windows: Simplified Chinese for Chinese display languages, English otherwise. Manual language selection is remembered.
- Configure tool keys and the mouse toggle before opening a project if desired; resolve conflicts first. Change the two default delays only with a project open and recording/playback stopped, then **Apply timing** and save.

## 2. Projects and recording

| Action | Behavior |
| --- | --- |
| Create project | Natively save the campaign, capture a fixed start, load a tool-owned copy, and start recording |
| Open project | Load a fresh copy of the fixed start without recording |
| Append recording | Keep the live state and append at the end; no loading or replay. You assess synchronization |
| Play from start | Reload the fixed start, then execute the script |
| Save | Store the script and project settings without changing the fixed start |
| Leave project | Save edits, stop sending, release held keys, load the original campaign, then remove the owned temporary copy |

Autosaves in the temporary campaign do not update the original save—including `default`—or the fixed start. Recovery follows **native game loading**, so animation and other transient states may differ. It is not full-memory restoration.

### Default keys

| Key | Purpose |
| --- | --- |
| W/A/S/D, 1–9, X/V | Directions, characters, activation, and take/drop; actual keys follow game settings |
| Native undo, normally Z | Undo in the game and remove the latest ordinary recorded action |
| E | Remove only the latest recorded action; cancel a pending T marker first if present |
| T | Mark an extra wait before the next action without making the live game wait |
| P | Disabled in Preview; replace/delete old P steps. Affected playback is rejected before sending |

E/T and the mouse toggle are configurable; character numbers are fixed identifiers. One press records one entry, without its real timing. Holding a key may repeat in-game while recording only once. Z/E can affect earlier recording rounds and preserve existing waits. Use E to correct the record if native undo—for example after hitting a wall—gets out of sync. Unsupported game actions may stop recording.

## 3. Timeline, timing, and speed

- **End recording/playback before editing.** Select an action or wait to open its window. **+ Add** inserts after the selection or appends if none is selected. These edits do not send game actions.
- Drag by the left handle; approaching the top/bottom scrolls. Leaving the list, Escape, loss of focus, or leaving mouse mode cancels the drag. Manual scrolling suspends following; **Follow current step** resumes it.
- Edit undo/redo changes only the script, without native Z or loading. History is limited to 50 changes/32MiB for the current project session. Timeline capacity is 65,536 entries.
- Each project stores its interval, initially **250ms**, and default extra wait, initially **1000ms**. `Action A → wait 1000ms → Action B` means **250 + 1000 = 1250ms**. Changing the extra-wait default does not overwrite existing entries. Ending recording discards an unused pending T marker.
- Earlier edits may mark later waits for review and invalidate checkpoints. Deleting a step does not reverse the live game.
- An open project offers Pause/0.25×/1×/4×. Pause retains recording but blocks gameplay input. Speed is not scripted and does not scale real milliseconds. Playback, checkpoint preparation, and trials lock to 1× and stay there afterwards; exit restores the pre-tool speed.

## 4. Wait trials

For `Action A → wait T → Action B`:

1. Select the wait, then **Prepare checkpoint**. The prefix replays from the fixed start and saves **before A executes**.
2. Adjust the wait and select **Run trial**. Every trial restores the checkpoint, sends **A → interval + T → B**, then stops sending. You assess the result.
3. **Return to checkpoint** only loads, without playback. When satisfied, **Apply + review**, then save the project.

Trials require both A and B and no adjacent waits. Edit/delete adjacent waits manually; they are not merged automatically. Closing the window stops its task without rolling back. Confirmed checkpoint cleanup removes only verifiable history, preserving current references and unrecognized material.

## 5. Backup, exit, and recovery

- **Close the game and editor before backup/restore.** In `SaveBackup.exe`, select the `Order of the Sinking Star` save root, not the Steam installation. Backups default to `data/save-backups/`; another drive may be selected. Versions are retained without automatic pruning.
- Restore verifies the backup, backs up the current directory, and requests confirmation before replacing all campaigns and settings/key bindings in that folder. Newer campaigns leave the current folder but remain in the pre-restore backup. Files are not merged. Platform cloud synchronization is outside the tool's control.
- Use **Leave project** or **Exit and unload** normally. If recovery fails, retain the files and follow the panel prompt. Do not force-delete `session.json`, temporary campaigns, or recovery records.
- After an interrupted restore, keep the game closed and use **Finish pending restore**. Emergency restore preserves and retires affected, verifiable local sessions; reopen projects from their fixed starts.
- Foreign-account, foreign-PC, or unverifiable unfinished sessions cannot be automatically recovered/cleaned. Exit them in their original environment first. Recovery drafts do not guarantee every last input survives power loss or forced termination.
- Exit safely before updates and preserve the entire `data/` folder. Project migration is unsupported. On errors, retain files and inspect logs; remove personal information before sharing them.

## 6. Compatibility and locations

Only Windows 10/11 x64 and the following complete game executable SHA256 fingerprints are supported. Unknown builds are rejected. The newer build can natively load copies of older projects; older builds reject newer projects/checkpoints.

```text
0ae10a513dae25286fe93d0db4fa8a2df9a473bc07e1734e12bc1ad30166db1c
d802098b7cb85eadfc733b88d1554042fad950c572e916febea3f669a474a549
```

| Location | Contents |
| --- | --- |
| `data/projects/` | Projects, fixed starts, scripts and checkpoints |
| `data/save-backups/` | Default full-save backups |
| `data/config/` | Language, tool keys and preferences |
| `data/logs/` | Logs and runtime recovery records |

These folders are created beside the program on first use. Move the whole application if the folder is not writable. Do not move EXEs alone or delete required runtime files.

## 7. Troubleshooting

| Symptom | Action |
| --- | --- |
| Cannot click buttons | Press your configured mouse toggle; the default is the grave/tilde key |
| Cannot connect | Start the game and compare its full EXE fingerprint above; do not bypass unknown-build checks |
| Recording/playback rejected | Resolve binding conflicts; replace or delete P steps in Preview |
| Cannot return to the original save | Keep the project, temporary campaign and recovery records. Retry through the panel; do not force-delete files |
| Guide opens as plain text | Read `.md` in a text editor; the launcher uses Notepad if no default association exists |

Preview does not support playback speed control, project migration, direct Queen selection, held/combined inputs or gamepad recording. Other PCs, GPUs, DPI settings and input methods have not been comprehensively validated. Users assess game effects and routes. Report problems with the version, reproduction steps and logs stripped of private information.
