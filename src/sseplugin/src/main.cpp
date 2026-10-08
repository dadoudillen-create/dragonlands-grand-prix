// Dragon-lands Grand Prix: Skyrim SE plugin, loaded as an .asi by Ultimate ASI Loader (no SKSE needed).
// Startup follows Melty's notes for CommonLibSSE-NG as .asi: DllMain only starts a thread; the thread waits for the
// game's UI singleton, creates its own trampoline (SKSE::Init never runs) and takes "data loaded" from game events.
#include "car.h"

namespace
{
	void SetupLog()
	{
		wchar_t* local = nullptr;
		std::filesystem::path dir;
		if (SUCCEEDED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &local))) {
			dir = std::filesystem::path(local) / "DragonlandsGP";
			CoTaskMemFree(local);
		}
		std::filesystem::create_directories(dir);
		auto sink = std::make_shared<spdlog::sinks::basic_file_sink_mt>((dir / "plugin.log").string(), true);
		auto log = std::make_shared<spdlog::logger>("log", std::move(sink));
		log->flush_on(spdlog::level::info);
		spdlog::set_default_logger(std::move(log));
	}

	struct MenuWatcher : RE::BSTEventSink<RE::MenuOpenCloseEvent>
	{
		bool dataLoaded = false;
		RE::BSEventNotifyControl ProcessEvent(const RE::MenuOpenCloseEvent*, RE::BSTEventSource<RE::MenuOpenCloseEvent>*) override
		{
			if (!dataLoaded && RE::TESForm::LookupByID(0x7)) {
				dataLoaded = true;
				spdlog::info("data loaded");
				dlgp::OnDataLoaded();
			}
			return RE::BSEventNotifyControl::kContinue;
		}
	};

	void Boot()
	{
		SetupLog();
		spdlog::info("Dragon-lands Grand Prix plugin starting");
		{
			const auto& mod = REL::Module::get();
			const auto lib = std::format("Data/SKSE/Plugins/versionlib-{}.bin", mod.version().string());
			spdlog::info("cwd {} | game {} | AE {} | {} exists: {}", std::filesystem::current_path().string(),
				mod.version().string(), REL::Module::IsAE(), lib, std::filesystem::exists(lib));
		}
		RE::UI* ui = nullptr;
		while (!(ui = RE::UI::GetSingleton())) {
			std::this_thread::sleep_for(std::chrono::milliseconds(50));
		}
		SKSE::AllocTrampoline(256);
		static MenuWatcher watcher;
		ui->AddEventSink<RE::MenuOpenCloseEvent>(&watcher);
		dlgp::InstallHooks();
		spdlog::info("hooks installed");
	}
}

BOOL APIENTRY DllMain(HMODULE, DWORD reason, LPVOID)
{
	if (reason == DLL_PROCESS_ATTACH) {
		std::thread(Boot).detach();
	}
	return TRUE;
}
