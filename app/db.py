import os
import sqlite3
from datetime import datetime
import secrets
from flask import current_app, g
from werkzeug.security import generate_password_hash

CUSTOMER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

BACKUP_TABLES = [
    'users', 'customers', 'games', 'packages', 'settings', 'site_pages', 'site_sections',
    'media_assets', 'bookings', 'sessions', 'cash_movements', 'events', 'signed_modules',
    'discount_codes', 'promo_popups', 'email_templates', 'newsletter_subscribers',
    'gallery_items', 'game_masters', 'stations', 'activity_logs', 'fidelity_points_history'
]
ID_TABLES = [t for t in BACKUP_TABLES if t != 'settings']

SCHEMA_SQL = "\n    CREATE TABLE IF NOT EXISTS users (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      name TEXT NOT NULL,\n      email TEXT UNIQUE NOT NULL,\n      password_hash TEXT NOT NULL,\n      role TEXT NOT NULL DEFAULT 'operator',\n      created_at TEXT NOT NULL\n    );\n    CREATE TABLE IF NOT EXISTS customers (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      customer_code TEXT UNIQUE,\n      name TEXT NOT NULL,\n      phone TEXT,\n      email TEXT,\n      birthday TEXT,\n      notes TEXT,\n      points INTEGER NOT NULL DEFAULT 0,\n      created_at TEXT NOT NULL\n    );\n    CREATE TABLE IF NOT EXISTS games (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      title TEXT NOT NULL,\n      category TEXT NOT NULL DEFAULT 'VR',\n      players TEXT DEFAULT '1-4',\n      duration INTEGER DEFAULT 30,\n      price REAL DEFAULT 0,\n      description TEXT,\n      cover TEXT,\n      active INTEGER NOT NULL DEFAULT 1\n    );\n    CREATE TABLE IF NOT EXISTS packages (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      name TEXT NOT NULL,\n      minutes INTEGER NOT NULL,\n      price REAL NOT NULL,\n      type TEXT NOT NULL DEFAULT 'VR',\n      active INTEGER NOT NULL DEFAULT 1\n    );\n    CREATE TABLE IF NOT EXISTS bookings (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      customer_id INTEGER,\n      customer_name TEXT NOT NULL,\n      phone TEXT,\n      booking_date TEXT NOT NULL,\n      start_time TEXT NOT NULL,\n      end_time TEXT NOT NULL,\n      service TEXT NOT NULL,\n      status TEXT NOT NULL DEFAULT 'confirmed',\n      people INTEGER DEFAULT 1,\n      deposit REAL DEFAULT 0,\n      total REAL DEFAULT 0,\n      notes TEXT,\n      created_at TEXT NOT NULL,\n      FOREIGN KEY(customer_id) REFERENCES customers(id)\n    );\n    CREATE TABLE IF NOT EXISTS sessions (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      customer_id INTEGER,\n      customer_name TEXT NOT NULL,\n      station TEXT NOT NULL,\n      game_title TEXT,\n      package_name TEXT,\n      start_at TEXT NOT NULL,\n      end_at TEXT NOT NULL,\n      status TEXT NOT NULL DEFAULT 'running',\n      amount REAL DEFAULT 0,\n      paid_method TEXT DEFAULT 'Contanti',\n      notes TEXT,\n      created_at TEXT NOT NULL,\n      FOREIGN KEY(customer_id) REFERENCES customers(id)\n    );\n    CREATE TABLE IF NOT EXISTS cash_movements (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      kind TEXT NOT NULL,\n      description TEXT NOT NULL,\n      amount REAL NOT NULL,\n      method TEXT DEFAULT 'Contanti',\n      created_at TEXT NOT NULL\n    );\n    CREATE TABLE IF NOT EXISTS events (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      title TEXT NOT NULL,\n      event_date TEXT NOT NULL,\n      start_time TEXT NOT NULL,\n      end_time TEXT NOT NULL,\n      customer_name TEXT,\n      phone TEXT,\n      status TEXT NOT NULL DEFAULT 'draft',\n      people INTEGER DEFAULT 1,\n      catering TEXT,\n      total REAL DEFAULT 0,\n      notes TEXT,\n      created_at TEXT NOT NULL\n    );\n    CREATE TABLE IF NOT EXISTS settings (\n      key TEXT PRIMARY KEY,\n      value TEXT\n    );\n    CREATE TABLE IF NOT EXISTS site_pages (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      slug TEXT UNIQUE NOT NULL,\n      nav_label TEXT NOT NULL,\n      title TEXT NOT NULL,\n      subtitle TEXT,\n      hero_image TEXT,\n      meta_description TEXT,\n      show_in_menu INTEGER NOT NULL DEFAULT 1,\n      active INTEGER NOT NULL DEFAULT 1,\n      sort_order INTEGER NOT NULL DEFAULT 0,\n      updated_at TEXT NOT NULL\n    );\n    CREATE TABLE IF NOT EXISTS site_sections (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      page_id INTEGER NOT NULL,\n      section_type TEXT NOT NULL DEFAULT 'text_image',\n      kicker TEXT,\n      title TEXT NOT NULL,\n      body TEXT,\n      image TEXT,\n      button_text TEXT,\n      button_url TEXT,\n      sort_order INTEGER NOT NULL DEFAULT 0,\n      active INTEGER NOT NULL DEFAULT 1,\n      updated_at TEXT NOT NULL,\n      FOREIGN KEY(page_id) REFERENCES site_pages(id) ON DELETE CASCADE\n    );\n    CREATE TABLE IF NOT EXISTS media_assets (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      filename TEXT NOT NULL,\n      original_name TEXT,\n      title TEXT,\n      alt TEXT,\n      created_at TEXT NOT NULL\n    );\n\n    CREATE TABLE IF NOT EXISTS signed_modules (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      customer_name TEXT NOT NULL,\n      phone TEXT,\n      module_type TEXT NOT NULL DEFAULT 'Liberatoria VR',\n      status TEXT NOT NULL DEFAULT 'firmato',\n      file_name TEXT,\n      notes TEXT,\n      created_at TEXT NOT NULL\n    );\n    CREATE TABLE IF NOT EXISTS discount_codes (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      code TEXT UNIQUE NOT NULL,\n      title TEXT NOT NULL,\n      discount_type TEXT NOT NULL DEFAULT 'percentuale',\n      value REAL NOT NULL DEFAULT 0,\n      valid_from TEXT,\n      valid_to TEXT,\n      active INTEGER NOT NULL DEFAULT 1,\n      notes TEXT,\n      created_at TEXT NOT NULL\n    );\n    CREATE TABLE IF NOT EXISTS promo_popups (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      title TEXT NOT NULL,\n      body TEXT,\n      button_text TEXT,\n      button_url TEXT,\n      image TEXT,\n      active INTEGER NOT NULL DEFAULT 0,\n      updated_at TEXT NOT NULL\n    );\n    CREATE TABLE IF NOT EXISTS email_templates (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      code TEXT UNIQUE NOT NULL,\n      name TEXT NOT NULL,\n      subject TEXT NOT NULL,\n      body TEXT,\n      button_text TEXT,\n      button_url TEXT,\n      active INTEGER NOT NULL DEFAULT 1,\n      updated_at TEXT NOT NULL\n    );\n    CREATE TABLE IF NOT EXISTS newsletter_subscribers (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      name TEXT,\n      email TEXT UNIQUE NOT NULL,\n      phone TEXT,\n      source TEXT DEFAULT 'Sito pubblico',\n      active INTEGER NOT NULL DEFAULT 1,\n      created_at TEXT NOT NULL\n    );\n    CREATE TABLE IF NOT EXISTS gallery_items (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      title TEXT NOT NULL,\n      image TEXT,\n      caption TEXT,\n      active INTEGER NOT NULL DEFAULT 1,\n      sort_order INTEGER NOT NULL DEFAULT 0,\n      created_at TEXT NOT NULL\n    );\n    CREATE TABLE IF NOT EXISTS game_masters (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      name TEXT NOT NULL,\n      phone TEXT,\n      role TEXT DEFAULT 'Game Master',\n      hourly_rate REAL DEFAULT 0,\n      active INTEGER NOT NULL DEFAULT 1,\n      notes TEXT,\n      created_at TEXT NOT NULL\n    );\n    CREATE TABLE IF NOT EXISTS stations (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      name TEXT NOT NULL,\n      station_type TEXT DEFAULT 'VR',\n      status TEXT DEFAULT 'libera',\n      hardware TEXT,\n      notes TEXT,\n      active INTEGER NOT NULL DEFAULT 1,\n      created_at TEXT NOT NULL\n    );\n    CREATE TABLE IF NOT EXISTS activity_logs (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      user_name TEXT,\n      action TEXT NOT NULL,\n      details TEXT,\n      created_at TEXT NOT NULL\n    );\n\n    CREATE TABLE IF NOT EXISTS fidelity_points_history (\n      id INTEGER PRIMARY KEY AUTOINCREMENT,\n      customer_id INTEGER NOT NULL,\n      change_amount INTEGER NOT NULL DEFAULT 0,\n      before_points INTEGER NOT NULL DEFAULT 0,\n      after_points INTEGER NOT NULL DEFAULT 0,\n      mode TEXT NOT NULL DEFAULT 'add',\n      motive TEXT,\n      operator TEXT,\n      created_at TEXT NOT NULL,\n      FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE\n    );\n"


