import os
import re
import secrets
import sqlite3
import time
import unicodedata
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import smtplib
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "database", "elora.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
LOCAL_TZ = timezone(timedelta(hours=-3))
VALID_STATUSES = {"pending", "confirmed", "cancelled", "completed"}
VALID_INTERVALS = {10, 15, 20, 30, 60}
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RATE_BUCKETS = defaultdict(deque)
CSRF_EXEMPT_ENDPOINTS = set()
RESERVED_SLUGS = {
    "admin", "login", "logout", "cadastro", "esqueci-senha",
    "redefinir-senha", "setup", "static", "api", "p", "favicon.ico"
}

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or "troque-esta-chave-em-producao",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
)

def now_local():
    return datetime.now(LOCAL_TZ)


app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

if not app.config["SECRET_KEY"]:
    raise RuntimeError(
        "Configure a variável de ambiente SECRET_KEY antes de iniciar."
    )

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("COOKIE_SECURE", "false").lower() == "true"
)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

if os.environ.get("TRUST_PROXY") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

DUMMY_HASH = generate_password_hash(secrets.token_hex(16))
RATE_BUCKETS = defaultdict(deque)


def now_local():
    return datetime.now(LOCAL_TZ)


def is_rate_limited(key, limit, window_seconds):
    now = time.monotonic()
    bucket = RATE_BUCKETS[key]

    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()

    if len(bucket) >= limit:
        return True

    bucket.append(now)
    return False


def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(DATABASE), exist_ok=True)

        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_db():
    db = get_db()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            nickname TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL UNIQUE,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            headline TEXT DEFAULT '',
            about TEXT DEFAULT '',
            whatsapp TEXT DEFAULT '',
            instagram TEXT DEFAULT '',
            facebook TEXT DEFAULT '',
            address TEXT DEFAULT '',
            neighborhood TEXT DEFAULT '',
            city TEXT DEFAULT '',
            state TEXT DEFAULT '',
            zip_code TEXT DEFAULT '',
            map_link TEXT DEFAULT '',
            map_embed_url TEXT DEFAULT '',
            cover_image TEXT DEFAULT '',
            profile_image TEXT DEFAULT '',
            interval_minutes INTEGER DEFAULT 30,
            booking_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price REAL NOT NULL DEFAULT 0,
            duration_minutes INTEGER NOT NULL DEFAULT 30,
            photo TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            weekday INTEGER NOT NULL,
            day_name TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            start_time TEXT DEFAULT '09:00',
            end_time TEXT DEFAULT '18:00',
            UNIQUE (business_id, weekday),
            FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS blocked_dates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            blocked_date TEXT NOT NULL,
            reason TEXT DEFAULT '',
            FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            service_id INTEGER,
            customer_name TEXT NOT NULL,
            customer_phone TEXT NOT NULL,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            notes TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE,
            FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_services_business
        ON services(business_id);

        CREATE INDEX IF NOT EXISTS idx_appointments_business_date
        ON appointments(business_id, appointment_date);

        CREATE INDEX IF NOT EXISTS idx_blocked_dates_business
        ON blocked_dates(business_id, blocked_date);
    """)

    db.commit()


def migrate_db():
    db = get_db()

    columns = [row["name"] for row in db.execute("PRAGMA table_info(users)")]

    if "nickname" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN nickname TEXT DEFAULT ''")

    if "phone" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''")

    db.commit()


def generate_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)

    return session["_csrf_token"]


@app.context_processor
def inject_template_functions():
    return {"csrf_token": generate_csrf_token}


@app.before_request
def validate_csrf():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return

    if request.endpoint in CSRF_EXEMPT_ENDPOINTS:
        return

    token_session = session.get("_csrf_token", "")
    token_sent = (
        request.form.get("csrf_token")
        or request.headers.get("X-CSRF-Token", "")
    )

    if (
        not token_session
        or not token_sent
        or not secrets.compare_digest(
            token_session.encode("utf-8"), token_sent.encode("utf-8")
        )
    ):
        abort(400)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


def slugify(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:60]


def create_unique_slug(name):
    db = get_db()
    base_slug = slugify(name) or "negocio"
    slug = base_slug
    counter = 2

    while slug in RESERVED_SLUGS or db.execute(
        "SELECT id FROM businesses WHERE slug = ?", (slug,)
    ).fetchone():
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


def only_digits(value):
    return re.sub(r"\D", "", value or "")


def to_minutes(time_value):
    hours, minutes = time_value.split(":")
    return int(hours) * 60 + int(minutes)


def password_errors(password):
    errors = []

    if len(password) < 8:
        errors.append("ter pelo menos 8 caracteres")

    if not re.search(r"[A-Z]", password):
        errors.append("uma letra maiúscula")

    if not re.search(r"\d", password):
        errors.append("um número")

    if not re.search(r"[^A-Za-z0-9\s]", password):
        errors.append("um caractere especial")

    return errors


def get_current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    return get_db().execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()


def get_current_business():
    user = get_current_user()

    if not user:
        return None

    return get_db().execute(
        "SELECT * FROM businesses WHERE owner_id = ?", (user["id"],)
    ).fetchone()


def login_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            flash("Faça login para acessar sua conta.", "warning")
            return redirect(url_for("login"))

        if not get_current_user():
            session.clear()
            flash("Sua sessão expirou. Entre novamente.", "warning")
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return decorated_function


def require_business():
    business = get_current_business()

    if not business:
        abort(403)

    return business


def get_business_schedule(business_id):
    rows = get_db().execute("""
        SELECT weekday, day_name, enabled, start_time, end_time
        FROM schedules
        WHERE business_id = ?
        ORDER BY weekday
    """, (business_id,)).fetchall()

    return [dict(row) for row in rows]


def get_business_services(business_id):
    rows = get_db().execute("""
        SELECT *
        FROM services
        WHERE business_id = ? AND active = 1
        ORDER BY id DESC
    """, (business_id,)).fetchall()

    return [dict(row) for row in rows]


def create_default_schedule(business_id):
    db = get_db()

    days = [
        (0, "Segunda-feira", 1, "09:00", "18:00"),
        (1, "Terça-feira", 1, "09:00", "18:00"),
        (2, "Quarta-feira", 1, "09:00", "18:00"),
        (3, "Quinta-feira", 1, "09:00", "18:00"),
        (4, "Sexta-feira", 1, "09:00", "18:00"),
        (5, "Sábado", 1, "09:00", "13:00"),
        (6, "Domingo", 0, "09:00", "13:00"),
    ]

    for weekday, name, enabled, start, end in days:
        db.execute("""
            INSERT INTO schedules (
                business_id, weekday, day_name,
                enabled, start_time, end_time
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (business_id, weekday, name, enabled, start, end))


