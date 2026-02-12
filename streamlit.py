import streamlit as st
import pandas as pd
import requests
import io
import math
import random
import plotly.graph_objects as go
import base64

# --- ⚙️ 設定エリア ---
GITHUB_USER = "Yuto02-10"   # ユーザー名
GITHUB_REPO = "Match--Metrics"  # リポジトリ名
GITHUB_FOLDER = "試合データ"      # フォルダ名
GITHUB_IMAGE = "打球分析.png"    # 画像ファイル名
GITHUB_TOKEN = None             # Privateなら必須

# --- アプリ設定 ---
st.set_page_config(page_title="チームデータ分析", layout="wide")
st.title("⚾️ チームデータ統合システム (指標強化版)")

# --- 1. データ取得関数 ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_github_data(user, repo, folder, token=None):
    base_url = f"https://api.github.com/repos/{user}/{repo}/contents"
    if folder: base_url += f"/{folder}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token: headers["Authorization"] = f"token {token}"
    
    try:
        response = requests.get(base_url, headers=headers)
        if response.status_code != 200:
            return pd.DataFrame(), f"Githubアクセスエラー: {response.status_code}"
        
        files = response.json()
        csv_files = [f for f in files if isinstance(f, dict) and f.get('name', '').endswith('.csv')]
        
        if not csv_files: return pd.DataFrame(), "CSVなし"

        df_list = []
        for f in csv_files:
            if f.get('download_url'):
                r = requests.get(f['download_url'], headers=headers)
                # UTF-8で読み込む
                temp = pd.read_csv(io.BytesIO(r.content))
                temp['SourceFile'] = f['name']
                df_list.append(temp)
        
        if df_list:
            return pd.concat(df_list, ignore_index=True), None
        return pd.DataFrame(), "結合失敗"

    except Exception as e:
        return pd.DataFrame(), f"エラー: {e}"

# --- 2. 画像取得関数 ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_github_image(user, repo, filename, token=None):
    branches = ["main", "master"]
    headers = {}
    if token: headers["Authorization"] = f"token {token}"

    for branch in branches:
        raw_url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{filename}"
        try:
            r = requests.get(raw_url, headers=headers)
            if r.status_code == 200:
                b64_img = base64.b64encode(r.content).decode()
                return f"data:image/png;base64,{b64_img}", None
        except: continue
    return None, "画像が見つかりませんでした"

# --- 3. データ前処理 ---
def clean_and_process(df):
    if df.empty: return df
    
    # カラム名の空白削除
    df.columns = df.columns.str.strip()
    
    # 必須カラムの存在保証
    required = ['PitchLocation', 'PitchResult', 'HitResult', 'KorBB', 'Memo', 'Batter', 'Pitcher']
    for col in required:
        if col not in df.columns: df[col] = None
    
    # 文字列データの空白削除
    str_cols = df.select_dtypes(include=['object']).columns
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip()
        df.loc[df[col] == 'nan', col] = None

    # 数値変換
    df['PitchLocation'] = pd.to_numeric(df['PitchLocation'], errors='coerce')
    
    # フラグ立て
    # ストライクゾーン (1-9)
    df['is_Zone'] = df['PitchLocation'].isin(range(1, 10))
    
    # スイング判定 (空振, ファール, インプレー)
    def check_swing(res):
        if not isinstance(res, str): return False
        return any(k in res for k in ['空振', 'ファール', 'インプレー'])
    
    # コンタクト判定 (ファール, インプレー)
    def check_contact(res):
        if not isinstance(res, str): return False
        return any(k in res for k in ['ファール', 'インプレー'])
        
    df['is_Swing'] = df['PitchResult'].apply(check_swing)
    df['is_Contact'] = df['PitchResult'].apply(check_contact)
    df['is_Miss'] = df['PitchResult'].apply(lambda x: '空振' in str(x))

    # 座標変換 (Memo)
    def parse_xy(memo):
        rank_to_dist = {1: 10, 2: 65, 3: 110, 4:










