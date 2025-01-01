import os
import sqlite3
import requests
from twitchio.ext import commands
import time
import random
from datetime import datetime
import sys
import subprocess
import asyncio
from datetime import datetime, timedelta
import fakten
import witze
import aiohttp
import twitchio
import re
import psutil
from datetime import datetime, date, timedelta
from datetime import date, datetime
from dateutil.parser import parse as parse_date
# Importiere den Befehl aus der neuen Datei
current_meteor = None
active_channels_with_messages = []
congratulated_users = set()


# Konfiguration
BOT_USERNAME = "ty7v"  # Twitch-Benutzername des Bots
ACCESS_TOKEN = "oauth:"  # OAuth Access Token
CLIENT_ID = ""  # Twitch Client-ID
CHANNELS_FILE = "channels.db"  # Datei für gespeicherte Kanäle




# Datenbank initialisieren
def init_db():
    conn = sqlite3.connect("channels.db")
    c = conn.cursor()

    # Tabelle für Kanäle
    c.execute('''CREATE TABLE IF NOT EXISTS channels (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE NOT NULL,
                  joined_at TEXT NOT NULL,
                  is_active INTEGER NOT NULL DEFAULT 0
              )''')

    # Tabelle für Nutzer und Schlafstatus
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  sleep_time TEXT,
                  sleep_message TEXT,
                  sleeping INTEGER NOT NULL DEFAULT 0
              )''')

    conn.commit()
    conn.close()

def init_leaderboard_db():
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS leaderboard_visibility (
                  username TEXT PRIMARY KEY,
                  visible_in_leaderboard INTEGER DEFAULT 1
              )''')

    conn.commit()
    conn.close()


def init_birthday_db():
    """Initialisiert die `birthdays.db`-Datenbank."""
    conn = sqlite3.connect("birthdays.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS birthdays (
            username TEXT PRIMARY KEY,
            birthday TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()



def init_intervals_db(db_path="intervals.db"):
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS intervals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    is_live INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL
                )
            """)
            conn.commit()
    except sqlite3.Error as e:
        print(f"Fehler bei der Datenbankinitialisierung (Intervalle): {e}")

init_intervals_db()


async def check_live_status(self, channel_name):
        try:
            async with self._http.session.get(f"https://api.twitch.tv/helix/streams?user_login={channel_name}", headers=self._http.headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return bool(data['data']) #True wenn live, False wenn nicht
                return False #Fehler beim Abruf
        except Exception as e:
            print(f"Fehler beim Überprüfen des Live-Status: {e}")
            return False

async def send_interval_message(self, channel_name, message):
      try:
        target_channel = self.get_channel(channel_name)
        if target_channel:
            await target_channel.send(message)
        else:
            print(f"Kanal {channel_name} nicht gefunden.")
      except Exception as e:
        print(f"Fehler beim Senden der Intervallnachricht: {e}")

async def run_interval(self, interval_id, channel_name, interval_seconds, is_live, message):
        while True:
            if is_live:
                live_status = await self.check_live_status(channel_name)
                if live_status:
                    await self.send_interval_message(channel_name, message)
            else:
                await self.send_interval_message(channel_name, message)
            await asyncio.sleep(interval_seconds)

async def start_intervals(self):
        try:
            with sqlite3.connect("intervals.db") as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, channel, interval_seconds, is_live, message FROM intervals")
                intervals = cursor.fetchall()

                for interval in intervals:
                    interval_id, channel_name, interval_seconds, is_live, message = interval
                    task = asyncio.create_task(self.run_interval(interval_id, channel_name, interval_seconds, bool(is_live), message))
                    self.interval_tasks[interval_id] = task
        except sqlite3.Error as e:
            print(f"Fehler beim Starten der Intervalle aus der Datenbank: {e}")


def init_bet_stats_db():
    """Initialisiert die Datenbank für Bet-Statistiken."""
    conn = sqlite3.connect("bet_stats.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS bet_stats (
            username TEXT PRIMARY KEY,
            total_bets INTEGER DEFAULT 0,
            won_deidis INTEGER DEFAULT 0,
            lost_deidis INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()


def init_counters_db():
    """Initialisiert die Datenbank für Counter."""
    conn = sqlite3.connect("counters.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS counters (
            channel TEXT,
            name TEXT,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (channel, name)
        )
    ''')
    conn.commit()
    conn.close()



def init_deidis_db_v2():
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    try:
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        table_exists = c.fetchone()

        if table_exists:
            #print("Tabelle 'users' existiert bereits. Starte Migration...")
            c.execute("ALTER TABLE users RENAME TO users_old;")
            c.execute('''
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    deidis INTEGER NOT NULL DEFAULT 0,
                    last_collect_time TEXT,
                    total_bets INTEGER NOT NULL DEFAULT 0,
                    won_bets INTEGER NOT NULL DEFAULT 0,
                    lost_bets INTEGER NOT NULL DEFAULT 0,
                    rank INTEGER NOT NULL DEFAULT 0,
                    double_collect INTEGER NOT NULL DEFAULT 0,
                    fast_collect INTEGER NOT NULL DEFAULT 0,
                    power_up_end_time TEXT
                );
            ''')
            try:
                c.execute("""
                    INSERT INTO users
                    SELECT MIN(id), LOWER(username), deidis, last_collect_time, total_bets, won_bets, lost_bets, rank, double_collect, fast_collect, power_up_end_time
                    FROM users_old
                    GROUP BY LOWER(username);
                """)
                #print("Daten erfolgreich migriert (Duplikate bereinigt).")
            except sqlite3.IntegrityError as e:
                print(f"Fehler beim Migrieren der Daten: {e}")
                print("Bitte überprüfe die doppelten Einträge manuell in users_old.")
            c.execute("DROP TABLE users_old;")
            #print("Alte Tabelle 'users_old' gelöscht.")
        else:
            print("Tabelle 'users' existiert noch nicht. Erstelle Tabelle mit COLLATE NOCASE...")
            c.execute('''
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    deidis INTEGER NOT NULL DEFAULT 0,
                    last_collect_time TEXT,
                    total_bets INTEGER NOT NULL DEFAULT 0,
                    won_bets INTEGER NOT NULL DEFAULT 0,
                    lost_bets INTEGER NOT NULL DEFAULT 0,
                    rank INTEGER NOT NULL DEFAULT 0,
                    double_collect INTEGER NOT NULL DEFAULT 0,
                    fast_collect INTEGER NOT NULL DEFAULT 0,
                    power_up_end_time TEXT
                );
            ''')
            print("Tabelle users wurde erstellt.")
    except sqlite3.Error as e:
        print(f"Ein Datenbankfehler ist aufgetreten: {e}")
    finally:
        conn.commit()
        conn.close()

def init_notify_db():
    """Initialisiert die Datenbank für Benachrichtigungen."""
    conn = sqlite3.connect("notify.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            username TEXT PRIMARY KEY,
            notifications_enabled INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()


def init_timer_db():
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS timer (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL,
                  end_time TEXT NOT NULL,
                  title TEXT NOT NULL
              )''')

    conn.commit()
    conn.close()

init_timer_db()

def ensure_timer_table():
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS timer (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL,
                  end_time TEXT NOT NULL,
                  title TEXT NOT NULL,
                  channel TEXT NOT NULL
              )''')

    conn.commit()
    conn.close()

ensure_timer_table()

def init_meteor_stats_db():
    """Initialisiert die Datenbank für Meteor-Statistiken."""
    conn = sqlite3.connect("meteor_stats.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS meteor_stats (
            username TEXT PRIMARY KEY,
            meteors_collected INTEGER DEFAULT 0,
            deidis_won INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()


import sqlite3

def init_noti_db():
    """Initialisiert die `noti.db`-Datenbank."""
    conn = sqlite3.connect("noti.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            username TEXT PRIMARY KEY,
            should_notify INTEGER DEFAULT 0,
            is_notified INTEGER DEFAULT 0,
            last_collected TEXT
        )
    ''')
    conn.commit()
    conn.close()




def add_channel_column_to_timer():
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    try:
        # Überprüfen, ob die Spalte "channel" bereits existiert
        c.execute("PRAGMA table_info(timer)")
        columns = [column[1] for column in c.fetchall()]
        if "channel" not in columns:
            c.execute("ALTER TABLE timer ADD COLUMN channel TEXT DEFAULT 'unknown'")
            print("Spalte 'channel' wurde zur Tabelle 'timer' hinzugefügt.")
        else:
            print("")
    except sqlite3.Error as e:
        print(f"Fehler beim Hinzufügen der Spalte: {e}")
    finally:
        conn.commit()
        conn.close()

add_channel_column_to_timer()


conn = sqlite3.connect("deidis_v2.db")
c = conn.cursor()
def init_cooldown_db():
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS cooldowns (
                user_id TEXT NOT NULL COLLATE NOCASE,
                command_name TEXT NOT NULL COLLATE NOCASE,
                last_used TEXT,
                PRIMARY KEY (user_id, command_name)
            )
        """)
        conn.commit()
        print("Cooldown Datenbank initialisiert/überprüft.")
    except sqlite3.Error as e:
        print(f"Fehler bei der Initialisierung der Cooldown-Datenbank: {e}")

