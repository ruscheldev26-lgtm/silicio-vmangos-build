// SPDX-License-Identifier: GPL-2.0-or-later
// Included by PlayerBotAI.cpp; opt-in controller for a normally created character.
#include "Config/Config.h"
#include "Creature.h"
#include "SpellMgr.h"

class SilicioAI final : public PlayerBotAI
{
public:
    void OnBotEntryLoad(PlayerBotEntry* entry) override
    {
        // Persistent progress must remain attached to the character's real account.
        // The generic population framework otherwise assigns a synthetic account ID.
        entry->accountId = sObjectMgr.GetPlayerAccountIdByGUID(entry->playerGUID);
    }
    bool OnSessionLoaded(PlayerBotEntry* entry, WorldSession* session) override
    {
        if (!sConfig.GetBoolDefault("Silicio.Enable", false))
            return false;
        std::unique_ptr<QueryResult> row = CharacterDatabase.PQuery(
            "SELECT race, class, name FROM characters WHERE guid=%u", entry->playerGUID);
        if (!row)
            return false;
        Field* f = row->Fetch();
        if (f[0].GetUInt8() != RACE_GNOME || f[1].GetUInt8() != CLASS_MAGE ||
            f[2].GetCppString() != "Silicio")
            return false;
        return PlayerBotAI::OnSessionLoaded(entry, session);
    }

    void OnPlayerLogin() override
    {
        m_homeX = me->GetPositionX(); m_homeY = me->GetPositionY(); m_homeZ = me->GetPositionZ();
        m_homeMap = me->GetMapId();
        m_ready = me->GetRace() == RACE_GNOME && me->GetClass() == CLASS_MAGE &&
                  me->GetName() == std::string("Silicio");
        sLog.Out(LOG_BASIC, LOG_LVL_MINIMAL, "[SilicioAI v1] login guid=%u level=%u ready=%u build=4449",
                 me->GetGUIDLow(), me->GetLevel(), uint32(m_ready));
    }

    void MovementInform(uint32 type, uint32 id) override
    {
        if (type == POINT_MOTION_TYPE && id == 4448) m_roaming = false;
    }

    void UpdateAI(uint32 diff) override
    {
        if (!me) return;
        PlayerBotAI::UpdateAI(diff);
        if (!m_ready || !me->IsInWorld() || !me->IsAlive() ||
            me->IsBeingTeleportedNear() || me->IsBeingTeleportedFar()) return;
        if (m_timer > diff) { m_timer -= diff; return; }
        m_timer = 500;
        // No cross-map travel, teleport, resurrection, learned spells or level grants.
        if (me->GetMapId() != m_homeMap || me->IsNonMeleeSpellCasted(true)) return;
        Unit* victim = me->GetVictim();
        if (!victim && me->IsInCombat())
            for (Unit* attacker : me->GetAttackers())
                if (attacker->GetTypeId() == TYPEID_UNIT && attacker->IsAlive())
                { victim = attacker; me->Attack(victim, true); break; }
        if (victim && !victim->IsAlive()) { me->AttackStop(); victim = nullptr; }
        if (!victim && !me->IsInCombat())
        {
            if (me->GetHealthPercent() < 85 || me->GetPowerPercent(POWER_MANA) < 80)
            {
                me->GetMotionMaster()->MoveIdle();
                me->StopMoving();
                m_roaming = false;
                return; // normal server regeneration only
            }
            if (me->GetDistance(m_homeX, m_homeY, m_homeZ) > 160.0f)
            {
                if (!m_returning) me->GetMotionMaster()->MovePoint(4449, m_homeX, m_homeY, m_homeZ, MOVE_PATHFINDING | MOVE_WALK_MODE);
                m_returning = true; m_roaming = false;
                return;
            }
            m_returning = false;
            std::list<Creature*> wolves;
            me->GetCreatureListWithEntryInGrid(wolves, 705, 60.0f); // Ragged Young Wolf, starter area
            for (Creature* wolf : wolves)
            {
                if (!wolf->IsAlive() || wolf->IsInCombat() || wolf->GetLootRecipientGuid() ||
                    wolf->GetLevel() > me->GetLevel() || !me->IsWithinLOSInMap(wolf) ||
                    wolf->GetDistance(m_homeX, m_homeY, m_homeZ) > 160.0f) continue;
                if (!victim || me->GetDistance(wolf) < me->GetDistance(victim)) victim = wolf;
            }
            if (!victim)
            {
                if (!m_roaming)
                {
                    float x, y, z;
                    if (me->GetRandomPoint(m_homeX, m_homeY, m_homeZ, 35.0f, x, y, z))
                    {
                        me->GetMotionMaster()->MovePoint(4448, x, y, z, MOVE_PATHFINDING | MOVE_WALK_MODE);
                        m_roaming = true;
                    }
                }
                return;
            }
            if (!me->Attack(victim, true)) return;
            m_roaming = false;
            sLog.Out(LOG_BASIC, LOG_LVL_MINIMAL, "[SilicioAI v1] engage guid=%u target=%u",
                     me->GetGUIDLow(), victim->GetGUIDLow());
        }
        if (!victim) return;
        SpellEntry const* fireball = sSpellMgr.GetSpellEntry(133);
        if (me->HasSpell(133) && fireball && CanCastSpell(victim, fireball, false))
        {
            me->GetMotionMaster()->MoveIdle();
            me->StopMoving();
            me->SetFacingToObject(victim);
            me->CastSpell(victim, 133, false);
            m_timer = 1500;
            return;
        }
        if (me->GetMotionMaster()->GetCurrentMovementGeneratorType() != CHASE_MOTION_TYPE)
            me->GetMotionMaster()->MoveChase(victim);
        if (me->CanReachWithMeleeAutoAttack(victim) && me->IsAttackReady())
        {
            me->AttackerStateUpdate(victim);
            me->ResetAttackTimer();
        }
    }
private:
    uint32 m_timer = 0, m_homeMap = 0;
    float m_homeX = 0, m_homeY = 0, m_homeZ = 0;
    bool m_ready = false, m_roaming = false, m_returning = false;
};
