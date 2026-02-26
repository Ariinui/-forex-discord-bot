"""
=============================================================
  FOREX FACTORY — Bot Discord avec DM + Hébergement Cloud
=============================================================
- Source   : fichier .ics Forex Factory
- Filtre   : événements FORT IMPACT uniquement
- Alerte   : DM Discord 30 minutes avant (notification push)
- Résumé   : DM hebdomadaire chaque lundi
- Fuseau   : UTC-10
- Hébergé  : Railway.app (tourne 24h/24 sans PC)
=============================================================
"""

import os
import asyncio
import logging
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import discord
    from icalendar import Calendar
except ImportError:
    print("Installez : pip install discord.py icalendar")
    raise

# ==============================================================
#  CONFIGURATION
# ==============================================================

def get_config(key: str, file_name: str = None, default: str = None) -> str:
    """
    Lit une config depuis :
      1. Variable d'environnement (Railway)
      2. Fichier sur le bureau (local)
      3. Valeur par défaut
    """
    # 1. Variable d'environnement (Railway / .env)
    val = os.environ.get(key)
    if val:
        return val.strip()

    # 2. Fichier sur le bureau
    if file_name:
        desktop_paths = [
            Path(os.environ.get("USERPROFILE", ""), "Desktop", file_name),
            Path(os.environ.get("USERPROFILE", ""), "Desktop", file_name + ".txt"),
            Path(os.environ.get("HOME", ""), "Desktop", file_name),
            Path("C:/Users/ariin/Desktop", file_name),
            Path("C:/Users/ariin/Desktop", file_name + ".txt"),
        ]
        for p in desktop_paths:
            if p.exists():
                content = p.read_text(encoding="utf-8").strip()
                if content:
                    return content

    if default:
        return default

    raise ValueError(f"Configuration manquante : {key} / {file_name}")


# Tokens & IDs
BOT_TOKEN       = get_config("DISCORD_BOT_TOKEN",     "Discord BOT TOKEN.txt")
DISCORD_USER_ID = int(get_config("DISCORD_USER_ID",   default="823007239521828916"))
WEBHOOK_URL     = get_config("DISCORD_WEBHOOK_URL",    "Discord WEBHOOK.txt")

# Forex Factory
FOREX_ICS_URL   = "https://nfs.faireconomy.media/ff_calendar_thisweek.ics"
ICS_CACHE_FILE  = "ff_calendar_cache.ics"
SENT_FILE       = "sent_alerts.json"

# Fuseau UTC-10
UTC_MINUS_10        = timezone(timedelta(hours=-10))
TZ_LABEL            = "UTC-10"
ALERT_BEFORE_MIN    = 30

# ==============================================================
#  LOGGING
# ==============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("forex_bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ==============================================================
#  DRAPEAUX DEVISES
# ==============================================================
CURRENCY_FLAGS = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "AUD": "🇦🇺", "CAD": "🇨🇦", "CHF": "🇨🇭", "NZD": "🇳🇿",
    "CNY": "🇨🇳", "CNH": "🇨🇳", "SGD": "🇸🇬", "HKD": "🇭🇰",
}

# ==============================================================
#  ANTI-DOUBLON
# ==============================================================
def load_sent() -> set:
    if os.path.exists(SENT_FILE):
        try:
            return set(json.load(open(SENT_FILE, encoding="utf-8")))
        except Exception:
            pass
    return set()

def save_sent(sent: set):
    json.dump(list(sent), open(SENT_FILE, "w", encoding="utf-8"), indent=2)

# ==============================================================
#  SCRAPING .ICS
# ==============================================================
def fetch_ics() -> bytes:
    headers = {"User-Agent": "Mozilla/5.0"}
    log.info(f"📥 Téléchargement ICS Forex Factory...")
    r = requests.get(FOREX_ICS_URL, headers=headers, timeout=30)
    r.raise_for_status()
    with open(ICS_CACHE_FILE, "wb") as f:
        f.write(r.content)
    log.info(f"✅ ICS téléchargé ({len(r.content)} octets)")
    return r.content

def load_cache() -> bytes:
    with open(ICS_CACHE_FILE, "rb") as f:
        return f.read()

