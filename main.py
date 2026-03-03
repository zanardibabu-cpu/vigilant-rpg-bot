import os
import time
import json
import math
import random
import aiosqlite
import discord
from discord import app_commands
from typing import Optional, List, Dict, Any, Tuple
# ==========================
# CONFIG / IDs
# ==========================

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise SystemExit("❌ TOKEN não encontrado. Defina a variável de ambiente TOKEN no Railway e redeploy.")


MESTRE_ID = 1255256495369748573  # Cannabinoide

# Canais (IDs fornecidos por você)
CANAL_BEM_VINDO_ID = 1472100698211483679
CANAL_COMANDOS_ID  = 1472216958647795965
CANAL_LOJA_ID      = 1472100628355350633
CANAL_MESTRE_ID    = 1472274401289310248
CANAL_CACAR_ID     = 1472365134801276998
CANAL_TAVERNA_ID   = 0

DB_FILE = "vigillant.db"

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

# Livro de magias
SPELLBOOK_SLOTS = 7

# ==============================
# DISCORD
# ==============================

intents = discord.Intents.default()
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

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
        "preco": 20,
        "tipo": "consumivel",
        "slot": "consumivel",
        "efeito": {"hp": 20},
        "bonus": {},
        "classes": [],
        "desc": "Recupera 20 HP."
    },
    "pocao_mana": {
        "nome": "Poção de Mana",
        "preco": 20,
        "tipo": "consumivel",
        "slot": "consumivel",
        "efeito": {"mana": 20},
        "bonus": {},
        "classes": [],
        "desc": "Recupera 20 Mana."
    },
    "tablet_hacker": {
        "nome": "Tablet Terminal Hacker",
        "preco": 1200,
        "tipo": "especial",
        "slot": "especial",
        "efeito": {"hack_stun_turns": 2},
        "bonus": {},
        "classes": ["mago", "clerigo"],
        "desc": "Narrativa: hack desativa cibernéticos por 2 turnos."
    },
}

INITIAL_SHOP_ACTIVE = [
    ("pocao_vida", None, None),
    ("pocao_mana", None, None),
    ("tablet_hacker", None, None),
]

