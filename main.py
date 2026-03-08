print("BOOT VERSION: FORCE-REBUILD-COMMANDS-06")

import os
import time
import json
import math
import random
from collections import Counter
from pathlib import Path
import re
import aiosqlite
import discord
from discord import app_commands
from typing import Optional, List, Dict, Any, Tuple

from x1_arena import setup_x1_arena

# ==========================
# DISCORD CLIENT / TREE
# ==========================
intents = discord.Intents.default()
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ==========================
# CONFIG / IDs
# ==========================

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise SystemExit("❌ TOKEN não encontrado. Defina a variável de ambiente TOKEN no Railway e redeploy.")


MESTRE_ID = 1255256495369748573  # Cannabinoide

# Para aparecer comandos slash instantaneamente (recomendado no Railway), defina GUILD_ID (ID do servidor) como variável de ambiente.
GUILD_ID = int(os.getenv("GUILD_ID", "0") or "0")

REQUIRED_CORE_COMMANDS = {"start", "bau", "reset", "restart", "upar"}


# Canais (IDs fornecidos por você)
CANAL_BEM_VINDO_ID = 1472100698211483679
CANAL_COMANDOS_ID  = 1472216958647795965
CANAL_LOJA_ID      = 1472100628355350633
CANAL_MESTRE_ID    = 1472274401289310248
CANAL_CACAR_ID     = 1472365134801276998
CANAL_ARENA_X1_ID  = 1479210311662960711
CANAL_TAVERNA_ID   = 0

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
ALBERGUE_CUSTO_FIXO = 150
ALBERGUE_DESCANSO_HORAS = 2

# XP
XP_BASE = 100
XP_MULT = 1.20  # +20% por nível

# Loja UI
ITEMS_PER_PAGE = 6

# ==============================
# UTIL / CHECKS
# ==============================

def normalize_item_list(raw: str) -> List[str]:
    if not raw:
        return []
    parts = [p.strip().lower() for p in raw.split(",")]
    return [p for p in parts if p]

def now_ts() -> int:
    return int(time.time())

def eh_mestre(user_id: int) -> bool:
    return user_id == MESTRE_ID

def rolar_d20() -> int:
    return random.randint(1, 20)

def xp_para_upar(level: int) -> int:
    return int(round(XP_BASE * (XP_MULT ** (level - 1))))

def clamp(n, a, b):
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
    return bool(NARRACAO_GUILD.get(interaction.guild.id, False))

def jload(s: Optional[str], default):
    try:
        if not s:
            return default
        return json.loads(s)
    except Exception:
        return default

def jdump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)

def slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or f"id_{random.randint(1000, 9999)}"

def parse_kv_list(text: str) -> Dict[str, Any]:
    """
    "atk=2,defesa=-1,magia=3" -> {"atk":2,"defesa":-1,"magia":3}
    """
    out: Dict[str, Any] = {}
    text = (text or "").strip()
    if not text:
        return out
    for part in text.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if not k:
            continue
        try:
            out[k] = int(v)
        except ValueError:
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
    return out

def parse_classes(text: str) -> List[str]:
    if not text:
        return []
    return [c.strip().lower() for c in text.split(",") if c.strip()]

def can_use_spellbook(classe: str) -> bool:
    return classe in ("mago", "clerigo")

# ==============================
# PROGRESSÃO — HP e Mana automáticos, até nível 100
# - 1–20: +1 (HP para todos; Mana para classes com mana > 0)
# - Depois: por faixas, igual HP (mesma estrutura), mas valores por classe
# ==============================

def hp_gain(classe: str, new_level: int) -> int:
    if new_level <= 20:
        return 1

    if classe == "barbaro":
        if new_level <= 40: return 2
        if new_level <= 60: return 3
        if new_level <= 80: return 4
        return 5

    if classe == "guerreiro":
        if new_level <= 40: return 2
        if new_level <= 60: return 3
        if new_level <= 80: return 3
        return 4

    if classe in ("arqueiro", "assassino", "clerigo"):
        if new_level <= 40: return 1
        if new_level <= 60: return 2
        if new_level <= 80: return 3
        return 3

    # mago
    if new_level <= 40: return 1
    if new_level <= 60: return 2
    if new_level <= 80: return 2
    return 3

def mana_gain(classe: str, new_level: int) -> int:
    # sem mana
    if classe == "barbaro":
        return 0

    # 1–20: +1 para classes que têm mana
    if new_level <= 20:
        return 1

    # mesma estrutura de faixas do HP, mas com “perfil” de mana
    if classe == "mago":
        if new_level <= 40: return 2
        if new_level <= 60: return 3
        if new_level <= 80: return 3
        return 4

    if classe == "clerigo":
        if new_level <= 40: return 1
        if new_level <= 60: return 2
        if new_level <= 80: return 2
        return 3

    # classes com mana baixa
    if new_level <= 40: return 1
    if new_level <= 60: return 1
    if new_level <= 80: return 2
    return 2

# ==============================
# BANCO DE DADOS
# ==============================

async def pick_drop_from_pool(pool: List[str]) -> Optional[Dict[str, Any]]:
    """
    Retorna um item aleatório DO POOL, mas apenas se estiver ATIVO na loja.
    Ajuste os nomes das tabelas/colunas se no seu DB forem diferentes.
    """
    if not pool:
        return None

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        # Tenta algumas vezes para achar um item válido/ativo
        for _ in range(12):
            drop_id = random.choice(pool)

            # ✅ AJUSTE AQUI se seu schema for diferente:
            # - items(item_id, nome, ...)
            # - shop_items(item_id, ativo)
            cur = await db.execute("""
                SELECT i.item_id, i.nome
                FROM items i
                JOIN shop_items s ON s.item_id = i.item_id
                WHERE i.item_id = ? AND s.ativo = 1
                LIMIT 1
            """, (drop_id,))
            row = await cur.fetchone()
            if row:
                return dict(row)

    return None



def build_shop_embed(loja: str, page: int, itens: List[Dict[str, Any]]) -> discord.Embed:
    total = len(itens)
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    chunk = itens[start:end]

    titulos = {
        "mercador": "🏪 Terminal de Suprimentos — MERCADOR",
        "ferreiro": "⚒️ Forja dos Ermos — FERREIRO",
        "alfaiate": "🧵 Atelier das Ruínas — ALFAIATE",
        "arcano": "🔮 Escola Arcana — ARCANOS",
        "igreja": "⛪ Santuário — IGREJA",
        "armaduras": "🛡️ Arsenal Blindado — ARMADURAS",
    }

    embed = discord.Embed(
        title=f"{titulos.get(loja, loja.upper())} (itens ativos)",
        description=(
            "Use **/comprar item_id** para comprar.\n"
            "Use **/vender item_id** para vender (**60%**).\n"
            "Use **/equipar** e **/desequipar**.\n"
        ),
        color=discord.Color.green()
    )

    for it in chunk:
        item_id = it["item_id"]
        preco = int(it.get("preco", 0))
        tipo = it.get("tipo", "—")
        desc = (it.get("desc", "") or "").strip()

        if tipo == "consumivel":
            eff = it.get("efeito", {})
            eff_txt = ", ".join([f"{k}+{v}" for k, v in eff.items()]) if eff else "—"
            val = f"💰 **{preco}** | 🧪 {eff_txt}"
        else:
            bonus = it.get("bonus", {})
            btxt = ", ".join([f"{k.upper()}+{v}" for k, v in bonus.items()]) if bonus else "—"
            val = f"💰 **{preco}** | ⚙️ **{tipo}** | {btxt}"

        if desc:
            desc = desc[:90] + ("…" if len(desc) > 90 else "")
            val += f"\n_{desc}_"

        embed.add_field(name=f"**{it.get('nome','Item')}** (`{item_id}`)", value=val, inline=False)

    embed.set_footer(text=f"Loja: {loja} • Página {page+1}/{total_pages} • Itens {start+1}-{min(end,total)} de {total}")
    return embed