def back_to(section):
    return redirect(url_for("admin", _anchor=section))


def clean_https_url(value, base=None):
    value = (value or "").strip()

    if not value:
        return ""

    if base and value.startswith("@"):
        value = base + value[1:]

    if value.startswith("https://") and len(value) <= 300:
        return value

    return None


def detect_image_extension(header):
    if header.startswith(b"\xff\xd8\xff"):
        return "jpg"

    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"

    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"

    return None


def save_image(file_storage, business_id):
    if not file_storage or not file_storage.filename:
        return None

    header = file_storage.stream.read(12)
    file_storage.stream.seek(0)

    extension = detect_image_extension(header)

    if not extension:
        raise ValueError("Envie uma imagem JPG, PNG ou WEBP.")

    folder = os.path.join(UPLOAD_DIR, str(business_id))
    os.makedirs(folder, exist_ok=True)

    filename = f"{secrets.token_hex(12)}.{extension}"
    file_storage.save(os.path.join(folder, filename))

    return f"/static/uploads/{business_id}/{filename}"


def delete_upload(path, business_id):
    prefix = f"/static/uploads/{business_id}/"

    if not path or not path.startswith(prefix):
        return

    full_path = os.path.normpath(
        os.path.join(BASE_DIR, path.lstrip("/").replace("/", os.sep))
    )

    if full_path.startswith(os.path.normpath(UPLOAD_DIR)) and os.path.isfile(full_path):
        try:
            os.remove(full_path)
        except OSError:
            app.logger.exception("Não foi possível remover o arquivo antigo.")


@app.route("/")
def home():
    if session.get("user_id"):
        return redirect(url_for("admin"))

    return redirect(url_for("login"))


@app.route("/favicon.ico")
def favicon():
    return "", 204



