--[[
    Script Name    : Spells/Commoner/Stalk.lua
    Script Author  : LordPazuzu
    Script Date    : 2023.03.30 08:03:54
    Script Purpose :
                   :
    Patched        : missing comma between Target and Hate (caused luac
                     parse failure: ')' expected near 'Hate').
--]]


function cast(Caster, Target, Hate)
    AddHate(Caster, Target, Hate, 1)
end
