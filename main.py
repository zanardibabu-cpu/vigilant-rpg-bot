print("BOOT VERSION: 2026-03-04-01")

import os
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
ALBERGUE_MAX_CUSTO = 50

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
    "espada_ferro": {
        "nome": 'Espada de Ferro',
        "preco": 400,
        "tipo": 'arma',
        "slot": 'mao_direita',
        "bonus": {"atk": 4},
        "efeito": {"forca": 1},
        "classes": [],
        "desc": 'Dano +4. Bônus: +1 força (conta como +1 ATK).',
        "loja": 'ferreiro',
    },
    "espada_longa": {
        "nome": 'Espada Longa',
        "preco": 700,
        "tipo": 'arma',
        "slot": 'mao_direita',
        "bonus": {"atk": 6},
        "efeito": {},
        "classes": [],
        "desc": 'Dano +6.',
        "loja": 'ferreiro',
    },
    "espada_soldado": {
        "nome": 'Espada do Soldado',
        "preco": 1100,
        "tipo": 'arma',
        "slot": 'mao_direita',
        "bonus": {"atk": 7, "defesa": 1},
        "efeito": {},
        "classes": [],
        "desc": 'Dano +7. +1 armadura (DEF).',
        "loja": 'ferreiro',
    },
    "espada_runica": {
        "nome": 'Espada Rúnica',
        "preco": 1900,
        "tipo": 'arma',
        "slot": 'mao_direita',
        "bonus": {"atk": 9, "magia": 2},
        "efeito": {},
        "classes": [],
        "desc": 'Dano +9. +2 inteligência (MAGIA).',
        "loja": 'ferreiro',
    },
    "espada_crepusculo": {
        "nome": 'Espada do Crepúsculo',
        "preco": 2800,
        "tipo": 'arma',
        "slot": 'mao_direita',
        "bonus": {"atk": 10},
        "efeito": {"ignora_def": 2},
        "classes": [],
        "desc": 'Dano +10. Ignora 2 armadura do alvo.',
        "loja": 'ferreiro',
    },
    "excalibur": {
        "nome": 'Excalibur',
        "preco": 9000,
        "tipo": 'arma',
        "slot": 'mao_direita',
        "bonus": {"atk": 14},
        "efeito": {"crit_pct": 5},
        "classes": [],
        "desc": 'Dano +14. 5% crítico.',
        "loja": 'ferreiro',
    },
    "frostmourne": {
        "nome": 'Frostmourne',
        "preco": 15000,
        "tipo": 'arma',
        "slot": 'mao_direita',
        "bonus": {"atk": 16},
        "efeito": {"lifesteal": 2},
        "classes": [],
        "desc": 'Dano +16. Rouba 2 HP por ataque.',
        "loja": 'ferreiro',
    },
    "machado_ferro": {
        "nome": 'Machado de Ferro',
        "preco": 450,
        "tipo": 'arma',
        "slot": 'mao_direita',
        "bonus": {"atk": 5},
        "efeito": {},
        "classes": [],
        "desc": 'Dano +5.',
        "loja": 'ferreiro',
    },
    "machado_guerra": {
        "nome": 'Machado de Guerra',
        "preco": 800,
        "tipo": 'arma',
        "slot": 'mao_direita',
        "bonus": {"atk": 7},
        "efeito": {},
        "classes": [],
        "desc": 'Dano +7.',
        "loja": 'ferreiro',
    },
    "machado_barbaro": {
        "nome": 'Machado Bárbaro',
        "preco": 1600,
        "tipo": 'arma',
        "slot": 'mao_direita',
        "bonus": {"atk": 10},
        "efeito": {"forca": 2},
        "classes": [],
        "desc": 'Dano +10. +2 força (ATK).',
        "loja": 'ferreiro',
    },
    "machado_grom": {
        "nome": 'Machado de Grom',
        "preco": 4200,
        "tipo": 'arma',
        "slot": 'mao_direita',
        "bonus": {"atk": 13},
        "efeito": {"sangramento": 1},
        "classes": [],
        "desc": 'Dano +13. Causa sangramento.',
        "loja": 'ferreiro',
    },
    "quebra_titas": {
        "nome": 'Quebra-Titãs',
        "preco": 7500,
        "tipo": 'arma',
        "slot": 'mao_direita',
        "bonus": {"atk": 15},
        "efeito": {"dano_vs_grande_mult": 2},
        "classes": [],
        "desc": 'Dano +15. Dano dobrado contra monstros grandes.',
        "loja": 'ferreiro',
    },
    "arco_curto": {
        "nome": 'Arco Curto',
        "preco": 350,
        "tipo": 'arma',
        "slot": 'duas_maos',
        "bonus": {"atk": 4, "destreza": 1},
        "efeito": {},
        "classes": [],
        "desc": 'Dano +4. +1 destreza.',
        "loja": 'ferreiro',
    },
    "arco_longo": {
        "nome": 'Arco Longo',
        "preco": 650,
        "tipo": 'arma',
        "slot": 'duas_maos',
        "bonus": {"atk": 6},
        "efeito": {},
        "classes": [],
        "desc": 'Dano +6.',
        "loja": 'ferreiro',
    },
    "arco_elfico": {
        "nome": 'Arco Élfico',
        "preco": 1500,
        "tipo": 'arma',
        "slot": 'duas_maos',
        "bonus": {"atk": 8, "destreza": 2},
        "efeito": {},
        "classes": [],
        "desc": 'Dano +8. +2 destreza.',
        "loja": 'ferreiro',
    },
    "arco_cacador": {
        "nome": 'Arco do Caçador',
        "preco": 2600,
        "tipo": 'arma',
        "slot": 'duas_maos',
        "bonus": {"atk": 9},
        "efeito": {"crit_pct": 5},
        "classes": [],
        "desc": 'Dano +9. 5% crítico.',
        "loja": 'ferreiro',
    },
    "arco_sombrio": {
        "nome": 'Arco Sombrio',
        "preco": 4800,
        "tipo": 'arma',
        "slot": 'duas_maos',
        "bonus": {"atk": 12},
        "efeito": {"bonus_vs_tag": {"radiação": 3}},
        "classes": [],
        "desc": 'Dano +12. +3 dano em criaturas irradiadas.',
        "loja": 'ferreiro',
    },
    "cajado_simples": {
        "nome": 'Cajado Simples',
        "preco": 350,
        "tipo": 'cajado',
        "slot": 'duas_maos',
        "bonus": {"mana": 3, "magia": 4},
        "efeito": {},
        "classes": [],
        "desc": 'Mana +3. Dano mágico +4 (MAGIA).',
        "loja": 'arcano',
    },
    "cajado_arcano": {
        "nome": 'Cajado Arcano',
        "preco": 800,
        "tipo": 'cajado',
        "slot": 'duas_maos',
        "bonus": {"mana": 6, "magia": 5},
        "efeito": {},
        "classes": [],
        "desc": 'Mana +6. Dano mágico +5.',
        "loja": 'arcano',
    },
    "cajado_mago": {
        "nome": 'Cajado do Mago',
        "preco": 1600,
        "tipo": 'cajado',
        "slot": 'duas_maos',
        "bonus": {"mana": 10, "magia": 2},
        "efeito": {},
        "classes": [],
        "desc": 'Mana +10. +2 inteligência (MAGIA).',
        "loja": 'arcano',
    },
    "cajado_merlin": {
        "nome": 'Cajado de Merlin',
        "preco": 3500,
        "tipo": 'cajado',
        "slot": 'duas_maos',
        "bonus": {"mana": 12},
        "efeito": {"custo_mana_reducao": 1},
        "classes": [],
        "desc": 'Mana +12. Magias custam -1 mana.',
        "loja": 'arcano',
    },
    "cajado_arquimago": {
        "nome": 'Cajado do Arquimago',
        "preco": 7000,
        "tipo": 'cajado',
        "slot": 'duas_maos',
        "bonus": {"mana": 18},
        "efeito": {"dup_magia_pct": 10},
        "classes": [],
        "desc": 'Mana +18. 10% chance de duplicar magia.',
        "loja": 'arcano',
    },
    "armadura_couro": {
        "nome": 'Armadura de Couro',
        "preco": 450,
        "tipo": 'armadura',
        "slot": 'peitoral',
        "bonus": {"defesa": 3},
        "efeito": {},
        "classes": [],
        "desc": 'Armadura +3.',
        "loja": 'armaduras',
    },
    "armadura_ferro": {
        "nome": 'Armadura de Ferro',
        "preco": 900,
        "tipo": 'armadura',
        "slot": 'peitoral',
        "bonus": {"defesa": 6},
        "efeito": {},
        "classes": [],
        "desc": 'Armadura +6.',
        "loja": 'armaduras',
    },
    "armadura_reforcada": {
        "nome": 'Armadura Reforçada',
        "preco": 1600,
        "tipo": 'armadura',
        "slot": 'peitoral',
        "bonus": {"defesa": 8, "hp": 5},
        "efeito": {},
        "classes": [],
        "desc": 'Armadura +8. HP +5.',
        "loja": 'armaduras',
    },
    "armadura_mithril": {
        "nome": 'Armadura de Mithril',
        "preco": 4200,
        "tipo": 'armadura',
        "slot": 'peitoral',
        "bonus": {"defesa": 10, "destreza": 2},
        "efeito": {},
        "classes": [],
        "desc": 'Armadura +10. +2 destreza.',
        "loja": 'armaduras',
    },
    "armadura_guardiao": {
        "nome": 'Armadura do Guardião',
        "preco": 6800,
        "tipo": 'armadura',
        "slot": 'peitoral',
        "bonus": {"defesa": 12, "hp": 10},
        "efeito": {},
        "classes": [],
        "desc": 'Armadura +12. HP +10.',
        "loja": 'armaduras',
    },
    "manto_aprendiz": {
        "nome": 'Manto do Aprendiz',
        "preco": 600,
        "tipo": 'manto',
        "slot": 'peitoral',
        "bonus": {"mana": 5},
        "efeito": {},
        "classes": [],
        "desc": 'Mana +5.',
        "loja": 'arcano',
    },
    "manto_arcano": {
        "nome": 'Manto Arcano',
        "preco": 1100,
        "tipo": 'manto',
        "slot": 'peitoral',
        "bonus": {"mana": 8, "magia": 1},
        "efeito": {},
        "classes": [],
        "desc": 'Mana +8. +1 inteligência (MAGIA).',
        "loja": 'arcano',
    },
    "manto_clerigo": {
        "nome": 'Manto do Clérigo',
        "preco": 1300,
        "tipo": 'manto',
        "slot": 'peitoral',
        "bonus": {"mana": 6},
        "efeito": {"cura_bonus": 2},
        "classes": [],
        "desc": 'Mana +6. Cura +2.',
        "loja": 'arcano',
    },
    "manto_estrelas": {
        "nome": 'Manto das Estrelas',
        "preco": 3200,
        "tipo": 'manto',
        "slot": 'peitoral',
        "bonus": {"mana": 12},
        "efeito": {"res_magica": 1},
        "classes": [],
        "desc": 'Mana +12. Resistência mágica.',
        "loja": 'arcano',
    },
    "manto_arquimago": {
        "nome": 'Manto do Arquimago',
        "preco": 7500,
        "tipo": 'manto',
        "slot": 'peitoral',
        "bonus": {"mana": 15},
        "efeito": {"mana_regen": 1},
        "classes": [],
        "desc": 'Mana +15. Regenera 1 mana por turno.',
        "loja": 'arcano',
    },
    "anel_mana": {
        "nome": 'Anel de Mana',
        "preco": 900,
        "tipo": 'anel',
        "slot": 'anel',
        "bonus": {"mana": 6},
        "efeito": {},
        "classes": [],
        "desc": 'Mana +6.',
        "loja": 'arcano',
    },
    "anel_vitalidade": {
        "nome": 'Anel da Vitalidade',
        "preco": 1000,
        "tipo": 'anel',
        "slot": 'anel',
        "bonus": {"hp": 8},
        "efeito": {},
        "classes": [],
        "desc": 'HP +8.',
        "loja": 'arcano',
    },
    "anel_protecao": {
        "nome": 'Anel da Proteção',
        "preco": 1200,
        "tipo": 'anel',
        "slot": 'anel',
        "bonus": {"defesa": 4},
        "efeito": {},
        "classes": [],
        "desc": 'Armadura +4.',
        "loja": 'arcano',
    },
    "anel_arcano": {
        "nome": 'Anel Arcano',
        "preco": 2100,
        "tipo": 'anel',
        "slot": 'anel',
        "bonus": {"mana": 8, "magia": 2},
        "efeito": {},
        "classes": [],
        "desc": 'Mana +8. Dano mágico +2.',
        "loja": 'arcano',
    },
    "anel_poder": {
        "nome": 'Anel do Poder',
        "preco": 3500,
        "tipo": 'anel',
        "slot": 'anel',
        "bonus": {"atk": 2},
        "efeito": {},
        "classes": [],
        "desc": '+2 força (ATK).',
        "loja": 'arcano',
    },
    "amuleto_vida": {
        "nome": 'Amuleto da Vida',
        "preco": 1600,
        "tipo": 'amuleto',
        "slot": 'amuleto',
        "bonus": {"hp": 12},
        "efeito": {},
        "classes": [],
        "desc": 'HP +12.',
        "loja": 'igreja',
    },
    "amuleto_luz": {
        "nome": 'Amuleto da Luz',
        "preco": 2200,
        "tipo": 'amuleto',
        "slot": 'amuleto',
        "bonus": {},
        "efeito": {"cura_bonus": 3},
        "classes": [],
        "desc": 'Cura +3.',
        "loja": 'igreja',
    },
    "amuleto_arcano": {
        "nome": 'Amuleto Arcano',
        "preco": 2600,
        "tipo": 'amuleto',
        "slot": 'amuleto',
        "bonus": {"mana": 10},
        "efeito": {},
        "classes": [],
        "desc": 'Mana +10.',
        "loja": 'igreja',
    },
    "amuleto_guardiao": {
        "nome": 'Amuleto do Guardião',
        "preco": 3800,
        "tipo": 'amuleto',
        "slot": 'amuleto',
        "bonus": {"defesa": 5, "hp": 6},
        "efeito": {},
        "classes": [],
        "desc": 'Armadura +5. HP +6.',
        "loja": 'igreja',
    },
    "pocao_cura": {
        "nome": 'Poção de Cura',
        "preco": 120,
        "tipo": 'consumivel',
        "slot": 'consumivel',
        "bonus": {},
        "efeito": {"cura_hp": 15},
        "classes": [],
        "desc": 'Cura 15 HP.',
        "loja": 'mercador',
    },
    "pocao_cura_grande": {
        "nome": 'Poção Grande de Cura',
        "preco": 260,
        "tipo": 'consumivel',
        "slot": 'consumivel',
        "bonus": {},
        "efeito": {"cura_hp": 35},
        "classes": [],
        "desc": 'Cura 35 HP.',
        "loja": 'mercador',
    },
    "pocao_mana": {
        "nome": 'Poção de Mana',
        "preco": 140,
        "tipo": 'consumivel',
        "slot": 'consumivel',
        "bonus": {},
        "efeito": {"cura_mana": 15},
        "classes": [],
        "desc": 'Recupera 15 mana.',
        "loja": 'mercador',
    },
    "pocao_arcana": {
        "nome": 'Poção Arcana',
        "preco": 320,
        "tipo": 'consumivel',
        "slot": 'consumivel',
        "bonus": {},
        "efeito": {"cura_mana": 30},
        "classes": [],
        "desc": 'Recupera 30 mana.',
        "loja": 'mercador',
    },
    "relicario_neural": {
        "nome": 'Relicário Neural',
        "preco": 0,
        "tipo": 'implante',
        "slot": 'implante',
        "bonus": {"mana": 5},
        "efeito": {"cura_bonus": 2, "custo_mana_reducao": 1, "nao_compravel": 1},
        "classes": [],
        "desc": 'Implante: Mana +5, Cura +2. Cura custa -1 mana. (Não vendável/Comprável)',
        "loja": 'arcano',
    },
    "nucleo_energia_antigo": {
        "nome": 'Núcleo de Energia Antigo',
        "preco": 7000,
        "tipo": 'especial',
        "slot": 'especial',
        "bonus": {"mana": 10},
        "efeito": {"mana_regen": 1},
        "classes": [],
        "desc": 'Mana +10. Regenera 1 mana/turno.',
        "loja": 'arcano',
    },
    "fragmento_ia": {
        "nome": 'Fragmento de IA',
        "preco": 12000,
        "tipo": 'especial',
        "slot": 'especial',
        "bonus": {"magia": 4},
        "efeito": {"prever_ataque_pct": 10},
        "classes": [],
        "desc": '+4 inteligência (MAGIA). Chance de prever ataque inimigo.',
        "loja": 'arcano',
    },
    "olho_vigilant": {
        "nome": 'Olho do Vigilant',
        "preco": 18000,
        "tipo": 'especial',
        "slot": 'especial',
        "bonus": {},
        "efeito": {"revela_ocultos": 1},
        "classes": [],
        "desc": 'Revela inimigos ocultos.',
        "loja": 'arcano',
    },
    "coracao_nuclear": {
        "nome": 'Coração Nuclear',
        "preco": 22000,
        "tipo": 'especial',
        "slot": 'especial',
        "bonus": {"hp": 20},
        "efeito": {"reduz_dano": 3},
        "classes": [],
        "desc": 'HP +20. Reduz dano recebido em 3.',
        "loja": 'arcano',
    },
}