def make_customer_code(existing=None):
    existing = existing or set()
    while True:
        code = "".join(secrets.choice(CUSTOMER_CODE_ALPHABET) for _ in range(6))
        if code not in existing:
            return code


def is_postgres():
    url = current_app.config.get('DATABASE_URL') or ''
    return url.startswith('postgres://') or url.startswith('postgresql://')


def _postgres_module():
    try:
        import psycopg
        from psycopg.rows import dict_row
        return psycopg, dict_row
    except Exception as exc:
        raise RuntimeError('DATABASE_URL è impostato ma manca psycopg. Installa requirements.txt oppure rimuovi DATABASE_URL per usare SQLite locale.') from exc


def _normalize_sql_for_postgres(sql):
    sql = sql.strip()
    sql = sql.replace("date(created_at)=date('now','localtime')", "DATE(created_at::timestamp)=CURRENT_DATE")
    sql = sql.replace("date(created_at) = date('now','localtime')", "DATE(created_at::timestamp)=CURRENT_DATE")
    sql = sql.replace("date(created_at)", "DATE(created_at::timestamp)")
    sql = sql.replace("strftime('%Y-%m', created_at)", "TO_CHAR(created_at::timestamp, 'YYYY-MM')")
    sql = sql.replace('?', '%s')
    return sql


