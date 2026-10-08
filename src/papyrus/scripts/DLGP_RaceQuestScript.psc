ScriptName DLGP_RaceQuestScript extends Quest
{Dragon-lands Grand Prix: grid, countdown, checkpoints, lap timer, best lap. Values come from sheets/*.json.}

Actor Property Car Auto                         ; records.car_npc (persistent)
ObjectReference Property GridMarker Auto        ; records.grid_marker at checkpoints.cp00
Form Property EntryPass Auto                    ; records.entry_pass (book)
Message Property GridPrompt Auto                ; records.grid_prompt: 0 = go to the grid, 1 = not now
GlobalVariable Property BestLap Auto            ; records.best_lap_global (seconds, 0 = none)
GlobalVariable Property F1Imported Auto         ; set to 1 by the importer when F1 2021 content is in place
Float[] Property CheckX Auto                    ; checkpoints.pos[0], outbound order
Float[] Property CheckY Auto                    ; checkpoints.pos[1]
Float Property CheckRadius = 600.0 Auto         ; checkpoints.radius_units
Float Property JumpStartPenalty = 5.0 Auto      ; F1 rule: seconds added for moving before lights out
DLGP_CarScript Property CarControl Auto
GlobalVariable Property Diag Auto               ; build --diag: auto-start the race and narrate each step

Int route          ; index into the out-and-back route (0..2N-2)
Int routeLen
Float lapStart
Bool racing = false
Float gridX
Float gridY

Bool announced = false
Bool startRequested = false

Function OfferStart()
	Debug.Trace("DLGP: offering the grid")
	If GridPrompt.Show() == 0
		RequestStart()
	EndIf
EndFunction

Function RequestStart()
	Debug.Trace("DLGP: start requested")
	startRequested = true
	RegisterForSingleUpdate(0.5)
EndFunction

Event OnInit()
	Debug.Trace("DLGP: race quest OnInit")
	Actor player = Game.GetPlayer()
	If player.GetItemCount(EntryPass) == 0
		player.AddItem(EntryPass, 1, true)
	EndIf
	Debug.Trace("DLGP: entry pass given")
	; notifications shown while a save is still loading are dropped, so announce a few seconds later
	RegisterForSingleUpdate(5.0)
EndEvent

Int Function RouteToCheckpoint(Int i)
	; outbound 0..N-1 (N-1 is the turn at Riverwood bridge), then back N-2..0
	Int n = CheckX.Length
	If i < n
		Return i
	EndIf
	Return 2 * (n - 1) - i
EndFunction

Function StartRace()
	Debug.Trace("DLGP: StartRace")
	Actor player = Game.GetPlayer()
	If F1Imported.GetValue() < 1.0
		Debug.MessageBox("F1 2021 was not found on this PC, so there is no car to race.\nInstall F1 2021 from Steam, then press Play in Melty again.")
		Return
	EndIf
	racing = false
	Step("1 moving car to grid")
	Car.MoveTo(GridMarker)
	Step("2 moving player to grid")
	player.MoveTo(GridMarker, 0.0, -250.0, 0.0)
	Utility.Wait(1.0)
	Step("3 mounting car")
	Car.Activate(player)
	Utility.Wait(2.0)
	Step("4 hiding rider")
	player.SetAlpha(0.0)
	routeLen = 2 * CheckX.Length - 1
	route = 1
	Debug.Notification("Dragon-lands Grand Prix - Whiterun to Riverwood and back")
	Utility.Wait(1.5)
	gridX = Car.GetPositionX()
	gridY = Car.GetPositionY()
	Debug.Notification("3")
	Utility.Wait(1.0)
	Debug.Notification("2")
	Utility.Wait(1.0)
	Debug.Notification("1")
	Utility.Wait(1.0)
	Float moved = Distance2D(Car.GetPositionX(), Car.GetPositionY(), gridX, gridY)
	lapStart = Utility.GetCurrentRealTime()
	If moved > 300.0
		lapStart -= JumpStartPenalty
		Debug.Notification("GO! - jump start, +" + JumpStartPenalty as Int + "s")
	Else
		Debug.Notification("GO!")
	EndIf
	racing = true
	CarControl.BeginRun()
	RegisterForSingleUpdate(0.1)
EndFunction

Function Step(String what)
	Debug.Trace("DLGP: step " + what)
	If Diag && Diag.GetValue() > 0.0
		Debug.Notification("diag: " + what)
		Utility.Wait(2.0)
	EndIf
EndFunction

Float Function Distance2D(Float ax, Float ay, Float bx, Float by)
	Float dx = ax - bx
	Float dy = ay - by
	Return Math.Sqrt(dx * dx + dy * dy)
EndFunction

String Function FormatTime(Float t)
	Int m = Math.Floor(t / 60.0)
	Float s = t - m * 60.0
	Int ms = Math.Floor((s - Math.Floor(s)) * 1000.0)
	String ss = Math.Floor(s) as String
	If Math.Floor(s) < 10
		ss = "0" + ss
	EndIf
	String mss = ms as String
	If ms < 10
		mss = "00" + mss
	ElseIf ms < 100
		mss = "0" + mss
	EndIf
	Return m + ":" + ss + "." + mss
EndFunction

Event OnUpdate()
	If !announced
		announced = true
		Debug.Trace("DLGP: announcing")
		Debug.Notification("Dragon-lands Grand Prix: your entry pass is in your inventory (Books).")
		OfferStart()
		Return
	EndIf
	If startRequested
		startRequested = false
		StartRace()
		Return
	EndIf
	If !racing
		Return
	EndIf
	Actor player = Game.GetPlayer()
	If !player.IsOnMount()
		racing = false
		CarControl.EndRun()
		player.SetAlpha(1.0)
		Debug.Notification("Run abandoned - you left the car.")
		Return
	EndIf
	CarControl.Tick()
	Int cp = RouteToCheckpoint(route)
	If Distance2D(player.GetPositionX(), player.GetPositionY(), CheckX[cp], CheckY[cp]) < CheckRadius
		Float t = Utility.GetCurrentRealTime() - lapStart
		If route >= routeLen - 1
			FinishLap(t)
			Return
		EndIf
		If cp == CheckX.Length - 1
			Debug.Notification("Turn at Riverwood bridge  " + FormatTime(t))
		Else
			Debug.Notification("Checkpoint " + route + "/" + (routeLen - 1) + "  " + FormatTime(t))
		EndIf
		route += 1
	EndIf
	RegisterForSingleUpdate(0.1)
EndEvent

Function FinishLap(Float t)
	racing = false
	CarControl.EndRun()
	CarControl.LapDone()
	Float best = BestLap.GetValue()
	If best <= 0.0 || t < best
		BestLap.SetValue(t)
		Debug.MessageBox("Lap: " + FormatTime(t) + "\nNew best lap!")
	Else
		Debug.MessageBox("Lap: " + FormatTime(t) + "\nBest: " + FormatTime(best))
	EndIf
	Game.GetPlayer().SetAlpha(1.0)
	OfferStart()
EndFunction
