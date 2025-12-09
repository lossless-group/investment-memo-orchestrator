# Papermark Self-Hosted Dataroom Deployment

## Goal

Deploy **Papermark** as a self-hosted, open-source virtual data room (VDR) solution for sharing investment memos, pitch decks, and due diligence documents with LPs and portfolio companies.

**Fork Repository:** `https://github.com/lossless-group/papermark.git`

This document provides a complete deployment specification for Railway, including solutions to common issues and alternative deployment options.

---

## What is Papermark?

[Papermark](https://github.com/mfts/papermark) is an open-source alternative to DocSend that provides:

- **Secure Document Sharing**: Distribute documents through custom URLs with granular access controls
- **Analytics**: Page-by-page tracking, visitor engagement metrics, real-time notifications
- **Virtual Data Rooms**: Unlimited branded data rooms with document-level permissions
- **Custom Branding**: Custom domains, white-labeling, brand-specific viewer experiences
- **Security**: AES-256 encryption, dynamic watermarking, password protection, NDA signing
- **Self-Hosted**: Full control over data with GDPR/CCPA compliance

### Use Cases for Investment Memos

1. **LP Data Rooms**: Share fund documents, PPMs, track records securely with prospective LPs
2. **Portfolio Company Sharing**: Distribute investment memos to stakeholders with view tracking
3. **Due Diligence Rooms**: Create secure spaces for deal documents with audit trails
4. **Investor Updates**: Share quarterly reports with analytics on engagement

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| **Framework** | Next.js (React) |
| **Language** | TypeScript |
| **Styling** | Tailwind CSS, shadcn/ui |
| **Database** | PostgreSQL |
| **ORM** | Prisma |
| **Authentication** | NextAuth.js (Google, GitHub OAuth) |
| **Blob Storage** | AWS S3 or Vercel Blob |
| **Analytics** | Tinybird (optional) |
| **Email** | Resend |
| **Payments** | Stripe (optional) |

---

## Deployment Issue: "No Start Command Was Found"

### Problem

When deploying the Papermark fork to Railway, the following error occurs:

```
[Region: us-east4]

Railpack 0.15.1

↳ Detected Python
↳ Using pipenv

No start command was found
```

### Root Cause

Railway's Railpack detected **Python instead of Node.js** because:

1. Papermark includes a `Pipfile` for Tinybird analytics (Python-based CLI)
2. Railpack saw Python files first and assumed it was a Python project
3. Python projects require explicit start commands (e.g., `uvicorn`, `gunicorn`)

### Solution

Force Railway to recognize this as a **Node.js/Next.js** project by:

1. Creating a `railway.json` configuration file
2. Explicitly specifying build and start commands
3. Optionally removing or relocating Python files

---

## Railway Deployment Configuration

### Step 1: Create `railway.json`

Add this file to your repository root:

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "npm install && npm run build"
  },
  "deploy": {
    "startCommand": "npx prisma migrate deploy && npm start",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

**Key configurations:**
- `builder: "NIXPACKS"`: Explicitly use Nixpacks (better Node.js detection)
- `buildCommand`: Installs dependencies and builds Next.js
- `startCommand`: Runs database migrations then starts the production server
- `restartPolicyType`: Automatically restarts on failure

### Step 2: Verify `package.json` Scripts

Ensure your `package.json` contains these scripts:

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "postinstall": "prisma generate",
    "db:migrate": "prisma migrate deploy"
  },
  "engines": {
    "node": ">=18.17.0"
  }
}
```

**Critical scripts:**
- `postinstall`: Generates Prisma Client after `npm install`
- `build`: Creates production `.next` directory
- `start`: Runs `next start` (requires build to exist)

### Step 3: Create `.railpackignore` (Optional)

To prevent Railpack from detecting Python, add:

```
lib/tinybird/
Pipfile
Pipfile.lock
*.py
```

Alternatively, delete the `lib/tinybird/` directory if you don't need analytics.

### Step 4: Set Root Directory (If Monorepo)

If Papermark is in a subdirectory, configure in Railway dashboard:

**Settings > Source > Root Directory** → Set to `/papermark` or wherever the `package.json` lives

---

## Environment Variables

### Required Variables

Set these in Railway's **Variables** tab:

```bash
# Node Environment
NODE_ENV=production

# Database (Railway PostgreSQL Plugin will auto-provide)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Authentication
NEXTAUTH_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}
NEXTAUTH_SECRET=<generate-with: openssl rand -hex 32>

