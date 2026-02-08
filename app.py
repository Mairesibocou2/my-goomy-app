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

# Récupération de la clé API
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("🚨 Clé API Google manquante dans les Secrets !")
    st.stop()

# Connexion Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Erreur de connexion Sheets : {e}")

# --- FONCTIONS ---

def clean_json(text):
    """Nettoie la réponse de l'IA pour trouver le JSON"""
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find('{')
    end = text.rfind('}') + 1
    if start != -1 and end != -1:
        return json.loads(text[start:end])
    return json.loads(text) # Tentative brute si pas de crochets trouvés

def save_to_gsheet(recipe, url, thumbnail):
    """Sauvegarde avec gestion d'erreurs détaillée"""
    try:
        # 1. On essaie de lire le sheet existant
        df_existing = conn.read()
        
        # 2. On prépare la nouvelle ligne
        new_data = {
            "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Nom": recipe.get('nom', 'Sans nom'),
            "Url": url,
            "Temps": recipe.get('temps', '?'),
            "Ingredients": " | ".join(recipe.get('ingredients', [])),
            "Etapes": " | ".join(recipe.get('etapes', [])),
            "Miniature": thumbnail if thumbnail else ""
        }
        
        # 3. Conversion en DataFrame
        df_new = pd.DataFrame([new_data])
        
        # 4. Fusion (concaténation)
        df_final = pd.concat([df_existing, df_new], ignore_index=True)
        
        # 5. Écriture
        conn.update(data=df_final)
        return True, "Succès"
        
    except Exception as e:
        return False, str(e)

