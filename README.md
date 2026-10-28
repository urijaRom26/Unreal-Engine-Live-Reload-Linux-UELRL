# UELRL — Unreal Engine Live Reload (Linux)

Live C++ iteration for Unreal Engine 5 on Linux: edit a function body, press
one button (or run one command), and the running editor executes the new code
**in about 5 seconds** — no editor restart, no re-opened project, no lost PIE
session, and the editor's automation/MCP connection stays alive.

Unreal's built-in **Live Coding does not exist on Linux** (`bWithLiveCoding` is
gated to Win64 in `TargetRules.cs`), and the legacy `Module Recompile` path
crashes the editor out of the box on Linux. This project turns that legacy path
into something usable.

Tested on **UE 5.8.4, Linux x64, installed (binary) build**, clang 20 toolchain
bundled with the engine.

| action | measured |
|---|---|
| apply a `.cpp` body edit | **2.8 – 5.2 s** |
| editor stays up | yes (PIE and MCP untouched) |
| plugin build, one time | ~3.5 s |
| full editor restart (the alternative) | ~40 – 60 s + project load |

## What it is

Two parts, both in this repo:

1. **`LiveReload/`** — an editor-only plugin. It exposes an MCP toolset
   (`LiveReload.LiveReloadToolset`) with `ReloadGameCode` (recompile + swap the
   project's gameplay modules) and `GetLiveReloadStatus`. It drives the engine's
   own `IHotReloadInterface::RecompileModule`, so it works with or without the
   editor UI.
2. **`scripts/`** — a two-script CLI: one installs the plugin into a project
   idempotently, the other triggers a reload over HTTP (so you don't need any
   MCP client integration to use it).

Plus a one-line patch to your game module that makes the reload safe — that is
the part everyone misses, and the reason the built-in command segfaults.

## Requirements

- Linux x64, Unreal Engine **5.x** with a **modular Development editor**
  (installed builds are fine — `Engine/Binaries/Linux/libUnrealEditor-HotReload.so`
  must exist).
- A **C++** game project (Blueprint-only projects have no game module to reload).
- The **MCP path** (toolset + `ue_live_reload.py`) additionally needs the
  engine's *Unreal MCP* plugin with its server running, and an engine that ships
  the *Toolset Registry* plugin (5.8 does). Without MCP you can still use the
  console command `Module Recompile <Module>` after applying the module patch.
- Python 3 for the scripts (standard library only).

## Install

### 1. Get the repo

    git clone https://github.com/<you>/<repo>.git "$HOME/Documents/Unreal Projects/_Shared"

The repo directory doubles as the **shared plugin root**: `_Shared/LiveReload/`
is the plugin, and every project points at it with one JSON line — no copying,
no symlinks, no engine changes, no sudo.

### 2. Add it to a project

    python3 "$HOME/Documents/Unreal Projects/_Shared/scripts/ue_live_reload_setup.py" \
        "$HOME/Documents/Unreal Projects/MyGame"

The script is idempotent and prints what it changed. `--dry-run` first if you
like. It:

- adds `"AdditionalPluginDirectories": ["../_Shared"]` to `MyGame.uproject`
  (an engine + UBT feature: extra plugin search roots)
- enables the `LiveReload` plugin in the same file
- rewrites `Source/MyGame/MyGame.cpp` so the primary game module reports
  `SupportsDynamicReloading() == false`

Want the plugin inside the project instead of shared? Use `--local`; it copies
the plugin to `MyGame/Plugins/LiveReload` and skips the extra plugin directory.

Engine not at `/opt/unreal-engine`? Add `--engine /path/to/UE` or set `UE_ROOT`.

### 3. Build once

The plugin module has to be compiled for the project's target:

```bash
cd "$HOME/Documents/Unreal Projects/MyGame"
/opt/unreal-engine/Engine/Build/BatchFiles/Linux/Build.sh \
  MyGameEditor Linux Development -Project="$PWD/MyGame.uproject" -WaitMutex > Saved/build.log 2>&1
grep -E "error:|Result:" Saved/build.log        # want: Result: Succeeded
```

If the editor is open on this project, `rm -f Binaries/Linux/libUnrealEditor-MyGame.so`
before the build so UBT writes a fresh inode instead of overwriting a mapped
file. The editor keeps running the old code; it picks up the new code when you
reopen it.

### 4. Verify

Open the project, then:

    python3 "$HOME/Documents/Unreal Projects/_Shared/scripts/ue_live_reload.py" --status

```
PIE running: no
HotReload module: available
Loaded gameplay modules:
  MyGame (/…/MyGame/Binaries/Linux/libUnrealEditor-MyGame.so)
```

## Use

**Loop:** stop PIE → edit a `.cpp` function body → reload → play.

```bash
# recompile + swap into the running editor
python3 ~/Documents/Unreal\ Projects/_Shared/scripts/ue_live_reload.py

# what does it see?
python3 ~/Documents/Unreal\ Projects/_Shared/scripts/ue_live_reload.py --status
```

Over MCP (from an agent, or `curl`-style tooling):

```json
call_tool(toolset_name="LiveReload.LiveReloadToolset", tool_name="ReloadGameCode", arguments={})
```

Without any of that, the editor console still works once the module patch is in:

```
Module Recompile MyGame
```

Set `UNREAL_MCP_URL` if the MCP server is not on `http://127.0.0.1:8000/mcp`.

## What is live, what is not

| change | live? |
|---|---|
| function body in an existing `.cpp` | **yes** |
| new locals, constants, lambdas, static helpers used inside a body | **yes** |
| `UE_LOG` additions, tuning values in a body | **yes** |
| function signature / return type / parameters | no |
| header edit, new or changed class members, layout | no |
| `UCLASS` / `USTRUCT` / `UENUM` / `UFUNCTION` / `UPROPERTY` | no |
| new class, new module, new plugin | no |

Structural changes are refused cleanly (`FailIfGeneratedCodeChanges`) instead of
being half-applied — the running editor is left untouched. For those: unlink the
module binary if the editor is open, run the build from step 3, then reopen the
editor. The cost is the restart, not the build.

## Verified behaviour (UE 5.8.4, Linux x64)

- Body edit applied in **4.4 s**, reverted in **5.2 s**, another project
  **2.8 s** — editor process alive the whole time.
- Log proof per reload:

  ```
  LogHotReload: Recompiling module MyGame...
  Module being reloaded does not support dynamic unloading -- abandoning existing loaded module ...
  Display: Reload/Re-instancing Complete: 1 package changed, 6 classes unchanged, 7 functions remapped
  ```

- Behaviour proof: a marker `UE_LOG` added to a function body fired in PIE with
  the new text, and a `FString::Printf` change showed up on screen without a
  restart; reverting the body and reloading removed the marker again.
- Guard works: reloading while PIE runs returns
  `Refused: a PIE session is running. Stop PIE, reload, then play again.` and the
  module is not touched.
- Two projects on the same engine coexist through the shared plugin directory.

## Troubleshooting

See [`docs/troubleshooting.md`](docs/troubleshooting.md). The three classics:

- **Editor segfaults on the first reload** (`TDeferredRegistry<...UPackage...>::AddRegistration`) —
  the module patch is missing. Run the setup script again and rebuild.
- **`LiveReload toolset not found`** — the plugin module isn't loaded (not
  enabled, not built, or the editor wasn't restarted after the build).
- **Reload says FAILED** — the change was structural. Read the compiler tail it
  prints; a header/UHT change needs a full build.

## How it works

[`docs/how-it-works.md`](docs/how-it-works.md) explains the crash, the
abandon-instead-of-unload trick, the UBT invocation, and why the toolset has to
register itself explicitly.

## Limitations

- Each reload leaves the previous module image mapped (that is what makes it
  safe). Editor RSS grows by the module size per reload — restart after a long
  session.
- Linux x64 only. Windows has Live Coding, macOS has its own path.
- Only the primary game module by default; additional gameplay modules in the
  project's `Binaries/` are picked up automatically.
- PIE must be stopped; live-reloading into a running game session isn't
  supported by the underlying reloader.
- Packaging/cooking is unaffected — the plugin is `EditorOnly`.

## Repo layout

```
LiveReload/                     editor-only plugin (uplugin + one module)
  Source/LiveReload/Public/LiveReloadToolset.h        UToolsetDefinition
  Source/LiveReload/Private/LiveReloadToolset.cpp     recompile + swap
  Source/LiveReload/Private/LiveReloadModule.cpp      registers the toolset
scripts/ue_live_reload_setup.py install into a project (idempotent)
scripts/ue_live_reload.py       trigger / status over the MCP HTTP endpoint
docs/how-it-works.md
docs/troubleshooting.md
```

## License

MIT — see [LICENSE](LICENSE).
