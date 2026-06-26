from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app, send_file
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime, timedelta, date
from pathlib import Path
import uuid
import secrets
import io
import json
import zipfile
from .db import query, execute, get_db, BACKUP_TABLES, ID_TABLES, is_postgres, reset_postgres_sequences, upsert_setting

bp = Blueprint('main', __name__)
ALLOWED_EXT = {'png','jpg','jpeg','webp','gif'}

CUSTOMER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

def generate_customer_code():
    while True:
        code = ''.join(secrets.choice(CUSTOMER_CODE_ALPHABET) for _ in range(6))
        existing = query('SELECT id FROM customers WHERE customer_code=?', (code,), one=True)
        if not existing:
            return code



def get_settings_dict():
    rows = query('SELECT key,value FROM settings')
    return {r['key']: r['value'] for r in rows}


def get_menu_pages():
    return query('SELECT * FROM site_pages WHERE active=1 AND show_in_menu=1 ORDER BY sort_order, id')


def upload_file(field='image'):
    f = request.files.get(field)
    if not f or not f.filename:
        return None
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_EXT:
        flash('Formato immagine non supportato. Usa JPG, PNG, WEBP o GIF.')
        return None
    safe = secure_filename(f.filename)
    filename = f'{datetime.now().strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:8]}_{safe}'
    upload_dir = Path(current_app.root_path) / 'static' / 'uploads'
    upload_dir.mkdir(parents=True, exist_ok=True)
    f.save(upload_dir / filename)
    execute('INSERT INTO media_assets(filename,original_name,title,alt,created_at) VALUES (?,?,?,?,?)',
            (filename, f.filename, request.form.get('media_title') or f.filename, request.form.get('media_alt') or '', datetime.now().isoformat(timespec='seconds')))
    return filename


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('main.login'))
        return fn(*args, **kwargs)
    return wrapper


@bp.app_context_processor
def inject_globals():
    return dict(menu_pages=get_menu_pages, settings=get_settings_dict, active_popup=lambda: query('SELECT * FROM promo_popups WHERE active=1 ORDER BY id DESC LIMIT 1', one=True))


@bp.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email','').strip().lower()
        password = request.form.get('password','')
        user = query('SELECT * FROM users WHERE email=?', (email,), one=True)
        if user and check_password_hash(user['password_hash'], password):
            session.permanent = True
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['role'] = user['role']
            return redirect(url_for('main.dashboard'))
        flash('Accesso non valido')
    return render_template('login.html')


@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.login'))


def render_public_page(slug):
    st = get_settings_dict()
    page = query('SELECT * FROM site_pages WHERE slug=? AND active=1', (slug,), one=True)
    if not page:
        return render_template('public_404.html', st=st), 404
    sections = query('SELECT * FROM site_sections WHERE page_id=? AND active=1 ORDER BY sort_order,id', (page['id'],))
    games = query('SELECT * FROM games WHERE active=1 ORDER BY featured DESC, category,title') if slug in ['home','giochi'] else []
    packs = query('SELECT * FROM packages WHERE active=1 ORDER BY type, price') if slug in ['home','prenota','compleanni'] else []
    gallery = query('SELECT * FROM gallery_items WHERE active=1 ORDER BY sort_order,id DESC LIMIT 8') if slug in ['home','compleanni','contatti'] else []
    return render_template('public_page.html', st=st, page=page, sections=sections, games=games, packs=packs, gallery=gallery)


@bp.route('/')
def public_home():
    return render_public_page('home')


@bp.route('/giochi')
def public_games():
    return render_public_page('giochi')


@bp.route('/compleanni')
def public_events():
    return render_public_page('compleanni')


@bp.route('/contatti')
def public_contacts():
    return render_public_page('contatti')




@bp.route('/gallery')
def public_gallery():
    st = get_settings_dict()
    page = query('SELECT * FROM site_pages WHERE slug=? AND active=1', ('gallery',), one=True)
    rows = query('SELECT * FROM gallery_items WHERE active=1 ORDER BY sort_order,id DESC')
    return render_template('public_gallery.html', st=st, page=page, rows=rows)


@bp.route('/fidelity', methods=['GET','POST'])
def public_fidelity():
    st = get_settings_dict()
    page = query('SELECT * FROM site_pages WHERE slug=? AND active=1', ('fidelity',), one=True)
    customer = None
    searched = False
    q = ''
    if request.method == 'POST':
        searched = True
        q = (request.form.get('search') or '').strip()
        if q:
            customer = query("""SELECT * FROM customers
                                WHERE phone=? OR email=? OR lower(name)=lower(?) OR upper(customer_code)=upper(?)
                                ORDER BY id DESC LIMIT 1""", (q, q, q, q), one=True)
    return render_template('public_fidelity.html', st=st, page=page, customer=customer, searched=searched, q=q)

@bp.route('/pagina/<slug>')
def public_custom_page(slug):
    return render_public_page(slug)


