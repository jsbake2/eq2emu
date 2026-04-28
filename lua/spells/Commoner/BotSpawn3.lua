--[[
    Script Name    : Spells/Commoner/BotSpawn3.lua
    Script Purpose : Spawn the caster's bot in slot 3 (matches the
                     bot_id used by /bot list / /bot spawn 3).
--]]

function cast(Caster, Target)
    BotCommand(Caster, "spawn 3")
end
