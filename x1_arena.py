import asyncio
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

import discord
from discord import app_commands

TURN_TIMEOUT_S = 60
MAX_TURNOS = 25
CANAL_ARENA_X1_ID = 1479210311662960711


@dataclass
class FighterState:
    user_id: int
    nome: str
    classe: str
    level: int
    hp: int
    hp_max: int
    stamina: int
    stamina_max: int
    mana: int
    mana_max: int
    acao: Optional[str] = None
    cooldowns: Dict[str, int] = field(default_factory=dict)
    buffs: Dict[str, Any] = field(default_factory=dict)
    debuffs: Dict[str, Any] = field(default_factory=dict)
    flags: Dict[str, Any] = field(default_factory=dict)
    momentum: int = 0


@dataclass
class ArenaMatch:
    ativo: bool
    canal_id: int
    guild_id: int
    playerA: FighterState
    playerB: FighterState
    turno_atual: int
    quem_comecou: int
    d20_iniciativa: int
    deadline_ts: int = 0
    view: Optional[discord.ui.View] = None
    resolve_event: asyncio.Event = field(default_factory=asyncio.Event)
    pressure_bonus: float = 0.0


class TurnActionView(discord.ui.View):
    def __init__(self, manager: "ArenaManager", match: ArenaMatch, turno: int):
        super().__init__(timeout=TURN_TIMEOUT_S)
        self.manager = manager
        self.match = match
        self.turno = turno

    async def _pick(self, interaction: discord.Interaction, action: str):
        if not self.match.ativo or self.turno != self.match.turno_atual:
            await interaction.response.send_message("❌ Este turno já foi encerrado.", ephemeral=True)
            return
        uid = interaction.user.id
        if uid not in (self.match.playerA.user_id, self.match.playerB.user_id):
            await interaction.response.send_message("❌ Você não participa deste combate.", ephemeral=True)
            return
        fighter = self.match.playerA if uid == self.match.playerA.user_id else self.match.playerB
        if fighter.acao is not None:
            await interaction.response.send_message("ℹ️ Você já registrou sua ação neste turno.", ephemeral=True)
            return

        if action in ("defender", "habilidade") and fighter.stamina <= 0:
            await interaction.response.send_message("⚠️ Sua stamina está zerada: só ataque básico é permitido.", ephemeral=True)
            return
        if action == "habilidade" and fighter.mana <= 0 and fighter.classe in ("mago", "clerigo"):
            await interaction.response.send_message("⚠️ Sua mana está zerada: habilidade indisponível.", ephemeral=True)
            return

        fighter.acao = action
        await interaction.response.send_message("✅ Ação registrada. Aguardando o oponente.", ephemeral=True)
        if self.match.playerA.acao and self.match.playerB.acao:
            self.match.resolve_event.set()

    @discord.ui.button(label="⚔ Atacar", style=discord.ButtonStyle.danger)
    async def atacar_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._pick(interaction, "atacar")

    @discord.ui.button(label="🛡 Defender", style=discord.ButtonStyle.primary)
    async def defender_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._pick(interaction, "defender")

    @discord.ui.button(label="✨ Habilidade", style=discord.ButtonStyle.success)
    async def habilidade_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._pick(interaction, "habilidade")

    @discord.ui.button(label="🏳 Render-se", style=discord.ButtonStyle.secondary)
    async def render_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._pick(interaction, "render")