@bp.route('/prenota', methods=['GET','POST'])
def public_booking():
    st = get_settings_dict()
    page = query('SELECT * FROM site_pages WHERE slug=? AND active=1', ('prenota',), one=True)
    sections = query('SELECT * FROM site_sections WHERE page_id=? AND active=1 ORDER BY sort_order,id', (page['id'],)) if page else []
    games = query('SELECT * FROM games WHERE active=1 ORDER BY title')
    packs = query('SELECT * FROM packages WHERE active=1 ORDER BY type, price')

    def _time_add_minutes(value, minutes):
        try:
            h, m = [int(x) for x in (value or '00:00').split(':')[:2]]
            base = datetime(2000, 1, 1, h, m)
            return (base + timedelta(minutes=int(minutes or 30))).strftime('%H:%M')
        except Exception:
            return value or ''

    if request.method == 'POST':
        data = request.form
        people = int(data.get('people') or 1)
        duration = int(data.get('duration') or 30)
        start_time = data.get('start_time') or ''
        end_time = data.get('end_time') or _time_add_minutes(start_time, duration)
        total = float(data.get('total') or 0)
        email = (data.get('email') or '').strip()
        mode = data.get('booking_mode') or 'Nuova partita'
        promo = (data.get('promo_code') or '').strip()
        raw_notes = (data.get('notes') or '').strip()
        notes_parts = [f'Tipo prenotazione: {mode}', f'Durata: {duration} minuti']
        if email:
            notes_parts.append(f'Email: {email}')
        if promo:
            notes_parts.append(f'Codice promo: {promo}')
        if raw_notes:
            notes_parts.append(raw_notes)
        notes = ' | '.join(notes_parts)
        execute('INSERT INTO bookings(customer_name,phone,booking_date,start_time,end_time,service,status,people,deposit,total,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (data.get('customer_name'), data.get('phone'), data.get('booking_date'), start_time, end_time,
                 data.get('service'), 'draft', people, 0, total, notes, datetime.now().isoformat(timespec='seconds')))
        flash('Richiesta inviata. Ti ricontatteremo per confermare la prenotazione.')
        return redirect(url_for('main.public_booking'))

    today = date.today().isoformat()
    booking_rows = query("SELECT id, customer_name, booking_date, start_time, end_time, service, status, people, total FROM bookings WHERE booking_date>=? AND status!='cancelled' ORDER BY booking_date,start_time", (today,))
    games_payload = []
    for g in games:
        games_payload.append({
            'id': g['id'],
            'title': g['title'],
            'category': g['category'],
            'players': g['players'],
            'duration': int(g['duration'] or 30),
            'price': float(g['price'] or 0),
            'description': g['description'] or '',
            'cover': g['cover'] or ''
        })
    bookings_payload = []
    for b in booking_rows:
        bookings_payload.append({
            'id': b['id'],
            'customer_name': b['customer_name'],
            'booking_date': b['booking_date'],
            'start_time': b['start_time'],
            'end_time': b['end_time'],
            'service': b['service'],
            'status': b['status'],
            'people': int(b['people'] or 1),
            'total': float(b['total'] or 0)
        })
    return render_template('public_booking.html', st=st, page=page, sections=sections, games=games, packs=packs, games_payload=games_payload, bookings_payload=bookings_payload)


@bp.route('/admin')
@login_required
def dashboard():
    today = date.today().isoformat()
    users = query('SELECT COUNT(*) c FROM users', one=True)['c']
    customers = query('SELECT COUNT(*) c FROM customers', one=True)['c']
    bookings_today = query('SELECT COUNT(*) c FROM bookings WHERE booking_date=?', (today,), one=True)['c']
    sessions_running = query("SELECT COUNT(*) c FROM sessions WHERE status='running'", one=True)['c']
    pages_count = query('SELECT COUNT(*) c FROM site_pages', one=True)['c']
    sections_count = query('SELECT COUNT(*) c FROM site_sections', one=True)['c']
    income_today = query("SELECT COALESCE(SUM(amount),0) c FROM cash_movements WHERE kind='incasso' AND date(created_at)=date('now','localtime')", one=True)['c']
    out_today = query("SELECT COALESCE(SUM(amount),0) c FROM cash_movements WHERE kind!='incasso' AND date(created_at)=date('now','localtime')", one=True)['c']
    upcoming = query('SELECT * FROM bookings WHERE booking_date>=? ORDER BY booking_date,start_time LIMIT 8', (today,))
    running = query("SELECT * FROM sessions WHERE status='running' ORDER BY end_at ASC")
    return render_template('dashboard.html', users=users, customers=customers, bookings_today=bookings_today, sessions_running=sessions_running, income_today=income_today, out_today=out_today, upcoming=upcoming, running=running, pages_count=pages_count, sections_count=sections_count)


@bp.route('/cms')
@login_required
def cms_pages():
    rows = query('SELECT p.*, (SELECT COUNT(*) FROM site_sections s WHERE s.page_id=p.id) sections_count FROM site_pages p ORDER BY sort_order,id')
    return render_template('cms_pages.html', rows=rows)


