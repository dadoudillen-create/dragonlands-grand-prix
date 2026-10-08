ScriptName ObjectReference extends Form Hidden
Bool Function Activate(ObjectReference akActivator, Bool abDefaultProcessingOnly = false) native
Function Disable(Bool abFadeOut = false) native
Function Enable(Bool abFadeIn = false) native
Float Function GetDistance(ObjectReference akOther) native
Float Function GetPositionX() native
Float Function GetPositionY() native
Float Function GetPositionZ() native
Float Function GetAngleZ() native
Bool Function Is3DLoaded() native
Function MoveTo(ObjectReference akTarget, Float afXOffset = 0.0, Float afYOffset = 0.0, Float afZOffset = 0.0, Bool abMatchRotation = true) native
ObjectReference Function PlaceAtMe(Form akFormToPlace, Int aiCount = 1, Bool abForcePersist = false, Bool abInitiallyDisabled = false) native
Function SetAngle(Float afXAngle, Float afYAngle, Float afZAngle) native
Event OnActivate(ObjectReference akActionRef)
EndEvent
Function SetPosition(Float afX, Float afY, Float afZ) native
Function AddItem(Form akItemToAdd, Int aiCount = 1, Bool abSilent = false) native
Int Function GetItemCount(Form akItem) native
Event OnRead()
EndEvent
