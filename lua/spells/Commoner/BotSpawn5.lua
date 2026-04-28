--[[
    Script Name    : Spells/Commoner/BotSpawn5.lua
    Script Purpose : Spawn the caster's bot in slot 5 (matches the
                     bot_id used by /bot list / /bot spawn 5).
--]]

function cast(Caster, Target)
    BotCommand(Caster, "spawn 5")
end
