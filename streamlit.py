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
# Privateリポジトリの場合はここにトークンを入力 (PublicならNoneのまま)
GITHUB_TOKEN = None 

# --- アプリ設定 ---
st.set_page_config(page_title="チームデータ分析", layout="wide")
st.title("⚾️ チームデータ統合システム")

# --- 関数1: Githubデータ取得 (CSV) ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_github_data(user, repo, folder, token=None):
    base_url = f"https://api.github.com/repos/{user}/{repo}/contents"
    if folder: base_url += f"/{folder}"
    
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    
    try:
        response = requests.get(base_url, headers=headers)
        if response.status_code != 200:
            return pd.DataFrame(), f"Githubアクセスエラー (Status: {response.status_code})"
        
        files = response.json()
        csv_files = [f for f in files if isinstance(f, dict) and f.get('name', '').endswith('.csv')]
        
        if not csv_files:
            return pd.DataFrame(), "CSVファイルが見つかりません"

        df_list = []
        for f in csv_files:
            if f.get('download_url'):
                r = requests.get(f['download_url'], headers=headers)
                temp = pd.read_csv(io.BytesIO(r.content))
                temp['SourceFile'] = f['name']
                df_list.append(temp)
        
        if df_list:
            combined = pd.concat(df_list, ignore_index=True)
            return combined, None
        return pd.DataFrame(), "データ結合失敗"

    except Exception as e:
        return pd.DataFrame(), f"プログラムエラー: {e}"

# --- 関数2: 画像データ取得 (ここを追加しました) ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_github_image(user, repo, filename, token=None):
    # API経由ではなく、Raw URLから直接取得する方式（より確実）
    # mainブランチとmasterブランチの両方を試す
    branches = ["main", "master"]
    
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"

    for branch in branches:
        raw_url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{filename}"
        try:
            r = requests.get(raw_url, headers=headers)
            if r.status_code == 200:
                # 成功したらBase64エンコードして返す
                b64_img = base64.b64encode(r.content).decode()
                return f"data:image/png;base64,{b64_img}", None
        except:
            continue
            
    return None, "画像が見つかりませんでした (main/master両方試行)"

# --- 関数3: 前処理 ---
def preprocess_data(df):
    if df.empty: return df
    
    required_cols = ['PitchLocation', 'PitchResult', 'HitResult', 'KorBB', 'Memo']
    for col in required_cols:
        if col not in df.columns:
            df[col] = None
            
    df['PitchLocation'] = pd.to_numeric(df['PitchLocation'], errors='coerce')
    df['is_Zone'] = df['PitchLocation'].isin(range(1, 10))
    
    df['is_Swing'] = df['PitchResult'].isin(['空振', 'ファール', 'インプレー'])
    df['is_Miss'] = df['PitchResult'] == '空振'
    df['is_Contact'] = df['PitchResult'].isin(['ファール', 'インプレー'])
    
    return df

# --- 関数4: 座標変換 ---
def parse_memo_to_xy(memo):
    rank_to_dist = {1: 10, 2: 65, 3: 110, 4: 155, 5: 195, 6: 240, 7: 290}
    dir_to_angle = {
        'B': -46.5, 'C': -42.2, 'D': -38, 'E': -34.2, 'F': -30, 'G': -26,
        'H': -22.15,'I': -18, 'J': -14, 'K': -10, 'L': -6, 'M': -2.5,
        'N': 1.5, 'O': 5.5, 'P': 9.5, 'Q': 13.5, 'R': 17.5, 'S': 21.5,
        'T': 25.5, 'U': 29.5, 'V': 33.5, 'W': 37.5, 'X': 41.5, 'Y': 45.5
    }
    if isinstance(memo, str) and len(memo) >= 2:
        d = memo[0].upper()
        try:
            rank = int(memo[1])
            angle = dir_to_angle.get(d)
            if angle is not None and rank in rank_to_dist:
                angle += random.uniform(-0.05, 0.05)
                dist = rank_to_dist[rank] * random.uniform(0.9, 1.1)
                rad = math.radians(angle)
                return pd.Series([round(dist*1.2*math.sin(rad),2), round(dist*0.8*math.cos(rad),2)])
        except: pass
    return pd.Series([None, None])


# --- メイン処理 ---
st.sidebar.header("📁 読み込みステータス")

# 1. CSV読み込み
with st.spinner("CSVデータを取得中..."):
    df, err_msg = fetch_github_data(GITHUB_USER, GITHUB_REPO, GITHUB_FOLDER, GITHUB_TOKEN)

if not df.empty:
    st.sidebar.success(f"✅ CSV: {len(df)} 行")
    df = preprocess_data(df)
    if 'Memo' in df.columns:
        df[['打球X', '打球Y']] = df['Memo'].apply(parse_memo_to_xy)
    else:
        df['打球X'], df['打球Y'] = None, None
else:
    st.sidebar.error(f"❌ CSV失敗: {err_msg}")
    st.stop()

# 2. 画像読み込み (ここを追加しました)
with st.spinner("画像データを取得中..."):
    bg_image, img_err = fetch_github_image(GITHUB_USER, GITHUB_REPO, GITHUB_IMAGE, GITHUB_TOKEN)

if bg_image:
    st.sidebar.success("✅ 画像: 取得成功")
else:
    st.sidebar.warning(f"⚠️ 画像失敗: {img_err}")


# --- 分析画面 ---
st.sidebar.markdown("---")
players = sorted(list(set(df['Batter'].dropna().unique()) | set(df['Pitcher'].dropna().unique())))
selected_player = st.sidebar.selectbox("選手を選択", players)

tab1, tab2 = st.tabs(["📊 詳細成績", "🏟 打球方向"])

with tab1:
    b_df = df[df['Batter'] == selected_player]
    if b_df.empty:
        st.warning("データなし")
    else:
        # 指標計算
        pa_rows = b_df[(b_df['KorBB'].notna()) | (b_df['HitResult'].notna())]
        pa = len(pa_rows)
        hits = b_df['HitResult'].isin(['単打', '二塁打', '三塁打', '本塁打']).sum()
        bb = b_df['KorBB'].isin(['四球']).sum()
        so = b_df['KorBB'].astype(str).str.contains('三振').sum







