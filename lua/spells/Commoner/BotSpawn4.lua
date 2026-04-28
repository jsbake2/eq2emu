--[[
    Script Name    : Spells/Commoner/BotSpawn4.lua
    Script Purpose : Spawn the caster's bot in slot 4 (matches the
                     bot_id used by /bot list / /bot spawn 4).
--]]

function cast(Caster, Target)
    BotCommand(Caster, "spawn 4")
end