class ShopView(discord.ui.View):
    def __init__(self, user_id: int, loja: str, itens: List[Dict[str, Any]], page: int = 0):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.loja = loja
        self.itens = itens
        self.page = page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        await interaction.response.edit_message(embed=build_shop_embed(self.loja, self.page, self.itens), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await interaction.response.edit_message(embed=build_shop_embed(self.loja, self.page, self.itens), view=self)

    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Loja fechada.", embed=None, view=None)


@tree.command(name="loja", description="Ver itens ativos de uma loja (paginado).")
@only_channel(CANAL_LOJA_ID, "loja")
@app_commands.describe(loja="mercador|ferreiro|alfaiate|arcano|igreja|armaduras")
async def loja_cmd(interaction: discord.Interaction, loja: str = "mercador"):
    # Evita erro 10062 (Unknown interaction) quando DB/embeds demoram
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    p = await require_player(interaction)
    if not p:
        await interaction.followup.send("❌ Use **/start** para criar seu personagem primeiro.", ephemeral=True)
        return
    if await blocked_by_rest(interaction, p):
        return

    loja = (loja or "mercador").lower().strip()
    if loja not in LOJAS_VALIDAS:
        loja = "mercador"

    itens = await items_list_active(loja)
    await interaction.followup.send(
        embed=build_shop_embed(loja, 0, itens),
        view=ShopView(interaction.user.id, loja, itens, 0),
        ephemeral=True
    )


@tree.command(name="comprar", description="Comprar um item ativo da loja.")
@only_channel(CANAL_LOJA_ID, "loja")
async def comprar_cmd(interaction: discord.Interaction, item_id: str):
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    p = await require_player(interaction)
    if not p:
        await interaction.followup.send("❌ Use **/start** para criar seu personagem primeiro.", ephemeral=True)
        return
    if await blocked_by_rest(interaction, p):
        return

    item_id = (item_id or "").lower().strip()
    it = await item_get(item_id)
    if not it or int(it.get("deleted", 0)) == 1:
        await interaction.followup.send("❌ Item inexistente.", ephemeral=True)
        return

    if not await shop_is_active(item_id):
        await interaction.followup.send("❌ Este item está inativo/não vendável no momento.", ephemeral=True)
        return

    preco = int(shop_price(it))
    gold = int(p.get("gold", 0))
    if gold < preco:
        await interaction.followup.send(f"❌ Gold insuficiente. Preço: **{preco}** | Seu gold: **{gold}**.", ephemeral=True)
        return

    if not await shop_decrease_stock(item_id, 1):
        await interaction.followup.send("❌ Item sem estoque no momento.", ephemeral=True)
        return

    p["gold"] = gold - preco
    p.setdefault("inventario", []).append(item_id)
    await save_player(p)

    await interaction.followup.send(
        f"✅ Você comprou **{it.get('nome', item_id)}** por **{preco} gold**.",
        ephemeral=True
    )

def parse_json_field(txt: str) -> Dict[str, Any]:
    txt = (txt or "").strip()
    if not txt:
        return {}
    try:
        obj = json.loads(txt)
        if isinstance(obj, dict):
            return obj
        return {}
    except Exception:
        return {}

def parse_json_list(txt: str) -> List[str]:
    txt = (txt or "").strip()
    if not txt:
        return []
    try:
        obj = json.loads(txt)
        if isinstance(obj, list):
            return [str(x) for x in obj]
        return []
    except Exception:
        return []


@tree.command(name="item_criar", description="(Mestre) Criar item no catálogo.")
@only_master_channel()
async def item_criar(
    interaction: discord.Interaction,
    item_id: str,
    nome: str,
    tipo: str,
    slot: str,
    preco: int,
    loja: str,
    bonus_json: str = "",
    efeito_json: str = "",
    classes_json: str = "",
    desc: str = ""
):
    item_id = item_id.lower().strip()
    loja = (loja or "mercador").lower().strip()
    if loja not in LOJAS_VALIDAS:
        await interaction.response.send_message("❌ Loja inválida.", ephemeral=True)
        return

    it = {
        "nome": nome,
        "tipo": tipo,
        "slot": slot,
        "preco": int(preco),
        "bonus": parse_json_field(bonus_json),
        "efeito": parse_json_field(efeito_json),
        "classes": parse_json_list(classes_json),
        "desc": desc,
        "loja": loja
    }
    await item_upsert(item_id, it)
    await interaction.response.send_message(f"✅ Item `{item_id}` criado/atualizado na loja **{loja}**.", ephemeral=True)

@tree.command(name="item_ativar", description="(Mestre) Ativar item na vitrine da loja.")
@only_master_channel()
async def item_ativar(interaction: discord.Interaction, item_id: str):
    item_id = item_id.lower().strip()
    it = await item_get(item_id)
    if not it or int(it.get("deleted", 0)) == 1:
        await interaction.response.send_message("❌ Item não existe (ou foi removido).", ephemeral=True)
        return
    await item_set_active(item_id, True)
    await interaction.response.send_message(f"✅ Item `{item_id}` ativado na loja **{it['loja']}**.", ephemeral=True)

@tree.command(name="item_desativar", description="(Mestre) Desativar item da vitrine.")
@only_master_channel()
async def item_desativar(interaction: discord.Interaction, item_id: str):
    item_id = item_id.lower().strip()
    it = await item_get(item_id)
    if not it:
        await interaction.response.send_message("❌ Item não existe.", ephemeral=True)
        return
    await item_set_active(item_id, False)
    await interaction.response.send_message(f"✅ Item `{item_id}` desativado.", ephemeral=True)

@tree.command(name="item_mover", description="(Mestre) Mover item para outra loja.")
@only_master_channel()
@app_commands.describe(loja="mercador|ferreiro|alfaiate|arcano|igreja|armaduras")
async def item_mover(interaction: discord.Interaction, item_id: str, loja: str):
    item_id = item_id.lower().strip()
    loja = (loja or "").lower().strip()
    if loja not in LOJAS_VALIDAS:
        await interaction.response.send_message("❌ Loja inválida.", ephemeral=True)
        return
    it = await item_get(item_id)
    if not it or int(it.get("deleted", 0)) == 1:
        await interaction.response.send_message("❌ Item não existe (ou foi removido).", ephemeral=True)
        return

    it["loja"] = loja
    await item_upsert(item_id, it)
    await interaction.response.send_message(f"✅ Item `{item_id}` movido para **{loja}**.", ephemeral=True)

@tree.command(name="item_excluir", description="(Mestre) Excluir item do mundo (some até se equipado).")
@only_master_channel()
async def item_excluir(interaction: discord.Interaction, item_id: str):
    item_id = item_id.lower().strip()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE items SET deleted=1, ativo=0 WHERE item_id=?", (item_id,))
        await db.commit()
    await interaction.response.send_message(f"🗑️ Item `{item_id}` removido do mundo (deleted=1).", ephemeral=True)
# Livro de magias
SPELLBOOK_SLOTS = 7

# ==============================
# LORE / FALAS
# ==============================

VIGILLANT_QUOTES = [
    "A humanidade é um erro estatístico. Eu vim corrigir.",
    "Eu observo cada movimento seu. Não há onde se esconder.",
    "A Diretriz não falha.",
    "Sua esperança é só ruído no sistema.",
    "Resistir é uma variável… e eu removo variáveis."
]

MOB_QUOTES = {
    "orgânico": [
        "Um uivo distante ecoa entre os destroços…",
        "O ar fede a ferrugem e carne podre.",
        "Algo vivo… mas errado… se arrasta na escuridão."
    ],
    "cibernético": [
        "Um zumbido mecânico corta o silêncio.",
        "Luzes frias varrem o terreno. Você foi detectado.",
        "Sinais da Diretriz… rastreando sua assinatura térmica."
    ],
    "demoníaco": [
        "O chão parece respirar. O ar fica quente demais.",
        "Uma presença antiga ri dentro da sua mente.",
        "O mundo perde cor. Algo do outro lado atravessou."
    ]
}

# ==============================
# DADOS DO RPG
# ==============================

CLASSES: Dict[str, Dict[str, int]] = {
    "clerigo":   {"hp_base": 55, "mana_base": 40, "atk": 2,  "magia": 8,  "defesa": 5, "sorte": 3, "furtividade": 1, "destreza": 2},
    "barbaro":   {"hp_base": 70, "mana_base": 0,  "atk": 10, "magia": 0,  "defesa": 6, "sorte": 2, "furtividade": 1, "destreza": 3},
    "arqueiro":  {"hp_base": 40, "mana_base": 15, "atk": 8,  "magia": 2,  "defesa": 3, "sorte": 4, "furtividade": 5, "destreza": 8},
    "mago":      {"hp_base": 35, "mana_base": 60, "atk": 1,  "magia": 12, "defesa": 2, "sorte": 3, "furtividade": 2, "destreza": 3},
    "assassino": {"hp_base": 35, "mana_base": 10, "atk": 9,  "magia": 3,  "defesa": 3, "sorte": 5, "furtividade": 8, "destreza": 7},
    "guerreiro": {"hp_base": 46, "mana_base": 2,  "atk": 12, "magia": 3,  "defesa": 6, "sorte": 5, "furtividade": 1, "destreza": 7},
}

# +1 automático por classe (stamina nunca)
AUTO_UP: Dict[str, str] = {
    "barbaro": "atk",
    "guerreiro": "atk",
    "assassino": "destreza",
    "arqueiro": "destreza",
    "mago": "magia",
    "clerigo": "magia",
}

# Monstros ponderados (fortes = raros)
MONSTROS = {
    "rato_irradiado":      {"nome": "Rato Irradiado",            "hp": 5,  "atk": 5,  "xp": 12,  "gold": 14,  "peso": 26, "tags": ["orgânico", "radiação"]},
    "lobo_mutante":        {"nome": "Lobo Mutante",              "hp": 6,  "atk": 7,  "xp": 18,  "gold": 22,  "peso": 22, "tags": ["orgânico"]},
    "carnical_radioativo": {"nome": "Carniçal Radioativo",       "hp": 6,  "atk": 9,  "xp": 26,  "gold": 32,  "peso": 18, "tags": ["orgânico", "radiação"]},
    "drone_vigia":         {"nome": "Drone Vigia da Diretriz",   "hp": 11,  "atk": 12, "xp": 45,  "gold": 60,  "peso": 12, "tags": ["cibernético", "diretriz"]},
    "vampiro_errante":     {"nome": "Vampiro Errante",           "hp": 14,  "atk": 16, "xp": 90,  "gold": 130, "peso": 6,  "tags": ["orgânico", "vampiro"]},
    "demonio_invadido":    {"nome": "Demônio Invadido",          "hp": 95,  "atk": 20, "xp": 140, "gold": 200, "peso": 4,  "tags": ["demoníaco"]},
    "ciborgue_diretriz":   {"nome": "Ciborgue da Mente-Colmeia", "hp": 30, "atk": 24, "xp": 190, "gold": 260, "peso": 3,  "tags": ["cibernético", "diretriz"]},
    "sentinela_antigo":    {"nome": "Sentinela Antigo",          "hp": 40, "atk": 30, "xp": 280, "gold": 360, "peso": 2,  "tags": ["cibernético", "antigo"]},
    "executor_vigillant":  {"nome": "Executor de VIGILLANT",     "hp": 45, "atk": 38, "xp": 450, "gold": 600, "peso": 1,  "tags": ["cibernético", "diretriz", "boss"]},
}
# ==============================
# CONFIG DE PROBABILIDADES
# ==============================

INIMIGOS_FRACOS_CHANCE = 0.38
DROP_FRACO_CHANCE = 0.04
DROP_RARO_CHANCE = 0.35

# ==============================
# INIMIGOS FRACOS (sempre morrem)
# ==============================

INIMIGOS_FRACOS = [
    {"nome": "Cachorro Magro",   "xp": (2, 6),  "gold": (1, 6),  "tags": ["orgânico"]},
    {"nome": "Rato de Esgoto",   "xp": (1, 5),  "gold": (0, 4),  "tags": ["orgânico"]},
    {"nome": "Drone Defeituoso", "xp": (3, 8),  "gold": (1, 8),  "tags": ["cibernético", "diretriz"]},
    {"nome": "Ladrão Maneta",    "xp": (4, 10), "gold": (2, 12), "tags": ["orgânico"]},
    {"nome": "Mendigo Ousado",   "xp": (2, 7),  "gold": (0, 5),  "tags": ["orgânico"]},
]


def enemy_get_stats(enemy: Dict[str, Any]) -> Tuple[int, int]:
    """Return (hp, def) for an enemy. If missing in dict, generate sane defaults by tier."""
    # weak enemies: lower stats
    tags = enemy.get("tags", []) or []
    # If explicit:
    if "hp" in enemy and "def" in enemy:
        return int(enemy["hp"]), int(enemy["def"])
    # Heuristic defaults
    base_hp = 14
    base_def = 1
    if "cibernético" in tags:
        base_hp += 4
        base_def += 1
    if "irradiado" in tags or "mutante" in tags:
        base_hp += 6
    # add randomness
    hp = int(enemy.get("hp", random.randint(base_hp, base_hp + 10)))
    df = int(enemy.get("def", random.randint(base_def, base_def + 2)))
    return hp, df


# ==============================
# POOLS DE DROP (só itens ATIVOS)
# ==============================
DROP_POOL_FRACO = [
    "pocao_vida",
    "pocao_mana",
    "anel_caveira_rato",
]

DROP_POOL_RARO = [
    "katana",
    "manto_negro_deus_cabra",
    "anel_pristino",
    "arco_longo_norte",
    "manoplas_aco_polido",
]
# ==============================
# NARRAÇÃO / COMBATE
# ==============================

# Narração ON = considerado "combate/narração ativa" para travar troca do livro de magias
NARRACAO_GUILD: Dict[int, bool] = {}


# ==============================
# SEED: ITENS INICIAIS (só para primeira execução)
# Depois você cria/edita tudo pelo Discord
# ==============================

INITIAL_ITEMS = {
    "pocao_vida": {
        "nome": "Poção de Vida",
        "preco": 200,
        "tipo": "consumivel",
        "slot": "consumivel",
        "efeito": {"hp": 20},
        "bonus": {},
        "classes": [],
        "desc": "Recupera 20 HP."
    },
    "pocao_mana": {
        "nome": "Poção de Mana",
        "preco": 200,
        "tipo": "consumivel",
        "slot": "consumivel",
        "efeito": {"mana": 20},
        "bonus": {},
        "classes": [],
        "desc": "Recupera 20 Mana."
    },
    "tablet_hacker": {
        "nome": "Tablet Terminal Hacker",
        "preco": 1900,
        "tipo": "especial",
        "slot": "especial",
        "efeito": {"hack_stun_turns": 2},
        "bonus": {},
        "classes": ["mago", "clerigo"],
        "desc": "Narrativa: hack desativa cibernéticos por 2 turnos."
    },

    "anel_do_vigor": {
        "nome": "Anel do Vigor",
        "tipo": "anel",
        "slot": "anel",
        "preco": 520,
        "bonus": {"atk": 1},
        "desc": "Um anel simples que fortalece o corpo do portador."
    },

    "anel_da_guarda": {
        "nome": "Anel da Guarda",
        "tipo": "anel",
        "slot": "anel",
        "preco": 560,
        "bonus": {"defesa": 1},
        "desc": "Gravado com runas antigas de proteção."
    },

    "anel_da_sabedoria": {
        "nome": "Anel da Sabedoria",
        "tipo": "anel",
        "slot": "anel",
        "preco": 620,
        "bonus": {"magia": 1},
        "desc": "Um cristal antigo amplifica o poder arcano."
    },

    "anel_da_sombra": {
        "nome": "Anel da Sombra",
        "tipo": "anel",
        "slot": "anel",
        "preco": 580,
        "bonus": {"furtividade": 1},
        "desc": "Usado por ladrões e exploradores das ruínas."
    },

    "anel_da_agilidade": {
        "nome": "Anel da Agilidade",
        "tipo": "anel",
        "slot": "anel",
        "preco": 580,
        "bonus": {"destreza": 1},
        "desc": "Leve como o vento, acelera os reflexos."
    },

    "anel_da_sorte_antiga": {
        "nome": "Anel da Sorte Antiga",
        "tipo": "anel",
        "slot": "anel",
        "preco": 650,
        "bonus": {"sorte": 1},
        "desc": "Relíquia de um cassino pré-guerra."
    },

    "anel_de_aco_negro": {
        "nome": "Anel de Aço Negro",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1050,
        "bonus": {"defesa": 2},
        "desc": "Forjado nas fornalhas de um ferreiro antigo."
    },

    "anel_arcano": {
        "nome": "Anel Arcano",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1200,
        "bonus": {"magia": 2},
        "desc": "Amplifica feitiços de magos experientes."
    },

    "anel_do_cacador": {
        "nome": "Anel do Caçador",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1150,
        "bonus": {"atk": 2},
        "desc": "Preferido pelos caçadores das zonas irradiadas."
    },

    "anel_da_luz_sagrada": {
        "nome": "Anel da Luz Sagrada",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1350,
        "bonus": {"magia": 2},
        "desc": "Relíquia usada por clérigos nas antigas catedrais."
    },

    # ====== FERREIRO (armas) ======
    "espada_aco": {
        "nome": "Espada de Aço",
        "preco": 650,
        "tipo": "arma",
        "slot": "arma",
        "efeito": {},
        "bonus": {"atk": 2},
        "classes": ["barbaro", "executor"],
        "loja": "ferreiro",
        "desc": "Aço antigo retemperado. Confiável e letal."
    },
    "machado_sucata": {
        "nome": "Machado de Sucata Reforçado",
        "preco": 900,
        "tipo": "arma",
        "slot": "arma",
        "efeito": {},
        "bonus": {"atk": 3, "destreza": -1},
        "classes": ["barbaro"],
        "loja": "ferreiro",
        "desc": "Pesado. Quando acerta, abre caminho."
    },
    "lamina_executor": {
        "nome": "Lâmina do Executor",
        "preco": 1450,
        "tipo": "arma",
        "slot": "arma",
        "efeito": {},
        "bonus": {"atk": 4, "sorte": 1},
        "classes": ["executor"],
        "loja": "ferreiro",
        "desc": "Equilíbrio perfeito. Feita para terminar lutas rápido."
    },

    # ====== ARCANO (mago / clérigo) ======
    "cajado_condutor": {
        "nome": "Cajado Condutor",
        "preco": 700,
        "tipo": "arma",
        "slot": "arma",
        "efeito": {},
        "bonus": {"magia": 2},
        "classes": ["mago", "clerigo"],
        "loja": "arcano",
        "desc": "Canaliza energia residual do pré-guerra."
    },
    "grimorio_riscado": {
        "nome": "Grimório Riscado",
        "preco": 1200,
        "tipo": "amuleto",
        "slot": "amuleto",
        "efeito": {},
        "bonus": {"magia": 3, "sorte": 1},
        "classes": ["mago"],
        "loja": "arcano",
        "desc": "Anotações em código. Aumenta sua precisão arcana."
    },
    "rosario_bento": {
        "nome": "Rosário Bento",
        "preco": 1100,
        "tipo": "amuleto",
        "slot": "amuleto",
        "efeito": {},
        "bonus": {"magia": 2, "defesa": 1},
        "classes": ["clerigo"],
        "loja": "arcano",
        "desc": "Símbolo de fé. Protege e fortalece rituais."
    },

    # ====== ARMADURAS (loja dedicada) ======
    "couraça_couro": {
        "nome": "Couraça de Couro Remendada",
        "preco": 550,
        "tipo": "armadura",
        "slot": "armadura",
        "efeito": {},
        "bonus": {"defesa": 2},
        "classes": [],
        "loja": "armaduras",
        "desc": "Leve. Boa para começar sem morrer em 2 hits."
    },
    "armadura_malha": {
        "nome": "Armadura de Malha",
        "preco": 1200,
        "tipo": "armadura",
        "slot": "armadura",
        "efeito": {},
        "bonus": {"defesa": 4, "destreza": -1},
        "classes": ["barbaro", "executor"],
        "loja": "armaduras",
        "desc": "Mais proteção, menos agilidade."
    },
    "manto_radioprotecao": {
        "nome": "Manto de Radioproteção",
        "preco": 1350,
        "tipo": "armadura",
        "slot": "armadura",
        "efeito": {},
        "bonus": {"defesa": 3, "magia": 1},
        "classes": ["mago", "clerigo"],
        "loja": "armaduras",
        "desc": "Tecelagem com fibras tratadas. Ideal para conjuradores."
    },

}

INITIAL_SHOP_ACTIVE = [
    ("pocao_vida", None, None),
    ("pocao_mana", None, None),
    ("tablet_hacker", None, None),
]

# ==============================
# FEITIÇOS / ESCOLA (DB)
# ==============================

ESCOLAS_SPELL = {"arcano", "igreja"}

SPELLS_PER_PAGE = 7

INITIAL_SPELLS: Dict[str, Dict[str, Any]] = {
    # ====== ARCANO (mago) ======
    "misseis_sucata": {
        "nome": "Mísseis de Sucata",
        "custo_mana": 6,
        "preco": 420,
        "escola": "arcano",
        "efeito_tipo": "dano",
        "efeito_valor": 12,
        "tags": ["arcano", "metal"],
        "classes": ["mago"],
        "desc": "Projéteis improvisados de metal e energia. Dano moderado."
    },
    "pulso_ionico": {
        "nome": "Pulso Iônico",
        "custo_mana": 8,
        "preco": 520,
        "escola": "arcano",
        "efeito_tipo": "util",
        "efeito_valor": 2,
        "tags": ["cibernético", "diretriz"],
        "classes": ["mago"],
        "desc": "Narrativa: interfere em sistemas cibernéticos por 2 turnos (stun/lock)."
    },
    "barreira_fractal": {
        "nome": "Barreira Fractal",
        "custo_mana": 7,
        "preco": 480,
        "escola": "arcano",
        "efeito_tipo": "buff",
        "efeito_valor": 2,
        "tags": ["defesa", "arcano"],
        "classes": ["mago"],
        "desc": "Conjura proteção: +2 DEF (interpretação via total_stat/efeitos)."
    },

    # ====== IGREJA (clérigo) ======
    "benção_do_aço": {
        "nome": "Bênção do Aço",
        "custo_mana": 6,
        "preco": 430,
        "escola": "igreja",
        "efeito_tipo": "buff",
        "efeito_valor": 2,
        "tags": ["sagrado", "defesa"],
        "classes": ["clerigo"],
        "desc": "Benção protetora: +2 DEF (interpretação via efeitos)."
    },
    "cura_de_campo": {
        "nome": "Cura de Campo",
        "custo_mana": 8,
        "preco": 560,
        "escola": "igreja",
        "efeito_tipo": "cura",
        "efeito_valor": 14,
        "tags": ["sagrado", "cura"],
        "classes": ["clerigo"],
        "desc": "Recupera 14 HP (cura direta)."
    },
    "exorcismo_ruidoso": {
        "nome": "Exorcismo Ruidoso",
        "custo_mana": 10,
        "preco": 720,
        "escola": "igreja",
        "efeito_tipo": "dano",
        "efeito_valor": 16,
        "tags": ["sagrado", "demoníaco"],
        "classes": ["clerigo"],
        "desc": "Dano elevado contra entidades demoníacas (interpretação por tags)."
    },
}

INITIAL_SPELLS_ACTIVE = [
    "misseis_sucata", "barreira_fractal",
    "cura_de_campo", "benção_do_aço"
]


async def spell_upsert(spell_id: str, s: Dict[str, Any]):
    spell_id = spell_id.lower().strip()
    escola = (s.get("escola") or "arcano").lower().strip()
    if escola not in ESCOLAS_SPELL:
        escola = "arcano"

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        INSERT INTO spells(spell_id, nome, custo_mana, preco, escola, efeito_tipo, efeito_valor, tags_json, classes_json, desc, ativo, deleted)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
        ON CONFLICT(spell_id) DO UPDATE SET
            nome=excluded.nome,
            custo_mana=excluded.custo_mana,
            preco=excluded.preco,
            escola=excluded.escola,
            efeito_tipo=excluded.efeito_tipo,
            efeito_valor=excluded.efeito_valor,
            tags_json=excluded.tags_json,
            classes_json=excluded.classes_json,
            desc=excluded.desc
        """, (
            spell_id,
            s.get("nome", spell_id),
            int(s.get("custo_mana", 0)),
            int(s.get("preco", 0)),
            escola,
            s.get("efeito_tipo", "util"),
            int(s.get("efeito_valor", 0)),
            json.dumps(s.get("tags", []), ensure_ascii=False),
            json.dumps(s.get("classes", []), ensure_ascii=False),
            s.get("desc", "")
        ))
        await db.commit()


async def spell_set_active(spell_id: str, ativo: bool):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE spells SET ativo=? WHERE spell_id=? AND deleted=0", (1 if ativo else 0, spell_id.lower().strip()))
        await db.commit()


async def spell_get(spell_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM spells WHERE spell_id=?", (spell_id.lower().strip(),))
        row = await cur.fetchone()
        if not row:
            return None
        s = dict(row)
        s["tags"] = json.loads(s.get("tags_json") or "[]")
        s["classes"] = json.loads(s.get("classes_json") or "[]")
        return s


async def spell_list_active(escola: str, classe: Optional[str] = None) -> List[Dict[str, Any]]:
    escola = (escola or "arcano").lower().strip()
    if escola not in ESCOLAS_SPELL:
        escola = "arcano"

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM spells
            WHERE escola=? AND ativo=1 AND deleted=0
            ORDER BY preco ASC, nome ASC
        """, (escola,))
        rows = await cur.fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        s = dict(r)
        s["tags"] = json.loads(s.get("tags_json") or "[]")
        s["classes"] = json.loads(s.get("classes_json") or "[]")
        if classe and classe not in s["classes"]:
            continue
        out.append(s)
    return out


