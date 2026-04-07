# Brightbean

Open-source, self-hostable social media management platform built for agencies and SMBs. Supports Facebook, Instagram, LinkedIn, TikTok, YouTube, Pinterest, Threads, Bluesky, Google Business Profile, and Mastodon.

## Quick Start (Docker)

```bash
git clone https://github.com/brightbeanxyz/brightbean-social-management.git
cd brightbean-social-management
cp .env.example .env
```

Edit `.env` — change `DATABASE_URL` to point to the Docker service name:

```
DATABASE_URL=postgres://postgres:postgres@postgres:5432/brightbean
```

Then start everything:

```bash
docker compose up -d
docker compose exec app python manage.py migrate
docker compose exec app python manage.py createsuperuser
```

Open http://localhost:8000 — you're running.

## Local Development (without Docker for the app)

Use Docker only for PostgreSQL, run Django on your host for faster iteration.

### Prerequisites

- Python 3.12+
- Node.js 20+ (for Tailwind CSS)
- Docker (for PostgreSQL)

### Setup

**1. Clone and configure**

```bash
git clone https://github.com/brightbeanxyz/brightbean-social-management.git
cd brightbean-social-management
cp .env.example .env
```

The default `.env` is ready for local development — `DATABASE_URL` points to `localhost:5432` which is correct when running Django on your host.

**2. Start PostgreSQL**

```bash
docker compose up postgres -d
```

Verify it's running:

```bash
docker compose ps
# postgres should show "healthy"
```

**3. Set up Python**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**4. Set up Tailwind CSS**

```bash
cd theme/static_src
npm install
cd ../..
```

**5. Run database migrations**

```bash
python manage.py migrate
```

**6. Create your admin account**

```bash
python manage.py createsuperuser
```

**7. Start the app (3 terminal tabs)**

Tab 1 — Tailwind watcher (recompiles CSS on template changes):
```bash
cd theme/static_src && npm run start
```

Tab 2 — Django dev server:
```bash
source .venv/bin/activate
python manage.py runserver
```

Tab 3 — Background worker (processes scheduled posts, inbox sync, etc.):
```bash
source .venv/bin/activate
python manage.py process_tasks
```

Open http://localhost:8000 and log in with the superuser you created.

### What each process does

| Process | Command | Purpose |
|---------|---------|---------|
| **Web server** | `python manage.py runserver` | Serves the Django app |
| **Worker** | `python manage.py process_tasks` | Runs background jobs (publishing, inbox sync, analytics collection) |
| **Tailwind** | `npm run start` (in `theme/static_src/`) | Watches templates and recompiles CSS |
| **PostgreSQL** | `docker compose up postgres -d` | Database |

### Daily workflow

After initial setup, your daily startup is:

```bash
docker compose up postgres -d           # start DB (if not running)
source .venv/bin/activate                # activate Python env
python manage.py runserver               # start web server
# (open another tab)
python manage.py process_tasks           # start worker
```

Tailwind watcher is only needed when you're editing templates/CSS.

## Fully Local Development (without Docker)

Run everything natively — no Docker, no PostgreSQL install. Uses SQLite for the database.

### Prerequisites

- Python 3.12+
- Node.js 20+

### Setup

**1. Clone and configure**

```bash
git clone https://github.com/brightbeanxyz/brightbean-social-management.git
cd brightbean-social-management
cp .env.example .env
```

**2. Switch to SQLite**

Open `.env` and replace the `DATABASE_URL` line:

```
DATABASE_URL=sqlite:///db.sqlite3
```

That's it — no database server to install or manage.

**3. Set up Python**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**4. Set up Tailwind CSS**

```bash
cd theme/static_src
npm install
cd ../..
```

**5. Run database migrations**

```bash
python manage.py migrate
```

**6. Create your admin account**

```bash
python manage.py createsuperuser
```

**7. Start the app (3 terminal tabs)**

Tab 1 — Tailwind watcher:
```bash
cd theme/static_src && npm run start
```

Tab 2 — Django dev server:
```bash
source .venv/bin/activate
python manage.py runserver
```

Tab 3 — Background worker:
```bash
source .venv/bin/activate
python manage.py process_tasks
```

Open http://localhost:8000 and log in with the superuser you created.

### Daily workflow (Docker-free)

```bash
source .venv/bin/activate                # activate Python env
python manage.py runserver               # start web server
# (open another tab)
python manage.py process_tasks           # start worker
```