def _schema_for_current_database():
    if not is_postgres():
        return SCHEMA_SQL
    return (SCHEMA_SQL
            .replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
            .replace('REAL', 'DOUBLE PRECISION'))


def get_db():
    if 'db' not in g:
        if current_app.config.get('DATABASE_URL'):
            psycopg, dict_row = _postgres_module()
            g.db = psycopg.connect(current_app.config['DATABASE_URL'], row_factory=dict_row)
        else:
            g.db = sqlite3.connect(current_app.config['DATABASE'])
            g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def query(sql, params=(), one=False):
    db = get_db()
    if is_postgres():
        sql = _normalize_sql_for_postgres(sql)
    cur = db.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def _insert_table_name(sql):
    """Return the target table for a simple INSERT statement, if present."""
    import re
    m = re.match(r"\s*INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, re.IGNORECASE)
    return m.group(1) if m else None


def execute(sql, params=()):
    db = get_db()
    wants_returning_id = False
    if is_postgres():
        sql = _normalize_sql_for_postgres(sql)
        table = _insert_table_name(sql)
        if table in ID_TABLES and ' returning ' not in f' {sql.lower()} ':
            sql = sql.rstrip().rstrip(';') + ' RETURNING id'
            wants_returning_id = True
    cur = db.execute(sql, params)
    last_id = None
    if wants_returning_id:
        row = cur.fetchone()
        if row:
            last_id = row['id'] if isinstance(row, dict) else row[0]
    else:
        last_id = getattr(cur, 'lastrowid', None)
    db.commit()
    cur.close()
    return last_id


def executemany(sql, seq_params):
    # sqlite3 has executemany() on the connection; psycopg v3 connections do not.
    # Looping through execute() keeps the same SQL-normalization and RETURNING handling
    # for both SQLite locale and PostgreSQL/Supabase online.
    params_list = list(seq_params)
    if not params_list:
        return
    if is_postgres():
        for params in params_list:
            execute(sql, params)
        return
    db = get_db()
    cur = db.executemany(sql, params_list)
    db.commit()
    cur.close()


def column_exists(table, column):
    if is_postgres():
        row = query("SELECT 1 AS ok FROM information_schema.columns WHERE table_schema='public' AND table_name=? AND column_name=?", (table, column), one=True)
        return row is not None
    rows = get_db().execute(f'PRAGMA table_info({table})').fetchall()
    return any(r['name'] == column for r in rows)


def table_count(table):
    row = query(f'SELECT COUNT(*) AS c FROM {table}', one=True)
    return int(row['c'] if row else 0)


def upsert_setting(key, value):
    if is_postgres():
        execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value', (key, value))
    else:
        execute('INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)', (key, value))


def insert_setting_default(key, value):
    if is_postgres():
        execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT (key) DO NOTHING', (key, value))
    else:
        execute('INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)', (key, value))


def reset_postgres_sequences():
    if not is_postgres():
        return
    db = get_db()
    for table in ID_TABLES:
        try:
            db.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1), true)")
        except Exception:
            pass
    db.commit()


