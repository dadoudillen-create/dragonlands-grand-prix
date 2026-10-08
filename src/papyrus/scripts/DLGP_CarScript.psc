ScriptName DLGP_CarScript extends Actor
{F1 2021 handling on a Skyrim mount: speed follows the car's real acceleration and coast curves (read from the
player's F1 2021 by the importer into the Accel/Coast globals), scaled by SpeedScale. Engine sound follows speed.}

GlobalVariable[] Property AccelT Auto     ; seconds   (F1 AIAC sample set, resampled to 16 by the importer)
GlobalVariable[] Property AccelV Auto     ; metres/s
GlobalVariable[] Property CoastT Auto     ; seconds   (F1 AICR)
GlobalVariable[] Property CoastV Auto     ; metres/s
GlobalVariable Property SpeedScale Auto   ; cars.speed_scale
GlobalVariable Property GripPerLap Auto   ; tyre wear: grip lost per completed lap (F1 grip levels 1.0 -> 0.6)
Float Property GallopUnitsPerSec = 750.0 Auto   ; horse sprint speed at SpeedMult 100
Sound Property EngineSound Auto

Float throttleT     ; time spent on the acceleration curve
Float lastTick
Float speedMs
Float grip = 1.0
Int engineId = 0

Float Function Interp(GlobalVariable[] xs, GlobalVariable[] ys, Float x)
	Int i = 1
	While i < xs.Length
		If x <= xs[i].GetValue()
			Float x0 = xs[i - 1].GetValue()
			Float x1 = xs[i].GetValue()
			Float y0 = ys[i - 1].GetValue()
			Float y1 = ys[i].GetValue()
			If x1 <= x0
				Return y1
			EndIf
			Return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
		EndIf
		i += 1
	EndWhile
	Return ys[ys.Length - 1].GetValue()
EndFunction

Float Function TimeAtSpeed(GlobalVariable[] ts, GlobalVariable[] vs, Float v)
	; inverse of Interp for a monotonic curve: where on the curve is this speed?
	Int i = 1
	Bool rising = vs[vs.Length - 1].GetValue() > vs[0].GetValue()
	While i < vs.Length
		Float v0 = vs[i - 1].GetValue()
		Float v1 = vs[i].GetValue()
		If (rising && v <= v1) || (!rising && v >= v1)
			If v1 == v0
				Return ts[i].GetValue()
			EndIf
			Return ts[i - 1].GetValue() + (ts[i].GetValue() - ts[i - 1].GetValue()) * (v - v0) / (v1 - v0)
		EndIf
		i += 1
	EndWhile
	Return ts[ts.Length - 1].GetValue()
EndFunction

Function BeginRun()
	throttleT = 0.0
	speedMs = 0.0
	lastTick = Utility.GetCurrentRealTime()
	If EngineSound && engineId == 0
		engineId = EngineSound.Play(Self)
	EndIf
	Apply()
EndFunction

Function EndRun()
	If engineId != 0
		Sound.StopInstance(engineId)
		engineId = 0
	EndIf
	SetActorValue("SpeedMult", 100.0)
	Refresh()
EndFunction

Function LapDone()
	grip -= GripPerLap.GetValue()
	If grip < 0.6
		grip = 0.6
	EndIf
	Debug.Notification("Tyres: grip " + (grip * 100.0) as Int + "%")
EndFunction

Function Tick()
	Float now = Utility.GetCurrentRealTime()
	Float dt = now - lastTick
	lastTick = now
	If IsSprinting()
		; full throttle: move along F1's acceleration curve; worn tyres put the power down more slowly
		throttleT = TimeAtSpeed(AccelT, AccelV, speedMs) + dt * grip
		speedMs = Interp(AccelT, AccelV, throttleT)
	ElseIf IsRunning()
		; part throttle: hold speed
	Else
		; lift: follow F1's coast-down curve
		Float c = TimeAtSpeed(CoastT, CoastV, speedMs) + dt
		speedMs = Interp(CoastT, CoastV, c)
	EndIf
	Apply()
EndFunction

Function Apply()
	Float units = speedMs * SpeedScale.GetValue() / 0.0142875
	Float mult = 100.0 * units / GallopUnitsPerSec
	If mult < 100.0
		mult = 100.0
	EndIf
	SetActorValue("SpeedMult", mult)
	Refresh()
	If engineId != 0
		Float vol = 0.35 + 0.65 * speedMs / 86.0
		If vol > 1.0
			vol = 1.0
		EndIf
		Sound.SetInstanceVolume(engineId, vol)
	EndIf
EndFunction

Function Refresh()
	; Skyrim only re-reads SpeedMult when carry weight changes
	ModActorValue("CarryWeight", 0.1)
	ModActorValue("CarryWeight", -0.1)
EndFunction