def init_notifications_db():
    conn = sqlite3.connect("notifications.db")
    c = conn.cursor()

    # Tabelle für Benachrichtigungseinstellungen
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                  username TEXT UNIQUE NOT NULL,
                  notifications_enabled INTEGER NOT NULL DEFAULT 0,
                  notified INTEGER NOT NULL DEFAULT 0
              )''')

    conn.commit()
    conn.close()


def init_steal_stats_db():
    """Initialisiert die Datenbank für Steal-Statistiken."""
    conn = sqlite3.connect("steal_stats.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS steal_stats (
            username TEXT PRIMARY KEY,
            stolen_from_others INTEGER DEFAULT 0,
            stolen_by_others INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()


def check_cooldown_db(username, command_name, cooldown_seconds):
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()
    now = datetime.now()

    try:
        c.execute("SELECT last_used FROM cooldowns WHERE user_id = ? AND command_name = ?", (username, command_name))
        result = c.fetchone()

        if result:
            last_used = datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
            elapsed_time = (now - last_used).total_seconds()

            if elapsed_time < cooldown_seconds:
                remaining_time = cooldown_seconds - elapsed_time
                conn.close()
                return False, int(remaining_time)

        # Cooldown aktualisieren
        c.execute("INSERT OR REPLACE INTO cooldowns (user_id, command_name, last_used) VALUES (?, ?, ?)",
                  (username, command_name, now.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        return True, 0

    except sqlite3.Error as e:
        print(f"Datenbankfehler beim Cooldown-Check: {e}")
        conn.close()
        return False, 0


def ensure_shop_table():
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS shop (id INTEGER PRIMARY KEY, power_up_name TEXT, cost INTEGER, duration_hours INTEGER)")
    conn.commit()
    conn.close()



def list_shop_items():
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()
    c.execute("SELECT * FROM shop")
    items = c.fetchall()
    conn.close()
    #print("Shop-Items:", items)

list_shop_items()
ensure_shop_table()


def parse_time_string(time_str):
        match = re.match(r"(\d+)(s|m|h)", time_str)
        if not match:
            raise ValueError("Ungültiges Zeitformat. Verwende z.B. 60s, 10m oder 1h.")
        value = int(match.group(1))
        unit = match.group(2)
        if unit == "s":
            return value
        elif unit == "m":
            return value * 60
        elif unit == "h":
            return value * 3600
        return 0


def init_channels_v2_db():
    conn = sqlite3.connect("channels.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS channels_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_channels_v2_db()


def ensure_power_up_columns():
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()
    c.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in c.fetchall()]
    
    if "double_collect" not in columns:
        c.execute("ALTER TABLE users ADD COLUMN double_collect INTEGER DEFAULT 0")
    if "fast_collect" not in columns:
        c.execute("ALTER TABLE users ADD COLUMN fast_collect INTEGER DEFAULT 0")
    if "power_up_end_time" not in columns:
        c.execute("ALTER TABLE users ADD COLUMN power_up_end_time TEXT")
    
    conn.commit()
    conn.close()

ensure_power_up_columns()

def remove_channel(channel_name):
    conn = sqlite3.connect("channels.db")
    c = conn.cursor()
    try:
        c.execute("DELETE FROM channels WHERE name = ?", (channel_name,))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Fehler beim Entfernen des Kanals: {e}")
    finally:
        conn.close()



def days_until_birthday(day, month):
    """Berechnet die Tage bis zum nächsten Geburtstag."""
    try:
        day = int(day)
        month = int(month)
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return None #Ungültiges Datum
    except ValueError:
        return None  # Ungültige Eingabe (keine Zahlen)

    today = date.today()
    this_year_birthday = date(today.year, month, day)

    if this_year_birthday < today:
        next_year_birthday = date(today.year + 1, month, day)
        days_remaining = (next_year_birthday - today).days
    else:
        days_remaining = (this_year_birthday - today).days

    return days_remaining

def parse_birthday(birthday_str):
    """Parses birthday string in format "DD.MM"."""
    try:
        day_str, month_str = birthday_str.split(".")
        day = int(day_str)
        month = int(month_str)
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return None
        return day, month
    except ValueError:
        return None  # Ungültiges Format



def calculate_easter(year):
    """Berechnet das Osterdatum für ein gegebenes Jahr (Gauss'sche Osterformel)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def debug_user_data(username):
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    user_data = c.fetchone()
    conn.close()

    if user_data:
        print(f"Debugging-Daten für {username}: {user_data}")
    else:
        print(f"Benutzer {username} nicht in der Datenbank gefunden.")






async def send_join_message(channel_name, bot, ctx):
    """
    Sendet eine Begrüßungsnachricht an einen Twitch-Kanal.
    """
    message = "👋"
    print(f"Versuche, Nachricht an {channel_name} zu senden: {message}")
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.ivr.fi/v2/twitch/user?login={channel_name}"
            print(f"API-Abfrage: {url}")
            async with session.get(url) as response:
                print(f"API-Antwortstatus: {response.status}")
                if response.status != 200:
                    raise Exception(f"HTTP Say Error: {response.status}")
                data = await response.json()
                print(f"API-Daten:")
                if not data:
                    return f"➜ {channel_name} nicht gefunden"

        target_channel = bot.get_channel(channel_name)
        print(f"Target Channel: {target_channel}")
        if target_channel:
            try:
                await target_channel.send(message)
                print(f"Nachricht erfolgreich gesendet: {message}") #Erfolgsmeldung hinzugefügt
            except Exception as send_error:
                print(f"FEHLER beim tatsächlichen Senden der Nachricht: {send_error}")
                return f"FEHLER beim Senden der Nachricht: {send_error}" #Fehler zurückgeben
            if ctx.channel.name != channel_name:
                await ctx.reply(f"Ich bin jetzt auf deinem Kanal {channel_name}!🎉 Schreibe &commands für Hilfe") #Bestätigung im Chat des Nutzers
            return f"Begrüßungsnachricht an {channel_name} gesendet!"
        else:
            return f"Kanal {channel_name} nicht gefunden. Ist der Bot bereits im Kanal?"
    except Exception as error:
        print(f"FEHLER in send_join_message: {error}")
        return f"FEHLER in send_join_message: {error}"


def create_shop_entry(power_up_name, cost, duration_hours):
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO shop (power_up_name, cost, duration_hours) VALUES (?, ?, ?)", (power_up_name, cost, duration_hours))
        conn.commit()
        print(f"✅ Power-up '{power_up_name}' wurde zum Shop hinzugefügt.")
    except sqlite3.Error as e:
        print(f"❌ Fehler beim Hinzufügen des Power-ups zum Shop: {e}")
        conn.rollback()
    finally:
        conn.close()

def toggle_notifications(username):
    conn = sqlite3.connect("notifications.db")
    c = conn.cursor()

    # Überprüfen, ob der Benutzer existiert
    c.execute("SELECT notifications_enabled FROM users WHERE username = ?", (username,))
    user = c.fetchone()

    if user:
        # Umschalten des Benachrichtigungsstatus
        new_status = 0 if user[0] == 1 else 1
        c.execute("UPDATE users SET notifications_enabled = ? WHERE username = ?", (new_status, username))
    else:
        # Neuen Benutzer mit deaktivierten Benachrichtigungen hinzufügen
        new_status = 0
        c.execute("INSERT INTO users (username, notifications_enabled) VALUES (?, ?)", (username, new_status))

    conn.commit()
    conn.close()
    return new_status



def update_deidis(username, deidis_change):
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()
    try:
        c.execute("UPDATE users SET deidis = deidis + ? WHERE username = ?", (deidis_change, username))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Fehler beim Aktualisieren der Deidis: {e}")
        conn.rollback()
    finally:
        conn.close()




def parse_date(input_date):
    """Parst das Datum in verschiedene Formate und gibt es als 'TT.MM.JJJJ' zurück."""
    formats = [
        "%d.%m.%Y",  # 01.01.2023
        "%d.%m",     # 01.01 (aktuelles Jahr wird ergänzt)
        "%d/%m/%Y",  # 01/01/2023
        "%d/%m",     # 01/01 (aktuelles Jahr wird ergänzt)
        "%d %B %Y",  # 1 Januar 2023
        "%d %B",     # 1 Januar (aktuelles Jahr wird ergänzt)
        "%d %b %Y",  # 1 Jan 2023
        "%d %b"      # 1 Jan (aktuelles Jahr wird ergänzt)
    ]

    for date_format in formats:
        try:
            parsed_date = datetime.strptime(input_date, date_format)
            # Ergänze das aktuelle Jahr, falls es fehlt
            if "%Y" not in date_format:
                parsed_date = parsed_date.replace(year=datetime.now().year)
            return parsed_date.strftime("%d.%m.%Y")
        except ValueError:
            continue

    raise ValueError("Ungültiges Datum.")


def parse_timer_input(time_input: str):
    now = datetime.now()

    try:
        if time_input.isdigit():  # Zahl ohne Suffix (Standard: Sekunden)
            return now + timedelta(seconds=int(time_input))
        elif time_input.endswith("s"):
            return now + timedelta(seconds=int(time_input[:-1]))
        elif time_input.endswith("m"):
            return now + timedelta(minutes=int(time_input[:-1]))
        elif time_input.endswith("h"):
            return now + timedelta(hours=int(time_input[:-1]))
        elif time_input.endswith("t"):
            return now + timedelta(days=int(time_input[:-1]))
        elif ":" in time_input:  # Zeitformat 00:00
            future_time = datetime.strptime(time_input, "%H:%M")
            return now.replace(hour=future_time.hour, minute=future_time.minute, second=0)
        elif "." in time_input:  # Datum und Zeitformat 01.01.0000
            future_date = datetime.strptime(time_input, "%d.%m.%Y")
            return future_date
        else:
            raise ValueError("Ungültiges Zeitformat")
    except Exception as e:
        print(f"Fehler beim Verarbeiten der Zeitangabe: {e}")
        return None

def convert_currency(amount, from_currency, to_currency):
    """Konvertiert Währungen mit Echtzeitdaten."""
    api_url = f"https://api.exchangerate.host/convert?from={from_currency}&to={to_currency}&amount={amount}"
    
    try:
        response = requests.get(api_url)
        response.raise_for_status()  # Hebt HTTP-Fehler hervor
        data = response.json()
        
        # Überprüfen, ob das Ergebnis vorhanden ist
        if "result" in data and data["result"] is not None:
            return data["result"]
        else:
            raise ValueError(f"Ungültige Währungsumrechnung: {from_currency} -> {to_currency}")
    
    except requests.RequestException as e:
        raise ValueError(f"Fehler bei der API-Abfrage: {e}")
    except Exception as e:
        raise ValueError(f"Ein unbekannter Fehler ist aufgetreten: {e}")



def convert_time(value, from_unit, to_unit):
    """Konvertiert Zeiteinheiten."""
    time_units = {
        "s": 1,       # Sekunden
        "m": 60,      # Minuten
        "h": 3600,    # Stunden
        "d": 86400    # Tage
    }

    if from_unit not in time_units or to_unit not in time_units:
        raise ValueError(f"Ungültige Zeiteinheit: {from_unit} -> {to_unit}")

    # Umrechnung
    value_in_seconds = value * time_units[from_unit]
    result = value_in_seconds / time_units[to_unit]

    if to_unit == "m" and from_unit == "s":  # Spezieller Fall für Sekunden zu Minuten mit Rest
        minutes = value_in_seconds // 60
        seconds = value_in_seconds % 60
        return f"{int(minutes)}m {int(seconds)}s"

    return f"{result:.2f} {to_unit}"

def check_collect_status(username):
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    c.execute("SELECT last_collect_time FROM users WHERE username = ?", (username,))
    user_data = c.fetchone()  # Umbenannt für bessere Lesbarkeit
    conn.close()

    if not user_data:
        return False, None  # Benutzer existiert nicht

    last_collect_time = user_data[0] if user_data and user_data[0] is not None else None # Korrektur: Doppelte Prüfung

    if last_collect_time: # Überprüfen ob last_collect_time nicht None ist.
        try:
            last_collect_time = datetime.strptime(last_collect_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            print(f"Fehler beim Parsen des Datums für Benutzer {username}: Ungültiges Datumsformat in der Datenbank.")
            return False, None #Rückgabe von False und None, da das Format in der Datenbank falsch ist.

    current_time = datetime.now()
    collect_interval = 3600

    if last_collect_time and (current_time - last_collect_time).total_seconds() >= collect_interval:
        return True, None
    elif last_collect_time: # Überprüfen ob last_collect_time nicht None ist, um einen Fehler zu vermeiden.
        remaining_time = int((collect_interval - (current_time - last_collect_time).total_seconds()) // 60)
        return False, remaining_time
    else:
        return False, None # Rückgabe von False und None, wenn last_collect_time None ist.



def calculate_rank_bonus(rank):
    # Bonus abhängig vom Rang (z. B. 10% pro Rang)
    return max(1, rank * 0.1)

def update_rank(username, ctx):
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()
    c.execute("SELECT deidis, rank FROM users WHERE username = ?", (username,))
    user_data = c.fetchone()

    if not user_data:
        conn.close()
        return

    deidis, current_rank = user_data
    new_rank = current_rank

    # Berechnung des neuen Rangs (Beispielwerte)
    thresholds = [100, 300, 600, 1000, 1500, 2100, 3500, 4444, 5050, 5999, 6666, 7500]  # Beispielschwellen
    for i, threshold in enumerate(thresholds):
        if deidis >= threshold:
            new_rank = i + 1

    if new_rank > current_rank:
        c.execute("UPDATE users SET rank = ? WHERE username = ?", (new_rank, username))
        conn.commit()
        next_threshold = thresholds[new_rank] if new_rank < len(thresholds) else "∞"
        ctx.send(f"🎉 @{username} ist jetzt Rang {new_rank}! Nur noch {next_threshold - deidis} Deidis bis zum nächsten Rang!")
    conn.close()



                
async def check_timers(bot):
    while True:
        conn = sqlite3.connect("deidis_v2.db")
        c = conn.cursor()

        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("SELECT id, username, title, channel FROM timer WHERE end_time <= ?", (now,))
            expired_timers = c.fetchall()

            for timer_id, username, title, channel in expired_timers:
                # Benachrichtigung im gespeicherten Kanal senden
                for active_channel in bot.connected_channels:
                    if active_channel.name == channel:
                        await active_channel.send(f"⏰ @{username}, dein Timer ist abgelaufen! {title} ")
                        break

                # Timer aus der Datenbank löschen
                c.execute("DELETE FROM timer WHERE id = ?", (timer_id,))
            
            conn.commit()
        except sqlite3.Error as e:
            print(f"Fehler beim Überprüfen der Timer: {e}")
        finally:
            conn.close()

        await asyncio.sleep(1)  # Überprüfung alle 1 Sekunde





def collect_deidis(username):
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    # Benutzer abrufen oder hinzufügen
    c.execute("SELECT deidis, last_collect_time FROM users WHERE username = ?", (username,))
    user = c.fetchone()

    if not user:
        # Neuen Benutzer hinzufügen
        c.execute("INSERT INTO users (username, deidis, last_collect_time, rank) VALUES (?, 0, NULL, 0)", 
                  (username,))
        conn.commit()
        print(f"👤 Neuer Benutzer '{username}' wurde zur Deidis-Datenbank hinzugefügt.")

    # Deidis-Sammellogik
    current_time = datetime.now()
    c.execute("SELECT deidis, last_collect_time FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    deidis, last_collect_time = user

    collect_interval = 3600  # 1 Stunde Sammelintervall
    if last_collect_time:
        last_collect_time = datetime.strptime(last_collect_time, "%Y-%m-%d %H:%M:%S")
        if (current_time - last_collect_time).total_seconds() < collect_interval:
            remaining_time = collect_interval - (current_time - last_collect_time).total_seconds()
            conn.close()
            return False, int(remaining_time // 60)

    # Berechne Deidis
    new_deidis = random.randint(1, 50)
    c.execute("UPDATE users SET deidis = deidis + ?, last_collect_time = ? WHERE username = ?", 
              (new_deidis, current_time.strftime("%Y-%m-%d %H:%M:%S"), username))
    conn.commit()
    conn.close()
    return True, new_deidis





def bet_deidis(username, amount):
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    # Benutzer-Daten abrufen
    c.execute("SELECT deidis, total_bets, won_bets, lost_bets FROM users WHERE username = ?", (username,))
    user = c.fetchone()

    if not user or user[0] < amount:
        conn.close()
        return False, 0  # Nicht genug Deidis

    # Zufallsentscheidung für Gewinn oder Verlust
    win = random.choice([True, False])
    new_deidis = user[0] + amount if win else user[0] - amount
    won_bets = user[2] + 1 if win else user[2]
    lost_bets = user[3] + 1 if not win else user[3]

    # Daten aktualisieren
    c.execute('''UPDATE users 
                 SET deidis = ?, total_bets = total_bets + 1, won_bets = ?, lost_bets = ? 
                 WHERE username = ?''', 
              (new_deidis, won_bets, lost_bets, username))
    conn.commit()
    conn.close()

    return win, amount if win else -amount


def buy_power_up(username, power_up_name):
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    try:
        power_up_name = power_up_name.strip().lower()

        # Benutzer-Daten abrufen
        c.execute("SELECT deidis FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        if not user:
            return False, "Benutzer nicht gefunden."

        deidis = user[0]

        # Shop-Daten abrufen
        c.execute("SELECT cost, duration_hours FROM shop WHERE LOWER(power_up_name) = ?", (power_up_name,))
        power_up = c.fetchone()
        if not power_up:
            return False, "Power-up nicht gefunden."

        cost, duration_hours = power_up

        if deidis < cost:
            return False, "Nicht genug Deidis."

        # Power-up-Endzeit berechnen
        power_up_end_time = datetime.now() + timedelta(hours=duration_hours)
        power_up_column = f"{power_up_name.replace(' ', '_')}_collect"

        # Überprüfen, ob die Spalte existiert
        c.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in c.fetchall()]
        if power_up_column not in columns:
            return False, "Fehler: Power-up-Spalte existiert nicht."

        # Benutzer aktualisieren
        c.execute(f"UPDATE users SET deidis = deidis - ?, {power_up_column} = 1, power_up_end_time = ? WHERE username = ?",
                  (cost, power_up_end_time.strftime("%Y-%m-%d %H:%M:%S"), username))
        conn.commit()
        return True, f"{power_up_name.title()} erfolgreich gekauft!"

    except sqlite3.Error as e:
        conn.rollback()
        print(f"Fehler beim Power-up-Kauf: {e}")
        return False, "Ein Fehler ist aufgetreten."
    finally:
        conn.close()


def clean_shop_table():
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    # Alle Einträge bereinigen
    c.execute("SELECT id, power_up_name FROM shop")
    rows = c.fetchall()

    for row in rows:
        id, name = row
        clean_name = name.strip().lower()
        c.execute("UPDATE shop SET power_up_name = ? WHERE id = ?", (clean_name, id))

    conn.commit()
    conn.close()
    print("🛒 Shop-Tabelle bereinigt.")



def give_deidis(from_user, to_user, amount):
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    # Überprüfen, ob der Absender genügend Deidis hat
    c.execute("SELECT deidis FROM users WHERE username = ?", (from_user,))
    sender = c.fetchone()
    if not sender or sender[0] < amount:
        conn.close()
        return False

    # Empfänger prüfen oder hinzufügen
    c.execute("SELECT deidis FROM users WHERE username = ?", (to_user,))
    receiver = c.fetchone()
    if not receiver:
        c.execute("INSERT INTO users (username, deidis) VALUES (?, 0)", (to_user,))
        conn.commit()
        print(f"👤 Empfänger '{to_user}' wurde zur Deidis-Datenbank hinzugefügt.")

    # Transaktion durchführen
    c.execute("UPDATE users SET deidis = deidis - ? WHERE username = ?", (amount, from_user))
    c.execute("UPDATE users SET deidis = deidis + ? WHERE username = ?", (amount, to_user))
    conn.commit()
    conn.close()
    return True


def track_bet(username, won, amount):
    """Verfolgt gewonnene und verlorene Deidis durch Wetten."""
    conn = sqlite3.connect("bet_stats.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO bet_stats (username, total_bets, won_deidis, lost_deidis) VALUES (?, 0, 0, 0)", 
              (username,))
    if won:
        c.execute("UPDATE bet_stats SET total_bets = total_bets + 1, won_deidis = won_deidis + ? WHERE username = ?", 
                  (amount, username))
    else:
        c.execute("UPDATE bet_stats SET total_bets = total_bets + 1, lost_deidis = lost_deidis + ? WHERE username = ?", 
                  (amount, username))
    conn.commit()
    conn.close()


def get_leaderboard():
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    c.execute("SELECT username, deidis FROM users ORDER BY deidis DESC LIMIT 10")
    leaderboard = c.fetchall()
    conn.close()

    return leaderboard


def get_user_rank(username):
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    c.execute("SELECT rank FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()

    return result[0] if result else 0

def get_user_deidis(username):
    conn = sqlite3.connect("deidis_v2.db")
    c = conn.cursor()

    c.execute("SELECT deidis FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()

    return result[0] if result else 0



"""
# Kanäle aus der Datenbank laden
def load_channels():
    conn = sqlite3.connect("channels.db")
    c = conn.cursor()
    c.execute("SELECT name FROM channels WHERE is_active = 1")
    channels = [row[0] for row in c.fetchall()]
    conn.close()

    # Falls keine aktiven Kanäle vorhanden sind, füge den Standardkanal hinzu
    if not channels:
        save_channel("#letslisatv")  # Speichere den Standardkanal in der Datenbank
        return ["#letslisatv"]
    
    return channels
"""

def load_channels():
    conn = sqlite3.connect("channels.db")
    c = conn.cursor()
    c.execute("SELECT name FROM channels_v2 WHERE is_active = 1")
    channels = [row[0] for row in c.fetchall()]
    conn.close()
    return channels


def activate_channel(channel_name):
    conn = sqlite3.connect("channels.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO channels_v2 (name, is_active) VALUES (?, 1)", (channel_name,))
    c.execute("UPDATE channels_v2 SET is_active = 1 WHERE name = ?", (channel_name,))
    conn.commit()
    conn.close()


def deactivate_channel(channel_name):
    conn = sqlite3.connect("channels.db")
    c = conn.cursor()
    c.execute("UPDATE channels_v2 SET is_active = 0 WHERE name = ?", (channel_name,))
    conn.commit()
    conn.close()





# Einzelnen Kanal speichern
def save_channel(channel):
    conn = sqlite3.connect("channels.db")
    c = conn.cursor()
    joined_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Aktuelles Datum und Uhrzeit
    c.execute('''
        INSERT OR IGNORE INTO channels_v2 (name, joined_at, is_active) 
        VALUES (?, ?, 1)
    ''', (channel, joined_at))
    c.execute('''
        UPDATE channels
        SET is_active = 1
        WHERE name = ?
    ''', (channel,))
    conn.commit()
    conn.close()

"""
# Kanal deaktivieren
def deactivate_channel(channel):
    conn = sqlite3.connect("channels.db")
    c = conn.cursor()
    c.execute('''
        UPDATE channels
        SET is_active = 0
        WHERE name = ?
    ''', (channel,))
    conn.commit()
    conn.close()
"""

def save_user_sleep(username, sleep_message):
    conn = sqlite3.connect("channels.db")
    c = conn.cursor()
    sleep_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO users (username, sleep_time, sleep_message, sleeping)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(username) DO UPDATE SET
        sleep_time = excluded.sleep_time,
        sleep_message = excluded.sleep_message,
        sleeping = 1
    ''', (username, sleep_time, sleep_message))
    conn.commit()
    conn.close()