> **Note:** SQLite is perfect for local development and small deployments. For production or heavy concurrent usage, switch to PostgreSQL.

## Running Tests

```bash
pytest
```

With coverage:

```bash
pytest --cov=apps --cov-report=term-missing
```

## Linting & Type Checking

```bash
ruff check .                             # lint
ruff format --check .                    # format check
mypy apps/ config/ --ignore-missing-imports  # type check
```

Auto-fix lint issues:

```bash
ruff check --fix .
ruff format .
```

## Production Deployment

### Docker Compose on a VPS (recommended)

```bash
# On your server:
git clone https://github.com/brightbeanxyz/brightbean-social-management.git
cd brightbean-social-management
cp .env.example .env
# Edit .env:
#   SECRET_KEY=<generate a random 50+ char string>
#   DEBUG=false
#   ALLOWED_HOSTS=yourdomain.com
#   APP_URL=https://yourdomain.com
#   DATABASE_URL=postgres://postgres:<strong-password>@postgres:5432/brightbean

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
docker compose exec app python manage.py migrate
docker compose exec app python manage.py createsuperuser
```

This starts 4 containers: app (Gunicorn), worker, PostgreSQL, and Caddy (auto-HTTPS). Edit the `Caddyfile` with your domain.

To update:

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec app python manage.py migrate
```

### Other Platforms

| Platform | Config file | Notes |
|----------|-------------|-------|
| **Heroku** | `Procfile` + `app.json` | Deploy-button ready. Must use Basic+ dynos (Eco dynos break the worker). |
| **Railway** | `railway.toml` | Three services: web, worker, managed PostgreSQL. |
| **Render** | `render.yaml` | Blueprint with web, worker, PostgreSQL. Must use paid tier. |

All platforms with ephemeral filesystems require `STORAGE_BACKEND=s3` — see `.env.example` for S3 configuration.

See `architecture.md` for detailed per-platform instructions and cost breakdowns.

## Project Structure

```
brightbean-social-management/
├── config/
│   ├── settings/
│   │   ├── base.py            # Shared settings
│   │   ├── development.py     # Local dev overrides
│   │   ├── production.py      # Production hardening
│   │   └── test.py            # Test overrides
│   ├── urls.py                # Root URL configuration
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── accounts/              # Custom User model, auth, OAuth, sessions
│   ├── organizations/         # Organization management
│   ├── workspaces/            # Workspace CRUD
│   ├── members/               # RBAC, invitations, middleware, decorators
│   ├── settings_manager/      # Configurable defaults with cascade logic
│   ├── credentials/           # Platform API credential storage (encrypted)
│   └── common/                # Shared: encrypted fields, scoped model managers
├── providers/                 # Social platform API modules (one file per platform)
├── templates/                 # Django templates
│   ├── base.html              # Layout with sidebar + nav
│   └── components/            # Reusable HTMX partials
├── static/
│   └── js/                    # Vendored HTMX + Alpine.js
├── theme/                     # django-tailwind theme app
│   └── static_src/
│       ├── src/styles.css     # Tailwind directives
│       └── tailwind.config.js
├── Dockerfile
├── docker-compose.yml         # Dev: app + worker + postgres
├── docker-compose.prod.yml    # Prod override: adds Caddy, uses Gunicorn
├── Caddyfile                  # Reverse proxy + auto-HTTPS config
├── .env.example               # All environment variables
├── Procfile                   # Heroku
├── app.json                   # Heroku deploy button
├── railway.toml               # Railway config
└── render.yaml                # Render blueprint
```

## Environment Variables

All configuration is via environment variables. See `.env.example` for the full list.

Key variables for local development:

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (required) | Django secret key. Any random string for dev. |
| `DEBUG` | `false` | Set to `true` for local development. |
| `DATABASE_URL` | — | PostgreSQL connection string. |
| `STORAGE_BACKEND` | `local` | `local` for filesystem, `s3` for S3-compatible storage. |
| `EMAIL_BACKEND_TYPE` | `smtp` | Set to `smtp` for SMTP or leave default (console in dev). |

## Platform Credentials

To connect social media accounts, you need API credentials from each platform's developer portal. You can set these via environment variables in `.env` (see `.env.example`) or through the admin UI at **Settings → Platform Credentials**.

**Redirect URI:** When registering your app on any platform, set the OAuth redirect URI to:

```
{APP_URL}/social-accounts/callback/{platform}/
```

For example, if your `APP_URL` is `https://brightbean.example.com`, the Facebook redirect URI would be `https://brightbean.example.com/social-accounts/callback/facebook/`.

