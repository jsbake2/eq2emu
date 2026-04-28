--[[
    Script Name    : Spells/Commoner/BotPrepull.lua
    Script Purpose : Prime every group bot the caster owns to lay
                     wards proactively before the pull. Wraps
                     /bot prepull.
--]]

function cast(Caster, Target)
    BotCommand(Caster, "prepull")
end