# Base URL for Links
NEXT_PUBLIC_BASE_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}
```

### Blob Storage (Choose One)

**Option A: AWS S3 (Recommended for Railway)**
```bash
AWS_ACCESS_KEY_ID=<your-aws-key>
AWS_SECRET_ACCESS_KEY=<your-aws-secret>
AWS_REGION=us-east-1
AWS_S3_BUCKET_NAME=<your-bucket-name>
```

**Option B: Vercel Blob** (Requires Vercel account)
```bash
BLOB_READ_WRITE_TOKEN=<from-vercel-storage>
```

**Recommendation:** Use AWS S3 for Railway deployments. Vercel Blob is tightly coupled to Vercel's infrastructure.

### Email (Required)

```bash
RESEND_API_KEY=<from-resend.com>
```

Create a free account at [resend.com](https://resend.com). Free tier includes 100 emails/day.

### OAuth (Optional but Recommended)

**Google OAuth:**
```bash
GOOGLE_CLIENT_ID=<from-google-cloud-console>
GOOGLE_CLIENT_SECRET=<from-google-cloud-console>
```

Setup: [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
- Callback URL: `https://your-domain.com/api/auth/callback/google`

**GitHub OAuth:**
```bash
GITHUB_CLIENT_ID=<from-github-developer-settings>
GITHUB_CLIENT_SECRET=<from-github-developer-settings>
```