### Meta (Facebook, Instagram, Threads)

Facebook, Instagram, and Threads all use the same Meta app credentials.

1. Go to [Meta for Developers](https://developers.facebook.com/) and create a new app (type: **Business**)
2. Under **App Settings → Basic**, copy your **App ID** and **App Secret**
3. In the App Dashboard, go to **Use cases** and add the following four use cases. For each use case, click into it and go to **Permissions and features** to add the required optional permissions:

   **Use case: "Manage everything on your Page"** (Facebook)
   - This use case auto-includes `business_management`, `pages_show_list`, and `public_profile`
   - Add these optional permissions: `pages_manage_posts`, `pages_read_engagement`, `pages_read_user_content`, `pages_manage_metadata`

   **Use case: "Messenger from Meta"** (Facebook Messaging)
   - Required to enable the `pages_messaging` permission, which is not available under the "Manage Pages" use case
   - Add the optional permission: `pages_messaging`

   **Use case: "Manage messaging & content on Instagram"** (Instagram)
   - Add these permissions: `instagram_basic`, `instagram_content_publish`, `instagram_manage_comments`, `instagram_manage_insights`

   **Use case: "Access the Threads API"** (Threads)
   - This use case auto-includes `threads_basic`
   - Add these optional permissions: `threads_content_publish`, `threads_manage_insights`, `threads_manage_replies`

4. Under **Facebook Login → Settings → Valid OAuth Redirect URIs**, add the following redirect URIs:
   ```
   {APP_URL}/social-accounts/callback/facebook/
   {APP_URL}/social-accounts/callback/instagram/
   {APP_URL}/social-accounts/callback/threads/
   ```
5. Set the environment variables:
   ```
   PLATFORM_FACEBOOK_APP_ID=your-app-id
   PLATFORM_FACEBOOK_APP_SECRET=your-app-secret
   ```

### Instagram (Personal Account)

The Instagram (Personal) connector uses the **Instagram API with Instagram Login** — a separate OAuth flow from the Facebook Login-based Instagram connector above. This supports personal, creator, and business Instagram accounts without requiring a linked Facebook Page.

1. In the same Meta app, go to **Use cases** and add the **"Instagram API"** use case
2. Under **API setup with Instagram Login**, note your **Instagram App ID** and **Instagram App Secret** (these are different from your Facebook App ID/Secret)
3. Go to **Permissions and features** and add the required permissions:
   - `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_comments`, `instagram_business_manage_messages`
4. Under **API setup with Instagram Login → Step 4: Set up Instagram business login**, click **Set up** and add the redirect URI:
   ```
   {APP_URL}/social-accounts/callback/instagram_personal/
   ```
5. Set the environment variables:
   ```
   PLATFORM_INSTAGRAM_APP_ID=your-instagram-app-id
   PLATFORM_INSTAGRAM_APP_SECRET=your-instagram-app-secret
   ```

### LinkedIn

Brightbean uses a **single LinkedIn app** (with Community Management API) for both personal profile and Company Page connections — each flow simply requests different OAuth scopes. The connect page shows two cards: *LinkedIn (Personal Profile)* and *LinkedIn (Company Page)*.

1. Go to the [LinkedIn Developer Portal](https://developer.linkedin.com/) and create a new app
2. Verify your app's association with a LinkedIn Company Page
3. Under **Products**, request access to:
   - **Community Management API** *(restricted — requires LinkedIn review)*
4. Under **Auth**, add **both** redirect URIs:
   ```
   {APP_URL}/social-accounts/callback/linkedin_personal/
   {APP_URL}/social-accounts/callback/linkedin_company/
   ```
5. Scopes are requested per connection type:
   - **Personal profile:** `r_basicprofile`, `w_member_social`, `r_member_social`
   - **Company page:** `r_basicprofile`, `w_member_social`, `w_organization_social`, `r_organization_social`, `rw_organization_admin`
6. Set the environment variables:
   ```
   PLATFORM_LINKEDIN_CLIENT_ID=your-client-id
   PLATFORM_LINKEDIN_CLIENT_SECRET=your-client-secret
   ```

> **Refresh tokens:** Community Management API provides refresh tokens natively (365-day lifetime, access tokens last 60 days). No Advertising API product is needed. Note: the **Share on LinkedIn** and **Community Management API** products are mutually exclusive on the same app — use Community Management API as it covers both personal and organization scopes.

### TikTok

1. Go to the [TikTok Developer Portal](https://developers.tiktok.com/) and create a new app
2. Add the products **Login Kit**, **Content Posting API**, and **Comment API**
3. Configure the redirect URI under your app's settings:
   ```
   {APP_URL}/social-accounts/callback/tiktok/
   ```
4. Required scopes: `user.info.basic`, `video.publish`, `video.upload`, `comment.list`, `comment.list.manage`
5. Note: TikTok uses **Client Key** (not Client ID). Copy the **Client Key** and **Client Secret** from your app dashboard
6. Set the environment variables:
   ```
   PLATFORM_TIKTOK_CLIENT_KEY=your-client-key
   PLATFORM_TIKTOK_CLIENT_SECRET=your-client-secret
   ```

### Google (YouTube, Google Business Profile)

YouTube and Google Business Profile share the same Google Cloud credentials.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a new project (or select an existing one)
2. Enable the following APIs under **APIs & Services → Library**:
   - **YouTube Data API v3** (for YouTube)
   - **My Business Account Management API**, **My Business Business Information API**, and **Google My Business API** (for Google Business Profile)
3. Go to **APIs & Services → Credentials** and create an **OAuth 2.0 Client ID** (type: Web application)
4. Add the following redirect URIs under **Authorized redirect URIs**:
   ```
   {APP_URL}/social-accounts/callback/youtube/
   {APP_URL}/social-accounts/callback/google_business/
   ```
5. Copy the **Client ID** and **Client Secret**
6. Required scopes:
   - **YouTube:** `https://www.googleapis.com/auth/youtube.upload`, `https://www.googleapis.com/auth/youtube.readonly`, `https://www.googleapis.com/auth/youtube.force-ssl`
   - **Google Business Profile:** `https://www.googleapis.com/auth/business.manage`
7. Set the environment variables:
   ```
   PLATFORM_GOOGLE_CLIENT_ID=your-client-id
   PLATFORM_GOOGLE_CLIENT_SECRET=your-client-secret
   ```

### Pinterest

1. Go to the [Pinterest Developer Portal](https://developers.pinterest.com/) and create a new app
2. Under your app settings, add the redirect URI:
   ```
   {APP_URL}/social-accounts/callback/pinterest/
   ```
3. Copy the **App ID** and **App Secret**
4. Required scopes: `boards:read`, `pins:read`, `pins:write`
5. Set the environment variables:
   ```
   PLATFORM_PINTEREST_APP_ID=your-app-id
   PLATFORM_PINTEREST_APP_SECRET=your-app-secret
   ```

### Bluesky

No developer app registration needed. Users connect by entering their Bluesky handle and an **App Password**:

1. Log in to [Bluesky](https://bsky.app/)
2. Go to **Settings → App Passwords**
3. Create a new app password and use it when connecting your account in Brightbean

### Mastodon

No developer app registration needed. Brightbean automatically registers an OAuth application on each Mastodon instance when a user connects their account. Users just need to enter their instance URL (e.g., `mastodon.social`).

## Inbox Support

| Platform | Fetch Comments | Reply to Comments | DMs |
|----------|---------------|-------------------|-----|
| Facebook | Yes | Yes | Yes |
| Instagram | Yes | Yes | Yes |
| YouTube | Yes | Yes | No |
| LinkedIn | Yes | Yes | No |
| TikTok | Yes | Yes* | No |
| Mastodon | Yes | Yes | No |

\*TikTok replies require the `comment.list.manage` scope, which must be approved by TikTok.

### Backfill Historical Messages

To import historical messages (e.g., from the last 7 days):

```bash
python manage.py backfill_inbox --days 7
```

Options:
- `--days N` — Number of days to backfill (default: 7)
- `--platform NAME` — Only backfill a specific platform (e.g., `youtube`, `linkedin`, `tiktok`)
- `--account-id UUID` — Only backfill a specific account

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.x, Django REST Framework |
| Frontend | Django templates, HTMX, Alpine.js |
| CSS | Tailwind CSS 4 via django-tailwind |
| Database | PostgreSQL 16+ |
| Background jobs | django-background-tasks (no Redis required) |
| Auth | django-allauth (email + Google OAuth) |
| Media | Pillow (images), FFmpeg (video) |
| Deployment | Docker, Gunicorn, Caddy |

## License

See [LICENSE](LICENSE) for details.