# ==============================
# UTIL / CHECKS
# ==============================

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
        if not eh_mestre(interaction.user.id):
            msg = "❌ Apenas o **Mestre** pode usar isso."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return False

        if CANAL_MESTRE_ID and interaction.channel_id != CANAL_MESTRE_ID:
            msg = "❌ Comandos do mestre só na **#Sala do mestre**."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return False
        return True
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

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        # players
        await db.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            classe TEXT,
            level INTEGER,
            xp INTEGER,
            gold INTEGER,
            pontos INTEGER,
            hp INTEGER,
            mana INTEGER,
            stamina INTEGER,
            max_stamina INTEGER,
            rest_until_ts INTEGER,
            last_hunt_ts INTEGER,
            stats_json TEXT,
            inventario_json TEXT,
            equipado_json TEXT,
            spellbook_json TEXT
        )
        """)

        # items catalog
        await db.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            preco_base INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            slot TEXT NOT NULL,
            bonus_json TEXT,
            efeito_json TEXT,
            classes_json TEXT,
            desc TEXT,
            deleted INTEGER NOT NULL DEFAULT 0
        )
        """)

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
            custo INTEGER NOT NULL,
            classes_json TEXT NOT NULL,
            efeito_tipo TEXT NOT NULL,   -- "dano" | "cura"
            efeito_valor INTEGER NOT NULL,
            desc TEXT,
            deleted INTEGER NOT NULL DEFAULT 0
        )
        """)

        await db.commit()

async def seed_initial_data():
    """
    Insere itens iniciais (se não existirem) e ativa alguns na loja.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        # itens
        for item_id, it in INITIAL_ITEMS.items():
            cur = await db.execute("SELECT 1 FROM items WHERE item_id=?", (item_id,))
            exists = await cur.fetchone()
            if exists:
                continue
            await db.execute("""
                INSERT INTO items (item_id, nome, preco_base, tipo, slot, bonus_json, efeito_json, classes_json, desc, deleted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                item_id,
                it["nome"],
                int(it["preco"]),
                it["tipo"],
                it["slot"],
                jdump(it.get("bonus", {})),
                jdump(it.get("efeito", {})),
                jdump(it.get("classes", [])),
                it.get("desc", "") or ""
            ))

        # ativa loja
        for item_id, preco, estoque in INITIAL_SHOP_ACTIVE:
            cur = await db.execute("SELECT 1 FROM shop_items WHERE item_id=?", (item_id,))
            exists = await cur.fetchone()
            if exists:
                continue
            await db.execute("""
                INSERT INTO shop_items (item_id, preco, estoque, ativo)
                VALUES (?, ?, ?, 1)
            """, (item_id, preco, estoque))

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
        super().__init__(placeholder="Escolha sua classe…", min_values=1, max_values=1, options=opts)

async def callback(self, interaction: discord.Interaction):
        if interaction.channel_id != CANAL_BEM_VINDO_ID:
            await interaction.response.send_message("❌ Criação de personagem só no canal de **bem-vindo**.", ephemeral=True)
            return

        existing = await get_player(interaction.user.id)
        if existing:
            await interaction.response.send_message("⚠️ Você já tem personagem. Use **/perfil**.", ephemeral=True)
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
                f"💰 Gold inicial: **{p['gold']}**\n\n"
                f"_👁️ Vigillant: “Mais um nome para a estatística…”_"
            ),
            color=discord.Color.dark_grey()
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

class ClasseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
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

@tree.command(name="magias", description="Listar magias disponíveis para sua classe.")
async def magias(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return
    if not can_use_spellbook(p["classe"]):
        await interaction.response.send_message("❌ Sua classe não usa magias.", ephemeral=True)
        return

    spells = await spell_list_for_class(p["classe"])
    if not spells:
        await interaction.response.send_message("📖 Nenhuma magia cadastrada ainda.", ephemeral=True)
        return

    lines = []
    for s in spells[:60]:
        lines.append(f"• `{s['spell_id']}` — {s['nome']} (custo {s['custo']}, {s['efeito_tipo']} {s['efeito_valor']})")

    await interaction.response.send_message("📖 **Magias disponíveis:**\n" + "\n".join(lines), ephemeral=True)

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

    if not can_use_spellbook(p["classe"]):
        await interaction.response.send_message("❌ Sua classe não usa livro de magias.", ephemeral=True)
        return

    if narration_is_on(interaction):
        await interaction.response.send_message("❌ Não é possível trocar o livro com **NARRAÇÃO ON**.", ephemeral=True)
        return

    spell_id = spell_id.lower().strip()
    book = p.get("spellbook") or []
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

@tree.command(name="narracao", description="(Mestre) Ativar/desativar modo narração (pausa /cacar e trava livro).")
@only_master_channel()
@app_commands.describe(modo="on ou off")
async def narracao(interaction: discord.Interaction, modo: str):
if not interaction.guild:
    await interaction.response.send_message("❌ Use em servidor.", ephemeral=True)
    return
modo = modo.lower().strip()
if modo not in ["on", "off"]:
    await interaction.response.send_message("❌ Use on/off.", ephemeral=True)
    return
NARRACAO_GUILD[interaction.guild.id] = (modo == "on")
await interaction.response.send_message(f"📖 Modo narração: **{modo.upper()}**", ephemeral=False)

# ---------- DAR XP / GOLD (individual / all / todos_exceto)

async def list_all_player_ids() -> List[int]:
async with aiosqlite.connect(DB_FILE) as db:
    cur = await db.execute("SELECT user_id FROM players")
    return [int(r[0]) for r in await cur.fetchall()]

@tree.command(name="darxp", description="(Mestre) Dar XP (jogador | all | todos_exceto).")
@only_master_channel()
@app_commands.describe(
    alvo="Mencione um jogador, ou digite 'all' ou 'todos_exceto'",
    quantidade="Quantidade de XP",
    exceto="Se alvo for 'todos_exceto', informe o jogador a excluir"
)
async def darxp(interaction: discord.Interaction, alvo: str, quantidade: int, exceto: Optional[discord.Member] = None):
    if quantidade <= 0:
        await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)
        return

    alvo = (alvo or "").lower().strip()

    if alvo == "all":
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

    if alvo == "todos_exceto":
        if not exceto:
            await interaction.response.send_message("❌ Use: /darxp alvo:todos_exceto quantidade:X exceto:@Fulano", ephemeral=True)
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

    # caso normal: alvo é menção/ID no texto (simplificado)
    # se você preferir obrigatório ser discord.Member, trocamos assinatura.
    await interaction.response.send_message("❌ Use alvo: **all** ou **todos_exceto**. (Para individual, use /darxp_individual)", ephemeral=True)

@tree.command(name="darxp_individual", description="(Mestre) Dar XP para 1 jogador.")
@only_master_channel()
async def darxp_individual(interaction: discord.Interaction, membro: discord.Member, quantidade: int):
    if quantidade <= 0:
        await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)
        return
    p = await get_player(membro.id)
    if not p:
        await interaction.response.send_message("❌ Jogador sem personagem.", ephemeral=True)
        return
    p["xp"] += quantidade
    upou = await try_auto_level(p)
    await save_player(p)
    await interaction.response.send_message(
        f"👑 Mestre deu **{quantidade} XP** para {membro.mention}."
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


