def check_and_reset_user(username):
    conn = sqlite3.connect("channels.db")
    c = conn.cursor()

    # Benutzer mit Schlafstatus abrufen
    c.execute("SELECT sleep_time, sleep_message FROM users WHERE username = ? AND sleeping = 1", (username,))
    user = c.fetchone()

    if user:
        # Schlafzeit berechnen und Nachricht vorbereiten
        sleep_time = datetime.strptime(user[0], "%Y-%m-%d %H:%M:%S")
        wake_time = datetime.now()
        duration = wake_time - sleep_time
        sleep_message = user[1]

        # Schlafstatus zurücksetzen
        c.execute("UPDATE users SET sleeping = 0 WHERE username = ?", (username,))
        conn.commit()
        conn.close()

        # Rückgabe der geschlafenen Zeit und der Nachricht
        return duration, sleep_message

    conn.close()
    return None, None

def load_active_channels():
    conn = sqlite3.connect("channels.db")
    c = conn.cursor()
    c.execute("SELECT name FROM channels_v2 WHERE is_active = 1")
    active_channels = [row[0] for row in c.fetchall()]
    conn.close()
    return active_channels




def reset_notification(user):
    """Setzt `is_notified` für einen Benutzer zurück."""
    conn = sqlite3.connect("noti.db")
    c = conn.cursor()
    try:
        c.execute("UPDATE notifications SET is_notified = 0 WHERE username = ?", (user,))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Fehler beim Zurücksetzen von Benachrichtigungen: {e}")
    finally:
        conn.close()