def extract_currency(summary: str) -> str:
    currencies = ["USD","EUR","GBP","JPY","AUD","CAD","CHF","NZD","CNY","CNH","SGD","HKD","NOK","SEK","DKK","MXN","ZAR","BRL","INR","KRW","TRY"]
    country_map = {"AU":"AUD","US":"USD","UK":"GBP","EU":"EUR","CA":"CAD","NZ":"NZD","JP":"JPY","CH":"CHF","CN":"CNY","SG":"SGD","HK":"HKD","NO":"NOK","SE":"SEK","DK":"DKK","MX":"MXN","ZA":"ZAR","BR":"BRL","IN":"INR","KR":"KRW","TR":"TRY","DE":"EUR","FR":"EUR","IT":"EUR","ES":"EUR"}
    clean = summary.replace("⁂","").replace("*","").strip().upper()
    for p in clean.split():
        if p in currencies:
            return p
        if p in country_map:
            return country_map[p]
    return "???"

def is_high_impact(component) -> bool:
    desc = str(component.get("DESCRIPTION",""))
    cats = str(component.get("CATEGORIES","")).lower()
    if "high" in cats:
        return True
    for sep in ("\\n","\n"):
        for line in desc.split(sep):
            if line.strip().lower() == "high":
                return True
    if "impact: high" in desc.lower():
        return True
    return False

def parse_events(ics_data: bytes) -> list:
    cal    = Calendar.from_ical(ics_data)
    events = []
    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        if not is_high_impact(comp):
            continue
        dtstart = comp.get("DTSTART")
        if not dtstart:
            continue
        dt = dtstart.dt
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = datetime(dt.year, dt.month, dt.day, 0, 0, 0, tzinfo=timezone.utc)

        summary  = str(comp.get("SUMMARY","")).strip()
        uid      = str(comp.get("UID", f"{summary}_{dt.isoformat()}")).strip()
        url      = str(comp.get("URL","")).strip()
        currency = extract_currency(summary)

        events.append({
            "uid":      uid,
            "summary":  summary,
            "url":      url,
            "currency": currency,
            "dt_utc":   dt,
            "dt_local": dt.astimezone(UTC_MINUS_10),
        })

    events.sort(key=lambda e: e["dt_utc"])
    log.info(f"📊 {len(events)} événements FORT IMPACT détectés")
    return events

# ==============================================================
#  MESSAGES DISCORD
# ==============================================================

def build_alert_embed(event: dict, is_test: bool = False) -> discord.Embed:
    """Embed alerte T-30min — design intuitif, coloré, lisible."""
    currency    = event["currency"]
    flag        = CURRENCY_FLAGS.get(currency, "🌐")
    title_clean = event["summary"].replace("⁂","").strip()
    t_local     = event["dt_local"].strftime("%H:%M")
    date_local  = event["dt_local"].strftime("%A %d %B %Y")

    embed = discord.Embed(
        title       = f"🔴 ALERTE FORT IMPACT — Dans 30 minutes !",
        description = (
            f"**{flag} {currency} — {title_clean}**\n\n"
            f"⏰ **Heure :** `{t_local}` {TZ_LABEL} — {date_local}\n"
            + (f"\n🔗 [Voir sur Forex Factory]({event['url']})" if event["url"] else "")
        ),
        color       = discord.Color.red(),
        timestamp   = event["dt_utc"],
    )
    if event["url"]:
        embed.url = event["url"]
    embed.set_footer(text=f"Forex Factory  ·  Impact: 🔴 Élevé  ·  {TZ_LABEL}{'  ·  [TEST]' if is_test else ''}")
    return embed


