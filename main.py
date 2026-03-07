import os
import time
import json
import math
from pathlib import Path
from typing import Optional, List, Dict, Any

import aiosqlite
import discord
from discord import app_commands

BOOT_VERSION = "2026-03-07-master-shop-stable"
print(f"BOOT VERSION: {BOOT_VERSION}")

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise SystemExit("TOKEN não encontrado.")

GUILD_ID_RAW = os.getenv("GUILD_ID", "").strip()
GUILD_ID = int(GUILD_ID_RAW) if GUILD_ID_RAW.isdigit() else None
MESTRE_ID = int(os.getenv("MESTRE_ID", "1255256495369748573"))

CANAL_LOJA_ID = int(os.getenv("CANAL_LOJA_ID", "1472100628355350633"))
CANAL_MESTRE_ID = int(os.getenv("CANAL_MESTRE_ID", "1472274401289310248"))

DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent
DB_FILE = str(DATA_DIR / "vigilant_rpg.sqlite")

ITEMS_PER_PAGE = 8
LOJAS_VALIDAS = {"mercador", "ferreiro", "arcano", "armaduras", "igreja"}

CLASSES: Dict[str, Dict[str, Any]] = {
    "barbaro": {"hp": 64, "mana": 0, "stamina": 20, "atk": 6, "def": 3, "int": 1, "dex": 2, "for": 4},
    "clerigo": {"hp": 51, "mana": 14, "stamina": 16, "atk": 3, "def": 4, "int": 3, "dex": 1, "for": 2},
    "mago": {"hp": 17, "mana": 21, "stamina": 12, "atk": 2, "def": 1, "int": 6, "dex": 2, "for": 1},
    "executor": {"hp": 43, "mana": 6, "stamina": 18, "atk": 5, "def": 2, "int": 2, "dex": 4, "for": 3},
}