def download_video_smart(url):
    """Essaie de télécharger la vidéo, sinon récupère juste le texte (Mode Secours)"""
    Path("temp").mkdir(exist_ok=True)
    
    # Options pour essayer de passer inaperçu
    ydl_opts = {
        'format': 'worst', 
        'outtmpl': 'temp/video_%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True, # IMPORTANT : Ne plante pas si échec
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if not info:
                return None, None, None, "Lien invalide ou privé."

            title = info.get('title', 'Recette sans titre')
            desc = info.get('description', '')
            thumb = info.get('thumbnail', '')
            
            # Vérification si le fichier vidéo existe vraiment
            filename = ydl.prepare_filename(info)
            if os.path.exists(filename):
                return filename, title, thumb, "VIDEO_OK"
            else:
                # Si pas de fichier (blocage TikTok), on renvoie les infos textuelles
                return None, f"{title} | {desc}", thumb, "TEXT_ONLY"
                
    except Exception as e:
        return None, None, None, str(e)

def generate_recipe(video_path, text_info, mode):
    """Génère la recette via Vidéo (Top qualité) ou Texte (Secours)"""
    try:
        # Choix du modèle (2.5 si possible, sinon 1.5)
        model_name = "gemini-1.5-flash" # Valeur par défaut sûre
        try:
            m = genai.GenerativeModel("gemini-2.5-flash")
            model_name = "gemini-2.5-flash"
        except:
            pass
            
        model = genai.GenerativeModel(model_name)
        
        if mode == "VIDEO_OK":
            # Mode 1 : Analyse Vidéo Complète
            video_file = genai.upload_file(path=video_path)
            while video_file.state.name == "PROCESSING":
                time.sleep(1)
                video_file = genai.get_file(video_file.name)
            
            prompt = "Tu es un chef. Analyse cette vidéo (visuel+son). Extrais la recette en JSON strict : {nom, temps, ingredients[], etapes[]}."
            response = model.generate_content([video_file, prompt])
            genai.delete_file(video_file.name) # Nettoyage
            
        else:
            # Mode 2 : Analyse Texte (Secours)
            prompt = f"""
            Tu es un chef. Je n'ai pas pu télécharger la vidéo, mais voici les infos brutes :
            {text_info}
            
            DÉDUIS une recette logique à partir de ça. 
            Format JSON strict : {{ "nom": "...", "temps": "...", "ingredients": [...], "etapes": [...] }}
            """
            response = model.generate_content(prompt)

        return clean_json(response.text)

    except Exception as e:
        return {"error": str(e)}

# --- INTERFACE ---

st.title("☁️ MyGoomY")
st.caption("Si le téléchargement échoue, l'IA devine la recette avec le texte !")

# Onglets
tab1, tab2 = st.tabs(["🔥 Nouvelle Recette", "📚 Ma Bibliothèque"])

with tab1:
    url = st.text_input("Lien TikTok / Instagram / Shorts :")
    
    if st.button("LANCER L'EXTRACTION", type="primary"):
        if url:
            with st.status("👨‍🍳 Le chef travaille...", expanded=True) as status:
                
                # 1. Téléchargement (ou Récupération infos)
                status.write("📥 Récupération des données...")
                video_path, info_text, thumb, mode = download_video_smart(url)
                
                if not mode or mode == "Lien invalide ou privé.":
                    status.update(label="Échec", state="error")
                    st.error("Impossible de lire ce lien. Vérifie qu'il est public.")
                
                else:
                    if mode == "TEXT_ONLY":
                        status.write("⚠️ Vidéo bloquée par TikTok. Passage en mode 'Analyse Texte'...")
                    else:
                        status.write("🎥 Vidéo récupérée avec succès !")
                    
                    # 2. Génération IA
                    status.write("🧠 L'IA rédige la recette...")
                    recipe = generate_recipe(video_path, info_text, mode)
                    
                    status.update(label="Recette prête !", state="complete", expanded=False)
                    
                    if "error" in recipe:
                        st.error(f"Erreur IA : {recipe['error']}")
                    else:
                        st.success(f"Recette : {recipe.get('nom')}")
                        
                        # --- AFFICHAGE COLONNES ---
                        col_img, col_recette = st.columns([1, 2])
                        
                        with col_img:
                            if thumb: st.image(thumb, use_container_width=True)
                            
                            # BOUTON SAUVEGARDE
                            if st.button("💾 ENREGISTRER"):
                                with st.spinner("Sauvegarde dans Google Sheets..."):
                                    ok, msg = save_to_gsheet(recipe, url, thumb)
                                    if ok:
                                        st.toast("C'est sauvegardé !", icon="✅")
                                        st.balloons()
                                    else:
                                        st.error(f"Erreur sauvegarde : {msg}")
                                        st.info("Vérifie que ton fichier Google Sheet s'appelle bien 'Feuille 1' en bas à gauche, ou change le code.")

                        with col_recette:
                            st.markdown(f"**⏱️ Temps :** {recipe.get('temps')}")
                            
                            c1, c2 = st.columns(2)
                            with c1:
                                st.subheader("🛒 Ingrédients")
                                for ing in recipe.get('ingredients', []):
                                    st.checkbox(ing, key=ing) # Key unique pour éviter bugs d'affichage
                            with c2:
                                st.subheader("🔪 Étapes")
                                for step in recipe.get('etapes', []):
                                    st.markdown(f"- {step}")
                            
                            # Nettoyage fichier temporaire
                            if video_path and os.path.exists(video_path):
                                try: os.remove(video_path)
                                except: pass

with tab2:
    st.header("Mes Recettes")
    if st.button("🔄 Actualiser la liste"):
        st.cache_data.clear() # Vide le cache pour forcer la mise à jour
        st.rerun()
        
    try:
        df = conn.read()
        if not df.empty:
            # On inverse pour avoir les dernières en premier
            for index, row in df.iloc[::-1].iterrows():
                with st.expander(f"🍳 {row['Nom']} ({row['Date']})"):
                    c_img, c_txt = st.columns([1, 3])
                    with c_img:
                        if row['Miniature'] and str(row['Miniature']) != "nan":
                            st.image(row['Miniature'])
                    with c_txt:
                        st.write(f"**Temps:** {row['Temps']}")
                        st.write(f"**Ingrédients:** {row['Ingredients']}")
                        st.write(f"**Étapes:** {row['Etapes']}")
                        st.link_button("Voir vidéo originale", row['Url'])
        else:
            st.info("Aucune recette enregistrée pour l'instant.")
    except Exception as e:
        st.warning("Impossible de lire la bibliothèque. As-tu bien sauvegardé une première recette ?")
