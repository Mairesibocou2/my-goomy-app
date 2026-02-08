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
st.set_page_config(page_title="MyGoomY", page_icon="🍳", layout="wide")

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("🚨 Clé API manquante !")
    st.stop()

# Connexion Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except:
    st.warning("Pas de connexion Sheets configurée.")

# --- FONCTIONS ---

def clean_json(text):
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find('{')
    end = text.rfind('}') + 1
    if start != -1 and end != -1:
        return json.loads(text[start:end])
    return json.loads(text)

def save_to_gsheet(recipe, url):
    try:
        df = conn.read()
        new_data = {
            "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Nom": recipe.get('nom', 'Sans nom'),
            "Url": url,
            "Temps": recipe.get('temps', '?'),
            "Ingredients": " | ".join(recipe.get('ingredients', [])),
            "Etapes": " | ".join(recipe.get('etapes', []))
        }
        df_final = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
        conn.update(data=df_final)
        return True, "Succès"
    except Exception as e:
        return False, str(e)

def download_video_smart(url):
    """Tente de télécharger. Si échec, renvoie un statut d'erreur."""
    Path("temp").mkdir(exist_ok=True)
    ydl_opts = {
        'format': 'worst', 
        'outtmpl': 'temp/video_%(id)s.%(ext)s',
        'quiet': True, 'no_warnings': True, 'ignoreerrors': True,
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info: return None, None, "BLOCKED" # Détection du blocage
            
            filename = ydl.prepare_filename(info)
            if os.path.exists(filename):
                return filename, info.get('title', ''), "VIDEO_OK"
            return None, info.get('title', ''), "TEXT_ONLY"
    except:
        return None, None, "BLOCKED"

def generate_recipe_from_text(text_input):
    """Génère la recette juste avec du texte (Mode Manuel)"""
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"""
    Tu es un chef. Voici une description de recette brute (copiée de TikTok/Insta) :
    ---
    {text_input}
    ---
    Extrais la recette en JSON strict : {{ "nom": "...", "temps": "...", "ingredients": [...], "etapes": [...] }}
    Si le texte est vide ou incompréhensible, invente une recette simple.
    """
    response = model.generate_content(prompt)
    return clean_json(response.text)

def generate_recipe_from_video(video_path):
    """Génère la recette avec la vidéo (Mode Auto)"""
    try:
        model = genai.GenerativeModel("gemini-1.5-flash") # Plus stable que le 2.5
        video_file = genai.upload_file(path=video_path)
        while video_file.state.name == "PROCESSING":
            time.sleep(1)
            video_file = genai.get_file(video_file.name)
        
        prompt = "Analyse cette vidéo. Extrais la recette en JSON strict : {{nom, temps, ingredients[], etapes[]}}."
        response = model.generate_content([video_file, prompt])
        genai.delete_file(video_file.name)
        return clean_json(response.text)
    except Exception as e:
        return {"error": str(e)}

# --- INTERFACE ---
st.title("☁️ MyGoomY (Cloud)")

tab1, tab2 = st.tabs(["🔥 Cuisine", "📚 Bibliothèque"])

with tab1:
    url = st.text_input("Lien TikTok / Instagram :")
    
    # Zone de repli manuel (cachée par défaut)
    manual_text = ""
    
    if st.button("LANCER"):
        if url:
            with st.status("Traitement...", expanded=True) as status:
                status.write("Tentative de connexion à TikTok...")
                video_path, title, mode = download_video_smart(url)
                
                recipe = None
                
                if mode == "VIDEO_OK":
                    status.write("🎥 Vidéo trouvée ! Analyse IA...")
                    recipe = generate_recipe_from_video(video_path)
                
                elif mode == "BLOCKED":
                    status.update(label="⚠️ TikTok bloque le serveur", state="error")
                    st.error("TikTok a détecté que nous sommes sur le Cloud et bloque la vidéo.")
                    st.info("👇 PAS DE PANIQUE : Copie-colle la description ci-dessous pour continuer !")
                    
                else:
                    status.write("📄 Analyse du texte seul...")
                    recipe = generate_recipe_from_text(title)

                if recipe:
                    status.update(label="Terminé !", state="complete", expanded=False)
                    st.success(f"Recette : {recipe.get('nom')}")
                    
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        if st.button("💾 ENREGISTRER"):
                            ok, msg = save_to_gsheet(recipe, url)
                            if ok: st.toast("Sauvegardé !", icon="✅")
                            else: st.error(f"Erreur Sheet : {msg}")
                    with c2:
                        st.write(f"⏱️ {recipe.get('temps')}")
                        for i in recipe.get('ingredients', []): st.checkbox(i)
                        st.write("---")
                        for s in recipe.get('etapes', []): st.write(f"- {s}")

    # LE SAUVETAGE : Si ça plante, tu peux coller le texte ici
    st.write("---")
    with st.expander("🛠️ Mode Manuel (Si le lien ne marche pas)"):
        st.caption("Si TikTok bloque le lien, colle simplement la description ou les ingrédients ici :")
        manual_input = st.text_area("Colle le texte ici :")
        if st.button("Générer depuis le texte"):
            with st.spinner("Le chef lit ton texte..."):
                recipe = generate_recipe_from_text(manual_input)
                if recipe:
                    st.success(recipe.get('nom'))
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("💾 SAUVEGARDER MANUEL"):
                             save_to_gsheet(recipe, "Manuel")
                             st.toast("Sauvegardé !")
                    with c2:
                         for i in recipe.get('ingredients', []): st.checkbox(i)

with tab2:
    if st.button("🔄 Actualiser"): st.cache_data.clear(); st.rerun()
    try:
        df = conn.read()
        for i, row in df.iloc[::-1].iterrows():
            with st.expander(f"{row['Nom']} ({row['Date']})"):
                st.write(f"**Ingrédients:** {row['Ingredients']}")
                st.write(f"**Étapes:** {row['Etapes']}")
                st.link_button("Voir", row['Url'])
    except:
        st.info("Liste vide ou erreur de lecture.")
