import streamlit as st
import yt_dlp
import google.generativeai as genai
import json
import os
import time
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
from pathlib import Path

# --- CONFIGURATION ---
st.set_page_config(page_title="MyGoomY Cloud", page_icon="☁️", layout="wide")
st.title("☁️ MyGoomY (Cloud Edition)")

# Récupération des secrets depuis le Cloud Streamlit
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
else:
    st.error("Clé API Google manquante dans les secrets !")
    st.stop()

# Connexion à Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FONCTIONS ---

def get_db_data():
    try:
        # On lit le Google Sheet
        df = conn.read(worksheet="Feuille 1", ttl="0") # ttl=0 pour ne pas avoir de cache
        return df
    except Exception as e:
        st.warning(f"Erreur lecture DB : {e}")
        return pd.DataFrame()

def save_to_gsheet(recipe, url, thumbnail):
    try:
        df_existing = get_db_data()
        
        new_data = {
            "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Nom": recipe.get('nom', 'Inconnu'),
            "Url": url,
            "Temps": recipe.get('temps', '?'),
            "Ingredients": ", ".join(recipe.get('ingredients', [])),
            "Etapes": " | ".join(recipe.get('etapes', [])),
            "Miniature": thumbnail if thumbnail else ""
        }
        
        df_new_row = pd.DataFrame([new_data])
        # On ajoute la nouvelle ligne
        df_updated = pd.concat([df_existing, df_new_row], ignore_index=True)
        
        # On met à jour le Sheet
        conn.update(worksheet="Feuille 1", data=df_updated)
        return True
    except Exception as e:
        st.error(f"Erreur sauvegarde : {e}")
        return False

def download_video(url):
    Path("temp").mkdir(exist_ok=True)
    ydl_opts = {
        'format': 'worst', 
        'outtmpl': 'temp/video_%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info: return None, "Vidéo introuvable", None
            filename = ydl.prepare_filename(info)
            thumbnail = info.get('thumbnail', '')
            return filename, info.get('title', 'Recette'), thumbnail
    except Exception as e:
        return None, str(e), None

def process_video(video_path, title):
    # Logique IA (Gemini 2.5 Flash de préférence)
    try:
        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
        except:
            model = genai.GenerativeModel("gemini-1.5-flash")

        video_file = genai.upload_file(path=video_path)
        while video_file.state.name == "PROCESSING":
            time.sleep(1)
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED": raise ValueError("Erreur Video Google")

        prompt = f"""
        Analyse cette vidéo (Visuel+Son). Titre : {title}
        Extrais la recette en JSON :
        {{
            "nom": "Nom",
            "temps": "15min",
            "ingredients": ["ing1", "ing2"],
            "etapes": ["step1", "step2"]
        }}
        """
        response = model.generate_content([video_file, prompt])
        genai.delete_file(video_file.name)
        text = response.text.replace("```json", "").replace("```", "").strip()
        start, end = text.find('{'), text.rfind('}') + 1
        return json.loads(text[start:end]) if start != -1 else json.loads(text)
    except Exception as e:
        return {"error": str(e)}
    finally:
        if os.path.exists(video_path):
            try: os.remove(video_path)
            except: pass

# --- INTERFACE ---
tab1, tab2 = st.tabs(["🔥 Extracteur", "📚 Bibliothèque"])

with tab1:
    url = st.text_input("Lien TikTok/Insta :")
    if st.button("EXTRAIRE"):
        if url:
            with st.status("Cuisine en cours...") as status:
                video, title, thumb = download_video(url)
                if not video:
                    st.error("Erreur téléchargement")
                else:
                    recipe = process_video(video, title)
                    status.update(label="Prêt !", state="complete")
                    
                    if "error" in recipe:
                        st.error(recipe['error'])
                    else:
                        c1, c2 = st.columns([1, 2])
                        with c1:
                            if thumb: st.image(thumb)
                            if st.button("💾 SAUVEGARDER"):
                                if save_to_gsheet(recipe, url, thumb):
                                    st.success("Sauvegardé dans le Sheet !")
                        with c2:
                            st.header(recipe.get('nom'))
                            st.write(f"⏱️ {recipe.get('temps')}")
                            for i in recipe.get('ingredients', []): st.write(f"- {i}")

with tab2:
    st.header("Mes Recettes")
    if st.button("🔄 Actualiser"):
        st.rerun()
        
    df = get_db_data()
    if not df.empty:
        # Affichage Grid
        for index, row in df.iterrows():
            with st.expander(f"{row['Nom']} ({row['Date']})"):
                c1, c2 = st.columns([1, 3])
                with c1:
                    if row['Miniature']: st.image(row['Miniature'])
                with c2:
                    st.write(f"**Temps:** {row['Temps']}")
                    st.write(f"**Ingrédients:** {row['Ingredients']}")
                    st.write(f"**Étapes:** {row['Etapes']}")
                    st.link_button("Voir original", row['Url'])
    else:
        st.info("Aucune recette trouvée.")
