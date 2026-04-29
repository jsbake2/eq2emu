--[[
    Script Name    : Spells/Commoner/BotSpawn2.lua
    Script Purpose : Spawn the caster's bot in slot 2 (matches the
                     bot_id used by /bot list / /bot spawn 2).
--]]

function cast(Caster, Target)
    BotCommand(Caster, "spawn 2")
end
