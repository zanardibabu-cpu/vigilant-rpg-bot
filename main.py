import discord
from discord import app_commands

from bot.runtime import *

# ==============================
# DISCORD
# ==============================

intents = discord.Intents.default()
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ==============================
# COMANDOS — JOGADOR
# ==============================

@tree.command(name="ping", description="Ver se o bot está vivo.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("👁️ **Vigillant está online.**", ephemeral=True)

@tree.command(name="start", description="Criar personagem (menu de classes).")
@only_channel(CANAL_BEM_VINDO_ID, "bem-vindo")
async def start(interaction: discord.Interaction):
    existing = await get_player(interaction.user.id)
    if existing:
        await interaction.response.send_message("⚠️ Você já tem personagem. Use **/perfil**.", ephemeral=True)
        return

    embed = discord.Embed(
        title="👁️ PROTOCOLO DE SOBREVIVÊNCIA — VIGILLANT",
        description="Escolha sua classe para entrar nas **Terras da Diretriz**.",
        color=discord.Color.dark_grey()
    )
    for cls, st in CLASSES.items():
        embed.add_field(
            name=f"🔹 {cls.capitalize()}",
            value=f"❤ {st['hp_base']} | 🔵 {st['mana_base']} | ⚔ {st['atk']} | ✨ {st['magia']} | 🛡 {st['defesa']}",
            inline=False
        )
    embed.set_footer(text="Depois use /perfil e leia o canal de comandos.")
    await interaction.response.send_message(embed=embed, view=ClasseView(), ephemeral=False)

@tree.command(name="perfil", description="Ver seu personagem.")
async def perfil(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return

    def fmt_item_name(item_id: Optional[str]) -> str:
        if not item_id:
            return "—"
        return item_id

    eq = ensure_equipado_format(p.get("equipado") or {})
    aneis = eq.get("aneis", [])
    linhas_aneis = []
    for i in range(8):
        linhas_aneis.append(f"{i+1}. {fmt_item_name(aneis[i] if i < len(aneis) else None)}")

    atk = await total_stat(p, "atk")
    defesa = await total_stat(p, "defesa")
    magia = await total_stat(p, "magia")
    dex = await total_stat(p, "destreza")
    sorte = await total_stat(p, "sorte")
    furt = await total_stat(p, "furtividade")

    embed = discord.Embed(title=f"👤 Perfil — {interaction.user.display_name}", color=discord.Color.blue())
    embed.add_field(name="Classe", value=str(p["classe"]).capitalize(), inline=True)
    embed.add_field(name="Nível", value=f"{p['level']} (XP {p['xp']}/{xp_para_upar(int(p['level']))})", inline=True)
    embed.add_field(name="Gold", value=f"💰 {p['gold']}", inline=True)

    embed.add_field(
        name="Status",
        value=(
            f"❤ HP: **{p['hp']}**\n"
            f"🔵 Mana: **{p['mana']}**\n"
            f"🥵 Stamina: **{p['stamina']}/{p['max_stamina']}**\n"
            f"⭐ Pontos pendentes: **{p.get('pontos', 0)}**"
        ),
        inline=True
    )

    embed.add_field(
        name="Atributos (com bônus)",
        value=(
            f"⚔ ATK: **{atk}**\n"
            f"🛡 DEF: **{defesa}**\n"
            f"✨ MAG: **{magia}**\n"
            f"🎯 DEX: **{dex}**\n"
            f"🍀 SORTE: **{sorte}**\n"
            f"🕶 FURT: **{furt}**"
        ),
        inline=True
    )

    embed.add_field(
        name="Equipado (IDs)",
        value=(
            f"🗡 Arma: **{fmt_item_name(eq.get('arma'))}**\n"
            f"🛡 Armadura: **{fmt_item_name(eq.get('armadura'))}**\n"
            f"🪖 Elmo: **{fmt_item_name(eq.get('elmo'))}**\n"
            f"👢 Botas: **{fmt_item_name(eq.get('botas'))}**\n"
            f"🧤 Luvas: **{fmt_item_name(eq.get('luvas'))}**\n"
            f"🪄 Cajado: **{fmt_item_name(eq.get('cajado'))}**\n"
            f"🧩 Especial: **{fmt_item_name(eq.get('especial'))}**\n"
            f"🧬 Implante: **{fmt_item_name(eq.get('implante'))}**\n"
            f"📖 Livro (item): **{fmt_item_name(eq.get('livro_magias'))}**"
        ),
        inline=False
    )

    embed.add_field(name="💍 Anéis (1–8)", value="\n".join(linhas_aneis), inline=False)

    if can_use_spellbook(p["classe"]):
        spells = p.get("spellbook", []) or []
        if spells:
            embed.add_field(
                name=f"📖 Livro de Magias (até {SPELLBOOK_SLOTS})",
                value="\n".join([f"• `{sid}`" for sid in spells[:SPELLBOOK_SLOTS]]),
                inline=False
            )
        else:
            embed.add_field(name=f"📖 Livro de Magias (até {SPELLBOOK_SLOTS})", value="_vazio_", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="comandos", description="Lista resumida de comandos.")
@only_channel(CANAL_COMANDOS_ID, "comandos-dos-players")
async def comandos(interaction: discord.Interaction):
    txt = (
        "👁️ **COMANDOS — RPG VIGILLANT (V2)**\n\n"
        "**🎮 Jogadores**\n"
        "• **/start** (somente no canal de início)\n"
        "• **/perfil**\n"
        "• **/cacar** (somente na sala de caçar)\n"
        "• **/descansar** (12h inativo)\n"
        "• **/albergue** (cura pagando gold)\n"
        "• **/loja** **/comprar** **/vender** **/inventario** **/equipar** **/desequipar** **/desequiparanel** **/usar** (somente na loja)\n"
        "• **/upar** (atributos)\n"
        "• **/enviargold** • **/doaritem**\n"
        "• **/magias** (listar) • **/livro_equipar** • **/livro_desequipar** (mago/clérigo)\n\n"
        "**👑 Mestre** (canal do mestre)\n"
        "• **/narracao on|off**\n"
        "• **/darxp** • **/dargold** • **/daritem** (inclui all e todos_exceto)\n"
        "• **/item_criar** • **/item_editar** • **/item_excluir** • **/loja_add** • **/loja_remove** • **/loja_set**\n"
        "• **/bau_add** • **/bau_remove** • **/bau_listar** • **/bau_dar**\n"
        "• **/magia_criar** • **/magia_editar** • **/magia_excluir**\n"
        "• **/mdano** • **/mcurar** • **/mstatus** • **/resetar** • **/setlevel**\n"
    )
    await interaction.response.send_message(txt, ephemeral=True)

# Loja
@tree.command(name="loja", description="Ver itens ativos na loja (paginado).")
@only_channel(CANAL_LOJA_ID, "loja")
async def loja_cmd(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return
    await interaction.response.send_message(embed=await build_loja_embed(0), view=LojaView(interaction.user.id, 0), ephemeral=True)

@tree.command(name="inventario", description="Ver seu inventário.")
@only_channel(CANAL_LOJA_ID, "loja")
async def inventario(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return
    inv = p.get("inventario") or []
    if not inv:
        await interaction.response.send_message("🎒 Inventário vazio.", ephemeral=True)
        return

    linhas = []
    for item_id in inv[:60]:
        it = await item_get(item_id)
        if not it or int(it.get("deleted", 0)) == 1:
            nm = f"{item_id} (REMOVIDO)"
        else:
            nm = it.get("nome", item_id)
        linhas.append(f"• `{item_id}` — {nm}")

    await interaction.response.send_message("🎒 **Seu inventário:**\n" + "\n".join(linhas), ephemeral=True)

@tree.command(name="comprar", description="Comprar item ativo da loja.")
@only_channel(CANAL_LOJA_ID, "loja")
@app_commands.describe(item_id="ID do item")
async def comprar(interaction: discord.Interaction, item_id: str):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return

    item_id = item_id.lower().strip()
    if not await shop_is_active(item_id):
        await interaction.response.send_message("❌ Item não está ativo na loja.", ephemeral=True)
        return

    it = await item_get(item_id)
    if not it or int(it.get("deleted", 0)) == 1:
        await interaction.response.send_message("❌ Item não existe (ou foi removido).", ephemeral=True)
        return

    # preço atual
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT i.preco_base, s.preco as preco_loja
            FROM items i JOIN shop_items s ON s.item_id=i.item_id
            WHERE i.item_id=? AND s.ativo=1 AND i.deleted=0
        """, (item_id,))
        row = await cur.fetchone()
        if not row:
            await interaction.response.send_message("❌ Item não está ativo.", ephemeral=True)
            return
        preco = int(row["preco_loja"]) if row["preco_loja"] is not None else int(row["preco_base"])

    if int(p["gold"]) < preco:
        await interaction.response.send_message("❌ Gold insuficiente.", ephemeral=True)
        return

    allowed = it.get("classes") or []
    if allowed and p["classe"] not in allowed:
        await interaction.response.send_message(f"❌ Apenas para: {', '.join(allowed)}", ephemeral=True)
        return

    if not await shop_decrease_stock(item_id, 1):
        await interaction.response.send_message("❌ Sem estoque.", ephemeral=True)
        return

    p["gold"] -= preco
    p.setdefault("inventario", []).append(item_id)
    await save_player(p)

    await interaction.response.send_message(f"✅ Comprou **{it['nome']}** por **{preco}** gold.", ephemeral=True)

@tree.command(name="vender", description="Vender item do inventário (60% do preço base).")
@only_channel(CANAL_LOJA_ID, "loja")
@app_commands.describe(item_id="ID do item")
async def vender(interaction: discord.Interaction, item_id: str):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return

    item_id = item_id.lower().strip()
    inv = p.get("inventario") or []
    if item_id not in inv:
        await interaction.response.send_message("❌ Você não tem esse item.", ephemeral=True)
        return

    it = await item_get(item_id)
    if not it or int(it.get("deleted", 0)) == 1:
        # item removido do mundo — não vende
        inv.remove(item_id)
        p["inventario"] = inv
        await save_player(p)
        await interaction.response.send_message("⚠️ Esse item foi removido do mundo. Ele desapareceu do seu inventário.", ephemeral=True)
        return

    preco_base = int(it.get("preco_base", 0))
    if preco_base <= 0:
        await interaction.response.send_message("❌ Este item não pode ser vendido.", ephemeral=True)
        return

    ganho = int(math.floor(preco_base * 0.6))
    inv.remove(item_id)
    p["inventario"] = inv
    p["gold"] += ganho
    await save_player(p)

    await interaction.response.send_message(f"💰 Vendeu **{it['nome']}** por **{ganho}** gold (60%).", ephemeral=True)

@tree.command(name="equipar", description="Equipar item (usa o slot do item).")
@only_channel(CANAL_LOJA_ID, "loja")
@app_commands.describe(item_id="ID do item")
async def equipar(interaction: discord.Interaction, item_id: str):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return

    item_id = item_id.lower().strip()
    inv = p.get("inventario") or []
    if item_id not in inv:
        await interaction.response.send_message("❌ Você não possui este item.", ephemeral=True)
        return

    it = await item_get(item_id)
    if not it or int(it.get("deleted", 0)) == 1:
        inv.remove(item_id)
        p["inventario"] = inv
        await save_player(p)
        await interaction.response.send_message("⚠️ Esse item foi removido do mundo. Ele desapareceu do seu inventário.", ephemeral=True)
        return

    allowed = it.get("classes") or []
    if allowed and p["classe"] not in allowed:
        await interaction.response.send_message(f"❌ Apenas para: {', '.join(allowed)}", ephemeral=True)
        return

    slot = (it.get("slot") or it.get("tipo") or "").lower().strip()
    if not slot:
        await interaction.response.send_message("❌ Item sem slot definido.", ephemeral=True)
        return

    p["equipado"] = ensure_equipado_format(p.get("equipado") or {})

    # anel = primeiro espaço vazio
    if slot == "anel":
        aneis = p["equipado"].get("aneis", [])
        try:
            idx = aneis.index(None)
        except ValueError:
            await interaction.response.send_message("❌ Você já está com 8 anéis equipados.", ephemeral=True)
            return
        aneis[idx] = item_id
        p["equipado"]["aneis"] = aneis
        await save_player(p)
        await interaction.response.send_message(f"💍 Equipou **{it['nome']}** no anel #{idx+1}.", ephemeral=True)
        return

    allowed_slots = {"arma","armadura","elmo","botas","luvas","cajado","especial","implante","livro_magias"}
    if slot not in allowed_slots:
        await interaction.response.send_message("❌ Este item não pode ser equipado.", ephemeral=True)
        return

    # implante e livro_magias podem ser mestre-only se quiser travar
    if slot == "implante" and not eh_mestre(interaction.user.id):
        await interaction.response.send_message("❌ Implantes só podem ser aplicados pelo Mestre.", ephemeral=True)
        return

    p["equipado"][slot] = item_id
    await save_player(p)
    await interaction.response.send_message(f"⚙️ Equipou **{it['nome']}** no slot **{slot}**.", ephemeral=True)

@tree.command(name="desequipar", description="Desequipar um slot.")
@only_channel(CANAL_LOJA_ID, "loja")
@app_commands.describe(slot="arma|armadura|elmo|botas|luvas|cajado|especial|implante|livro_magias")
async def desequipar(interaction: discord.Interaction, slot: str):
    p = await require_player(interaction)
    if not p:
        return

    slot = slot.lower().strip()
    allowed_slots = {"arma","armadura","elmo","botas","luvas","cajado","especial","implante","livro_magias"}
    if slot not in allowed_slots:
        await interaction.response.send_message("❌ Slot inválido.", ephemeral=True)
        return

    if slot == "implante" and not eh_mestre(interaction.user.id):
        await interaction.response.send_message("❌ Implantes só podem ser removidos pelo Mestre.", ephemeral=True)
        return

    p["equipado"] = ensure_equipado_format(p.get("equipado") or {})
    if not p["equipado"].get(slot):
        await interaction.response.send_message("⚠️ Nada equipado nesse slot.", ephemeral=True)
        return

    item_id = p["equipado"][slot]
    p["equipado"][slot] = None
    await save_player(p)

    await interaction.response.send_message(f"✅ Desequipou `{item_id}` do slot **{slot}**.", ephemeral=True)

@tree.command(name="desequiparanel", description="Desequipar um anel (posição 1 a 8).")
@only_channel(CANAL_LOJA_ID, "loja")
@app_commands.describe(posicao="1 a 8")
async def desequiparanel(interaction: discord.Interaction, posicao: int):
    p = await require_player(interaction)
    if not p:
        return

    if posicao < 1 or posicao > 8:
        await interaction.response.send_message("❌ Posição inválida. Use 1 a 8.", ephemeral=True)
        return

    p["equipado"] = ensure_equipado_format(p.get("equipado") or {})
    idx = posicao - 1
    aneis = p["equipado"].get("aneis", [])
    item_id = aneis[idx] if idx < len(aneis) else None

    if not item_id:
        await interaction.response.send_message(f"⚠️ Não há anel equipado na posição {posicao}.", ephemeral=True)
        return

    aneis[idx] = None
    p["equipado"]["aneis"] = aneis
    await save_player(p)

    await interaction.response.send_message(f"✅ Desequipou `{item_id}` do anel #{posicao}.", ephemeral=True)

@tree.command(name="usar", description="Usar consumível do inventário.")
@only_channel(CANAL_LOJA_ID, "loja")
@app_commands.describe(item_id="ID do item")
async def usar(interaction: discord.Interaction, item_id: str):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return

    item_id = item_id.lower().strip()
    inv = p.get("inventario") or []
    if item_id not in inv:
        await interaction.response.send_message("❌ Você não tem este item.", ephemeral=True)
        return

    it = await item_get(item_id)
    if not it or int(it.get("deleted", 0)) == 1:
        inv.remove(item_id)
        p["inventario"] = inv
        await save_player(p)
        await interaction.response.send_message("⚠️ Esse item foi removido do mundo. Ele desapareceu do seu inventário.", ephemeral=True)
        return

    if (it.get("tipo") or "").lower() != "consumivel":
        await interaction.response.send_message("❌ Este item não é consumível.", ephemeral=True)
        return

    eff = it.get("efeito", {}) or {}
    if "hp" in eff:
        p["hp"] += int(eff["hp"])
    if "mana" in eff:
        p["mana"] += int(eff["mana"])
    if "stamina" in eff:
        p["stamina"] = min(int(p["max_stamina"]), int(p["stamina"]) + int(eff["stamina"]))

    inv.remove(item_id)
    p["inventario"] = inv
    await save_player(p)

    eff_txt = ", ".join([f"{k}+{v}" for k, v in eff.items()]) if eff else "—"
    await interaction.response.send_message(f"🧪 Usou **{it['nome']}** ({eff_txt}).", ephemeral=True)

# Upar atributos (SEM hp_base/mana_base e sem stamina)
@tree.command(name="upar", description="Distribuir pontos pendentes em atributos.")
@app_commands.describe(atributo="atk|defesa|magia|sorte|furtividade|destreza", quantidade="quantos pontos")
async def upar(interaction: discord.Interaction, atributo: str, quantidade: int):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return

    if quantidade <= 0:
        await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)
        return

    atributo = atributo.lower().strip()
    allowed = {"atk","defesa","magia","sorte","furtividade","destreza"}
    if atributo not in allowed:
        await interaction.response.send_message("❌ Atributo inválido.", ephemeral=True)
        return

    pontos = int(p.get("pontos", 0))
    if pontos < quantidade:
        await interaction.response.send_message(f"❌ Você tem apenas **{pontos}** pontos.", ephemeral=True)
        return

    p["stats"][atributo] = int(p["stats"].get(atributo, 0)) + quantidade
    p["pontos"] = pontos - quantidade
    await save_player(p)

    await interaction.response.send_message(f"✅ Upou **{atributo}** (+{quantidade}). Pontos restantes: **{p['pontos']}**", ephemeral=True)

# Trade
@tree.command(name="enviargold", description="Enviar gold para outro jogador.")
@app_commands.describe(membro="Quem recebe", quantidade="quanto enviar")
async def enviargold(interaction: discord.Interaction, membro: discord.Member, quantidade: int):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return
    if quantidade <= 0:
        await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)
        return
    if int(p["gold"]) < quantidade:
        await interaction.response.send_message("❌ Você não tem gold suficiente.", ephemeral=True)
        return

    alvo = await get_player(membro.id)
    if not alvo:
        await interaction.response.send_message("❌ O alvo não tem personagem.", ephemeral=True)
        return

    p["gold"] -= quantidade
    alvo["gold"] += quantidade
    await save_player(p)
    await save_player(alvo)

    await interaction.response.send_message(f"💰 Você enviou **{quantidade}** gold para {membro.mention}.", ephemeral=True)

@tree.command(name="doaritem", description="Doar item do inventário para outro jogador.")
@app_commands.describe(membro="Quem recebe", item_id="ID do item")
async def doaritem(interaction: discord.Interaction, membro: discord.Member, item_id: str):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return

    alvo = await get_player(membro.id)
    if not alvo:
        await interaction.response.send_message("❌ O alvo não tem personagem.", ephemeral=True)
        return

    item_id = item_id.lower().strip()
    inv = p.get("inventario") or []
    if item_id not in inv:
        await interaction.response.send_message("❌ Você não tem esse item.", ephemeral=True)
        return

    # se item foi removido, ele some
    it = await item_get(item_id)
    if not it or int(it.get("deleted", 0)) == 1:
        inv.remove(item_id)
        p["inventario"] = inv
        await save_player(p)
        await interaction.response.send_message("⚠️ Esse item foi removido do mundo. Ele desapareceu.", ephemeral=True)
        return

    inv.remove(item_id)
    p["inventario"] = inv
    alvo.setdefault("inventario", []).append(item_id)

    await save_player(p)
    await save_player(alvo)
    await interaction.response.send_message(f"🎁 Você doou `{item_id}` para {membro.mention}.", ephemeral=True)

# Descansar / Albergue
@tree.command(name="descansar", description="Descansar: 12h inativo, recupera stamina e garante HP/Mana mínimos.")
async def descansar(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return

    p["rest_until_ts"] = now_ts() + DESCANSO_HORAS * 3600
    p["stamina"] = int(p["max_stamina"])

    # Garantir pelo menos o "base" atual (não reduz)
    p["hp"] = max(int(p["hp"]), int(p["stats"].get("hp_base", 1)))
    p["mana"] = max(int(p["mana"]), int(p["stats"].get("mana_base", 0)))

    await save_player(p)
    await interaction.response.send_message(f"⛺ Descanso iniciado. Você ficará inativo por **{DESCANSO_HORAS}h**.", ephemeral=True)

@tree.command(name="albergue", description="Descanso pago: recupera HP/Mana/Stamina proporcional (até 50 gold).")
async def albergue(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return

    # custo proporcional: quanto falta para “cheio”, mais paga, até ALBERGUE_MAX_CUSTO
    # Aqui “cheio” = HP e Mana atuais (não temos max separado), então usamos um alvo simples:
    # alvo_hp = stats.hp_base + level*1 (mínimo), alvo_mana = stats.mana_base + level*1 (mínimo)
    # (Se quiser max reais, dá pra adicionar depois)
    lvl = int(p["level"])
    alvo_hp = int(p["stats"].get("hp_base", p["hp"])) + lvl
    alvo_mana = int(p["stats"].get("mana_base", p["mana"])) + lvl
    alvo_stam = int(p["max_stamina"])

    falta_hp = max(0, alvo_hp - int(p["hp"]))
    falta_mana = max(0, alvo_mana - int(p["mana"]))
    falta_stam = max(0, alvo_stam - int(p["stamina"]))

    # peso do que falta (stamina pesa menos)
    score = falta_hp + falta_mana + (falta_stam * 0.5)
    if score <= 0:
        await interaction.response.send_message("🏨 Você já está bem. Não precisa do albergue.", ephemeral=True)
        return

    # paga proporcional até o máximo
    custo = min(ALBERGUE_MAX_CUSTO, max(5, int(round(score / 10))))
    if int(p["gold"]) < custo:
        await interaction.response.send_message(f"❌ Você precisa de **{custo} gold** (você tem {p['gold']}).", ephemeral=True)
        return

    p["gold"] -= custo
    # recupera tudo até os alvos
    p["hp"] = max(int(p["hp"]), alvo_hp)
    p["mana"] = max(int(p["mana"]), alvo_mana)
    p["stamina"] = alvo_stam

    await save_player(p)
    await interaction.response.send_message(
        f"🏨 **Albergue**\n"
        f"Pagou **{custo} gold**.\n"
        f"❤ HP: **{p['hp']}** | 🔵 Mana: **{p['mana']}** | 🥵 Stamina: **{p['stamina']}/{p['max_stamina']}**\n"
        f"💰 Gold restante: **{p['gold']}**",
        ephemeral=True
    )

# ==============================
# MAGIAS (Jogador) — Livro de Magias
# ==============================

@tree.command(name="magias", description="Listar magias que você conhece.")
async def magias(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return

    known = p.get("known_spells") or []
    if not known:
        await interaction.response.send_message("📖 Você ainda não aprendeu nenhuma magia. Use **/escola**.", ephemeral=True)
        return

    lines = []
    for sid in known[:80]:
        s = await spell_get(sid)
        if not s or int(s.get("deleted", 0)) == 1:
            continue
        lines.append(f"• `{sid}` — **{s['nome']}** (mana {s['custo_mana']}, {s['efeito_tipo']} {s['efeito_valor']})")

    if not lines:
        await interaction.response.send_message("📖 Suas magias foram removidas do mundo.", ephemeral=True)
        return

    await interaction.response.send_message("📖 **Magias conhecidas:**\n" + "\n".join(lines), ephemeral=True)

@tree.command(name="livro_equipar", description="Equipar magia no livro (mago/clérigo).")
@app_commands.describe(spell_id="ID da magia")
async def livro_equipar(interaction: discord.Interaction, spell_id: str):
    p = await require_player(interaction)
    if not p:
        return

    if not can_use_spellbook(p["classe"]):
        await interaction.response.send_message("❌ Sua classe não usa livro de magias.", ephemeral=True)
        return

    # regra: somente fora de combate/narração OFF
    if narration_is_on(interaction):
        await interaction.response.send_message("❌ Não é possível trocar o livro com **NARRAÇÃO ON**.", ephemeral=True)
        return

    spell_id = spell_id.lower().strip()
    s = await spell_get(spell_id)
    if not s or int(s.get("deleted", 0)) == 1:
        await interaction.response.send_message("❌ Magia não existe (ou foi removida).", ephemeral=True)
        return

    classes = s.get("classes") or []
    if p["classe"] not in classes:
        await interaction.response.send_message(
            f"❌ Essa magia não é para sua classe. Permitidas: {', '.join(classes)}",
            ephemeral=True
        )
        return

    book = p.get("spellbook") or []
    if spell_id in book:
        await interaction.response.send_message("⚠️ Essa magia já está no seu livro.", ephemeral=True)
        return
    if len(book) >= SPELLBOOK_SLOTS:
        await interaction.response.send_message(
            f"❌ Seu livro está cheio (máx {SPELLBOOK_SLOTS}). Desequipe uma primeiro.",
            ephemeral=True
        )
        return

    book.append(spell_id)
    p["spellbook"] = book
    await save_player(p)

    await interaction.response.send_message(
        f"✅ Equipou **{s['nome']}** no livro.",
        ephemeral=True
    )

@tree.command(name="livro_desequipar", description="Desequipar magia do livro (mago/clérigo).")
@app_commands.describe(spell_id="ID da magia")
async def livro_desequipar(interaction: discord.Interaction, spell_id: str):
    p = await require_player(interaction)
    if not p:
        return

    # classe pode usar livro?
    if not can_use_spellbook(p.get("classe", "")):
        await interaction.response.send_message("❌ Sua classe não usa livro de magias.", ephemeral=True)
        return

    # trava em narração
    if narration_is_on(interaction):
        await interaction.response.send_message("❌ Não é possível trocar o livro com **NARRAÇÃO ON**.", ephemeral=True)
        return

    spell_id = spell_id.lower().strip()

    # garante formato lista mesmo em saves antigos
    book = p.get("spellbook", [])
    if isinstance(book, str):
        try:
            book = json.loads(book)
        except Exception:
            book = []
    if not isinstance(book, list):
        book = []

    if spell_id not in book:
        await interaction.response.send_message("⚠️ Essa magia não está no seu livro.", ephemeral=True)
        return

    book.remove(spell_id)
    p["spellbook"] = book

    await save_player(p)
    await interaction.response.send_message(f"✅ Removeu `{spell_id}` do livro.", ephemeral=True)

# ==============================
# /CACAR — D20 AUTOMÁTICO
# ==============================

@tree.command(name="cacar", description="Caçar nas terras da Diretriz.")
async def cacar(interaction: discord.Interaction):

    # ------------------------
    # Bloqueios iniciais
    # ------------------------

    if await blocked_by_narration(interaction):
        return

    p = await require_player(interaction)
    if not p:
        return

    if await blocked_by_rest(interaction, p):
        return

    now = now_ts()
    last = int(p.get("last_hunt_ts", 0))

    if now - last < CACAR_COOLDOWN_S:
        await interaction.response.send_message("⏳ Você precisa esperar para caçar novamente.", ephemeral=True)
        return

    if int(p["stamina"]) < STAMINA_CUSTO_CACAR:
        await interaction.response.send_message("🥵 Stamina insuficiente.", ephemeral=True)
        return

    # desconta stamina
    p["stamina"] -= STAMINA_CUSTO_CACAR
    p["last_hunt_ts"] = now

    # ------------------------
    # 38% - Inimigo fraco
    # ------------------------

    if random.random() < INIMIGOS_FRACOS_CHANCE:

        inimigo = random.choice(INIMIGOS_FRACOS)

        xp_gain = random.randint(*inimigo["xp"])
        gold_gain = random.randint(*inimigo["gold"])

        drop_txt = ""

        # 4% chance drop fraco
        if random.random() < DROP_FRACO_CHANCE:
            drop_item = await pick_drop_from_pool(DROP_POOL_FRACO)
            if drop_item:
                p.setdefault("inventario", []).append(drop_item["item_id"])
                drop_txt = f"\n🎁 Drop: **{drop_item['nome']}**"

        p["xp"] += xp_gain
        p["gold"] += gold_gain

        upou = await try_auto_level(p)
        await save_player(p)

        embed = discord.Embed(
            title="⚔️ CAÇADA — VIGILLANT",
            description=(
                f"👹 Alvo: **{inimigo['nome']}**\n"
                f"🎲 Abate fácil.\n\n"
                f"❤ HP: **{p['hp']}** | 🥵 Stamina: **{p['stamina']}/{p['max_stamina']}**"
            ),
            color=discord.Color.orange()
        )

        embed.add_field(
            name="🏆 Vitória",
            value=f"✨ +{xp_gain} XP | 💰 +{gold_gain} Gold{drop_txt}",
            inline=False
        )

        if upou:
            embed.add_field(
                name="🆙 LEVEL UP",
                value=f"Você upou **{upou}** nível(is)!",
                inline=False
            )

        await interaction.response.send_message(embed=embed)
        return

    # ------------------------
    # Sorteio normal ponderado
    # ------------------------

    ids = list(MONSTROS.keys())
    pesos = [MONSTROS[i]["peso"] for i in ids]
    mob_id = random.choices(ids, weights=pesos, k=1)[0]
    m = MONSTROS[mob_id]

    d20 = rolar_d20()
    dano = d20  # você pode adaptar para seu cálculo real

    defesa = 0
    dano_monstro = max(0, int(m["atk"]) - defesa)

    mob_hp = int(m["hp"]) - dano
    tomou = dano_monstro if mob_hp > 0 else 0
    p["hp"] = max(0, int(p["hp"]) - tomou)

    ganhou = (mob_hp <= 0 and dano > 0)

    xp_gain = int(m["xp"])
    gold_gain = int(m["gold"])

    if dano == 0:
        xp_gain //= 3
        gold_gain //= 3

    drop_txt = ""

    if ganhou:
        p["xp"] += xp_gain
        p["gold"] += gold_gain

        # raro = peso <= 4
        if int(m.get("peso", 99)) <= 4 and random.random() < DROP_RARO_CHANCE:
            drop_item = await pick_drop_from_pool(DROP_POOL_RARO)
            if drop_item:
                p.setdefault("inventario", []).append(drop_item["item_id"])
                drop_txt = f"\n🎁 Drop Raro: **{drop_item['nome']}**"

    upou = await try_auto_level(p)
    await save_player(p)

    embed = discord.Embed(
        title="⚔️ CAÇADA — VIGILLANT",
        description=(
            f"👹 Alvo: **{m['nome']}**\n"
            f"🎲 D20: **{d20}**\n\n"
            f"⚔️ Dano causado: **{dano}**\n"
            f"💥 Dano recebido: **{tomou}**\n\n"
            f"❤ HP: **{p['hp']}** | 🥵 Stamina: **{p['stamina']}/{p['max_stamina']}**"
        ),
        color=discord.Color.orange()
    )

    if ganhou:
        embed.add_field(
            name="🏆 Vitória",
            value=f"✨ +{xp_gain} XP | 💰 +{gold_gain} Gold{drop_txt}",
            inline=False
        )
    else:
        embed.add_field(
            name="⚠️ Resultado",
            value="O alvo resistiu / você falhou. Reorganize-se e tente novamente.",
            inline=False
        )

    if upou:
        embed.add_field(
            name="🆙 LEVEL UP",
            value=f"Você upou **{upou}** nível(is)!",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

# ==============================
# COMANDOS — MESTRE
# ==============================

@tree.command(
    name="narracao",
    description="(Mestre) Ativar/desativar modo narração (pausa /cacar e trava livro)."
)
@only_master_channel()
@app_commands.describe(modo="on ou off")
async def narracao(interaction: discord.Interaction, modo: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ Use em servidor.", ephemeral=True)
        return

    modo = (modo or "").lower().strip()
    if modo not in ["on", "off"]:
        await interaction.response.send_message("❌ Use on/off.", ephemeral=True)
        return

    NARRACAO_GUILD[interaction.guild.id] = (modo == "on")
    await interaction.response.send_message(
        f"📖 Modo narração: **{modo.upper()}**",
        ephemeral=False
    )


# ---------- DAR XP / GOLD (individual / all / todos_exceto)

async def list_all_player_ids() -> List[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT user_id FROM players")
        rows = await cur.fetchall()
        return [int(r[0]) for r in rows]
@tree.command(name="spawn", description="(Mestre) Criar/Recriar personagem sem /start (classe, nível, stats e itens).")
@only_master_channel()
@app_commands.describe(
    membro="Jogador",
    classe="clerigo | barbaro | arqueiro | mago | assassino | guerreiro",
    nivel="Nível",
    gold="Gold",
    xp="XP",
    atk="ATK (opcional)",
    defesa="DEFESA (opcional)",
    magia="MAGIA (opcional)",
    sorte="SORTE (opcional)",
    furtividade="FURTIVIDADE (opcional)",
    destreza="DESTREZA (opcional)",
    itens="Inventário CSV (ex: pocao_vida, anel_arcano)",
    sobrescrever="sim para apagar e recriar do zero"
)
async def spawn(
    interaction: discord.Interaction,
    membro: discord.Member,
    classe: str,
    nivel: int = 1,
    gold: int = 100,
    xp: int = 0,
    atk: Optional[int] = None,
    defesa: Optional[int] = None,
    magia: Optional[int] = None,
    sorte: Optional[int] = None,
    furtividade: Optional[int] = None,
    destreza: Optional[int] = None,
    itens: str = "",
    sobrescrever: str = "nao",
):
    classe = (classe or "").lower().strip()
    if classe not in CLASSES:
        await interaction.response.send_message(f"❌ Classe inválida. Use: {', '.join(CLASSES.keys())}", ephemeral=True)
        return

    # sobrescrever?
    do_reset = (sobrescrever or "nao").lower().strip() in ["sim", "s", "yes", "y", "true", "1"]
    if do_reset:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("DELETE FROM players WHERE user_id=?", (membro.id,))
            await db.commit()

    # existe?
    p = await get_player(membro.id)
    if not p:
        p = build_new_player(membro.id, classe)

    # aplica classe e base
    p["classe"] = classe
    base_stats = CLASSES[classe].copy()

    # overrides se vierem
    if atk is not None: base_stats["atk"] = int(atk)
    if defesa is not None: base_stats["defesa"] = int(defesa)
    if magia is not None: base_stats["magia"] = int(magia)
    if sorte is not None: base_stats["sorte"] = int(sorte)
    if furtividade is not None: base_stats["furtividade"] = int(furtividade)
    if destreza is not None: base_stats["destreza"] = int(destreza)

    p["stats"] = base_stats

    # set nível/xp/gold
    p["level"] = max(1, int(nivel))
    p["xp"] = max(0, int(xp))
    p["gold"] = max(0, int(gold))

    # hp/mana mínimos (não deixa zerar)
    p["hp"] = max(int(p.get("hp", 1)), int(p["stats"].get("hp_base", 1)))
    p["mana"] = max(int(p.get("mana", 0)), int(p["stats"].get("mana_base", 0)))

    # inventário
    if itens:
        inv_add = [x.strip().lower() for x in itens.split(",") if x.strip()]
        p.setdefault("inventario", [])
        added = 0
        for item_id in inv_add:
            if item_id in LOJA:
                p["inventario"].append(item_id)
                added += 1
    else:
        added = 0

    # equipado normalizado
    p.setdefault("equipado", {})
    p["equipado"] = ensure_equipado_format(p["equipado"])

    await save_player(p)

    await interaction.response.send_message(
        "✅ **Spawn concluído**\n"
        f"Jogador: {membro.mention}\n"
        f"Classe: **{classe}** | Nível: **{p['level']}** | XP: **{p['xp']}** | Gold: **{p['gold']}**\n"
        f"Itens adicionados: **{added}**",
        ephemeral=False
    )

@tree.command(name="darxp", description="(Mestre) Dar XP (jogador | all | todos_exceto).")
@only_master_channel()
@app_commands.describe(
    alvo="Mencione um jogador, ou digite 'all' ou 'todos_exceto'",
    quantidade="Quantidade de XP",
    exceto="Se alvo for 'todos_exceto', informe o jogador a excluir"
)
async def darxp(
    interaction: discord.Interaction,
    alvo: str,
    quantidade: int,
    exceto: Optional[discord.Member] = None
):
    if quantidade <= 0:
        await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)
        return

    alvo_norm = (alvo or "").lower().strip()

    # ------------------------
    # ALL
    # ------------------------
    if alvo_norm == "all":
        ids = await list_all_player_ids()
        total = 0
        ups: List[str] = []

        for uid in ids:
            p = await get_player(uid)
            if not p:
                continue

            p["xp"] += quantidade
            upou = await try_auto_level(p)
            await save_player(p)
            total += 1

            if upou:
                ups.append(f"<@{uid}> (+{upou})")

        msg = f"👑 Mestre deu **{quantidade} XP** para **{total}** jogadores (ALL)."
        if ups:
            msg += "\n🆙 Uparam: " + ", ".join(ups[:20]) + ("…" if len(ups) > 20 else "")

        await interaction.response.send_message(msg, ephemeral=False)
        return

    # ------------------------
    # TODOS_EXCETO
    # ------------------------
    if alvo_norm == "todos_exceto":
        if not exceto:
            await interaction.response.send_message(
                "❌ Use: /darxp alvo:todos_exceto quantidade:X exceto:@Fulano",
                ephemeral=True
            )
            return

        ids = await list_all_player_ids()
        total = 0
        ups: List[str] = []

        for uid in ids:
            if uid == exceto.id:
                continue

            p = await get_player(uid)
            if not p:
                continue

            p["xp"] += quantidade
            upou = await try_auto_level(p)
            await save_player(p)
            total += 1

            if upou:
                ups.append(f"<@{uid}> (+{upou})")

        msg = f"👑 Mestre deu **{quantidade} XP** para **{total}** jogadores (todos exceto {exceto.mention})."
        if ups:
            msg += "\n🆙 Uparam: " + ", ".join(ups[:20]) + ("…" if len(ups) > 20 else "")

        await interaction.response.send_message(msg, ephemeral=False)
        return

    # ------------------------
    # JOGADOR INDIVIDUAL (mencionar)
    # ------------------------
    # Aqui você pode decidir o formato: alvo pode ser "<@id>" ou nome.
    # Vou suportar "<@id>" e "<@!id>" (mencionar no Discord).
    alvo_txt = (alvo or "").strip()
    uid = None
    if alvo_txt.startswith("<@") and alvo_txt.endswith(">"):
        alvo_txt = alvo_txt.replace("<@", "").replace(">", "").replace("!", "")
        if alvo_txt.isdigit():
            uid = int(alvo_txt)

    if uid is None:
        await interaction.response.send_message(
            "❌ Para alvo individual, mencione o jogador (ex: `<@123>`), ou use 'all' / 'todos_exceto'.",
            ephemeral=True
        )
        return

    p = await get_player(uid)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return

    p["xp"] += quantidade
    upou = await try_auto_level(p)
    await save_player(p)

    await interaction.response.send_message(
        f"👑 Mestre deu **{quantidade} XP** para <@{uid}>."
        + (f" 🆙 (upou {upou}x)" if upou else ""),
        ephemeral=False
    )

@tree.command(name="dargold", description="(Mestre) Dar gold (jogador | all | todos_exceto).")
@only_master_channel()
@app_commands.describe(
    alvo="Digite 'all' ou 'todos_exceto'",
    quantidade="Quantidade de gold (pode ser negativo)",
    exceto="Se alvo for 'todos_exceto', informe o jogador a excluir"
)
async def dargold(interaction: discord.Interaction, alvo: str, quantidade: int, exceto: Optional[discord.Member] = None):
    alvo = (alvo or "").lower().strip()

    if alvo == "all":
        ids = await list_all_player_ids()
        total = 0
        for uid in ids:
            p = await get_player(uid)
            if not p:
                continue
            p["gold"] = max(0, int(p["gold"]) + quantidade)
            await save_player(p)
            total += 1
        await interaction.response.send_message(f"💰 Gold ajustado em **{quantidade}** para **{total}** jogadores (ALL).", ephemeral=False)
        return

    if alvo == "todos_exceto":
        if not exceto:
            await interaction.response.send_message("❌ Use: /dargold alvo:todos_exceto quantidade:X exceto:@Fulano", ephemeral=True)
            return
        ids = await list_all_player_ids()
        total = 0
        for uid in ids:
            if uid == exceto.id:
                continue
            p = await get_player(uid)
            if not p:
                continue
            p["gold"] = max(0, int(p["gold"]) + quantidade)
            await save_player(p)
            total += 1
        await interaction.response.send_message(f"💰 Gold ajustado em **{quantidade}** para **{total}** jogadores (todos exceto {exceto.mention}).", ephemeral=False)
        return

    await interaction.response.send_message("❌ Use alvo: **all** ou **todos_exceto**. (Para individual, use /dargold_individual)", ephemeral=True)

@tree.command(name="dargold_individual", description="(Mestre) Dar/remover gold para 1 jogador.")
@only_master_channel()
async def dargold_individual(interaction: discord.Interaction, membro: discord.Member, quantidade: int):
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    p["gold"] = max(0, int(p["gold"]) + quantidade)
    await save_player(p)
    await interaction.response.send_message(f"💰 Gold ajustado em **{quantidade}** para {membro.mention}. (Agora {p['gold']})", ephemeral=False)

@tree.command(name="daritem", description="(Mestre) Dar item (direto no inventário).")
@only_master_channel()
async def daritem(interaction: discord.Interaction, membro: discord.Member, item_id: str, quantidade: int = 1):
    item_id = item_id.lower().strip()
    if quantidade <= 0:
        await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)
        return
    it = await item_get(item_id)
    if not it or int(it.get("deleted", 0)) == 1:
        await interaction.response.send_message("❌ Item não existe (ou foi removido).", ephemeral=True)
        return
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    p.setdefault("inventario", []).extend([item_id] * quantidade)
    await save_player(p)
    await interaction.response.send_message(f"🎁 Mestre deu **{it['nome']}** x{quantidade} para {membro.mention}.", ephemeral=False)

# ---------- ITENS: criar/editar/excluir + loja + baú
@tree.command(name="spell_criar", description="(Mestre) Criar/atualizar feitiço.")
@only_master_channel()
@app_commands.describe(
    spell_id="id unico ex: cura_maior",
    nome="nome exibido",
    custo_mana="custo em mana",
    preco="preço em gold",
    escola="arcano ou igreja",
    efeito_tipo="dano|cura|buff|util",
    efeito_valor="valor numérico",
    tags_json='JSON list ex: ["cibernético","radiação"]',
    classes_json='JSON list ex: ["mago"]',
    desc="descrição"
)
async def spell_criar(
    interaction: discord.Interaction,
    spell_id: str,
    nome: str,
    custo_mana: int,
    preco: int,
    escola: str,
    efeito_tipo: str,
    efeito_valor: int,
    tags_json: str = "",
    classes_json: str = "",
    desc: str = ""
):
    spell_id = spell_id.lower().strip()
    escola = (escola or "arcano").lower().strip()
    if escola not in ESCOLAS_SPELL:
        await interaction.response.send_message("❌ Escola inválida (arcano/igreja).", ephemeral=True)
        return

    s = {
        "nome": nome,
        "custo_mana": int(custo_mana),
        "preco": int(preco),
        "escola": escola,
        "efeito_tipo": (efeito_tipo or "util").lower().strip(),
        "efeito_valor": int(efeito_valor),
        "tags": parse_json_list(tags_json),
        "classes": parse_json_list(classes_json),
        "desc": desc
    }
    await spell_upsert(spell_id, s)
    await interaction.response.send_message(f"✅ Feitiço `{spell_id}` criado/atualizado.", ephemeral=True)


@tree.command(name="spell_ativar", description="(Mestre) Ativar feitiço na escola.")
@only_master_channel()
async def spell_ativar(interaction: discord.Interaction, spell_id: str):
    s = await spell_get(spell_id)
    if not s or int(s.get("deleted", 0)) == 1:
        await interaction.response.send_message("❌ Feitiço não existe (ou foi removido).", ephemeral=True)
        return
    await spell_set_active(spell_id, True)
    await interaction.response.send_message(f"✅ `{spell_id}` ativado.", ephemeral=True)


@tree.command(name="spell_desativar", description="(Mestre) Desativar feitiço da escola.")
@only_master_channel()
async def spell_desativar(interaction: discord.Interaction, spell_id: str):
    s = await spell_get(spell_id)
    if not s:
        await interaction.response.send_message("❌ Feitiço não existe.", ephemeral=True)
        return
    await spell_set_active(spell_id, False)
    await interaction.response.send_message(f"✅ `{spell_id}` desativado.", ephemeral=True)


@tree.command(name="spell_excluir", description="(Mestre) Excluir feitiço do mundo (deleted=1).")
@only_master_channel()
async def spell_excluir(interaction: discord.Interaction, spell_id: str):
    spell_id = spell_id.lower().strip()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE spells SET deleted=1, ativo=0 WHERE spell_id=?", (spell_id,))
        await db.commit()
    await interaction.response.send_message(f"🗑️ Feitiço `{spell_id}` removido do mundo.", ephemeral=True)
@tree.command(name="item_criar", description="(Mestre) Criar item no catálogo.")
@only_master_channel()
async def item_criar(
    interaction: discord.Interaction,
    nome: str,
    tipo: str,
    slot: str,
    preco: int,
    item_id: Optional[str] = None,
    bonus: Optional[str] = None,
    efeito: Optional[str] = None,
    classes: Optional[str] = None,
    desc: Optional[str] = None
):
    if preco < 0:
        await interaction.response.send_message("❌ Preço inválido.", ephemeral=True)
        return

    iid = (item_id or slugify(nome)).lower().strip()
    tipo = (tipo or "").lower().strip()
    slot = (slot or "").lower().strip()

    bonus_obj = parse_kv_list(bonus or "")
    efeito_obj = parse_kv_list(efeito or "")
    classes_list = parse_classes(classes or "")

    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT 1 FROM items WHERE item_id=?", (iid,))
        if await cur.fetchone():
            await interaction.response.send_message("❌ Já existe um item com esse ID. Use /item_editar.", ephemeral=True)
            return

        await db.execute("""
            INSERT INTO items (item_id, nome, preco_base, tipo, slot, bonus_json, efeito_json, classes_json, desc, deleted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (iid, nome, int(preco), tipo, slot, jdump(bonus_obj), jdump(efeito_obj), jdump(classes_list), desc or ""))
        await db.commit()

    await interaction.response.send_message(f"✅ Item criado: **{nome}** (`{iid}`). Agora use **/loja_add** ou **/bau_add**.", ephemeral=False)

@tree.command(name="item_editar", description="(Mestre) Editar item do catálogo.")
@only_master_channel()
async def item_editar(
    interaction: discord.Interaction,
    item_id: str,
    nome: Optional[str] = None,
    tipo: Optional[str] = None,
    slot: Optional[str] = None,
    preco: Optional[int] = None,
    bonus: Optional[str] = None,
    efeito: Optional[str] = None,
    classes: Optional[str] = None,
    desc: Optional[str] = None
):
    iid = item_id.lower().strip()
    it = await item_get(iid)
    if not it or int(it.get("deleted", 0)) == 1:
        await interaction.response.send_message("❌ Item não existe (ou foi removido).", ephemeral=True)
        return

    updates = []
    params = []

    if nome is not None:
        updates.append("nome=?")
        params.append(nome)
    if tipo is not None:
        updates.append("tipo=?")
        params.append(tipo.lower().strip())
    if slot is not None:
        updates.append("slot=?")
        params.append(slot.lower().strip())
    if preco is not None:
        if preco < 0:
            await interaction.response.send_message("❌ Preço inválido.", ephemeral=True)
            return
        updates.append("preco_base=?")
        params.append(int(preco))
    if bonus is not None:
        updates.append("bonus_json=?")
        params.append(jdump(parse_kv_list(bonus)))
    if efeito is not None:
        updates.append("efeito_json=?")
        params.append(jdump(parse_kv_list(efeito)))
    if classes is not None:
        updates.append("classes_json=?")
        params.append(jdump(parse_classes(classes)))
    if desc is not None:
        updates.append("desc=?")
        params.append(desc)

    if not updates:
        await interaction.response.send_message("⚠️ Nenhuma alteração enviada.", ephemeral=True)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        params.append(iid)
        await db.execute(f"UPDATE items SET {', '.join(updates)} WHERE item_id=?", tuple(params))
        await db.commit()

    await interaction.response.send_message(f"✅ Item atualizado: `{iid}`.", ephemeral=False)

async def purge_item_from_all_players(item_id: str) -> Tuple[int, int]:
    """
    Remove item_id de inventários e de qualquer slot/anéis. Retorna (afetados_inventario, afetados_equipado)
    """
    inv_hits = 0
    eq_hits = 0

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT user_id, inventario_json, equipado_json FROM players")
        rows = await cur.fetchall()

        for r in rows:
            uid = int(r["user_id"])
            inv = jload(r["inventario_json"], [])
            eq = ensure_equipado_format(jload(r["equipado_json"], {}))

            changed = False

            # inventário
            before_len = len(inv)
            inv = [x for x in inv if x != item_id]
            if len(inv) != before_len:
                inv_hits += 1
                changed = True

            # slots
            for slot in ["arma","armadura","elmo","botas","luvas","cajado","especial","implante","livro_magias"]:
                if eq.get(slot) == item_id:
                    eq[slot] = None
                    eq_hits += 1
                    changed = True

            # anéis
            aneis = eq.get("aneis", [])
            for i in range(len(aneis)):
                if aneis[i] == item_id:
                    aneis[i] = None
                    eq_hits += 1
                    changed = True
            eq["aneis"] = aneis

            if changed:
                await db.execute(
                    "UPDATE players SET inventario_json=?, equipado_json=? WHERE user_id=?",
                    (jdump(inv), jdump(eq), uid)
                )

        await db.commit()

    return inv_hits, eq_hits

@tree.command(name="item_excluir", description="(Mestre) Excluir item do mundo inteiro (some de todo mundo).")
@only_master_channel()
async def item_excluir(interaction: discord.Interaction, item_id: str):
    iid = item_id.lower().strip()
    it = await item_get(iid)
    if not it or int(it.get("deleted", 0)) == 1:
        await interaction.response.send_message("❌ Item não existe (ou já foi removido).", ephemeral=True)
        return

    # marca deletado + remove da loja + remove do baú + purge de players
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE items SET deleted=1 WHERE item_id=?", (iid,))
        await db.execute("UPDATE shop_items SET ativo=0 WHERE item_id=?", (iid,))
        await db.execute("DELETE FROM master_chest WHERE item_id=?", (iid,))
        await db.commit()

    inv_hits, eq_hits = await purge_item_from_all_players(iid)
    await interaction.response.send_message(
        f"🗑️ Item removido do mundo: **{it['nome']}** (`{iid}`)\n"
        f"Afetados: inventários **{inv_hits}**, equipamentos/anéis **{eq_hits}**.",
        ephemeral=False
    )

@tree.command(name="loja_add", description="(Mestre) Ativar item na loja.")
@only_master_channel()
async def loja_add(interaction: discord.Interaction, item_id: str, preco: Optional[int] = None, estoque: Optional[int] = None):
    iid = item_id.lower().strip()
    it = await item_get(iid)
    if not it or int(it.get("deleted", 0)) == 1:
        await interaction.response.send_message("❌ Item não existe (ou foi removido).", ephemeral=True)
        return
    if preco is not None and preco < 0:
        await interaction.response.send_message("❌ Preço inválido.", ephemeral=True)
        return
    if estoque is not None and estoque < 0:
        await interaction.response.send_message("❌ Estoque inválido.", ephemeral=True)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT 1 FROM shop_items WHERE item_id=?", (iid,))
        if await cur.fetchone():
            await db.execute("UPDATE shop_items SET ativo=1, preco=?, estoque=? WHERE item_id=?", (preco, estoque, iid))
        else:
            await db.execute("INSERT INTO shop_items (item_id, preco, estoque, ativo) VALUES (?, ?, ?, 1)", (iid, preco, estoque))
        await db.commit()

    await interaction.response.send_message(f"✅ Item ativado na loja: **{it['nome']}** (`{iid}`).", ephemeral=False)

@tree.command(name="loja_remove", description="(Mestre) Desativar item da loja (não apaga do mundo).")
@only_master_channel()
async def loja_remove(interaction: discord.Interaction, item_id: str):
    iid = item_id.lower().strip()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE shop_items SET ativo=0 WHERE item_id=?", (iid,))
        await db.commit()
    await interaction.response.send_message(f"✅ Item `{iid}` desativado na loja.", ephemeral=False)

@tree.command(name="loja_set", description="(Mestre) Ajustar preço/estoque de item ativo.")
@only_master_channel()
async def loja_set(interaction: discord.Interaction, item_id: str, preco: Optional[int] = None, estoque: Optional[int] = None):
    iid = item_id.lower().strip()
    if preco is not None and preco < 0:
        await interaction.response.send_message("❌ Preço inválido.", ephemeral=True)
        return
    if estoque is not None and estoque < 0:
        await interaction.response.send_message("❌ Estoque inválido.", ephemeral=True)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT 1 FROM shop_items WHERE item_id=?", (iid,))
        if not await cur.fetchone():
            await interaction.response.send_message("❌ Item não está na loja. Use /loja_add.", ephemeral=True)
            return

        sets = []
        params = []
        if preco is not None:
            sets.append("preco=?")
            params.append(preco)
        if estoque is not None:
            sets.append("estoque=?")
            params.append(estoque)

        if not sets:
            await interaction.response.send_message("⚠️ Nada para alterar.", ephemeral=True)
            return

        params.append(iid)
        await db.execute(f"UPDATE shop_items SET {', '.join(sets)} WHERE item_id=?", tuple(params))
        await db.commit()

    await interaction.response.send_message(f"✅ Loja atualizada para `{iid}`.", ephemeral=False)

@tree.command(name="bau_add", description="(Mestre) Adicionar item ao Baú do Mestre.")
@only_master_channel()
async def bau_add(interaction: discord.Interaction, item_id: str, qtd: int = 1):
    iid = item_id.lower().strip()
    if qtd <= 0:
        await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)
        return
    it = await item_get(iid)
    if not it or int(it.get("deleted", 0)) == 1:
        await interaction.response.send_message("❌ Item não existe (ou foi removido).", ephemeral=True)
        return
    await master_chest_add(iid, qtd)
    await interaction.response.send_message(f"✅ Baú: +{qtd}x **{it['nome']}** (`{iid}`).", ephemeral=False)

@tree.command(name="bau_remove", description="(Mestre) Remover item do Baú do Mestre.")
@only_master_channel()
async def bau_remove(interaction: discord.Interaction, item_id: str, qtd: int = 1):
    iid = item_id.lower().strip()
    if qtd <= 0:
        await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)
        return
    ok = await master_chest_remove(iid, qtd)
    if not ok:
        await interaction.response.send_message("❌ Baú não tem essa quantidade.", ephemeral=True)
        return
    await interaction.response.send_message(f"✅ Baú: -{qtd}x `{iid}`.", ephemeral=False)

@tree.command(name="bau_listar", description="(Mestre) Listar itens no Baú do Mestre.")
@only_master_channel()
async def bau_listar(interaction: discord.Interaction):
    rows = await master_chest_list()
    if not rows:
        await interaction.response.send_message("📦 Baú vazio.", ephemeral=True)
        return
    lines = []
    for iid, qtd in rows[:80]:
        it = await item_get(iid)
        nm = it["nome"] if it and int(it.get("deleted", 0)) == 0 else f"{iid} (REMOVIDO)"
        lines.append(f"• `{iid}` — {nm} x{qtd}")
    await interaction.response.send_message("📦 **Baú do Mestre:**\n" + "\n".join(lines), ephemeral=True)

@tree.command(name="bau_dar", description="(Mestre) Dar item do Baú para um jogador.")
@only_master_channel()
async def bau_dar(interaction: discord.Interaction, membro: discord.Member, item_id: str, qtd: int = 1):
    iid = item_id.lower().strip()
    if qtd <= 0:
        await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)
        return
    it = await item_get(iid)
    if not it or int(it.get("deleted", 0)) == 1:
        await interaction.response.send_message("❌ Item não existe (ou foi removido).", ephemeral=True)
        return
    ok = await master_chest_remove(iid, qtd)
    if not ok:
        await interaction.response.send_message("❌ Baú não tem essa quantidade.", ephemeral=True)
        return
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    p.setdefault("inventario", []).extend([iid] * qtd)
    await save_player(p)
    await interaction.response.send_message(f"🎁 Baú → {membro.mention}: **{it['nome']}** x{qtd}.", ephemeral=False)

# ---------- MAGIAS: criar/editar/excluir

@tree.command(name="magia_criar", description="(Mestre) Criar magia no grimório.")
@only_master_channel()
async def magia_criar(
    interaction: discord.Interaction,
    nome: str,
    custo: int,
    efeito_tipo: str,
    efeito_valor: int,
    classes: str,
    spell_id: Optional[str] = None,
    desc: Optional[str] = None
):
    if custo < 0:
        await interaction.response.send_message("❌ Custo inválido.", ephemeral=True)
        return
    if efeito_valor < 0:
        await interaction.response.send_message("❌ Valor inválido.", ephemeral=True)
        return

    stype = (efeito_tipo or "").lower().strip()
    if stype not in ("dano", "cura"):
        await interaction.response.send_message("❌ efeito_tipo deve ser: dano ou cura.", ephemeral=True)
        return

    sid = (spell_id or slugify(nome)).lower().strip()
    classes_list = parse_classes(classes)
    if not classes_list:
        await interaction.response.send_message("❌ Informe classes (ex: mago ou clerigo ou mago,clerigo).", ephemeral=True)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT 1 FROM spells WHERE spell_id=?", (sid,))
        if await cur.fetchone():
            await interaction.response.send_message("❌ Já existe magia com esse ID. Use /magia_editar.", ephemeral=True)
            return

        await db.execute("""
            INSERT INTO spells (spell_id, nome, custo, classes_json, efeito_tipo, efeito_valor, desc, deleted)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (sid, nome, int(custo), jdump(classes_list), stype, int(efeito_valor), desc or ""))
        await db.commit()

    await interaction.response.send_message(f"✅ Magia criada: **{nome}** (`{sid}`) — {stype} {efeito_valor}, custo {custo}.", ephemeral=False)

@tree.command(name="magia_editar", description="(Mestre) Editar magia.")
@only_master_channel()
async def magia_editar(
    interaction: discord.Interaction,
    spell_id: str,
    nome: Optional[str] = None,
    custo: Optional[int] = None,
    efeito_tipo: Optional[str] = None,
    efeito_valor: Optional[int] = None,
    classes: Optional[str] = None,
    desc: Optional[str] = None
):
    sid = spell_id.lower().strip()
    s = await spell_get(sid)
    if not s or int(s.get("deleted", 0)) == 1:
        await interaction.response.send_message("❌ Magia não existe (ou foi removida).", ephemeral=True)
        return

    updates = []
    params = []

    if nome is not None:
        updates.append("nome=?")
        params.append(nome)
    if custo is not None:
        if custo < 0:
            await interaction.response.send_message("❌ Custo inválido.", ephemeral=True)
            return
        updates.append("custo=?")
        params.append(int(custo))
    if efeito_tipo is not None:
        stype = efeito_tipo.lower().strip()
        if stype not in ("dano", "cura"):
            await interaction.response.send_message("❌ efeito_tipo deve ser: dano ou cura.", ephemeral=True)
            return
        updates.append("efeito_tipo=?")
        params.append(stype)
    if efeito_valor is not None:
        if efeito_valor < 0:
            await interaction.response.send_message("❌ Valor inválido.", ephemeral=True)
            return
        updates.append("efeito_valor=?")
        params.append(int(efeito_valor))
    if classes is not None:
        cl = parse_classes(classes)
        if not cl:
            await interaction.response.send_message("❌ Classes inválidas.", ephemeral=True)
            return
        updates.append("classes_json=?")
        params.append(jdump(cl))
    if desc is not None:
        updates.append("desc=?")
        params.append(desc)

    if not updates:
        await interaction.response.send_message("⚠️ Nada para alterar.", ephemeral=True)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        params.append(sid)
        await db.execute(f"UPDATE spells SET {', '.join(updates)} WHERE spell_id=?", tuple(params))
        await db.commit()

    await interaction.response.send_message(f"✅ Magia atualizada: `{sid}`.", ephemeral=False)

async def purge_spell_from_all_players(spell_id: str) -> int:
    hits = 0
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT user_id, spellbook_json FROM players")
        rows = await cur.fetchall()
        for r in rows:
            uid = int(r["user_id"])
            book = jload(r["spellbook_json"], [])
            before = len(book)
            book = [x for x in book if x != spell_id]
            if len(book) != before:
                hits += 1
                await db.execute("UPDATE players SET spellbook_json=? WHERE user_id=?", (jdump(book), uid))
        await db.commit()
    return hits

@tree.command(name="magia_excluir", description="(Mestre) Excluir magia do mundo (some do livro de todos).")
@only_master_channel()
async def magia_excluir(interaction: discord.Interaction, spell_id: str):
    sid = spell_id.lower().strip()
    s = await spell_get(sid)
    if not s or int(s.get("deleted", 0)) == 1:
        await interaction.response.send_message("❌ Magia não existe (ou já foi removida).", ephemeral=True)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE spells SET deleted=1 WHERE spell_id=?", (sid,))
        await db.commit()

    hits = await purge_spell_from_all_players(sid)
    await interaction.response.send_message(f"🗑️ Magia removida: **{s['nome']}** (`{sid}`) — removida de {hits} livros.", ephemeral=False)

# ---------- Outros comandos mestre utilitários

@tree.command(name="resetar", description="(Mestre) Resetar personagem do jogador.")
@only_master_channel()
async def resetar(interaction: discord.Interaction, membro: discord.Member):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM players WHERE user_id=?", (membro.id,))
        await db.commit()
    await interaction.response.send_message(f"🗑️ Personagem de {membro.mention} resetado. (Use /start)", ephemeral=False)

@tree.command(name="setlevel", description="(Mestre) Definir nível (não recalcula stats).")
@only_master_channel()
async def setlevel(interaction: discord.Interaction, membro: discord.Member, nivel: int):
    if nivel < 1 or nivel > 100:
        await interaction.response.send_message("❌ Nível inválido (1–100).", ephemeral=True)
        return
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    p["level"] = nivel
    await save_player(p)
    await interaction.response.send_message(f"🆙 {membro.mention} agora está no nível **{nivel}**.", ephemeral=False)

@tree.command(name="mdano", description="(Mestre) Aplicar dano manual em jogador.")
@only_master_channel()
async def mdano(interaction: discord.Interaction, membro: discord.Member, dano: int):
    if dano <= 0:
        await interaction.response.send_message("❌ Dano inválido.", ephemeral=True)
        return
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    p["hp"] = max(0, int(p["hp"]) - dano)
    await save_player(p)
    await interaction.response.send_message(f"💥 {membro.mention} sofreu **{dano}** dano. (HP {p['hp']})", ephemeral=False)

@tree.command(name="mcurar", description="(Mestre) Curar manualmente jogador.")
@only_master_channel()
async def mcurar(interaction: discord.Interaction, membro: discord.Member, hp: int = 0, mana: int = 0):
    if hp < 0 or mana < 0:
        await interaction.response.send_message("❌ Valores inválidos.", ephemeral=True)
        return
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    p["hp"] += hp
    p["mana"] += mana
    await save_player(p)
    await interaction.response.send_message(f"✨ {membro.mention} curado: ❤ +{hp} | 🔵 +{mana}.", ephemeral=False)

@tree.command(name="mstatus", description="(Mestre) Status rápido de um jogador.")
@only_master_channel()
async def mstatus(interaction: discord.Interaction, membro: discord.Member):
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    await interaction.response.send_message(
        f"🧾 **Status — {membro.display_name}**\n"
        f"Classe: {p['classe']} | Lv {p['level']} | XP {p['xp']}/{xp_para_upar(int(p['level']))}\n"
        f"❤ HP {p['hp']} | 🔵 Mana {p['mana']} | 🥵 Stamina {p['stamina']}/{p['max_stamina']} | 💰 Gold {p['gold']}\n"
        f"⭐ Pontos pendentes: {p.get('pontos',0)}",
        ephemeral=True
    )

# ==============================
# READY
# ==============================

@client.event
async def on_ready():
    await init_db()
    await seed_initial_data()
    try:
        await tree.sync()
    except Exception:
        pass
    print(f"👁️ VIGILLANT ONLINE: {client.user}")

# ==============================
# RUN
# ==============================

client.run(TOKEN)


