RAW_ITEMS = [
    ("espada_ferro", "Espada de Ferro", "arma", "arma", 400, "ferreiro", {"atk": 4, "for": 1}, {}, [], "Dano +4, +1 força"),
    ("espada_longa", "Espada Longa", "arma", "arma", 700, "ferreiro", {"atk": 6}, {}, [], "Dano +6"),
    ("espada_soldado", "Espada do Soldado", "arma", "arma", 1100, "ferreiro", {"atk": 7, "def": 1}, {}, [], "Dano +7, +1 armadura"),
    ("espada_runica", "Espada Rúnica", "arma", "arma", 1900, "ferreiro", {"atk": 9, "int": 2}, {}, [], "Dano +9, +2 inteligência"),
    ("espada_crepusculo", "Espada do Crepúsculo", "arma", "arma", 2800, "ferreiro", {"atk": 10}, {"ignora_def": 2}, [], "Dano +10, ignora 2 armadura"),
    ("excalibur", "Excalibur", "arma", "arma", 9000, "ferreiro", {"atk": 14}, {"crit_chance": 5}, [], "Dano +14, 5% crítico"),
    ("frostmourne", "Frostmourne", "arma", "arma", 15000, "ferreiro", {"atk": 16}, {"lifesteal": 2}, [], "Dano +16, rouba 2 HP por ataque"),
    ("machado_ferro", "Machado de Ferro", "arma", "arma", 450, "ferreiro", {"atk": 5}, {}, ["barbaro", "executor"], "Dano +5"),
    ("machado_guerra", "Machado de Guerra", "arma", "arma", 800, "ferreiro", {"atk": 7}, {}, ["barbaro", "executor"], "Dano +7"),
    ("machado_barbaro", "Machado Bárbaro", "arma", "arma", 1600, "ferreiro", {"atk": 10, "for": 2}, {}, ["barbaro"], "Dano +10, +2 força"),
    ("machado_grom", "Machado de Grom", "arma", "arma", 4200, "ferreiro", {"atk": 13}, {"sangramento": 1}, ["barbaro"], "Dano +13, sangramento"),
    ("quebra_titas", "Quebra-Titãs", "arma", "arma", 7500, "ferreiro", {"atk": 15}, {"vs_grandes": 2}, ["barbaro", "executor"], "Dano +15, dano dobrado contra monstros grandes"),
    ("arco_curto", "Arco Curto", "arco", "arma", 350, "ferreiro", {"atk": 4, "dex": 1}, {}, ["executor"], "Dano +4, +1 destreza"),
    ("arco_longo", "Arco Longo", "arco", "arma", 650, "ferreiro", {"atk": 6}, {}, ["executor"], "Dano +6"),
    ("arco_elfico", "Arco Élfico", "arco", "arma", 1500, "ferreiro", {"atk": 8, "dex": 2}, {}, ["executor"], "Dano +8, +2 destreza"),
    ("arco_cacador", "Arco do Caçador", "arco", "arma", 2600, "ferreiro", {"atk": 9}, {"crit_chance": 5}, ["executor"], "Dano +9, 5% crítico"),
    ("arco_sombrio", "Arco Sombrio", "arco", "arma", 4800, "ferreiro", {"atk": 12}, {"vs_irradiado": 3}, ["executor"], "Dano +12, +3 dano em criaturas irradiadas"),
    ("cajado_simples", "Cajado Simples", "cajado", "arma", 350, "arcano", {"mana": 3, "magia": 4}, {}, ["mago", "clerigo"], "Mana +3, dano mágico +4"),
    ("cajado_arcano", "Cajado Arcano", "cajado", "arma", 800, "arcano", {"mana": 6, "magia": 5}, {}, ["mago", "clerigo"], "Mana +6, dano mágico +5"),
    ("cajado_mago", "Cajado do Mago", "cajado", "arma", 1600, "arcano", {"mana": 10, "int": 2}, {}, ["mago"], "Mana +10, +2 inteligência"),
    ("cajado_merlin", "Cajado de Merlin", "cajado", "arma", 3500, "arcano", {"mana": 12}, {"custo_magia_menos": 1}, ["mago"], "Mana +12, magias custam -1 mana"),
    ("cajado_arquimago", "Cajado do Arquimago", "cajado", "arma", 7000, "arcano", {"mana": 18}, {"duplicar_magia": 10}, ["mago"], "Mana +18, 10% duplicar magia"),
    ("armadura_couro", "Armadura de Couro", "armadura", "armadura", 450, "armaduras", {"def": 3}, {}, [], "Armadura +3"),
    ("armadura_ferro", "Armadura de Ferro", "armadura", "armadura", 900, "armaduras", {"def": 6}, {}, [], "Armadura +6"),
    ("armadura_reforcada", "Armadura Reforçada", "armadura", "armadura", 1600, "armaduras", {"def": 8, "hp": 5}, {}, [], "Armadura +8, HP +5"),
    ("armadura_mithril", "Armadura de Mithril", "armadura", "armadura", 4200, "armaduras", {"def": 10, "dex": 2}, {}, [], "Armadura +10, +2 destreza"),
    ("armadura_guardiao", "Armadura do Guardião", "armadura", "armadura", 6800, "armaduras", {"def": 12, "hp": 10}, {}, [], "Armadura +12, HP +10"),
    ("manto_aprendiz", "Manto do Aprendiz", "manto", "manto", 600, "arcano", {"mana": 5}, {}, ["mago", "clerigo"], "Mana +5"),
    ("manto_arcano", "Manto Arcano", "manto", "manto", 1100, "arcano", {"mana": 8, "int": 1}, {}, ["mago", "clerigo"], "Mana +8, +1 inteligência"),
    ("manto_clerigo", "Manto do Clérigo", "manto", "manto", 1300, "igreja", {"mana": 6, "cura": 2}, {}, ["clerigo"], "Mana +6, cura +2"),
    ("manto_estrelas", "Manto das Estrelas", "manto", "manto", 3200, "arcano", {"mana": 12}, {"resist_magica": 1}, ["mago", "clerigo"], "Mana +12, resistência mágica"),
    ("manto_arquimago", "Manto do Arquimago", "manto", "manto", 7500, "arcano", {"mana": 15}, {"regen_mana_turno": 1}, ["mago"], "Mana +15, regenera 1 mana por turno"),
    ("anel_mana", "Anel de Mana", "anel", "anel", 900, "arcano", {"mana": 6}, {}, [], "Mana +6"),
    ("anel_vitalidade", "Anel da Vitalidade", "anel", "anel", 1000, "armaduras", {"hp": 8}, {}, [], "HP +8"),
    ("anel_protecao", "Anel da Proteção", "anel", "anel", 1200, "armaduras", {"def": 4}, {}, [], "Armadura +4"),
    ("anel_arcano", "Anel Arcano", "anel", "anel", 2100, "arcano", {"mana": 8, "magia": 2}, {}, [], "Mana +8, dano mágico +2"),
    ("anel_poder", "Anel do Poder", "anel", "anel", 3500, "ferreiro", {"for": 2}, {}, [], "+2 força"),
    ("amuleto_vida", "Amuleto da Vida", "amuleto", "amuleto", 1600, "igreja", {"hp": 12}, {}, [], "HP +12"),
    ("amuleto_luz", "Amuleto da Luz", "amuleto", "amuleto", 2200, "igreja", {"cura": 3}, {}, ["clerigo"], "Cura +3"),
    ("amuleto_arcano", "Amuleto Arcano", "amuleto", "amuleto", 2600, "arcano", {"mana": 10}, {}, [], "Mana +10"),
    ("amuleto_guardiao", "Amuleto do Guardião", "amuleto", "amuleto", 3800, "armaduras", {"def": 5, "hp": 6}, {}, [], "Armadura +5, HP +6"),
    ("pocao_cura", "Poção de Cura", "consumivel", "consumivel", 120, "mercador", {}, {"cura_hp": 15}, [], "Cura 15 HP"),
    ("pocao_cura_grande", "Poção Grande de Cura", "consumivel", "consumivel", 260, "mercador", {}, {"cura_hp": 35}, [], "Cura 35 HP"),
    ("pocao_mana", "Poção de Mana", "consumivel", "consumivel", 140, "mercador", {}, {"cura_mana": 15}, [], "Recupera 15 mana"),
    ("pocao_arcana", "Poção Arcana", "consumivel", "consumivel", 320, "mercador", {}, {"cura_mana": 30}, [], "Recupera 30 mana"),
    ("relicario_neural", "Relicário Neural", "especial", "especial", 0, "igreja", {"mana": 5, "cura": 2}, {"cura_custa_menos": 1, "nao_vendavel": 1}, [], "Implante: mana +5, cura +2, cura custa -1 mana"),
    ("nucleo_energia_antigo", "Núcleo de Energia Antigo", "especial", "especial", 7000, "arcano", {"mana": 10}, {"regen_mana_turno": 1}, [], "Mana +10, regenera 1 mana/turno"),
    ("fragmento_ia", "Fragmento de IA", "especial", "especial", 12000, "arcano", {"int": 4}, {"prever_ataque": 1}, [], "+4 inteligência, chance de prever ataque inimigo"),
    ("olho_vigilant", "Olho do Vigilant", "especial", "especial", 18000, "arcano", {}, {"revela_ocultos": 1}, [], "Revela inimigos ocultos"),
    ("coracao_nuclear", "Coração Nuclear", "especial", "especial", 22000, "armaduras", {"hp": 20}, {"reduz_dano": 3}, [], "HP +20, reduz dano recebido em 3"),
]

