ScriptName DLGP_PassScript extends ObjectReference
{The Dragon-lands Grand Prix entry pass: reading it offers to take you to the grid.}

DLGP_RaceQuestScript Property Race Auto

Event OnRead()
	Race.OfferStart()
EndEvent
