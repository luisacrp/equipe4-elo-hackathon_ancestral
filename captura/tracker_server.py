"""
tracker_server.py — endpoint de captura (protótipo)
----------------------------------------------------
Recebe os eventos enviados pelo tracker.js e grava em eventos_live.csv,
com as MESMAS colunas de acessos_simulados.csv — por isso o dashboard
(app.py) consegue ler os dois lados lado a lado sem transformação.

Em produção isso é API Gateway → Lambda Node → armazenamento
(ver diagrama_arquitetura.svg). Aqui é Flask + CSV para poder gravar
o vídeo de demonstração sem depender de nuvem.

Rodar:
    pip install -r requirements_tracker.txt
    python tracker_server.py
    # abre em http://localhost:5000  (serve também a portal_demo.html)
"""

import csv
import os
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# eventos_live.csv fica em ../dados, junto dos outros CSVs, para que
# app.py (em ../app) e este servidor leiam/gravem sempre o mesmo arquivo.
DADOS_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "dados"))
CSV_PATH = os.path.join(DADOS_DIR, "eventos_live.csv")

COLUNAS = [
    "event_id", "timestamp", "session_id", "ordem_na_sessao", "pagina_entrada",
    "anonymous_id", "usuario_id", "identificado", "empresa", "cnpj_hash",
    "perfil_real", "area", "pagina", "oportunidade_id", "categoria", "modalidade",
    "enviou_proposta", "utm_source", "utm_medium", "utm_campaign", "device",
    "uf", "porte_empresa",
]

app = Flask(__name__, static_folder=BASE_DIR)


@app.after_request
def _cors(resp):
    # CORS manual — evita depender de flask-cors. Só é necessário se a
    # demo for aberta como file:// em vez de servida por este processo.
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.route("/api/track", methods=["OPTIONS"])
def track_options():
    return "", 204

_ordem_por_sessao = {}


def _proxima_ordem(session_id: str) -> int:
    _ordem_por_sessao[session_id] = _ordem_por_sessao.get(session_id, 0) + 1
    return _ordem_por_sessao[session_id]


def _garantir_csv():
    os.makedirs(DADOS_DIR, exist_ok=True)
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(COLUNAS)


@app.post("/api/track")
def track():
    dado = request.get_json(force=True, silent=True) or {}
    if not dado.get("session_id"):
        return jsonify({"ok": False, "erro": "session_id ausente"}), 400

    _garantir_csv()
    linha = {coluna: dado.get(coluna, "") for coluna in COLUNAS}
    linha["event_id"] = "LV" + uuid.uuid4().hex[:8].upper()
    linha["timestamp"] = dado.get("timestamp") or datetime.now(timezone.utc).isoformat()
    linha["ordem_na_sessao"] = _proxima_ordem(linha["session_id"])

    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=COLUNAS).writerow(linha)

    return jsonify({"ok": True, "event_id": linha["event_id"]})


@app.get("/api/events")
def events():
    if not os.path.exists(CSV_PATH):
        return jsonify([])
    with open(CSV_PATH, encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    return jsonify(linhas[-50:])


@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "portal_demo.html")


@app.get("/tracker.js")
def tracker_js():
    return send_from_directory(BASE_DIR, "tracker.js")


@app.get("/healthz")
def healthz():
    # usado pela plataforma de deploy (Render etc.) para checar se o
    # serviço está de pé; não faz parte do contrato de dados.
    return jsonify({"ok": True})


if __name__ == "__main__":
    _garantir_csv()
    # PORT é definida automaticamente por plataformas de deploy (Render,
    # Railway, Fly.io etc.) — localmente, sem essa variável, cai em 5000
    # como antes, então nada muda para quem já roda local.
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False, threaded=True)
