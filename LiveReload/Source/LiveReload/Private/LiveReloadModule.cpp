#include "LiveReloadToolset.h"

#include "Misc/CoreDelegates.h"
#include "Modules/ModuleManager.h"
#include "ToolsetRegistry/UToolsetRegistry.h"

class FLiveReloadModule : public FDefaultModuleImpl
{
public:
	virtual void StartupModule() override
	{
		FCoreDelegates::OnAllModuleLoadingPhasesComplete.AddRaw(this, &FLiveReloadModule::RegisterToolsets);
		FCoreDelegates::OnPreExit.AddRaw(this, &FLiveReloadModule::UnregisterToolsets);
	}

	virtual void ShutdownModule() override
	{
		FCoreDelegates::OnAllModuleLoadingPhasesComplete.RemoveAll(this);
		FCoreDelegates::OnPreExit.RemoveAll(this);
	}

private:
	void RegisterToolsets()
	{
		UToolsetRegistry::RegisterToolsetClass(ULiveReloadToolset::StaticClass());
	}

	void UnregisterToolsets()
	{
		UToolsetRegistry::UnregisterToolsetClass(ULiveReloadToolset::StaticClass());
	}
};

IMPLEMENT_MODULE(FLiveReloadModule, LiveReload);
