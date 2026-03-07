 print("BOOT VERSION: 2026-03-04-01")
 
 import os
+import asyncio
 import time
 import json
 import math
 import random
 from pathlib import Path
 import re
 import aiosqlite
 import discord
 from discord import app_commands
 from typing import Optional, List, Dict, Any, Tuple
 
 # ==========================
 # DISCORD CLIENT / TREE
 # ==========================
 intents = discord.Intents.default()
 intents.members = True
 
 client = discord.Client(intents=intents)
 tree = app_commands.CommandTree(client)
+_COMMANDS_SYNCED = False
+X1_PENDENTES: Dict[int, Dict[str, Any]] = {}
+X1_ATIVOS: Dict[int, Dict[str, Any]] = {}
+X1_LOCK = asyncio.Lock()
+PLAYERS_TABLE_COLS_CACHE: Optional[set] = None
 
 # ==========================
 # CONFIG / IDs
 # ==========================
 
 TOKEN = os.getenv("TOKEN")
 if not TOKEN:
     raise SystemExit("❌ TOKEN não encontrado. Defina a variável de ambiente TOKEN no Railway e redeploy.")
 
 
 MESTRE_ID = 1255256495369748573  # Cannabinoide
 
 # Para aparecer comandos slash instantaneamente (recomendado no Railway), defina GUILD_ID (ID do servidor) como variável de ambiente.
 GUILD_ID = int(os.getenv("GUILD_ID", "0") or "0")
 
 
 # Canais (IDs fornecidos por você)
 CANAL_BEM_VINDO_ID = 1472100698211483679
 CANAL_COMANDOS_ID  = 1472216958647795965
 CANAL_LOJA_ID      = 1472100628355350633
 CANAL_MESTRE_ID    = 1472274401289310248
 CANAL_CACAR_ID     = 1472365134801276998
 CANAL_TAVERNA_ID   = 0
+CANAL_ARENA_X1_ID  = 1472365134801276998
 
 BASE_DIR = Path(__file__).resolve().parent
 # Persistência no Railway: se você habilitar um Volume montado em /data, o banco fica permanente
 DATA_DIR = Path(os.getenv('DATA_DIR', '/data'))
 if DATA_DIR.exists() and DATA_DIR.is_dir():
     DB_FILE = str(DATA_DIR / 'vigilant_rpg.sqlite')
 else:
     DB_FILE = str(BASE_DIR / 'vigilant_rpg.sqlite')
 
 # Gameplay
 STAMINA_MAX = 100
 STAMINA_CUSTO_CACAR = 12
 CACAR_COOLDOWN_S = 35
 DESCANSO_HORAS = 12
 
 
 # Lojas válidas (definidas cedo para evitar NameError em runtime)
 LOJAS_VALIDAS = {"mercador", "ferreiro", "alfaiate", "arcano", "igreja", "armaduras"}
 ALBERGUE_MAX_CUSTO = 50
 
 # XP
 XP_BASE = 100
 XP_MULT = 1.20  # +20% por nível
 
 # Loja UI
@@ -96,50 +103,87 @@ def clamp(n, a, b):
     return max(a, min(b, n))
 
 def only_channel(channel_id: int, friendly: str):
     async def predicate(interaction: discord.Interaction) -> bool:
         if channel_id == 0:
             return True
         if interaction.channel_id != channel_id:
             msg = f"❌ Este comando só pode ser usado em **#{friendly}**."
             if interaction.response.is_done():
                 await interaction.followup.send(msg, ephemeral=True)
             else:
                 await interaction.response.send_message(msg, ephemeral=True)
             return False
         return True
     return app_commands.check(predicate)
 
 def only_master_channel():
 
     async def predicate(interaction: discord.Interaction) -> bool:
         if not interaction.user:
             return False
         return interaction.user.id == MESTRE_ID
 
     return app_commands.check(predicate)
 