# Todos os itens do catálogo ficam visíveis na loja (ativo=1). Não existe mais 'itens iniciais' limitando vitrine.


async def item_upsert(item_id: str, it: Dict[str, Any]):
    loja = (it.get("loja") or "mercador").lower().strip()
    if loja not in LOJAS_VALIDAS:
        loja = "mercador"

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        INSERT INTO items(item_id, nome, tipo, slot, preco, bonus_json, efeito_json, classes_json, desc, loja, ativo, deleted)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0)
        ON CONFLICT(item_id) DO UPDATE SET
            nome=excluded.nome,
            tipo=excluded.tipo,
            slot=excluded.slot,
            preco=excluded.preco,
            bonus_json=excluded.bonus_json,
            efeito_json=excluded.efeito_json,
            classes_json=excluded.classes_json,
            desc=excluded.desc,
            loja=excluded.loja,
            ativo=1
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
    """Garante que o catálogo padrão exista no banco (idempotente)."""
    await seed_initial_items()

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
            SELECT i.*, s.preco as preco_loja, s.estoque, s.ativo
            FROM shop_items s
            JOIN items i ON i.item_id = s.item_id
            WHERE s.ativo=1 AND i.deleted=0
            ORDER BY i.nome COLLATE NOCASE
        """)
        rows = await cur.fetchall()
        out = []
        for r in rows:
            it = dict(r)
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
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("""
            SELECT 1
            FROM shop_items s
            JOIN items i ON i.item_id=s.item_id
            WHERE s.item_id=? AND s.ativo=1 AND i.deleted=0
        """, (item_id,))
        return (await cur.fetchone()) is not None

async def shop_decrease_stock(item_id: str, n: int = 1) -> bool:
    """
    estoque NULL = infinito
    """
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT estoque FROM shop_items WHERE item_id=? AND ativo=1", (item_id,))
        row = await cur.fetchone()
        if not row:
            return False
        estoque = row["estoque"]
        if estoque is None:
            return True
        estoque = int(estoque)
        if estoque < n:
            return False
        await db.execute("UPDATE shop_items SET estoque=? WHERE item_id=?", (estoque - n, item_id))
        await db.commit()
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


# ==============================
# COMANDOS — MESTRE
# ==============================



# ---------- DAR XP / GOLD (individual / all / todos_exceto)

async def list_all_player_ids() -> List[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT user_id FROM players")
        rows = await cur.fetchall()
        return [int(r[0]) for r in rows]


# [REMOVIDO DUPLICADO] command 'spell_ativar'

# [REMOVIDO DUPLICADO] command 'magia_criar'

# ==============================
# RUN
# ==============================

client.run(TOKEN)
