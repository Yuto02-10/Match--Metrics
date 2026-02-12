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
        rank_to_dist = {1: 10, 2: 65, 3: 110, 4: 155, 5: 195, 6: 240, 7: 290}
        dir_to_angle = {
            'B': -46.5, 'C': -42.2, 'D': -38, 'E': -34.2, 'F': -30, 'G': -26,
            'H': -22.15,'I': -18, 'J': -14, 'K': -10, 'L': -6, 'M': -2.5,
            'N': 1.5, 'O': 5.5, 'P': 9.5, 'Q': 13.5, 'R': 17.5, 'S': 21.5,
            'T': 25.5, 'U': 29.5, 'V': 33.5, 'W': 37.5, 'X': 41.5, 'Y': 45.5
        }
        
        if not isinstance(memo, str) or len(memo) < 2:
            return pd.Series([None, None])
            
        try:
            memo = memo.replace(" ", "").upper()
            d = memo[0]
            rank_str = "".join([c for c in memo[1:] if c.isdigit()])
            if not rank_str: return pd.Series([None, None])
            
            rank = int(rank_str)
            angle = dir_to_angle.get(d)
            
            if angle is not None and rank in rank_to_dist:
                angle += random.uniform(-0.05, 0.05)
                dist = rank_to_dist[rank] * random.uniform(0.9, 1.1)
                rad = math.radians(angle)
                return pd.Series([round(dist*1.2*math.sin(rad),2), round(dist*0.8*math.cos(rad),2)])
        except: pass
        return pd.Series([None, None])

    df[['打球X', '打球Y']] = df['Memo'].apply(parse_xy)
    return df

# --- メイン処理 ---
st.sidebar.header("📁 ステータス")

with st.spinner("データ取得中..."):
    df, err = fetch_github_data(GITHUB_USER, GITHUB_REPO, GITHUB_FOLDER, GITHUB_TOKEN)

if df.empty:
    st.error(f"データ取得失敗: {err}")
    st.info("手動でCSVをアップロードしてください")
    uploaded = st.file_uploader("CSVアップロード", accept_multiple_files=True)
    if uploaded:
        df = pd.concat([pd.read_csv(f).assign(SourceFile=f.name) for f in uploaded], ignore_index=True)
    else:
        st.stop()

# データクリーニング実行
df = clean_and_process(df)
st.sidebar.success(f"✅ 読み込み: {len(df)}行")

# 画像取得
bg_image, img_err = fetch_github_image(GITHUB_USER, GITHUB_REPO, GITHUB_IMAGE, GITHUB_TOKEN)
if bg_image: st.sidebar.success("✅ 画像: OK")
else: st.sidebar.warning("⚠️ 画像: NG")

# --- 分析画面 ---
players = sorted(list(set(df['Batter'].dropna().unique()) | set(df['Pitcher'].dropna().unique())))
if not players:
    st.error("選手名が見つかりません。")
    st.stop()

selected_player = st.selectbox("選手を選択", players)
b_df = df[df['Batter'] == selected_player]

tab1, tab2 = st.tabs(["📊 成績表", "🏟 打球方向"])

with tab1:
    if b_df.empty:
        st.warning("この選手のデータはありません")
    else:
        # --- 指標計算ロジック ---
        
        # 1. 打席数 (PA): KorBB(四死球・三振) または HitResult(安打・凡打) または PitchResult(死球) がある行
        pa_rows = b_df[(b_df['KorBB'].notna()) | (b_df['HitResult'].notna()) | (b_df['PitchResult'].astype(str).str.contains('死球'))]
        pa = len(pa_rows)
        
        # 2. ヒット数
        hits = b_df['HitResult'].isin(['単打', '二塁打', '三塁打', '本塁打']).sum()
        
        # 3. 四死球・三振
        bb = b_df['KorBB'].isin(['四球']).sum()
        hbp = b_df['PitchResult'].astype(str).str.contains('死球').sum()
        so = b_df['KorBB'].astype(str).str.contains('三振').sum()
        
        # 4. 犠打・犠飛
        sac = b_df['HitResult'].isin(['犠打', '犠飛']).sum()
        
        # 5. 打数 (AB) = PA - BB - HBP - SAC
        ab = pa - bb - hbp - sac
        
        # 6. Advanced Stats用カウント
        total_swings = b_df['is_Swing'].sum()
        total_contact = b_df['is_Contact'].sum()
        total_misses = b_df['is_Miss'].sum()
        
        # Zone系 (ストライクゾーン内の球)
        z_df = b_df[b_df['is_Zone']]
        z_total = len(z_df)
        z_swings = z_df['is_Swing'].sum()
        z_contact = z_df['is_Contact'].sum()
        
        # Out系 (ボールゾーンの球)
        o_df = b_df[~b_df['is_Zone']]
        o_total = len(o_df)
        o_swings = o_df['is_Swing'].sum()
        o_contact = o_df['is_Contact'].sum()
        
        # パーセント計算関数 (0除算回避)
        def pct(n, d): return (n / d * 100) if d > 0 else 0
        
        # 指標辞書の作成
        stats = {
            "試合数": b_df['SourceFile'].nunique() if 'SourceFile' in b_df.columns else 1,
            "打席数": pa,
            "打率": f"{hits/ab:.3f}" if ab > 0 else "-",
            "四球率": f"{pct(bb, pa):.1f}%",
            "三振率": f"{pct(so, pa):.1f}%",
            "O-Swing%": f"{pct(o_swings, o_total):.1f}%",
            "Z-Swing%": f"{pct(z_swings, z_total):.1f}%",
            "SwStr%": f"{pct(total_misses, len(b_df)):.1f}%",
            "O-Contact%": f"{pct(o_contact, o_swings):.1f}%",
            "Z-Contact%": f"{pct(z_contact, z_swings):.1f}%",
            "Contact%": f"{pct(total_contact, total_swings):.1f}%",
            "K-BB%": f"{pct(so - bb, pa):.1f}%"
        }
        
        st.subheader("打撃成績詳細")
        st.table(pd.DataFrame([stats]))
        
        with st.expander("全打席ログ"):
            st.dataframe(b_df[['Inning', 'Pitcher', 'PitchResult', 'HitResult', 'Memo']].fillna(''))

with tab2:
    chart_df = b_df.dropna(subset=['打球X', '打球Y'])
    
    if chart_df.empty:
        st.warning("打球データがありません (Memo列が空、または形式違い)")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart_df['打球X'], y=chart_df['打球Y'],
            mode='markers',
            marker=dict(size=12, color='blue', line=dict(width=1, color='white')),
            text=chart_df['Memo'],
            name=selected_player
        ))
        
        layout = dict(
            xaxis=dict(range=[-200, 200], showticklabels=False, fixedrange=True),
            yaxis=dict(range=[-20, 240], showticklabels=False, fixedrange=True),
            width=600, height=600,
            plot_bgcolor="white",
            margin=dict(l=0, r=0, t=0, b=0)
        )
        if bg_image:
            layout['images'] = [dict(
                source=bg_image, xref="x", yref="y",
                x=-292.5, y=296.25, sizex=585, sizey=315,
                sizing="stretch", layer="below"
            )]
            
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)