INITIAL_ITEMS: Dict[str, Dict[str, Any]] = {}
for item_id, nome, tipo, slot, preco, loja, bonus, efeito, classes, desc in RAW_ITEMS:
    INITIAL_ITEMS[item_id] = {
        "nome": nome,
        "tipo": tipo,
        "slot": slot,
        "preco": preco,
        "preco_base": preco,
        "bonus": bonus,
        "efeito": efeito,
        "classes": classes,
        "desc": desc,
        "loja": loja,
        "ativo": 1,
        "deleted": 0,
    }


def now_ts() -> int:
    return int(time.time())


def jdumps(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False)


def jloads(txt: Optional[str], default: Any):
    if not txt:
        return default
    try:
        return json.loads(txt)
    except Exception:
        return default


def xp_needed(level: int) -> int:
    return max(100, int(100 * (1.20 ** max(0, level - 1))))


def class_choices() -> List[app_commands.Choice[str]]:
    return [app_commands.Choice(name=k.title(), value=k) for k in CLASSES.keys()]


def loja_choices() -> List[app_commands.Choice[str]]:
    return [app_commands.Choice(name=x.title(), value=x) for x in sorted(LOJAS_VALIDAS)]


def build_new_player(user_id: int, classe: str, level: int = 1, gold: int = 0, xp: int = 0) -> Dict[str, Any]:
    classe = (classe or "barbaro").lower().strip()
    if classe not in CLASSES:
        classe = "barbaro"
    base = dict(CLASSES[classe])
    p = {
        "user_id": user_id,
        "classe": classe,
        "level": max(1, int(level)),
        "xp": max(0, int(xp)),
        "gold": max(0, int(gold)),
        "pontos": 0,
        "hp": base["hp"],
        "mana": base["mana"],
        "stamina": base["stamina"],
        "max_stamina": base["stamina"],
        "rest_until_ts": 0,
        "last_hunt_ts": 0,
        "stats": base,
        "inventario": [],
        "equipado": {},
        "spellbook": [],
    }
    for _ in range(2, p["level"] + 1):
        p["hp"] += 5
        p["mana"] += 2 if classe in {"mago", "clerigo"} else 0
        p["stamina"] += 1
        p["max_stamina"] += 1
        p["stats"]["atk"] = int(p["stats"].get("atk", 0)) + 1
        if classe in {"barbaro", "clerigo"}:
            p["stats"]["def"] = int(p["stats"].get("def", 0)) + 1
        if classe in {"mago", "executor"}:
            p["stats"]["int"] = int(p["stats"].get("int", 0)) + 1
    return p


def item_to_row(item_id: str, it: Dict[str, Any]) -> tuple:
    return (
        item_id,
        it.get("nome", item_id),
        it.get("tipo", "especial"),
        it.get("slot", "especial"),
        int(it.get("preco", 0)),
        int(it.get("preco_base", it.get("preco", 0))),
        jdumps(it.get("bonus", {})),
        jdumps(it.get("efeito", {})),
        jdumps(it.get("classes", [])),
        it.get("desc", ""),
        it.get("loja", "mercador"),
        int(it.get("ativo", 1)),
        int(it.get("deleted", 0)),
    )


