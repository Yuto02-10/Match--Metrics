import streamlit as st
import pandas as pd
import requests
import io
import math
import random
import base64
import plotly.graph_objects as go

# --- ⚙️ 設定エリア (GitHub情報を入力) ---
GITHUB_USER = "Yuto02-10"    # 例: "kanazawa-baseball"
GITHUB_REPO = "Match--Metrics"   # 例: "game-data-2025"
GITHUB_FOLDER = "試合データ"       # CSVが入っているフォルダ名
GITHUB_IMAGE = "打球分析.png"     # 背景画像のファイル名（ルートにある場合）

# --- アプリ設定 ---
st.set_page_config(page_title="チームデータ統合分析", layout="wide")
st.title("⚾️ チームデータ統合システム (可視化機能付き)")

# --- 1. データ取得・前処理関数 ---

# GitHubから全CSVを取得（以前の glob の代わり）
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_github_data(user, repo, folder):
    base_url = f"https://api.github.com/repos/{user}/{repo}/contents"
    if folder: base_url += f"/{folder}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    
    try:
        response = requests.get(base_url, headers=headers)
        if response.status_code != 200:
            return pd.DataFrame(), f"アクセス失敗: {response.status_code}"
        
        files = response.json()
        csv_files = [f for f in files if isinstance(f, dict) and f.get('name', '').endswith('.csv')]
        
        if not csv_files:
            return pd.DataFrame(), "CSVファイルが見つかりません"

        df_list = []
        for f in csv_files:
            if f.get('download_url'):
                res = requests.get(f['download_url'])
                temp = pd.read_csv(io.BytesIO(res.content))
                temp['SourceFile'] = f['name']
                df_list.append(temp)
        
        if df_list:
            return pd.concat(df_list, ignore_index=True), None
        return pd.DataFrame(), "データ結合失敗"
    except Exception as e:
        return pd.DataFrame(), f"エラー: {e}"

# 背景画像をGithubから取得（URL対応版）
@st.cache_data(ttl=3600)
def load_github_image(user, repo, filepath):
    url = f"https://raw.githubusercontent.com/{user}/{repo}/main/{filepath}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            encoded = base64.b64encode(response.content).decode()
            return f"data:image/png;base64,{encoded}"
    except:
        pass
    return None

# Memo列をXY座標に変換（以前のコードから移植）
def parse_memo_to_xy(memo, angle_range=0.05, distance_range=0.1):
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
        except:
            return pd.Series([None, None])
            
        angle_c = dir_to_angle.get(d)
        if angle_c is None or rank not in rank_to_dist:
            return pd.Series([None, None])
            
        # ランダム散らし
        angle = angle_c + random.uniform(-angle_range, angle_range)
        dist = rank_to_dist[rank] * random.uniform(1 - distance_range, 1 + distance_range)
        rad = math.radians(angle)
        
        # 楕円補正
        x = round(dist * 1.2 * math.sin(rad), 2)
        y = round(dist * 0.8 * math.cos(rad), 2)
        return pd.Series([x, y])
    return pd.Series([None, None])

# --- 2. データ読み込み実行 ---

# データ取得
with st.spinner("Githubからデータを取得中..."):
    df, err = fetch_github_data(GITHUB_USER, GITHUB_REPO, GITHUB_FOLDER)

if not df.empty:
    st.sidebar.success(f"✅ {len(df)} データの読み込み完了")
    
    # 座標変換を実行
    if 'Memo' in df.columns:
        df[['打球X', '打球Y']] = df['Memo'].apply(parse_memo_to_xy)
    else:
        df['打球X'], df['打球Y'] = None, None

    # 画像取得
    bg_image = load_github_image(GITHUB_USER, GITHUB_REPO, GITHUB_IMAGE)
else:
    st.error(f"データ取得失敗: {err}")
    # フォールバック: ファイルアップロード
    uploaded = st.sidebar.file_uploader("手動アップロード", accept_multiple_files=True)
    if uploaded:
        df_list = [pd.read_csv(f).assign(SourceFile=f.name) for f in uploaded]
        df = pd.concat(df_list, ignore_index=True)
        if 'Memo' in df.columns:
            df[['打球X', '打球Y']] = df['Memo'].apply(parse_memo_to_xy)
    else:
        st.stop()


# --- 3. 分析UI ---
st.sidebar.markdown("---")
st.sidebar.header("🔍 選手選択")

players = sorted(list(set(df['Batter'].dropna().unique()) | set(df['Pitcher'].dropna().unique())))
selected_player = st.sidebar.selectbox("選手", players)

# タブ切り替え
tab1, tab2 = st.tabs(["📊 成績データ", "🏟 打球方向分析"])

# --- タブ1: 成績データ (前回の機能) ---
with tab1:
    batter_df = df[df['Batter'] == selected_player]
    if not batter_df.empty:
        hits = batter_df['HitResult'].isin(['単打', '二塁打', '三塁打', '本塁打']).sum()
        pa = len(batter_df[(batter_df['KorBB'].notna()) | (batter_df['HitResult'].notna())])
        st.subheader("打撃成績")
        st.metric("打席数", pa, f"安打: {hits}")
        st.dataframe(batter_df)
    else:
        st.info("打撃データなし")

# --- タブ2: 打球方向分析 (復活させた機能) ---
with tab2:
    st.subheader(f"{selected_player} の打球方向")
    
    # データ抽出
    chart_df = df[df['Batter'] == selected_player].copy()
    chart_df = chart_df.dropna(subset=['打球X', '打球Y'])
    
    if chart_df.empty:
        st.warning("打球座標データ（Memo列）がありません。")
    else:
        # フィルター
        p_types = ["すべて"] + list(chart_df['PitchType'].unique())
        pt_filter = st.selectbox("球種で絞り込み", p_types)
        
        if pt_filter != "すべて":
            chart_df = chart_df[chart_df['PitchType'] == pt_filter]
            
        # Plotlyグラフ
        fig = go.Figure()
        
        # プロット
        fig.add_trace(go.Scatter(
            x=chart_df['打球X'], y=chart_df['打球Y'],
            mode='markers',
            marker=dict(
                size=10,
                color=chart_df['HitType'].map({"ゴロ": "green", "フライ": "blue", "ライナー": "red"}).fillna("gray"),
                symbol=chart_df['PitchType'].map({"ストレート": "circle", "スライダー": "square"}).fillna("circle")
            ),
            text=chart_df['Memo'],
            name=selected_player
        ))
        
        # 背景画像設定
        layout_dict = dict(
            xaxis=dict(range=[-200, 200], showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(range=[-20, 240], showgrid=False, zeroline=False, showticklabels=False),
            width=600, height=600,
            plot_bgcolor="white"
        )
        
        if bg_image:
            layout_dict['images'] = [dict(
                source=bg_image,
                xref="x", yref="y",
                x=-292.5, y=296.25,
                sizex=585, sizey=315,
                sizing="stretch",
                layer="below"
            )]
        else:
            st.warning("背景画像が見つかりません (Githubに画像を置いてください)")
            
        fig.update_layout(**layout_dict)
        st.plotly_chart(fig)


