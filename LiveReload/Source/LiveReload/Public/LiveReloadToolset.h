#pragma once

#include "ToolsetRegistry/ToolsetDefinition.h"

#include "LiveReloadToolset.generated.h"

/**
 * Recompiles the project's gameplay modules and swaps them into the running
 * editor. On Linux the HotReload module normally dlcloses the old module,
 * which leaves its reflected-class registration records dangling and crashes
 * in the new module's static initialisation. Game modules that report
 * SupportsDynamicReloading() == false are abandoned instead of unloaded, which
 * keeps those records valid.
 */
UCLASS(MinimalAPI)
class ULiveReloadToolset : public UToolsetDefinition
{
	GENERATED_BODY()

public:

	/**
	 * Recompiles every loaded gameplay module and hot-reloads it into the running editor.
	 * Refuses while PIE is running. Only function-body changes are applied: Unreal
	 * Header Tool, class-layout and new-class changes are rejected by the compile.
	 * @return Per-module status with timings, plus compiler diagnostics on failure.
	 */
	UFUNCTION(meta = (AICallable), Category = "LiveReload")
	static LIVERELOAD_API FString ReloadGameCode();

	/**
	 * Reports whether PIE is running, which gameplay modules are loaded, and whether
	 * the HotReload module is available.
	 * @return Human-readable status summary.
	 */
	UFUNCTION(meta = (AICallable), Category = "LiveReload")
	static LIVERELOAD_API FString GetLiveReloadStatus();
};