def row_to_item(r: aiosqlite.Row) -> Dict[str, Any]:
    d = dict(r)
    d["bonus"] = jloads(d.get("bonus_json"), {})
    d["efeito"] = jloads(d.get("efeito_json"), {})
    d["classes"] = jloads(d.get("classes_json"), [])
    return d


def parse_json_field(txt: str) -> Dict[str, Any]:
    try:
        obj = json.loads((txt or "").strip() or "{}")
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def parse_json_list(txt: str) -> List[str]:
    try:
        obj = json.loads((txt or "").strip() or "[]")
        return [str(x) for x in obj] if isinstance(obj, list) else []
    except Exception:
        return []


async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            classe TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0,
            gold INTEGER NOT NULL DEFAULT 0,
            pontos INTEGER NOT NULL DEFAULT 0,
            hp INTEGER NOT NULL DEFAULT 0,
            mana INTEGER NOT NULL DEFAULT 0,
            stamina INTEGER NOT NULL DEFAULT 0,
            max_stamina INTEGER NOT NULL DEFAULT 0,
            rest_until_ts INTEGER NOT NULL DEFAULT 0,
            last_hunt_ts INTEGER NOT NULL DEFAULT 0,
            stats_json TEXT NOT NULL DEFAULT '{}',
            inventario_json TEXT NOT NULL DEFAULT '[]',
            equipado_json TEXT NOT NULL DEFAULT '{}',
            spellbook_json TEXT NOT NULL DEFAULT '[]'
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            slot TEXT NOT NULL,
            preco INTEGER NOT NULL DEFAULT 0,
            preco_base INTEGER NOT NULL DEFAULT 0,
            bonus_json TEXT NOT NULL DEFAULT '{}',
            efeito_json TEXT NOT NULL DEFAULT '{}',
            classes_json TEXT NOT NULL DEFAULT '[]',
            desc TEXT NOT NULL DEFAULT '',
            loja TEXT NOT NULL DEFAULT 'mercador',
            ativo INTEGER NOT NULL DEFAULT 1,
            deleted INTEGER NOT NULL DEFAULT 0
        )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_items_loja ON items(loja, deleted, ativo)")
        await db.commit()

        cur = await db.execute("PRAGMA table_info(players)")
        pcols = {r[1] for r in await cur.fetchall()}
        if "rest_until_ts" not in pcols:
            await db.execute("ALTER TABLE players ADD COLUMN rest_until_ts INTEGER NOT NULL DEFAULT 0")
        if "last_hunt_ts" not in pcols:
            await db.execute("ALTER TABLE players ADD COLUMN last_hunt_ts INTEGER NOT NULL DEFAULT 0")
        if "max_stamina" not in pcols:
            await db.execute("ALTER TABLE players ADD COLUMN max_stamina INTEGER NOT NULL DEFAULT 0")
            await db.execute("UPDATE players SET max_stamina = stamina WHERE max_stamina = 0")

        cur = await db.execute("PRAGMA table_info(items)")
        icols = {r[1] for r in await cur.fetchall()}
        if "preco_base" not in icols:
            await db.execute("ALTER TABLE items ADD COLUMN preco_base INTEGER NOT NULL DEFAULT 0")
            await db.execute("UPDATE items SET preco_base = preco WHERE preco_base = 0")
        if "loja" not in icols:
            await db.execute("ALTER TABLE items ADD COLUMN loja TEXT NOT NULL DEFAULT 'mercador'")
        if "ativo" not in icols:
            await db.execute("ALTER TABLE items ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1")
        if "deleted" not in icols:
            await db.execute("ALTER TABLE items ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
        await db.commit()


async def seed_initial_data():
    await init_db()
    async with aiosqlite.connect(DB_FILE) as db:
        for item_id, it in INITIAL_ITEMS.items():
            await db.execute(
                """
                INSERT INTO items (item_id, nome, tipo, slot, preco, preco_base, bonus_json, efeito_json, classes_json, desc, loja, ativo, deleted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                """,
                item_to_row(item_id, it),
            )
        await db.commit()


async def get_all_items_map() -> Dict[str, Dict[str, Any]]:
    await init_db()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM items WHERE deleted=0")
        rows = await cur.fetchall()
    return {r["item_id"]: row_to_item(r) for r in rows}


async def items_list_active(loja: str) -> List[Dict[str, Any]]:
    await init_db()
    loja = (loja or "mercador").lower().strip()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM items WHERE loja=? AND deleted=0 ORDER BY preco ASC, nome COLLATE NOCASE",
            (loja,),
        )
        rows = await cur.fetchall()
    return [row_to_item(r) for r in rows]