# Datenbankfunktionen für notified.db
def create_notified_table():
    with sqlite3.connect("notified.db") as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    username TEXT PRIMARY KEY,
                    last_collect_time TEXT,
                    should_notify INTEGER DEFAULT 0,
                    is_notified INTEGER DEFAULT 0
                );
            """)
            conn.commit()

        except sqlite3.Error as e:
            print(f"Fehler beim Erstellen der Tabelle 'notifications': {e}")

def update_last_collect_time(username, timestamp):
    with sqlite3.connect("notified.db") as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT OR REPLACE INTO notifications (username, last_collect_time) VALUES (?, ?)", (username, timestamp))
            conn.commit()
        except sqlite3.Error as e:
            print(f"Fehler beim Aktualisieren der letzten Sammelzeit: {e}")

def toggle_should_notify(username):
    with sqlite3.connect("notified.db") as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE notifications SET should_notify = NOT should_notify WHERE username = ?", (username,))
            conn.commit()
        except sqlite3.Error as e:
            print(f"Fehler beim Umschalten von should_notify: {e}")

def set_is_notified(username, value):  # value: 0 oder 1
    with sqlite3.connect("notified.db") as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE notifications SET is_notified = ? WHERE username = ?", (value, username))
            conn.commit()
        except sqlite3.Error as e:
            print(f"Fehler beim Setzen von is_notified: {e}")
def add_user_to_notified(username):
    with sqlite3.connect("notified.db") as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT OR IGNORE INTO notifications (username) VALUES (?)", (username,))
            conn.commit()
        except sqlite3.Error as e:
            print(f"Fehler beim Hinzufügen des Users: {e}")

def check_and_notify(user, channel):
    with sqlite3.connect("notified.db") as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT last_collect_time, should_notify, is_notified FROM notifications WHERE username = ?", (user,))
            result = cursor.fetchone()

            if result:
                last_collect_time_str, should_notify, is_notified = result
                if should_notify == 1 and is_notified == 0:
                    if last_collect_time_str: #Überprüft ob last_collect_time nicht None ist
                        last_collect_time = datetime.fromisoformat(last_collect_time_str)
                        if (datetime.now() - last_collect_time).total_seconds() >= 3600:
                            bot.loop.create_task(channel.send(f" {user}, du kannst wieder Deidis sammeln! Schreibe `&deidis`."))
                            set_is_notified(user, 1) #Benachrichtigungsstatus setzen
        except sqlite3.Error as e:
            print(f"Fehler bei der Benachrichtigungsprüfung für {user}: {e}")



async def check_birthdays(username):
    """
    Checks if a specific user has a birthday today (asynchronously).
    """
    today = date.today()
    conn = None
    try:
        conn = sqlite3.connect("birthdays.db")
        conn.row_factory = sqlite3.Row  # For accessing results by column names
        c = conn.cursor()
        await asyncio.sleep(0)  # Yield control to allow other tasks to run (optional)
        c.execute("SELECT day, month FROM birthdays_new WHERE username = ?", (username,))
        result = c.fetchone()
        if result:
            day_db, month_db = result
            if today.day == day_db and today.month == month_db:
                return True  # Birthday found
        return False  # No birthday found
    except sqlite3.Error as e:
        return False
    finally:
        if conn:
            conn.close()  # Ensure connection is closed

async def automatic_meteor_spawning(bot):
    """Spawnt Meteore basierend auf Kanälen mit Nachrichtenaktivität."""
    global active_channels_with_messages

    while True:
        try:
            # Wartezeit bis zum nächsten Meteor (z. B. 10 bis 30 Minuten für Testzwecke)
            wait_time = random.randint(120, 24400)  # 10 bis 30 Minuten in Sekunden
            await asyncio.sleep(wait_time)

            # Kanäle mit Nachrichten überprüfen
            if not active_channels_with_messages:
                print("❌ Keine aktiven Kanäle mit Nachrichtenaktivität verfügbar.")
                continue

            # Zufälligen Kanal auswählen
            channel_name = random.choice(active_channels_with_messages)
            channel = bot.get_channel(channel_name)

            # Überprüfen, ob der Kanal gültig ist
            if not channel or not hasattr(channel, "send"):
                print(f"❌ Kanal '{channel_name}' konnte nicht gefunden werden oder ist ungültig.")
                active_channels_with_messages.remove(channel_name)  # Ungültigen Kanal entfernen
                continue

            # Seltenheit bestimmen
            rarity = random.choices(
                ["normal", "rare", "epic", "legendary"],
                weights=[60, 25, 10, 5],
                k=1
            )[0]

            # Meteor spawnen
            await spawn_meteor(bot, channel.name, rarity)
        finally:
            print(f"🌠 Meteor gespawnt in Kanal: {channel.name} (Seltenheit: {rarity})")




async def spawn_meteor(bot, channel_name=None, rarity=None):
        """Spawnt einen Meteor in einem zufälligen oder angegebenen Kanal."""
        global current_meteor

        # Kanal auswählen
        active_channels = bot.connected_channels
        if not active_channels:
            print("Keine aktiven Kanäle verfügbar.")
            return

        channel_name = channel_name or random.choice(active_channels)
        channel = bot.get_channel(channel_name)

        # Seltenheit bestimmen
        rarity = rarity or random.choices(
            ["🔵normaler", "🟠seltener", "💎epischer", "🐦‍🔥legendärer"],
            weights=[60, 25, 10, 5],
            k=1
        )[0]

        # Deidis-Werte für die Seltenheit
        deidis_range = {
            "normal": (100, 250),
            "rare": (200, 400),
            "epic": (350, 600),
            "legendary": (600, 1500)
        }
        deidis = random.randint(*deidis_range[rarity])

        # Meteor erstellen
        current_meteor = {
            "channel": channel_name,
            "rarity": rarity,
            "deidis": deidis,
            "expires_at": datetime.now() + timedelta(minutes=15)
        }

        # Nachricht senden
        await channel.send(
            f"🌠 Ein {rarity.capitalize()} Meteor fliegt vorbei! ☄️  "
            f"Baue ihn mit  &mine ab, und bekomme {deidis} Deidis!\n"
        )


        # Nach Ablauf der Zeit Meteor entfernen
        await asyncio.sleep(120)  # 15 Minuten
        if current_meteor and current_meteor["channel"] == channel_name:
            await channel.send("🌌 Der Meteor ist weitergeflogen... ")
            current_meteor = None


current_meteor = None
# Bot-Klasse
class TwitchBot(commands.Bot):

    def __init__(self, db_path="channels.db"):
        init_db()  # Standarddatenbank initialisieren
        init_deidis_db_v2()  # Neue Deidis-Datenbank initialisieren
        init_cooldown_db()
        init_notify_db()
        init_notifications_db() 
        init_noti_db()
        init_birthday_db()
        init_steal_stats_db()
        init_bet_stats_db()
        init_counters_db()
        init_meteor_stats_db()
        self.start_time = datetime.now() 
        
        
        self.active_channels = load_active_channels() 
        self.channels = self.active_channels  #Lokale Liste für aktive Kanäle
        if not self.active_channels:
            print("❌ Keine aktiven Kanäle gefunden. Trete #LetsLisaTV bei.")
            self.active_channels = ["#LetsLisaTV"]
            activate_channel("#LetsLisaTV")

        self.active_duels = {}  # Aktive Herausforderungen speichern
        init_leaderboard_db()  # Tabelle für Ranglisten-Sichtbarkeit erstellen
 
        super().__init__(token="oauth:e0efuthvw3i31w7udvmtgoxrm9rp4p", prefix="&", initial_channels=self.channels)

        self.loop.create_task(self.run_every_second())
        
        





    async def part_channel(self, channel):
            try:
                await self.part_channels([channel])  # Verlasse den Kanal
                print(f"🔴 Bot hat den Kanal verlassen: {channel}")
            except Exception as e:
                print(f"❌ Fehler beim Verlassen des Kanals {channel}: {e}")




    def reset_notification(self,user):
        """Setzt `is_notified` für einen Benutzer zurück."""
        conn = sqlite3.connect("noti.db")
        c = conn.cursor()
        try:
            c.execute("UPDATE notifications SET is_notified = 0 WHERE username = ?", (user,))
            conn.commit()
        except sqlite3.Error as e:
            print(f"Fehler beim Zurücksetzen von Benachrichtigungen: {e}")
        finally:
            conn.close()


    def should_notify(self, user):
        """Prüft, ob der Benutzer eine Benachrichtigung erhalten soll."""
        conn_noti = sqlite3.connect("noti.db")
        conn_deidis = sqlite3.connect("deidis_v2.db")
        c_noti = conn_noti.cursor()
        c_deidis = conn_deidis.cursor()

        try:
            # Benutzer aus der noti.db abrufen
            c_noti.execute("SELECT should_notify, is_notified FROM notifications WHERE username = ?", (user,))
            noti_result = c_noti.fetchone()

            if not noti_result or not noti_result[0]:  # should_notify = 0 oder kein Eintrag
                return False

            should_notify, is_notified = noti_result
            if is_notified == 1:
                return False  # Benutzer wurde bereits benachrichtigt

            # Letzte Sammlung aus deidis_v2 abrufen
            c_deidis.execute("SELECT last_collect_time FROM users WHERE username = ?", (user,))
            collect_result = c_deidis.fetchone()

            if not collect_result or not collect_result[0]:
                reset_notification(user)
                return True  # Keine Sammlung bisher, daher benachrichtigen
                

            # Prüfen, ob mehr als eine Stunde seit der letzten Sammlung vergangen ist
            last_collect_time = datetime.fromisoformat(collect_result[0])
            if (datetime.now() - last_collect_time).total_seconds() >= 3600:
                return True

            return False
        except sqlite3.Error as e:
            print(f"Fehler bei der Benachrichtigungsprüfung für {user}: {e}")
            return False
        finally:
            conn_noti.close()
            conn_deidis.close()


    async def run_every_second(self):

        while True:
            
            await asyncio.sleep(1)  # Warten für eine Sekunde

    async def event_ready(self):
        print(f"✅ Bot ist eingeloggt als | {self.nick}")
        print(f"🤖 Aktive Kanäle: {', '.join(self.active_channels)}")
        create_notified_table()
        self.loop.create_task(check_timers(self))
        self.loop.create_task(check_birthdays(self))
        bot.loop.create_task(automatic_meteor_spawning(bot))

        
    async def on_ready(self):
        self.start_time = datetime.now()
        print(f"Bot ist bereit und überwacht Timer.")

    
    

    async def event_message(self, message):

        if message.echo:
            return  # Ignoriere eigene Nachrichten
        self.active_channels = load_active_channels()
        self.channels = self.active_channels

        global active_channels_with_messages

        # Kanalname speichern, wenn noch nicht in der Liste
        channel_name = message.channel.name
        if channel_name not in active_channels_with_messages:
            active_channels_with_messages.append(channel_name)

        # Überprüfen, ob der Benutzer schläft
        user = message.author.name
        duration, sleep_message = check_and_reset_user(user)

        today = date.today()
        user_key = (message.author.name.lower(), today) #Key bestehend aus Username und Datum

        if user_key not in congratulated_users: # Überprüfen ob dem Nutzer heute schon gratuliert wurde
            has_birthday = await check_birthdays(message.author.name.lower())
            if has_birthday:
                await message.channel.send(f"Herzlichen Glückwunsch zum Geburtstag, @{message.author.name}!")
                congratulated_users.add(user_key) #Nutzer zum Set hinzufügen
                #Optional: Set nach 24 Stunden leeren
                await asyncio.sleep(86400) # 24 Stunden = 86400 Sekunden
                congratulated_users.remove(user_key)
                print(f"User {message.author.name} from congratulation list removed")


        if duration:
            # Guten Morgen Nachricht mit geschlafener Zeit senden
            hours, remainder = divmod(duration.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            await message.channel.send(
                f"🌞 Guten Morgen, @{user}! Du hast {int(hours)} Stunden und {int(minutes)} Minuten geschlafen. "
                f"{sleep_message}"
            )

        user = message.author.name
        command_name = "deidisbenachrichtigung"
        cooldown_time = 600  

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            await self.handle_commands(message)
            return
        else:
            # Überprüfen, ob der Benutzer Benachrichtigungen aktiviert hat
            conn = sqlite3.connect("notifications.db")
            c = conn.cursor()
            c.execute("SELECT notifications_enabled FROM users WHERE username = ?", (user,))
            result = c.fetchone()
            notifications_enabled = result[0] if result else 0  # Standardmäßig deaktiviert
            # Benachrichtigung nur, wenn aktiviert
            if notifications_enabled:
            
                can_collect, _ = check_collect_status(user)
                if can_collect:
                    await message.channel.send(f"🔔 @{user}, du kannst jetzt wieder Deidis sammeln! Schreibe `&deidis`.")
            

        await self.handle_commands(message)

    

    

    @commands.command(name="mine")
    async def collect(self, ctx):
        """Erlaubt es einem Benutzer, einen Meteor zu sammeln."""
        global current_meteor
        user = ctx.author.name.lower()
        channel_name = ctx.channel.name

        if not current_meteor or current_meteor["channel"] != channel_name:
            await ctx.send("❌ Es gibt keinen Meteor, den du einsammeln kannst.")
            return

        if datetime.now() > current_meteor["expires_at"]:
            await ctx.send("❌ Der Meteor ist bereits verschwunden.")
            current_meteor = None
            return

        # Deidis und Statistiken aktualisieren
        deidis = current_meteor["deidis"]
        conn = sqlite3.connect("deidis_v2.db")
        c = conn.cursor()
        c.execute("UPDATE users SET deidis = deidis + ? WHERE username = ?", (deidis, user))
        conn.commit()
        conn.close()

        # Meteor-Statistiken aktualisieren
        conn_meteor = sqlite3.connect("meteor_stats.db")
        c_meteor = conn_meteor.cursor()
        c_meteor.execute("INSERT OR IGNORE INTO meteor_stats (username) VALUES (?)", (user,))
        c_meteor.execute("UPDATE meteor_stats SET meteors_collected = meteors_collected + 1, deidis_won = deidis_won + ? WHERE username = ?", (deidis, user))
        conn_meteor.commit()
        conn_meteor.close()

        await ctx.send(f"🎉 @{user} hat den Meteor eingesammelt und {deidis} Deidis erhalten!")
        current_meteor = None

    



    # Befehl: Bot zu einem Kanal hinzufügen
    @commands.command(name="join", aliases=["Join", "joinchannel", "Joinchannel", "joinme", "Joinme"])
    async def join_channel(self, ctx):
        user = ctx.author.name
        command_name = "join"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        user_channel = f"#{ctx.author.name}"

        # Prüfen, ob der Kanal bereits aktiv ist
        if user_channel in self.active_channels:
            await ctx.send(f"❌ Ich bin bereits in deinem Kanal aktiv.")
            return

        try:
            # Kanal aktivieren und Liste synchronisieren
            activate_channel(user_channel)
            self.active_channels = load_active_channels()

            # Kanal beitreten und Begrüßungsnachricht senden
            await self.join_channels([user_channel])
            await send_join_message(ctx.author.name, bot, ctx)
        except Exception as e:
            await ctx.send(f"❌ Fehler beim Beitreten deines Kanals: {e}")




    # Befehl: Bot aus einem Kanal entfernen
    @commands.command(name="leave", aliases=["Leave", "leavechannel", "Leavechannel", "leaveme", "Leaveme"])
    async def leave_channel(self, ctx):
        user = ctx.author.name
        command_name = "leave"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        user_channel = f"#{ctx.author.name}"

        # Prüfen, ob der Kanal aktiv ist
        if user_channel not in self.active_channels:
            await ctx.send(f"❌ Ich bin nicht in deinem Kanal aktiv.")
            return

        try:
            # Kanal deaktivieren und Liste synchronisieren
            deactivate_channel(user_channel)
            self.active_channels = load_active_channels()

            # Kanal verlassen
            await ctx.send(f"🚪 Tschüss! Ich verlasse deinen Kanal.")
            await self.part_channels([user_channel])  # Kanal verlassen

        except Exception as e:
            print(f"Fehler beim Verlassen des Kanals: {e}")
            await ctx.send(f"❌ Es gab einen Fehler beim Verlassen deines Kanals: {e}")




    @commands.command(name="gn", aliases=["Gn","GN","gN","goodnight"])
    async def gn(self, ctx, *, message=""):
        user = ctx.author.name
        command_name = "gn"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        user = ctx.author.name

        # Speichere den Schlafstatus und die Nachricht in der Datenbank
        save_user_sleep(user, message)

        # Antwort im Chat
        await ctx.send(f"🌙 Gute Nacht, @{user}! {message}")
        print(f"💤 Benutzer {user} ist schlafen gegangen mit Nachricht: {message}")


    @commands.command(name="deidis", aliases=["d", "Deidis", "DEIDIS"])
    async def deidis(self, ctx):
        user = ctx.author.name
        command_name = "deidis"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        user = ctx.author.name.lower()
        conn = sqlite3.connect("deidis_v2.db")
        c = conn.cursor()

        # Prüfen, ob der Benutzer in der Datenbank existiert
        c.execute("SELECT deidis, rank, double_collect, fast_collect, power_up_end_time, last_collect_time FROM users WHERE username = ?", (user,))
        user_data = c.fetchone()

        if not user_data:
            # Neuer Benutzer wird hinzugefügt
            welcome_bonus = 15
            c.execute("INSERT INTO users (username, deidis, rank, double_collect, fast_collect, power_up_end_time, last_collect_time) VALUES (?, ?, ?, 0, 0, NULL, NULL)", 
                    (user, welcome_bonus, 1))
            conn.commit()
            conn.close()
            await ctx.send(f"🎉 Willkommen @{user}! Als Willkommensbonus erhältst du {welcome_bonus} Deidis 🪙. Sammle regelmäßig mit `&deidis`!")
            return

        # Wenn der Benutzer existiert, wird der normale Ablauf durchgeführt
        deidis, rank, double_collect, fast_collect, power_up_end_time, last_collect_time = user_data
        now = datetime.now()

        # Sammelintervall (Standard: 1 Stunde)
        collect_interval = 3600  # in Sekunden
        if fast_collect:
            collect_interval //= 2  # Sammelzeit halbieren

        # Überprüfen, ob die Sammelzeit abgelaufen ist
        if last_collect_time:
            last_collect_time = datetime.strptime(last_collect_time, "%Y-%m-%d %H:%M:%S")
            elapsed_time = (now - last_collect_time).total_seconds()
            if elapsed_time < collect_interval:
                remaining_time = int((collect_interval - elapsed_time) // 60)
                await ctx.send(f"⏳ @{user}, du kannst erst in {remaining_time} Minuten wieder sammeln. Du hast {deidis} Deidis 🪙 (TIER {rank}⭐).")
                conn.close()
                return

        # Power-up-Endzeit überprüfen
        active_power_ups = []
        if power_up_end_time:
            power_up_end_time = datetime.strptime(power_up_end_time, "%Y-%m-%d %H:%M:%S")
            if now > power_up_end_time:
                # Power-ups abgelaufen
                c.execute("UPDATE users SET double_collect = 0, fast_collect = 0, power_up_end_time = NULL WHERE username = ?", (user,))
                conn.commit()
            else:
                if double_collect:
                    active_power_ups.append("Doppelte Deidis")
                if fast_collect:
                    active_power_ups.append("Schnelles Sammeln")

        # Deidis berechnen
        collected_deidis = round(random.randint(1, 50) * (rank / 10 + 1))
        if double_collect:
            collected_deidis *= 2  # Verdoppelte Deidis

        # Aktualisiere Datenbank
        c.execute("UPDATE users SET deidis = deidis + ?, last_collect_time = ? WHERE username = ?", 
                (collected_deidis, now.strftime("%Y-%m-%d %H:%M:%S"), user))
        conn.commit()
        conn.close()

        # Power-ups in Nachricht anzeigen
        power_ups_msg = f" AKTIVE POWER-UPS: {', '.join(active_power_ups)}" if active_power_ups else ""

        await ctx.send(f"🎉 @{user}, du hast {collected_deidis} Deidis gesammelt! Du hast jetzt {deidis + collected_deidis} Deidis 🪙 (TIER {rank}⭐). {power_ups_msg}")

        self.reset_notification(user)
        now = datetime.now().isoformat()
        update_last_collect_time(user, now)
        add_user_to_notified(user) 



    @commands.command(name="shop", aliases=["Shop", "Powerup", "powerup","Powerups","powerups","powerUps","PowerUps","buy","Buy"])
    async def shop(self, ctx, power_up_name: str = None):
        user = ctx.author.name
        command_name = "shop"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        if not power_up_name:
            # Liste der verfügbaren Power-ups anzeigen
            conn = sqlite3.connect("deidis_v2.db")
            c = conn.cursor()
            c.execute("SELECT power_up_name, cost, duration_hours FROM shop")
            power_ups = c.fetchall()
            conn.close()

            if power_ups:
                message = "🏪Shop Übersicht: \n"
                for power_up in power_ups:
                    name, cost, duration = power_up
                    message += f"- **{name}**: {cost} Deidis für {duration} Stunden\n"
                await ctx.send(" SHOP ITEMS: 'fast'(200) => Verkürzt die Zeit zum deidis einsammeln um die Hälfte für 2h |  'double'(200) verdoppelt die deidis Pro einsammeln für 2h")
            else:
                await ctx.send("🏪 Der Shop ist leer.")
            return

        # Power-up kaufen
        user = ctx.author.name
        success, message = buy_power_up(user, power_up_name)
        await ctx.send(message)


    @commands.command(name="bet", aliases=["Bet","gamba","Gamba","gamble","Gamble","GAMBA","casino","Casino"])
    async def bet(self, ctx, amount: str):
        user = ctx.author.name
        command_name = "bet"
        cooldown_time = 3  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        """Ermöglicht es einem Benutzer, Deidis zu setzen."""
        user = ctx.author.name.lower()

        conn = sqlite3.connect("deidis_v2.db")
        c = conn.cursor()

        # Überprüfen, ob der Benutzer existiert
        c.execute("SELECT deidis FROM users WHERE username = ?", (user,))
        user_data = c.fetchone()

        if not user_data:
            await ctx.send(f"❌ @{user}, du bist nicht in der Datenbank! Sammle zuerst Deidis mit `&deidis`.")
            conn.close()
            return

        current_deidis = user_data[0]

        # Betrag verarbeiten
        if amount.lower() == "all":
            bet_amount = current_deidis
        elif amount.lower() == "half":
            bet_amount = current_deidis // 2
        elif "%" in amount:
            try:
                percentage = int(amount.strip('%'))
                bet_amount = current_deidis * percentage // 100
            except ValueError:
                await ctx.send(f"❌ Ungültiger Betrag: {amount}.")
                return
        else:
            try:
                bet_amount = int(amount)
            except ValueError:
                await ctx.send(f"❌ Ungültiger Betrag: {amount}.")
                return

        # Betrag validieren
        if bet_amount <= 0 or bet_amount > current_deidis:
            await ctx.send(f"❌ Ungültiger Betrag. Du kannst maximal {current_deidis} Deidis setzen.")
            return

        # Zufällige Entscheidung
        won = random.choice([True, False])
        if won:
            winnings = bet_amount 
            c.execute("UPDATE users SET deidis = deidis + ? WHERE username = ?", (bet_amount, user))
            conn.commit()
            await ctx.send(f"🎉 @{user} hat gewonnen! Du hast jetzt {current_deidis + winnings} Deidis!")
            track_bet(user, True, bet_amount)
        else:
            c.execute("UPDATE users SET deidis = deidis - ? WHERE username = ?", (bet_amount, user))
            conn.commit()
            await ctx.send(f"😞 @{user} hat verloren. Du hast jetzt {current_deidis - bet_amount} Deidis.")
            track_bet(user, False, bet_amount)

        # Rang prüfen und Nachricht senden, falls ein Aufstieg erfolgt
        update_rank(user, ctx)

        conn.close()




    @commands.command(name="toggleping", aliases=["toggle","deidisping","pingdeidis","notifications","Notify","Toggleping","TogglePing","Toggle"])
    async def deidisping(self, ctx):
        user = ctx.author.name
        command_name = "toggle"
        cooldown_time = 3  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        user = ctx.author.name
        new_status = toggle_notifications(user)

        if new_status == 1:
            await ctx.send(f"🔔 @{user}, Benachrichtigungen sind jetzt aktiviert!")
        else:
            await ctx.send(f"🔕 @{user}, Benachrichtigungen sind jetzt deaktiviert!")




    @commands.command(name="stats", aliases=["statistics", "Stats", "STATS", "st"])
    async def stats(self, ctx, target_user: str = None):
        user = ctx.author.name
        command_name = "stats"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        """Zeigt Statistiken zu einem Benutzer an."""
        user = target_user.lstrip("@").lower() if target_user else ctx.author.name.lower()

        conn_deidis = sqlite3.connect("deidis_v2.db")
        conn_bet = sqlite3.connect("bet_stats.db")
        conn_steal = sqlite3.connect("steal_stats.db")
        c_deidis = conn_deidis.cursor()
        c_bet = conn_bet.cursor()
        c_steal = conn_steal.cursor()

        try:
            # Deidis-Daten abrufen
            c_deidis.execute("SELECT deidis, rank FROM users WHERE username = ?", (user,))
            user_data = c_deidis.fetchone()

            if not user_data:
                await ctx.send(f"❌ Keine Statistiken für @{user} verfügbar.")
                return

            deidis, rank = user_data

            # Platzierung berechnen
            c_deidis.execute("SELECT username FROM users ORDER BY deidis DESC")
            all_users = [row[0] for row in c_deidis.fetchall()]
            placement = all_users.index(user) + 1

            # Bet-Statistiken abrufen
            c_bet.execute("SELECT total_bets, won_deidis, lost_deidis FROM bet_stats WHERE username = ?", (user,))
            bet_data = c_bet.fetchone()

            total_bets = bet_data[0] if bet_data else 0
            won_deidis = bet_data[1] if bet_data else 0
            lost_deidis = bet_data[2] if bet_data else 0

            # Steal-Statistiken abrufen
            c_steal.execute("SELECT stolen_from_others, stolen_by_others FROM steal_stats WHERE username = ?", (user,))
            steal_data = c_steal.fetchone()

            stolen_from_others = steal_data[0] if steal_data else 0
            stolen_by_others = steal_data[1] if steal_data else 0
            conn_meteor = sqlite3.connect("meteor_stats.db")
            c_meteor = conn_meteor.cursor()
            c_meteor.execute("SELECT meteors_collected, deidis_won FROM meteor_stats WHERE username = ?", (user,))
            meteor_data = c_meteor.fetchone()

            meteors_collected = meteor_data[0] if meteor_data else 0
            deidis_won_from_meteors = meteor_data[1] if meteor_data else 0

            # Nachricht zusammenstellen
            stats_message = (
                f"📊 Statsfür @{user}:\n"
                f"🪙 Deidis: {deidis}\n"
                f"🏆 Platz: {placement}/{len(all_users)}\n"
                f"⭐ Tier: {rank}\n"
                f"🎲 Wetten gemacht: {total_bets}\n"
                f"🤑 Dadurch Gewonnen: {won_deidis}\n"
                f"😞 Dadurch Verloren: {lost_deidis}\n"
                f"🦹‍♂️ Gestohlen: {stolen_from_others}\n"
                f"🛡️ Wurden: {stolen_by_others} gestohlen\n"
                f"💫 Meteoriten gefunden: {meteors_collected} ({deidis_won_from_meteors})"
            )

            await ctx.send(stats_message)
        except Exception as e:
            print(f"Fehler beim Abrufen der Statistiken: {e}")
            await ctx.send("❌ Ein Fehler ist aufgetreten. Bitte versuche es später erneut.")
        finally:
            conn_deidis.close()
            conn_bet.close()
            conn_steal.close()





    @commands.command(name="give", aliases=["Give","pay","Pay","gift","Gift"])
    async def give(self, ctx, to_user: str, amount: int):
        user = ctx.author.name
        command_name = "give"
        cooldown_time = 4  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        from_user = ctx.author.name
        to_user = to_user.lstrip("@")  # Entferne '@', falls vorhanden

        if amount <= 0:
            await ctx.send(f"❌ @{from_user}, bitte gib einen gültigen Betrag ein.")
            return


        success = give_deidis(from_user, to_user, amount)
        if success:
            await ctx.send(f"✅ @{from_user} hat {amount} Deidis an @{to_user} gesendet!")
            update_rank(to_user, ctx)
        else:
            await ctx.send(f"❌ @{from_user}, die Transaktion ist fehlgeschlagen. Überprüfe deinen Kontostand oder den Empfänger.")


    @commands.command(name="rangliste", aliases=["Rangliste","leaderboard","Leaderboard","list","List","top","Top"])
    async def rangliste(self, ctx):
        user = ctx.author.name
        command_name = "rangliste"
        cooldown_time = 10  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        conn = sqlite3.connect("deidis_v2.db")
        c = conn.cursor()

        try:
            # Rangliste abrufen, nur sichtbare Benutzer anzeigen
            c.execute('''SELECT u.username, u.deidis 
                        FROM users u
                        LEFT JOIN leaderboard_visibility lv 
                        ON u.username = lv.username
                        WHERE COALESCE(lv.visible_in_leaderboard, 1) = 1
                        ORDER BY u.deidis DESC
                        LIMIT 10''')
            leaderboard = c.fetchall()

            if leaderboard:
                leaderboard_message = "🏆 **Rangliste der Top-Spieler:**\n"
                for rank, (username, deidis) in enumerate(leaderboard, start=1):
                    leaderboard_message += f" [{rank}.] {username} - {deidis} Deidis  |\n"
                await ctx.send(leaderboard_message)
                await ctx.send("/me Schreibe &leaderboardtoggle wenn du keine pings beim leaderboard bekommen willst")
            else:
                await ctx.send("❌ Es gibt derzeit keine sichtbaren Spieler in der Rangliste.")
        except sqlite3.Error as e:
            print(f"Fehler beim Abrufen der Rangliste: {e}")
            await ctx.send("Es gab einen Fehler beim Abrufen der Rangliste.")
        finally:
            conn.close()

    @commands.command(name="leaderboardtoggle")
    async def leaderboardtoggle(self, ctx):
        user = ctx.author.name
        command_name = "leaderboardtoggle"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        user = ctx.author.name.lower()

        conn = sqlite3.connect("deidis_v2.db")
        c = conn.cursor()

        # Status prüfen oder neuen Benutzer hinzufügen
        c.execute("SELECT visible_in_leaderboard FROM leaderboard_visibility WHERE username = ?", (user,))
        result = c.fetchone()

        if result:
            # Status umschalten
            new_status = 0 if result[0] == 1 else 1
            c.execute("UPDATE leaderboard_visibility SET visible_in_leaderboard = ? WHERE username = ?", (new_status, user))
        else:
            # Standardmäßig hinzufügen und umschalten
            new_status = 0
            c.execute("INSERT INTO leaderboard_visibility (username, visible_in_leaderboard) VALUES (?, ?)", (user, new_status))

        conn.commit()
        conn.close()

        if new_status == 1:
            await ctx.send(f"✅ @{user}, dein Name wird jetzt in der Rangliste angezeigt.")
        else:
            await ctx.send(f"❌ @{user}, dein Name wird jetzt aus der Rangliste ausgeblendet.")


    @commands.command(name='ping', aliases=[])
    async def ping(self, ctx):
        user = ctx.author.name
        command_name = "ping"
        cooldown_time = 3  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        try:
            start = time.perf_counter()
            async with aiohttp.ClientSession() as session:
                async with session.get("https://twitch.tv") as resp:
                    if resp.status == 200:
                        end = time.perf_counter()
                        latency = round((end - start) * 1000)
            current_time = datetime.now()
            uptime = current_time - self.start_time
            uptime_str = str(uptime).split('.')[0]

            process = psutil.Process(os.getpid())
            memory_usage = process.memory_info().rss / (1024 * 1024)

            channel_count = len(self.connected_channels)

            message = f"🎉 Uptime: {uptime_str} ⚡ Latenz: {latency}ms 🖥️ RAM-Nutzung: {memory_usage:.2f} MB 📺 Kanäle: {channel_count}"
            await ctx.send(message)
        except Exception as error:
            print(f"Fehler im !ping-Command: {error}")
            await ctx.send("😢 Ein Fehler ist aufgetreten")

    @commands.command(name="gpt")
    async def gpt_command(self, ctx, *args):
        if not args:
            await ctx.send("Bitte gib eine Frage oder einen Text für GPT an. z.B. *gpt Was ist der Sinn des Lebens?")
            return

        prompt = " ".join(args)
        try:
            # Ausführen von gpt.py als Unterprozess
            process = subprocess.run(["python", "gpt.py", prompt], capture_output=True, text=True, check=True)
            gpt_response = process.stdout.strip()

            # Antwort im Twitch-Chat senden
            await ctx.reply(gpt_response)

        except subprocess.CalledProcessError as e:
            print(f"Fehler beim Ausführen von gpt.py: {e}")
            await ctx.reply(f"Es gab einen Fehler bei der GPT-Anfrage. Fehlercode: {e.returncode}")
            if e.stderr:
                print(f"stderr: {e.stderr}")
        except Exception as e:
            print(f"Unerwarteter Fehler im gpt-Befehl: {e}")
            await ctx.reply("Es gab einen unerwarteten Fehler.")

    # Weitere Befehle wie `stop`, `restart`, `titel`, `witz` bleiben unverändert

    # Befehl: Stoppt den Bot (nur von `deidaraxx`)
    @commands.command(name="stop")
    async def stop_bot(self, ctx):
        if ctx.author.name.lower() != "deidaraxx":
            await ctx.send("Nur der Besitzer darf diesen Befehl verwenden! deidar16Grrrrr")
            return
        await ctx.send("🛑 Der Bot wird gestoppt.")
        print("🛑 Der Bot wurde gestoppt.")
        await self.close()


    # Befehl: Titel ändern
    @commands.command(name="titel")
    async def change_title(self, ctx, *args):
        if not args:
            await ctx.send("❌Befehl kommt noch...")# eigentlich:❌ Bitte gib einen neuen Titel an. Beispiel: *titel Mein neuer Titel
            return

        new_title = " ".join(args)
        success = self.update_stream_title(new_title)
        if success:
            await ctx.send(f"✅ Titel wurde zu '{new_title}' geändert!")
        else:
            await ctx.send("❌Befehl kommt noch...")#egientlich:❌ Fehler beim Ändern des Titels.

    def update_stream_title(self, new_title):
        url = "https://api.twitch.tv/helix/channels"
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Client-Id": CLIENT_ID}
        data = {"broadcaster_id": self.get_broadcaster_id(CHANNELS_FILE), "title": new_title}
        response = requests.patch(url, headers=headers, json=data)
        return response.status_code == 204

    def get_broadcaster_id(self, channel_name):
        url = f"https://api.twitch.tv/helix/users?login={channel_name}"
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Client-Id": CLIENT_ID}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()["data"][0]["id"]
        return None

    # Befehl: Witz ausgeben
    @commands.command(name="witz", aliases=["Witz","joke","Joke","witze","Witze",])
    async def witz(self, ctx):
        user = ctx.author.name
        command_name = "witz"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        await ctx.reply(random.choice(witze.witze)) # Greift auf die Liste witze in witze.py zu


    # Befehl: Uhrzeit anzeigen
    @commands.command(name="zeit", aliases=["time","Zeit","Time","t"])
    async def zeit(self, ctx):
        user = ctx.author.name
        command_name = "zeit"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        current_time = datetime.now().strftime("%H:%M:%S")
        await ctx.send(f"Es ist gerade: {current_time}🕒")



    @commands.command(name="fakt", aliases=["Fakt","fact","Fact","Facts","facts","Fakten","fakten"])
    async def fakt(self, ctx):
        user = ctx.author.name
        command_name = "fakt"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        await ctx.reply(random.choice(fakten.fakten)) # Greift auf die Liste fakten in fakten.py zu



    @commands.command(name="coinflip", aliases=["cf","coin","flip","Coinflip","münze","Münze","entscheiden"])
    async def coinflip(self, ctx):
        user = ctx.author.name
        command_name = "coinflip"
        cooldown_time = 10  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        coin = [
            "Kopf🪙",
            "Zahl🪙",
        ]
        await ctx.reply(random.choice(coin))


    # Befehl: Zufällige Zahl generieren
    @commands.command(name="zufall", aliases=["random","zufallszahl","randomnumber","rnd"])
    async def zufall(self, ctx, min_val: int, max_val: int):
        user = ctx.author.name
        command_name = "zufall"
        cooldown_time = 3  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        if min_val > max_val:
            await ctx.send("❌ Die erste Zahl muss kleiner als die zweite Zahl sein!")
        else:
            random_number = random.randint(min_val, max_val)
            await ctx.reply(f"Zufallszahl zwischen {min_val} und {max_val} ist: {random_number}🎲")

    # Befehl: Countdown starten
    @commands.command(name="countdown")
    async def countdown(self, ctx, seconds: int):
        user = ctx.author.name
        command_name = "countdown"
        cooldown_time = 15

        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return

        if seconds > 0:
            countdown_message = await ctx.send(f"⏳ Countdown gestartet: {seconds} Sekunden!")
            countdown_task = asyncio.create_task(self.run_countdown(ctx, seconds, countdown_message))

            def check_for_abort(message):
                if message.content.lower() == "&abbruch" and message.author == ctx.author:
                    return True
                return False

            @self.event("message")
            async def message_event(message):
                if check_for_abort(message):
                    countdown_task.cancel()
                    await ctx.send(" Countdown abgebrochen!")
                    self.event("message", None) # Eventlistener entfernen
                    return
                await self.handle_commands(message) #Wichtig! Sonst funktionieren keine anderen Commands mehr!

        else:
            await ctx.send("❌ Bitte gib eine Zahl größer als 0 an.")

    async def run_countdown(self, ctx, seconds, countdown_message):
        try:
            while seconds > 0:
                await asyncio.sleep(1)
                seconds -= 1
                await ctx.send(f"⏳ {seconds}...")
            await ctx.send("🔚")
            await countdown_message.delete() #Startnachricht löschen
        except asyncio.CancelledError:
            await countdown_message.delete() #Startnachricht löschen
            return #Countdown wurde abgebrochen

    # Befehl: Benutzer loben
    @commands.command(name="lob", aliases=["cool","Lob","praise",""])
    async def lob(self, ctx, target_user: str):
        user = ctx.author.name
        command_name = "lob"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        await ctx.send(f"👏 {target_user} ist echt cool 😎💪💯")


    @commands.command(name="stop")
    async def stop_bot(self, ctx):
        # Überprüfe, ob der Befehl von 'deidaraxx' kommt
        if ctx.author.name.lower() != "deidaraxx":
            await ctx.send("⚠️ Nur der Besitzer darf diesen Befehl verwenden!")
            return
    
        await ctx.send("🛑 Der Bot wird gestoppt.")
        print("🛑 Der Bot wurde gestoppt.")
        await self.close()  # Beendet den Bot sicher
    import sys  # Fügt die Möglichkeit hinzu, das Skript neu zu starten
    import subprocess  # Zum Neustarten des Skripts

    @commands.command(name="restart", aliases=["r","reload","Restart","Reload","R"])
    async def restart_bot(self, ctx):
        # Überprüfe, ob der Befehl von 'deidaraxx' kommt
        if ctx.author.name.lower() != "deidaraxx":
            await ctx.send("⚠️ Nur der Besitzer darf diesen Befehl verwenden!")
            return
    
        await ctx.reply("🔄...")
        print("🔄 Der Bot wird neu gestartet...")
        await self.close()  # Beendet den aktuellen Bot

        # Neustart des Programms
        subprocess.Popen([sys.executable, sys.argv[0]])  # Startet das aktuelle Skript neu
        #sys.exit()  # Beendet das aktuelle Skript

    @commands.command(name="spam", aliases=["spamm","Spam","Spamm","sp"])
    async def spam(self, ctx, anzahl: int, *, nachricht: str):
        user = ctx.author.name
        command_name = "spamm"
        cooldown_time = 10  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        if anzahl <= 0:
            await ctx.send("❌ Die Anzahl muss größer als 0 sein.")
            return

        if anzahl > 100:
            await ctx.send("❌ Du kannst maximal 100 Nachrichten gleichzeitig spammen.")
            return

        max_nachrichten = 20
        intervall_sekunden = 30
        nachrichten_zeiten = []

        for _ in range(anzahl):
            aktuelle_zeit = time.monotonic()

            nachrichten_zeiten = [
                zeit for zeit in nachrichten_zeiten
                if aktuelle_zeit - zeit < intervall_sekunden
            ]

            anzahl_aktuelle_nachrichten = len(nachrichten_zeiten)

            if anzahl_aktuelle_nachrichten >= max_nachrichten:
                ueberschreitung = anzahl_aktuelle_nachrichten - max_nachrichten + 1
                wartezeit = (intervall_sekunden / max_nachrichten) * ueberschreitung
                wartezeit = max(0, wartezeit)
                print(f"Ratenbegrenzung erreicht in Kanal {ctx.channel.name}. Warte {wartezeit:.2f} Sekunden.")
                await asyncio.sleep(wartezeit)
                aktuelle_zeit = time.monotonic()
                nachrichten_zeiten = [
                    zeit for zeit in nachrichten_zeiten
                    if aktuelle_zeit - zeit < intervall_sekunden
                ]

            nachrichten_zeiten.append(aktuelle_zeit)
            await ctx.send(nachricht)

    @commands.command(name="pyramide", aliases=["pyramid","Pyramid","Pyramide","pyr"])
    async def pyramide(self, ctx, groesse: int, *, nachricht: str):
        user = ctx.author.name
        command_name = "pyramide"
        cooldown_time = 10  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        if groesse <= 0:
            groesse = 5
            

        if groesse > 25:
            groesse = 25

        if not nachricht:
            await ctx.send("Richtige benutzung -> &pyramid <anzahl> <text>")
            return
            
        nachricht = nachricht.strip()

        max_nachrichten = 20
        intervall_sekunden = 30
        nachrichten_zeiten = []

        for i in range(1, groesse + 1):  # Obere Hälfte der Pyramide
            zeile = " ".join([nachricht] * i) # Leerzeichen zwischen den Wörtern
            await self.sende_mit_ratenbegrenzung(ctx, zeile, max_nachrichten, intervall_sekunden, nachrichten_zeiten)


        for i in range(groesse - 1, 0, -1):  # Untere Hälfte der Pyramide (ohne die Spitze doppelt)
            zeile = " ".join([nachricht] * i) # Leerzeichen zwischen den Wörtern
            await self.sende_mit_ratenbegrenzung(ctx, zeile, max_nachrichten, intervall_sekunden, nachrichten_zeiten)

    async def sende_mit_ratenbegrenzung(self, ctx, nachricht, max_nachrichten, intervall_sekunden, nachrichten_zeiten):
        aktuelle_zeit = time.monotonic()
        nachrichten_zeiten = [
            zeit for zeit in nachrichten_zeiten
            if aktuelle_zeit - zeit < intervall_sekunden
        ]
        anzahl_aktuelle_nachrichten = len(nachrichten_zeiten)

        if anzahl_aktuelle_nachrichten >= max_nachrichten:
            ueberschreitung = anzahl_aktuelle_nachrichten - max_nachrichten + 1
            wartezeit = (intervall_sekunden / max_nachrichten) * ueberschreitung
            wartezeit = max(0, wartezeit)
            print(f"Ratenbegrenzung erreicht in Kanal {ctx.channel.name}. Warte {wartezeit:.2f} Sekunden.")
            await asyncio.sleep(wartezeit)
            aktuelle_zeit = time.monotonic()
            nachrichten_zeiten = [
                zeit for zeit in nachrichten_zeiten
                if aktuelle_zeit - zeit < intervall_sekunden
            ]
        nachrichten_zeiten.append(aktuelle_zeit)
        await ctx.send(nachricht)


    @commands.command(name="tier", aliases=["rank"])
    async def rank(self, ctx):
        user = ctx.author.name
        command_name = "tier"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        username = ctx.author.name
        conn = sqlite3.connect("deidis_v2.db")
        c = conn.cursor()
        update_rank(username, ctx)
        c.execute("SELECT deidis, rank FROM users WHERE username = ?", (username,))
        user_data = c.fetchone()
        conn.close()

        if user_data:
            deidis, rank = user_data
            next_rank_deidis = None
            next_rank_name = None

            # Logik für die benötigten Deidis zum nächsten Rang

            if rank == 0:
                next_rank_deidis = 150
                next_rank_name = 1
            elif rank == 1:
                next_rank_deidis = 450
                next_rank_name = 2
            elif rank == 2:
                next_rank_deidis = 900
                next_rank_name = 3
            elif rank == 3:
                next_rank_deidis = 1500
                next_rank_name = 4
            elif rank == 4:
                next_rank_deidis = 2750
                next_rank_name = 5
            elif rank == 5:
                next_rank_deidis = 3500
                next_rank_name = 6
            elif rank == 6:
                next_rank_deidis = 4000
                next_rank_name = 7
            elif rank == 7:
                next_rank_deidis = 4900
                next_rank_name = 8
            elif rank == 8:
                next_rank_deidis = 5555
                next_rank_name = 9
            elif rank == 9:
                next_rank_deidis = 6969
                next_rank_name = 10
            elif rank == 10:
                next_rank_deidis = 7575
                next_rank_name = 11
            elif rank == 11:
                next_rank_deidis = 8008
                next_rank_name = 12
            elif rank == 12:
                next_rank_deidis = 9000
                next_rank_name = 13
            elif rank == 13:
                next_rank_deidis = 10101
                next_rank_name = 14
            elif rank == 14:
                next_rank_deidis = 12000
                next_rank_name = 15
            elif rank == 15:
                next_rank_deidis = 14444
                next_rank_name = 16
            elif rank == 16:
                next_rank_deidis = 16048
                next_rank_name = 17
            elif rank == 17:
                next_rank_deidis = 18500
                next_rank_name = 18
            elif rank == 18:
                next_rank_deidis = 20000
                next_rank_name = 19
            elif rank == 19:
                next_rank_deidis = 24000
                next_rank_name = 20
            elif rank == 20:
                next_rank_deidis = 30000
                next_rank_name = 21
            elif rank == 21:
                next_rank_deidis = 45000
                next_rank_name = 22
            elif rank == 22:
                next_rank_deidis = 60000
                next_rank_name = 23
            elif rank == 23:
                next_rank_deidis = 80000
                next_rank_name = 24
            elif rank == 24:
                next_rank_deidis = 100000
                next_rank_name = "MAX"

            deidis_bis_naechster_rang = next_rank_deidis - deidis 

            await ctx.send(f"@{username}, dein Rang ist {rank}. Dir fehlen noch {deidis_bis_naechster_rang} Deidis bis Rang {next_rank_name}.")
        else:
            await ctx.send(f"@{username}, du bist noch nicht in der Deidis-Datenbank.")


    @commands.command(name="kok", aliases=["Kok","cock","Cock"])
    async def kok(self, ctx):
        user = ctx.author.name
        command_name = "kok"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        benutzer_id = ctx.author.id

        laenge = random.uniform(-60, 60)  # Zufällige Gleitkommazahl
        laenge_gerundet = round(laenge, 2)

        nachricht = ""

        if laenge_gerundet < -50:
            nachricht = f"{ctx.author.name}, dein kok ist {laenge_gerundet} cm groß deidar16Auslachen 🫵😹😹😹! "
        elif laenge_gerundet < -20:
            nachricht = f"{ctx.author.name}, dein kok ist {laenge_gerundet} cm groß deidar16Auslachen 😴😴😴! "
        elif laenge_gerundet < 0:
            nachricht = f"{ctx.author.name}, dein kok ist {laenge_gerundet} cm groß deidar16Auslachen !"
        elif laenge_gerundet == 0:
            nachricht = f"{ctx.author.name}, dein kok ist {laenge_gerundet} cm groß 🫵😹 "
        elif laenge_gerundet < 20:
            nachricht = f"{ctx.author.name}, dein kok ist {laenge_gerundet} cm groß 😴 "
        elif laenge_gerundet < 40:
            nachricht = f"{ctx.author.name}, dein kok ist {laenge_gerundet} cm groß :O "
        elif laenge_gerundet < 55:
            nachricht = f"{ctx.author.name}, dein kok ist {laenge_gerundet} cm groß :O :O 👏 "
        else:
            nachricht = f"{ctx.author.name}, dein kok ist {laenge_gerundet} cm groß!!!!! deidar16WasZurHoelleRave  🎉🎉🎉"

        await ctx.send(nachricht)


    @commands.command(name="deletefromdeidis")
    async def deletefromdeidis(self, ctx, user: str):
        # Überprüfen, ob der Aufrufer deidaraxx ist
        if ctx.author.name.lower() != "deidaraxx":
            await ctx.send("❌ Du hast keine Berechtigung, diesen Befehl zu verwenden.")
            return

        username = user.lstrip("@")  # Entferne ein vorangestelltes '@', falls vorhanden

        # Entferne den Benutzer aus der deidis-Datenbank
        conn_deidis = sqlite3.connect("deidis_v2.db")
        c_deidis = conn_deidis.cursor()
        c_deidis.execute("DELETE FROM users WHERE username = ?", (username,))
        rows_deleted_deidis = c_deidis.rowcount  # Anzahl der gelöschten Zeilen
        conn_deidis.commit()
        conn_deidis.close()

        # Entferne den Benutzer aus der notifications-Datenbank
        conn_notifications = sqlite3.connect("notifications.db")
        c_notifications = conn_notifications.cursor()
        c_notifications.execute("DELETE FROM users WHERE username = ?", (username,))
        rows_deleted_notifications = c_notifications.rowcount  # Anzahl der gelöschten Zeilen
        conn_notifications.commit()
        conn_notifications.close()

        if rows_deleted_deidis > 0 or rows_deleted_notifications > 0:
            await ctx.send(f"✅ Benutzer @{username} wurde erfolgreich aus allen relevanten Datenbanken entfernt.")
        else:
            await ctx.send(f"❌ Benutzer @{username} wurde in keiner der relevanten Datenbanken gefunden.")

    @commands.command(name="clear75690486049868")
    async def clearen(self, ctx):
        if ctx.author.is_mod or ctx.author.is_broadcaster:
            anzahl_wiederholungen = 3 # Anzahl der Wiederholungen des clear Befehls
            verzögerung = 0.001 # Verzögerung zwischen den Befehlen in Sekunden
            countdown = 1

            await ctx.reply("3...")
            await asyncio.sleep(countdown)
            await ctx.reply("2...")
            await asyncio.sleep(countdown)
            await ctx.reply("1...")
            await asyncio.sleep(countdown)
            await ctx.send("🚨")

            for _ in range(anzahl_wiederholungen):
                await ctx.send("/clear")
                await asyncio.sleep(verzögerung) # Kurze Pause

            await ctx.send(f"Der Chat wurde von @{ctx.author.name} geleert (x{anzahl_wiederholungen}).")
        else:
            await ctx.send(f"@{ctx.author.name}, du hast keine Berechtigung, diesen Befehl auszuführen.")
    
    @commands.command(name="leeren43563465346546")
    async def leeren(self, ctx):
        print(f"Befehl 'leeren' wurde von {ctx.author.name} aufgerufen.") # Debugging-Ausgabe
        print(f"Ist Moderator: {ctx.author.is_mod}") # Debugging-Ausgabe
        print(f"Ist Broadcaster: {ctx.author.is_broadcaster}") # Debugging-Ausgabe
        if ctx.author.is_mod or ctx.author.is_broadcaster:
            print("Berechtigung erteilt. Versuche Chat zu leeren.") # Debugging-Ausgabe
            try:
                await ctx.channel.clear()
                await ctx.send(f"Der Chat wurde von @{ctx.author.name} geleert.")
                print("Chat wurde erfolgreich geleert.") # Debugging-Ausgabe
            except Exception as e:
                print(f"Fehler beim Leeren des Chats: {e}") # Fehler ausgeben
        else:
            print("Keine Berechtigung.") # Debugging-Ausgabe
            await ctx.send(f"@{ctx.author.name}, du hast keine Berechtigung, diesen Befehl auszuführen.")

    @commands.command(name="leeren167567567567")
    async def leeren1(self, ctx):
        if ctx.author.is_mod or ctx.author.is_broadcaster:
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {
                        "Authorization": f"Bearer {ACCESS_TOKEN}", # Dein Bot OAuth Token
                        "Client-Id": CLIENT_ID, # Deine Client ID
                        "Content-Type": "application/json"
                    }
                    data = {} # Leeres JSON-Objekt zum leeren des Chats
                    broadcaster_id = ctx.channel.id # ID des Kanals
                    moderator_id = ctx.author.id # ID des Moderators (oder Broadcasters)

                    url = f"https://api.twitch.tv/helix/moderation/chat?broadcaster_id={broadcaster_id}&moderator_id={moderator_id}"
                    async with session.delete(url, headers=headers, json=data) as response:
                        if response.status == 204: # 204 No Content = Erfolgreich
                            await ctx.send(f"Der Chat wurde von @{ctx.author.name} geleert.")
                        else:
                            error_data = await response.json()
                            print(f"Fehler beim Leeren des Chats: {response.status} - {error_data}")
                            await ctx.send(f"Es gab einen Fehler beim Leeren des Chats. ({response.status})")
            except Exception as e:
                print(f"Unerwarteter Fehler beim Leeren des Chats: {e}")
                await ctx.send(f"Es gab einen unerwarteten Fehler beim Leeren des Chats.")
        else:
            await ctx.send(f"@{ctx.author.name}, du hast keine Berechtigung, diesen Befehl auszuführen.")

    @commands.command(name="adddeidis")
    async def add_deidis(self, ctx, to_user: str, amount: int):
            if ctx.author.name.lower() != "deidaraxx":
                await ctx.send("Nur der Besitzer darf diesen Befehl verwenden! deidar16Grrrrr")
                return

            to_user = to_user.lstrip("@").lower()  # Entferne '@' und normalisiere den Benutzernamen



            conn = sqlite3.connect("deidis_v2.db")
            c = conn.cursor()

            try:
                c.execute("INSERT OR IGNORE INTO users (username, deidis) VALUES (?, 0)", (to_user,))
                c.execute("UPDATE users SET deidis = deidis + ? WHERE username = ?", (amount, to_user))
                conn.commit()
                await ctx.send(f"@{ctx.author.name} hat {amount} Deidis an @{to_user} gutgeschrieben!")
                update_rank(to_user, ctx)
            except sqlite3.Error as e:
                conn.rollback()  # Rollback bei Fehler
                await ctx.send(f"Es gab einen Fehler beim Gutschreiben der Deidis: {e}")
                print(f"Fehler in add_deidis: {e}")
            finally:
                conn.close()

    @commands.command(name="duel")
    async def duel_command(self, ctx, challenged_user: str = None, bet: int = 0):
        user = ctx.author.name
        command_name = "duel"
        cooldown_time = 5 # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        if challenged_user is None:
            await ctx.send("Bitte gib einen Benutzer an, den du herausfordern möchtest. (z.B. &duel @Nutzer)")
            return

        challenged_user = challenged_user.lstrip("@").lower()
        challenger = ctx.author.name.lower()

        if challenged_user == challenger:
            await ctx.send("Du kannst dich nicht selbst herausfordern!")
            return

        if bet <= 0:
            await ctx.send("Bitte gib einen gültigen Einsatz (mehr als 0) an.")
            return

        conn = sqlite3.connect("deidis_v2.db")
        c = conn.cursor()
        try:
            # Herausforderer Deidis abrufen
            c.execute("SELECT deidis FROM users WHERE username = ?", (challenger,))
            challenger_data = c.fetchone()
            if challenger_data is None:
                await ctx.send(f"❌ @{challenger}, du bist nicht in der Datenbank. Sammle zuerst Deidis mit `&deidis`.")
                return
            challenger_deidis = challenger_data[0]

            # Herausgeforderter Deidis abrufen
            c.execute("SELECT deidis FROM users WHERE username = ?", (challenged_user,))
            challenged_data = c.fetchone()
            if challenged_data is None:
                await ctx.send(f"❌ @{challenged_user} ist nicht in der Datenbank. Der Benutzer muss zuerst Deidis sammeln.")
                return
            challenged_deidis = challenged_data[0]

            if bet > challenger_deidis or bet > challenged_deidis:
                await ctx.send("Einer der Spieler hat nicht genug Deidis.")
                return
        except sqlite3.Error as e:
            print(f"Fehler beim Überprüfen der Deidis: {e}")
            await ctx.send("Es gab einen Fehler beim Überprüfen der Deidis.")
            return
        finally:
            conn.close()

        await ctx.send(f"@{challenger} fordert @{challenged_user} zu einem Duell um {bet} Deidis heraus! @{challenged_user}, schreibe 'accept', um anzunehmen.")

        # Speichern der Herausforderung
        self.active_duels[challenged_user] = {
            "challenger": challenger,
            "bet": bet,
            "channel": ctx.channel.name,
        }

    @commands.command(name="accept")
    async def accept_duel(self, ctx):
        user = ctx.author.name
        command_name = "accept"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        challenged_user = ctx.author.name.lower()

        # Überprüfen, ob eine aktive Herausforderung existiert
        if challenged_user not in self.active_duels:
            await ctx.send(f"❌ @{challenged_user}, es gibt keine aktive Herausforderung, die du annehmen kannst.")
            return

        duel = self.active_duels.pop(challenged_user)
        challenger = duel["challenger"]
        bet = duel["bet"]

        # Gewinner bestimmen
        winner = random.choice([challenger, challenged_user])
        if winner == challenger:
            update_deidis(challenger, bet)
            update_deidis(challenged_user, -bet)
        else:
            update_deidis(challenger, -bet)
            update_deidis(challenged_user, bet)

        await ctx.send(f"🎉 @{winner} hat das Duell gewonnen und {bet} Deidis erhalten!")



    @commands.command(name="steal", aliases=["klauen"])
    async def steal(self, ctx, target_user: str, amount: int = None):
        user = ctx.author.name
        command_name = "steal"
        cooldown_time = 10  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        """Ermöglicht es einem Benutzer, Deidis von einem anderen zu stehlen."""
        thief = ctx.author.name.lower()
        target = target_user.lstrip("@").lower()

        if thief == target:
            await ctx.send("❌ Du kannst nicht von dir selbst stehlen!")
            return

        conn = sqlite3.connect("deidis_v2.db")
        c = conn.cursor()

        # Überprüfen, ob das Ziel in der Datenbank existiert
        c.execute("SELECT deidis FROM users WHERE username = ?", (target,))
        target_data = c.fetchone()

        if not target_data:
            await ctx.send(f"❌ {target} ist nicht in der Datenbank!")
            conn.close()
            return

        target_deidis = target_data[0]

        if target_deidis <= 0:
            await ctx.send(f"❌ {target} hat keine Deidis zum Stehlen.")
            conn.close()
            return

        # Bestimmen, wie viele Deidis gestohlen werden sollen
        if amount is None:
            amount = random.randint(1, min(50, target_deidis // 2))  # Zufälliger Betrag, falls keine Zahl angegeben wurde

        if amount > target_deidis:
            amount = target_deidis  # Es kann nicht mehr gestohlen werden, als der Nutzer hat

        # Erfolgswahrscheinlichkeit berechnen
        success_chance = max(2, 10 - (amount / target_deidis) * 100)  # Sehr geringe Wahrscheinlichkeit bei hohen Beträgen
        success = random.randint(1, 100) <= success_chance

        if success:
            # Aktualisieren der Deidis-Werte
            c.execute("UPDATE users SET deidis = deidis - ? WHERE username = ?", (amount, target))
            c.execute("UPDATE users SET deidis = deidis + ? WHERE username = ?", (amount, thief))
            conn.commit()

            # Steal-Statistiken aktualisieren
            conn_stats = sqlite3.connect("steal_stats.db")
            c_stats = conn_stats.cursor()

            # Angreifer-Statistiken aktualisieren
            c_stats.execute("INSERT OR IGNORE INTO steal_stats (username) VALUES (?)", (thief,))
            c_stats.execute("UPDATE steal_stats SET stolen_from_others = stolen_from_others + ? WHERE username = ?", (amount, thief))

            # Opfer-Statistiken aktualisieren
            c_stats.execute("INSERT OR IGNORE INTO steal_stats (username) VALUES (?)", (target,))
            c_stats.execute("UPDATE steal_stats SET stolen_by_others = stolen_by_others + ? WHERE username = ?", (amount, target))

            conn_stats.commit()
            conn_stats.close()

            await ctx.send(f"🎉 @{thief} hat erfolgreich {amount} Deidis von @{target} gestohlen!")
            update_rank(thief, ctx)
        else:
            # Strafe bei Fehlschlag
            penalty = min(amount // 1, 5)  # Strafe ist die Hälfte des gestohlenen Betrags, max. 20
            c.execute("SELECT deidis FROM users WHERE username = ?", (thief,))
            thief_data = c.fetchone()
            thief_deidis = thief_data[0] if thief_data else 0

            penalty = round(min(penalty, thief_deidis))  # Strafe darf nicht höher als der Kontostand sein

            # Abziehen der Strafe vom Dieb und Hinzufügen zum Opfer
            c.execute("UPDATE users SET deidis = deidis - ? WHERE username = ?", (penalty, thief))
            c.execute("UPDATE users SET deidis = deidis + ? WHERE username = ?", (penalty, target))
            conn.commit()

            await ctx.send(f"❌ @{thief} hat versucht, {amount} Deidis von @{target} zu stehlen, :/ Als strafe muss er {penalty} Deidis zahlen! :7")
            update_rank(target, ctx)
        conn.close()







    @commands.command(name="mass")
    async def mass_command(self, ctx):
        """Listet alle Benutzer im Chatraum auf."""
        user = ctx.author.name
        command_name = "mass"
        cooldown_time = 10  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        if ctx.author.is_mod:
            try:
                chatters = ctx.channel.chatters # Alle Chatter im Channel abrufen
                chatter_names = [chatter.name for chatter in chatters] # Nur die Namen extrahieren

                if chatter_names: # Überprüfen, ob überhaupt Chatter vorhanden sind
                    # Nachricht formatieren (max. 500 Zeichen pro Nachricht auf Twitch)
                    message = ", ".join(chatter_names)
                    #Nachrichten aufteilen falls zu lang
                    messages = [message[i:i + 450] for i in range(0, len(message), 450)]
                    for msg in messages:
                        await ctx.send(f"{msg}")

                else:
                    await ctx.send("Es sind keine Zuschauer im Chat.")

            except Exception as e:
                await ctx.send(f"Ein Fehler ist aufgetreten: {e}")


    @commands.command(name="chatters4365457567657")
    async def chatters_command(self, ctx):
        try:
            chatters = ctx.channel.chatters
            chatter_count = 0
            moderator_count = 0
            vip_count = 0

            chatter_names = [chatter.name for chatter in chatters]
            for chatter_name in chatter_names:
                try:
                    chatter = await ctx.channel.get_chatter(chatter_name)
                    chatter_count += 1
                    if chatter.is_mod:
                        moderator_count += 1
                    if chatter.is_vip:
                        vip_count += 1
                except twitchio.errors.HTTPError:
                    pass

            normal_chatter_count = chatter_count - moderator_count - vip_count

            headers = {'Client-ID': CLIENT_ID}
            url = f'https://api.twitch.tv/helix/streams?user_login={ctx.channel.name}'
            try: # Try-Except Block für den Request
                response = requests.get(url, headers=headers).json()
            except requests.exceptions.RequestException as e:
                await ctx.send(f"Fehler beim Abrufen der Zuschauerzahl von der Twitch API: {e}")
                return # Wichtig, um den Rest des Befehls abzubrechen

            if response['data']:
                viewer_count = response['data'][0]['viewer_count']
                await ctx.send(f"Aktuelle Zuschauer: {viewer_count}, Aktive Chatter im Chat: {chatter_count} (davon {moderator_count} Moderatoren, {vip_count} VIPs und {normal_chatter_count} normale Chatter).")
            else:
                await ctx.send(f"Aktive Chatter im Chat: {chatter_count} (davon {moderator_count} Moderatoren, {vip_count} VIPs und {normal_chatter_count} normale Chatter). Der Stream ist offline oder die Zuschauerzahl konnte nicht abgerufen werden.")

        except Exception as e:
            await ctx.send(f"Ein unerwarteter Fehler ist aufgetreten: {e}")

    @commands.command(name="timer")
    async def timer(self, ctx, time_input: str, *, title: str = ""):
        user = ctx.author.name
        command_name = "timer"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        user = ctx.author.name.lower()
        channel = ctx.channel.name  # Speichere den aktuellen Kanal

        # Zeitangabe parsen
        end_time = parse_timer_input(time_input)
        if not end_time:
            await ctx.send("❌ Ungültiges Zeitformat. Bitte gib eine korrekte Zeit an (z. B. 10, 10s, 5m, 01.01.2024).")
            return

        conn = sqlite3.connect("deidis_v2.db")
        c = conn.cursor()

        try:
            # Timer in die Datenbank einfügen
            c.execute("INSERT INTO timer (username, end_time, title, channel) VALUES (?, ?, ?, ?)", 
                    (user, end_time.strftime("%Y-%m-%d %H:%M:%S"), title, channel))
            conn.commit()
            await ctx.send(f"✅ @{user}, dein Timer {title} wurde für {time_input} gesetzt.")
        except sqlite3.Error as e:
            print(f"Fehler beim Hinzufügen des Timers: {e}")
            await ctx.send("❌ Es gab einen Fehler beim Erstellen des Timers.")
        finally:
            conn.close()

  
    @commands.command(name='say', aliases=["sayat"])
    async def say(self, ctx, *, args=None):
        user = ctx.author.name
        command_name = "say"
        cooldown_time = 5  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        
        if not args or len(args.split()) < 2:
            prefix = ctx.prefix
            usage = f"&say <channel> <message>".replace("&", prefix)
            return await ctx.send(f"Schreibe: {usage}")

        args = args.split()
        channel_name = args[0].replace('@', '').replace(',', '').strip().lower()
        message = "➡️ " + " ".join(args[1:])

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.ivr.fi/v2/twitch/user?login={channel_name}") as response:
                    if response.status != 200:
                        raise Exception(f"HTTP Say Error: {response.status}")
                    data = await response.json()
                    if not data:
                        return await ctx.send(f"➜ {channel_name} nicht gefunden")

            target_channel = self.get_channel(channel_name)
            if target_channel:
                await target_channel.send(message)
                if ctx.channel.name != channel_name:
                    await ctx.reply(f"👍")
            else:
                await ctx.send(f"{channel_name} hat mich noch nicht. FeelsDankMan")
        except Exception as error:
            print(error)
            await ctx.send(f"➜ Error: {error}")


    @commands.command(name='clear')
    async def clear(self, ctx):
            channel_name = ctx.channel.name
            await ctx.send("CLEAR START")
            for i in range(3, 0, -1):
                await asyncio.sleep(1)
                await ctx.send(f"CLEAR {i}...")
            
            async with aiohttp.ClientSession() as session:
                try:
                    url = f"https://api.ivr.fi/v2/twitch/user?login={channel_name}"
                    async with session.get(url) as response:
                        if response.status != 200:
                            await ctx.send("/me Fehler")
                            return
                        data = await response.json()
                        broadcaster_id = data[0]['id']
                except Exception as e:
                    await ctx.send(f" Fehler bei ID: {e}")
                    return

            self.clear_running = True
            success_count = 0
            error_count = 0

            async def send_clear_requests():
                nonlocal success_count, error_count
                url = f'https://api.twitch.tv/helix/moderation/chat?broadcaster_id={broadcaster_id}&moderator_id=1106471679'
                headers = {
                    'Authorization': f'Bearer {ACCESS_TOKEN}',
                    'Client-ID': f'{CLIENT_ID}',
                    'Content-Type': 'application/json'
                }
                try:
                    clear_response = requests.delete(url, headers=headers)
                    if clear_response.status_code == 204:
                        success_count += 1
                    else:
                        error_count += 1
                        error_message = clear_response.json()
                        print(f"Fehler Code: {error_message}")
                except Exception as e:
                    print(f"Fehler beim Clearen des Chats: {e}")
                    error_count += 1

            tasks = [send_clear_requests() for _ in range(100)]
            await asyncio.gather(*tasks)
            self.clear_running = False

            if success_count > 0:
                await ctx.send("Saved")
            else:
                await ctx.send("Fehler beim clearen")  # geht aber nicht weil client id mit den token2 nicht geht also info tokens sind ohne oauth


    @commands.command(name="commands", aliases=["help", "Commands", "Help"])
    async def help(self, ctx):
        user = ctx.author.name
        command_name = "commands"
        cooldown_time = 7  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        """Listet alle verfügbaren Befehle einzeln auf."""
        commands_list = [
            "&deidis - Sammelt Deidis, wenn verfügbar.",
            "&bet <Betrag> - Setze Deidis und gewinne oder verliere.",
            "&stats [Nutzer] - Zeigt Statistiken zu dir oder einem Nutzer.",
            "&steal <Nutzer> [Betrag] - Versuche, Deidis von einem Nutzer zu stehlen.",
            "&rank - Zeigt deinen aktuellen Rang und Fortschritt.",
            "&give <Nutzer> <Betrag> - Überweise Deidis an einen Nutzer.",
            "&join <Kanal> - Fügt den Bot zu deinem Kanal hinzu.",
            "&leave - Entfernt den Bot aus deinem Kanal.",
            "&mass - Sendet eine Nachricht an alle Kanäle.",
            "&test - Führt einen Countdown zu einem Ereignis aus.",
            "&toggle - Schaltet Benachrichtigungen für Deidis ein/aus.",
            "&commands - Zeigt diese Liste an.",
        ]

        # Jeden Befehl einzeln senden
        for command in commands_list:
            await ctx.send(command)




    @commands.command(name="forceJoin")
    async def force_join(self, ctx, channel_name: str):
        if ctx.author.name != "deidaraxx":
            await ctx.send("❌ Du hast keine Berechtigung, diesen Befehl zu verwenden.")
            return

        formatted_channel = f"#{channel_name.strip('#')}"  # Formatieren des Kanals

        if formatted_channel in self.active_channels:
            await ctx.send(f"❌ Der Bot ist bereits im Kanal {formatted_channel} aktiv.")
            return

        try:
            activate_channel(formatted_channel)  # Kanal aktivieren
            self.active_channels.append(formatted_channel)  # Lokale Liste aktualisieren
            await self.join_channels([formatted_channel])  # Kanal beitreten
            await ctx.send(f"✅ Ich habe den Kanal {formatted_channel} erfolgreich hinzugefügt und bin ihm beigetreten.")
        except Exception as e:
            await ctx.send(f"❌ Fehler beim Hinzufügen und Beitreten des Kanals: {e}")


    
    @commands.command(name="birthday", aliases=["bday", "geburtstag"])
    async def birthday(self, ctx, *args):
        user = ctx.author.name.lower()
        conn = sqlite3.connect("birthdays.db")
        c = conn.cursor()

        try:
            # Tabelle mit nur Tag und Monat erstellen (falls noch nicht vorhanden)
            c.execute('''
                CREATE TABLE IF NOT EXISTS birthdays_new (
                    username TEXT PRIMARY KEY,
                    day INTEGER NOT NULL,
                    month INTEGER NOT NULL
                )
            ''')
            conn.commit()

            if not args:
                c.execute("SELECT day, month FROM birthdays_new WHERE username = ?", (user,))
                result = c.fetchone()
                if result:
                    days = days_until_birthday(result[0], result[1])
                    if days is not None:
                        await ctx.send(f"@{user}, dein Geburtstag ist am {result[0]}.{result[1]} (in {days} Tagen)")
                    else:
                        await ctx.send(f"@{user}, dein Geburtstag ist am {result[0]}.{result[1]}!") #Fallback
                else:
                    await ctx.send(f"❌ @{user}, du hast deinen Geburtstag noch nicht eingetragen. Schreibe `&birthday <Tag>.<Monat>` (z.B. 24.12).")
            elif len(args) == 1:
                birthday = parse_birthday(args[0])
                if birthday:
                    day, month = birthday
                    c.execute("INSERT OR REPLACE INTO birthdays_new (username, day, month) VALUES (?, ?, ?)", (user, day, month))
                    conn.commit()
                    await ctx.send(f"✅ @{user}, dein Geburtstag wurde am {day}.{month} gespeichert!")
                else:
                    await ctx.send(f"❌ Ungültiges Datum. Bitte nutze das Format 'Tag.Monat' (z.B. 24.12).")
            elif len(args) == 2 and args[0].lower() == "check":
                target_user = args[1].lstrip("@").lower()
                c.execute("SELECT day, month FROM birthdays_new WHERE username = ?", (target_user,))
                result = c.fetchone()
                if result:
                    days = days_until_birthday(result[0], result[1])
                    if days is not None:
                        await ctx.send(f"@{target_user} hat am {result[0]}.{result[1]} Geburtstag (in {days} Tagen!)")
                    else:
                        await ctx.send(f"@{target_user} hat am {result[0]}.{result[1]} Geburtstag!") #Fallback
                else:
                    await ctx.send(f"❌ @{target_user} hat keinen Geburtstag eingetragen.")
            else:
                await ctx.send(f"❌ Ungültige Nutzung. Schreibe `&birthday <Tag>.<Monat>` oder `&birthday check @Nutzer`.")

        except sqlite3.Error as e:
            print(f"Fehler beim Bearbeiten des Geburtstags: {e}")
            await ctx.send(f"❌ Ein Fehler ist aufgetreten.")
        finally:
            conn.close()



    @commands.command(name="echo")
    async def echo(self, ctx, *, message: str):
        user = ctx.author.name
        command_name = "echo"
        cooldown_time = 2 # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        """Wiederholt die Nachricht des Benutzers."""
        await ctx.send(message)


    @commands.command(name="ostern", aliases=["easter"])
    async def ostern_command(self, ctx):
        now = datetime.now()
        current_year = now.year
        easter_date = calculate_easter(current_year)

        if now.date() > easter_date: #wenn Ostern schon vorbei ist, wird das Osterdatum für nächstes Jahr berechnet
            easter_date = calculate_easter(current_year +1)

        time_remaining = datetime(easter_date.year, easter_date.month, easter_date.day) - now

        days = time_remaining.days
        hours, remainder = divmod(time_remaining.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        message = f"Es sind noch {days} Tage, {hours} Stunden, {minutes} Minuten und {seconds} Sekunden bis Ostern {easter_date.year}!"

        if days < 0:
            message = "Ostern war schon dieses Jahr!"

        await ctx.send(message)


    @commands.command(name="weihnachten", aliases=["christmas", "xmas"])
    async def weihnachten_command(self, ctx):
        now = datetime.now()
        current_year = now.year
        christmas_date = date(current_year, 12, 24)

        if now.date() > christmas_date: #wenn Weihnachten schon vorbei ist, wird das Weihnachtstdatum für nächstes Jahr berechnet
            christmas_date = date(current_year + 1, 12, 24)


        time_remaining = datetime(christmas_date.year, christmas_date.month, christmas_date.day) - now

        days = time_remaining.days
        hours, remainder = divmod(time_remaining.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        message = f"Es sind noch {days} Tage, {hours} Stunden, {minutes} Minuten und {seconds} Sekunden bis Weihnachten {christmas_date.year}!"

        if days < 0:
            message = "Frohe Weihnachten! Das war dieses Jahr!"

        await ctx.send(message)





    @commands.command(name="calculate", aliases=["calc", "berechnen","rechnen","Calculate","Rechnen","rechne","Rechne"])
    async def calculate(self, ctx, *args):
        user = ctx.author.name
        command_name = "calculate"
        cooldown_time = 2  # 5 sekunden

        # Cooldown prüfen
        can_execute, remaining_time = check_cooldown_db(user, command_name, cooldown_time)
        if not can_execute:
            return
        """Löst Rechenaufgaben, Währungsumrechnungen und Zeiteinheiten."""
        if not args:
            await ctx.send("❌ Bitte gib eine gültige Rechenaufgabe oder Konvertierung an.")
            return

        try:
            query = " ".join(args)

            # Mathematische Berechnung (z. B. 2 + 3 * 5)
            if re.match(r"^[0-9\.\+\-\*/\(\)\s]+$", query):
                result = eval(query)
                await ctx.reply(f"🧮{result}")
                return

            # Währungsumrechnung (z. B. 20 USD EUR)
            match = re.match(r"(\d+(\.\d+)?)\s?([A-Za-z]{3})\s?([A-Za-z]{3})", query)
            if match:
                amount = float(match.group(1))
                from_currency = match.group(3).upper()
                to_currency = match.group(4).upper()
                result = convert_currency(amount, from_currency, to_currency)
                await ctx.send(f"💱 {amount} {from_currency} = {result:.2f} {to_currency}")
                return


            # Zeiteinheiten umrechnen (z. B. 1h m)
            match = re.match(r"(\d+)\s?([a-zA-Z]+)\s?([a-zA-Z]*)", query)
            if match:
                value = int(match.group(1))
                from_unit = match.group(2).lower()
                to_unit = match.group(3).lower()
                result = convert_time(value, from_unit, to_unit)
                await ctx.send(f"⏱️ {value} {from_unit} = {result}")
                return

            await ctx.send("❌ Unbekannte Eingabe. Versuche eine Rechenaufgabe, Währungsumrechnung oder Zeiteinheit.")
        except Exception as e:
            print(f"Fehler bei &calculate: {e}")
            await ctx.send("❌ Ein Fehler ist aufgetreten. Bitte überprüfe deine Eingabe.")


    async def broadcast_message(self, message):
        """Sendet eine Nachricht an alle aktiven Kanäle."""
        for channel in self.connected_channels:
            try:
                # Prüfen, ob `channel` ein `str` oder ein `Channel`-Objekt ist
                if isinstance(channel, str):
                    # Wenn es ein Name ist, sende die Nachricht direkt
                    await self.join_channels([channel])
                    await self.get_channel(channel).send(message)
                elif hasattr(channel, "send"):
                    # Wenn es ein `Channel`-Objekt ist, sende die Nachricht
                    await channel.send(message)
                else:
                    print(f"Unbekannter Kanaltyp: {type(channel)}")
            except Exception as e:
                print(f"Fehler beim Senden an Kanal {channel}: {e}")

    async def neuesjahr(bot):
        """Countdown bis Silvester, sendet Ankündigungen in allen aktiven Kanälen."""
        target_time = datetime(datetime.now().year + 1, 1, 1, 0, 0, 0)  # Silvester um Mitternacht
        notified_intervals = set()  # Verfolgung der bereits angekündigten Zeitpunkte

        while True:
            now = datetime.now()
            remaining = target_time - now  # Verbleibende Zeit berechnen

            if remaining.total_seconds() <= 0:
                # Silvester ist erreicht
                await broadcast_message(bot, "🎉 Frohes neues Jahr! 🎆")
                break

            # Countdown-Ankündigungen basierend auf der verbleibenden Zeit
            if remaining.total_seconds() >= 600 and "10m" not in notified_intervals:  # 10 Minuten
                await broadcast_message(bot, "⏳ Noch 10 Minuten bis zum neuen Jahr!")
                notified_intervals.add("10m")
            elif remaining.total_seconds() >= 300 and "5m" not in notified_intervals:  # 5 Minuten
                await broadcast_message(bot, "⏳ Noch 5 Minuten bis zum neuen Jahr!")
                notified_intervals.add("5m")
            elif remaining.total_seconds() >= 180 and "3m" not in notified_intervals:  # 3 Minuten
                await broadcast_message(bot, "⏳ Noch 3 Minuten bis zum neuen Jahr!")
                notified_intervals.add("3m")
            elif remaining.total_seconds() >= 60 and "1m" not in notified_intervals:  # 1 Minute
                await broadcast_message(bot, "⏳ Noch 1 Minute bis zum neuen Jahr!")
                notified_intervals.add("1m")
            elif remaining.total_seconds() <= 10 and remaining.total_seconds() > 0 and "10s" not in notified_intervals:
                # Ab 10 Sekunden vor Mitternacht herunterzählen
                await broadcast_message(bot, f"⏳ Noch {int(remaining.total_seconds())} Sekunden!")
                if remaining.total_seconds() <= 1:
                    notified_intervals.add("10s")

            await asyncio.sleep(1)  # Jede Sekunde prüfen

        async def broadcast_message(self, message):
            """Sendet eine Nachricht an alle aktiven Kanäle."""
            for channel in self.connected_channels:
                try:
                    # Prüfen, ob `channel` ein `str` oder ein `Channel`-Objekt ist
                    if isinstance(channel, str):
                        # Wenn es ein Name ist, sende die Nachricht direkt
                        await self.join_channels([channel])
                        await self.get_channel(channel).send(message)
                    elif hasattr(channel, "send"):
                        # Wenn es ein `Channel`-Objekt ist, sende die Nachricht
                        await channel.send(message)
                    else:
                        print(f"Unbekannter Kanaltyp: {type(channel)}")
                except Exception as e:
                    print(f"Fehler beim Senden an Kanal {channel}: {e}")







    @commands.command(name="test")
    async def test(self, ctx):
        """Countdown zu einem Ereignis."""
        now = datetime.now()
        target = now.replace(hour=23, minute=59, second=50)  # Beispielzielzeit (Mitternacht)

        while now < target:
            remaining = (target - now).total_seconds()

            # Countdown-Nachrichten
            if remaining in [600, 300, 180, 120, 60]:  # Minutenmarken
                minutes = int(remaining // 60)
                await self.broadcast_message(f"⏳ Noch {minutes} Minuten bis zum Ereignis!")
            elif remaining <= 10:  # Letzter Countdown
                await self.broadcast_message(f"⏳ Noch {int(remaining)} Sekunden!")

            await asyncio.sleep(1)
            now = datetime.now()

        # Abschlussnachricht: Jeder Nutzer einzeln
        for channel_name in self.connected_channels:
            channel = self.get_channel(channel_name)
            async for user in channel.users:
                await channel.send(f"🎉 @{user.name}, frohes neues Jahr!")



    @commands.command(name="counter_create")
    async def counter_create(self, ctx, name: str, start: int = 0):
        """Erstellt einen neuen Counter für den Kanal."""
        channel = ctx.channel.name.lower()

        conn = sqlite3.connect("counters.db")
        c = conn.cursor()

        try:
            c.execute("INSERT INTO counters (channel, name, count) VALUES (?, ?, ?)", (channel, name, start))
            conn.commit()
            await ctx.send(f"✅ Counter '{name}' wurde erstellt und startet bei {start}.")
        except sqlite3.IntegrityError:
            await ctx.send(f"❌ Ein Counter mit dem Namen '{name}' existiert bereits in diesem Kanal.")
        finally:
            conn.close()


    @commands.command(name="counter_add")
    async def counter_add(self, ctx, name: str, amount: int = 1):
        """Erhöht den Stand eines Counters."""
        channel = ctx.channel.name.lower()

        conn = sqlite3.connect("counters.db")
        c = conn.cursor()

        c.execute("SELECT count FROM counters WHERE channel = ? AND name = ?", (channel, name))
        result = c.fetchone()

        if result:
            new_count = result[0] + amount
            c.execute("UPDATE counters SET count = ? WHERE channel = ? AND name = ?", (new_count, channel, name))
            conn.commit()
            await ctx.send(f"✅ Counter '{name}' wurde aktualisiert: {new_count}.")
        else:
            await ctx.send(f"❌ Kein Counter mit dem Namen '{name}' in diesem Kanal gefunden.")
        conn.close()

    @commands.command(name="counter")
    async def counter(self, ctx):
        """Zeigt alle Counter im aktuellen Kanal an."""
        channel = ctx.channel.name.lower()

        conn = sqlite3.connect("counters.db")
        c = conn.cursor()

        c.execute("SELECT name, count FROM counters WHERE channel = ?", (channel,))
        counters = c.fetchall()

        if counters:
            response = "**📊 Counter in diesem Kanal:**\n"
            response += "\n".join([f"{name}: {count}" for name, count in counters])
            await ctx.send(response)
        else:
            await ctx.send("❌ Es gibt keine Counter in diesem Kanal.")
        conn.close()

    @commands.command(name="counter_delete")
    async def counter_delete(self, ctx, name: str):
        """Löscht einen Counter aus dem aktuellen Kanal."""
        channel = ctx.channel.name.lower()

        conn = sqlite3.connect("counters.db")
        c = conn.cursor()

        c.execute("DELETE FROM counters WHERE channel = ? AND name = ?", (channel, name))
        if c.rowcount > 0:
            conn.commit()
            await ctx.send(f"✅ Counter '{name}' wurde gelöscht.")
        else:
            await ctx.send(f"❌ Kein Counter mit dem Namen '{name}' in diesem Kanal gefunden.")
        conn.close()



    @commands.command()
    async def dynamic_counter(self, ctx, name: str):
        """Zeigt den Stand eines Counters an."""
        channel = ctx.channel.name.lower()

        conn = sqlite3.connect("counters.db")
        c = conn.cursor()

        c.execute("SELECT count FROM counters WHERE channel = ? AND name = ?", (channel, name))
        result = c.fetchone()

        if result:
            await ctx.send(f"📊 Counter '{name}': {result[0]}")
        else:
            await ctx.send(f"❌ Kein Counter mit dem Namen '{name}' in diesem Kanal gefunden.")
        conn.close()

    @commands.command(name="neujahr", aliases=["silvester", "jahreswechsel", "newyear"])
    async def neujahr_command(self, ctx):
        now = datetime.now()
        next_year = now.year + 1
        new_year = datetime(next_year, 1, 1, 0, 0, 0) #Neujahr um 0 Uhr

        time_remaining = new_year - now

        days = time_remaining.days
        hours, remainder = divmod(time_remaining.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        message = f"Es sind noch {days} Tage, {hours} Stunden, {minutes} Minuten und {seconds} Sekunden bis Neujahr {next_year}!"

        if days < 0:
            message = "Frohes neues Jahr! Wir sind schon im Jahr {}!".format(next_year)

        await ctx.send(message)


    @commands.command(name="spawn_meteor")
    async def spawn_meteor_command(self, ctx, rarity: str = None):
        """Erlaubt es deidaraxx, manuell einen Meteor zu spawnen."""
        if ctx.author.name.lower() != "deidaraxx":
            await ctx.send("❌ Dieser Befehl ist nur für den Bot-Administrator verfügbar.")
            return

        await spawn_meteor(bot, ctx.channel.name, rarity)
        await ctx.send(f"✅ Meteor (Seltenheit: {rarity or 'zufällig'}) wurde gespawnt.")


    def clear_old_channels():
        """Entfernt alle Einträge aus der alten Tabelle `channels`."""
        conn = sqlite3.connect("channels.db")
        c = conn.cursor()
        try:
            # Prüfen, ob die Tabelle existiert
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='channels';")
            if c.fetchone():
                # Alle Einträge aus der Tabelle löschen
                c.execute("DELETE FROM channels;")
                conn.commit()
                print("✅ Alle Einträge aus der Tabelle `channels` wurden entfernt.")
            else:
                print("❌ Die Tabelle `channels` existiert nicht.")
        except sqlite3.Error as e:
            print(f"Fehler beim Löschen der Einträge: {e}")
        finally:
            conn.close()

# Starte den Bot
bot = TwitchBot()

bot.run()
