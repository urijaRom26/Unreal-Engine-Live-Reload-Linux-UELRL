#include "LiveReloadToolset.h"

#include "Editor.h"
#include "Misc/HotReloadInterface.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogLiveReload, Log, All);

namespace
{
	class FTeeOutputDevice : public FOutputDevice
	{
	public:
		FTeeOutputDevice(FOutputDevice& InPrimary, FString& InCapture)
			: Primary(InPrimary)
			, Capture(InCapture)
		{
		}

		virtual void Serialize(const TCHAR* Message, ELogVerbosity::Type Verbosity, const FName& Category) override
		{
			Primary.Serialize(Message, Verbosity, Category);
			Capture += Message;
			Capture += TEXT("\n");
		}

	private:
		FOutputDevice& Primary;
		FString& Capture;
	};

	TArray<FModuleStatus> FindLoadedGameModules()
	{
		const FString ProjectBinaries = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir() / TEXT("Binaries"));

		TArray<FModuleStatus> Found;
		TArray<FModuleStatus> AllModules;
		FModuleManager::Get().QueryModules(AllModules);
		for (FModuleStatus& Status : AllModules)
		{
			const bool bInProject = Status.FilePath.StartsWith(ProjectBinaries);
			if (Status.bIsLoaded && Status.bIsGameModule && bInProject)
			{
				Found.Add(MoveTemp(Status));
			}
		}
		Found.Sort([](const FModuleStatus& A, const FModuleStatus& B) { return A.Name < B.Name; });
		return Found;
	}

	IHotReloadInterface* GetHotReloadInterface()
	{
		IHotReloadInterface* HotReload = IHotReloadInterface::GetPtr();
		if (!HotReload)
		{
			HotReload = FModuleManager::Get().LoadModulePtr<IHotReloadInterface>(TEXT("HotReload"));
		}
		return HotReload;
	}

	bool IsPIERunning()
	{
		return GEditor && GEditor->IsPlaySessionInProgress();
	}
}

FString ULiveReloadToolset::ReloadGameCode()
{
	if (IsPIERunning())
	{
		return TEXT("Refused: a PIE session is running. Stop PIE, reload, then play again.");
	}

	IHotReloadInterface* HotReload = GetHotReloadInterface();
	if (!HotReload)
	{
		return TEXT("Error: the HotReload module is not available in this editor build.");
	}
	if (HotReload->IsCurrentlyCompiling())
	{
		return TEXT("Refused: a compile is already in progress.");
	}

	const TArray<FModuleStatus> Modules = FindLoadedGameModules();
	if (Modules.IsEmpty())
	{
		return TEXT("Error: no loaded gameplay modules found in the project's Binaries directory.");
	}

	FString Report;
	for (const FModuleStatus& Module : Modules)
	{
		FString CompilerOutput;
		FTeeOutputDevice Tee(*GLog, CompilerOutput);

		const double StartSeconds = FPlatformTime::Seconds();
		const bool bSucceeded = HotReload->RecompileModule(
			FName(*Module.Name),
			Tee,
			ERecompileModuleFlags::ReloadAfterRecompile | ERecompileModuleFlags::FailIfGeneratedCodeChanges);
		const double ElapsedSeconds = FPlatformTime::Seconds() - StartSeconds;

		UE_LOG(LogLiveReload, Display, TEXT("%s: %s in %.1f s"),
			*Module.Name, bSucceeded ? TEXT("reloaded") : TEXT("FAILED"), ElapsedSeconds);

		Report += FString::Printf(TEXT("%s: %s in %.1f s\n"),
			*Module.Name, bSucceeded ? TEXT("reloaded") : TEXT("FAILED"), ElapsedSeconds);

		if (!bSucceeded)
		{
			const int32 MaxTail = 4000;
			if (CompilerOutput.Len() > MaxTail)
			{
				CompilerOutput.RightInline(MaxTail);
				CompilerOutput = TEXT("...\n") + CompilerOutput;
			}
			Report += TEXT("--- compiler output ---\n") + CompilerOutput;
			Report += TEXT("If the change touched a header, UCLASS/USTRUCT/UFUNCTION/UPROPERTY or a class layout, close the editor and do a full build.\n");
		}
	}
	return Report;
}

FString ULiveReloadToolset::GetLiveReloadStatus()
{
	const TArray<FModuleStatus> Modules = FindLoadedGameModules();

	FString ModuleList;
	for (const FModuleStatus& Module : Modules)
	{
		ModuleList += FString::Printf(TEXT("\n  %s (%s)"), *Module.Name, *Module.FilePath);
	}
	if (ModuleList.IsEmpty())
	{
		ModuleList = TEXT(" (none)");
	}

	return FString::Printf(
		TEXT("PIE running: %s\nHotReload module: %s\nLoaded gameplay modules:%s"),
		IsPIERunning() ? TEXT("yes") : TEXT("no"),
		GetHotReloadInterface() ? TEXT("available") : TEXT("missing"),
		*ModuleList);
}