class ArenaManager:
    def __init__(self, tree: app_commands.CommandTree, get_player, save_player, total_stat, require_player):
        self.tree = tree
        self.get_player = get_player
        self.save_player = save_player
        self.total_stat = total_stat
        self.require_player = require_player
        self.pending: Dict[int, Dict[str, int]] = {}
        self.matches_by_user: Dict[int, ArenaMatch] = {}

    def _busy(self, uid: int) -> bool:
        if uid in self.matches_by_user:
            return True
        for target_id, pend in self.pending.items():
            if uid == target_id or uid == int(pend["desafiante_id"]):
                return True
        return False

    async def _ensure_channel(self, interaction: discord.Interaction) -> bool:
        if interaction.channel_id != CANAL_ARENA_X1_ID:
            await interaction.response.send_message(
                "⚔️ O sistema de X1 só pode ser usado no canal 🏆arena-x1🏆.", ephemeral=True
            )
            return False
        return True

    def _fighter_from_player(self, uid: int, member_name: str, p: dict) -> FighterState:
        max_stamina = int(p.get("max_stamina", 100))
        return FighterState(
            user_id=uid,
            nome=member_name,
            classe=(p.get("classe") or "").lower(),
            level=int(p.get("level", 1)),
            hp=int(p.get("hp", 1)),
            hp_max=int(p.get("hp", 1)),
            stamina=int(p.get("stamina", max_stamina)),
            stamina_max=max_stamina,
            mana=int(p.get("mana", 0)),
            mana_max=int(p.get("mana", 0)),
        )

    def _pressure_for_turn(self, turno: int) -> float:
        if turno <= 5:
            return 0.0
        if turno <= 10:
            return 0.10
        if turno <= 15:
            return 0.20
        return 0.30

    def _hp_limit(self, f: FighterState) -> int:
        return max(1, math.ceil(f.hp_max * 0.05))

    def _cooldowns_text(self, f: FighterState) -> str:
        items = [f"{k}:{v}" for k, v in sorted(f.cooldowns.items()) if v > 0]
        return ", ".join(items) if items else "nenhum"

    def _momentum_label(self, value: int) -> str:
        return f"{value:+d}"

    def _mod_from_d20_offensive(self, d20: int):
        if d20 == 1:
            return "crit_fail", 0.0
        if 2 <= d20 <= 5:
            return "fail", 0.0
        if d20 == 19:
            return "power", 1.5
        if d20 == 20:
            return "crit", 2.0
        return "hit", 1.0

    def _mod_from_d20_support(self, d20: int) -> float:
        if d20 == 1:
            return 0.5
        if 2 <= d20 <= 5:
            return 0.75
        if d20 == 19:
            return 1.25
        if d20 == 20:
            return 1.5
        return 1.0

    def _add_momentum(self, logs: list[str], f: FighterState, delta: int):
        before = f.momentum
        f.momentum = max(-3, min(3, f.momentum + delta))
        if f.momentum == before:
            return
        if delta > 0:
            logs.append(f"🔥 {f.nome} ganhou Momentum +1")
        else:
            logs.append(f"💨 {f.nome} perdeu Momentum -1")

    async def _base_stats(self, fighter: FighterState) -> Dict[str, float]:
        p = await self.get_player(fighter.user_id)
        atk = float(await self.total_stat(p, "atk"))
        defesa = float(await self.total_stat(p, "defesa"))
        magia = float(await self.total_stat(p, "magia"))
        return {"atk": atk, "def": defesa, "mag": magia}

    async def _resolve_offensive_action(
        self,
        src: FighterState,
        dst: FighterState,
        logs: list[str],
        momentum_logs: list[str],
        hp_logs: list[str],
        base_power: float,
        pressure_bonus: float,
        defend_bonus_scale: float,
        extra_dmg_mult: float = 1.0,
        is_skill: bool = False,
    ) -> tuple[int, int, str]:
        d20 = random.randint(1, 20)
        logs.append(f"🎲 d20 de {src.nome} = {d20}")

        outcome, mult = self._mod_from_d20_offensive(d20)

        if dst.classe == "assassino" and dst.buffs.get("oculto_turns", 0) > 0 and random.random() < 0.50:
            if outcome in ("crit_fail", "fail"):
                logs.append(f"🌫 {src.nome} errou: {dst.nome} evitou o golpe enquanto estava oculto.")
                if outcome == "crit_fail":
                    src.debuffs["crit_fail_def_down_next"] = True
                    logs.append(f"💥 Falha crítica de {src.nome}: ação perdida e -10% defesa no próximo turno.")
                self._add_momentum(momentum_logs, src, -1)
                return 0, d20, "evaded"

            before = dst.hp
            dst.hp = max(self._hp_limit(dst), dst.hp - 1)
            dealt = max(0, before - dst.hp)
            logs.append("⚔ O golpe passou de raspão e causou 1 de dano.")
            hp_logs.append(f"🩸 {dst.nome} perdeu {dealt} HP.")
            self._add_momentum(momentum_logs, src, +1)
            return dealt, d20, "evaded_graze"

        if src.debuffs.get("crit_fail_def_down_next", False):
            src.debuffs.pop("crit_fail_def_down_next", None)

        if outcome == "crit_fail":
            logs.append(f"💥 Falha crítica de {src.nome}: ação perdida e -10% defesa no próximo turno.")
            src.debuffs["crit_fail_def_down_next"] = True
            self._add_momentum(momentum_logs, src, -1)
            return 0, d20, "crit_fail"
        if outcome == "fail":
            logs.append(f"❌ {src.nome} falhou no ataque.")
            self._add_momentum(momentum_logs, src, -1)
            return 0, d20, "fail"

        src_stats = await self._base_stats(src)
        dst_stats = await self._base_stats(dst)

        acc_bonus = src.momentum * 0.02
        atk_total = d20 + src_stats["atk"] + (src_stats["atk"] * acc_bonus)

        defend_extra = float(dst.buffs.get("defender_bonus", 0.0))
        defense_total = 10 + dst_stats["def"] + (defend_extra * defend_bonus_scale)
        if dst.stamina <= 0:
            defense_total *= 0.85
        if dst.mana <= 0 and dst.classe in ("mago", "clerigo"):
            defense_total *= 0.80
        if dst.debuffs.get("mana_zero_def_down", False):
            defense_total *= 0.50
        if dst.debuffs.get("berserk_def_down", False):
            defense_total *= 0.50
        if dst.debuffs.get("crit_fail_def_down_next", False):
            defense_total *= 0.90

        if atk_total < defense_total:
            before = dst.hp
            dst.hp = max(self._hp_limit(dst), dst.hp - 1)
            dealt = max(0, before - dst.hp)
            logs.append("⚔ O golpe passou de raspão e causou 1 de dano.")
            hp_logs.append(f"🩸 {dst.nome} perdeu {dealt} HP.")
            self._add_momentum(momentum_logs, src, +1)
            return dealt, d20, "blocked_graze"

        raw = random.randint(1, 8) + base_power - (dst_stats["def"] / 2)
        raw = max(1, int(raw))

        if outcome == "power":
            logs.append("✨ Acerto poderoso! (+50% dano)")
        elif outcome == "crit":
            logs.append("💀 Crítico! (x2 dano)")

        momentum_dmg = 1.0 + (src.momentum * 0.02)
        dmg = raw * mult * extra_dmg_mult * (1.0 + pressure_bonus) * momentum_dmg

        if src.classe == "barbaro" and src.buffs.get("berserk_on", False):
            dmg *= 2.0
        if src.classe == "assassino" and src.buffs.get("oculto_turns", 0) > 0:
            dmg *= 0.75
        if src.classe == "guerreiro" and src.buffs.get("postura_turns", 0) > 0:
            dmg *= 1.25
        if src.classe == "arqueiro" and d20 >= 19:
            dmg *= 1.10
        if dst.classe == "guerreiro":
            dmg *= 0.90

        final_damage = max(1, int(dmg))
        before = dst.hp
        dst.hp = max(self._hp_limit(dst), dst.hp - final_damage)
        dealt = max(0, before - dst.hp)
        logs.append(f"💥 {src.nome} causou {dealt} de dano.")
        hp_logs.append(f"🩸 {dst.nome} perdeu {dealt} HP.")

        if dealt > 0:
            self._add_momentum(momentum_logs, src, +1)
            if outcome == "crit":
                self._add_momentum(momentum_logs, dst, -1)

        if src.classe == "clerigo" and is_skill and dealt > 0:
            cap = max(1, int(src.hp_max * 0.15))
            heal = min(cap, int(dealt * 0.15))
            h_before = src.hp
            src.hp = min(src.hp_max, src.hp + heal)
            if src.hp > h_before:
                logs.append(f"⛪ Julgamento Sagrado curou {src.nome} em {src.hp - h_before} HP.")

        return dealt, d20, "hit" if not is_skill else "skill_hit"

    def _apply_resource_costs(self, src: FighterState, action: str, cost_logs: list[str]) -> bool:
        if action == "defender":
            cost = 20
            if src.stamina < cost:
                return False
            src.stamina -= cost
            cost_logs.append(f"🔋 {src.nome} gastou {cost} stamina.")
            mana_before = src.mana
            src.mana = min(src.mana_max, src.mana + 8)
            recovered = src.mana - mana_before
            cost_logs.append(f"🔵 {src.nome} recuperou {recovered} mana ao focar na defesa.")
            src.buffs["defender_bonus"] = src.flags.get("base_def", 0.0) * 0.50
            return True
        return True

    async def _resolve_turn(self, match: ArenaMatch):
        logs: list[str] = [f"⚔ Turno {match.turno_atual} — Resultado"]
        action_logs: list[str] = []
        hp_logs: list[str] = []
        cost_logs: list[str] = []
        regen_logs: list[str] = []
        momentum_logs: list[str] = []

        a, b = match.playerA, match.playerB
        for f in (a, b):
            f.flags["base_def"] = (await self._base_stats(f))["def"]

        for f in (a, b):
            if not f.acao:
                f.acao = "atacar"
                action_logs.append(f"⏱ {f.nome} não escolheu em {TURN_TIMEOUT_S}s: ação automática = ataque básico.")

        action_logs.append(f"{a.nome} escolheu {a.acao}.")
        action_logs.append(f"{b.nome} escolheu {b.acao}.")

        prev_pressure = match.pressure_bonus
        match.pressure_bonus = self._pressure_for_turn(match.turno_atual)
        if match.pressure_bonus != prev_pressure:
            logs.append(f"🔥 Pressão da Arena: +{int(match.pressure_bonus * 100)}% dano")

        for f in (a, b):
            if f.classe == "barbaro" and f.hp <= int(f.hp_max * 0.4) and not f.flags.get("berserk_used"):
                f.flags["berserk_used"] = True
                f.buffs["berserk_on"] = True
                f.debuffs["berserk_def_down"] = True
                action_logs.append(f"🔥 {f.nome} ativou Fúria Berserker (x2 dano, -50% defesa).")

        order = ["render", "defender", "habilidade", "atacar"]
        acted = set()

        for action in order:
            for src, dst in ((a, b), (b, a)):
                if src.user_id in acted or src.acao != action:
                    continue
                acted.add(src.user_id)

                if src.acao == "render":
                    action_logs.append(f"🏳 {src.nome} se rendeu.")
                    src.hp = self._hp_limit(src)
                    continue

                if src.stamina <= 0 and src.acao in ("defender", "habilidade"):
                    src.acao = "atacar"
                    action_logs.append(f"⚠️ {src.nome} está sem stamina e só pode atacar.")
                    acted.remove(src.user_id)
                    continue

                if src.mana <= 0 and src.acao == "habilidade" and src.classe in ("mago", "clerigo"):
                    src.acao = "atacar"
                    src.debuffs["mana_zero_def_down"] = True
                    action_logs.append(f"⚠️ {src.nome} está sem mana e só pode atacar.")
                    acted.remove(src.user_id)
                    continue

                if src.acao == "defender":
                    if not self._apply_resource_costs(src, "defender", cost_logs):
                        action_logs.append(f"❌ {src.nome} tentou defender, mas não tinha stamina suficiente.")
                        continue
                    action_logs.append(f"🛡 {src.nome} ergueu defesa (+50% defesa base no turno).")
                    continue

                if src.acao == "habilidade":
                    if src.classe == "mago":
                        if src.cooldowns.get("arcano", 0) > 0:
                            action_logs.append(f"⌛ {src.nome} está em cooldown e virou ataque básico.")
                            src.acao = "atacar"
                            acted.remove(src.user_id)
                            continue
                        cost = max(1, int(src.mana * 0.50))
                        if src.mana < cost:
                            src.acao = "atacar"
                            acted.remove(src.user_id)
                            continue
                        src.mana -= cost
                        src.cooldowns["arcano"] = 1
                        cost_logs.append(f"🔵 {src.nome} gastou {cost} mana.")
                        if src.mana <= 0:
                            src.debuffs["mana_zero_def_down"] = True
                        mag = (await self._base_stats(src))["mag"]
                        await self._resolve_offensive_action(
                            src, dst, action_logs, momentum_logs, hp_logs,
                            base_power=(mag * 0.7),
                            pressure_bonus=match.pressure_bonus,
                            defend_bonus_scale=0.5,
                            is_skill=True,
                        )
                        continue

                    if src.classe == "clerigo":
                        if src.cooldowns.get("cura", 0) > 0:
                            action_logs.append(f"⌛ {src.nome} está em cooldown e virou ataque básico.")
                            src.acao = "atacar"
                            acted.remove(src.user_id)
                            continue
                        cost = max(1, int(src.mana * 0.50))
                        if src.mana < cost:
                            src.acao = "atacar"
                            acted.remove(src.user_id)
                            continue
                        src.mana -= cost
                        src.cooldowns["cura"] = 1
                        cost_logs.append(f"🔵 {src.nome} gastou {cost} mana.")
                        d20 = random.randint(1, 20)
                        action_logs.append(f"🎲 d20 de {src.nome} = {d20}")
                        eff_mult = self._mod_from_d20_support(d20)
                        mag = (await self._base_stats(src))["mag"]
                        heal_base = (mag * 0.5) + random.randint(1, 8)
                        heal = max(1, int(heal_base * eff_mult))
                        before = src.hp
                        src.hp = min(src.hp_max, src.hp + heal)
                        action_logs.append(f"✨ Cura Divina restaurou {src.hp - before} HP em {src.nome}.")
                        if src.mana <= 0:
                            src.debuffs["mana_zero_def_down"] = True
                        continue

                    if src.classe == "barbaro":
                        if src.cooldowns.get("brutal", 0) > 0:
                            src.acao = "atacar"
                            acted.remove(src.user_id)
                            continue
                        if src.stamina < 35:
                            src.acao = "atacar"
                            acted.remove(src.user_id)
                            continue
                        src.stamina -= 35
                        src.cooldowns["brutal"] = 1
                        cost_logs.append(f"🔋 {src.nome} gastou 35 stamina.")
                        atk = (await self._base_stats(src))["atk"]
                        await self._resolve_offensive_action(
                            src, dst, action_logs, momentum_logs, hp_logs,
                            base_power=(atk * 1.4),
                            pressure_bonus=match.pressure_bonus,
                            defend_bonus_scale=0.5,
                            is_skill=True,
                        )
                        continue

                    if src.classe == "assassino":
                        if src.cooldowns.get("sombras", 0) > 0:
                            src.acao = "atacar"
                            acted.remove(src.user_id)
                            continue
                        if src.stamina < 30:
                            src.acao = "atacar"
                            acted.remove(src.user_id)
                            continue
                        src.stamina -= 30
                        src.cooldowns["sombras"] = 2
                        src.buffs["oculto_turns"] = 2
                        cost_logs.append(f"🔋 {src.nome} gastou 30 stamina.")
                        action_logs.append(f"✨ {src.nome} usou Ocultar nas Sombras por 2 turnos.")
                        continue

                    if src.classe == "guerreiro":
                        if src.cooldowns.get("postura", 0) > 0:
                            src.acao = "atacar"
                            acted.remove(src.user_id)
                            continue
                        if src.stamina < 25:
                            src.acao = "atacar"
                            acted.remove(src.user_id)
                            continue
                        src.stamina -= 25
                        src.cooldowns["postura"] = 2
                        src.buffs["postura_turns"] = 2
                        cost_logs.append(f"🔋 {src.nome} gastou 25 stamina.")
                        action_logs.append(f"✨ {src.nome} entrou em Postura de Combate (+25% atk/def por 2 turnos).")
                        continue

                    if src.classe == "arqueiro":
                        if src.cooldowns.get("chuva", 0) > 0:
                            src.acao = "atacar"
                            acted.remove(src.user_id)
                            continue
                        if src.stamina < 30:
                            src.acao = "atacar"
                            acted.remove(src.user_id)
                            continue
                        src.stamina -= 30
                        src.cooldowns["chuva"] = 1
                        src.buffs["chuva_atk_bonus"] = 0.5
                        cost_logs.append(f"🔋 {src.nome} gastou 30 stamina.")
                        action_logs.append(f"✨ {src.nome} ativou Chuva de Flechas (+50% ataque neste turno).")
                        continue

                    src.acao = "atacar"
                    acted.remove(src.user_id)
                    continue

                if src.acao == "atacar":
                    atk = (await self._base_stats(src))["atk"]
                    extra = 1.0
                    if src.buffs.get("postura_turns", 0) > 0:
                        extra *= 1.25
                    if src.buffs.get("chuva_atk_bonus", 0) > 0:
                        extra *= 1.5
                    await self._resolve_offensive_action(
                        src, dst, action_logs, momentum_logs, hp_logs,
                        base_power=atk,
                        pressure_bonus=match.pressure_bonus,
                        defend_bonus_scale=1.0,
                        extra_dmg_mult=extra,
                    )

        for f in (a, b):
            for key in list(f.cooldowns.keys()):
                if f.cooldowns[key] > 0:
                    f.cooldowns[key] -= 1
                if f.cooldowns[key] <= 0:
                    f.cooldowns.pop(key, None)
            if f.buffs.get("oculto_turns", 0) > 0:
                f.buffs["oculto_turns"] -= 1
            if f.buffs.get("postura_turns", 0) > 0:
                f.buffs["postura_turns"] -= 1
            f.buffs.pop("chuva_atk_bonus", None)
            f.buffs.pop("defender_bonus", None)

            add_stam = 5
            add_mana = 2
            if f.classe == "mago":
                add_mana = 12
            elif f.classe == "clerigo":
                add_stam = 10
                add_mana = 4

            before_s = f.stamina
            before_m = f.mana
            f.stamina = min(f.stamina_max, f.stamina + add_stam)
            f.mana = min(f.mana_max, f.mana + add_mana)
            s_msg = f"+{f.stamina - before_s} stamina" if f.stamina > before_s else "stamina já estava no máximo"
            m_msg = f"+{f.mana - before_m} mana" if f.mana > before_m else "mana já estava no máximo"
            regen_logs.append(f"{f.nome} {s_msg} | {m_msg}")

        logs.extend(action_logs)
        if hp_logs:
            logs.append("")
            logs.extend(hp_logs)
        if cost_logs:
            logs.append("")
            logs.extend(cost_logs)
        logs.append("")
        logs.append("♻ Regeneração do turno:")
        logs.extend(regen_logs)
        if momentum_logs:
            logs.append("")
            logs.append("🔥 Momentum:")
            logs.extend(momentum_logs)
        logs.append("")
        logs.append("📊 Estado atual:")
        logs.append(
            f"{a.nome} — Nv. {a.level} | HP {a.hp}/{a.hp_max} | Mana {a.mana}/{a.mana_max} | "
            f"Stamina {a.stamina}/{a.stamina_max} | Momentum {self._momentum_label(a.momentum)} | CD {self._cooldowns_text(a)}"
        )
        logs.append(
            f"{b.nome} — Nv. {b.level} | HP {b.hp}/{b.hp_max} | Mana {b.mana}/{b.mana_max} | "
            f"Stamina {b.stamina}/{b.stamina_max} | Momentum {self._momentum_label(b.momentum)} | CD {self._cooldowns_text(b)}"
        )
        return "\n".join(logs)

    async def _finish_match(self, match: ArenaMatch, winner_id: Optional[int], loser_id: Optional[int], motivo: str, channel: discord.abc.Messageable):
        match.ativo = False
        for uid in (match.playerA.user_id, match.playerB.user_id):
            self.matches_by_user.pop(uid, None)

        if match.view:
            for item in match.view.children:
                item.disabled = True

        if winner_id and loser_id:
            winner = await self.get_player(winner_id)
            loser = await self.get_player(loser_id)
            if winner and loser:
                loser_gold = int(loser.get("gold", 0))
                reward_gold = int(loser_gold * 0.30)
                if loser_gold > 0:
                    reward_gold = max(1, reward_gold)
                loser["gold"] = max(0, loser_gold - reward_gold)
                winner["gold"] = int(winner.get("gold", 0)) + reward_gold
                winner["xp"] = int(winner.get("xp", 0)) + 500
                await self.save_player(loser)
                await self.save_player(winner)

            w_state = match.playerA if match.playerA.user_id == winner_id else match.playerB
            l_state = match.playerA if match.playerA.user_id == loser_id else match.playerB
            await channel.send(
                f"🏁 Luta encerrada ({motivo}).\n"
                f"🏆 Vencedor: <@{winner_id}> — Nv. {w_state.level}\n"
                f"☠ Derrotado: <@{loser_id}> — Nv. {l_state.level}\n"
                f"🎁 Recompensa: 500 XP e 30% do gold do derrotado."
            )
        else:
            await channel.send(f"🏁 Luta encerrada ({motivo}). Resultado: empate técnico.")

    async def _run_match(self, match: ArenaMatch, channel: discord.abc.Messageable):
        a, b = match.playerA, match.playerB
        await channel.send(
            "🎲 Arena iniciada!\n"
            f"A: <@{a.user_id}> — Nv. {a.level} | B: <@{b.user_id}> — Nv. {b.level}\n"
            f"d20 de iniciativa = {match.d20_iniciativa}\n"
            f"Começa: <@{match.quem_comecou}>"
        )

        while match.ativo:
            match.turno_atual += 1
            if match.turno_atual > MAX_TURNOS:
                await self._finish_match(match, None, None, "🏁 Empate por exaustão.", channel)
                return

            for f in (match.playerA, match.playerB):
                f.acao = None
            match.resolve_event = asyncio.Event()
            match.deadline_ts = int(time.time()) + TURN_TIMEOUT_S

            match.view = TurnActionView(self, match, match.turno_atual)
            await channel.send(
                f"⏳ Turno {match.turno_atual}: escolham suas ações em segredo (60s).",
                view=match.view,
            )

            try:
                await asyncio.wait_for(match.resolve_event.wait(), timeout=TURN_TIMEOUT_S)
            except asyncio.TimeoutError:
                pass

            for item in match.view.children:
                item.disabled = True

            turn_log = await self._resolve_turn(match)
            await channel.send(turn_log)

            a_limit = self._hp_limit(match.playerA)
            b_limit = self._hp_limit(match.playerB)
            a_down = match.playerA.hp <= a_limit
            b_down = match.playerB.hp <= b_limit

            if match.playerA.acao == "render":
                await self._finish_match(match, match.playerB.user_id, match.playerA.user_id, "por rendição", channel)
                return
            if match.playerB.acao == "render":
                await self._finish_match(match, match.playerA.user_id, match.playerB.user_id, "por rendição", channel)
                return

            if a_down and b_down:
                if match.playerA.hp > match.playerB.hp:
                    await self._finish_match(match, match.playerA.user_id, match.playerB.user_id, "duplo nocaute (vantagem de HP)", channel)
                elif match.playerB.hp > match.playerA.hp:
                    await self._finish_match(match, match.playerB.user_id, match.playerA.user_id, "duplo nocaute (vantagem de HP)", channel)
                else:
                    await self._finish_match(match, None, None, "duplo nocaute com HP igual", channel)
                return
            if a_down:
                await self._finish_match(match, match.playerB.user_id, match.playerA.user_id, "HP limite atingido", channel)
                return
            if b_down:
                await self._finish_match(match, match.playerA.user_id, match.playerB.user_id, "HP limite atingido", channel)
                return

    def register_commands(self):
        @self.tree.command(name="x1", description="Desafiar um jogador para duelo na arena.")
        async def x1_cmd(interaction: discord.Interaction, jogador: discord.Member):
            if not await self._ensure_channel(interaction):
                return
            if jogador.bot or jogador.id == interaction.user.id:
                await interaction.response.send_message("❌ Desafio inválido.", ephemeral=True)
                return
            if self._busy(interaction.user.id) or self._busy(jogador.id):
                await interaction.response.send_message("❌ Um dos jogadores já está em desafio/luta de X1.", ephemeral=True)
                return
            p1 = await self.get_player(interaction.user.id)
            p2 = await self.get_player(jogador.id)
            if not p1 or not p2:
                await interaction.response.send_message("❌ Ambos precisam ter personagem.", ephemeral=True)
                return
            self.pending[jogador.id] = {"desafiante_id": interaction.user.id, "desafiado_id": jogador.id}
            await interaction.response.send_message(
                f"⚔️ {interaction.user.mention} desafiou {jogador.mention}. Use /aceitarx1 ou /recusarx1."
            )

        @self.tree.command(name="aceitarx1", description="Aceitar um desafio de X1.")
        async def aceitarx1_cmd(interaction: discord.Interaction):
            if not await self._ensure_channel(interaction):
                return
            pend = self.pending.pop(interaction.user.id, None)
            if not pend:
                await interaction.response.send_message("❌ Você não possui desafio pendente.", ephemeral=True)
                return
            a_id = int(pend["desafiante_id"])
            b_id = int(pend["desafiado_id"])
            if self._busy(a_id) or self._busy(b_id):
                await interaction.response.send_message("❌ Um dos jogadores já está em X1.", ephemeral=True)
                return

            pa = await self.get_player(a_id)
            pb = await self.get_player(b_id)
            if not pa or not pb:
                await interaction.response.send_message("❌ Um dos jogadores não possui personagem válido.", ephemeral=True)
                return

            member_a = interaction.guild.get_member(a_id) if interaction.guild else None
            member_b = interaction.guild.get_member(b_id) if interaction.guild else None
            fa = self._fighter_from_player(a_id, member_a.display_name if member_a else f"{a_id}", pa)
            fb = self._fighter_from_player(b_id, member_b.display_name if member_b else f"{b_id}", pb)
            players = [fa, fb]
            random.shuffle(players)
            d20 = random.randint(1, 20)
            starter = players[0] if d20 <= 10 else players[1]

            match = ArenaMatch(
                ativo=True,
                canal_id=interaction.channel_id,
                guild_id=interaction.guild_id or 0,
                playerA=players[0],
                playerB=players[1],
                turno_atual=0,
                quem_comecou=starter.user_id,
                d20_iniciativa=d20,
            )
            self.matches_by_user[fa.user_id] = match
            self.matches_by_user[fb.user_id] = match
            await interaction.response.send_message("✅ Desafio aceito. Iniciando arena...")
            asyncio.create_task(self._run_match(match, interaction.channel))

        @self.tree.command(name="recusarx1", description="Recusar um desafio de X1.")
        async def recusarx1_cmd(interaction: discord.Interaction):
            if not await self._ensure_channel(interaction):
                return
            pend = self.pending.pop(interaction.user.id, None)
            if not pend:
                await interaction.response.send_message("❌ Você não possui desafio pendente.", ephemeral=True)
                return
            await interaction.response.send_message(f"❎ <@{interaction.user.id}> recusou o desafio de <@{int(pend['desafiante_id'])}>.")

        @self.tree.command(name="cancelarx1", description="Cancelar um desafio de X1 ainda não aceito.")
        async def cancelarx1_cmd(interaction: discord.Interaction):
            if not await self._ensure_channel(interaction):
                return
            target = next((k for k, v in self.pending.items() if int(v["desafiante_id"]) == interaction.user.id), None)
            if target is None:
                await interaction.response.send_message("❌ Você não possui desafio pendente para cancelar.", ephemeral=True)
                return
            self.pending.pop(target, None)
            await interaction.response.send_message("✅ Seu desafio de X1 foi cancelado.")

        @self.tree.command(name="statusx1", description="Ver seu status atual no sistema de X1.")
        async def statusx1_cmd(interaction: discord.Interaction):
            if not await self._ensure_channel(interaction):
                return
            uid = interaction.user.id
            if uid in self.pending:
                await interaction.response.send_message(
                    f"📨 Você foi desafiado por <@{int(self.pending[uid]['desafiante_id'])}>. Use /aceitarx1 ou /recusarx1.", ephemeral=True
                )
                return
            for alvo_id, pend in self.pending.items():
                if int(pend["desafiante_id"]) == uid:
                    await interaction.response.send_message(f"⏳ Seu desafio para <@{alvo_id}> está pendente.", ephemeral=True)
                    return
            if uid in self.matches_by_user:
                m = self.matches_by_user[uid]
                other = m.playerA if uid == m.playerB.user_id else m.playerB
                me = m.playerA if uid == m.playerA.user_id else m.playerB
                await interaction.response.send_message(
                    f"⚔️ Você está em um X1 ativo contra <@{other.user_id}>.\n"
                    f"Seu estado: Nv. {me.level} | HP {me.hp}/{me.hp_max} | Mana {me.mana}/{me.mana_max} | "
                    f"Stamina {me.stamina}/{me.stamina_max} | Momentum {me.momentum:+d}",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message("✅ Você não possui desafio/luta de X1 no momento.", ephemeral=True)


def setup_x1_arena(tree: app_commands.CommandTree, get_player: Callable, save_player: Callable, total_stat: Callable, require_player: Callable):
    manager = ArenaManager(tree, get_player, save_player, total_stat, require_player)
    manager.register_commands()
    return manager
