--[[
    Script Name    : Spells/Commoner/SpiritSteed.lua
    Script Author  : Skywalker646
    Script Date    : 2020.05.14 08:05:17
    Script Purpose :
                   :
    Patched        : upstream used SetMount(Caster, 51282) — appearance id
                     6921 is "leather artifact medium shoulders", not a
                     horse, so the rider got the speed bonus with no
                     visible mount. Switched to 2889 (creatures/mounts/
                     horse_ghost) to match the spirit-steed theme.
--]]

function precast(Caster)
 if GetMount(Caster) > 0 then
        return false
    end

    return true
end

function cast(Caster, Target, Speed, SkillAmt)
--Summons a mount to ride
SetMount(Caster, 3715)


-- Increases your ground speed by 130%
AddSpellBonus(Caster, 611, Speed)


end

function remove(Caster, Target)
SetMount(Caster, 0)
    RemoveSpellBonus(Caster)
    RemoveSkillBonus(Caster)
end
