--[[
    Script Name    : Spells/Commoner/CallVulrich.lua
    Script Author  : LordPazuzu
    Script Date    : 2025.02.15 07:02:04
    Script Purpose : 
                   : 
--]]

function cast(Caster, Target)
    SetMount(Caster, 219)
end

function remove(Caster, Target)
    SetMount(Caster, 0)
end
