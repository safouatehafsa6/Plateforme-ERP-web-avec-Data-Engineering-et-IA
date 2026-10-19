"""Dashboard analytique des commandes a partir du dernier dataset valide de MinIO."""
import io
import json
import os
import re

import jwt
import pandas as pd
import plotly.express as px
import streamlit as st
from minio import Minio
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="ERP | Data Analytics", page_icon="📊", layout="wide")
CURATED_BUCKET = os.getenv("LAKE_CURATED_BUCKET", "curated")
LATEST_KEY = "_meta/latest_success.json"
TOKEN_SECRET = os.environ.get("DASHBOARD_TOKEN_SECRET", "")


def refuse(message):
    st.error(message)
    st.stop()


def company_from_token():
    """Entreprise autorisee = celle du jeton signe par le backend (5 min). Jamais un choix de l'utilisateur."""
    if "company_id" in st.session_state:
        return st.session_state["company_id"]
    token = st.query_params.get("t")
    if not token or not TOKEN_SECRET:
        refuse("Accès refusé. Ouvrez le Dashboard depuis la plateforme ERP.")
    try:
        claims = jwt.decode(token, TOKEN_SECRET, algorithms=["HS256"])
        company_id = int(claims.get("entrepriseId"))
        if claims.get("purpose") != "dashboard" or company_id <= 0:
            raise jwt.InvalidTokenError
    except jwt.ExpiredSignatureError:
        refuse("Lien expiré. Retournez dans l'ERP et cliquez à nouveau sur Dashboard.")
    except Exception:
        refuse("Accès refusé. Ouvrez le Dashboard depuis la plateforme ERP.")
    st.session_state["company_id"] = company_id
    st.query_params.clear()  # le jeton ne reste pas dans l'URL
    return company_id


def minio_client():
    endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000").replace("http://", "").replace("https://", "")
    return Minio(
        endpoint,
        access_key=os.environ["MINIO_ROOT_USER"],
        secret_key=os.environ["MINIO_ROOT_PASSWORD"],
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )


@st.cache_data(ttl=5, show_spinner=False)
def read_latest_pointer():
    response = minio_client().get_object(CURATED_BUCKET, LATEST_KEY)
    try:
        pointer = json.loads(response.read().decode("utf-8"))
    finally:
        response.close()
        response.release_conn()
    dataset = pointer.get("dataset", "")
    if not re.fullmatch(r"commandes/run_id=[A-Za-z0-9_-]{8,64}", dataset):
        raise ValueError("Le pointeur latest_success.json contient un dataset invalide.")
    return pointer


@st.cache_data(ttl=20, show_spinner="Chargement de la dernière version validée…")
def load_curated_dataset(dataset, company_id):
    client = minio_client()
    prefix = f"{dataset}/_company_id={int(company_id)}/"
    objects = list(client.list_objects(CURATED_BUCKET, prefix=prefix, recursive=True))
    parquet_objects = [obj for obj in objects if obj.object_name.endswith(".parquet")]
    if not parquet_objects:
        return pd.DataFrame(columns=["id", "_company_id", "client_id", "date_commande", "statut", "montant_total"])

    frames = []
    for obj in parquet_objects:
        response = client.get_object(CURATED_BUCKET, obj.object_name)
        try:
            content = response.read()
        finally:
            response.close()
            response.release_conn()
        frame = pd.read_parquet(io.BytesIO(content))
        # Spark stocke _company_id comme partition et ne la met donc pas dans chaque fichier Parquet.
        if "_company_id" not in frame.columns:
            match = re.search(r"(?:^|/)_company_id=([^/]+)/", obj.object_name)
            if match:
                frame["_company_id"] = int(match.group(1))
        frames.append(frame)

    data = pd.concat(frames, ignore_index=True)
    required = {"id", "_company_id", "client_id", "date_commande", "statut", "montant_total"}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError("Colonnes absentes du dataset final : " + ", ".join(missing))
    data["date_commande"] = pd.to_datetime(data["date_commande"], errors="coerce", utc=True).dt.tz_convert(None)
    data["montant_total"] = pd.to_numeric(data["montant_total"], errors="coerce")
    data["_company_id"] = pd.to_numeric(data["_company_id"], errors="coerce").astype("Int64")
    data["statut"] = data["statut"].fillna("Non renseigné").astype(str)
    return data


