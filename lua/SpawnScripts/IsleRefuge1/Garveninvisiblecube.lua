--[[
    Script Name    : SpawnScripts/IsleRefuge1/Garveninvisiblecube.lua
    Script Author  : Dorbin (upstream); modified for friends-only server
    Script Date    : 2022.09.09 06:09:23
    Script Purpose :
        - Offer the Isle of Refuge tutorial quest (5725) on player approach.

    Server override: removed the SummonItem(Spawn, 20902, 1, 1) call that
    granted a 4-slot "small bag" to fresh characters. The starter loadout
    migration (006) already gives 6 × 36-slot Brewmeister's Backpacks, so
    the small bag just landed in overflow as clutter.
--]]

function spawn(NPC)
    SetPlayerProximityFunction(NPC, 10, "InRange", "LeaveRange")
    SetTempVariable(NPC, "QuestOfferCheck", "false")
end

function InRange(NPC, Spawn)
    if GetTempVariable(NPC, "QuestOfferCheck") == "false" then
        if GetClass(Spawn) == 0 and not HasQuest(Spawn, 5725) and not HasCompletedQuest(Spawn, 5725) then
            OfferQuest(NPC, Spawn, 5725)
            SetTempVariable(NPC, "QuestOfferCheck", "true")
            AddTimer(NPC, 10000, "TimerReset")
        end
    end
end

function respawn(NPC)
    spawn(NPC)
end

function TimerReset(NPC)
    SetTempVariable(NPC, "QuestOfferCheck", "false")
end
