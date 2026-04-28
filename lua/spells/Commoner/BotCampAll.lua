--[[
    Script Name    : Spells/Commoner/BotCampAll.lua
    Script Purpose : Camp every group bot the caster owns. Wraps
                     /bot camp all.
--]]

function cast(Caster, Target)
    BotCommand(Caster, "camp all")
end
