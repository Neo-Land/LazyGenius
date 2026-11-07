# Connecting Canvas

Optional: uploading files works without this. Sync has only been tested against a mocked Canvas, not a
real school's. Your token can read every course you're enrolled in, and your grades, so treat it like a
password. It belongs only in `.env`.

## Get a token
1. Log in to Canvas and click **Account**, then **Settings**.
2. Under **Approved Integrations**, click **New Access Token**. If that button is missing, your school has
   turned tokens off. Upload files by hand instead.
3. For **Purpose**, enter `LazyGenius`. Set an **Expires** date, such as the end of the semester.
4. Click **Generate Token** and copy it. Canvas only shows it once.
5. In `.env`, set:
   ```
   CANVAS_BASE_URL=https://yourschool.instructure.com
   CANVAS_TOKEN=paste-it-here
   ```

Check your school's acceptable use policy too, since some schools restrict automated access.

## Use it
Click **Sync with Canvas** in the web app, or run `python -m app sync`. The first sync reads up to the 5
newest lecture files per course, so with the real model it costs money per file.

Optional settings in `.env`, with entries separated by `;`:
```
CANVAS_IGNORE_COURSES=Advising;Library Orientation
CANVAS_COURSE_NAMES=CMPT-270-01=Algorithms;MATH-122=Calculus
```

## What it reads
Your active course list, each course's file list, and the PDF and PowerPoint files themselves. It never
reads grades, messages, or assignments, and it never writes anything to Canvas. Files stay in `data/`,
which git ignores.

## Revoke it
In Canvas, go to **Account**, then **Settings**, find the token under **Approved Integrations**, and click
**Delete**. Then remove it from `.env`.

## Sync on a schedule (optional)
Only on your own machine, never in public CI. To sync weekdays at 7am, run `crontab -e` and add this line,
using your own path:
```
0 7 * * 1-5 cd /path/to/LazyGenius && set -a && . ./.env && set +a && .venv/bin/python -m app sync
```
On a Mac, cron may need **Full Disk Access** in **System Settings**, then **Privacy & Security**. Each run
with the real model can cost money, so check your spend limit first.