def init_db():
    db = get_db()
    if is_postgres():
        for statement in _schema_for_current_database().split(';'):
            statement = statement.strip()
            if statement:
                db.execute(statement)
    else:
        db.executescript(_schema_for_current_database())
    db.commit()

    if not column_exists('customers', 'customer_code'):
        execute('ALTER TABLE customers ADD COLUMN customer_code TEXT')

    existing_codes = {r['customer_code'] for r in query("SELECT customer_code FROM customers WHERE customer_code IS NOT NULL AND customer_code != ''")}
    for r in query("SELECT id FROM customers WHERE customer_code IS NULL OR customer_code = ''"):
        code = make_customer_code(existing_codes)
        existing_codes.add(code)
        execute('UPDATE customers SET customer_code=? WHERE id=?', (code, r['id']))

    if not column_exists('games', 'cover'):
        execute('ALTER TABLE games ADD COLUMN cover TEXT')
    if not column_exists('games', 'trailer_url'):
        execute('ALTER TABLE games ADD COLUMN trailer_url TEXT')
    if not column_exists('games', 'age_rating'):
        execute("ALTER TABLE games ADD COLUMN age_rating TEXT DEFAULT '7+'")
    if not column_exists('games', 'difficulty'):
        execute("ALTER TABLE games ADD COLUMN difficulty TEXT DEFAULT 'Media'")
    if not column_exists('games', 'featured'):
        execute('ALTER TABLE games ADD COLUMN featured INTEGER NOT NULL DEFAULT 0')


