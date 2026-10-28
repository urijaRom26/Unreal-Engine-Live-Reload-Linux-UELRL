using UnrealBuildTool;

public class LiveReload : ModuleRules
{
	public LiveReload(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "ToolsetRegistry" });
		PrivateDependencyModuleNames.AddRange(new string[] { "Engine", "UnrealEd" });
	}
}