Setup: [GitHub Developer Settings](https://github.com/settings/developers)
- Callback URL: `https://your-domain.com/api/auth/callback/github`

### Analytics (Optional)

```bash
TINYBIRD_TOKEN=<from-tinybird.co>
```

**Note:** Tinybird is optional for basic functionality. You can skip this for initial deployment.

### Payments (Optional)

```bash
STRIPE_SECRET_KEY=<from-stripe.com>
STRIPE_PUBLISHABLE_KEY=<from-stripe.com>
STRIPE_WEBHOOK_SECRET=<from-stripe.com>
```

---

## Step-by-Step Railway Deployment

### 1. Provision Railway Services

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Create new project
railway init
```

In Railway dashboard:
1. Click **+ New** → **Database** → **PostgreSQL**
2. Note that `DATABASE_URL` will be auto-provided

### 2. Configure Repository

```bash
# Clone your fork
git clone https://github.com/lossless-group/papermark.git
cd papermark

# Create railway.json (as shown above)
# Add .railpackignore (optional)

# Commit changes
git add railway.json .railpackignore
git commit -m "Add Railway deployment configuration"
git push
```

### 3. Connect Repository

In Railway dashboard:
1. **+ New** → **GitHub Repo**
2. Select `lossless-group/papermark`
3. Railway will detect and configure automatically

### 4. Set Environment Variables

In the service settings → **Variables**:
1. Add all required variables from the list above
2. Reference PostgreSQL with `${{Postgres.DATABASE_URL}}`
3. Reference domain with `${{RAILWAY_PUBLIC_DOMAIN}}`

### 5. Initial Deployment

Railway will automatically:
1. Clone repository
2. Detect Node.js (with `railway.json`)
3. Run `npm install` → `prisma generate` (postinstall) → `npm run build`
4. Run `prisma migrate deploy` → `npm start`

### 6. Verify Deployment

```bash
# Check logs
railway logs

# Open deployed app
railway open
```

### 7. Configure Custom Domain

In Railway service settings → **Networking**:
1. Click **+ Custom Domain**
2. Add your domain (e.g., `dataroom.yourfirm.com`)
3. Configure DNS CNAME record
4. Update `NEXTAUTH_URL` and `NEXT_PUBLIC_BASE_URL` to use custom domain

---

## Known Issues & Solutions

### Issue 1: Cookie Domain for Authentication

**Problem:** Login succeeds but redirects fail (session cookie domain mismatch)

**Solution:** Modify NextAuth cookie domain configuration:

In `pages/api/auth/[...nextauth].ts` or similar:
```typescript
cookies: {
  sessionToken: {
    name: `__Secure-next-auth.session-token`,
    options: {
      domain: process.env.NEXT_PUBLIC_BASE_URL
        ? `.${new URL(process.env.NEXT_PUBLIC_BASE_URL).hostname}`
        : undefined,
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      secure: true,
    },
  },
}
```

### Issue 2: Prisma Migration Failures

**Problem:** `prisma migrate deploy` fails on first run

**Solution:** Ensure Prisma is in `dependencies` (not just `devDependencies`):

```json
{
  "dependencies": {
    "prisma": "^5.x.x",
    "@prisma/client": "^5.x.x"
  }
}
```

### Issue 3: Build Memory Issues

**Problem:** Next.js build fails with out-of-memory errors

**Solution:** Increase Railway service memory limit:
- Railway dashboard → Service → Settings → **Resources** → Increase memory

Or add to `next.config.js`:
```javascript
module.exports = {
  experimental: {
    workerThreads: false,
    cpus: 1,
  },
}
```

### Issue 4: S3 CORS Configuration

**Problem:** Document uploads fail with CORS errors

**Solution:** Configure S3 bucket CORS:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
    "AllowedOrigins": ["https://your-domain.com"],
    "ExposeHeaders": ["ETag"]
  }
]
```

### Issue 5: Nginx Reverse Proxy (If Using)

**Problem:** WebSocket connections fail behind Nginx

**Solution:** Configure Nginx for WebSocket support:

```nginx
location / {
    proxy_pass http://localhost:3000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_cache_bypass $http_upgrade;
    proxy_buffering off;
    proxy_read_timeout 300s;
}
```

---

## Cost Estimates

### Railway Costs (Monthly)

| Service | Free Tier | Pro Tier |
|---------|-----------|----------|
| **App Hosting** | $0-5 | $20 base + usage |
| **PostgreSQL** | Included | Included |
| **Bandwidth** | 100GB | Unlimited |

### External Services (Monthly)

| Service | Free Tier | Paid |
|---------|-----------|------|
| **AWS S3** | 5GB | ~$0.023/GB |
| **Resend** | 100 emails/day | $20+ |
| **Tinybird** | 10M rows/mo | $29+ |
| **Stripe** | N/A | 2.9% + $0.30/txn |

**Estimated Total:**
- Minimal: ~$10-15/month
- Full features: ~$50-80/month

---

## Alternative Deployment Options

If Railway proves challenging:

### Vercel (Papermark's Native Platform)

**Pros:** Designed for Papermark, automatic setup, native Vercel Blob
**Cons:** Vendor lock-in, serverless constraints, higher cost at scale
**Difficulty:** Easy

```bash
# One-click deploy
npx vercel
```

### Docker (Self-Hosted)

**Dockerfile** (community-provided, may need customization):

```dockerfile
FROM node:18-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npx prisma generate
RUN npm run build

FROM node:18-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/next.config.js ./
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/prisma ./prisma

EXPOSE 3000
ENV PORT 3000

CMD ["node", "server.js"]
```

**Note:** Add to `next.config.js`:
```javascript
module.exports = {
  output: 'standalone',
}
```

### DigitalOcean App Platform

Similar to Railway with good PostgreSQL integration. Set build/run commands in app spec.

---

## Licensing Considerations

**Personal/Non-Commercial:** Free under AGPLv3

**Commercial Use:** Requires self-hosting license from Papermark team for:
- Team/company deployments
- Advanced security features
- Data room functionality beyond basic features

Contact: https://www.papermark.com for commercial licensing

---

## Integration with Investment Memo Orchestrator

Once deployed, Papermark can serve as the distribution platform for generated memos:

### Workflow Integration

```
1. Generate memo with orchestrator
   → output/Company-v0.0.x/4-final-draft.md

2. Export to HTML/PDF
   → python export-branded.py memo.md --brand hypernova

3. Upload to Papermark
   → Create data room for Company
   → Add memo document
   → Generate shareable link with analytics

4. Distribute to stakeholders
   → Track engagement per page
   → Monitor which sections receive attention
   → Identify follow-up interests
```

### Future Integration Points

- **API Integration**: Auto-upload generated memos via Papermark API
- **Analytics Feedback**: Use view data to improve memo sections
- **Custom Branding**: Match Papermark branding to firm templates
- **Access Control**: Integrate with LP relationship management

---

## Publishing a Railway Template

Once your Papermark deployment works, you can publish it as a reusable template for others (or yourself) to one-click deploy.

### Why Create a Template?

- **One-click deploys**: Share a button that provisions everything automatically
- **Reproducible**: Same configuration every time
- **Monetization**: Railway offers up to 50% kickbacks for open-source templates
- **Updates**: Users get notified when you push updates to your repo

### Step 1: Deploy a Working Project First

Before creating a template, ensure you have a **working Railway project** with:
- All services configured (app + PostgreSQL)
- Environment variables set
- Successful deployment

### Step 2: Create Template from Project

**Option A: Convert Existing Project**
1. Go to your Railway project
2. **Settings** → **Generate Template from Project**
3. Railway captures your entire infrastructure as a template

**Option B: Build from Scratch**
1. Go to **Workspace Settings** → **Templates**
2. Click **New Template**
3. Add services manually (GitHub repo + PostgreSQL)

### Step 3: Configure Template Services

For each service, configure:

**App Service (Papermark):**
```
Source: https://github.com/lossless-group/papermark/tree/deploy
```

**Variables Tab** - Define required environment variables:
```bash
# Use Railway's template variable functions
DATABASE_URL=${{Postgres.DATABASE_URL}}
NEXTAUTH_SECRET=${{secret(32)}}
NEXTAUTH_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}
NEXT_PUBLIC_BASE_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}

# User must provide these
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_S3_BUCKET_NAME=
AWS_REGION=us-east-1
RESEND_API_KEY=

# Optional
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

**Settings Tab:**
- Root Directory: `/` (or subdirectory if monorepo)
- Start Command: `npx prisma migrate deploy && npm start`
- Build Command: `npm install && npm run build`

**PostgreSQL Service:**
- Add from Railway's database plugins
- Railway auto-provides `DATABASE_URL`

### Step 4: Template Variable Functions

Railway provides special functions for generating values at deploy time:

| Function | Description | Example |
|----------|-------------|---------|
| `secret(length)` | Random string | `${{secret(32)}}` |
| `secret(length, alphabet)` | Custom alphabet | `${{secret(16, "hex")}}` |
| `randomInt(min, max)` | Random integer | `${{randomInt(1000, 9999)}}` |

**Example for NEXTAUTH_SECRET:**
```
NEXTAUTH_SECRET=${{secret(32)}}
```

### Step 5: Publish to Marketplace

1. Go to **Workspace Settings** → **Templates**
2. Find your template → Click **Publish**
3. Fill out the form:
   - **Name**: `Papermark - Open Source Data Room`
   - **Description**: Brief explanation
   - **Category**: Select appropriate category
   - **Demo URL**: Link to a working instance (optional)

### Step 6: Get Your Deploy Button

After publishing, Railway provides:

**Template URL:**
```
https://railway.com/new/template/YOUR_TEMPLATE_ID
```

**Markdown Button:**
```markdown
[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/YOUR_TEMPLATE_ID?referralCode=YOUR_CODE)
```

**HTML Button:**
```html
<a href="https://railway.com/new/template/YOUR_TEMPLATE_ID?referralCode=YOUR_CODE">
  <img src="https://railway.com/button.svg" alt="Deploy on Railway" />
</a>
```

### Step 7: Add to Your README

In your fork's `README.md`:

```markdown
## One-Click Deploy

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/YOUR_TEMPLATE_ID?referralCode=lossless)