+
+async def ensure_x1_arena_channel(interaction: discord.Interaction) -> bool:
+    if interaction.channel_id == CANAL_ARENA_X1_ID:
+        return True
+    msg = "⚔️ O sistema de X1 só pode ser usado no canal 🏆arena-x1🏆."
+    if interaction.response.is_done():
+        await interaction.followup.send(msg, ephemeral=True)
+    else:
+        await interaction.response.send_message(msg, ephemeral=True)
+    return False
+
+def x1_user_busy(user_id: int) -> bool:
+    if user_id in X1_ATIVOS:
+        return True
+    for pend in X1_PENDENTES.values():
+        if user_id in (pend["challenger_id"], pend["target_id"]):
+            return True
+    return False
+
+def x1_duel_status_text(user_id: int) -> str:
+    pend = X1_PENDENTES.get(user_id)
+    if pend:
+        return (
+            f"⏳ Você tem um desafio pendente de <@{pend['challenger_id']}>. "
+            "Use /aceitarx1 ou /recusarx1."
+        )
+
+    for pend in X1_PENDENTES.values():
+        if pend["challenger_id"] == user_id:
+            return f"⏳ Você desafiou <@{pend['target_id']}> e aguarda resposta."
+
+    active = X1_ATIVOS.get(user_id)
+    if active:
+        return f"⚔️ X1 ativo contra <@{active['opponent_id']}>."
+
+    return "ℹ️ Você não está em nenhum X1 no momento."
+
 async def blocked_by_rest(interaction: discord.Interaction, p: dict) -> bool:
     if now_ts() < int(p.get("rest_until_ts", 0)):
         falta = int(p["rest_until_ts"]) - now_ts()
         horas = max(1, (falta + 3599) // 3600)
         msg = f"⛺ Você está **descansando**. Volte em ~**{horas}h**."
         if interaction.response.is_done():
             await interaction.followup.send(msg, ephemeral=True)
         else:
             await interaction.response.send_message(msg, ephemeral=True)
         return True
     return False
 
 async def blocked_by_narration(interaction: discord.Interaction) -> bool:
     if interaction.guild and NARRACAO_GUILD.get(interaction.guild.id, False):
         msg = "📖 **Modo Narração ATIVO.** Caça automática está pausada (mestre controla)."
         if interaction.response.is_done():
             await interaction.followup.send(msg, ephemeral=True)
         else:
             await interaction.response.send_message(msg, ephemeral=True)
         return True
     return False
 
 def narration_is_on(interaction: discord.Interaction) -> bool:
     if not interaction.guild:
         return False
@@ -1613,80 +1657,91 @@ def ensure_equipado_format(eq: dict) -> dict:
     aneis = eq.get("aneis", [])
     if not isinstance(aneis, list):
         aneis = []
     while len(aneis) < 8:
         aneis.append(None)
     eq["aneis"] = aneis[:8]
     return eq
 
 async def get_player(user_id: int):
     async with aiosqlite.connect(DB_FILE) as db:
         db.row_factory = aiosqlite.Row
         cur = await db.execute("SELECT * FROM players WHERE user_id=?", (user_id,))
         row = await cur.fetchone()
         if not row:
             return None
         p = dict(row)
         p["stats"] = jload(p.get("stats_json"), {})
         p["inventario"] = jload(p.get("inventario_json"), [])
         p["equipado"] = ensure_equipado_format(jload(p.get("equipado_json"), {}))
         p["spellbook"] = jload(p.get("spellbook_json"), [])
         return p
 
 async def save_player(p: dict):
     async with aiosqlite.connect(DB_FILE) as db:
         p["equipado"] = ensure_equipado_format(p.get("equipado", {}))
-        await db.execute("""
-        INSERT INTO players (
-            user_id, classe, level, xp, gold, pontos, hp, mana, stamina, max_stamina,
-            rest_until_ts, last_hunt_ts, stats_json, inventario_json, equipado_json, spellbook_json
-        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
+        global PLAYERS_TABLE_COLS_CACHE
+        if PLAYERS_TABLE_COLS_CACHE is None:
+            cur = await db.execute("PRAGMA table_info(players)")
+            rows = await cur.fetchall()
+            PLAYERS_TABLE_COLS_CACHE = {str(r[1]) for r in rows}
+
+        values_by_col = {
+            "user_id": p["user_id"],
+            "classe": p["classe"],
+            "level": int(p["level"]),
+            "xp": int(p["xp"]),
+            "gold": int(p["gold"]),
+            "pontos": int(p.get("pontos", 0)),
+            "hp": int(p["hp"]),
+            "mana": int(p["mana"]),
+            "stamina": int(p["stamina"]),
+            "max_stamina": int(p["max_stamina"]),
+            "rest_until_ts": int(p.get("rest_until_ts", 0)),
+            "last_hunt_ts": int(p.get("last_hunt_ts", 0)),
+            "stats_json": jdump(p.get("stats", {})),
+            "inventario_json": jdump(p.get("inventario", [])),
+            "equipado_json": jdump(p.get("equipado", {})),
+            "spellbook_json": jdump(p.get("spellbook", [])),
+        }
+
+        cols = [c for c in values_by_col.keys() if c in PLAYERS_TABLE_COLS_CACHE]
+        if "user_id" not in cols:
+            raise RuntimeError("Tabela players sem coluna user_id; não é possível salvar jogador.")
+
+        placeholders = ", ".join(["?"] * len(cols))
+        insert_cols = ", ".join(cols)
+        update_cols = [c for c in cols if c != "user_id"]
+        update_sql = ",\n            ".join([f"{c}=excluded.{c}" for c in update_cols])
+        params = [values_by_col[c] for c in cols]
+
+        await db.execute(f"""
+        INSERT INTO players ({insert_cols})
+        VALUES ({placeholders})
         ON CONFLICT(user_id) DO UPDATE SET
-            classe=excluded.classe,
-            level=excluded.level,
-            xp=excluded.xp,
-            gold=excluded.gold,
-            pontos=excluded.pontos,
-            hp=excluded.hp,
-            mana=excluded.mana,
-            stamina=excluded.stamina,
-            max_stamina=excluded.max_stamina,
-            rest_until_ts=excluded.rest_until_ts,
-            last_hunt_ts=excluded.last_hunt_ts,
-            stats_json=excluded.stats_json,
-            inventario_json=excluded.inventario_json,
-            equipado_json=excluded.equipado_json,
-            spellbook_json=excluded.spellbook_json
-        """, (
-            p["user_id"], p["classe"], int(p["level"]), int(p["xp"]), int(p["gold"]), int(p.get("pontos", 0)),
-            int(p["hp"]), int(p["mana"]), int(p["stamina"]), int(p["max_stamina"]),
-            int(p.get("rest_until_ts", 0)), int(p.get("last_hunt_ts", 0)),
-            jdump(p.get("stats", {})),
-            jdump(p.get("inventario", [])),
-            jdump(p.get("equipado", {})),
-            jdump(p.get("spellbook", [])),
-        ))
+            {update_sql}
+        """, params)
         await db.commit()
 
 async def require_player(interaction: discord.Interaction):
     p = await get_player(interaction.user.id)
     if not p:
         msg = "⚠️ Você ainda não tem personagem. Use **/start** no canal de bem-vindo."
         if interaction.response.is_done():
             await interaction.followup.send(msg, ephemeral=True)
         else:
             await interaction.response.send_message(msg, ephemeral=True)
         return None
     return p
 
 # ==============================
 # ITENS / LOJA / BAÚ
 # ==============================
 
 async def item_get(item_id: str) -> Optional[dict]:
     async with aiosqlite.connect(DB_FILE) as db:
         db.row_factory = aiosqlite.Row
         cur = await db.execute("SELECT * FROM items WHERE item_id=?", (item_id,))
         row = await cur.fetchone()
         if not row:
             return None
         it = dict(row)
@@ -1956,50 +2011,75 @@ class ClasseSelect(discord.ui.Select):
                     f"💰 Gold inicial: **{p['gold']}**"
                 ),
                 color=discord.Color.dark_grey()
             )
 
             # remove o menu depois de escolher
             try:
                 await interaction.message.edit(view=None)
             except Exception:
                 pass
 
             await interaction.followup.send(embed=embed, ephemeral=False)
 
         except Exception as e:
             import traceback
             tb = traceback.format_exc()
             print(tb)
             await interaction.followup.send("❌ Erro ao registrar. Veja os logs.", ephemeral=True)
 
 
 class ClasseView(discord.ui.View):
     def __init__(self):
         super().__init__(timeout=None)
         self.add_item(ClasseSelect())
 
