// Dragon-lands Grand Prix - the F1 2021 car driven in Skyrim SE, every frame.
// Physics data comes from the player's own F1 2021 (written by the importer to Data/SKSE/Plugins/DragonlandsGP/car.json);
// the track comes from sheets/checkpoints.json (shipped as Data/SKSE/Plugins/DragonlandsGP/track.json).
#include "car.h"

#include <nlohmann/json.hpp>

namespace dlgp
{
	namespace
	{
		constexpr float kUnitsPerMetre = 1.0f / 0.0142875f;
		constexpr float kWheelbase = 3.65f;  // metres, from the F1 2021 Ferrari's wheel nodes

		struct Curve
		{
			std::vector<float> x, y;
			float at(float v) const
			{
				if (x.empty()) return 0.0f;
				if (v <= x.front()) return y.front();
				for (std::size_t i = 1; i < x.size(); ++i) {
					if (v <= x[i]) {
						const float t = (v - x[i - 1]) / std::max(1e-6f, x[i] - x[i - 1]);
						return y[i - 1] + t * (y[i] - y[i - 1]);
					}
				}
				return y.back();
			}
		};

		struct CarData
		{
			bool loaded = false;
			std::string name;
			Curve accel;      // speed (m/s) -> acceleration at full throttle (m/s^2)
			Curve brake;      // speed -> deceleration at full brake
			Curve coast;      // speed -> deceleration off throttle
			Curve cornering;  // speed -> max lateral acceleration (m/s^2), fresh tyres (F1 grip 1.0)
			Curve corneringWorn;  // same at F1 grip 0.6
			float topSpeed = 80.0f;
			float speedScale = 0.5f;
			float gripLossPerLap = 0.05f;
			float gripMin = 0.6f;
		} car;

		struct Track
		{
			std::vector<RE::NiPoint3> points;  // outbound order; the lap goes out and back
			float radius = 600.0f;
			RE::NiPoint3 grid;
			float gridHeading = 0.0f;
		} track;

		enum class Phase { Idle, Countdown, Racing, Finished };

		struct State
		{
			Phase phase = Phase::Idle;
			RE::NiPoint3 pos;
			float heading = 0.0f;  // radians, 0 = +Y (north), clockwise
			float speed = 0.0f;    // m/s (real F1 units; scaled to Skyrim on output)
			float grip = 1.0f;
			float timer = 0.0f;
			float countdown = 0.0f;
			int route = 1;
			float best = 0.0f;
			bool prevStartButton = false;
		} st;

		RE::TESObjectREFR* carRef = nullptr;
		std::filesystem::path dataDir = "Data/SKSE/Plugins/DragonlandsGP";

		Curve CurveFrom(const nlohmann::json& j)
		{
			Curve c;
			for (auto& v : j.at("x")) c.x.push_back(v.get<float>());
			for (auto& v : j.at("y")) c.y.push_back(v.get<float>());
			return c;
		}

		void LoadData()
		{
			try {
				auto cj = nlohmann::json::parse(std::ifstream(dataDir / "car.json"));
				car.name = cj.value("name", "F1 2021 car");
				car.accel = CurveFrom(cj.at("accel"));
				car.brake = CurveFrom(cj.at("brake"));
				car.coast = CurveFrom(cj.at("coast"));
				car.cornering = CurveFrom(cj.at("cornering"));
				car.corneringWorn = CurveFrom(cj.at("cornering_worn"));
				car.topSpeed = cj.value("top_speed", 80.0f);
				car.speedScale = cj.value("speed_scale", 0.5f);
				car.gripLossPerLap = cj.value("grip_loss_per_lap", 0.05f);
				car.gripMin = cj.value("grip_min", 0.6f);
				car.loaded = true;
				spdlog::info("car data: {} top {:.1f} m/s, scale {}", car.name, car.topSpeed, car.speedScale);
			} catch (const std::exception& e) {
				spdlog::warn("no F1 car data ({}): F1 2021 not imported", e.what());
			}
			try {
				auto tj = nlohmann::json::parse(std::ifstream(dataDir / "track.json"));
				for (auto& p : tj.at("points")) track.points.emplace_back(p[0].get<float>(), p[1].get<float>(), p[2].get<float>());
				track.radius = tj.value("radius", 600.0f);
				track.grid = track.points.front();
				track.gridHeading = tj.value("grid_heading", 0.0f);
				spdlog::info("track: {} checkpoints", track.points.size());
			} catch (const std::exception& e) {
				spdlog::error("track.json: {}", e.what());
			}
		}

		struct Input
		{
			float throttle = 0, brake = 0, steer = 0;
			bool start = false;
		};