@bp.route('/cms/page/new', methods=['GET','POST'])
@login_required
def cms_page_new():
    if request.method == 'POST':
        data = request.form
        hero = upload_file('hero_image')
        slug = data.get('slug','').strip().lower().replace(' ','-')
        execute('''INSERT INTO site_pages(slug,nav_label,title,subtitle,hero_image,meta_description,show_in_menu,active,sort_order,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (slug, data.get('nav_label'), data.get('title'), data.get('subtitle'), hero, data.get('meta_description'), 1 if data.get('show_in_menu') else 0, 1 if data.get('active') else 0, data.get('sort_order') or 0, datetime.now().isoformat(timespec='seconds')))
        flash('Pagina creata')
        return redirect(url_for('main.cms_pages'))
    return render_template('cms_page_form.html', page=None)


@bp.route('/cms/page/<int:id>', methods=['GET','POST'])
@login_required
def cms_page_edit(id):
    page = query('SELECT * FROM site_pages WHERE id=?', (id,), one=True)
    if not page:
        flash('Pagina non trovata')
        return redirect(url_for('main.cms_pages'))
    if request.method == 'POST':
        data = request.form
        hero = upload_file('hero_image') or page['hero_image']
        slug = data.get('slug','').strip().lower().replace(' ','-')
        execute('''UPDATE site_pages SET slug=?, nav_label=?, title=?, subtitle=?, hero_image=?, meta_description=?, show_in_menu=?, active=?, sort_order=?, updated_at=? WHERE id=?''',
                (slug, data.get('nav_label'), data.get('title'), data.get('subtitle'), hero, data.get('meta_description'), 1 if data.get('show_in_menu') else 0, 1 if data.get('active') else 0, data.get('sort_order') or 0, datetime.now().isoformat(timespec='seconds'), id))
        flash('Pagina aggiornata')
        return redirect(url_for('main.cms_page_edit', id=id))
    sections = query('SELECT * FROM site_sections WHERE page_id=? ORDER BY sort_order,id', (id,))
    return render_template('cms_page_form.html', page=page, sections=sections)


@bp.route('/cms/page/<int:id>/delete', methods=['POST'])
@login_required
def cms_page_delete(id):
    execute('DELETE FROM site_sections WHERE page_id=?', (id,))
    execute('DELETE FROM site_pages WHERE id=?', (id,))
    flash('Pagina eliminata')
    return redirect(url_for('main.cms_pages'))


@bp.route('/cms/section/new/<int:page_id>', methods=['GET','POST'])
@login_required
def cms_section_new(page_id):
    page = query('SELECT * FROM site_pages WHERE id=?', (page_id,), one=True)
    if request.method == 'POST':
        data = request.form
        image = upload_file('image')
        execute('''INSERT INTO site_sections(page_id,section_type,kicker,title,body,image,button_text,button_url,sort_order,active,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (page_id, data.get('section_type'), data.get('kicker'), data.get('title'), data.get('body'), image, data.get('button_text'), data.get('button_url'), data.get('sort_order') or 0, 1 if data.get('active') else 0, datetime.now().isoformat(timespec='seconds')))
        flash('Sezione aggiunta')
        return redirect(url_for('main.cms_page_edit', id=page_id))
    return render_template('cms_section_form.html', section=None, page=page)


@bp.route('/cms/section/<int:id>', methods=['GET','POST'])
@login_required
def cms_section_edit(id):
    section = query('SELECT * FROM site_sections WHERE id=?', (id,), one=True)
    if not section:
        flash('Sezione non trovata')
        return redirect(url_for('main.cms_pages'))
    page = query('SELECT * FROM site_pages WHERE id=?', (section['page_id'],), one=True)
    if request.method == 'POST':
        data = request.form
        image = upload_file('image') or section['image']
        execute('''UPDATE site_sections SET section_type=?, kicker=?, title=?, body=?, image=?, button_text=?, button_url=?, sort_order=?, active=?, updated_at=? WHERE id=?''',
                (data.get('section_type'), data.get('kicker'), data.get('title'), data.get('body'), image, data.get('button_text'), data.get('button_url'), data.get('sort_order') or 0, 1 if data.get('active') else 0, datetime.now().isoformat(timespec='seconds'), id))
        flash('Sezione aggiornata')
        return redirect(url_for('main.cms_page_edit', id=section['page_id']))
    return render_template('cms_section_form.html', section=section, page=page)


@bp.route('/cms/section/<int:id>/delete', methods=['POST'])
@login_required
def cms_section_delete(id):
    sec = query('SELECT page_id FROM site_sections WHERE id=?', (id,), one=True)
    execute('DELETE FROM site_sections WHERE id=?', (id,))
    flash('Sezione eliminata')
    return redirect(url_for('main.cms_page_edit', id=sec['page_id'] if sec else 1))


@bp.route('/admin/editor-home', methods=['GET','POST'])
@login_required
def editor_home():
    page = query('SELECT * FROM site_pages WHERE slug=?', ('home',), one=True)
    if not page:
        now = datetime.now().isoformat(timespec='seconds')
        pid = execute('INSERT INTO site_pages(slug,nav_label,title,subtitle,meta_description,show_in_menu,active,sort_order,updated_at) VALUES (?,?,?,?,?,?,?,?,?)', ('home','Home','Home','', 'Home page', 1, 1, 1, now))
        page = query('SELECT * FROM site_pages WHERE id=?', (pid,), one=True)
    if request.method == 'POST':
        data = request.form
        hero = upload_file('hero_image') or page['hero_image']
        execute('UPDATE site_pages SET nav_label=?, title=?, subtitle=?, hero_image=?, meta_description=?, show_in_menu=?, active=?, sort_order=?, updated_at=? WHERE id=?',
                (data.get('nav_label'), data.get('title'), data.get('subtitle'), hero, data.get('meta_description'), 1 if data.get('show_in_menu') else 0, 1 if data.get('active') else 0, data.get('sort_order') or 1, datetime.now().isoformat(timespec='seconds'), page['id']))
        flash('Home aggiornata')
        return redirect(url_for('main.editor_home'))
    sections = query('SELECT * FROM site_sections WHERE page_id=? ORDER BY sort_order,id', (page['id'],))
    return render_template('editor_home.html', page=page, sections=sections)


@bp.route('/admin/pagine-giochi', methods=['GET','POST'])
@login_required
def pagine_giochi():
    page = query('SELECT * FROM site_pages WHERE slug=?', ('giochi',), one=True)
    if not page:
        now = datetime.now().isoformat(timespec='seconds')
        pid = execute('INSERT INTO site_pages(slug,nav_label,title,subtitle,meta_description,show_in_menu,active,sort_order,updated_at) VALUES (?,?,?,?,?,?,?,?,?)', ('giochi','Giochi','Giochi','', 'Pagina giochi', 1, 1, 2, now))
        page = query('SELECT * FROM site_pages WHERE id=?', (pid,), one=True)
    if request.method == 'POST':
        action = request.form.get('action')
        data = request.form
        if action == 'page':
            hero = upload_file('hero_image') or page['hero_image']
            execute('UPDATE site_pages SET nav_label=?, title=?, subtitle=?, hero_image=?, meta_description=?, show_in_menu=?, active=?, sort_order=?, updated_at=? WHERE id=?',
                    (data.get('nav_label'), data.get('title'), data.get('subtitle'), hero, data.get('meta_description'), 1 if data.get('show_in_menu') else 0, 1 if data.get('active') else 0, data.get('sort_order') or 2, datetime.now().isoformat(timespec='seconds'), page['id']))
            flash('Pagina giochi aggiornata')
        elif action == 'game':
            cover = upload_file('cover')
            execute('INSERT INTO games(title,category,players,duration,price,description,cover,trailer_url,age_rating,difficulty,featured,active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (data.get('title'), data.get('category'), data.get('players'), data.get('duration') or 30, data.get('price') or 0, data.get('description'), cover, data.get('trailer_url'), data.get('age_rating') or '7+', data.get('difficulty') or 'Media', 1 if data.get('featured') else 0, 1 if data.get('active') else 0))
            flash('Gioco aggiunto')
        return redirect(url_for('main.pagine_giochi'))
    sections = query('SELECT * FROM site_sections WHERE page_id=? ORDER BY sort_order,id', (page['id'],))
    games = query('SELECT * FROM games ORDER BY category,title')
    return render_template('pagine_giochi.html', page=page, sections=sections, games=games)


@bp.route('/admin/editor-email', methods=['GET','POST'])
@login_required
def editor_email():
    if request.method == 'POST':
        data = request.form
        now = datetime.now().isoformat(timespec='seconds')
        template_id = data.get('template_id')
        if template_id:
            execute('UPDATE email_templates SET name=?, subject=?, body=?, button_text=?, button_url=?, active=?, updated_at=? WHERE id=?',
                    (data.get('name'), data.get('subject'), data.get('body'), data.get('button_text'), data.get('button_url'), 1 if data.get('active') else 0, now, template_id))
            flash('Template email aggiornato')
        else:
            code = data.get('code','').strip().lower().replace(' ','_') or 'email_' + uuid.uuid4().hex[:6]
            execute('INSERT INTO email_templates(code,name,subject,body,button_text,button_url,active,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                    (code, data.get('name'), data.get('subject'), data.get('body'), data.get('button_text'), data.get('button_url'), 1 if data.get('active') else 0, now))
            flash('Template email creato')
        return redirect(url_for('main.editor_email'))
    selected_id = request.args.get('id')
    rows = query('SELECT * FROM email_templates ORDER BY id')
    selected = query('SELECT * FROM email_templates WHERE id=?', (selected_id,), one=True) if selected_id else (rows[0] if rows else None)
    return render_template('editor_email.html', rows=rows, selected=selected)


@bp.route('/media', methods=['GET','POST'])
@login_required
def media():
    if request.method == 'POST':
        upload_file('image')
        return redirect(url_for('main.media'))
    rows = query('SELECT * FROM media_assets ORDER BY created_at DESC')
    return render_template('media.html', rows=rows)


@bp.route('/bookings', methods=['GET','POST'])
@login_required
def bookings():
    if request.method == 'POST':
        data = request.form
        now = datetime.now().isoformat(timespec='seconds')
        execute('''INSERT INTO bookings(customer_name,phone,booking_date,start_time,end_time,service,status,people,deposit,total,notes,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                (data.get('customer_name'), data.get('phone'), data.get('booking_date'), data.get('start_time'), data.get('end_time'), data.get('service'), data.get('status','confirmed'), data.get('people') or 1, data.get('deposit') or 0, data.get('total') or 0, data.get('notes'), now))
        flash('Prenotazione salvata')
        return redirect(url_for('main.bookings'))
    rows = query('SELECT * FROM bookings ORDER BY booking_date DESC,start_time DESC LIMIT 100')
    return render_template('bookings.html', rows=rows)


@bp.route('/bookings/<int:booking_id>/update', methods=['POST'])
@login_required
def update_booking(booking_id):
    data = request.form
    execute('''UPDATE bookings
               SET customer_name=?, phone=?, booking_date=?, start_time=?, end_time=?, service=?,
                   status=?, people=?, deposit=?, total=?, notes=?
               WHERE id=?''',
            (data.get('customer_name'), data.get('phone'), data.get('booking_date'), data.get('start_time'),
             data.get('end_time'), data.get('service'), data.get('status','draft'), data.get('people') or 1,
             data.get('deposit') or 0, data.get('total') or 0, data.get('notes'), booking_id))
    flash('Prenotazione aggiornata')
    return redirect(url_for('main.bookings'))


@bp.route('/sessions', methods=['GET','POST'])
@login_required
def sessions_page():
    if request.method == 'POST':
        data = request.form
        minutes = int(data.get('minutes') or 30)
        start = datetime.now()
        end = start + timedelta(minutes=minutes)
        now = start.isoformat(timespec='seconds')
        execute('''INSERT INTO sessions(customer_name,station,game_title,package_name,start_at,end_at,status,amount,paid_method,notes,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (data.get('customer_name'), data.get('station'), data.get('game_title'), data.get('package_name'), start.isoformat(timespec='seconds'), end.isoformat(timespec='seconds'), 'running', data.get('amount') or 0, data.get('paid_method'), data.get('notes'), now))
        if float(data.get('amount') or 0) > 0:
            execute('INSERT INTO cash_movements(kind,description,amount,method,created_at) VALUES (?,?,?,?,?)', ('incasso', 'Sessione ' + data.get('customer_name',''), float(data.get('amount') or 0), data.get('paid_method'), now))
        return redirect(url_for('main.sessions_page'))
    rows = query('SELECT * FROM sessions ORDER BY created_at DESC LIMIT 100')
    games = query('SELECT * FROM games WHERE active=1 ORDER BY title')
    packs = query('SELECT * FROM packages WHERE active=1 ORDER BY type,name')
    return render_template('sessions.html', rows=rows, games=games, packs=packs)


@bp.route('/sessions/<int:id>/close', methods=['POST'])
@login_required
def close_session(id):
    execute("UPDATE sessions SET status='closed' WHERE id=?", (id,))
    return redirect(url_for('main.sessions_page'))


@bp.route('/cash', methods=['GET','POST'])
@login_required
def cash():
    if request.method == 'POST':
        data = request.form
        execute('INSERT INTO cash_movements(kind,description,amount,method,created_at) VALUES (?,?,?,?,?)',
                (data.get('kind'), data.get('description'), data.get('amount') or 0, data.get('method'), datetime.now().isoformat(timespec='seconds')))
        return redirect(url_for('main.cash'))
    rows = query('SELECT * FROM cash_movements ORDER BY created_at DESC LIMIT 150')
    income = query("SELECT COALESCE(SUM(amount),0) c FROM cash_movements WHERE kind='incasso'", one=True)['c']
    expense = query("SELECT COALESCE(SUM(amount),0) c FROM cash_movements WHERE kind!='incasso'", one=True)['c']
    return render_template('cash.html', rows=rows, income=income, expense=expense)


@bp.route('/customers', methods=['GET','POST'])
@login_required
def customers():
    if request.method == 'POST':
        data = request.form
        action = data.get('action')
        customer_id = data.get('customer_id')

        if action == 'update_customer':
            execute('''UPDATE customers
                       SET name=?, phone=?, email=?, birthday=?, notes=?, points=?
                       WHERE id=?''',
                    (data.get('name'), data.get('phone'), data.get('email'), data.get('birthday'),
                     data.get('notes') or '', data.get('points') or 0, customer_id))
            flash('Dati cliente aggiornati')
            return redirect(url_for('main.customers', q=request.args.get('q','')))

        if action == 'delete_customer':
            customer = query('SELECT * FROM customers WHERE id=?', (customer_id,), one=True)
            if customer:
                execute('UPDATE bookings SET customer_id=NULL WHERE customer_id=?', (customer_id,))
                execute('UPDATE sessions SET customer_id=NULL WHERE customer_id=?', (customer_id,))
                execute('DELETE FROM fidelity_points_history WHERE customer_id=?', (customer_id,))
                execute('DELETE FROM customers WHERE id=?', (customer_id,))
                flash('Cliente eliminato')
            else:
                flash('Cliente non trovato')
            return redirect(url_for('main.customers', q=request.args.get('q','')))

        execute('INSERT INTO customers(customer_code,name,phone,email,birthday,notes,points,created_at) VALUES (?,?,?,?,?,?,?,?)',
                (generate_customer_code(), data.get('name'), data.get('phone'), data.get('email'), data.get('birthday'),
                 data.get('notes') or '', data.get('points') or 0, datetime.now().isoformat(timespec='seconds')))
        flash('Cliente salvato')
        return redirect(url_for('main.customers'))

    search = request.args.get('q','').strip()
    if search:
        like = f'%{search}%'
        rows = query('SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? OR email LIKE ? OR customer_code LIKE ? ORDER BY name', (like, like, like, like))
    else:
        rows = query('SELECT * FROM customers ORDER BY created_at DESC LIMIT 100')
    return render_template('customers.html', rows=rows, search=search)


@bp.route('/games', methods=['GET','POST'])
@login_required
def games():
    if request.method == 'POST':
        data = request.form
        cover = upload_file('cover')
        execute('INSERT INTO games(title,category,players,duration,price,description,cover,trailer_url,age_rating,difficulty,featured,active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (data.get('title'), data.get('category'), data.get('players'), data.get('duration') or 30, data.get('price') or 0, data.get('description'), cover, data.get('trailer_url'), data.get('age_rating') or '7+', data.get('difficulty') or 'Media', 1 if data.get('featured') else 0, 1 if data.get('active') else 0))
        return redirect(url_for('main.games'))
    rows = query('SELECT * FROM games ORDER BY category,title')
    return render_template('games.html', rows=rows)


@bp.route('/events', methods=['GET','POST'])
@login_required
def events():
    if request.method == 'POST':
        data = request.form
        execute('''INSERT INTO events(title,event_date,start_time,end_time,customer_name,phone,status,people,catering,total,notes,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                (data.get('title'), data.get('event_date'), data.get('start_time'), data.get('end_time'), data.get('customer_name'), data.get('phone'), data.get('status'), data.get('people') or 1, data.get('catering'), data.get('total') or 0, data.get('notes'), datetime.now().isoformat(timespec='seconds')))
        return redirect(url_for('main.events'))
    rows = query('SELECT * FROM events ORDER BY event_date DESC,start_time DESC LIMIT 100')
    return render_template('events.html', rows=rows)


@bp.route('/analytics')
@login_required
def analytics():
    days = query("""
    SELECT date(created_at) day,
           SUM(CASE WHEN kind='incasso' THEN amount ELSE 0 END) income,
           SUM(CASE WHEN kind!='incasso' THEN amount ELSE 0 END) expenses
    FROM cash_movements GROUP BY date(created_at) ORDER BY day DESC LIMIT 14
    """)
    return render_template('analytics.html', days=days)



@bp.route('/admin/moduli-firmati', methods=['GET','POST'])
@login_required
def signed_modules():
    if request.method == 'POST':
        data = request.form
        file_name = upload_file('file')
        execute("""INSERT INTO signed_modules(customer_name,phone,module_type,status,file_name,notes,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (data.get('customer_name'), data.get('phone'), data.get('module_type') or 'Liberatoria VR', data.get('status') or 'firmato', file_name, data.get('notes'), datetime.now().isoformat(timespec='seconds')))
        flash('Modulo firmato salvato')
        return redirect(url_for('main.signed_modules'))
    rows = query('SELECT * FROM signed_modules ORDER BY created_at DESC LIMIT 150')
    return render_template('signed_modules.html', rows=rows)


@bp.route('/admin/moduli-firmati/<int:id>/delete', methods=['POST'])
@login_required
def signed_module_delete(id):
    execute('DELETE FROM signed_modules WHERE id=?', (id,))
    flash('Modulo eliminato')
    return redirect(url_for('main.signed_modules'))


@bp.route('/admin/codici-sconto', methods=['GET','POST'])
@login_required
def discounts():
    if request.method == 'POST':
        data = request.form
        execute("""INSERT INTO discount_codes(code,title,discount_type,value,valid_from,valid_to,active,notes,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                ((data.get('code') or '').upper().replace(' ',''), data.get('title'), data.get('discount_type'), data.get('value') or 0, data.get('valid_from'), data.get('valid_to'), 1 if data.get('active') else 0, data.get('notes'), datetime.now().isoformat(timespec='seconds')))
        flash('Codice sconto creato')
        return redirect(url_for('main.discounts'))
    rows = query('SELECT * FROM discount_codes ORDER BY active DESC, id DESC')
    return render_template('discounts.html', rows=rows)


@bp.route('/admin/codici-sconto/<int:id>/toggle', methods=['POST'])
@login_required
def discount_toggle(id):
    execute('UPDATE discount_codes SET active=CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?', (id,))
    return redirect(url_for('main.discounts'))


@bp.route('/admin/codici-sconto/<int:id>/delete', methods=['POST'])
@login_required
def discount_delete(id):
    execute('DELETE FROM discount_codes WHERE id=?', (id,))
    flash('Codice eliminato')
    return redirect(url_for('main.discounts'))


@bp.route('/admin/popup-promozionale', methods=['GET','POST'])
@login_required
def popup_promo():
    popup = query('SELECT * FROM promo_popups ORDER BY id DESC LIMIT 1', one=True)
    if request.method == 'POST':
        data = request.form
        image = upload_file('image') or (popup['image'] if popup else None)
        now = datetime.now().isoformat(timespec='seconds')
        if popup:
            execute('UPDATE promo_popups SET title=?, body=?, button_text=?, button_url=?, image=?, active=?, updated_at=? WHERE id=?',
                    (data.get('title'), data.get('body'), data.get('button_text'), data.get('button_url'), image, 1 if data.get('active') else 0, now, popup['id']))
        else:
            execute('INSERT INTO promo_popups(title,body,button_text,button_url,image,active,updated_at) VALUES (?,?,?,?,?,?,?)',
                    (data.get('title'), data.get('body'), data.get('button_text'), data.get('button_url'), image, 1 if data.get('active') else 0, now))
        flash('Popup promozionale aggiornato')
        return redirect(url_for('main.popup_promo'))
    return render_template('popup_promo.html', popup=popup)


@bp.route('/admin/utenti-accessi', methods=['GET','POST'])
@login_required
def users_access():
    if request.method == 'POST':
        data = request.form
        name = data.get('name','').strip()
        email = data.get('email','').strip().lower()
        password = data.get('password','').strip()
        role = data.get('role','operator')
        if not name or not email or not password:
            flash('Compila nome, email e password.')
            return redirect(url_for('main.users_access'))
        try:
            execute('INSERT INTO users(name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)',
                    (name, email, generate_password_hash(password), role, datetime.now().isoformat(timespec='seconds')))
            flash('Utente creato')
        except Exception:
            flash('Email già presente o dati non validi')
        return redirect(url_for('main.users_access'))
    rows = query('SELECT id,name,email,role,created_at FROM users ORDER BY role,name')
    return render_template('users_access.html', rows=rows)


@bp.route('/admin/utenti-accessi/<int:id>/delete', methods=['POST'])
@login_required
def users_access_delete(id):
    if id == session.get('user_id'):
        flash('Non puoi eliminare il tuo utente mentre sei collegato.')
    else:
        execute('DELETE FROM users WHERE id=?', (id,))
        flash('Utente eliminato')
    return redirect(url_for('main.users_access'))



@bp.route('/admin/cambia-password', methods=['GET','POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current = request.form.get('current_password','')
        new_password = request.form.get('new_password','')
        confirm = request.form.get('confirm_password','')
        user = query('SELECT * FROM users WHERE id=?', (session.get('user_id'),), one=True)
        if not user or not check_password_hash(user['password_hash'], current):
            flash('Password attuale non corretta.')
            return redirect(url_for('main.change_password'))
        if len(new_password) < 8:
            flash('La nuova password deve avere almeno 8 caratteri.')
            return redirect(url_for('main.change_password'))
        if new_password != confirm:
            flash('La conferma password non coincide.')
            return redirect(url_for('main.change_password'))
        execute('UPDATE users SET password_hash=? WHERE id=?', (generate_password_hash(new_password), session.get('user_id')))
        flash('Password aggiornata correttamente.')
        return redirect(url_for('main.dashboard'))
    return render_template('change_password.html')


@bp.route('/admin/fidelity-card', methods=['GET','POST'])
@login_required
def fidelity():
    search = request.args.get('q','').strip()
    now = datetime.now().isoformat(timespec='seconds')

    if request.method == 'POST':
        data = request.form
        action = data.get('action')
        customer_id = data.get('customer_id')
        customer = query('SELECT * FROM customers WHERE id=?', (customer_id,), one=True)
        if not customer:
            flash('Cliente non trovato')
            return redirect(url_for('main.fidelity', q=search))

        before_points = int(customer['points'] or 0)

        if action == 'update_customer':
            execute('''UPDATE customers
                       SET name=?, phone=?, email=?, birthday=?, notes=?
                       WHERE id=?''',
                    (data.get('name'), data.get('phone'), data.get('email'), data.get('birthday'),
                     data.get('notes') or '', customer_id))
            flash('Dati cliente aggiornati')
            return redirect(url_for('main.fidelity', q=search))

        if action == 'points':
            mode = data.get('mode') or 'add'
            raw_points = int(data.get('points') or 0)
            points = abs(raw_points)
            motive = data.get('motive') or 'Movimento punti fidelity'

            if mode == 'reset':
                after_points = 0
                change_amount = -before_points
                motive = data.get('motive') or 'Azzera punti fidelity'
            elif mode == 'subtract':
                after_points = max(before_points - points, 0)
                change_amount = after_points - before_points
                motive = data.get('motive') or 'Punti utilizzati / rimossi'
            elif mode == 'set':
                after_points = points
                change_amount = after_points - before_points
            else:
                after_points = before_points + points
                change_amount = points
                mode = 'add'

            execute('UPDATE customers SET points=? WHERE id=?', (after_points, customer_id))
            execute('''INSERT INTO fidelity_points_history(customer_id,change_amount,before_points,after_points,mode,motive,operator,created_at)
                       VALUES (?,?,?,?,?,?,?,?)''',
                    (customer_id, change_amount, before_points, after_points, mode, motive, session.get('user_name',''), now))
            if mode == 'reset':
                flash('Punti fidelity azzerati')
            elif mode == 'subtract':
                flash('Punti fidelity scalati')
            else:
                flash('Punti fidelity aggiornati')
            return redirect(url_for('main.fidelity', q=search))

        return redirect(url_for('main.fidelity', q=search))

    base_sql = '''SELECT c.*,
                       (SELECT MAX(s.start_at)
                        FROM sessions s
                        WHERE s.customer_id=c.id OR lower(s.customer_name)=lower(c.name)) AS last_visit
                  FROM customers c'''
    if search:
        like = f'%{search}%'
        rows = query(base_sql + ' WHERE c.name LIKE ? OR c.phone LIKE ? OR c.email LIKE ? OR c.customer_code LIKE ? ORDER BY c.points DESC, c.name', (like, like, like, like))
    else:
        rows = query(base_sql + ' ORDER BY c.points DESC, c.name LIMIT 100')
    total_points = query('SELECT COALESCE(SUM(points),0) c FROM customers', one=True)['c']

    histories = {}
    visits = {}
    customer_ids = [r['id'] for r in rows]
    if customer_ids:
        placeholders = ','.join('?' for _ in customer_ids)
        history_rows = query(f'''SELECT * FROM fidelity_points_history
                                 WHERE customer_id IN ({placeholders})
                                 ORDER BY created_at DESC, id DESC''', tuple(customer_ids))
        for h in history_rows:
            histories.setdefault(h['customer_id'], []).append(h)

        for r in rows:
            visit_rows = query('''SELECT * FROM sessions
                                  WHERE customer_id=? OR lower(customer_name)=lower(?)
                                  ORDER BY start_at DESC, id DESC LIMIT 30''', (r['id'], r['name']))
            visits[r['id']] = visit_rows
    return render_template('fidelity.html', rows=rows, total_points=total_points, search=search, histories=histories, visits=visits)


@bp.route('/admin/newsletter', methods=['GET','POST'])
@login_required
def newsletter():
    if request.method == 'POST':
        data = request.form
        email = data.get('email','').strip().lower()
        if not email:
            flash('Inserisci una email valida')
            return redirect(url_for('main.newsletter'))
        try:
            execute('INSERT INTO newsletter_subscribers(name,email,phone,source,active,created_at) VALUES (?,?,?,?,?,?)',
                    (data.get('name'), email, data.get('phone'), data.get('source') or 'Pannello admin', 1 if data.get('active') else 0, datetime.now().isoformat(timespec='seconds')))
            flash('Iscritto newsletter aggiunto')
        except Exception:
            flash('Email già presente')
        return redirect(url_for('main.newsletter'))
    rows = query('SELECT * FROM newsletter_subscribers ORDER BY created_at DESC')
    active_count = query('SELECT COUNT(*) c FROM newsletter_subscribers WHERE active=1', one=True)['c']
    return render_template('newsletter.html', rows=rows, active_count=active_count)


@bp.route('/admin/newsletter/<int:id>/toggle', methods=['POST'])
@login_required
def newsletter_toggle(id):
    execute('UPDATE newsletter_subscribers SET active=CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?', (id,))
    return redirect(url_for('main.newsletter'))


@bp.route('/admin/newsletter/<int:id>/delete', methods=['POST'])
@login_required
def newsletter_delete(id):
    execute('DELETE FROM newsletter_subscribers WHERE id=?', (id,))
    flash('Iscritto eliminato')
    return redirect(url_for('main.newsletter'))


@bp.route('/admin/pacchetti-prezzi', methods=['GET','POST'])
@login_required
def packages_prices():
    if request.method == 'POST':
        data = request.form
        execute('INSERT INTO packages(name,minutes,price,type,active) VALUES (?,?,?,?,?)',
                (data.get('name'), data.get('minutes') or 30, data.get('price') or 0, data.get('type') or 'VR', 1 if data.get('active') else 0))
        flash('Pacchetto/prezzo aggiunto')
        return redirect(url_for('main.packages_prices'))
    rows = query('SELECT * FROM packages ORDER BY active DESC, type, price')
    return render_template('packages_prices.html', rows=rows)


@bp.route('/admin/pacchetti-prezzi/<int:id>/toggle', methods=['POST'])
@login_required
def package_toggle(id):
    execute('UPDATE packages SET active=CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?', (id,))
    return redirect(url_for('main.packages_prices'))


@bp.route('/admin/galleria', methods=['GET','POST'])
@login_required
def gallery():
    if request.method == 'POST':
        data = request.form
        image = upload_file('image')
        execute('INSERT INTO gallery_items(title,image,caption,active,sort_order,created_at) VALUES (?,?,?,?,?,?)',
                (data.get('title'), image, data.get('caption'), 1 if data.get('active') else 0, data.get('sort_order') or 0, datetime.now().isoformat(timespec='seconds')))
        flash('Immagine galleria aggiunta')
        return redirect(url_for('main.gallery'))
    rows = query('SELECT * FROM gallery_items ORDER BY active DESC, sort_order, id DESC')
    return render_template('gallery.html', rows=rows)


@bp.route('/admin/calendario-sala')
@login_required
def calendar_view():
    today = date.today().isoformat()
    bookings_rows = query('SELECT * FROM bookings WHERE booking_date>=? ORDER BY booking_date,start_time LIMIT 120', (today,))
    events_rows = query('SELECT * FROM events WHERE event_date>=? ORDER BY event_date,start_time LIMIT 80', (today,))
    return render_template('calendar_view.html', bookings=bookings_rows, events=events_rows)


@bp.route('/admin/timer-postazioni')
@login_required
def timer_stations():
    running = query("SELECT * FROM sessions WHERE status='running' ORDER BY end_at ASC")
    stations_rows = query('SELECT * FROM stations WHERE active=1 ORDER BY station_type,name')
    return render_template('timer_stations.html', running=running, stations=stations_rows)


@bp.route('/admin/game-master', methods=['GET','POST'])
@login_required
def game_masters():
    if request.method == 'POST':
        data = request.form
        execute('INSERT INTO game_masters(name,phone,role,hourly_rate,active,notes,created_at) VALUES (?,?,?,?,?,?,?)',
                (data.get('name'), data.get('phone'), data.get('role') or 'Game Master', data.get('hourly_rate') or 0, 1 if data.get('active') else 0, data.get('notes'), datetime.now().isoformat(timespec='seconds')))
        flash('Game master aggiunto')
        return redirect(url_for('main.game_masters'))
    rows = query('SELECT * FROM game_masters ORDER BY active DESC, name')
    return render_template('game_masters.html', rows=rows)


@bp.route('/admin/postazioni', methods=['GET','POST'])
@login_required
def stations():
    if request.method == 'POST':
        data = request.form
        execute('INSERT INTO stations(name,station_type,status,hardware,notes,active,created_at) VALUES (?,?,?,?,?,?,?)',
                (data.get('name'), data.get('station_type') or 'VR', data.get('status') or 'libera', data.get('hardware'), data.get('notes'), 1 if data.get('active') else 0, datetime.now().isoformat(timespec='seconds')))
        flash('Postazione aggiunta')
        return redirect(url_for('main.stations'))
    rows = query('SELECT * FROM stations ORDER BY active DESC, station_type,name')
    return render_template('stations.html', rows=rows)


@bp.route('/admin/stato-hardware', methods=['GET','POST'])
@login_required
def hardware_power():
    if request.method == 'POST':
        for k,v in request.form.items():
            upsert_setting(k, v)
        flash('Stato hardware aggiornato')
        return redirect(url_for('main.hardware_power'))
    st = get_settings_dict()
    return render_template('hardware_power.html', st=st)


@bp.route('/admin/report-mensile')
@login_required
def monthly_report():
    rows = query("""
    SELECT strftime('%Y-%m', created_at) month,
           SUM(CASE WHEN kind='incasso' THEN amount ELSE 0 END) income,
           SUM(CASE WHEN kind!='incasso' THEN amount ELSE 0 END) expenses,
           SUM(CASE WHEN kind='incasso' THEN amount ELSE -amount END) net
    FROM cash_movements
    GROUP BY strftime('%Y-%m', created_at)
    ORDER BY month DESC
    LIMIT 18
    """)
    return render_template('monthly_report.html', rows=rows)


def _row_to_dict(row):
    return dict(row)


def _backup_payload():
    data = {
        'app': 'Game World Arena VR',
        'versione': 'v23-online-ready',
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'database': 'postgresql_supabase' if is_postgres() else 'sqlite_locale',
        'tables': {}
    }
    for table in BACKUP_TABLES:
        order = 'ORDER BY key' if table == 'settings' else 'ORDER BY id'
        try:
            data['tables'][table] = [_row_to_dict(r) for r in query(f'SELECT * FROM {table} {order}')]
        except Exception:
            data['tables'][table] = []
    return data


@bp.route('/admin/backup')
@login_required
def backup():
    db_path = current_app.config['DATABASE']
    exists = Path(db_path).exists() if not is_postgres() else True
    size = Path(db_path).stat().st_size if (not is_postgres() and exists) else 0
    mode = 'Supabase / PostgreSQL' if is_postgres() else 'SQLite locale'
    counts = []
    for table in BACKUP_TABLES:
        try:
            counts.append((table, query(f'SELECT COUNT(*) AS c FROM {table}', one=True)['c']))
        except Exception:
            counts.append((table, 0))
    return render_template('backup.html', exists=exists, size=size, db_path=db_path, mode=mode, counts=counts)


@bp.route('/admin/backup/download')
@login_required
def backup_download():
    payload = _backup_payload()
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    mem = io.BytesIO()
    name_date = datetime.now().strftime('%Y%m%d_%H%M%S')
    with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('arena_backup.json', raw)
    mem.seek(0)
    return send_file(mem, mimetype='application/zip', as_attachment=True, download_name=f'arena_backup_{name_date}.zip')


@bp.route('/admin/backup/restore', methods=['POST'])
@login_required
def backup_restore():
    if request.form.get('confirm','').strip().upper() != 'RIPRISTINA':
        flash('Per ripristinare devi scrivere RIPRISTINA nel campo di conferma.')
        return redirect(url_for('main.backup'))
    f = request.files.get('backup_file')
    if not f or not f.filename:
        flash('Seleziona un file backup ZIP o JSON.')
        return redirect(url_for('main.backup'))
    raw = f.read()
    try:
        if f.filename.lower().endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                raw = zf.read('arena_backup.json')
        payload = json.loads(raw.decode('utf-8'))
        tables = payload.get('tables', {})
    except Exception:
        flash('Backup non valido: carica il file ZIP generato da questa app.')
        return redirect(url_for('main.backup'))

    db = get_db()
    try:
        if is_postgres():
            db.execute('TRUNCATE TABLE ' + ', '.join(BACKUP_TABLES) + ' RESTART IDENTITY CASCADE')
            db.commit()
        else:
            db.execute('PRAGMA foreign_keys=OFF')
            for table in reversed(BACKUP_TABLES):
                db.execute(f'DELETE FROM {table}')
            db.commit()

        for table in BACKUP_TABLES:
            for row in tables.get(table, []):
                if not row:
                    continue
                cols = list(row.keys())
                placeholders = ','.join(['?'] * len(cols))
                col_sql = ','.join(cols)
                values = [row.get(c) for c in cols]
                execute(f'INSERT INTO {table} ({col_sql}) VALUES ({placeholders})', values)

        if is_postgres():
            reset_postgres_sequences()
        else:
            try:
                db.execute('PRAGMA foreign_keys=ON')
                db.commit()
            except Exception:
                pass
        flash('Backup ripristinato correttamente.')
    except Exception as exc:
        flash('Errore durante il ripristino: ' + str(exc)[:160])
    return redirect(url_for('main.backup'))


@bp.route('/admin/tema-grafico', methods=['GET','POST'])
@login_required
def theme_settings():
    if request.method == 'POST':
        for k,v in request.form.items():
            upsert_setting(k, v)
        flash('Tema grafico salvato')
        return redirect(url_for('main.theme_settings'))
    st = get_settings_dict()
    return render_template('theme_settings.html', st=st)

@bp.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    if request.method == 'POST':
        for k,v in request.form.items():
            upsert_setting(k, v)
        return redirect(url_for('main.settings'))
    rows = query('SELECT * FROM settings ORDER BY key')
    return render_template('settings.html', rows=rows)


@bp.route('/api/sessions')
@login_required
def api_sessions():
    rows = query("SELECT * FROM sessions WHERE status='running' ORDER BY end_at")
    return jsonify([dict(r) for r in rows])