@app.route("/cadastro", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("admin"))

    if request.method == "POST":
        owner_name = request.form.get("owner_name", "").strip()[:100]
        nickname = request.form.get("nickname", "").strip()[:40]
        business_name = request.form.get("business_name", "").strip()[:100]
        phone = only_digits(request.form.get("phone"))
        email = request.form.get("email", "").strip().lower()
        confirm_email = request.form.get("confirm_email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        terms = request.form.get("terms")

        if is_rate_limited(f"register:{request.remote_addr}", 10, 3600):
            flash("Muitas tentativas de cadastro. Tente novamente mais tarde.", "error")
            return redirect(url_for("register"))

        if not all([owner_name, nickname, business_name, phone, email, password]):
            flash("Preencha todos os campos obrigatórios.", "error")
            return redirect(url_for("register"))

        if len(phone) not in (10, 11):
            flash("Informe um telefone válido com DDD.", "error")
            return redirect(url_for("register"))

        if not EMAIL_PATTERN.match(email):
            flash("Informe um e-mail válido.", "error")
            return redirect(url_for("register"))

        if email != confirm_email:
            flash("Os e-mails não coincidem.", "error")
            return redirect(url_for("register"))

        missing = password_errors(password)

        if missing:
            flash("A senha precisa ter: " + ", ".join(missing) + ".", "error")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("As senhas não coincidem.", "error")
            return redirect(url_for("register"))

        if not terms:
            flash("Você precisa aceitar os termos de uso.", "warning")
            return redirect(url_for("register"))

        db = get_db()

        if db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            flash("Este e-mail já possui uma conta.", "error")
            return redirect(url_for("register"))

        try:
            now = datetime.now(timezone.utc).isoformat()

            cursor = db.execute("""
                INSERT INTO users (name, nickname, phone, email, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                owner_name, nickname, phone, email,
                generate_password_hash(password), now,
            ))

            user_id = cursor.lastrowid
            slug = create_unique_slug(business_name)

            business_cursor = db.execute("""
                INSERT INTO businesses (owner_id, name, slug, whatsapp, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, business_name, slug, "55" + phone, now))

            create_default_schedule(business_cursor.lastrowid)
            db.commit()

        except sqlite3.Error:
            db.rollback()
            app.logger.exception("Erro ao criar conta.")
            flash("Não foi possível concluir o cadastro. Tente novamente.", "error")
            return redirect(url_for("register"))

        session.clear()
        generate_csrf_token()

        flash(f"Conta criada com sucesso, {nickname}! Entre com seu e-mail e senha.", "success")
        return redirect(url_for("login"))

    return render_template("cadastro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("admin"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember")

        ip_key = f"login:{request.remote_addr}"
        email_key = f"login:{request.remote_addr}:{email}"

        if is_rate_limited(ip_key, 30, 600) or is_rate_limited(email_key, 8, 600):
            flash("Muitas tentativas. Aguarde alguns minutos e tente novamente.", "error")
            return redirect(url_for("login"))

        user = get_db().execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()

        password_hash = user["password_hash"] if user else DUMMY_HASH
        valid = check_password_hash(password_hash, password)

        if not user or not valid:
            flash("E-mail ou senha incorretos.", "error")
            return redirect(url_for("login"))

        RATE_BUCKETS.pop(email_key, None)

        session.clear()
        session["user_id"] = user["id"]
        session.permanent = bool(remember)
        generate_csrf_token()

        return redirect(url_for("admin"))

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("Você saiu da sua conta.", "success")
    return redirect(url_for("login"))


def send_recovery_email(email, reset_url):
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("MAIL_FROM", smtp_user or "")

    if not all([smtp_host, smtp_user, smtp_password, sender]):
        app.logger.warning("SMTP não configurado. E-mail de recuperação não enviado.")
        return False

    message = EmailMessage()
    message["Subject"] = "Recuperação de senha | MW3 Digital"
    message["From"] = sender
    message["To"] = email

    message.set_content(f"""
Olá!

Recebemos uma solicitação para redefinir sua senha.

Acesse o link abaixo para criar uma nova senha:

{reset_url}

Este link é válido por 30 minutos e só pode ser usado uma vez.

Se você não solicitou a recuperação, ignore esta mensagem.
""")

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(message)

        return True

    except Exception:
        app.logger.exception("Erro ao enviar e-mail de recuperação.")
        return False


def load_reset_user(token):
    try:
        payload = serializer.loads(token, salt="password-reset", max_age=1800)
    except (BadSignature, SignatureExpired):
        return None

    if not isinstance(payload, dict):
        return None

    user = get_db().execute(
        "SELECT * FROM users WHERE email = ?", (payload.get("email", ""),)
    ).fetchone()

    if not user or user["password_hash"][-12:] != payload.get("h"):
        return None

    return user


@app.route("/esqueci-senha", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if is_rate_limited(f"forgot:{request.remote_addr}", 5, 900):
            flash("Muitas solicitações. Aguarde alguns minutos.", "error")
            return redirect(url_for("forgot_password"))

        user = get_db().execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()

        if user:
            token = serializer.dumps(
                {"email": user["email"], "h": user["password_hash"][-12:]},
                salt="password-reset",
            )

            reset_url = url_for("reset_password", token=token, _external=True)

            if not send_recovery_email(user["email"], reset_url) and app.debug:
                app.logger.warning("Link de redefinição (modo desenvolvimento): %s", reset_url)

        flash(
            "Se o e-mail estiver cadastrado, você receberá as instruções de recuperação.",
            "info",
        )

        return redirect(url_for("forgot_password"))

    return render_template("esqueci_senha.html")


@app.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = load_reset_user(token)

    if not user:
        flash("O link é inválido, expirou ou já foi utilizado. Solicite outro.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        missing = password_errors(password)

        if missing:
            flash("A senha precisa ter: " + ", ".join(missing) + ".", "error")
            return redirect(url_for("reset_password", token=token))

        if password != confirm_password:
            flash("As senhas não coincidem.", "error")
            return redirect(url_for("reset_password", token=token))

        db = get_db()

        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user["id"]),
        )
        db.commit()

        flash("Senha redefinida com sucesso! Faça login.", "success")
        return redirect(url_for("login"))

    return render_template("redefinir_senha.html", token=token)


@app.route("/admin")
@login_required
def admin():
    user = get_current_user()
    business = require_business()
    db = get_db()

    today = now_local().strftime("%Y-%m-%d")

    stats = {
        "today": db.execute("""
            SELECT COUNT(*) AS total FROM appointments
            WHERE business_id = ? AND appointment_date = ?
            AND status IN ('pending', 'confirmed')
        """, (business["id"], today)).fetchone()["total"],

        "pending": db.execute("""
            SELECT COUNT(*) AS total FROM appointments
            WHERE business_id = ? AND status = 'pending'
        """, (business["id"],)).fetchone()["total"],

        "services": db.execute("""
            SELECT COUNT(*) AS total FROM services
            WHERE business_id = ? AND active = 1
        """, (business["id"],)).fetchone()["total"],
    }

    appointments = db.execute("""
        SELECT appointments.*, services.name AS service_name
        FROM appointments
        LEFT JOIN services ON appointments.service_id = services.id
        WHERE appointments.business_id = ?
        ORDER BY appointments.appointment_date DESC,
                 appointments.appointment_time DESC
        LIMIT 100
    """, (business["id"],)).fetchall()

    blocked_dates = db.execute("""
        SELECT * FROM blocked_dates
        WHERE business_id = ?
        ORDER BY blocked_date
    """, (business["id"],)).fetchall()

    owner = dict(user)
    owner.pop("password_hash", None)

    return render_template(
        "admin.html",
        owner=owner,
        business=dict(business),
        services=get_business_services(business["id"]),
        schedule=get_business_schedule(business["id"]),
        stats=stats,
        appointments=appointments,
        blocked_dates=blocked_dates,
    )


@app.route("/admin/perfil", methods=["POST"])
@login_required
def save_profile():
    user = get_current_user()
    business = require_business()

    business_name = request.form.get("business_name", "").strip()[:100]
    owner_name = request.form.get("owner_name", "").strip()[:100]
    nickname = request.form.get("nickname", "").strip()[:40]
    headline = request.form.get("headline", "").strip()[:120]
    description = request.form.get("description", "").strip()[:300]
    about = request.form.get("about", "").strip()[:1000]
    phone = only_digits(request.form.get("phone"))

    if not business_name or not owner_name:
        flash("Informe o nome do espaço e o nome da profissional.", "error")
        return back_to("perfil")

    if phone and len(phone) not in (10, 11):
        flash("Informe um telefone válido com DDD.", "error")
        return back_to("perfil")

    db = get_db()

    db.execute(
        "UPDATE users SET name = ?, nickname = ?, phone = ? WHERE id = ?",
        (owner_name, nickname, phone, user["id"]),
    )

    db.execute("""
        UPDATE businesses
        SET name = ?, headline = ?, description = ?, about = ?
        WHERE id = ?
    """, (business_name, headline, description, about, business["id"]))

    db.commit()

    flash("Informações atualizadas!", "success")
    return back_to("perfil")


@app.route("/admin/localizacao", methods=["POST"])
@login_required
def save_location():
    business = require_business()

    address = request.form.get("address", "").strip()[:150]
    neighborhood = request.form.get("neighborhood", "").strip()[:80]
    city = request.form.get("city", "").strip()[:80]
    state = request.form.get("state", "").strip().upper()[:2]
    zip_code = request.form.get("zip_code", "").strip()[:9]

    map_link = clean_https_url(request.form.get("map_link"))

    if map_link is None:
        flash("O link do Google Maps deve começar com https://", "error")
        return back_to("localizacao")

    embed_raw = request.form.get("map_embed_url", "").strip()
    iframe_match = re.search(r'src="([^"]+)"', embed_raw)

    if iframe_match:
        embed_raw = iframe_match.group(1)

    map_embed_url = embed_raw[:600]

    if map_embed_url and not map_embed_url.startswith("https://www.google.com/maps/embed"):
        flash("O mapa incorporado deve ser o link de incorporação do Google Maps.", "error")
        return back_to("localizacao")

    db = get_db()

    db.execute("""
        UPDATE businesses
        SET address = ?, neighborhood = ?, city = ?, state = ?,
            zip_code = ?, map_link = ?, map_embed_url = ?
        WHERE id = ?
    """, (
        address, neighborhood, city, state,
        zip_code, map_link, map_embed_url, business["id"],
    ))

    db.commit()

    flash("Localização atualizada!", "success")
    return back_to("localizacao")


@app.route("/admin/redes", methods=["POST"])
@login_required
def save_social():
    business = require_business()

    instagram = clean_https_url(request.form.get("instagram"), "https://instagram.com/")
    facebook = clean_https_url(request.form.get("facebook"), "https://facebook.com/")

    if instagram is None or facebook is None:
        flash(
            "Os links das redes sociais devem começar com https:// "
            "(no Instagram, pode usar @perfil).",
            "error",
        )
        return back_to("redes")

    whatsapp = only_digits(request.form.get("whatsapp"))

    if whatsapp and len(whatsapp) in (10, 11):
        whatsapp = "55" + whatsapp

    if whatsapp and len(whatsapp) not in (12, 13):
        flash("Informe um WhatsApp válido com DDD.", "error")
        return back_to("redes")

    db = get_db()

    db.execute("""
        UPDATE businesses
        SET instagram = ?, facebook = ?, whatsapp = ?
        WHERE id = ?
    """, (instagram, facebook, whatsapp, business["id"]))

    db.commit()

    flash("Redes sociais atualizadas!", "success")
    return back_to("redes")


@app.route("/admin/horarios", methods=["POST"])
@login_required
def save_schedule():
    business = require_business()

    try:
        interval = int(request.form.get("interval_minutes", 30))
    except ValueError:
        interval = 0

    if interval not in VALID_INTERVALS:
        flash("Escolha um intervalo válido.", "error")
        return back_to("horarios")

    updates = []

    for weekday in range(7):
        if not request.form.get(f"enabled_{weekday}"):
            updates.append((weekday, False, None, None))
            continue

        start = request.form.get(f"start_{weekday}", "")
        end = request.form.get(f"end_{weekday}", "")

        if not TIME_PATTERN.match(start) or not TIME_PATTERN.match(end) or start >= end:
            flash("Confira os horários. O encerramento deve ser posterior ao início.", "error")
            return back_to("horarios")

        updates.append((weekday, True, start, end))

    db = get_db()

    for weekday, enabled, start, end in updates:
        if enabled:
            db.execute("""
                UPDATE schedules
                SET enabled = 1, start_time = ?, end_time = ?
                WHERE business_id = ? AND weekday = ?
            """, (start, end, business["id"], weekday))
        else:
            db.execute("""
                UPDATE schedules SET enabled = 0
                WHERE business_id = ? AND weekday = ?
            """, (business["id"], weekday))

    db.execute(
        "UPDATE businesses SET interval_minutes = ? WHERE id = ?",
        (interval, business["id"]),
    )

    db.commit()

    flash("Horários salvos com sucesso!", "success")
    return back_to("horarios")


@app.route("/admin/datas-bloqueadas", methods=["POST"])
@login_required
def add_blocked_date():
    business = require_business()
    blocked_date = request.form.get("blocked_date", "")

    try:
        datetime.strptime(blocked_date, "%Y-%m-%d")
    except ValueError:
        flash("Selecione uma data válida.", "error")
        return back_to("horarios")

    db = get_db()

    exists = db.execute("""
        SELECT id FROM blocked_dates
        WHERE business_id = ? AND blocked_date = ?
    """, (business["id"], blocked_date)).fetchone()

    if exists:
        flash("Essa data já está bloqueada.", "warning")
        return back_to("horarios")

    db.execute(
        "INSERT INTO blocked_dates (business_id, blocked_date) VALUES (?, ?)",
        (business["id"], blocked_date),
    )
    db.commit()

    flash("Data bloqueada com sucesso!", "success")
    return back_to("horarios")


@app.route("/admin/datas-bloqueadas/<int:blocked_id>/remover", methods=["POST"])
@login_required
def remove_blocked_date(blocked_id):
    business = require_business()
    db = get_db()

    db.execute(
        "DELETE FROM blocked_dates WHERE id = ? AND business_id = ?",
        (blocked_id, business["id"]),
    )
    db.commit()

    flash("Data desbloqueada.", "success")
    return back_to("horarios")


@app.route("/admin/servicos", methods=["POST"])
@login_required
def save_service():
    business = require_business()
    db = get_db()

    service_id = request.form.get("service_id", "").strip()
    name = request.form.get("name", "").strip()[:100]
    description = request.form.get("description", "").strip()[:500]

    try:
        price = float(request.form.get("price", "0").replace(",", "."))
        duration = int(request.form.get("duration", "0"))
    except ValueError:
        flash("Confira o preço e a duração do serviço.", "error")
        return back_to("servicos")

    if not name or price < 0 or price > 100000 or not 5 <= duration <= 720:
        flash("Confira os dados do serviço.", "error")
        return back_to("servicos")

    try:
        new_photo = save_image(request.files.get("photo"), business["id"])
    except ValueError as error:
        flash(str(error), "error")
        return back_to("servicos")

    if service_id:
        service = db.execute("""
            SELECT * FROM services
            WHERE id = ? AND business_id = ? AND active = 1
        """, (service_id, business["id"])).fetchone()

        if not service:
            abort(404)

        db.execute("""
            UPDATE services
            SET name = ?, description = ?, price = ?, duration_minutes = ?, photo = ?
            WHERE id = ?
        """, (
            name, description, price, duration,
            new_photo or service["photo"], service["id"],
        ))

        if new_photo:
            delete_upload(service["photo"], business["id"])

    else:
        db.execute("""
            INSERT INTO services (
                business_id, name, description, price,
                duration_minutes, photo, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            business["id"], name, description, price, duration,
            new_photo or "", datetime.now(timezone.utc).isoformat(),
        ))

    db.commit()

    flash("Serviço salvo com sucesso!", "success")
    return back_to("servicos")


@app.route("/admin/servicos/<int:service_id>/excluir", methods=["POST"])
@login_required
def delete_service(service_id):
    business = require_business()
    db = get_db()

    db.execute(
        "UPDATE services SET active = 0 WHERE id = ? AND business_id = ?",
        (service_id, business["id"]),
    )
    db.commit()

    flash("Serviço excluído.", "success")
    return back_to("servicos")


@app.route("/admin/aparencia", methods=["POST"])
@login_required
def save_appearance():
    business = require_business()
    db = get_db()

    try:
        new_cover = save_image(request.files.get("cover_image"), business["id"])
        new_profile = save_image(request.files.get("profile_image"), business["id"])
    except ValueError as error:
        flash(str(error), "error")
        return back_to("aparencia")

    if new_cover:
        db.execute(
            "UPDATE businesses SET cover_image = ? WHERE id = ?",
            (new_cover, business["id"]),
        )
        delete_upload(business["cover_image"], business["id"])

    if new_profile:
        db.execute(
            "UPDATE businesses SET profile_image = ? WHERE id = ?",
            (new_profile, business["id"]),
        )
        delete_upload(business["profile_image"], business["id"])

    db.commit()

    if new_cover or new_profile:
        flash("Aparência salva com sucesso!", "success")
    else:
        flash("Nenhuma imagem nova foi selecionada.", "info")

    return back_to("aparencia")


@app.route("/admin/agendamentos/<int:appointment_id>/status", methods=["POST"])
@login_required
def update_appointment_status(appointment_id):
    business = require_business()
    status = request.form.get("status", "")

    if status not in VALID_STATUSES:
        flash("Status inválido.", "error")
        return back_to("agenda")

    db = get_db()

    db.execute(
        "UPDATE appointments SET status = ? WHERE id = ? AND business_id = ?",
        (status, appointment_id, business["id"]),
    )
    db.commit()

    flash("Status atualizado.", "success")
    return back_to("agenda")


def find_business_by_slug(slug):
    return get_db().execute(
        "SELECT * FROM businesses WHERE slug = ?", (slug,)
    ).fetchone()


def get_active_appointments(db, business_id, date_from, date_to=None):
    query = """
        SELECT
            a.appointment_date,
            a.appointment_time,
            COALESCE(s.duration_minutes, b.interval_minutes, 30) AS duration
        FROM appointments a
        JOIN businesses b ON b.id = a.business_id
        LEFT JOIN services s ON s.id = a.service_id
        WHERE a.business_id = ?
        AND a.status IN ('pending', 'confirmed')
        AND a.appointment_date >= ?
    """
    params = [business_id, date_from]

    if date_to:
        query += " AND a.appointment_date <= ?"
        params.append(date_to)

    return db.execute(query, params).fetchall()


def json_error(message, status):
    response = jsonify({"ok": False, "error": message})
    response.status_code = status
    return response


@app.route("/<slug>")
def public_page(slug):
    business = find_business_by_slug(slug)

    if not business:
        abort(404)

    return render_template(
        "index.html",
        business=dict(business),
        services=get_business_services(business["id"]),
        schedule=get_business_schedule(business["id"]),
    )


@app.route("/<slug>/disponibilidade")
def availability(slug):
    business = find_business_by_slug(slug)

    if not business:
        return json_error("Página não encontrada.", 404)

    db = get_db()
    today = now_local().strftime("%Y-%m-%d")

    blocked = [
        row["blocked_date"]
        for row in db.execute("""
            SELECT blocked_date FROM blocked_dates
            WHERE business_id = ? AND blocked_date >= ?
        """, (business["id"], today))
    ]

    booked = [
        {
            "date": row["appointment_date"],
            "time": row["appointment_time"],
            "duration": row["duration"],
        }
        for row in get_active_appointments(db, business["id"], today)
    ]

    response = jsonify({
        "ok": True,
        "bookingActive": bool(business["booking_active"]),
        "blockedDates": blocked,
        "bookedTimes": booked,
    })
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/<slug>/agendar", methods=["POST"])
def create_appointment(slug):
    business = find_business_by_slug(slug)

    if not business:
        return json_error("Página não encontrada.", 404)

    if is_rate_limited(f"book:{request.remote_addr}", 6, 600):
        return json_error("Muitas solicitações. Aguarde alguns minutos.", 429)

    if not business["booking_active"]:
        return json_error("Os agendamentos estão pausados no momento.", 400)

    data = request.get_json(silent=True) or {}
    db = get_db()

    customer_name = str(data.get("name", "")).strip()[:100]
    customer_phone = only_digits(str(data.get("phone", "")))
    notes = str(data.get("notes", "")).strip()[:500]
    date_value = str(data.get("date", ""))
    time_value = str(data.get("time", ""))

    if len(customer_name) < 2:
        return json_error("Informe seu nome.", 400)

    if len(customer_phone) not in (10, 11, 12, 13):
        return json_error("Informe um telefone válido com DDD.", 400)

    service = None
    service_id = data.get("service_id")

    if service_id not in (None, ""):
        try:
            service = db.execute("""
                SELECT * FROM services
                WHERE id = ? AND business_id = ? AND active = 1
            """, (int(service_id), business["id"])).fetchone()
        except (TypeError, ValueError):
            service = None
    else:
        service = db.execute("""
            SELECT * FROM services
            WHERE name = ? AND business_id = ? AND active = 1
        """, (str(data.get("service", "")), business["id"])).fetchone()

    if not service:
        return json_error("Procedimento não encontrado.", 400)

    try:
        appointment_date = datetime.strptime(date_value, "%Y-%m-%d").date()
    except ValueError:
        return json_error("Data inválida.", 400)

    if not TIME_PATTERN.match(time_value):
        return json_error("Horário inválido.", 400)

    now = now_local()

    if appointment_date < now.date() or appointment_date > now.date() + timedelta(days=180):
        return json_error("Escolha uma data disponível.", 400)

    start = to_minutes(time_value)
    duration = service["duration_minutes"]

    if appointment_date == now.date() and start <= now.hour * 60 + now.minute:
        return json_error("Esse horário já passou.", 400)

    day = db.execute("""
        SELECT * FROM schedules
        WHERE business_id = ? AND weekday = ?
    """, (business["id"], appointment_date.weekday())).fetchone()

    if (
        not day
        or not day["enabled"]
        or start < to_minutes(day["start_time"])
        or start + duration > to_minutes(day["end_time"])
    ):
        return json_error("Esse horário está fora do atendimento.", 400)

    if db.execute("""
        SELECT id FROM blocked_dates
        WHERE business_id = ? AND blocked_date = ?
    """, (business["id"], date_value)).fetchone():
        return json_error("Não há atendimento nesta data.", 400)

    if db.in_transaction:
        db.commit()

    db.execute("BEGIN IMMEDIATE")

    try:
        for row in get_active_appointments(db, business["id"], date_value, date_value):
            existing_start = to_minutes(row["appointment_time"])
            existing_end = existing_start + row["duration"]

            if start < existing_end and start + duration > existing_start:
                db.rollback()
                return json_error("Esse horário acabou de ser ocupado. Escolha outro.", 409)

        cursor = db.execute("""
            INSERT INTO appointments (
                business_id, service_id, customer_name, customer_phone,
                appointment_date, appointment_time, notes, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (
            business["id"], service["id"], customer_name, customer_phone,
            date_value, time_value, notes, datetime.now(timezone.utc).isoformat(),
        ))

        db.commit()

    except sqlite3.Error:
        db.rollback()
        app.logger.exception("Erro ao registrar agendamento.")
        return json_error("Não foi possível registrar o agendamento.", 500)

    return jsonify({"ok": True, "id": cursor.lastrowid})


def render_error(code, message):
    return render_template("error.html", code=code, message=message), code


@app.errorhandler(400)
def bad_request(error):
    return render_error(400, "Não foi possível validar sua solicitação. Volte e tente novamente.")


@app.errorhandler(403)
def forbidden(error):
    return render_error(403, "Você não tem permissão para acessar esta página.")


@app.errorhandler(404)
def not_found(error):
    return render_error(404, "A página que você procura não foi encontrada.")


@app.errorhandler(405)
def method_not_allowed(error):
    return render_error(405, "Esta ação não é permitida.")


@app.errorhandler(413)
def file_too_large(error):
    flash("O arquivo é grande demais. O limite é de 8 MB.", "error")
    return redirect(url_for("admin"))


@app.errorhandler(500)
def server_error(error):
    return render_error(500, "Algo deu errado do nosso lado. Tente novamente em instantes.")


@app.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    business = require_business()

    if request.method == "POST":
        name = request.form.get("name", business["name"]).strip()[:100]
        headline = request.form.get("headline", "").strip()[:120]
        description = request.form.get("description", "").strip()[:300]

        if not name:
            flash("Informe o nome do espaço.", "error")
            return redirect(url_for("setup"))

        db = get_db()
        db.execute(
            "UPDATE businesses SET name = ?, headline = ?, description = ? WHERE id = ?",
            (name, headline, description, business["id"]),
        )
        db.commit()
        flash("Configuração inicial salva.", "success")
        return redirect(url_for("admin"))

    return render_template("setup.html", business=dict(business))


with app.app_context():
    init_db()
    migrate_db()

@app.route("/p/<slug>")
def public_page_shortlink(slug):
    business = get_db().execute("SELECT * FROM businesses WHERE slug=?", (slug,)).fetchone()
    if not business:
        abort(404)
    if not business["booking_active"]:
        return render_template("error.html", message="Agendamentos temporariamente indisponíveis."), 403
    return render_template("link.html", business=dict(business), services=get_business_services(business["id"]),
                           schedule=get_business_schedule(business["id"]))

@app.route("/api/horarios/<slug>")
def available_times(slug):
    business = get_db().execute("SELECT * FROM businesses WHERE slug=? AND booking_active=1", (slug,)).fetchone()
    if not business:
        return jsonify({"times": []}), 404
    date = request.args.get("date", "")
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"times": []}), 400
    db = get_db()
    schedule = db.execute("SELECT * FROM schedules WHERE business_id=? AND weekday=?",
                          (business["id"], day.weekday())).fetchone()
    blocked = db.execute("SELECT 1 FROM blocked_dates WHERE business_id=? AND blocked_date=?",
                         (business["id"], date)).fetchone()
    if not schedule or not schedule["enabled"] or blocked:
        return jsonify({"times": []})
    interval = business["interval_minutes"] or 30
    start = datetime.strptime(schedule["start_time"], "%H:%M")
    end = datetime.strptime(schedule["end_time"], "%H:%M")
    busy = {r["appointment_time"] for r in db.execute("""SELECT appointment_time FROM appointments
        WHERE business_id=? AND appointment_date=? AND status IN ('pending','confirmed')""",
        (business["id"], date)).fetchall()}
    times = []
    current = start
    while current < end:
        value = current.strftime("%H:%M")
        if value not in busy:
            times.append(value)
        current += timedelta(minutes=interval)
    return jsonify({"times": times})

