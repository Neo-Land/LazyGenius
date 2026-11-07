# Deploying the public demo

The demo is read-only, serves only the MIT sample lectures, and needs no API key. Never deploy the full app
publicly: it has no accounts. Dashboards change, so button names may differ slightly.

## 1. API on Render
1. Sign in at [render.com](https://render.com) with GitHub.
2. Click **New**, then **Web Service**, and pick the `LazyGenius` repo.
3. Set **Language** to **Docker**, **Branch** to `main`, and **Instance Type** to **Free**.
4. Leave the Docker settings at their defaults. `Dockerfile` builds the read-only demo by default.
5. Add one environment variable for now: `HARNESS_CORS_ORIGINS` = `http://localhost:3000`.
6. Click **Deploy Web Service**. When it's live, copy its URL and check that `<url>/health` shows `{"ok":true}`.

## 2. Web app on Vercel
1. Sign in at [vercel.com](https://vercel.com) with GitHub.
2. Click **Add New**, then **Project**, and import `LazyGenius`.
3. Set **Root Directory** to `web`.
4. Add the environment variable `NEXT_PUBLIC_API_URL` with your Render URL, with no trailing slash.
5. Click **Deploy** and copy the site's URL.

## 3. Connect them
1. In Render, set `HARNESS_CORS_ORIGINS` to your Vercel URL, with no trailing slash. It redeploys by itself.
2. Open the Vercel URL, click the sample course, open a lecture, click a citation, and ask a question.

Pushes to `main` now redeploy both.

## 4. Release
When the demo works, tag `v1.0.0` after moving the `[Unreleased]` changelog notes under `## [1.0.0]`. The
Release workflow runs CI, builds the images, and publishes the release.

## Using real AI in the demo
Don't do this until a live eval has run. Set a low spend limit on a dedicated Anthropic key first. Limits in
the app reset whenever the server restarts, so the key's limit is the real cap. See ADR 0006.

## Troubleshooting
| What you see | Likely cause |
|---|---|
| "Can't reach the API" | `NEXT_PUBLIC_API_URL` is wrong, or Render is waking up (wait a minute) |
| Browser console mentions CORS | `HARNESS_CORS_ORIGINS` doesn't exactly match the Vercel URL |
| Changed `NEXT_PUBLIC_API_URL` and nothing happened | Redeploy on Vercel, since it's read at build time |