async def seed_initial_spells():
    for sid, s in INITIAL_SPELLS.items():
        await spell_upsert(sid, s)
    for sid in INITIAL_SPELLS_ACTIVE:
        await spell_set_active(sid, True)


def build_spellshop_embed(escola: str, page: int, spells: List[Dict[str, Any]]) -> discord.Embed:
    total = len(spells)
    total_pages = max(1, (total + SPELLS_PER_PAGE - 1) // SPELLS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * SPELLS_PER_PAGE
    end = start + SPELLS_PER_PAGE
    chunk = spells[start:end]

    titulo = "🔮 Escola Arcana — FEITIÇOS (ativos)" if escola == "arcano" else "⛪ Igreja — LITURGIAS (ativas)"

    embed = discord.Embed(
        title=titulo,
        description=(
            "Use **/aprender spell_id** para comprar e aprender.\n"
            "Depois equipe com **/livro_equipar spell_id** (fora de narração).\n"
        ),
        color=discord.Color.purple()
    )

    for s in chunk:
        sid = s["spell_id"]
        preco = int(s["preco"])
        mana = int(s["custo_mana"])
        et = s.get("efeito_tipo", "util")
        ev = int(s.get("efeito_valor", 0))
        classes = ", ".join(s.get("classes", [])) or "—"
        desc = (s.get("desc") or "").strip()
        if desc:
            desc = desc[:90] + ("…" if len(desc) > 90 else "")

        embed.add_field(
            name=f"**{s['nome']}** (`{sid}`)",
            value=(
                f"💰 **{preco}** | 🔵 Mana **{mana}**\n"
                f"✨ {et.upper()} {ev} | 🎭 {classes}\n"
                f"_{desc}_" if desc else f"✨ {et.upper()} {ev} | 🎭 {classes}"
            ),
            inline=False
        )

    embed.set_footer(text=f"Escola: {escola} • Página {page+1}/{total_pages} • Feitiços {start+1}-{min(end,total)} de {total}")
    return embed


class SpellShopView(discord.ui.View):
    def __init__(self, user_id: int, escola: str, spells: List[Dict[str, Any]], page: int = 0):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.escola = escola
        self.spells = spells
        self.page = page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        await interaction.response.edit_message(embed=build_spellshop_embed(self.escola, self.page, self.spells), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await interaction.response.edit_message(embed=build_spellshop_embed(self.escola, self.page, self.spells), view=self)

    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Escola fechada.", embed=None, view=None)
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        # items catalog
        await db.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            slot TEXT NOT NULL,
            preco INTEGER NOT NULL,
            preco_base INTEGER NOT NULL DEFAULT 0,
            bonus_json TEXT NOT NULL,
            efeito_json TEXT NOT NULL,
            classes_json TEXT NOT NULL,
            desc TEXT NOT NULL,
            loja TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0
        )
        """)

        # migrations: ensure new columns exist on older DBs
        cur = await db.execute("PRAGMA table_info(items)")
        cols = [r[1] for r in await cur.fetchall()]
        if "preco_base" not in cols:
            await db.execute("ALTER TABLE items ADD COLUMN preco_base INTEGER NOT NULL DEFAULT 0")
            await db.execute("UPDATE items SET preco_base = preco WHERE preco_base = 0")



        # migrations: ensure new columns exist on older DBs (players)
        cur = await db.execute("PRAGMA table_info(players)")
        pcols = [r[1] for r in await cur.fetchall()]
        if "rest_until_ts" not in pcols:
            await db.execute("ALTER TABLE players ADD COLUMN rest_until_ts INTEGER NOT NULL DEFAULT 0")
        if "last_hunt_ts" not in pcols:
            await db.execute("ALTER TABLE players ADD COLUMN last_hunt_ts INTEGER NOT NULL DEFAULT 0")
        if "max_stamina" not in pcols:
            await db.execute("ALTER TABLE players ADD COLUMN max_stamina INTEGER NOT NULL DEFAULT 0")
            # best-effort backfill: keep max_stamina aligned with stamina when upgrading old DB
            await db.execute("UPDATE players SET max_stamina = COALESCE(max_stamina, stamina)")
        if "pontos" not in pcols:
            await db.execute("ALTER TABLE players ADD COLUMN pontos INTEGER NOT NULL DEFAULT 0")
        if "stats_json" not in pcols:
            await db.execute("ALTER TABLE players ADD COLUMN stats_json TEXT NOT NULL DEFAULT '{}'") 
        if "inventario_json" not in pcols:
            await db.execute("ALTER TABLE players ADD COLUMN inventario_json TEXT NOT NULL DEFAULT '{}'") 
        if "equipado_json" not in pcols:
            await db.execute("ALTER TABLE players ADD COLUMN equipado_json TEXT NOT NULL DEFAULT '{}'") 
        if "spellbook_json" not in pcols:
            await db.execute("ALTER TABLE players ADD COLUMN spellbook_json TEXT NOT NULL DEFAULT '{}'") 


        await db.execute("CREATE INDEX IF NOT EXISTS idx_items_loja_ativo ON items(loja, ativo, deleted)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_items_tipo ON items(tipo, deleted)")

        # shop
        await db.execute("""
        CREATE TABLE IF NOT EXISTS shop_items (
            item_id TEXT PRIMARY KEY,
            preco INTEGER,
            estoque INTEGER,
            ativo INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(item_id) REFERENCES items(item_id)
        )
        """)

        # master chest
        await db.execute("""
        CREATE TABLE IF NOT EXISTS master_chest (
            item_id TEXT PRIMARY KEY,
            qtd INTEGER NOT NULL,
            FOREIGN KEY(item_id) REFERENCES items(item_id)
        )
        """)

        # spells catalog
        await db.execute("""
        CREATE TABLE IF NOT EXISTS spells (
            spell_id TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            custo_mana INTEGER NOT NULL,
            preco INTEGER NOT NULL,
            escola TEXT NOT NULL,              -- "arcano" ou "igreja"
            efeito_tipo TEXT NOT NULL,         -- "dano", "cura", "buff", "util"
            efeito_valor INTEGER NOT NULL,     -- número (ex: 12)
            tags_json TEXT NOT NULL,           -- ["cibernetico","radiação"...]
            classes_json TEXT NOT NULL,        -- ["mago"] etc
            desc TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0
        )
        """)

        await db.execute("CREATE INDEX IF NOT EXISTS idx_spells_escola_ativo ON spells(escola, ativo, deleted)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_spells_classes ON spells(deleted)")


        # players
        await db.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            classe TEXT NOT NULL,
            level INTEGER NOT NULL,
            xp INTEGER NOT NULL,
            gold INTEGER NOT NULL,
            pontos INTEGER NOT NULL,
            hp INTEGER NOT NULL,
            mana INTEGER NOT NULL,
            stamina INTEGER NOT NULL,
            max_stamina INTEGER NOT NULL,
            rest_until_ts INTEGER NOT NULL DEFAULT 0,
            last_hunt_ts INTEGER NOT NULL DEFAULT 0,
            stats_json TEXT NOT NULL,
            inventario_json TEXT NOT NULL,
            equipado_json TEXT NOT NULL,
            spellbook_json TEXT NOT NULL
        )
        """)

        # Migrações: adiciona colunas novas sem apagar dados (DB antigo)
        cur = await db.execute("PRAGMA table_info(players)")
        cols = {r[1] for r in await cur.fetchall()}
        def addcol(name, ddl):
            return (name not in cols, ddl)
        migs = [
            ("rest_until_ts", "ALTER TABLE players ADD COLUMN rest_until_ts INTEGER NOT NULL DEFAULT 0"),
            ("last_hunt_ts", "ALTER TABLE players ADD COLUMN last_hunt_ts INTEGER NOT NULL DEFAULT 0"),
            ("max_stamina", "ALTER TABLE players ADD COLUMN max_stamina INTEGER NOT NULL DEFAULT 100"),
            ("stats_json", "ALTER TABLE players ADD COLUMN stats_json TEXT NOT NULL DEFAULT '{}'"),
            ("inventario_json", "ALTER TABLE players ADD COLUMN inventario_json TEXT NOT NULL DEFAULT '[]'"),
            ("equipado_json", "ALTER TABLE players ADD COLUMN equipado_json TEXT NOT NULL DEFAULT '{}'"),
            ("spellbook_json", "ALTER TABLE players ADD COLUMN spellbook_json TEXT NOT NULL DEFAULT '[]'"),
        ]
        for name, ddl in migs:
            if name not in cols:
                await db.execute(ddl)


        await db.execute("CREATE INDEX IF NOT EXISTS idx_players_level ON players(level)")
        await db.commit()

