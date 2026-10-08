ScriptName Actor extends ObjectReference Hidden
Bool Function AddSpell(Spell akSpell, Bool abVerbose = true) native
Float Function GetActorValue(String asValueName) native
Bool Function IsOnMount() native
Bool Function IsSprinting() native
Function ModActorValue(String asValueName, Float afAmount) native
Function SetActorValue(String asValueName, Float afValue) native
Function SetAlpha(Float afTargetAlpha, Bool abFade = false) native
Bool Function HasSpell(Form akForm) native
Bool Function IsRunning() native
Function EquipSpell(Spell akSpell, Int aiSource) native