### What Gets Deployed
- Papermark Next.js application
- PostgreSQL database
- Automatic Prisma migrations

### You'll Need to Provide
- AWS S3 credentials (for document storage)
- Resend API key (for emails)
- OAuth credentials (optional, for Google/GitHub login)
```

### Template Updates

When you push changes to your `deploy` branch:
1. Railway detects the update
2. Users who deployed your template get notified
3. They can choose to apply the update

**Important:** Only GitHub-based templates support auto-updates. Docker image templates don't.

### Monetization (Optional)

Railway's kickback program:
- Up to **50% kickbacks** for open-source templates
- Based on deployment activity and support engagement
- Become a **Technology Partner** for verified status

Apply at: [Railway Partners](https://railway.com/partners)

---

## Next Steps

1. **Immediate**: Add `railway.json` to fork, redeploy to Railway
2. **Short-term**: Configure AWS S3, Resend, OAuth providers
3. **Medium-term**: Set up custom domain, test document workflows
4. **Long-term**: Explore API integration with memo orchestrator

---

## References

- [Papermark GitHub Repository](https://github.com/mfts/papermark)
- [Papermark Self-Hosting Guide](https://www.papermark.com/help/article/self-hosting)
- [Railway Documentation](https://docs.railway.com)
- [Railway Config as Code](https://docs.railway.com/reference/config-as-code)
- [Railway "No Start Command" Error](https://docs.railway.com/reference/errors/no-start-command-could-be-found)
- [Prisma Railway Deployment](https://www.prisma.io/docs/orm/prisma-client/deployment/traditional/deploy-to-railway)
- [NextAuth.js Documentation](https://next-auth.js.org)
- [Self-Hosting Issue #1566](https://github.com/mfts/papermark/issues/1566)
- [Railway Create Template Guide](https://docs.railway.com/guides/create)
- [Railway Publish and Share Templates](https://docs.railway.com/guides/publish-and-share)
- [Railway Templates Reference](https://docs.railway.com/reference/templates)