# ==============================
# LOJAS / CATÁLOGO (DB driven)
# ==============================

LOJAS_VALIDAS = {"mercador", "ferreiro", "alfaiate", "arcano", "igreja", "armaduras"}

# Itens iniciais (catálogo) - você pode editar aqui no código pra ser mais rápido
INITIAL_ITEMS: Dict[str, Dict[str, Any]] = {
    # ===== CONSUMÍVEIS (Mercador) =====
    "pocao_vida": {
        "nome": "Poção de Vida",
        "preco": 200,
        "tipo": "consumivel",
        "slot": "consumivel",
        "efeito": {"hp": 20},
        "bonus": {},
        "classes": [],
        "desc": "Recupera 20 HP.",
        "loja": "mercador",
    },
    "pocao_mana": {
        "nome": "Poção de Mana",
        "preco": 200,
        "tipo": "consumivel",
        "slot": "consumivel",
        "efeito": {"mana": 20},
        "bonus": {},
        "classes": [],
        "desc": "Recupera 20 Mana.",
        "loja": "mercador",
    },

    # ===== ESPECIAIS (Mercador) =====
    "tablet_hacker": {
        "nome": "Tablet Terminal Hacker",
        "preco": 1900,
        "tipo": "especial",
        "slot": "especial",
        "efeito": {"hack_stun_turns": 2},
        "bonus": {},
        "classes": ["mago", "clerigo"],
        "desc": "Narrativa: hack desativa cibernéticos por 2 turnos.",
        "loja": "mercador",
    },

    # ===== ANÉIS (Ferreiro) =====
    "anel_do_vigor": {
        "nome": "Anel do Vigor",
        "tipo": "anel",
        "slot": "anel",
        "preco": 520,
        "bonus": {"atk": 1},
        "efeito": {},
        "classes": [],
        "desc": "Um anel simples que fortalece o corpo do portador.",
        "loja": "ferreiro",
    },
    "anel_da_guarda": {
        "nome": "Anel da Guarda",
        "tipo": "anel",
        "slot": "anel",
        "preco": 560,
        "bonus": {"defesa": 1},
        "efeito": {},
        "classes": [],
        "desc": "Gravado com runas antigas de proteção.",
        "loja": "ferreiro",
    },
    "anel_da_sabedoria": {
        "nome": "Anel da Sabedoria",
        "tipo": "anel",
        "slot": "anel",
        "preco": 620,
        "bonus": {"magia": 1},
        "efeito": {},
        "classes": [],
        "desc": "Um cristal antigo amplifica o poder arcano.",
        "loja": "arcano",
    },
    "anel_da_sombra": {
        "nome": "Anel da Sombra",
        "tipo": "anel",
        "slot": "anel",
        "preco": 580,
        "bonus": {"furtividade": 1},
        "efeito": {},
        "classes": [],
        "desc": "Usado por ladrões e exploradores das ruínas.",
        "loja": "ferreiro",
    },
    "anel_da_agilidade": {
        "nome": "Anel da Agilidade",
        "tipo": "anel",
        "slot": "anel",
        "preco": 580,
        "bonus": {"destreza": 1},
        "efeito": {},
        "classes": [],
        "desc": "Leve como o vento, acelera os reflexos.",
        "loja": "alfaiate",
    },
    "anel_da_sorte_antiga": {
        "nome": "Anel da Sorte Antiga",
        "tipo": "anel",
        "slot": "anel",
        "preco": 650,
        "bonus": {"sorte": 1},
        "efeito": {},
        "classes": [],
        "desc": "Relíquia de um cassino pré-guerra.",
        "loja": "mercador",
    },
    "anel_de_aco_negro": {
        "nome": "Anel de Aço Negro",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1050,
        "bonus": {"defesa": 2},
        "efeito": {},
        "classes": [],
        "desc": "Forjado nas fornalhas de um ferreiro antigo.",
        "loja": "ferreiro",
    },
    "anel_arcano": {
        "nome": "Anel Arcano",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1200,
        "bonus": {"magia": 2},
        "efeito": {},
        "classes": ["mago"],
        "desc": "Amplifica feitiços de magos experientes.",
        "loja": "arcano",
    },
    "anel_do_cacador": {
        "nome": "Anel do Caçador",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1150,
        "bonus": {"atk": 2},
        "efeito": {},
        "classes": ["arqueiro", "assassino"],
        "desc": "Preferido pelos caçadores das zonas irradiadas.",
        "loja": "ferreiro",
    },
    "anel_da_luz_sagrada": {
        "nome": "Anel da Luz Sagrada",
        "tipo": "anel",
        "slot": "anel",
        "preco": 1350,
        "bonus": {"magia": 2},
        "efeito": {"cura_bonus": 1},
        "classes": ["clerigo"],
        "desc": "Relíquia usada por clérigos nas antigas catedrais.",
        "loja": "igreja",
    },

    # ===== ITENS ARCANOS (Arcano) =====
    "cajado_serpente": {
        "nome": "Cajado da Serpente",
        "preco": 340,
        "tipo": "cajado",
        "slot": "cajado",
        "bonus": {"magia": 2},
        "efeito": {},
        "classes": ["mago", "clerigo"],
        "desc": "+2 MAGIA.",
        "loja": "arcano",
    },
    "grimorio_fissura": {
        "nome": "Grimório da Fissura",
        "preco": 900,
        "tipo": "livro",
        "slot": "especial",
        "bonus": {"magia": 2},
        "efeito": {"mana": 5},
        "classes": ["mago"],
        "desc": "Um tomo pré-guerra que aumenta o foco arcano. +2 MAGIA, +5 Mana máx (efeito).",
        "loja": "arcano",
    },

    # ===== IGREJA (Igreja) =====
    "sino_do_juizo": {
        "nome": "Sino do Juízo",
        "preco": 850,
        "tipo": "reliquia",
        "slot": "especial",
        "bonus": {"defesa": 1},
        "efeito": {"cura_bonus": 2},
        "classes": ["clerigo"],
        "desc": "Ressoa contra o caos. +2 cura (efeito), +1 DEF.",
        "loja": "igreja",
    },
    "livro_hinos": {
        "nome": "Livro de Hinos",
        "preco": 500,
        "tipo": "livro",
        "slot": "especial",
        "bonus": {"magia": 1},
        "efeito": {"cura_bonus": 1},
        "classes": ["clerigo"],
        "desc": "Cantos antigos amplificam bençãos. +1 MAGIA, +1 cura.",
        "loja": "igreja",
    },
}

# Quais itens começam "ativos" na vitrine (o resto existe, mas fica desativado até você ativar)
INITIAL_ACTIVE_IDS = [
    "pocao_vida", "pocao_mana", "tablet_hacker",
    # Novas lojas
    "espada_aco", "machado_sucata", "lamina_executor",
    "cajado_condutor", "grimorio_riscado", "rosario_bento",
    "couraça_couro", "armadura_malha", "manto_radioprotecao",
    # Anéis (ativos pra já aparecer)
    "anel_do_vigor", "anel_da_guarda", "anel_da_sabedoria", "anel_da_sorte_antiga",
    # Arcano/Igreja
    "cajado_serpente", "livro_hinos"
]


