# Render deployment notes

- Region: Singapore
- Runtime: Python
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app`
- Health check: `/health`
- SQLite: `/var/data/feedbackhub.sqlite3`
- Disk: 1 GB persistent disk at `/var/data`
- Run a single web instance; SQLite is not shared across multiple instances.

**Cost note:** The web service can use the Free plan, but Render persistent disks are paid. A free web service without a disk will lose local SQLite data on instance replacement/redeploy.

Set `SECRET_KEY`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` in the dashboard. Then run once in the service shell:

```bash
flask --app app create-admin
```