		Input ReadInput()
		{
			Input in;
			XINPUT_STATE xs{};
			if (XInputGetState(0, &xs) == ERROR_SUCCESS) {
				in.throttle = xs.Gamepad.bRightTrigger / 255.0f;
				in.brake = xs.Gamepad.bLeftTrigger / 255.0f;
				const float lx = xs.Gamepad.sThumbLX / 32767.0f;
				in.steer = std::abs(lx) < 0.12f ? 0.0f : lx;
				in.start = (xs.Gamepad.wButtons & XINPUT_GAMEPAD_BACK) != 0;
			}
			if (GetForegroundWindow() == reinterpret_cast<HWND>(RE::Main::GetSingleton()->wnd)) {
				auto down = [](int vk) { return (GetAsyncKeyState(vk) & 0x8000) != 0; };
				if (down('W')) in.throttle = 1.0f;
				if (down('S')) in.brake = 1.0f;
				if (down('A')) in.steer = -1.0f;
				if (down('D')) in.steer = 1.0f;
				if (down(VK_F8)) in.start = true;
			}
			return in;
		}

		float GroundZ(float x, float y, float fallback)
		{
			float z = fallback;
			if (auto tes = RE::TES::GetSingleton()) {
				RE::NiPoint3 p{ x, y, fallback + 2000.0f };
				if (tes->GetLandHeight(p, z)) return z;
			}
			return fallback;
		}

		// HUD message (top left). CommonLibVR ng dropped RE::DebugNotification; Address Library IDs from
		// CommonLibSSE-NG's Offsets.h (MIT): SE 52050, AE 52933.
		void Notify(const std::string& s)
		{
			using func_t = void(const char*, const char*, bool);
			static REL::Relocation<func_t*> func{ REL::RelocationID(52050, 52933) };
			func(s.c_str(), nullptr, true);
		}

		std::string Fmt(float t)
		{
			const int m = static_cast<int>(t / 60.0f);
			return std::format("{}:{:06.3f}", m, t - m * 60.0f);
		}

		void PlaceCar()
		{
			if (!carRef) return;
			const float sx = std::sin(st.heading), cy = std::cos(st.heading);
			// pitch/roll from the ground under the wheels so the car sits on slopes
			const float half = kWheelbase * 0.5f * kUnitsPerMetre;
			const float zf = GroundZ(st.pos.x + sx * half, st.pos.y + cy * half, st.pos.z);
			const float zr = GroundZ(st.pos.x - sx * half, st.pos.y - cy * half, st.pos.z);
			const float zl = GroundZ(st.pos.x - cy * 70.0f, st.pos.y + sx * 70.0f, st.pos.z);
			const float zR = GroundZ(st.pos.x + cy * 70.0f, st.pos.y - sx * 70.0f, st.pos.z);
			st.pos.z = (zf + zr) * 0.5f;
			const float pitch = -std::atan2(zf - zr, 2.0f * half);
			const float roll = std::atan2(zR - zl, 140.0f);
			carRef->SetPosition(st.pos);
			carRef->SetAngle(RE::NiPoint3{ pitch, roll, st.heading });
		}

		void HidePlayerInCar(RE::PlayerCharacter* player, bool hide)
		{
			if (auto root = player->Get3D()) root->SetAppCulled(hide);
			if (auto cm = RE::ControlMap::GetSingleton()) {
				cm->ToggleControls(RE::ControlMap::UEFlag::kMovement, !hide, false);
				cm->ToggleControls(RE::ControlMap::UEFlag::kActivate, !hide, false);
			}
		}

		void StartRun(RE::PlayerCharacter* player)
		{
			if (!car.loaded) {
				RE::DebugMessageBox("F1 2021 was not found on this PC, so there is no car to race.\n"
				                    "Install F1 2021 from Steam, then press Play in Melty again.");
				return;
			}
			if (!carRef || track.points.empty()) return;
			st = State{ .best = st.best };
			st.phase = Phase::Countdown;
			st.countdown = 4.0f;
			st.pos = track.grid;
			st.heading = track.gridHeading;
			player->MoveTo(carRef);
			HidePlayerInCar(player, true);
			Notify("Dragon-lands Grand Prix - Whiterun to Riverwood and back");
			spdlog::info("run started");
		}

		void Step(RE::PlayerCharacter* player, float dt)
		{
			if (dt <= 0.0f || dt > 0.25f) return;
			const Input in = ReadInput();
			if (in.start && !st.prevStartButton && player->GetParentCell() && player->GetParentCell()->IsExteriorCell()) {
				StartRun(player);
			}
			st.prevStartButton = in.start;
			if (st.phase == Phase::Idle || st.phase == Phase::Finished) return;

			if (st.phase == Phase::Countdown) {
				const int before = static_cast<int>(std::ceil(st.countdown - 1.0f));
				st.countdown -= dt;
				const int after = static_cast<int>(std::ceil(st.countdown - 1.0f));
				if (after != before && after >= 1 && after <= 3) Notify(std::to_string(after));
				if (st.countdown <= 1.0f) {
					st.phase = Phase::Racing;
					Notify("GO!");
				}
				PlaceCar();
				return;
			}

			// longitudinal: F1 2021 Ferrari curves (m/s^2 at the current speed), grip limits traction
			float a = -car.coast.at(st.speed);
			if (in.throttle > 0.0f) a = car.accel.at(st.speed) * in.throttle * (0.75f + 0.25f * st.grip);
			if (in.brake > 0.0f) a = -car.brake.at(st.speed) * in.brake * (0.6f + 0.4f * st.grip);
			st.speed = std::clamp(st.speed + a * dt, 0.0f, car.topSpeed);

			// lateral: bicycle model, yaw rate capped by F1 cornering grip (v^2 / r <= aLat)
			const float steerAngle = in.steer * 0.35f / (1.0f + st.speed / 30.0f);
			float yawRate = st.speed * std::tan(steerAngle) / kWheelbase;
			const float wear = std::clamp((st.grip - 0.6f) / 0.4f, 0.0f, 1.0f);   // 1 = fresh, 0 = F1 grip 0.6
			const float aLatMax = car.corneringWorn.at(st.speed) + wear * (car.cornering.at(st.speed) - car.corneringWorn.at(st.speed));
			if (st.speed > 1.0f) yawRate = std::clamp(yawRate, -aLatMax / st.speed, aLatMax / st.speed);
			st.heading += yawRate * dt;

			const float d = st.speed * car.speedScale * kUnitsPerMetre * dt;
			st.pos.x += std::sin(st.heading) * d;
			st.pos.y += std::cos(st.heading) * d;
			PlaceCar();
			player->SetPosition(RE::NiPoint3{ st.pos.x, st.pos.y, st.pos.z + 10.0f }, true);
			player->SetAngle(RE::NiPoint3{ 0.0f, 0.0f, st.heading });

			// checkpoints: out to the turn, back to the line
			st.timer += dt;
			const int n = static_cast<int>(track.points.size());
			const int routeLen = 2 * n - 1;
			const int cp = st.route < n ? st.route : 2 * (n - 1) - st.route;
			const auto& target = track.points[cp];
			if (std::hypot(st.pos.x - target.x, st.pos.y - target.y) < track.radius) {
				if (st.route >= routeLen - 1) {
					st.phase = Phase::Finished;
					const bool pb = st.best <= 0.0f || st.timer < st.best;
					if (pb) st.best = st.timer;
					st.grip = std::max(car.gripMin, st.grip - car.gripLossPerLap);
					HidePlayerInCar(player, false);
					RE::DebugMessageBox(std::format("Lap: {}\n{}\nPress View/Back (or F8) to race again.", Fmt(st.timer),
						pb ? "New best lap!" : "Best: " + Fmt(st.best)).c_str());
					spdlog::info("lap {:.3f}s best {:.3f}s", st.timer, st.best);
					return;
				}
				Notify(cp == n - 1 ? "Turn at Riverwood bridge  " + Fmt(st.timer)
				                   : std::format("Checkpoint {}/{}  {}", st.route, routeLen - 1, Fmt(st.timer)));
				++st.route;
			}
		}

		struct PlayerUpdate
		{
			static void thunk(RE::PlayerCharacter* a_this, float a_delta)
			{
				func(a_this, a_delta);
				Step(a_this, a_delta);
			}
			static inline REL::Relocation<decltype(thunk)> func;
		};
	}

	void InstallHooks()
	{
		REL::Relocation<std::uintptr_t> vtbl{ RE::VTABLE_PlayerCharacter[0] };
		PlayerUpdate::func = vtbl.write_vfunc(0xAD, PlayerUpdate::thunk);
	}

	void OnDataLoaded()
	{
		spdlog::info("game version {}", REL::Module::get().version().string());
		LoadData();
		if (auto dh = RE::TESDataHandler::GetSingleton()) {
			carRef = dh->LookupForm<RE::TESObjectREFR>(0x801, "DragonlandsGP.esp");
			spdlog::info("car reference {}", carRef ? "found" : "MISSING (DragonlandsGP.esp not loaded?)");
		}
	}
}