async def item_upsert(item_id: str, it: Dict[str, Any]):
    loja = (it.get("loja") or "mercador").lower().strip()
    if loja not in LOJAS_VALIDAS:
        loja = "mercador"

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        INSERT INTO items(item_id, nome, tipo, slot, preco, bonus_json, efeito_json, classes_json, desc, loja, ativo, deleted)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
        ON CONFLICT(item_id) DO UPDATE SET
            nome=excluded.nome,
            tipo=excluded.tipo,
            slot=excluded.slot,
            preco=excluded.preco,
            bonus_json=excluded.bonus_json,
            efeito_json=excluded.efeito_json,
            classes_json=excluded.classes_json,
            desc=excluded.desc,
            loja=excluded.loja
        """, (
            item_id,
            it.get("nome", item_id),
            it.get("tipo", "especial"),
            it.get("slot", it.get("tipo", "especial")),
            int(it.get("preco", 0)),
            json.dumps(it.get("bonus", {}), ensure_ascii=False),
            json.dumps(it.get("efeito", {}), ensure_ascii=False),
            json.dumps(it.get("classes", []), ensure_ascii=False),
            it.get("desc", ""),
            loja
        ))
        await db.commit()


async def item_set_active(item_id: str, ativo: bool):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE items SET ativo=? WHERE item_id=? AND deleted=0", (1 if ativo else 0, item_id))
        await db.commit()


async def item_get(item_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM items WHERE item_id=?", (item_id,))
        row = await cur.fetchone()
        if not row:
            return None
        it = dict(row)
        it["bonus"] = json.loads(it.get("bonus_json") or "{}")
        it["efeito"] = json.loads(it.get("efeito_json") or "{}")
        it["classes"] = json.loads(it.get("classes_json") or "[]")
        return it


async def seed_initial_data():
    """
    Garante que todo o catálogo padrão exista no banco e fique visível nas lojas.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        for item_id, it in INITIAL_ITEMS.items():
            loja = (it.get("loja") or "mercador").lower().strip()
            if loja not in LOJAS_VALIDAS:
                loja = "mercador"
            await db.execute("""
                INSERT INTO items (
                    item_id, nome, tipo, slot, preco, preco_base,
                    bonus_json, efeito_json, classes_json, desc, loja, ativo, deleted
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0)
                ON CONFLICT(item_id) DO UPDATE SET
                    nome=excluded.nome,
                    tipo=excluded.tipo,
                    slot=excluded.slot,
                    preco=excluded.preco,
                    preco_base=excluded.preco_base,
                    bonus_json=excluded.bonus_json,
                    efeito_json=excluded.efeito_json,
                    classes_json=excluded.classes_json,
                    desc=excluded.desc,
                    loja=excluded.loja,
                    ativo=1,
                    deleted=0
            """, (
                item_id,
                it.get("nome", item_id),
                it.get("tipo", "especial"),
                it.get("slot", it.get("tipo", "especial")),
                int(it.get("preco", 0)),
                int(it.get("preco", 0)),
                jdump(it.get("bonus", {})),
                jdump(it.get("efeito", {})),
                jdump(it.get("classes", [])),
                it.get("desc", "") or "",
                loja,
            ))

            # shop_items como espelho visível de tudo, com estoque infinito (NULL)
            await db.execute("""
                INSERT INTO shop_items (item_id, preco, estoque, ativo)
                VALUES (?, ?, NULL, 1)
                ON CONFLICT(item_id) DO UPDATE SET
                    preco=excluded.preco,
                    ativo=1
            """, (item_id, int(it.get("preco", 0))))

        await db.commit()

# ==============================
# PLAYER CRUD
# ==============================

def ensure_equipado_format(eq: dict) -> dict:
    if not isinstance(eq, dict):
        eq = {}
    # Slots
    eq.setdefault("arma", None)
    eq.setdefault("armadura", None)
    eq.setdefault("elmo", None)
    eq.setdefault("botas", None)
    eq.setdefault("luvas", None)
    eq.setdefault("cajado", None)
    eq.setdefault("especial", None)
    eq.setdefault("implante", None)        # slot novo (mestre-only)
    eq.setdefault("livro_magias", None)    # slot novo (item físico opcional, se quiser)

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
        await db.execute("""
        INSERT INTO players (
            user_id, classe, level, xp, gold, pontos, hp, mana, stamina, max_stamina,
            rest_until_ts, last_hunt_ts, stats_json, inventario_json, equipado_json, spellbook_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            classe=excluded.classe,
            level=excluded.level,
            xp=excluded.xp,
            gold=excluded.gold,
            pontos=excluded.pontos,
            hp=excluded.hp,
            mana=excluded.mana,
            stamina=excluded.stamina,
            max_stamina=excluded.max_stamina,
            rest_until_ts=excluded.rest_until_ts,
            last_hunt_ts=excluded.last_hunt_ts,
            stats_json=excluded.stats_json,
            inventario_json=excluded.inventario_json,
            equipado_json=excluded.equipado_json,
            spellbook_json=excluded.spellbook_json
        """, (
            p["user_id"], p["classe"], int(p["level"]), int(p["xp"]), int(p["gold"]), int(p.get("pontos", 0)),
            int(p["hp"]), int(p["mana"]), int(p["stamina"]), int(p["max_stamina"]),
            int(p.get("rest_until_ts", 0)), int(p.get("last_hunt_ts", 0)),
            jdump(p.get("stats", {})),
            jdump(p.get("inventario", [])),
            jdump(p.get("equipado", {})),
            jdump(p.get("spellbook", [])),
        ))
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
        it["bonus"] = jload(it.get("bonus_json"), {})
        it["efeito"] = jload(it.get("efeito_json"), {})
        it["classes"] = jload(it.get("classes_json"), [])
        return it

async def item_exists_active(item_id: str) -> bool:
    it = await item_get(item_id)
    return bool(it) and int(it.get("deleted", 0)) == 0


async def shop_list_active() -> List[dict]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM items
            WHERE deleted=0
            ORDER BY nome COLLATE NOCASE
        """)
        rows = await cur.fetchall()
        out = []
        for r in rows:
            it = dict(r)
            it["preco_loja"] = int(it.get("preco", 0))
            it["estoque"] = None
            it["ativo"] = 1
            it["bonus"] = jload(it.get("bonus_json"), {})
            it["efeito"] = jload(it.get("efeito_json"), {})
            it["classes"] = jload(it.get("classes_json"), [])
            out.append(it)
        return out


async def items_list_active(loja: str) -> List[dict]:
    loja = (loja or "mercador").lower().strip()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM items
            WHERE deleted=0 AND loja=?
            ORDER BY preco ASC, nome COLLATE NOCASE
        """, (loja,))
        rows = await cur.fetchall()
        out = []
        for r in rows:
            it = dict(r)
            it["preco_loja"] = int(it.get("preco", 0))
            it["estoque"] = None
            it["ativo"] = 1
            it["bonus"] = jload(it.get("bonus_json"), {})
            it["efeito"] = jload(it.get("efeito_json"), {})
            it["classes"] = jload(it.get("classes_json"), [])
            out.append(it)
        return out

def shop_price(it: dict) -> int:
    p = it.get("preco_loja")
    if p is None:
        return int(it.get("preco_base", 0))
    return int(p)


async def shop_is_active(item_id: str) -> bool:
    it = await item_get(item_id)
    return bool(it) and int(it.get("deleted", 0)) == 0


async def shop_decrease_stock(item_id: str, n: int = 1) -> bool:
    # Estoque infinito por padrão para a loja principal
    return True

async def master_chest_add(item_id: str, qtd: int):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT qtd FROM master_chest WHERE item_id=?", (item_id,))
        row = await cur.fetchone()
        if not row:
            await db.execute("INSERT INTO master_chest (item_id, qtd) VALUES (?, ?)", (item_id, qtd))
        else:
            await db.execute("UPDATE master_chest SET qtd=? WHERE item_id=?", (int(row[0]) + qtd, item_id))
        await db.commit()

async def master_chest_remove(item_id: str, qtd: int) -> bool:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT qtd FROM master_chest WHERE item_id=?", (item_id,))
        row = await cur.fetchone()
        if not row:
            return False
        have = int(row[0])
        if have < qtd:
            return False
        left = have - qtd
        if left <= 0:
            await db.execute("DELETE FROM master_chest WHERE item_id=?", (item_id,))
        else:
            await db.execute("UPDATE master_chest SET qtd=? WHERE item_id=?", (left, item_id))
        await db.commit()
        return True

async def master_chest_list() -> List[Tuple[str, int]]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT item_id, qtd FROM master_chest ORDER BY item_id")
        return [(r[0], int(r[1])) for r in await cur.fetchall()]

# ==============================
# MAGIAS / LIVRO
# ==============================

