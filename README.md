# IBM-Bob-Hackathon

## Run locally

RECOMMENDED:
Install Docker Desktop to make running the backend easier.


**Frontend** (`client-react-vite`, port 5173):

```bash
cd client-react-vite
npm install
npm run dev
```

**Backend** (`backend-python`, port 8000):

With Docker installed, from project root: `docker compose up`

(or without Docker installed:)
```bash
cd backend-python
python -m venv .venv
.venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```



Start the backend first; the Vite dev server proxies `/api` to `localhost:8000`.