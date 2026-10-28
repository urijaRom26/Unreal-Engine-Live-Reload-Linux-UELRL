# How it works

Engine paths below are relative to the engine root (e.g. `/opt/unreal-engine`).

## 1. No Live Coding on Linux

`Engine/Source/Programs/UnrealBuildTool/Configuration/TargetRules.cs` enables
Live Coding only for Win64 targets — the single place it is switched on is gated
by the target platform, and no Linux path exists.

The implementation is Windows-only as well —
`Engine/Source/Developer/Windows/LiveCoding/` is the single implementation of
`ILiveCodingModule`. On Linux there is no Live Coding binary at all, so the
`Ctrl+Alt+F11` workflow and the editor's "Live Coding" toolbar simply don't
exist.

## 2. What Linux does ship: the legacy reloader

Modular Development editor builds define `WITH_HOT_RELOAD` (see
`Engine/Source/Runtime/Core/Public/Misc/Build.h`) and ship
`Engine/Binaries/Linux/libUnrealEditor-HotReload.so`. It implements
`IHotReloadInterface` (`Engine/Source/Developer/HotReload/Public/Misc/HotReloadInterface.h`)
and is what the `Module Recompile <Module>` console command calls.

For a given module it:

1. runs UnrealBuildTool against the project with `-ModuleWithSuffix=<Module>,<n>`,
2. loads the newly linked `<Module>-<n>.so` (the running editor keeps the
   original file open),
3. re-instances UObjects whose class lives in that module and recompiles
   dependent Blueprints,
4. reports `Reload/Re-instancing Complete: N packages changed, ...`.

That is already the loop we want. It is *not* Live Coding: no incremental
patching, no function-level swapping — it is a full recompile and link of the
module, just done in-process.

## 3. Why it segfaults out of the box

The reload only works if the old module image stays mapped. By default the game
module inherits `FDefaultGameModuleImpl`, whose `SupportsDynamicReloading()`
returns `true`, so `FModuleManager` unloads the old module: it calls
`FreeDllHandle`, which is `dlclose` on Linux
(`Engine/Source/Runtime/Core/Private/Modules/ModuleManager.cpp`).

CoreUObject keeps **deferred registration records** for reflected types, and
those records hold raw pointers into the module's static storage — the memory
that `dlclose` just unmapped
(`Engine/Source/Runtime/CoreUObject/Private/UObject/DeferredRegistry.h`). When
the new module runs its static initialisation it walks those records and
dereferences freed pages:

```
SIGSEGV in TDeferredRegistry<... UPackage ...>::AddRegistration
```

This is a genuine engine bug on Linux; it is not caused by the plugin.

## 4. Why the module patch fixes it

```cpp
class FMyGameModule : public FDefaultGameModuleImpl
{
public:
    virtual bool SupportsDynamicReloading() override { return false; }
};
IMPLEMENT_PRIMARY_GAME_MODULE(FMyGameModule, MyGame, "MyGame");
```

With `false`, `FModuleManager` refuses to unload and instead **abandons** the
module:

```
Module being reloaded does not support dynamic unloading -- abandoning existing
loaded module so that we can load the recompiled version!
```

The old image is never freed, so every registration record stays valid, and the
new module can be loaded alongside it. `FDefaultGameModuleImpl` already sets
`IsGameModule() == true`, which is how the plugin finds gameplay modules
afterwards.

Cost: the abandoned image stays resident. A small gameplay module is a few
hundred KB per reload; a very large one is a few MB. Restart the editor after a
long session.

## 5. The plugin

`LiveReload/Source/LiveReload/` is one editor module.

`LiveReloadToolset.cpp`:

- `FindLoadedGameModules()` — `FModuleManager::QueryModules()`, keep entries with
  `bIsLoaded && bIsGameModule` whose `FilePath` is under the project's
  `Binaries/`. Engine game modules and plugins are excluded, so only your code
  is recompiled.
- `GetHotReloadInterface()` — `IHotReloadInterface::GetPtr()`, falling back to
  `FModuleManager::LoadModulePtr<IHotReloadInterface>(TEXT("HotReload"))`.
- `FTeeOutputDevice` — mirrors the compiler output to `GLog` (so it lands in the
  editor log) while capturing it for the tool's return value.
- `ReloadGameCode()` — for each module:

  ```cpp
  HotReload->RecompileModule(
      FName(*Module.Name),
      Tee,
      ERecompileModuleFlags::ReloadAfterRecompile
    | ERecompileModuleFlags::FailIfGeneratedCodeChanges);
  ```

  `ReloadAfterRecompile` is the "swap it in" flag. `FailIfGeneratedCodeChanges`
  makes the reload refuse when the change would have altered generated code
  (headers, UHT macros, layouts) instead of half-applying it — those cases need
  a real rebuild anyway. On failure the last 4000 characters of compiler output
  are returned.
- Guards: refuses while `GEditor->IsPlaySessionInProgress()` (the reloader is not
  safe mid-PIE) and while `IHotReloadInterface::IsCurrentlyCompiling()`.
- Errors are returned as text, never as crashes; the toolset returns a string so
  an agent or script can read compiler diagnostics.

`LiveReloadModule.cpp` registers the toolset class. This is not optional:
`UToolsetDefinition` subclasses are **not** auto-discovered — a plugin that only
mounts shows up in `list_toolsets` as nothing. The module defers registration to
`FCoreDelegates::OnAllModuleLoadingPhasesComplete` (module loading phases must
finish before the registry is touched from a `PostEngineInit` module) and
unregisters on `FCoreDelegates::OnPreExit`.

## 6. How one plugin serves every project

`MyGame.uproject`:

```json
"AdditionalPluginDirectories": ["../_Shared"]
```

Read by `ProjectDescriptor::AdditionalPluginDirectories`
(`Engine/Source/Runtime/Projects/`) and by UnrealBuildTool
(`Configuration/Descriptors/ProjectDescriptor.cs`), which adds the directory to
the plugin search roots, so `../_Shared/LiveReload/LiveReload.uplugin` is a
normal project-visible plugin. No symlinks, no engine install, no sudo, and
plugins built there are shared by every project using that engine build.

## 7. Building while the editor is open

The editor maps `Binaries/Linux/libUnrealEditor-<Module>.so` with `MAP_PRIVATE`.
Overwriting those bytes in place gives a process a mix of old and new pages —
undefined behaviour, usually a crash.

`rm -f` the file first: the kernel keeps the old inode alive for the running
process, and UBT links a brand-new file. The editor keeps executing the old
code until it restarts, which is exactly the semantics you want: a structural
build can run any time, and the restart is what activates it.

## 8. Version notes

- Tested on UE **5.8.4** Linux x64 installed build. The legacy reloader and
  `IHotReloadInterface` have existed for many versions, so the module patch and
  `Module Recompile` should work well before 5.8; the MCP toolset half needs an
  engine that ships the experimental **Toolset Registry** plugin (5.8 does).
- Shipping/monolithic builds don't define `WITH_HOT_RELOAD`; the toolset then
  reports `HotReload module: missing`, as expected.