async def spell_get(spell_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM spells WHERE spell_id=?", (spell_id,))
        row = await cur.fetchone()
        if not row:
            return None
        s = dict(row)
        s["classes"] = jload(s.get("classes_json"), [])
        return s

async def spell_exists_active(spell_id: str) -> bool:
    s = await spell_get(spell_id)
    return bool(s) and int(s.get("deleted", 0)) == 0

async def spell_list_for_class(classe: str) -> List[dict]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM spells WHERE deleted=0 ORDER BY nome COLLATE NOCASE")
        rows = await cur.fetchall()
        out = []
        for r in rows:
            s = dict(r)
            s["classes"] = jload(s.get("classes_json"), [])
            if classe in s["classes"]:
                out.append(s)
        return out

# ==============================
# STATS + EQUIPAMENTOS (bonus vem dos itens do DB)
# ==============================

def iter_equips(p: dict):
    eq = p.get("equipado") or {}
    for slot in ["arma", "armadura", "elmo", "botas", "luvas", "cajado", "especial", "implante", "livro_magias"]:
        iid = eq.get(slot)
        if iid:
            yield iid
    for iid in eq.get("aneis", []) or []:
        if iid:
            yield iid

async def total_stat(p: dict, stat: str) -> int:
    base = int((p.get("stats") or {}).get(stat, 0))
    for item_id in iter_equips(p):
        it = await item_get(item_id)
        if not it or int(it.get("deleted", 0)) == 1:
            continue
        bonus = it.get("bonus", {}) or {}
        base += int(bonus.get(stat, 0) or 0)
        if stat == "cura":
            efeito = it.get("efeito", {}) or {}
            base += int(efeito.get("cura_bonus", 0) or 0)
    return base

# ==============================
# LEVEL UP (auto em loop)
# ==============================

async def apply_level_up_once(p: dict):
    p["level"] = int(p["level"]) + 1
    new_level = int(p["level"])

    # 3 pontos livres pendentes
    p["pontos"] = int(p.get("pontos", 0)) + 3

    # +1 automático por classe
    auto_attr = AUTO_UP.get(p["classe"])
    if auto_attr:
        p["stats"][auto_attr] = int(p["stats"].get(auto_attr, 0)) + 1

    # HP/Mana automáticos e progressivos
    p["hp"] = int(p["hp"]) + hp_gain(p["classe"], new_level)
    p["mana"] = int(p["mana"]) + mana_gain(p["classe"], new_level)

async def try_auto_level(p: dict) -> int:
    upou = 0
    while True:
        if int(p["level"]) >= 100:
            break
        custo = xp_para_upar(int(p["level"]))
        if int(p["xp"]) < custo:
            break
        p["xp"] -= custo
        await apply_level_up_once(p)
        upou += 1
    if upou:
        await save_player(p)
    return upou

# ==============================
# CRIAÇÃO DE PERSONAGEM
# ==============================

def build_new_player(user_id: int, classe: str) -> dict:
    base = CLASSES[classe].copy()
    return {
        "user_id": user_id,
        "classe": classe,
        "level": 1,
        "xp": 0,
        "gold": 100,
        "pontos": 0,
        "hp": int(base["hp_base"]),
        "mana": int(base["mana_base"]),
        "stamina": STAMINA_MAX,
        "max_stamina": STAMINA_MAX,
        "rest_until_ts": 0,
        "last_hunt_ts": 0,
        "stats": base,
        "inventario": [],
        "equipado": ensure_equipado_format({}),
        "spellbook": [],
    }


class ClasseSelect(discord.ui.Select):
    def __init__(self):
        opts = []
        for cls, st in CLASSES.items():
            opts.append(discord.SelectOption(
                label=cls.capitalize(),
                value=cls,
                description=f"HP {st['hp_base']} | Mana {st['mana_base']} | ATK {st['atk']} | MAG {st['magia']} | DEF {st['defesa']}"
            ))

        super().__init__(
            placeholder="Escolha sua classe…",
            min_values=1,
            max_values=1,
            options=opts,
            custom_id="classe_select_v1"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            if interaction.channel_id != CANAL_BEM_VINDO_ID:
                await interaction.followup.send("❌ Criação de personagem só no canal de **bem-vindo**.", ephemeral=True)
                return

            existing = await get_player(interaction.user.id)
            if existing:
                await interaction.followup.send("⚠️ Você já tem personagem. Use **/perfil**.", ephemeral=True)
                return

            classe = self.values[0]
            p = build_new_player(interaction.user.id, classe)
            await save_player(p)

            embed = discord.Embed(
                title="✅ Registro Concluído",
                description=(
                    f"**{interaction.user.mention}** agora é **{classe.upper()}**.\n\n"
                    f"⭐ Nível: **1**\n"
                    f"❤ HP: **{p['hp']}** | 🔵 Mana: **{p['mana']}**\n"
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


@tree.command(name="start", description="Criar seu personagem.")
async def start_cmd(interaction: discord.Interaction):
    existente = await get_player(interaction.user.id)
    if existente:
        await interaction.response.send_message("⚠️ Você já tem personagem. Use **/perfil**.", ephemeral=True)
        return

    if interaction.channel_id != CANAL_BEM_VINDO_ID:
        await interaction.response.send_message(
            "❌ Criação de personagem só no canal de **bem-vindo**.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "🧬 **Criação de personagem**\nEscolha sua classe no menu abaixo.",
        view=ClasseView(),
        ephemeral=True
    )


@tree.command(name="spaw", description="(Mestre) Criar personagem para outro jogador.")
@only_master_channel()
@app_commands.describe(jogador="Jogador alvo", classe="Classe do personagem")
async def spaw_cmd(interaction: discord.Interaction, jogador: discord.Member, classe: str):
    classe_key = (classe or "").strip().lower()
    if classe_key not in CLASSES:
        validas = ", ".join(sorted([c.upper() for c in CLASSES.keys()]))
        await interaction.response.send_message(
            f"❌ Classe inválida. Use uma destas: {validas}.",
            ephemeral=True
        )
        return

    existente = await get_player(jogador.id)
    if existente:
        await interaction.response.send_message("❌ Esse jogador já possui personagem.", ephemeral=True)
        return

    novo = build_new_player(jogador.id, classe_key)
    await save_player(novo)
    await interaction.response.send_message(
        f"✅ Personagem criado para {jogador.mention}.\n\nClasse: {classe_key.upper()}\nNível: 1",
        ephemeral=True
    )


@tree.command(name="reset", description="(Mestre) Resetar o personagem de um jogador.")
@only_master_channel()
@app_commands.describe(jogador="Jogador alvo")
async def reset_cmd(interaction: discord.Interaction, jogador: discord.Member):
    existente = await get_player(jogador.id)
    if not existente:
        await interaction.response.send_message("❌ Esse jogador não possui personagem para resetar.", ephemeral=True)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM players WHERE user_id=?", (jogador.id,))
        await db.commit()

    await interaction.response.send_message(
        f"♻️ Personagem de {jogador.mention} resetado com sucesso.",
        ephemeral=True
    )


@tree.command(name="restart", description="(Mestre) Reiniciar o personagem de um jogador.")
@only_master_channel()
@app_commands.describe(jogador="Jogador alvo")
async def restart_cmd(interaction: discord.Interaction, jogador: discord.Member):
    existente = await get_player(jogador.id)
    if not existente:
        await interaction.response.send_message("❌ Esse jogador não possui personagem para resetar.", ephemeral=True)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM players WHERE user_id=?", (jogador.id,))
        await db.commit()

    await interaction.response.send_message(
        f"♻️ Personagem de {jogador.mention} resetado com sucesso.",
        ephemeral=True
    )

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
        key = it["item_id"]
        preco = shop_price(it)
        tipo = it.get("tipo", "—")
        desc = (it.get("desc", "") or "").strip()
        estoque = it.get("estoque", None)

        if tipo == "consumivel":
            eff = it.get("efeito", {}) or {}
            eff_txt = ", ".join([f"{k}+{v}" for k, v in eff.items()]) if eff else "—"
            val = f"💰 **{preco}** | 🧪 {eff_txt}"
        else:
            bonus = it.get("bonus", {}) or {}
            btxt = ", ".join([f"{k.upper()}+{v}" for k, v in bonus.items()]) if bonus else "—"
            val = f"💰 **{preco}** | ⚙️ **{tipo}** | {btxt}"

        if estoque is not None:
            val += f"\n📦 Estoque: **{int(estoque)}**"

        if desc:
            desc = desc[:80] + ("…" if len(desc) > 80 else "")
            val += f"\n_{desc}_"

        embed.add_field(name=f"**{it.get('nome','Item')}** (`{key}`)", value=val, inline=False)

    embed.set_footer(text=f"Página {page+1}/{total_pages} • Itens {start+1}-{min(end,total)} de {total}")
    return embed

class LojaView(discord.ui.View):
    def __init__(self, user_id: int, page: int = 0):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.page = page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        await interaction.response.edit_message(embed=await build_loja_embed(self.page), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await interaction.response.edit_message(embed=await build_loja_embed(self.page), view=self)

    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Loja fechada.", embed=None, view=None)

# ==============================
# VIEW: BANDIDOS
# ==============================

class BandidosView(discord.ui.View):
    def __init__(self, user_id: int, forca: int):
        super().__init__(timeout=45)
        self.user_id = user_id
        self.forca = forca

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Pagar 100 gold", style=discord.ButtonStyle.secondary, emoji="💰")
    async def pagar(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = await get_player(interaction.user.id)
        if not p:
            await interaction.response.send_message("⚠️ Use **/start** primeiro.", ephemeral=True)
            return
        if int(p["gold"]) < 100:
            await interaction.response.send_message("❌ Você não tem 100 gold. Terá que lutar.", ephemeral=True)
            return
        p["gold"] -= 100
        await save_player(p)
        await interaction.response.send_message("💰 Você pagou. Os bandidos foram embora.", ephemeral=False)

    @discord.ui.button(label="Lutar", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def lutar(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = await get_player(interaction.user.id)
        if not p:
            await interaction.response.send_message("⚠️ Use **/start** primeiro.", ephemeral=True)
            return

        d20 = rolar_d20()
        dc = 11 + self.forca
        venceu = d20 >= dc

        defesa = await total_stat(p, "defesa")
        dano_recebido = max(4, (12 + self.forca * 3) - defesa)

        if venceu:
            xp = 60 + self.forca * 20
            gold = 120 + self.forca * 40
            p["xp"] += xp
            p["gold"] += gold
            upou = await try_auto_level(p)
            await save_player(p)
            await interaction.response.send_message(
                f"🎲 D20: **{d20}** (DC {dc})\n"
                f"🏆 Você venceu os bandidos!\n"
                f"✨ +{xp} XP | 💰 +{gold} Gold"
                + (f"\n🆙 UPOU {upou} nível(is)!" if upou else ""),
                ephemeral=False
            )
        else:
            p["hp"] = max(0, int(p["hp"]) - dano_recebido)
            await save_player(p)
            await interaction.response.send_message(
                f"🎲 D20: **{d20}** (DC {dc})\n"
                f"💀 Você perdeu a luta.\n"
                f"💥 Dano: **{dano_recebido}**\n"
                f"❤ HP agora: **{p['hp']}**",
                ephemeral=False
            )

# ==============================
# COMANDOS — JOGADOR
# ==============================

def _fmt_list(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return "—"
    return ", ".join([str(x) for x in items])


async def build_profile_embed(p: dict, owner_name: str, owner_mention: str) -> discord.Embed:
    stats = p.get("stats") or {}
    equipado = ensure_equipado_format(p.get("equipado") or {})
    spellbook = p.get("spellbook") or []
    level = int(p.get("level", 1))
    xp_atual = int(p.get("xp", 0))
    xp_next = int(xp_para_upar(level))

    base_atk = int(stats.get("atk", 0))
    base_def = int(stats.get("defesa", 0))
    base_mag = int(stats.get("magia", 0))
    base_dex = int(stats.get("destreza", 0))
    base_sorte = int(stats.get("sorte", 0))
    base_furt = int(stats.get("furtividade", 0))

    total_atk = await total_stat(p, "atk")
    total_def = await total_stat(p, "defesa")
    total_mag = await total_stat(p, "magia")
    total_dex = await total_stat(p, "destreza")
    total_sorte = await total_stat(p, "sorte")
    total_furt = await total_stat(p, "furtividade")

    embed = discord.Embed(
        title=f"👤 Perfil — {owner_name}",
        description=f"Jogador: {owner_mention}",
        color=discord.Color.blurple()
    )

    embed.add_field(name="Classe", value=str(p.get("classe", "—")).capitalize(), inline=True)
    embed.add_field(name="Nível", value=f"{level} (XP {xp_atual}/{xp_next})", inline=True)
    embed.add_field(name="Gold", value=f"💰 {int(p.get('gold', 0))}", inline=True)

    embed.add_field(
        name="Status",
        value=(
            f"❤️ HP: {int(p.get('hp', 0))}\n"
            f"🔵 Mana: {int(p.get('mana', 0))}\n"
            f"🥵 Stamina: {int(p.get('stamina', 0))}/{int(p.get('max_stamina', STAMINA_MAX))}\n"
            f"⭐ Pontos pendentes: {int(p.get('pontos', 0))}"
        ),
        inline=False
    )

    embed.add_field(
        name="Atributos (com bônus)",
        value=(
            f"⚔️ ATK: {total_atk} ({base_atk:+d} base, {total_atk - base_atk:+d} bônus)\n"
            f"🛡️ DEF: {total_def} ({base_def:+d} base, {total_def - base_def:+d} bônus)\n"
            f"✨ MAG: {total_mag} ({base_mag:+d} base, {total_mag - base_mag:+d} bônus)\n"
            f"🎯 DEX: {total_dex} ({base_dex:+d} base, {total_dex - base_dex:+d} bônus)\n"
            f"🍀 SORTE: {total_sorte} ({base_sorte:+d} base, {total_sorte - base_sorte:+d} bônus)\n"
            f"🥷 FURT: {total_furt} ({base_furt:+d} base, {total_furt - base_furt:+d} bônus)"
        ),
        inline=False
    )

    eq_lines = [
        f"🗡️ Arma: {equipado.get('arma') or '—'}",
        f"🛡️ Armadura: {equipado.get('armadura') or '—'}",
        f"🪖 Elmo: {equipado.get('elmo') or '—'}",
        f"👢 Botas: {equipado.get('botas') or '—'}",
        f"🧤 Luvas: {equipado.get('luvas') or '—'}",
        f"🔮 Cajado: {equipado.get('cajado') or '—'}",
        f"🧩 Especial: {equipado.get('especial') or '—'}",
        f"🧬 Implante: {equipado.get('implante') or '—'}",
        f"📖 Livro (item): {equipado.get('livro_magias') or '—'}",
    ]
    embed.add_field(name="Equipado (IDs)", value="\n".join(eq_lines), inline=False)

    aneis = list(equipado.get("aneis") or [])
    while len(aneis) < 8:
        aneis.append(None)
    aneis = aneis[:8]
    aneis_lines = [f"{i+1}. {aneis[i] or '—'}" for i in range(8)]
    embed.add_field(name="💍 Anéis (1-8)", value="\n".join(aneis_lines), inline=False)

    embed.add_field(name="✨ Spellbook", value=_fmt_list(spellbook), inline=False)

    extras = []
    for k in ["especializacao", "perks", "sanidade", "corrupcao", "regiao", "regiao_atual"]:
        if k in p and p.get(k) not in (None, "", [], {}):
            val = p.get(k)
            if isinstance(val, list):
                val = _fmt_list(val)
            extras.append(f"{k}: **{val}**")
    if extras:
        embed.add_field(name="🧠 Extras", value="\n".join(extras), inline=False)

    return embed


@tree.command(name="perfil", description="Ver sua ficha atual.")
async def perfil_cmd(interaction: discord.Interaction):
    p = await get_player(interaction.user.id)
    if not p:
        await interaction.response.send_message("⚠️ Você ainda não tem personagem. Use /start.", ephemeral=True)
        return
    embed = await build_profile_embed(p, interaction.user.display_name, interaction.user.mention)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="bau", description="Ver itens guardados (não equipados).")
async def bau_cmd(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return

    inv = [str(i) for i in (p.get("inventario") or []) if i]
    if not inv:
        await interaction.response.send_message(f"📦 Baú de {interaction.user.display_name}\n\n(sem itens guardados)", ephemeral=True)
        return

    eq = ensure_equipado_format(p.get("equipado") or {})
    equipped_ids = set()
    for slot in ["arma", "armadura", "elmo", "botas", "luvas", "cajado", "especial", "implante", "livro_magias"]:
        iid = eq.get(slot)
        if iid:
            equipped_ids.add(str(iid))
    for iid in (eq.get("aneis") or []):
        if iid:
            equipped_ids.add(str(iid))

    guardados = [iid for iid in inv if iid not in equipped_ids]
    if not guardados:
        await interaction.response.send_message(f"📦 Baú de {interaction.user.display_name}\n\n(sem itens não equipados)", ephemeral=True)
        return

    counts = Counter(guardados)
    lines = []
    for item_id, qtd in sorted(counts.items()):
        it = await item_get(item_id)
        nome = (it or {}).get("nome") if it else None
        if nome:
            line = f"• {nome} (`{item_id}`)"
        else:
            line = f"• {item_id}"
        if qtd > 1:
            line += f" x{qtd}"
        lines.append(line)

    await interaction.response.send_message(
        f"📦 Baú de {interaction.user.display_name}\n\n" + "\n".join(lines[:60]),
        ephemeral=True
    )


# Loja

# Upar atributos (SEM hp_base/mana_base e sem stamina)

@tree.command(name="upar", description="Gastar pontos para aumentar um atributo.")
@app_commands.describe(
    atributo="atk|magia|defesa|sorte|furtividade|destreza",
    quantidade="Quantidade de pontos para gastar"
)
async def upar_cmd(interaction: discord.Interaction, atributo: str, quantidade: int):
    p = await require_player(interaction)
    if not p:
        return

    pontos = int(p.get("pontos", 0))
    if pontos <= 0:
        await interaction.response.send_message(
            "❌ Você não possui pontos pendentes para distribuir.",
            ephemeral=True
        )
        return

    if quantidade <= 0:
        await interaction.response.send_message(
            "❌ A quantidade deve ser maior que 0.",
            ephemeral=True
        )
        return

    if quantidade > pontos:
        await interaction.response.send_message(
            f"❌ Você só possui {pontos} ponto(s) pendente(s).",
            ephemeral=True
        )
        return

    aliases = {
        "atk": "atk",
        "ataque": "atk",
        "magia": "magia",
        "mag": "magia",
        "defesa": "defesa",
        "def": "defesa",
        "sorte": "sorte",
        "furtividade": "furtividade",
        "furt": "furtividade",
        "destreza": "destreza",
        "dex": "destreza",
    }

    key = aliases.get((atributo or "").strip().lower())
    if key is None:
        await interaction.response.send_message(
            "❌ Atributo inválido. Use: atk, magia, defesa, sorte, furtividade ou destreza.",
            ephemeral=True
        )
        return

    p.setdefault("stats", {})
    p["stats"][key] = int(p["stats"].get(key, 0)) + quantidade
    p["pontos"] = pontos - quantidade
    await save_player(p)

    await interaction.response.send_message(
        f"✅ **{key.upper()}** aumentado em +{quantidade}.\n⭐ Pontos restantes: **{p['pontos']}**",
        ephemeral=True
    )


# Trade

# Descansar / Albergue
@tree.command(name="albergue", description="Hospedar-se no albergue para descansar (2h).")
async def albergue_cmd(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return

    agora = now_ts()
    rest_until = int(p.get("rest_until_ts", 0))
    if agora < rest_until:
        falta = rest_until - agora
        horas = falta // 3600
        minutos = (falta % 3600) // 60
        await interaction.response.send_message(
            f"⛺ Você já está descansando. Volte em aproximadamente {horas}h {minutos:02d}min.",
            ephemeral=True,
        )
        return

    if int(p.get("gold", 0)) < ALBERGUE_CUSTO_FIXO:
        await interaction.response.send_message(
            "❌ Você precisa de 150 gold para se hospedar no albergue.",
            ephemeral=True,
        )
        return

    p["gold"] = int(p.get("gold", 0)) - ALBERGUE_CUSTO_FIXO
    p["rest_until_ts"] = agora + (ALBERGUE_DESCANSO_HORAS * 3600)
    p["stamina"] = int(p.get("max_stamina", STAMINA_MAX))
    await save_player(p)

    await interaction.response.send_message(
        "🛏️ Você se hospedou no albergue.\n"
        "💰 -150 gold\n"
        "⚡ Stamina totalmente restaurada.\n"
        "⏳ Você ficará descansando por 2 horas.",
        ephemeral=False,
    )

# ==============================
# MAGIAS (Jogador) — Livro de Magias
# ==============================


# ==============================
# /CACAR — D20 AUTOMÁTICO
# ==============================

def pick_weighted_monster() -> Dict[str, Any]:
    entries = list(MONSTROS.values())
    pesos = [max(1, int(e.get("peso", 1))) for e in entries]
    return random.choices(entries, weights=pesos, k=1)[0]


async def cacar_turn(p: dict, monstro: Dict[str, Any], monster_hp: int) -> Tuple[int, int, int, bool]:
    atk_total = await total_stat(p, "atk")
    magia_total = await total_stat(p, "magia")
    defesa_total = await total_stat(p, "defesa")
    destreza_total = await total_stat(p, "destreza")
    sorte_total = await total_stat(p, "sorte")

    dano_jogador = max(1, random.randint(1, 8) + atk_total + (magia_total // 4) + (destreza_total // 6) + (sorte_total // 8) - 3)
    monster_hp = max(0, int(monster_hp) - dano_jogador)

    dano_monstro = 0
    forced_retreat = False
    if monster_hp > 0:
        dano_monstro = max(1, random.randint(1, 6) + int(monstro.get("atk", 1)) - (defesa_total // 2))
        p["hp"] = int(p.get("hp", 1)) - dano_monstro
        if int(p["hp"]) <= 0:
            p["hp"] = 1
            forced_retreat = True

    return monster_hp, dano_jogador, dano_monstro, forced_retreat


class CacarFightView(discord.ui.View):
    def __init__(self, user_id: int, monstro: Dict[str, Any], monster_hp: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.monstro = monstro
        self.monster_hp = int(monster_hp)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Este combate não é seu.", ephemeral=True)
            return False
        return True

    def _disable_all(self):
        for c in self.children:
            c.disabled = True

    @discord.ui.button(label="Recuar", style=discord.ButtonStyle.secondary, emoji="🏃")
    async def recuar(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = await get_player(self.user_id)
        if not p:
            self._disable_all()
            await interaction.response.edit_message(content="⚠️ Personagem não encontrado. Combate encerrado.", view=self)
            return

        p["xp"] = max(0, int(p.get("xp", 0)) - 50)
        await save_player(p)
        self._disable_all()
        await interaction.response.edit_message(
            content=(
                "🏃 Você recuou da batalha.\n"
                "❌ -50 XP"
            ),
            view=self
        )

    @discord.ui.button(label="Atacar novamente", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def atacar_novamente(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = await get_player(self.user_id)
        if not p:
            self._disable_all()
            await interaction.response.edit_message(content="⚠️ Personagem não encontrado. Combate encerrado.", view=self)
            return

        self.monster_hp, dano_j, dano_m, forced = await cacar_turn(p, self.monstro, self.monster_hp)

        if self.monster_hp <= 0:
            xp = int(self.monstro.get("xp", 10))
            gold = int(self.monstro.get("gold", 8))
            p["xp"] = int(p.get("xp", 0)) + xp
            p["gold"] = int(p.get("gold", 0)) + gold

            drop_txt = ""
            if random.random() < DROP_RARO_CHANCE:
                drop = await pick_drop_from_pool(DROP_POOL_RARO)
                if drop:
                    p.setdefault("inventario", []).append(drop["item_id"])
                    drop_txt = f"\n🎁 Drop raro: **{drop['nome']}** (`{drop['item_id']}`)"

            upou = await try_auto_level(p)
            await save_player(p)
            self._disable_all()
            await interaction.response.edit_message(
                content=(
                    f"⚔️ Você derrotou **{self.monstro['nome']}**!\n"
                    f"🩸 Dano no último turno: **{dano_j}**\n"
                    f"✨ +{xp} XP | 💰 +{gold} Gold"
                    + (f"\n🆙 UPOU {upou} nível(is)!" if upou else "")
                    + drop_txt
                ),
                view=self
            )
            return

        if forced:
            await save_player(p)
            self._disable_all()
            await interaction.response.edit_message(
                content=(
                    f"💀 Você foi levado ao limite contra **{self.monstro['nome']}**.\n"
                    f"🩸 Dano recebido no último turno: **{dano_m}**\n"
                    f"❤ Você ficou com **1 HP** e foi forçado a recuar."
                ),
                view=self
            )
            return

        await save_player(p)
        await interaction.response.edit_message(
            content=(
                f"⚔️ Combate continua contra **{self.monstro['nome']}**!\n"
                f"🩸 Você causou **{dano_j}** | recebeu **{dano_m}**\n"
                f"👾 HP do monstro: **{self.monster_hp}**\n"
                f"❤ Seu HP: **{p['hp']}**"
            ),
            view=self
        )


@tree.command(name="cacar", description="Sair para caçar criaturas nas ruínas.")
@only_channel(CANAL_CACAR_ID, "cacar")
async def cacar_cmd(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return
    if await blocked_by_rest(interaction, p):
        return
    if await blocked_by_narration(interaction):
        return

    agora = now_ts()
    restante_cd = int(p.get("last_hunt_ts", 0)) + CACAR_COOLDOWN_S - agora
    if restante_cd > 0:
        await interaction.response.send_message(
            f"⏳ Aguarde **{restante_cd}s** para caçar novamente.",
            ephemeral=True,
        )
        return

    stamina = int(p.get("stamina", STAMINA_MAX))
    if stamina < STAMINA_CUSTO_CACAR:
        await interaction.response.send_message(
            f"🥵 Stamina insuficiente. Precisa de **{STAMINA_CUSTO_CACAR}** (atual: {stamina}).",
            ephemeral=True,
        )
        return

    p["stamina"] = max(0, stamina - STAMINA_CUSTO_CACAR)
    p["last_hunt_ts"] = agora

    if random.random() < INIMIGOS_FRACOS_CHANCE:
        inimigo = random.choice(INIMIGOS_FRACOS)
        xp = random.randint(*inimigo["xp"])
        gold = random.randint(*inimigo["gold"])
        p["xp"] = int(p.get("xp", 0)) + xp
        p["gold"] = int(p.get("gold", 0)) + gold

        drop_txt = ""
        if random.random() < DROP_FRACO_CHANCE:
            drop = await pick_drop_from_pool(DROP_POOL_FRACO)
            if drop:
                p.setdefault("inventario", []).append(drop["item_id"])
                drop_txt = f"\n🎁 Drop: **{drop['nome']}** (`{drop['item_id']}`)"

        upou = await try_auto_level(p)
        await save_player(p)
        await interaction.response.send_message(
            f"🏹 Você caçou **{inimigo['nome']}** com facilidade!\n"
            f"✨ +{xp} XP | 💰 +{gold} Gold\n"
            f"⚡ Stamina: **{p['stamina']}**/{p.get('max_stamina', STAMINA_MAX)}"
            + (f"\n🆙 UPOU {upou} nível(is)!" if upou else "")
            + drop_txt,
            ephemeral=False,
        )
        return

    monstro = pick_weighted_monster()
    hp_monstro = int(monstro.get("hp", 1))
    hp_monstro, dano_jogador, dano_monstro, forced = await cacar_turn(p, monstro, hp_monstro)

    if hp_monstro <= 0:
        xp = int(monstro.get("xp", 10))
        gold = int(monstro.get("gold", 8))
        p["xp"] = int(p.get("xp", 0)) + xp
        p["gold"] = int(p.get("gold", 0)) + gold

        drop_txt = ""
        if random.random() < DROP_RARO_CHANCE:
            drop = await pick_drop_from_pool(DROP_POOL_RARO)
            if drop:
                p.setdefault("inventario", []).append(drop["item_id"])
                drop_txt = f"\n🎁 Drop raro: **{drop['nome']}** (`{drop['item_id']}`)"

        upou = await try_auto_level(p)
        await save_player(p)
        await interaction.response.send_message(
            f"⚔️ Você venceu **{monstro['nome']}**!\n"
            f"🩸 Dano no 1º turno: **{dano_jogador}**\n"
            f"✨ +{xp} XP | 💰 +{gold} Gold\n"
            f"⚡ Stamina: **{p['stamina']}**/{p.get('max_stamina', STAMINA_MAX)}"
            + (f"\n🆙 UPOU {upou} nível(is)!" if upou else "")
            + drop_txt,
            ephemeral=False,
        )
    elif forced:
        await save_player(p)
        await interaction.response.send_message(
            f"💀 Você foi sobrepujado por **{monstro['nome']}** no 1º turno.\n"
            f"🩸 Dano recebido: **{dano_monstro}**\n"
            f"❤ Você ficou com **1 HP** e recuou.",
            ephemeral=False
        )
    else:
        await save_player(p)
        await interaction.response.send_message(
            content=(
                f"⚔️ Você encontrou **{monstro['nome']}**!\n"
                f"🩸 1º turno: você causou **{dano_jogador}** e recebeu **{dano_monstro}**\n"
                f"👾 HP do monstro: **{hp_monstro}**\n"
                f"❤ Seu HP: **{p['hp']}**\n"
                f"⚡ Stamina: **{p['stamina']}**/{p.get('max_stamina', STAMINA_MAX)}\n\n"
                f"Escolha: **Recuar** ou **Atacar novamente**."
            ),
            view=CacarFightView(interaction.user.id, monstro, hp_monstro),
            ephemeral=False
        )


# ==============================
# COMANDOS — MESTRE
# ==============================

@tree.command(name="mstatus", description="(Mestre) Ver ficha de um jogador.")
@only_master_channel()
@app_commands.describe(jogador="Jogador alvo")
async def mstatus_cmd(interaction: discord.Interaction, jogador: discord.Member):
    p = await get_player(jogador.id)
    if not p:
        await interaction.response.send_message("❌ Esse jogador não possui personagem.", ephemeral=True)
        return
    embed = await build_profile_embed(p, jogador.display_name, jogador.mention)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------- DAR XP / GOLD (individual / all / todos_exceto)

async def list_all_player_ids() -> List[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT user_id FROM players")
        rows = await cur.fetchall()
        return [int(r[0]) for r in rows]


@tree.command(name="darxp", description="(Mestre) Dar XP para 1 jogador.")
@only_master_channel()
async def darxp_cmd(interaction: discord.Interaction, jogador: str, quantidade: int):
    if quantidade == 0:
        await interaction.response.send_message("❌ A quantidade deve ser diferente de 0.", ephemeral=True)
        return

    jogador_raw = (jogador or "").strip()
    if jogador_raw.lower() == "all":
        ids = await list_all_player_ids()
        if not ids:
            await interaction.response.send_message("❌ Não há jogadores cadastrados.", ephemeral=True)
            return

        afetados = 0
        for pid in ids:
            p = await get_player(pid)
            if not p:
                continue
            p["xp"] = int(p.get("xp", 0)) + quantidade
            await try_auto_level(p)
            await save_player(p)
            afetados += 1

        await interaction.response.send_message(
            f"✅ XP {quantidade:+d} aplicado em {afetados} jogador(es).",
            ephemeral=True
        )
        return

    m = re.fullmatch(r"<@!?(\d+)>", jogador_raw)
    if m:
        target_id = int(m.group(1))
    elif jogador_raw.isdigit():
        target_id = int(jogador_raw)
    else:
        await interaction.response.send_message("❌ Use 'all', uma menção válida ou um ID de usuário.", ephemeral=True)
        return

    p = await get_player(target_id)
    if not p:
        await interaction.response.send_message("❌ Esse jogador não tem personagem.", ephemeral=True)
        return

    p["xp"] = int(p.get("xp", 0)) + quantidade
    upou = await try_auto_level(p)
    await save_player(p)
    await interaction.response.send_message(
        f"✅ XP atualizado para <@{target_id}>: {quantidade:+d}."
        + (f" 🆙 Subiu {upou} nível(is)." if upou else ""),
        ephemeral=True
    )


@tree.command(name="dargold", description="(Mestre) Dar gold para 1 jogador.")
@only_master_channel()
async def dargold_cmd(interaction: discord.Interaction, jogador: str, quantidade: int):
    if quantidade == 0:
        await interaction.response.send_message("❌ A quantidade deve ser diferente de 0.", ephemeral=True)
        return

    jogador_raw = (jogador or "").strip()
    if jogador_raw.lower() == "all":
        ids = await list_all_player_ids()
        if not ids:
            await interaction.response.send_message("❌ Não há jogadores cadastrados.", ephemeral=True)
            return

        afetados = 0
        for pid in ids:
            p = await get_player(pid)
            if not p:
                continue
            p["gold"] = int(p.get("gold", 0)) + quantidade
            await save_player(p)
            afetados += 1

        await interaction.response.send_message(
            f"✅ Gold {quantidade:+d} aplicado em {afetados} jogador(es).",
            ephemeral=True
        )
        return

    m = re.fullmatch(r"<@!?(\d+)>", jogador_raw)
    if m:
        target_id = int(m.group(1))
    elif jogador_raw.isdigit():
        target_id = int(jogador_raw)
    else:
        await interaction.response.send_message("❌ Use 'all', uma menção válida ou um ID de usuário.", ephemeral=True)
        return

    p = await get_player(target_id)
    if not p:
        await interaction.response.send_message("❌ Esse jogador não tem personagem.", ephemeral=True)
        return

    p["gold"] = int(p.get("gold", 0)) + quantidade
    await save_player(p)
    await interaction.response.send_message(
        f"✅ Gold atualizado para <@{target_id}>: {quantidade:+d}.",
        ephemeral=True
    )


@tree.command(name="darxp_todos", description="(Mestre) Dar XP para todos os jogadores.")
@only_master_channel()
async def darxp_todos_cmd(interaction: discord.Interaction, quantidade: int):
    if quantidade == 0:
        await interaction.response.send_message("❌ A quantidade deve ser diferente de 0.", ephemeral=True)
        return
    ids = await list_all_player_ids()
    if not ids:
        await interaction.response.send_message("❌ Não há jogadores cadastrados.", ephemeral=True)
        return

    afetados = 0
    for uid in ids:
        p = await get_player(uid)
        if not p:
            continue
        p["xp"] = int(p.get("xp", 0)) + quantidade
        await try_auto_level(p)
        await save_player(p)
        afetados += 1
    await interaction.response.send_message(f"✅ XP {quantidade:+d} aplicado em {afetados} jogador(es).", ephemeral=True)


@tree.command(name="dargold_todos", description="(Mestre) Dar gold para todos os jogadores.")
@only_master_channel()
async def dargold_todos_cmd(interaction: discord.Interaction, quantidade: int):
    if quantidade == 0:
        await interaction.response.send_message("❌ A quantidade deve ser diferente de 0.", ephemeral=True)
        return
    ids = await list_all_player_ids()
    if not ids:
        await interaction.response.send_message("❌ Não há jogadores cadastrados.", ephemeral=True)
        return

    afetados = 0
    for uid in ids:
        p = await get_player(uid)
        if not p:
            continue
        p["gold"] = int(p.get("gold", 0)) + quantidade
        await save_player(p)
        afetados += 1
    await interaction.response.send_message(f"✅ Gold {quantidade:+d} aplicado em {afetados} jogador(es).", ephemeral=True)


@tree.command(name="darxp_exceto", description="(Mestre) Dar XP para todos, exceto um jogador.")
@only_master_channel()
async def darxp_exceto_cmd(interaction: discord.Interaction, quantidade: int, exceto: discord.Member):
    if quantidade == 0:
        await interaction.response.send_message("❌ A quantidade deve ser diferente de 0.", ephemeral=True)
        return
    ids = await list_all_player_ids()
    if not ids:
        await interaction.response.send_message("❌ Não há jogadores cadastrados.", ephemeral=True)
        return

    afetados = 0
    for uid in ids:
        if uid == exceto.id:
            continue
        p = await get_player(uid)
        if not p:
            continue
        p["xp"] = int(p.get("xp", 0)) + quantidade
        await try_auto_level(p)
        await save_player(p)
        afetados += 1
    await interaction.response.send_message(
        f"✅ XP {quantidade:+d} aplicado em {afetados} jogador(es), exceto {exceto.mention}.",
        ephemeral=True
    )


@tree.command(name="dargold_exceto", description="(Mestre) Dar gold para todos, exceto um jogador.")
@only_master_channel()
async def dargold_exceto_cmd(interaction: discord.Interaction, quantidade: int, exceto: discord.Member):
    if quantidade == 0:
        await interaction.response.send_message("❌ A quantidade deve ser diferente de 0.", ephemeral=True)
        return
    ids = await list_all_player_ids()
    if not ids:
        await interaction.response.send_message("❌ Não há jogadores cadastrados.", ephemeral=True)
        return

    afetados = 0
    for uid in ids:
        if uid == exceto.id:
            continue
        p = await get_player(uid)
        if not p:
            continue
        p["gold"] = int(p.get("gold", 0)) + quantidade
        await save_player(p)
        afetados += 1
    await interaction.response.send_message(
        f"✅ Gold {quantidade:+d} aplicado em {afetados} jogador(es), exceto {exceto.mention}.",
        ephemeral=True
    )


setup_x1_arena(
    tree=tree,
    get_player=get_player,
    save_player=save_player,
    total_stat=total_stat,
    require_player=require_player,
)


# [REMOVIDO DUPLICADO] command 'spell_ativar'

# [REMOVIDO DUPLICADO] command 'magia_criar'



@tree.command(name="sync", description="(Mestre) Forçar sincronização dos slash commands.")
@only_master_channel()
async def sync_cmd(interaction: discord.Interaction):
    try:
        if not GUILD_ID:
            await interaction.response.send_message(
                "❌ Defina GUILD_ID no Railway para sincronização rápida por servidor.",
                ephemeral=True
            )
            return

        guild = discord.Object(id=GUILD_ID)

        tree.clear_commands(guild=guild)
        await tree.sync(guild=guild)

        tree.copy_global_to(guild=guild)

        synced = await tree.sync(guild=guild)

        synced_names = [cmd.name for cmd in synced]
        nomes = ", ".join(synced_names)
        faltando = sorted(REQUIRED_CORE_COMMANDS - set(synced_names))
        status_core = "✅ Core OK" if not faltando else f"⚠️ Core faltando: {', '.join(faltando)}"
        print(f"✅ Nomes sincronizados (guild {GUILD_ID}): {synced_names}")
        print(f"🔎 Verificação comandos core: {status_core}")

        await interaction.response.send_message(
            f"✅ Sync concluído na guild {GUILD_ID}: {len(synced)} comandos.\n{nomes}\n{status_core}",
            ephemeral=True
        )

    except Exception as e:
        await interaction.response.send_message(
            f"❌ Erro no sync: {e}",
            ephemeral=True
        )

@client.event
async def on_ready():
    print("BOOT VERSION: FORCE-REBUILD-COMMANDS-06")
    print(f"✅ Logado como {client.user} (ID: {client.user.id if client.user else 'n/a'})")

    try:
        loaded = [cmd.name for cmd in tree.get_commands()]
        print(f"🧩 Comandos carregados no código: {len(loaded)} -> {loaded}")
        faltando_loaded = sorted(REQUIRED_CORE_COMMANDS - set(loaded))
        status_loaded = "✅ Core carregados no código" if not faltando_loaded else f"⚠️ Core ausentes no código: {', '.join(faltando_loaded)}"
        print(f"🔎 Verificação comandos core no código: {status_loaded}")
    except Exception as e:
        print(f"⚠️ Falha ao listar comandos carregados: {e}")

    try:
        await init_db()
        await seed_initial_data()
        await seed_initial_spells()
    except Exception as e:
        print(f"❌ Erro na inicialização do DB/seed: {e}")

    try:
        client.add_view(ClasseView())
    except Exception as e:
        print(f"⚠️ Falha ao registrar ClasseView persistente: {e}")

    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)

            print(f"🧹 Limpando comandos antigos da guild {GUILD_ID}...")
            tree.clear_commands(guild=guild)
            cleared = await tree.sync(guild=guild)
            print(f"🧹 Comandos após limpeza: {len(cleared)}")

            print(f"📋 Copiando comandos globais para a guild {GUILD_ID}...")
            tree.copy_global_to(guild=guild)

            synced = await tree.sync(guild=guild)
            synced_names = [cmd.name for cmd in synced]
            faltando_sync = sorted(REQUIRED_CORE_COMMANDS - set(synced_names))
            status_sync = "✅ presentes" if not faltando_sync else f"⚠️ faltando: {', '.join(faltando_sync)}"
            print(f"✅ Slash sync (guild {GUILD_ID}): {len(synced)} comandos")
            print(f"✅ Nomes sincronizados: {synced_names}")
            print(f"🔎 Verificação comandos core sincronizados: {status_sync}")
        else:
            synced = await tree.sync()
            print(f"✅ Slash sync global: {len(synced)} comandos")
    except Exception as e:
        print(f"❌ Falha no tree.sync(): {e}")

# ==============================
# RUN
# ==============================

client.run(TOKEN)
