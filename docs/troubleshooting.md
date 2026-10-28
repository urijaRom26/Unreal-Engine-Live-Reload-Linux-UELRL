# Troubleshooting

Log first, always:

```bash
tail -f Saved/Logs/<Project>.log | grep -E "LiveReload|HotReload|error:|Error:"
```

The toolset also returns the compiler output on failure, so run
`ue_live_reload.py` from a terminal before digging into the editor.

## Editor crashes the moment a reload finishes

```
SIGSEGV in TDeferredRegistry<... UPackage ...>::AddRegistration
```

The game module still unloads dynamically. Either the module patch was never
applied, or it was applied and the editor was not rebuilt/restarted since.
Check `Source/<Project>/<Project>.cpp` for `SupportsDynamicReloading()`, then
rebuild (`Result: Succeeded`) and reopen the editor. Crash dumps land in
`Saved/Crashes/`.

## `LiveReload toolset not found - is the LiveReload plugin enabled…`

In order of likelihood:

1. The editor was not restarted after the plugin was built — plugin modules load
   at startup.
2. `LiveReload` is not enabled in the `.uproject`, or `AdditionalPluginDirectories`
   doesn't point at the directory that contains `LiveReload/LiveReload.uplugin`.
   Resolve by re-running `ue_live_reload_setup.py` (it prints the path it wrote).
3. The plugin module failed to compile. Look for `LiveReload` in the build log.
4. You're talking to a different editor instance. The scripts always hit
   `http://127.0.0.1:8000/mcp`; set `UNREAL_MCP_URL` if you changed the port.

Sanity check from the editor side: the log contains
`Mounting Project plugin LiveReload`, and `list_toolsets` shows
`LiveReload.LiveReloadToolset`.

## `Error: no loaded gameplay modules found...`

- Blueprint-only project — there is no game module. This plugin cannot help.
- The project's module didn't load (check the log for
  `Mounting Project modules`).
- You opened an engine sample or a project whose module lives outside
  `<Project>/Binaries`; the filter deliberately only picks modules from your
  project's binaries directory.

## Reload returns `FAILED` with compiler output

That's the design working: structural changes are refused instead of being
half-applied. Common ones:

| message | cause |
|---|---|
| `Formatting string must be a TCHAR array` / `%s expects ANSICHAR* ... got TCHAR*` | `UE_LOG(Log, Display, "%s", ...)` — use `TEXT("...")`, and `*Name.ToString()` for `FName` |
| `undefined reference to ...::StaticClass()` after adding a member | header/reflection change: needs a full build |
| `unreachable code` / `-Wunreachable-code-loop-increment` | the engine builds with `-Werror`; restructure the loop |
| `generated code` / `generated.h` complaints | UHT input changed: full build |

Fix, then:

```bash
rm -f Binaries/Linux/libUnrealEditor-<Project>.so    # only if the editor is open
/opt/unreal-engine/Engine/Build/BatchFiles/Linux/Build.sh <Project>Editor Linux Development \
  -Project="$PWD/<Project>.uproject" -WaitMutex > Saved/build.log 2>&1
grep -E "error:|Result:" Saved/build.log
```

and reopen the editor to activate it.

## `Refused: a PIE session is running`

Stop PIE. The legacy reloader re-instances objects and is not safe while a play
session owns them. The module is not touched by the refusal.

## `Refused: a compile is already in progress`

A reload is still running (or `Module Recompile` is queued in the editor). Wait
for the log to print `Reload/Re-instancing Complete` and retry.

## `Error: the HotReload module is not available in this editor build`

The engine binary lacks `WITH_HOT_RELOAD` (shipping/monolithic build) or
`Engine/Binaries/Linux/libUnrealEditor-HotReload.so` is missing from your engine.
Use a normal modular Development editor build.

## MCP tools disappeared mid-session

An editor restart unregisters the MCP tools for the rest of the client session.
Not a plugin problem — use `scripts/ue_live_reload.py`, which opens its own HTTP
session per call and keeps working.

## `The following modules are missing or built with a different engine version`

The plugin binary was built by a different engine install than the editor
loading it. Rebuild the project with the engine you actually launch, and delete
stale `LiveReload/Binaries/` and `LiveReload/Intermediate/` if you switched
engines.

## Build: `... modifies the values of properties ... has build products in common with UnrealEditor`

`DefaultBuildSettings` is too old for the engine. Set
`DefaultBuildSettings = BuildSettingsVersion.V7;` (5.8) in both target files, or
use `BuildEnvironment = TargetBuildEnvironment.Unique;`.

## Reload works but the new behaviour doesn't appear

- You edited something the reload cannot apply (header, UHT macro, layout) —
  check that the file you changed is a `.cpp` body.
- PIE was started before the reload: stop and start PIE again.
- The changed function isn't reached in the current flow — add a `UE_LOG` marker
  and confirm it fires.

## Editor memory keeps growing

Expected: each reload abandons the previous module image instead of freeing it.
Restart the editor after a long iteration session.