+
+@tree.command(name="spaw", description="(Mestre) Criar personagem para outro jogador.")
+@only_master_channel()
+async def spaw_cmd(interaction: discord.Interaction, jogador: discord.Member, classe: str):
+    classe_key = (classe or "").strip().lower()
+    if classe_key not in CLASSES:
+        validas = ", ".join(sorted([c.upper() for c in CLASSES.keys()]))
+        await interaction.response.send_message(
+            f"❌ Classe inválida. Use uma destas: {validas}.",
+            ephemeral=True
+        )
+        return
+
+    existente = await get_player(jogador.id)
+    if existente:
+        await interaction.response.send_message("❌ Esse jogador já possui personagem.", ephemeral=True)
+        return
+
+    novo = build_new_player(jogador.id, classe_key)
+    await save_player(novo)
+    await interaction.response.send_message(
+        f"✅ Personagem criado para {jogador.mention}: {classe_key.upper()} nível 1.",
+        ephemeral=True
+    )
+
 # ==============================
 # LOJA PAGINADA (DB)
 # ==============================
 
 async def build_loja_embed(page: int) -> discord.Embed:
     itens = await shop_list_active()
     total = len(itens)
     total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
     page = max(0, min(page, total_pages - 1))
 
     start = page * ITEMS_PER_PAGE
     end = start + ITEMS_PER_PAGE
     chunk = itens[start:end]
 
     embed = discord.Embed(
         title="🏪 Terminal de Suprimentos — LOJA (itens ativos)",
         description=(
             "Use **/comprar item_id** para comprar.\n"
             "Use **/vender item_id** para vender (**60%**).\n"
             "Use **/equipar**, **/desequipar**, **/desequiparanel**, **/usar**.\n"
         ),
         color=discord.Color.green()
     )
 
     for it in chunk:
@@ -2118,50 +2198,716 @@ class BandidosView(discord.ui.View):
                 ephemeral=False
             )
 
 # ==============================
 # COMANDOS — JOGADOR
 # ==============================
 
 
 # Loja
 
 # Upar atributos (SEM hp_base/mana_base e sem stamina)
 
 # Trade
 
 # Descansar / Albergue
 
 # ==============================
 # MAGIAS (Jogador) — Livro de Magias
 # ==============================
 
 
 # ==============================
 # /CACAR — D20 AUTOMÁTICO
 # ==============================
 
