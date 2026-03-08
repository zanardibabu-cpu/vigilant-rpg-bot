import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

import discord
from discord import app_commands

TURN_TIMEOUT_S = 35
CANAL_ARENA_X1_ID = 1479210311662960711


@dataclass
class FighterState:
    user_id: int
    nome: str
    classe: str
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
    used_stamina_skill: bool = False
    used_mana_skill: bool = False
    prev_action: Optional[str] = None


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
    turn_message_id: Optional[int] = None
    view: Optional[discord.ui.View] = None
    resolve_event: asyncio.Event = field(default_factory=asyncio.Event)


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
            hp=int(p.get("hp", 1)),
            hp_max=int(p.get("hp", 1)),
            stamina=int(p.get("stamina", max_stamina)),
            stamina_max=max_stamina,
            mana=int(p.get("mana", 0)),
            mana_max=int(p.get("mana", 0)),
        )

    async def _roll_attack(self, src: FighterState, dst: FighterState, atk_value: float, allow_crit: bool = True, accuracy_mult: float = 1.0, dmg_mult: float = 1.0):
        d20 = random.randint(1, 20)
        atk_total = int((d20 + atk_value) * accuracy_mult)
        def_total = 10 + int(dst.flags.get("base_def", 0)) + int(dst.buffs.get("def_turn", 0))
        if atk_total < def_total:
            return 0, d20, False
        dano = max(1, int(random.randint(1, 8) + atk_value - (def_total / 2)))
        crit = allow_crit and (d20 == 20 or (src.classe == "assassino" and random.random() < 0.10))
        if crit:
            dano *= 2
        dano = int(dano * dmg_mult)
        return max(1, dano), d20, crit

    async def _resolve_turn(self, match: ArenaMatch):
        logs = [f"⚔ Turno {match.turno_atual} — Resultado"]
        a, b = match.playerA, match.playerB
        for f in (a, b):
            if not f.acao:
                f.acao = "atacar"
                logs.append(f"⏱ {f.nome} não escolheu em 35s: ação automática = Atacar.")
            f.used_stamina_skill = False
            f.used_mana_skill = False

        logs.append(f"{a.nome} escolheu **{a.acao}**.")
        logs.append(f"{b.nome} escolheu **{b.acao}**.")

        order = ["render", "defender", "habilidade", "atacar"]
        acted = {a.user_id: False, b.user_id: False}

        for f in (a, b):
            if f.hp <= int(f.hp_max * 0.4) and f.classe == "barbaro" and not f.flags.get("berserk_activated"):
                f.flags["berserk_activated"] = True
                logs.append(f"🔥 {f.nome} ativou Fúria Berserk (dano x2, defesa -50%).")

        for action in order:
            for src, dst in ((a, b), (b, a)):
                if src.acao != action or acted[src.user_id]:
                    continue
                acted[src.user_id] = True

                src_player = await self.get_player(src.user_id)
                atk = await self.total_stat(src_player, "atk")
                mag = await self.total_stat(src_player, "magia")
                base_def = await self.total_stat(src_player, "defesa")
                src.flags["base_def"] = base_def

                dst_player = await self.get_player(dst.user_id)
                dst_base_def = await self.total_stat(dst_player, "defesa")
                dst.flags["base_def"] = dst_base_def

                if src.acao == "render":
                    src.hp = 0
                    logs.append(f"🏳 {src.nome} se rendeu.")
                    continue

                if src.acao == "defender":
                    custo = max(1, int(src.stamina_max * 0.20))
                    if src.stamina < custo:
                        logs.append(f"❌ {src.nome} tentou Defender, mas faltou stamina ({src.stamina}/{custo}).")
                    else:
                        src.stamina -= custo
                        src.buffs["def_turn"] = int(dst.flags.get("base_def", 0) * 0.5)
                        logs.append(f"🛡 {src.nome} defendeu (+50% defesa no turno) e gastou {custo} stamina.")
                        if src.classe == "guerreiro":
                            src.buffs["next_atk_bonus"] = 0.15
                    continue

                if src.acao == "habilidade":
                    if src.classe in ("guerreiro", "barbaro"):
                        if src.cooldowns.get("poder", 0) > 0:
                            src.acao = "atacar"
                            logs.append(f"⌛ {src.nome} está em cooldown de Poder Máximo. Virou ataque básico.")
                            acted[src.user_id] = False
                            continue
                        custo = max(1, int(src.stamina_max * 0.35))
                        if src.stamina < custo:
                            src.acao = "atacar"; acted[src.user_id] = False
                            logs.append(f"❌ {src.nome} sem stamina para Poder Máximo. Virou ataque básico.")
                            continue
                        src.stamina -= custo
                        src.used_stamina_skill = True
                        src.cooldowns["poder"] = 2
                        src.debuffs["def_down_next"] = 0.25
                        dmg_mult = 1.0 + 0.60
                        if src.flags.get("berserk_activated"):
                            dmg_mult *= 2
                        logs.append(f"✨ {src.nome} usou Poder Máximo (-{custo} stamina).")
                        dano, _, crit = await self._roll_attack(src, dst, atk * 1.60, dmg_mult=dmg_mult)
                        dst.hp = max(0, dst.hp - dano)
                        logs.append(f"💥 {src.nome} causou {dano} de dano{' (CRÍTICO)' if crit else ''}.")
                        continue

                    if src.classe == "clerigo":
                        if src.cooldowns.get("cura", 0) > 0:
                            src.acao = "atacar"; acted[src.user_id] = False
                            logs.append(f"⌛ {src.nome} está em cooldown de Cura Divina. Virou ataque básico.")
                            continue
                        custo = max(1, int(src.mana_max * 0.50))
                        if src.mana < custo:
                            src.acao = "atacar"; acted[src.user_id] = False
                            logs.append(f"❌ {src.nome} sem mana para Cura Divina. Virou ataque básico.")
                            continue
                        src.mana -= custo
                        src.used_mana_skill = True
                        src.cooldowns["cura"] = 2
                        cura = int((custo * 0.5) * 1.5)
                        cura = int(cura * 1.15)
                        hp_before = src.hp
                        src.hp = min(src.hp_max, src.hp + cura)
                        logs.append(f"✨ {src.nome} usou Cura Divina (-{custo} mana) e curou {src.hp - hp_before} HP.")
                        continue

                    if src.classe == "mago":
                        if src.cooldowns.get("arcano", 0) > 0:
                            src.acao = "atacar"; acted[src.user_id] = False
                            logs.append(f"⌛ {src.nome} está em cooldown de Poder Máximo Arcano. Virou ataque básico.")
                            continue
                        custo = max(1, int(src.mana_max * 0.50))
                        if src.mana < custo:
                            src.acao = "atacar"; acted[src.user_id] = False
                            logs.append(f"❌ {src.nome} sem mana para Poder Máximo Arcano. Virou ataque básico.")
                            continue
                        src.mana -= custo
                        src.used_mana_skill = True
                        src.cooldowns["arcano"] = 2
                        src.debuffs["def_down_next"] = 0.20
                        src.buffs["fluxo_next"] = min(0.30, float(src.buffs.get("fluxo_next", 0.0)) + 0.10)
                        dano, _, crit = await self._roll_attack(src, dst, mag * 1.70, dmg_mult=(1.0 + float(src.buffs.get("fluxo_now", 0.0))))
                        dst.hp = max(0, dst.hp - dano)
                        logs.append(f"✨ {src.nome} conjurou Poder Máximo Arcano (-{custo} mana), dano {dano}{' (CRÍTICO)' if crit else ''}.")
                        continue

                    if src.classe == "assassino":
                        if src.cooldowns.get("sombras", 0) > 0:
                            src.acao = "atacar"; acted[src.user_id] = False
                            logs.append(f"⌛ {src.nome} está em cooldown de Sombras. Virou ataque básico.")
                            continue
                        custo = max(1, int(src.stamina_max * 0.30))
                        if src.stamina < custo:
                            src.acao = "atacar"; acted[src.user_id] = False
                            logs.append(f"❌ {src.nome} sem stamina para Sombras. Virou ataque básico.")
                            continue
                        src.stamina -= custo
                        src.used_stamina_skill = True
                        src.cooldowns["sombras"] = 3
                        src.buffs["shadow_turns"] = 2
                        logs.append(f"✨ {src.nome} ocultou-se nas sombras por 2 turnos (-{custo} stamina).")
                        continue

                    if src.classe == "arqueiro":
                        if src.cooldowns.get("chuva", 0) > 0:
                            src.acao = "atacar"; acted[src.user_id] = False
                            logs.append(f"⌛ {src.nome} está em cooldown de Chuva de Flechas. Virou ataque básico.")
                            continue
                        custo = max(1, int(src.stamina_max * 0.30))
                        if src.stamina < custo:
                            src.acao = "atacar"; acted[src.user_id] = False
                            logs.append(f"❌ {src.nome} sem stamina para Chuva de Flechas. Virou ataque básico.")
                            continue
                        src.stamina -= custo
                        src.used_stamina_skill = True
                        src.cooldowns["chuva"] = 2
                        for idx in (1, 2):
                            dano, _, _ = await self._roll_attack(src, dst, atk * 0.75, allow_crit=False)
                            dst.hp = max(0, dst.hp - dano)
                            logs.append(f"🏹 {src.nome} flecha {idx} causou {dano}.")
                        continue

                    src.acao = "atacar"; acted[src.user_id] = False

                if src.acao == "atacar":
                    accuracy_mult = 1.0
                    dmg_mult = 1.0
                    atk_value = atk
                    if src.buffs.get("next_atk_bonus"):
                        atk_value *= 1.0 + float(src.buffs.pop("next_atk_bonus"))
                    if src.classe == "assassino" and src.buffs.get("shadow_turns", 0) > 0:
                        atk_value *= 0.75
                    if src.classe == "assassino" and dst.prev_action == "defender":
                        dmg_mult *= 1.20
                    if src.classe == "arqueiro" and dst.acao in ("atacar", "habilidade"):
                        accuracy_mult *= 1.20
                        dmg_mult *= 1.10
                    if dst.classe == "assassino" and dst.buffs.get("shadow_turns", 0) > 0:
                        accuracy_mult *= 0.40
                    if src.flags.get("berserk_activated"):
                        dmg_mult *= 2
                    if match.turno_atual >= 6:
                        dmg_mult *= 1.0 + (0.05 * (match.turno_atual - 5))
                    dano, _, crit = await self._roll_attack(src, dst, atk_value, accuracy_mult=accuracy_mult, dmg_mult=dmg_mult)
                    dst.hp = max(0, dst.hp - dano)
                    logs.append(f"⚔ {src.nome} atacou e causou {dano} de dano{' (CRÍTICO)' if crit else ''}.")
                    if src.classe == "mago":
                        src.buffs["fluxo_now"] = 0.0

        # efeitos defensivos/debuffs
        for f in (a, b):
            if f.debuffs.pop("def_down_next", 0):
                pass
            for k in list(f.cooldowns.keys()):
                f.cooldowns[k] = max(0, int(f.cooldowns[k]) - 1)
                if f.cooldowns[k] == 0:
                    del f.cooldowns[k]
            if f.buffs.get("shadow_turns", 0) > 0:
                f.buffs["shadow_turns"] -= 1
            f.prev_action = f.acao

        for f in (a, b):
            stam_regen = max(1, int(f.stamina_max * (0.10 if f.classe == "clerigo" else 0.05)))
            mana_regen = 2 if f.classe == "clerigo" else max(0, int(f.mana_max * 0.04))
            if f.used_stamina_skill:
                stam_regen = 0
            if f.used_mana_skill:
                mana_regen = 0
            old_st, old_mn = f.stamina, f.mana
            f.stamina = min(f.stamina_max, f.stamina + stam_regen)
            f.mana = min(f.mana_max, f.mana + mana_regen)
            logs.append(f"♻ {f.nome} regenerou +{f.stamina - old_st} stamina | +{f.mana - old_mn} mana.")

            if f.stamina <= 0:
                f.buffs["def_penalty"] = 0.15
            if f.mana <= 0:
                f.buffs["def_penalty_mana"] = 0.20

        logs.append("📊 Estado atual:")
        for f in (a, b):
            logs.append(
                f"{f.nome} — HP {f.hp}/{f.hp_max} | Mana {f.mana}/{f.mana_max} | Stamina {f.stamina}/{f.stamina_max} | CD {f.cooldowns or '-'}"
            )
        return "\n".join(logs)

    async def _finish_match(self, match: ArenaMatch, winner_id: Optional[int], loser_id: Optional[int], reason: str, channel: discord.abc.Messageable):
        match.ativo = False
        pa = await self.get_player(match.playerA.user_id)
        pb = await self.get_player(match.playerB.user_id)
        pa["hp"], pb["hp"] = max(1, match.playerA.hp), max(1, match.playerB.hp)
        pa["mana"], pb["mana"] = match.playerA.mana, match.playerB.mana
        pa["stamina"], pb["stamina"] = match.playerA.stamina, match.playerB.stamina

        extra = ""
        if winner_id and loser_id:
            w = pa if winner_id == pa["user_id"] else pb
            l = pb if loser_id == pb["user_id"] else pa
            transfer = int(int(l.get("gold", 0)) * 0.30)
            if transfer == 0 and int(l.get("gold", 0)) > 0:
                transfer = 1
            transfer = min(transfer, int(l.get("gold", 0)))
            l["gold"] = int(l.get("gold", 0)) - transfer
            w["gold"] = int(w.get("gold", 0)) + transfer
            w["xp"] = int(w.get("xp", 0)) + 500
            extra = f"\n🏆 Vencedor: <@{winner_id}>\n✨ +500 XP\n💰 Transferência: {transfer} gold."

        await self.save_player(pa)
        await self.save_player(pb)
        self.matches_by_user.pop(match.playerA.user_id, None)
        self.matches_by_user.pop(match.playerB.user_id, None)
        await channel.send(f"🏁 X1 encerrado: {reason}{extra}")

    async def _run_match(self, match: ArenaMatch, channel: discord.abc.Messageable):
        await channel.send(
            f"🎲 Arena iniciada!\nA: <@{match.playerA.user_id}> | B: <@{match.playerB.user_id}>\n"
            f"d20 de iniciativa = **{match.d20_iniciativa}**\nComeça: <@{match.quem_comecou}>"
        )

        while match.ativo:
            match.turno_atual += 1
            match.playerA.acao = None
            match.playerB.acao = None
            match.resolve_event.clear()
            match.deadline_ts = int(time.time()) + TURN_TIMEOUT_S
            view = TurnActionView(self, match, match.turno_atual)
            match.view = view
            msg = await channel.send(
                f"🕒 Turno {match.turno_atual}: escolhas secretas abertas por {TURN_TIMEOUT_S}s."
                f"\n<@{match.playerA.user_id}> e <@{match.playerB.user_id}>, escolham nos botões:",
                view=view,
            )
            match.turn_message_id = msg.id

            try:
                await asyncio.wait_for(match.resolve_event.wait(), timeout=TURN_TIMEOUT_S)
            except asyncio.TimeoutError:
                pass

            view.stop()
            await msg.edit(view=None)
            resumo = await self._resolve_turn(match)
            await channel.send(resumo)

            limit_a = max(1, int(match.playerA.hp_max * 0.05))
            limit_b = max(1, int(match.playerB.hp_max * 0.05))
            a_down = match.playerA.hp <= limit_a
            b_down = match.playerB.hp <= limit_b

            if a_down and b_down:
                if match.playerA.hp > match.playerB.hp:
                    await self._finish_match(match, match.playerA.user_id, match.playerB.user_id, "duplo nocaute com vantagem de HP", channel)
                elif match.playerB.hp > match.playerA.hp:
                    await self._finish_match(match, match.playerB.user_id, match.playerA.user_id, "duplo nocaute com vantagem de HP", channel)
                else:
                    await self._finish_match(match, None, None, "empate técnico", channel)
                return
            if a_down:
                await self._finish_match(match, match.playerB.user_id, match.playerA.user_id, "HP limite atingido", channel)
                return
            if b_down:
                await self._finish_match(match, match.playerA.user_id, match.playerB.user_id, "HP limite atingido", channel)
                return
            if match.playerA.acao == "render":
                await self._finish_match(match, match.playerB.user_id, match.playerA.user_id, "rendição", channel)
                return
            if match.playerB.acao == "render":
                await self._finish_match(match, match.playerA.user_id, match.playerB.user_id, "rendição", channel)
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
            match = ArenaMatch(True, interaction.channel_id, interaction.guild_id or 0, players[0], players[1], 0, starter.user_id, d20)
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
                other = m.playerA.user_id if uid == m.playerB.user_id else m.playerB.user_id
                await interaction.response.send_message(f"⚔️ Você está em um X1 ativo contra <@{other}>.", ephemeral=True)
                return
            await interaction.response.send_message("✅ Você não possui desafio/luta de X1 no momento.", ephemeral=True)


def setup_x1_arena(tree: app_commands.CommandTree, get_player: Callable, save_player: Callable, total_stat: Callable, require_player: Callable):
    manager = ArenaManager(tree, get_player, save_player, total_stat, require_player)
    manager.register_commands()
    return manager