@app.route("/agendar/<slug>", methods=["POST"])
def create_appointment_form(slug):
    business = get_db().execute("SELECT * FROM businesses WHERE slug=? AND booking_active=1", (slug,)).fetchone()
    if not business:
        abort(404)
    name = request.form.get("customer_name", "").strip()[:100]
    phone = only_digits(request.form.get("customer_phone"))
    date = request.form.get("appointment_date", "")
    hour = request.form.get("appointment_time", "")
    service_id = request.form.get("service_id") or None
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        day = None
    if not name or len(phone) < 10 or not day or day < now_local().date() or not TIME_PATTERN.match(hour):
        flash("Confira seus dados e escolha uma data e horário válidos.", "error")
        return redirect(url_for("public_page", slug=slug))
    db = get_db()
    if service_id and not db.execute("SELECT 1 FROM services WHERE id=? AND business_id=? AND active=1",
                                     (service_id, business["id"])).fetchone():
        abort(400)
    available = available_times_for_request(db, business, day, hour)
    if not available:
        flash("Este horário não está disponível. Escolha outro.", "error")
        return redirect(url_for("public_page", slug=slug))
    db.execute("""INSERT INTO appointments(business_id,service_id,customer_name,customer_phone,
        appointment_date,appointment_time,notes,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
        (business["id"], service_id, name, phone, date, hour,
         request.form.get("notes", "")[:500], "pending", datetime.now(timezone.utc).isoformat()))
    db.commit()
    flash("Solicitação de agendamento enviada!", "success")
    return redirect(url_for("public_page", slug=slug))

def available_times_for_request(db, business, day, hour):
    schedule = db.execute("SELECT * FROM schedules WHERE business_id=? AND weekday=?",
                          (business["id"], day.weekday())).fetchone()
    if not schedule or not schedule["enabled"]:
        return False
    if db.execute("SELECT 1 FROM blocked_dates WHERE business_id=? AND blocked_date=?",
                  (business["id"], day.isoformat())).fetchone():
        return False
    start = datetime.strptime(schedule["start_time"], "%H:%M")
    end = datetime.strptime(schedule["end_time"], "%H:%M")
    chosen = datetime.strptime(hour, "%H:%M")
    interval = business["interval_minutes"] or 30
    if chosen < start or chosen >= end or (chosen-start).seconds // 60 % interval:
        return False
    return not db.execute("""SELECT 1 FROM appointments WHERE business_id=? AND appointment_date=?
        AND appointment_time=? AND status IN ('pending','confirmed')""",
        (business["id"], day.isoformat(), hour)).fetchone()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    )
   