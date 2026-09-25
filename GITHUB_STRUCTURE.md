# POLARLOGIX — GitHub Project Structure

This repository is organized for direct GitHub upload.

```text
POLARLOGIX/
├── .github/
│   └── workflows/
│       └── ci.yml
├── app/
│   ├── routers/
│   ├── services/
│   ├── main.py
│   ├── models.py
│   ├── db.py
│   ├── config.py
│   ├── security.py
│   ├── audit.py
│   ├── serializers.py
│   ├── seed.py
│   └── demo.py
├── static/
│   ├── css/
│   ├── js/
│   ├── icons/
│   ├── index.html
│   ├── login.html
│   ├── manifest.webmanifest
│   └── sw.js
├── data/
│   ├── geo/
│   ├── *.csv
│   ├── routes.json
│   └── cargo_rules.json
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API.md
│   └── DATA.md
├── scripts/
│   ├── run_dev.sh
│   ├── generate_data.py
│   ├── build_geo.py
│   └── reset_db.py
├── tests/
│   ├── conftest.py
│   └── test_services.py
├── .github/workflows/ci.yml
├── .dockerignore
├── .gitignore
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── render.yaml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

## Upload to GitHub

Upload the **contents of this folder** as the repository root. Do not create another
`POLARLOGIX/POLARLOGIX/` nested folder.

Keep `.env` out of GitHub. Use `.env.example` as the template for local configuration.