+def pick_weighted_monster() -> Dict[str, Any]:
+    entries = list(MONSTROS.values())
+    pesos = [max(1, int(e.get("peso", 1))) for e in entries]
+    return random.choices(entries, weights=pesos, k=1)[0]
+
+async def cacar_turn(p: dict, monstro: Dict[str, Any], monster_hp: int) -> Tuple[int, int, int, bool]:
+    atk_total = await total_stat(p, "atk")
+    magia_total = await total_stat(p, "magia")
+    defesa_total = await total_stat(p, "defesa")
+    destreza_total = await total_stat(p, "destreza")
+    sorte_total = await total_stat(p, "sorte")
+
+    dano_jogador = max(1, random.randint(1, 8) + atk_total + (magia_total // 4) + (destreza_total // 6) + (sorte_total // 8) - 3)
+    monster_hp = max(0, int(monster_hp) - dano_jogador)
+
+    dano_monstro = 0
+    forced_retreat = False
+    if monster_hp > 0:
+        dano_monstro = max(1, random.randint(1, 6) + int(monstro.get("atk", 1)) - (defesa_total // 2))
+        p["hp"] = int(p["hp"]) - dano_monstro
+        if int(p["hp"]) <= 0:
+            p["hp"] = 1
+            forced_retreat = True
+
+    return monster_hp, dano_jogador, dano_monstro, forced_retreat
+
+class CacarFightView(discord.ui.View):
+    def __init__(self, user_id: int, monstro: Dict[str, Any], monster_hp: int, turno: int = 1):
+        super().__init__(timeout=120)
+        self.user_id = user_id
+        self.monstro = monstro
+        self.monster_hp = int(monster_hp)
+        self.turno = int(turno)
+
+    async def interaction_check(self, interaction: discord.Interaction) -> bool:
+        return interaction.user.id == self.user_id
+
+    @discord.ui.button(label="Recuar", style=discord.ButtonStyle.secondary, emoji="🏃")
+    async def recuar(self, interaction: discord.Interaction, button: discord.ui.Button):
+        p = await get_player(interaction.user.id)
+        if not p:
+            await interaction.response.send_message("⚠️ Use **/start** primeiro.", ephemeral=True)
+            return
+
+        p["xp"] = max(0, int(p.get("xp", 0)) - 50)
+        await save_player(p)
+        await interaction.response.edit_message(
+            content="🏃 Você recuou da batalha.\n❌ -50 XP",
+            view=None
+        )
+
+    @discord.ui.button(label="Atacar novamente", style=discord.ButtonStyle.danger, emoji="⚔️")
+    async def atacar_novamente(self, interaction: discord.Interaction, button: discord.ui.Button):
+        p = await get_player(interaction.user.id)
+        if not p:
+            await interaction.response.send_message("⚠️ Use **/start** primeiro.", ephemeral=True)
+            return
+
+        self.turno += 1
+        self.monster_hp, dano_jogador, dano_monstro, forced_retreat = await cacar_turn(p, self.monstro, self.monster_hp)
+
+        if forced_retreat:
+            await save_player(p)
+            await interaction.response.edit_message(
+                content=(
+                    f"🎲 Turno {self.turno}\n"
+                    f"Você causou **{dano_jogador}** de dano.\n"
+                    f"{self.monstro['nome']} causou **{dano_monstro}** de dano.\n"
+                    "🩸 Você ficou em estado crítico e fugiu automaticamente.\n"
+                    f"❤ Seu HP: **{p['hp']}**"
+                ),
+                view=None
+            )
+            return
+
+        if self.monster_hp <= 0:
+            p["xp"] = int(p.get("xp", 0)) + int(self.monstro.get("xp", 0))
+            p["gold"] = int(p.get("gold", 0)) + int(self.monstro.get("gold", 0))
+
+            drop_txt = ""
+            if random.random() < DROP_RARO_CHANCE:
+                drop = await pick_drop_from_pool(DROP_POOL_RARO)
+                if drop:
+                    p.setdefault("inventario", []).append(drop["item_id"])
+                    drop_txt = f"\n📦 Drop: {drop['nome']}"
+
+            upou = await try_auto_level(p)
+            await save_player(p)
+
+            await interaction.response.edit_message(
+                content=(
+                    f"🎲 Turno {self.turno}\n"
+                    f"Você causou **{dano_jogador}** de dano.\n"
+                    f"🏆 Vitória! Você derrotou {self.monstro['nome']}.\n"
+                    f"✨ +{int(self.monstro.get('xp', 0))} XP\n"
+                    f"💰 +{int(self.monstro.get('gold', 0))} Gold"
+                    + (f"\n🆙 UPOU {upou} nível(is)!" if upou else "")
+                    + drop_txt
+                ),
+                view=None
+            )
+            return
+
+        await save_player(p)
+        await interaction.response.edit_message(
+            content=(
+                f"🎲 Turno {self.turno}\n"
+                f"Você causou **{dano_jogador}** de dano.\n"
+                f"{self.monstro['nome']} causou **{dano_monstro}** de dano.\n"
+                f"❤ Seu HP: **{p['hp']}**\n"
+                f"👹 HP do monstro: **{self.monster_hp}**\n\n"
+                "⚠️ O monstro ainda está de pé. Escolha:"
+            ),
+            view=self
+        )
+
+
+@tree.command(name="cacar", description="Sair para caçar criaturas nas ruínas.")
+@only_channel(CANAL_CACAR_ID, "cacar")
+async def cacar_cmd(interaction: discord.Interaction):
+    if interaction.channel_id != 1472365134801276998:
+        await interaction.response.send_message(
+            "❌ O comando /cacar só pode ser usado no canal de caça.",
+            ephemeral=True
+        )
+        return
+
+    p = await require_player(interaction)
+    if not p:
+        return
+    if await blocked_by_rest(interaction, p):
+        return
+    if await blocked_by_narration(interaction):
+        return
+
+    if now_ts() - int(p.get("last_hunt_ts", 0)) < CACAR_COOLDOWN_S:
+        falta = CACAR_COOLDOWN_S - (now_ts() - int(p.get("last_hunt_ts", 0)))
+        await interaction.response.send_message(f"⏳ Aguarde **{falta}s** para caçar novamente.", ephemeral=True)
+        return
+
+    if int(p.get("stamina", 0)) < STAMINA_CUSTO_CACAR:
+        await interaction.response.send_message("😮‍💨 Stamina insuficiente para caçar agora.", ephemeral=True)
+        return
+
+    p["stamina"] = max(0, int(p.get("stamina", 0)) - STAMINA_CUSTO_CACAR)
+    p["last_hunt_ts"] = now_ts()
+
+    if random.random() < INIMIGOS_FRACOS_CHANCE:
+        inimigo = random.choice(INIMIGOS_FRACOS)
+        xp = random.randint(int(inimigo["xp"][0]), int(inimigo["xp"][1]))
+        gold = random.randint(int(inimigo["gold"][0]), int(inimigo["gold"][1]))
+        p["xp"] = int(p.get("xp", 0)) + xp
+        p["gold"] = int(p.get("gold", 0)) + gold
+
+        drop_txt = ""
+        if random.random() < DROP_FRACO_CHANCE:
+            drop = await pick_drop_from_pool(DROP_POOL_FRACO)
+            if drop:
+                p.setdefault("inventario", []).append(drop["item_id"])
+                drop_txt = f"\n📦 Drop: {drop['nome']}"
+
+        upou = await try_auto_level(p)
+        await save_player(p)
+
+        await interaction.response.send_message(
+            "🌆 Você saiu para caçar nas ruínas...\n"
+            f"⚔️ Encontrou {inimigo['nome']} (inimigo fraco).\n"
+            f"🏆 Vitória instantânea!\n"
+            f"✨ +{xp} XP\n"
+            f"💰 +{gold} Gold"
+            + (f"\n🆙 UPOU {upou} nível(is)!" if upou else "")
+            + drop_txt,
+            ephemeral=False
+        )
+        return
+
+    monstro = pick_weighted_monster()
+    monster_hp = int(monstro.get("hp", 1))
+    monster_hp, dano_jogador, dano_monstro, forced_retreat = await cacar_turn(p, monstro, monster_hp)
+
+    if forced_retreat:
+        await save_player(p)
+        await interaction.response.send_message(
+            "🌆 Você saiu para caçar nas ruínas...\n"
+            f"👹 Um {monstro['nome']} apareceu!\n"
+            "🎲 Turno 1\n"
+            f"Você causou **{dano_jogador}** de dano.\n"
+            f"{monstro['nome']} causou **{dano_monstro}** de dano.\n"
+            "🩸 Você ficou em estado crítico e fugiu automaticamente.\n"
+            f"❤ Seu HP: **{p['hp']}**",
+            ephemeral=False
+        )
+        return
+
+    if monster_hp <= 0:
+        p["xp"] = int(p.get("xp", 0)) + int(monstro.get("xp", 0))
+        p["gold"] = int(p.get("gold", 0)) + int(monstro.get("gold", 0))
+
+        drop_txt = ""
+        if random.random() < DROP_RARO_CHANCE:
+            drop = await pick_drop_from_pool(DROP_POOL_RARO)
+            if drop:
+                p.setdefault("inventario", []).append(drop["item_id"])
+                drop_txt = f"\n📦 Drop: {drop['nome']}"
+
+        upou = await try_auto_level(p)
+        await save_player(p)
+
+        await interaction.response.send_message(
+            "🌆 Você saiu para caçar nas ruínas...\n"
+            f"👹 Um {monstro['nome']} apareceu!\n"
+            "🎲 Turno 1\n"
+            f"Você causou **{dano_jogador}** de dano.\n"
+            f"🏆 Vitória!\n"
+            f"Você derrotou {monstro['nome']}.\n"
+            f"✨ +{int(monstro.get('xp', 0))} XP\n"
+            f"💰 +{int(monstro.get('gold', 0))} Gold"
+            + (f"\n🆙 UPOU {upou} nível(is)!" if upou else "")
+            + drop_txt,
+            ephemeral=False
+        )
+        return
+
+    await save_player(p)
+    await interaction.response.send_message(
+        "🌆 Você saiu para caçar nas ruínas...\n"
+        f"👹 Um {monstro['nome']} apareceu!\n"
+        "🎲 Turno 1\n"
+        f"Você causou **{dano_jogador}** de dano.\n"
+        f"{monstro['nome']} causou **{dano_monstro}** de dano.\n"
+        f"❤ Seu HP: **{p['hp']}**\n"
+        f"👹 HP do monstro: **{monster_hp}**\n\n"
+        "⚠️ O monstro ainda está de pé. Escolha:",
+        view=CacarFightView(interaction.user.id, monstro, monster_hp, turno=1),
+        ephemeral=False
+    )
+
 
 # ==============================
 # COMANDOS — MESTRE
 # ==============================
 
 
 
 # ---------- DAR XP / GOLD (individual / all / todos_exceto)
 
+@tree.command(name="darxp", description="(Mestre) Dar XP para 1 jogador.")
+@only_master_channel()
+async def darxp_cmd(interaction: discord.Interaction, jogador: str, quantidade: int):
+    if quantidade == 0:
+        await interaction.response.send_message("❌ A quantidade deve ser diferente de 0.", ephemeral=True)
+        return
+
+    jogador_raw = (jogador or "").strip()
+    if jogador_raw.lower() == "all":
+        ids = await list_all_player_ids()
+        if not ids:
+            await interaction.response.send_message("❌ Não há jogadores cadastrados.", ephemeral=True)
+            return
+
+        afetados = 0
+        for pid in ids:
+            p = await get_player(pid)
+            if not p:
+                continue
+            p["xp"] = int(p.get("xp", 0)) + quantidade
+            await try_auto_level(p)
+            await save_player(p)
+            afetados += 1
+
+        await interaction.response.send_message(
+            f"✅ XP {quantidade:+d} aplicado em {afetados} jogador(es).",
+            ephemeral=True
+        )
+        return
+
+    m = re.fullmatch(r"<@!?(\d+)>", jogador_raw)
+    if m:
+        target_id = int(m.group(1))
+    elif jogador_raw.isdigit():
+        target_id = int(jogador_raw)
+    else:
+        await interaction.response.send_message("❌ Use 'all', uma menção válida ou um ID de usuário.", ephemeral=True)
+        return
+
+    p = await get_player(target_id)
+    if not p:
+        await interaction.response.send_message("❌ Esse jogador não tem personagem.", ephemeral=True)
+        return
+
+    p["xp"] = int(p.get("xp", 0)) + quantidade
+    upou = await try_auto_level(p)
+    await save_player(p)
+    await interaction.response.send_message(
+        f"✅ XP atualizado para <@{target_id}>: {quantidade:+d}."
+        + (f" 🆙 Subiu {upou} nível(is)." if upou else ""),
+        ephemeral=True
+    )
+
+@tree.command(name="dargold", description="(Mestre) Dar gold para 1 jogador.")
+@only_master_channel()
+async def dargold_cmd(interaction: discord.Interaction, jogador: str, quantidade: int):
+    if quantidade == 0:
+        await interaction.response.send_message("❌ A quantidade deve ser diferente de 0.", ephemeral=True)
+        return
+
+    jogador_raw = (jogador or "").strip()
+    if jogador_raw.lower() == "all":
+        ids = await list_all_player_ids()
+        if not ids:
+            await interaction.response.send_message("❌ Não há jogadores cadastrados.", ephemeral=True)
+            return
+
+        afetados = 0
+        for pid in ids:
+            p = await get_player(pid)
+            if not p:
+                continue
+            p["gold"] = int(p.get("gold", 0)) + quantidade
+            await save_player(p)
+            afetados += 1
+
+        await interaction.response.send_message(
+            f"✅ Gold {quantidade:+d} aplicado em {afetados} jogador(es).",
+            ephemeral=True
+        )
+        return
+
+    m = re.fullmatch(r"<@!?(\d+)>", jogador_raw)
+    if m:
+        target_id = int(m.group(1))
+    elif jogador_raw.isdigit():
+        target_id = int(jogador_raw)
+    else:
+        await interaction.response.send_message("❌ Use 'all', uma menção válida ou um ID de usuário.", ephemeral=True)
+        return
+
+    p = await get_player(target_id)
+    if not p:
+        await interaction.response.send_message("❌ Esse jogador não tem personagem.", ephemeral=True)
+        return
+
+    p["gold"] = int(p.get("gold", 0)) + quantidade
+    await save_player(p)
+    await interaction.response.send_message(
+        f"✅ Gold atualizado para <@{target_id}>: {quantidade:+d}.",
+        ephemeral=True
+    )
+
+@tree.command(name="darxp_todos", description="(Mestre) Dar XP para todos os jogadores.")
+@only_master_channel()
+async def darxp_todos_cmd(interaction: discord.Interaction, quantidade: int):
+    if quantidade == 0:
+        await interaction.response.send_message("❌ A quantidade deve ser diferente de 0.", ephemeral=True)
+        return
+
+    ids = await list_all_player_ids()
+    if not ids:
+        await interaction.response.send_message("❌ Não há jogadores cadastrados.", ephemeral=True)
+        return
+
+    afetados = 0
+    for uid in ids:
+        p = await get_player(uid)
+        if not p:
+            continue
+        p["xp"] = int(p.get("xp", 0)) + quantidade
+        await try_auto_level(p)
+        await save_player(p)
+        afetados += 1
+
+    await interaction.response.send_message(f"✅ XP {quantidade:+d} aplicado em {afetados} jogador(es).", ephemeral=True)
+
+@tree.command(name="dargold_todos", description="(Mestre) Dar gold para todos os jogadores.")
+@only_master_channel()
+async def dargold_todos_cmd(interaction: discord.Interaction, quantidade: int):
+    if quantidade == 0:
+        await interaction.response.send_message("❌ A quantidade deve ser diferente de 0.", ephemeral=True)
+        return
+
+    ids = await list_all_player_ids()
+    if not ids:
+        await interaction.response.send_message("❌ Não há jogadores cadastrados.", ephemeral=True)
+        return
+
+    afetados = 0
+    for uid in ids:
+        p = await get_player(uid)
+        if not p:
+            continue
+        p["gold"] = int(p.get("gold", 0)) + quantidade
+        await save_player(p)
+        afetados += 1
+
+    await interaction.response.send_message(f"✅ Gold {quantidade:+d} aplicado em {afetados} jogador(es).", ephemeral=True)
+
+@tree.command(name="darxp_exceto", description="(Mestre) Dar XP para todos, exceto um jogador.")
+@only_master_channel()
+async def darxp_exceto_cmd(interaction: discord.Interaction, quantidade: int, exceto: discord.Member):
+    if quantidade == 0:
+        await interaction.response.send_message("❌ A quantidade deve ser diferente de 0.", ephemeral=True)
+        return
+
+    ids = await list_all_player_ids()
+    if not ids:
+        await interaction.response.send_message("❌ Não há jogadores cadastrados.", ephemeral=True)
+        return
+
+    afetados = 0
+    for uid in ids:
+        if uid == exceto.id:
+            continue
+        p = await get_player(uid)
+        if not p:
+            continue
+        p["xp"] = int(p.get("xp", 0)) + quantidade
+        await try_auto_level(p)
+        await save_player(p)
+        afetados += 1
+
+    await interaction.response.send_message(
+        f"✅ XP {quantidade:+d} aplicado em {afetados} jogador(es), exceto {exceto.mention}.",
+        ephemeral=True
+    )
+
+@tree.command(name="dargold_exceto", description="(Mestre) Dar gold para todos, exceto um jogador.")
+@only_master_channel()
+async def dargold_exceto_cmd(interaction: discord.Interaction, quantidade: int, exceto: discord.Member):
+    if quantidade == 0:
+        await interaction.response.send_message("❌ A quantidade deve ser diferente de 0.", ephemeral=True)
+        return
+
+    ids = await list_all_player_ids()
+    if not ids:
+        await interaction.response.send_message("❌ Não há jogadores cadastrados.", ephemeral=True)
+        return
+
+    afetados = 0
+    for uid in ids:
+        if uid == exceto.id:
+            continue
+        p = await get_player(uid)
+        if not p:
+            continue
+        p["gold"] = int(p.get("gold", 0)) + quantidade
+        await save_player(p)
+        afetados += 1
+
+    await interaction.response.send_message(
+        f"✅ Gold {quantidade:+d} aplicado em {afetados} jogador(es), exceto {exceto.mention}.",
+        ephemeral=True
+    )
+
+async def _x1_execute_round(attacker: dict, defender: dict, attacker_name: str, defender_name: str, defender_limit_hp: int) -> str:
+    atk_roll = rolar_d20()
+    atk_stat = await total_stat(attacker, "atk")
+    def_stat = await total_stat(defender, "defesa")
+    atk_total = atk_roll + atk_stat
+    def_total = 10 + def_stat
+
+    if atk_total < def_total:
+        return f"{attacker_name} errou ({atk_total} vs {def_total})."
+
+    dano = max(1, random.randint(1, 8) + atk_stat - def_stat)
+    if atk_roll == 20:
+        dano *= 2
+
+    novo_hp = int(defender["hp"]) - dano
+    defender["hp"] = max(defender_limit_hp, novo_hp)
+    crit_txt = " 💥 CRÍTICO!" if atk_roll == 20 else ""
+    return f"{attacker_name} acertou {defender_name} por **{dano}** de dano.{crit_txt} (HP {defender_name}: {defender['hp']})"
+
+async def _x1_run_duel(channel: discord.abc.Messageable, challenger_id: int, target_id: int):
+    p1 = await get_player(challenger_id)
+    p2 = await get_player(target_id)
+    if not p1 or not p2:
+        await channel.send("❌ X1 cancelado: um dos jogadores não possui personagem.")
+        async with X1_LOCK:
+            X1_ATIVOS.pop(challenger_id, None)
+            X1_ATIVOS.pop(target_id, None)
+        return
+
+    n1 = f"<@{challenger_id}>"
+    n2 = f"<@{target_id}>"
+    hp1_inicial = int(p1["hp"])
+    hp2_inicial = int(p2["hp"])
+    hp1_limite = max(1, int(hp1_inicial * 0.05))
+    hp2_limite = max(1, int(hp2_inicial * 0.05))
+
+    rodada = 1
+    while int(p1["hp"]) > hp1_limite and int(p2["hp"]) > hp2_limite:
+        ini1 = rolar_d20() + await total_stat(p1, "destreza")
+        ini2 = rolar_d20() + await total_stat(p2, "destreza")
+
+        if ini1 >= ini2:
+            first = (p1, p2, n1, n2, hp2_limite)
+            second = (p2, p1, n2, n1, hp1_limite)
+        else:
+            first = (p2, p1, n2, n1, hp1_limite)
+            second = (p1, p2, n1, n2, hp2_limite)
+
+        log1 = await _x1_execute_round(*first)
+        if int(p1["hp"]) <= hp1_limite or int(p2["hp"]) <= hp2_limite:
+            await channel.send(f"🎲 Rodada {rodada}: {log1}")
+            break
+
+        log2 = await _x1_execute_round(*second)
+        await channel.send(f"🎲 Rodada {rodada}: {log1}\n{log2}")
+        rodada += 1
+
+    if int(p1["hp"]) <= hp1_limite:
+        vencedor, perdedor = p2, p1
+        vencedor_id, perdedor_id = target_id, challenger_id
+    else:
+        vencedor, perdedor = p1, p2
+        vencedor_id, perdedor_id = challenger_id, target_id
+
+    gold_perdedor = int(perdedor.get("gold", 0))
+    gold_transferido = int(gold_perdedor * 0.30)
+    if gold_transferido == 0 and gold_perdedor > 0:
+        gold_transferido = 1
+
+    perdedor["gold"] = max(0, gold_perdedor - gold_transferido)
+    vencedor["gold"] = int(vencedor.get("gold", 0)) + gold_transferido
+
+    await save_player(vencedor)
+    await save_player(perdedor)
+
+    await channel.send(
+        f"🏆 Vencedor: <@{vencedor_id}>\n"
+        f"😵 Perdedor: <@{perdedor_id}>\n"
+        f"💰 Transferência: **{gold_transferido}** gold."
+    )
+
+    async with X1_LOCK:
+        X1_ATIVOS.pop(challenger_id, None)
+        X1_ATIVOS.pop(target_id, None)
+
+@tree.command(name="x1", description="Desafiar outro jogador para um X1 por turnos.")
+async def x1_cmd(interaction: discord.Interaction, jogador: discord.Member):
+    if not await ensure_x1_arena_channel(interaction):
+        return
+    if jogador.bot:
+        await interaction.response.send_message("❌ Você não pode desafiar um bot.", ephemeral=True)
+        return
+    if jogador.id == interaction.user.id:
+        await interaction.response.send_message("❌ Você não pode se desafiar.", ephemeral=True)
+        return
+
+    p_challenger = await get_player(interaction.user.id)
+    p_target = await get_player(jogador.id)
+    if not p_challenger or not p_target:
+        await interaction.response.send_message("❌ Ambos os jogadores precisam ter personagem.", ephemeral=True)
+        return
+
+    async with X1_LOCK:
+        if x1_user_busy(interaction.user.id) or x1_user_busy(jogador.id):
+            await interaction.response.send_message("❌ Um dos jogadores já está em outro X1.", ephemeral=True)
+            return
+
+        X1_PENDENTES[jogador.id] = {
+            "challenger_id": interaction.user.id,
+            "target_id": jogador.id,
+            "channel_id": interaction.channel_id,
+            "created_at": now_ts(),
+        }
+
+    await interaction.response.send_message(
+        f"⚔️ {interaction.user.display_name} desafiou {jogador.display_name} para um X1. "
+        f"{jogador.display_name}, use /aceitarx1 ou /recusarx1.",
+        ephemeral=False
+    )
+
+@tree.command(name="aceitarx1", description="Aceitar um desafio de X1 pendente.")
+async def aceitarx1_cmd(interaction: discord.Interaction):
+    if not await ensure_x1_arena_channel(interaction):
+        return
+
+    async with X1_LOCK:
+        pend = X1_PENDENTES.get(interaction.user.id)
+        if not pend:
+            await interaction.response.send_message("❌ Você não tem desafio pendente.", ephemeral=True)
+            return
+
+        challenger_id = pend["challenger_id"]
+        target_id = pend["target_id"]
+
+        if interaction.user.id != target_id:
+            await interaction.response.send_message("❌ Apenas o desafiado pode aceitar.", ephemeral=True)
+            return
+
+        if challenger_id in X1_ATIVOS or target_id in X1_ATIVOS:
+            X1_PENDENTES.pop(interaction.user.id, None)
+            await interaction.response.send_message("❌ Esse desafio não está mais disponível.", ephemeral=True)
+            return
+
+        X1_PENDENTES.pop(interaction.user.id, None)
+        X1_ATIVOS[challenger_id] = {"opponent_id": target_id}
+        X1_ATIVOS[target_id] = {"opponent_id": challenger_id}
+
+    await interaction.response.send_message("✅ Desafio aceito. O duelo começou.", ephemeral=False)
+    asyncio.create_task(_x1_run_duel(interaction.channel, challenger_id, target_id))
+
+@tree.command(name="recusarx1", description="Recusar um desafio de X1 pendente.")
+async def recusarx1_cmd(interaction: discord.Interaction):
+    if not await ensure_x1_arena_channel(interaction):
+        return
+
+    async with X1_LOCK:
+        pend = X1_PENDENTES.get(interaction.user.id)
+        if not pend:
+            await interaction.response.send_message("❌ Você não tem desafio pendente.", ephemeral=True)
+            return
+        if pend["target_id"] != interaction.user.id:
+            await interaction.response.send_message("❌ Apenas o desafiado pode recusar.", ephemeral=True)
+            return
+
+        X1_PENDENTES.pop(interaction.user.id, None)
+        challenger_id = pend["challenger_id"]
+
+    await interaction.response.send_message(
+        f"🛑 <@{interaction.user.id}> recusou o desafio de <@{challenger_id}>.",
+        ephemeral=False
+    )
+
+@tree.command(name="cancelarx1", description="Cancelar um desafio de X1 ainda não iniciado.")
+async def cancelarx1_cmd(interaction: discord.Interaction):
+    if not await ensure_x1_arena_channel(interaction):
+        return
+
+    async with X1_LOCK:
+        pend_target = None
+        for target_id, pend in X1_PENDENTES.items():
+            if pend["challenger_id"] == interaction.user.id:
+                pend_target = target_id
+                break
+
+        if pend_target is None:
+            await interaction.response.send_message("❌ Você não tem desafio pendente para cancelar.", ephemeral=True)
+            return
+
+        X1_PENDENTES.pop(pend_target, None)
+
+    await interaction.response.send_message("✅ Seu desafio pendente foi cancelado.", ephemeral=True)
+
+@tree.command(name="statusx1", description="Ver seu status atual no sistema de X1.")
+async def statusx1_cmd(interaction: discord.Interaction):
+    if not await ensure_x1_arena_channel(interaction):
+        return
+    await interaction.response.send_message(x1_duel_status_text(interaction.user.id), ephemeral=True)
+
+
 async def list_all_player_ids() -> List[int]:
     async with aiosqlite.connect(DB_FILE) as db:
         cur = await db.execute("SELECT user_id FROM players")
         rows = await cur.fetchall()
         return [int(r[0]) for r in rows]
 
 
 # [REMOVIDO DUPLICADO] command 'spell_ativar'
 
 # [REMOVIDO DUPLICADO] command 'magia_criar'
 
+
+@client.event
+async def on_ready():
+    global _COMMANDS_SYNCED
+    if _COMMANDS_SYNCED:
+        return
+
+    _COMMANDS_SYNCED = True
+    try:
+        if GUILD_ID:
+            guild_obj = discord.Object(id=GUILD_ID)
+            tree.copy_global_to(guild=guild_obj)
+            synced = await tree.sync(guild=guild_obj)
+            print(f"✅ Slash commands sincronizados na guild {GUILD_ID}: {len(synced)}")
+        else:
+            synced = await tree.sync()
+            print(f"✅ Slash commands sincronizados globalmente: {len(synced)}")
+    except Exception as e:
+        print(f"❌ Falha ao sincronizar slash commands: {e}")
+
+    print(f"🤖 Bot online como {client.user}")
+
+
 # ==============================
 # RUN
 # ==============================
 
 client.run(TOKEN)
 
EOF
)