def build_weekly_embeds(events: list) -> list:
    """Embeds résumé hebdomadaire — structuré, aéré, un embed par jour."""
    from collections import defaultdict

    now_local = datetime.now(UTC_MINUS_10)

    DAY_NAMES  = {0:"Lundi",1:"Mardi",2:"Mercredi",3:"Jeudi",4:"Vendredi",5:"Samedi",6:"Dimanche"}
    DAY_EMOJIS = {0:"🔵",1:"🟣",2:"🟢",3:"🟠",4:"🔴",5:"⚪",6:"⚪"}
    DAY_COLORS = {
        0: 0x3498DB, 1: 0x9B59B6, 2: 0x1ABC9C,
        3: 0xE67E22, 4: 0xE74C3C, 5: 0x95A5A6, 6: 0x95A5A6,
    }

    # Stats devises
    ccy_count: dict = {}
    for ev in events:
        ccy_count[ev["currency"]] = ccy_count.get(ev["currency"],0) + 1
    ccy_bar = "  ".join(
        f"{CURRENCY_FLAGS.get(c,'🌐')} **{c}** `×{n}`"
        for c,n in sorted(ccy_count.items(), key=lambda x:-x[1])
    )

    # Embed header
    header = discord.Embed(
        title       = f"📅  Calendrier Économique — Semaine du {now_local.strftime('%d %B %Y')}",
        description = (
            f"> 🔴 **{len(events)} événement(s) à FORT IMPACT** cette semaine\n"
            f"> ⏰  Toutes les heures en **{TZ_LABEL}** — Alerte **30 min** avant chaque release\n"
            f"> 📡  Source : Forex Factory ICS — Mis à jour chaque lundi\n"
            f"\n**Devises sous surveillance**\n{ccy_bar}"
        ),
        color       = 0xFF6600,
    )
    header.set_footer(text=f"Généré le {now_local.strftime('%A %d %B %Y à %H:%M')} {TZ_LABEL}  ·  Forex Factory")

    # Embeds par jour
    days: dict = defaultdict(list)
    for ev in events:
        days[ev["dt_local"].date()].append(ev)

    day_embeds = []
    for day_date in sorted(days.keys()):
        day_events = sorted(days[day_date], key=lambda e: e["dt_utc"])
        weekday    = day_date.weekday()
        lines = []
        for ev in day_events:
            flag = CURRENCY_FLAGS.get(ev["currency"],"🌐")
            t    = ev["dt_local"].strftime("%H:%M")
            name = ev["summary"].replace("⁂","").strip()
            url  = ev.get("url","")
            line = f"**`{t}`** {TZ_LABEL}  ·  {flag} **{ev['currency']}**  —  {name}"
            if url:
                line += f"  [↗]({url})"
            lines.append(line)

        emb = discord.Embed(
            title       = f"{DAY_EMOJIS.get(weekday,'⚪')}  {DAY_NAMES.get(weekday,'')}  ·  {day_date.strftime('%d %B %Y')}",
            description = f"\n{'─'*32}\n".join(lines),
            color       = DAY_COLORS.get(weekday, 0x95A5A6),
        )
        emb.set_footer(text=f"{len(day_events)} release(s)  ·  Alerte T−30min  ·  {TZ_LABEL}")
        day_embeds.append(emb)

    return [header] + day_embeds

# ==============================================================
#  BOT DISCORD
# ==============================================================

class ForexBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.events      = []
        self.sent        = load_sent()
        self.summary_sent_week = None

    async def on_ready(self):
        log.info(f"✅ Bot connecté : {self.user} (ID: {self.user.id})")
        # Lance la boucle de surveillance
        self.loop.create_task(self.weekly_loop())

    async def send_dm(self, content: str = None, embeds: list = None):
        """Envoie un DM à l'utilisateur configuré."""
        try:
            user = await self.fetch_user(DISCORD_USER_ID)
            if content:
                await user.send(content=content)
            if embeds:
                # Discord limite à 10 embeds par message
                for i in range(0, len(embeds), 10):
                    chunk = embeds[i:i+10]
                    await user.send(embeds=chunk)
                    await asyncio.sleep(0.5)
            log.info(f"✅ DM envoyé à l'utilisateur {DISCORD_USER_ID}")
        except discord.Forbidden:
            log.error("❌ Impossible d'envoyer un DM — vérifiez que le bot partage un serveur avec vous et que vos DM sont ouverts.")
        except Exception as e:
            log.error(f"❌ Erreur DM : {e}")

    async def weekly_loop(self):
        """Boucle principale : chargement ICS lundi + surveillance semaine."""
        await self.wait_until_ready()

        while not self.is_closed():
            now_utc   = datetime.now(timezone.utc)
            now_local = now_utc.astimezone(UTC_MINUS_10)

            # ── Chargement ICS chaque lundi (ou si cache vide) ──
            is_monday = now_local.weekday() == 0
            cache_ok  = os.path.exists(ICS_CACHE_FILE)
            week_key  = now_local.strftime("%Y-W%W")

            if is_monday and self.summary_sent_week != week_key:
                try:
                    ics_data     = fetch_ics()
                    self.events  = parse_events(ics_data)
                    self.sent    = load_sent()  # reset partiel

                    # Résumé hebdomadaire en DM
                    if self.events:
                        embeds = build_weekly_embeds(self.events)
                        await self.send_dm(
                            content = "## 📊  RÉSUMÉ HEBDOMADAIRE — Événements Forex à Fort Impact\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                            embeds  = embeds,
                        )
                    else:
                        await self.send_dm(content="📅 Aucun événement à fort impact cette semaine.")

                    self.summary_sent_week = week_key
                    log.info(f"✅ Résumé hebdomadaire envoyé — semaine {week_key}")

                except Exception as e:
                    log.error(f"Erreur chargement ICS : {e}")
                    if cache_ok and not self.events:
                        self.events = parse_events(load_cache())

            elif not self.events and cache_ok:
                # Recharge depuis le cache si redémarrage en milieu de semaine
                self.events = parse_events(load_cache())

            # ── Vérification alertes T-30min ──────────────────────
            window_start = now_utc + timedelta(minutes=ALERT_BEFORE_MIN - 1)
            window_end   = now_utc + timedelta(minutes=ALERT_BEFORE_MIN + 1)

            for ev in self.events:
                if window_start <= ev["dt_utc"] <= window_end:
                    alert_id = f"alert_{ev['uid']}_{ev['dt_utc'].isoformat()}"
                    if alert_id not in self.sent:
                        log.info(f"⚡ Alerte T-30min : {ev['summary']}")
                        embed = build_alert_embed(ev)
                        await self.send_dm(
                            content = "⚠️ **Actualité économique FORT IMPACT dans 30 minutes !**",
                            embeds  = [embed],
                        )
                        self.sent.add(alert_id)
                        save_sent(self.sent)

            # Nettoyage anti-débordement
            if len(self.sent) > 5000:
                self.sent = set(list(self.sent)[-2000:])
                save_sent(self.sent)

            # Pause 60 secondes
            await asyncio.sleep(60)


# ==============================================================
#  MODE TEST
# ==============================================================
async def test_dm():
    """Test : envoie le résumé + une alerte simulée en DM."""
    log.info("--- MODE TEST DM ---")

    intents = discord.Intents.default()
    client  = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        log.info(f"✅ Bot connecté : {client.user}")
        try:
            # Télécharge le ICS
            try:
                ics_data = fetch_ics()
            except Exception:
                ics_data = load_cache()

            events = parse_events(ics_data)
            user   = await client.fetch_user(DISCORD_USER_ID)

            if not events:
                await user.send(content="✅ **[TEST]** Bot opérationnel. Aucun événement fort impact cette semaine.")
            else:
                # Résumé hebdomadaire
                embeds = build_weekly_embeds(events)
                await user.send(
                    content = "## 📊  RÉSUMÉ HEBDOMADAIRE — Événements Forex à Fort Impact\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                    embeds  = embeds[:10],
                )
                await asyncio.sleep(1)
                if len(embeds) > 10:
                    await user.send(embeds=embeds[10:])

                # Alerte simulée sur le prochain événement
                now_utc = datetime.now(timezone.utc)
                future  = [e for e in events if e["dt_utc"] > now_utc]
                target  = future[0] if future else events[-1]
                embed   = build_alert_embed(target, is_test=True)
                await user.send(
                    content = "⚠️ **[TEST] Actualité économique FORT IMPACT dans 30 minutes !**",
                    embeds  = [embed],
                )
                log.info("✅ Test DM terminé. Vérifiez vos messages privés Discord !")

        except discord.Forbidden:
            log.error("❌ DM bloqués — ouvrez vos messages privés ou invitez le bot sur votre serveur.")
        except Exception as e:
            log.error(f"❌ Erreur : {e}")
        finally:
            await client.close()

    await client.start(BOT_TOKEN)


# ==============================================================
#  POINT D'ENTREE
# ==============================================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(test_dm())
    else:
        bot = ForexBot()
        bot.run(BOT_TOKEN)