async def item_get(item_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM items WHERE item_id=?", (item_id,))
        row = await cur.fetchone()
    return row_to_item(row) if row else None


async def item_upsert(item_id: str, it: Dict[str, Any]):
    await init_db()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO items (item_id, nome, tipo, slot, preco, preco_base, bonus_json, efeito_json, classes_json, desc, loja, ativo, deleted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ativo=excluded.ativo,
                deleted=excluded.deleted
            """,
            item_to_row(item_id, it),
        )
        await db.commit()


async def get_player(user_id: int) -> Optional[Dict[str, Any]]:
    await init_db()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM players WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
    if not row:
        return None
    return {
        "user_id": row["user_id"],
        "classe": row["classe"],
        "level": row["level"],
        "xp": row["xp"],
        "gold": row["gold"],
        "pontos": row["pontos"],
        "hp": row["hp"],
        "mana": row["mana"],
        "stamina": row["stamina"],
        "max_stamina": row["max_stamina"],
        "rest_until_ts": row["rest_until_ts"],
        "last_hunt_ts": row["last_hunt_ts"],
        "stats": jloads(row["stats_json"], {}),
        "inventario": jloads(row["inventario_json"], []),
        "equipado": jloads(row["equipado_json"], {}),
        "spellbook": jloads(row["spellbook_json"], []),
    }


async def save_player(p: Dict[str, Any]):
    await init_db()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO players (user_id, classe, level, xp, gold, pontos, hp, mana, stamina, max_stamina, rest_until_ts, last_hunt_ts, stats_json, inventario_json, equipado_json, spellbook_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            """,
            (
                int(p["user_id"]), p["classe"], int(p["level"]), int(p["xp"]), int(p["gold"]), int(p.get("pontos", 0)),
                int(p["hp"]), int(p["mana"]), int(p["stamina"]), int(p.get("max_stamina", p["stamina"])),
                int(p.get("rest_until_ts", 0)), int(p.get("last_hunt_ts", 0)),
                jdumps(p.get("stats", {})), jdumps(p.get("inventario", [])), jdumps(p.get("equipado", {})), jdumps(p.get("spellbook", []))
            ),
        )
        await db.commit()


async def delete_player(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM players WHERE user_id=?", (user_id,))
        await db.commit()


intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


async def safe_send(interaction: discord.Interaction, content: Optional[str] = None, **kwargs):
    try:
        if interaction.response.is_done():
            return await interaction.followup.send(content, **kwargs)
        return await interaction.response.send_message(content, **kwargs)
    except discord.errors.NotFound:
        try:
            return await interaction.followup.send(content, **kwargs)
        except Exception:
            return None


def mestre_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user and interaction.user.id == MESTRE_ID:
            return True
        await safe_send(interaction, "❌ Apenas o mestre pode usar este comando.", ephemeral=True)
        return False
    return app_commands.check(predicate)


def only_channel(channel_id: int, friendly: str):
    async def predicate(interaction: discord.Interaction) -> bool:
        if not channel_id or interaction.channel_id == channel_id:
            return True
        await safe_send(interaction, f"❌ Este comando só pode ser usado em **#{friendly}**.", ephemeral=True)
        return False
    return app_commands.check(predicate)


async def require_player(interaction: discord.Interaction) -> Optional[Dict[str, Any]]:
    p = await get_player(interaction.user.id)
    if not p:
        await safe_send(interaction, "❌ Você ainda não tem personagem. Use **/start**.", ephemeral=True)
    return p


def total_stat_from_items(p: Dict[str, Any], item_map: Dict[str, Dict[str, Any]], stat: str) -> int:
    base = int((p.get("stats") or {}).get(stat, 0))
    extra = 0
    for iid in (p.get("equipado") or {}).values():
        if iid and iid in item_map:
            extra += int((item_map[iid].get("bonus") or {}).get(stat, 0))
    return base + extra


def build_shop_embed(loja: str, page: int, itens: List[Dict[str, Any]]) -> discord.Embed:
    titles = {
        "mercador": "🏪 Mercador",
        "ferreiro": "⚒️ Ferreiro",
        "arcano": "🔮 Itens Arcanos",
        "armaduras": "🛡️ Armaduras",
        "igreja": "⛪ Igreja",
    }
    total = len(itens)
    total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    chunk = itens[page * ITEMS_PER_PAGE:(page + 1) * ITEMS_PER_PAGE]
    emb = discord.Embed(
        title=titles.get(loja, loja.title()),
        description="Use **/comprar item_id** para comprar e **/vender item_id** para vender por 60%.",
        color=discord.Color.green(),
    )
    if not chunk:
        emb.add_field(name="Sem itens", value="Esta loja ainda não possui itens cadastrados.", inline=False)
    for it in chunk:
        parts = [f"💰 {int(it.get('preco', 0))} gold", f"🧩 {it.get('tipo', '-')}"]
        if it.get("bonus"):
            parts.append("Bônus: " + ", ".join(f"{k}+{v}" for k, v in it["bonus"].items()))
        if it.get("efeito"):
            parts.append("Efeitos: " + ", ".join(f"{k}={v}" for k, v in it["efeito"].items()))
        if it.get("desc"):
            parts.append(it["desc"])
        emb.add_field(name=f"{it['nome']} (`{it['item_id']}`)", value="\n".join(parts), inline=False)
    emb.set_footer(text=f"Página {page+1}/{total_pages} • {total} itens")
    return emb


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
        self.page = max(0, self.page - 1)
        await interaction.response.edit_message(embed=build_shop_embed(self.loja, self.page, self.itens), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, math.ceil(len(self.itens) / ITEMS_PER_PAGE) - 1)
        self.page = min(max_page, self.page + 1)
        await interaction.response.edit_message(embed=build_shop_embed(self.loja, self.page, self.itens), view=self)

    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Loja fechada.", embed=None, view=None)


@tree.command(name="start", description="Criar seu personagem.")
@app_commands.describe(classe="Escolha sua classe")
@app_commands.choices(classe=class_choices())
async def start_cmd(interaction: discord.Interaction, classe: app_commands.Choice[str]):
    existing = await get_player(interaction.user.id)
    if existing:
        await safe_send(interaction, "❌ Você já tem personagem. Use /perfil.", ephemeral=True)
        return
    p = build_new_player(interaction.user.id, classe.value, 1, 200, 0)
    await save_player(p)
    await safe_send(interaction, f"✅ Personagem criado: **{classe.value.title()}** nível 1.", ephemeral=True)


@tree.command(name="perfil", description="Ver seu personagem.")
async def perfil_cmd(interaction: discord.Interaction):
    p = await require_player(interaction)
    if not p:
        return
    items_map = await get_all_items_map()
    emb = discord.Embed(title=f"Perfil de {interaction.user.display_name}", color=discord.Color.blurple())
    emb.add_field(name="Classe", value=p["classe"].title())
    emb.add_field(name="Nível", value=str(p["level"]))
    emb.add_field(name="XP", value=f"{p['xp']} / {xp_needed(p['level'])}")
    emb.add_field(name="Gold", value=str(p["gold"]))
    emb.add_field(name="HP", value=str(p["hp"]))
    emb.add_field(name="Mana", value=str(p["mana"]))
    emb.add_field(name="Stamina", value=f"{p['stamina']}/{p.get('max_stamina', p['stamina'])}")
    emb.add_field(name="ATK", value=str(total_stat_from_items(p, items_map, "atk")))
    emb.add_field(name="DEF", value=str(total_stat_from_items(p, items_map, "def")))
    emb.add_field(name="INT", value=str(total_stat_from_items(p, items_map, "int")))
    emb.add_field(name="DEX", value=str(total_stat_from_items(p, items_map, "dex")))
    equip = []
    for slot, iid in (p.get("equipado") or {}).items():
        if iid and iid in items_map:
            equip.append(f"**{slot}**: {items_map[iid]['nome']} (`{iid}`)")
    emb.add_field(name="Equipado", value="\n".join(equip) if equip else "Nada equipado", inline=False)
    emb.add_field(name="Inventário", value=f"{len(p.get('inventario', []))} itens", inline=False)
    await safe_send(interaction, embed=emb, ephemeral=True)


@tree.command(name="loja", description="Ver itens de uma loja.")
@only_channel(CANAL_LOJA_ID, "loja")
@app_commands.describe(loja="Escolha a loja")
@app_commands.choices(loja=loja_choices())
async def loja_cmd(interaction: discord.Interaction, loja: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True)
    p = await require_player(interaction)
    if not p:
        return
    itens = await items_list_active(loja.value)
    await interaction.followup.send(embed=build_shop_embed(loja.value, 0, itens), view=ShopView(interaction.user.id, loja.value, itens), ephemeral=True)


@tree.command(name="comprar", description="Comprar item da loja.")
@only_channel(CANAL_LOJA_ID, "loja")
async def comprar_cmd(interaction: discord.Interaction, item_id: str):
    p = await require_player(interaction)
    if not p:
        return
    item_id = item_id.lower().strip()
    it = await item_get(item_id)
    if not it or int(it.get("deleted", 0)) == 1:
        await safe_send(interaction, "❌ Item não encontrado.", ephemeral=True)
        return
    preco = int(it.get("preco", 0))
    if preco <= 0:
        await safe_send(interaction, "❌ Este item não pode ser comprado na loja.", ephemeral=True)
        return
    if p["gold"] < preco:
        await safe_send(interaction, f"❌ Gold insuficiente. Falta **{preco - p['gold']}**.", ephemeral=True)
        return
    p["gold"] -= preco
    p.setdefault("inventario", []).append(item_id)
    await save_player(p)
    await safe_send(interaction, f"✅ Você comprou **{it['nome']}** por **{preco} gold**.", ephemeral=True)


@tree.command(name="vender", description="Vender item do inventário por 60%.")
@only_channel(CANAL_LOJA_ID, "loja")
async def vender_cmd(interaction: discord.Interaction, item_id: str):
    p = await require_player(interaction)
    if not p:
        return
    item_id = item_id.lower().strip()
    if item_id not in p.get("inventario", []):
        await safe_send(interaction, "❌ Esse item não está no seu inventário.", ephemeral=True)
        return
    it = await item_get(item_id)
    if not it:
        await safe_send(interaction, "❌ Item inválido.", ephemeral=True)
        return
    if int((it.get("efeito") or {}).get("nao_vendavel", 0)) == 1:
        await safe_send(interaction, "❌ Esse item não pode ser vendido.", ephemeral=True)
        return
    valor = int(int(it.get("preco", 0)) * 0.60)
    p["inventario"].remove(item_id)
    for slot, iid in list((p.get("equipado") or {}).items()):
        if iid == item_id:
            p["equipado"][slot] = None
    p["gold"] += valor
    await save_player(p)
    await safe_send(interaction, f"✅ Você vendeu **{it['nome']}** por **{valor} gold**.", ephemeral=True)


@tree.command(name="equipar", description="Equipar item do inventário.")
async def equipar_cmd(interaction: discord.Interaction, item_id: str):
    p = await require_player(interaction)
    if not p:
        return
    item_id = item_id.lower().strip()
    if item_id not in p.get("inventario", []):
        await safe_send(interaction, "❌ Você não possui esse item.", ephemeral=True)
        return
    it = await item_get(item_id)
    if not it:
        await safe_send(interaction, "❌ Item inválido.", ephemeral=True)
        return
    if it.get("slot") == "consumivel":
        await safe_send(interaction, "❌ Consumíveis não podem ser equipados.", ephemeral=True)
        return
    classes = it.get("classes", [])
    if classes and p["classe"] not in classes:
        await safe_send(interaction, "❌ Sua classe não pode equipar esse item.", ephemeral=True)
        return
    p.setdefault("equipado", {})[it["slot"]] = item_id
    await save_player(p)
    await safe_send(interaction, f"✅ Equipado: **{it['nome']}** no slot **{it['slot']}**.", ephemeral=True)


@tree.command(name="desequipar", description="Desequipar slot.")
async def desequipar_cmd(interaction: discord.Interaction, slot: str):
    p = await require_player(interaction)
    if not p:
        return
    slot = slot.lower().strip()
    if slot not in (p.get("equipado") or {}) or not p["equipado"].get(slot):
        await safe_send(interaction, "❌ Nada equipado nesse slot.", ephemeral=True)
        return
    iid = p["equipado"][slot]
    p["equipado"][slot] = None
    await save_player(p)
    await safe_send(interaction, f"✅ Item `{iid}` removido do slot **{slot}**.", ephemeral=True)


@tree.command(name="spawn", description="(Mestre) Criar/Recriar personagem para um jogador.")
@mestre_only()
@app_commands.describe(membro="Jogador alvo", classe="Classe", nivel="Nível inicial", gold="Gold inicial", xp="XP inicial", sobrescrever="Sim para recriar")
@app_commands.choices(classe=class_choices(), sobrescrever=[app_commands.Choice(name="sim", value="sim"), app_commands.Choice(name="nao", value="nao")])
async def spawn_cmd(interaction: discord.Interaction, membro: discord.Member, classe: app_commands.Choice[str], nivel: app_commands.Range[int, 1, 100] = 1, gold: app_commands.Range[int, 0, 1000000] = 0, xp: app_commands.Range[int, 0, 1000000] = 0, sobrescrever: Optional[app_commands.Choice[str]] = None):
    existing = await get_player(membro.id)
    if existing and (not sobrescrever or sobrescrever.value != "sim"):
        await safe_send(interaction, "❌ O jogador já possui personagem. Use sobrescrever: sim para recriar.", ephemeral=True)
        return
    p = build_new_player(membro.id, classe.value, nivel, gold, xp)
    await save_player(p)
    await safe_send(interaction, f"✅ Personagem criado para {membro.mention}: **{classe.value.title()}** nível **{nivel}**.", ephemeral=True)


@tree.command(name="reset", description="(Mestre) Apagar personagem de um jogador.")
@mestre_only()
async def reset_cmd(interaction: discord.Interaction, membro: discord.Member):
    await delete_player(membro.id)
    await safe_send(interaction, f"✅ Personagem de {membro.mention} apagado.", ephemeral=True)


@tree.command(name="resetar", description="(Mestre) Alias de /reset.")
@mestre_only()
async def resetar_cmd(interaction: discord.Interaction, membro: discord.Member):
    await delete_player(membro.id)
    await safe_send(interaction, f"✅ Personagem de {membro.mention} apagado.", ephemeral=True)


@tree.command(name="darxp", description="(Mestre) Dar XP a um jogador.")
@mestre_only()
async def darxp_cmd(interaction: discord.Interaction, membro: discord.Member, quantidade: app_commands.Range[int, 1, 1000000]):
    p = await get_player(membro.id)
    if not p:
        await safe_send(interaction, "❌ Jogador sem personagem.", ephemeral=True)
        return
    p["xp"] += int(quantidade)
    subidas = 0
    while p["xp"] >= xp_needed(p["level"]):
        p["xp"] -= xp_needed(p["level"])
        p["level"] += 1
        p["hp"] += 5
        p["mana"] += 2 if p["classe"] in {"mago", "clerigo"} else 0
        p["stamina"] += 1
        p["max_stamina"] += 1
        p["stats"]["atk"] = int(p["stats"].get("atk", 0)) + 1
        subidas += 1
    await save_player(p)
    msg = f"✅ {membro.mention} recebeu **{quantidade} XP**."
    if subidas:
        msg += f" Subiu **{subidas} nível(is)** e agora está no nível **{p['level']}**."
    await safe_send(interaction, msg, ephemeral=True)


@tree.command(name="dargold", description="(Mestre) Dar gold a um jogador.")
@mestre_only()
async def dargold_cmd(interaction: discord.Interaction, membro: discord.Member, quantidade: app_commands.Range[int, 1, 1000000]):
    p = await get_player(membro.id)
    if not p:
        await safe_send(interaction, "❌ Jogador sem personagem.", ephemeral=True)
        return
    p["gold"] += int(quantidade)
    await save_player(p)
    await safe_send(interaction, f"✅ {membro.mention} recebeu **{quantidade} gold**. Total: **{p['gold']}**.", ephemeral=True)


@tree.command(name="criaritem", description="(Mestre) Criar ou atualizar item no catálogo.")
@mestre_only()
@app_commands.describe(item_id="ID único", nome="Nome", tipo="arma/armadura/manto/anel/amuleto/consumivel/especial", slot="slot", preco="Preço", loja="Loja", bonus_json="JSON bônus", efeito_json="JSON efeitos", classes_json="JSON classes", desc="Descrição")
@app_commands.choices(loja=loja_choices())
async def criaritem_cmd(interaction: discord.Interaction, item_id: str, nome: str, tipo: str, slot: str, preco: app_commands.Range[int, 0, 1000000], loja: app_commands.Choice[str], bonus_json: str = "{}", efeito_json: str = "{}", classes_json: str = "[]", desc: str = ""):
    item_id = item_id.lower().strip()
    it = {
        "nome": nome,
        "tipo": tipo.lower().strip(),
        "slot": slot.lower().strip(),
        "preco": int(preco),
        "preco_base": int(preco),
        "bonus": parse_json_field(bonus_json),
        "efeito": parse_json_field(efeito_json),
        "classes": parse_json_list(classes_json),
        "desc": desc,
        "loja": loja.value,
        "ativo": 1,
        "deleted": 0,
    }
    await item_upsert(item_id, it)
    await safe_send(interaction, f"✅ Item `{item_id}` salvo na loja **{loja.value}**.", ephemeral=True)


@tree.command(name="item_criar", description="(Mestre) Alias de /criaritem.")
@mestre_only()
@app_commands.describe(item_id="ID único", nome="Nome", tipo="tipo", slot="slot", preco="Preço", loja="Loja", bonus_json="JSON bônus", efeito_json="JSON efeitos", classes_json="JSON classes", desc="Descrição")
@app_commands.choices(loja=loja_choices())
async def item_criar_cmd(interaction: discord.Interaction, item_id: str, nome: str, tipo: str, slot: str, preco: app_commands.Range[int, 0, 1000000], loja: app_commands.Choice[str], bonus_json: str = "{}", efeito_json: str = "{}", classes_json: str = "[]", desc: str = ""):
    item_id = item_id.lower().strip()
    it = {
        "nome": nome,
        "tipo": tipo.lower().strip(),
        "slot": slot.lower().strip(),
        "preco": int(preco),
        "preco_base": int(preco),
        "bonus": parse_json_field(bonus_json),
        "efeito": parse_json_field(efeito_json),
        "classes": parse_json_list(classes_json),
        "desc": desc,
        "loja": loja.value,
        "ativo": 1,
        "deleted": 0,
    }
    await item_upsert(item_id, it)
    await safe_send(interaction, f"✅ Item `{item_id}` salvo na loja **{loja.value}**.", ephemeral=True)


@tree.command(name="sync", description="(Mestre) Forçar sincronização dos slash commands.")
@mestre_only()
async def sync_cmd(interaction: discord.Interaction):
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        tree.clear_commands(guild=guild)
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
        await safe_send(interaction, f"✅ Sync local concluído: **{len(synced)}** comandos.", ephemeral=True)
    else:
        synced = await tree.sync()
        await safe_send(interaction, f"✅ Sync global concluído: **{len(synced)}** comandos.", ephemeral=True)


@client.event
async def on_ready():
    await init_db()
    await seed_initial_data()
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        tree.clear_commands(guild=guild)
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
        print(f"Synced {len(synced)} commands to guild {GUILD_ID}")
    else:
        synced = await tree.sync()
        print(f"Synced {len(synced)} global commands")
    print(f"✅ Logado como {client.user}")


client.run(TOKEN)
