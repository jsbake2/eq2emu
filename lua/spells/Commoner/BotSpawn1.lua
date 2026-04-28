--[[
    Script Name    : Spells/Commoner/BotSpawn1.lua
    Script Purpose : Spawn the caster's bot in slot 1 (matches the
                     bot_id used by /bot list / /bot spawn 1).
--]]

function cast(Caster, Target)
    BotCommand(Caster, "spawn 1")
end