def seed_if_empty():
    now = datetime.now().isoformat(timespec='seconds')
    admin_name = os.environ.get('ADMIN_NAME', 'Administrator')
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@arena.local').strip().lower()
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')

    if table_count('users') == 0:
        execute('INSERT INTO users(name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)',
                (admin_name, admin_email, generate_password_hash(admin_password), 'admin', now))

    if table_count('packages') == 0:
        packs = [('VR 30 minuti',30,12,'VR'),('VR 60 minuti',60,20,'VR'),('Console 30 minuti',30,5,'Console'),('Compleanno Base',120,120,'Evento')]
        executemany('INSERT INTO packages(name,minutes,price,type) VALUES (?,?,?,?)', packs)

    if table_count('games') == 0:
        games = [('Quantum Arena','VR','2-6',30,12,'Arena futuristica a squadre'),('Cyber Shot','VR','1-4',30,12,'Sparatutto arcade'),('Cops vs Robbers','VR','2-6',30,12,'Sfida multiplayer'),('PlayStation 5','Console','1-4',60,10,'Postazione console')]
        executemany('INSERT INTO games(title,category,players,duration,price,description) VALUES (?,?,?,?,?,?)', games)

    defaults = [('business_name','Game World Arena VR'),('business_kicker','GAME WORLD · VR EXPERIENCE'),('home_title','Vivi la realtà virtuale come non l’hai mai vista'),('home_subtitle','Arena VR, console, compleanni ed eventi privati con atmosfera neon dark fucsia.'),('booking_title','Prenota la tua esperienza VR'),('public_footer','Esperienze VR, console, compleanni ed eventi privati.'),('whatsapp_prefix','39'),('currency','€')]
    for k, v in defaults:
        insert_setting_default(k, v)

    if query('SELECT COUNT(*) AS c FROM media_assets WHERE filename=?', ('home_vr_dark_fucsia.png',), one=True)['c'] == 0:
        execute('INSERT INTO media_assets(filename,original_name,title,alt,created_at) VALUES (?,?,?,?,?)',
                ('home_vr_dark_fucsia.png','home_vr_dark_fucsia.png','Hero home VR dark fucsia','Arena VR futuristica con luci fucsia e giocatori in realtà virtuale',now))

    if table_count('email_templates') == 0:
        emails = [
            ('booking_request','Richiesta prenotazione','Abbiamo ricevuto la tua richiesta','Ciao {nome}, abbiamo ricevuto la tua richiesta per il giorno {data}. Ti ricontatteremo per confermare la disponibilità.','Vedi sito','/'),
            ('booking_confirmed','Prenotazione confermata','Prenotazione confermata','Ciao {nome}, la tua prenotazione è confermata. Ti aspettiamo in arena!','Apri mappa','/contatti'),
            ('birthday_info','Informazioni compleanno','Pacchetto compleanno VR','Ciao {nome}, ecco le informazioni per organizzare il compleanno in sala VR. Possiamo gestire sala, orari, note e acconto.','Prenota evento','/prenota'),
            ('newsletter','Newsletter promo','Nuova promo Arena VR','Abbiamo una nuova promozione per giochi VR, console ed eventi. Prenota la tua esperienza dark fucsia.','Scopri ora','/giochi')
        ]
        executemany('INSERT INTO email_templates(code,name,subject,body,button_text,button_url,updated_at) VALUES (?,?,?,?,?,?,?)', [(a,b,c,d,e,f,now) for a,b,c,d,e,f in emails])

    if table_count('discount_codes') == 0:
        execute('INSERT INTO discount_codes(code,title,discount_type,value,valid_from,valid_to,active,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                ('WELCOME10','Sconto benvenuto','percentuale',10,'','',1,'Promo iniziale modificabile dal pannello',now))

    if table_count('newsletter_subscribers') == 0:
        if is_postgres():
            execute('INSERT INTO newsletter_subscribers(name,email,phone,source,active,created_at) VALUES (?,?,?,?,?,?) ON CONFLICT (email) DO NOTHING',
                    ('Cliente Demo','demo@arena.local','', 'Demo pannello', 1, now))
        else:
            execute('INSERT OR IGNORE INTO newsletter_subscribers(name,email,phone,source,active,created_at) VALUES (?,?,?,?,?,?)',
                    ('Cliente Demo','demo@arena.local','', 'Demo pannello', 1, now))

    if table_count('promo_popups') == 0:
        execute('INSERT INTO promo_popups(title,body,button_text,button_url,image,active,updated_at) VALUES (?,?,?,?,?,?,?)',
                ('Promo Dark Fucsia','Prenota una sessione VR o una festa privata e scopri le offerte disponibili.','Prenota ora','/prenota',None,0,now))

    if table_count('stations') == 0:
        stations = [
            ('Arena VR 1','VR','libera','Meta Quest / PC VR','Postazione principale'),
            ('Arena VR 2','VR','libera','Meta Quest / PC VR','Postazione secondaria'),
            ('Console 1','Console','libera','PlayStation 5 + TV','Postazione console')
        ]
        executemany('INSERT INTO stations(name,station_type,status,hardware,notes,created_at) VALUES (?,?,?,?,?,?)', [(a,b,c,d,e,now) for a,b,c,d,e in stations])

    if table_count('game_masters') == 0:
        masters = [('Salvo','', 'Admin / Game Master', 0, 1, 'Account demo'),('Operatore Demo','', 'Game Master', 0, 1, 'Modificabile dal pannello')]
        executemany('INSERT INTO game_masters(name,phone,role,hourly_rate,active,notes,created_at) VALUES (?,?,?,?,?,?,?)', [(a,b,c,d,e,f,now) for a,b,c,d,e,f in masters])

    if table_count('gallery_items') == 0:
        execute('INSERT INTO gallery_items(title,image,caption,active,sort_order,created_at) VALUES (?,?,?,?,?,?)',
                ('Arena VR dark fucsia','home_vr_dark_fucsia.png','Immagine hero della home',1,1,now))

    if table_count('site_pages') == 0:
        pages = [
            ('home','Home','Arena VR Dark Fucsia','Entra in un’esperienza immersiva con giochi VR, console, compleanni ed eventi privati.','home_vr_dark_fucsia.png','La home page principale della sala VR',1,1,1,now),
            ('giochi','Giochi','Giochi e arene','Scegli l’esperienza più adatta: sparatutto, cooperativi, console e sfide multiplayer.',None,'Catalogo giochi VR e console',1,1,2,now),
            ('compleanni','Compleanni','Compleanni ed eventi','Organizza feste, compleanni e serate private con arena VR, console e pacchetti personalizzati.',None,'Eventi e feste private',1,1,3,now),
            ('prenota','Prenota','Prenota la tua esperienza','Invia una richiesta di prenotazione. La conferma viene gestita dal pannello amministratore.',None,'Richiesta prenotazione online',1,1,4,now),
            ('contatti','Contatti','Contatti e informazioni','Scrivici per disponibilità, compleanni, eventi privati e informazioni sui pacchetti.',None,'Contatti sala VR',1,1,5,now),
            ('gallery','Gallery','Gallery','Guarda alcune immagini della sala, degli eventi e dell’esperienza VR.',None,'Gallery sala VR',1,1,6,now),
            ('fidelity','Fidelity','Fidelity Card','Controlla i punti della tua fidelity card con codice, telefono o email.',None,'Fidelity card Game World Arena VR',1,1,7,now)
        ]
        executemany('INSERT INTO site_pages(slug,nav_label,title,subtitle,hero_image,meta_description,show_in_menu,active,sort_order,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)', pages)
        page_ids = {r['slug']: r['id'] for r in query('SELECT id,slug FROM site_pages')}
        sections = [
            (page_ids['home'],'hero','NEON VR ARENA','Esperienza VR immersiva','Gioca con amici, festeggia compleanni e crea sfide multiplayer in una sala dark fucsia ad alto impatto.',None,'Prenota ora','/prenota',1,1,now),
            (page_ids['home'],'cards','COSA PUOI FARE','Arena VR, console ed eventi','Gestisci partite, feste, compleanni e pacchetti personalizzati. Ogni blocco del sito è modificabile dal pannello.',None,'Scopri i giochi','/giochi',2,1,now),
            (page_ids['giochi'],'text_image','CATALOGO','Giochi sempre aggiornati','Dal pannello puoi aggiungere giochi, copertine, descrizioni, prezzi e durata.',None,None,None,1,1,now),
            (page_ids['compleanni'],'text_image','EVENTI','Compleanni senza pensieri','Crea pacchetti, blocca fasce orarie e gestisci acconti, note e catering.',None,'Richiedi evento','/prenota',1,1,now),
            (page_ids['contatti'],'text','DOVE SIAMO','Contattaci','Inserisci qui indirizzo, telefono, WhatsApp, orari e link social.',None,None,None,1,1,now)
        ]
        executemany('INSERT INTO site_sections(page_id,section_type,kicker,title,body,image,button_text,button_url,sort_order,active,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)', sections)
