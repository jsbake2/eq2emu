--[[
    Script Name    : Spells/Commoner/BotSummonAll.lua
    Script Purpose : Summon every group bot the caster owns to the
                     caster's location. Wraps /bot summon group.
--]]

function cast(Caster, Target)
    BotCommand(Caster, "summon group")
end