def format_mad(value):
    return f"{value:,.2f} MAD".replace(",", " ")


COMPANY_ID = company_from_token()

st.title("📊 Dashboard des commandes")
st.caption("Données validées par le contrôle qualité — actualisation automatique toutes les 30 secondes.")
st_autorefresh(interval=30_000, key="dashboard_refresh")

try:
    pointer = read_latest_pointer()
    df = load_curated_dataset(pointer["dataset"], COMPANY_ID)
except Exception as exc:
    st.error("Impossible de charger la dernière version validée des données.")
    st.info("Vérifie que la pipeline Airflow a terminé avec succès et que MinIO est accessible.")
    with st.expander("Détail technique"):
        st.code(str(exc))
    st.stop()

st.success(
    f"Dernière version validée : {pointer.get('published_at', 'date inconnue')} · {len(df):,} commandes"
)
if df.empty:
    st.warning("La dernière version publiée ne contient aucune commande.")
    st.stop()

st.sidebar.header("Filtres")
valid_dates = df["date_commande"].dropna()
if not valid_dates.empty:
    min_date, max_date = valid_dates.min().date(), valid_dates.max().date()
    date_range = st.sidebar.date_input(
        "Période des commandes", value=(min_date, max_date), min_value=min_date, max_value=max_date
    )
else:
    date_range = ()
status_options = sorted(df["statut"].unique().tolist())
selected_statuses = st.sidebar.multiselect("Statut", status_options, default=status_options)

filtered = df[df["statut"].isin(selected_statuses)].copy()
if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date, end_date = date_range
    filtered = filtered[
        filtered["date_commande"].notna()
        & (filtered["date_commande"].dt.date >= start_date)
        & (filtered["date_commande"].dt.date <= end_date)
    ]

# Les identifiants client peuvent se répéter d'une entreprise à l'autre.
clients_count = filtered[["_company_id", "client_id"]].dropna().drop_duplicates().shape[0]
orders_count = filtered[["_company_id", "id"]].dropna().drop_duplicates().shape[0]
revenue = float(filtered["montant_total"].fillna(0).sum())
average_order = revenue / orders_count if orders_count else 0.0

st.subheader("Vue générale des commandes")
kpis = st.columns(4)
kpis[0].metric("Nombre de commandes", f"{orders_count:,}".replace(",", " "))
kpis[1].metric("Chiffre d'affaires", format_mad(revenue))
kpis[2].metric("Clients ayant commandé", f"{clients_count:,}".replace(",", " "))
kpis[3].metric("Valeur moyenne d'une commande", format_mad(average_order))

left, right = st.columns(2)
with left:
    st.subheader("Évolution des commandes")
    dated = filtered.dropna(subset=["date_commande"]).copy()
    if dated.empty:
        st.info("Aucune date exploitable pour les filtres choisis.")
    else:
        dated["jour"] = dated["date_commande"].dt.date
        trend = dated.groupby("jour", as_index=False).size().rename(columns={"size": "commandes"})
        fig = px.line(trend, x="jour", y="commandes", markers=True, title="Nombre de commandes par jour")
        fig.update_layout(xaxis_title="Date", yaxis_title="Commandes")
        st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader("Répartition par statut")
    status_counts = filtered.groupby("statut", as_index=False).size().rename(columns={"size": "commandes"})
    if status_counts.empty:
        st.info("Aucune commande pour ces filtres.")
    else:
        fig = px.pie(status_counts, names="statut", values="commandes", hole=0.45, title="Commandes par statut")
        st.plotly_chart(fig, use_container_width=True)

with st.expander("Consulter les données CURATED"):
    st.dataframe(filtered.sort_values("date_commande", ascending=False), use_container_width=True, hide_index=True)
st.caption("Source : données validées (MinIO / curated), limitées à votre entreprise.")
