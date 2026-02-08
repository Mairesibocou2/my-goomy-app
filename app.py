import streamlit as st
import yt_dlp
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import json
import os
import time
import re
import requests
import urllib.parse
from datetime import datetime
from pathlib import Path

# --- CONFIGURATION FAVICON ---
favicon = "🥘"
if os.path.exists("favicon.png"):
    favicon = "favicon.png"
elif os.path.exists("favicon.ico"):
    favicon = "favicon.ico"

st.set_page_config(page_title="Goumin", page_icon=favicon, layout="wide")

# --- API KEY ---
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
    

os.environ["GOOGLE_API_KEY"] = API_KEY
genai.configure(api_key=API_KEY)

# --- DOSSIERS ---
DB_FILE = "database.json"
MEDIA_FOLDER = "media"
TEMP_FOLDER = "temp"
Path(MEDIA_FOLDER).mkdir(exist_ok=True)
Path(TEMP_FOLDER).mkdir(exist_ok=True)

# --- CSS PREMIUM (DESIGN APPLE) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Poppins', sans-serif; }
    .stApp { background-color: #F2F2F7; }
    
    div[data-testid="stVerticalBlock"] > div[style*="border"] {
        background-color: white; border-radius: 20px !important; border: none !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05); padding: 15px; transition: transform 0.2s;
    }
    div[data-testid="stVerticalBlock"] > div[style*="border"]:hover {
        transform: translateY(-2px); box-shadow: 0 8px 15px rgba(0,0,0,0.1);
    }
    
    .stButton>button {
        width: 100%; border-radius: 12px; font-weight: 600; min-height: 45px; border: none;
        background: linear-gradient(135deg, #FF6B6B 0%, #FF4757 100%); color: white;
        box-shadow: 0 4px 10px rgba(255, 71, 87, 0.3);
    }
    .stButton>button:hover { transform: scale(1.02); box-shadow: 0 6px 15px rgba(255, 71, 87, 0.4); }
    
    .stTextInput>div>div>input, .stNumberInput>div>div>input {
        border-radius: 12px; border: 1px solid #E5E5EA; padding: 10px; background-color: white;
    }
    
    .score-badge {padding: 4px 10px; border-radius: 15px; color: white; font-weight: bold; font-size: 0.8em; box-shadow: 0 2px 5px rgba(0,0,0,0.1);}
    .portion-badge {background-color: #007AFF; color: white; padding: 4px 10px; border-radius: 15px; font-size: 0.8em; font-weight: bold;}
    .small-text {font-size: 0.85em; color: #3A3A3C;}
    .big-icon {font-size: 40px; text-align: center;}
    
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background-color: white; border-radius: 10px; border: none; padding: 10px 20px; font-weight: 600;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .stTabs [aria-selected="true"] { background-color: #FF4757 !important; color: white !important; }
    
    div[data-testid="stMetric"] { background-color: #F8F9FA; padding: 10px; border-radius: 12px; text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
if 'current_recipe' not in st.session_state: st.session_state.current_recipe = None
if 'generated_recipes' not in st.session_state: st.session_state.generated_recipes = None
if 'alternative_result' not in st.session_state: st.session_state.alternative_result = None
if 'frigo_suggestions' not in st.session_state: st.session_state.frigo_suggestions = None
if 'workout_plan' not in st.session_state: st.session_state.workout_plan = None
if 'selected_recipe_id' not in st.session_state: st.session_state.selected_recipe_id = None
if 'cookies_path' not in st.session_state: st.session_state.cookies_path = None
if 'shopping_list' not in st.session_state: st.session_state.shopping_list = []    

# --- SECURITE ---
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# --- DATABASE ---
def load_db():
    if not os.path.exists(DB_FILE): return []
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Correction rétroactive des champs manquants
            for r in data:
                if 'tags' not in r: r['tags'] = []
                if 'nutrition' not in r: r['nutrition'] = {}
                if 'score' not in r: r['score'] = 50
                if 'portion_text' not in r: r['portion_text'] = "Non spécifié"
            return data
    except: return []

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def save_image_locally(url_image, nom_fichier):
    try:
        if not url_image: return None
        if "pollinations" in url_image: return url_image
        if "http" not in url_image: return None
        img_data = requests.get(url_image).content
        chemin = os.path.join(MEDIA_FOLDER, f"{nom_fichier}.jpg")
        with open(chemin, 'wb') as handler: handler.write(img_data)
        return chemin
    except: return None

def save_uploaded_file(uploaded_file, nom_fichier):
    try:
        ext = uploaded_file.name.split('.')[-1]
        chemin = os.path.join(MEDIA_FOLDER, f"{nom_fichier}.{ext}")
        with open(chemin, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return chemin
    except: return None

def add_recipe(recipe, url, thumb_url):
    db = load_db()
    uid = datetime.now().strftime("%Y%m%d_%H%M%S")
    local_img = save_image_locally(thumb_url, uid)
    final_img = local_img if local_img else thumb_url

    entry = {
        "id": uid, "date": datetime.now().strftime("%d/%m/%Y"),
        "nom": recipe.get('nom', 'Sans nom'), "temps": recipe.get('temps', '?'),
        "tags": recipe.get('tags', []), "nutrition": recipe.get('nutrition', {}),
        "score": recipe.get('score', 50), "portion_text": recipe.get('portion_text', 'Standard'),
        "url": url, "ingredients": recipe.get('ingredients', []),
        "etapes": recipe.get('etapes', []), "image_path": final_img
    }
    db.append(entry)
    save_db(db)

def update_recipe_image(rid, new_path):
    db = load_db()
    for r in db:
        if r['id'] == rid:
            r['image_path'] = new_path
            break
    save_db(db)

def delete_recipe(rid):
    db = load_db()
    new_db = [r for r in db if r['id'] != rid]
    img = os.path.join(MEDIA_FOLDER, rid + ".jpg")
    if os.path.exists(img):
        try: os.remove(img)
        except: pass
    save_db(new_db)

# --- MOTEUR IA ---

def clean_ai_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        if text.startswith("["): return json.loads(text[:text.rfind(']')+1])
        start, end = text.find('{'), text.rfind('}') + 1
        return json.loads(text[start:end]) if start != -1 else json.loads(text)
    except: return {"error": "Erreur format JSON", "raw": text}

def clean_ingredient_name(text):
    """Nettoie une ligne d'ingrédient pour ne garder que le nom du produit."""
    # 1. Enlever ce qui est entre parenthèses (ex: "riz (cuit)")
    text = re.sub(r'\([^)]*\)', '', text)
    
    # 2. Enlever les quantités au début (ex: "100g de", "2 c.à.s de", "1/2 tasse")
    # Cette regex cherche : Chiffres -> Unités optionnelles -> "de/d'" optionnel
    pattern = r"^[\d\/\-\.,\s]+(?:g|kg|ml|cl|l|oz|lb|cuillères?|c\.à\.s|c\.à\.c|tasses?|verres?|pincées?|tranches?|bottes?|poignées?|gousses?|filets?)\s*(?:à\s*(?:soupe|café|dessert))?\s*(?:de\s+|d'|d’|du\s+|des\s+)?"
    
    # On remplace le pattern trouvé par rien
    clean_text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # 3. Nettoyage final (espaces en trop et majuscule)
    return clean_text.strip().capitalize()

def generate_image_url(food_name):
    clean_name = urllib.parse.quote(food_name)
    return f"https://image.pollinations.ai/prompt/delicious_{clean_name}_food_photography_high_quality?width=400&height=300&nologo=true"

# --- DOWNLOADER AVEC GESTION DES COOKIES (SECRETS OU UPLOAD) ---
def download_video(url):
    # 1. Priorité aux cookies uploadés manuellement (Sidebar)
    cookies_to_use = st.session_state.cookies_path
    
    # 2. Sinon, on cherche dans les SECRETS Streamlit (Cloud)
    if not cookies_to_use and "INSTAGRAM_COOKIES" in st.secrets:
        secret_cookies_path = os.path.join(TEMP_FOLDER, "secret_cookies.txt")
        # On écrit les secrets dans un fichier temporaire car yt-dlp a besoin d'un fichier
        with open(secret_cookies_path, "w", encoding="utf-8") as f:
            f.write(st.secrets["INSTAGRAM_COOKIES"])
        cookies_to_use = secret_cookies_path

    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{TEMP_FOLDER}/video_%(id)s.%(ext)s',
        'quiet': True, 'no_warnings': True, 'ignoreerrors': True, 'nocheckcertificate': True,
        # On se déguise en iPhone
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1',
    }
    
    # Si on a trouvé des cookies, on les utilise
    if cookies_to_use:
        ydl_opts['cookiefile'] = cookies_to_use

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info: return None, None, None
            return ydl.prepare_filename(info), info.get('title', 'Recette'), info.get('thumbnail')
    except Exception as e: return None, str(e), None

def process_ai_full(video_path, title):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        video_file = genai.upload_file(path=video_path)
        while video_file.state.name == "PROCESSING": time.sleep(1); video_file = genai.get_file(video_file.name)
        
        # PROMPT MODIFIÉ : "ingredients": ["item1", "item2"] (liste simple de strings)
        prompt = f"""
        Analyse: "{title}". Recette + Nutrition.
        INSTRUCTION: 1. Recette complète. 2. Nutri 1 PART. 3. Score Santé Sévère /100.
        IMPORTANT: 'ingredients' doit être une liste simple de textes (Ex: ["2 oeufs", "100g farine"]). Pas de catégories.
        JSON STRICT: {{ "nom": "...", "temps": "...", "tags": [], "score": 85, "portion_text": "Selon vidéo", "nutrition": {{ "cal": "...", "prot": "...", "carb": "...", "fat": "..." }}, "ingredients": ["..."], "etapes": [] }}
        """
        response = model.generate_content([video_file, prompt], safety_settings=safety_settings)
        genai.delete_file(video_file.name)
        return clean_ai_json(response.text)
    except Exception as e:
        if os.path.exists(video_path):
             try: os.remove(video_path)
             except: pass
        return {"error": str(e)}

def generate_recipe_from_text(text_description):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""
        Crée une recette saine basée sur ce texte : "{text_description}".
        INSTRUCTION: Recette complète, note sévère, nutrition précise.
        JSON STRICT: {{ "nom": "...", "temps": "...", "tags": [], "score": 85, "portion_text": "1 personne", "nutrition": {{ "cal": "...", "prot": "...", "carb": "...", "fat": "..." }}, "ingredients": [], "etapes": [] }}
        """
        response = model.generate_content(prompt, safety_settings=safety_settings)
        return clean_ai_json(response.text)
    except Exception as e: return {"error": str(e)}

def suggest_frigo_recipes(ingredient, nb_pers):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""
        J'ai SEULEMENT: "{ingredient}".
        Propose 3 recettes simples. Ingrédients pour {nb_pers} PERSONNES.
        IMPORTANT: 'ingredients' doit être une liste simple de textes. Pas de catégories.
        LISTE JSON: [ {{ "nom": "...", "temps": "...", "score": 75, "portion_text": "Pour {nb_pers} p.", "nutrition": {{ "cal": "...", "prot": "...", "carb": "...", "fat": "..." }}, "ingredients": ["..."], "etapes_courtes": "..." }} ]
        """
        response = model.generate_content(prompt, safety_settings=safety_settings)
        return clean_ai_json(response.text)
    except Exception as e: return {"error": str(e)}

def generate_chef_proposals(req, frigo_items, options, nb_pers):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        constraint_txt = ""
        if "Healthy" in options: constraint_txt += "Recettes très saines. "
        if "Economique" in options: constraint_txt += "Ingrédients pas chers. "
        if "Rapide" in options: constraint_txt += "Prêt en 15 min. "
        if "Peu d'ing." in options: constraint_txt += "Max 5 ingrédients. "
        
        frigo_txt = f"Utiliser en priorité: {frigo_items}." if frigo_items else ""

        prompt = f"""
        3 recettes pour : "{req}". {frigo_txt} Contraintes : {constraint_txt}
        Quantités: {nb_pers} Pers. Nutri: 1 Pers.
        IMPORTANT: 'ingredients' doit être une liste simple de textes. Pas de catégories.
        LISTE JSON: [ {{ "nom": "...", "type": "Rapide", "score": 80, "portion_text": "Pour {nb_pers} p.", "nutrition": {{...}}, "ingredients": ["...", "..."], "etapes": [...] }}, ... ]
        """
        response = model.generate_content(prompt, safety_settings=safety_settings)
        return clean_ai_json(response.text)
    except Exception as e: return {"error": str(e)}
    
def generate_workout(time_min, intensity, place, tools):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""
        Sport. Temps: {time_min} min. Int: {intensity}. Lieu: {place}. Matos: {tools}.
        JSON STRICT: {{ "titre": "...", "resume": "...", "echauffement": [], "circuit": [ {{"exo": "...", "rep": "...", "repos": "..."}} ], "cooldown": [] }}
        """
        response = model.generate_content(prompt, safety_settings=safety_settings)
        return clean_ai_json(response.text)
    except Exception as e: return {"error": str(e)}

def analyze_alternative(prod):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""Analyse "{prod}". JSON STRICT: {{ "verdict": "Bon/Mauvais/Moyen", "analyse": "...", "alternative": "...", "recette_rapide": "..." }}"""
        response = model.generate_content(prompt, safety_settings=safety_settings)
        return clean_ai_json(response.text)
    except Exception as e: return {"error": str(e)}

# --- UI HELPERS ---

def display_score(score):
    try: s = int(score)
    except: s = 50
    if s >= 80: color = "#2ed573"
    elif s >= 50: color = "#ffa502"
    else: color = "#ff4757"
    st.markdown(f"<span style='background-color:{color};' class='score-badge'>{s}/100</span>", unsafe_allow_html=True)

def display_nutrition_row(nutri_data):
    c1, c2, c3, c4 = st.columns(4)
    c1.caption(f"🔥 {nutri_data.get('cal', '?')}")
    c2.caption(f"🥩 {nutri_data.get('prot', '?')}")
    c3.caption(f"🍞 {nutri_data.get('carb', '?')}")
    c4.caption(f"🥑 {nutri_data.get('fat', '?')}")

def display_recipe_card_full(r, url, thumb, show_save=False):
    st.divider()
    c_titre, c_badge = st.columns([3, 1])
    with c_titre:
        st.header(r.get('nom', 'Recette'))
        # LIEN VIDÉO CLIQUABLE
        if r.get('url') and "http" in r.get('url'):
            st.markdown(f"🔗 [Voir la vidéo originale]({r.get('url')})")
        if r.get('type'): st.caption(f"Style : {r.get('type')}")
    with c_badge:
        st.markdown(f"<div style='text-align:right;'><span class='portion-badge'>👥 {r.get('portion_text', 'Standard')}</span></div>", unsafe_allow_html=True)

    display_score(r.get('score', 50))
    st.write(f"⏱️ **{r.get('temps', '?')}**")
    st.info("📊 Nutrition (1 part)")
    display_nutrition_row(r.get('nutrition', {}))
    
    col1, col2 = st.columns([1, 2])
    with col1:
        if thumb and "http" in thumb: st.image(thumb, use_container_width=True)
        else: st.markdown('<div class="big-icon">🥘</div>', unsafe_allow_html=True)
        if show_save:
            st.write("")
            if st.button("💾 Sauvegarder", type="primary", key=f"save_{r.get('nom')}"):
                final_thumb = thumb
                if not thumb or thumb == "AI_GENERATED":
                    final_thumb = generate_image_url(r.get('nom'))
                add_recipe(r, url, final_thumb)
                st.balloons()
                st.toast("Ajouté !", icon="✅")
                time.sleep(1)
                st.rerun()
    with col2:
        st.subheader("Ingrédients (Cocher pour courses)")
        
        raw_ingredients = r.get('ingredients', [])
        final_ingredients = []

        # CORRECTION DU BUG D'AFFICHAGE "CATEGORIE"
        # On aplatit la liste si l'IA a fait des catégories complexes
        if raw_ingredients and isinstance(raw_ingredients[0], dict):
            for group in raw_ingredients:
                # On ajoute les éléments de chaque groupe à notre liste finale
                final_ingredients.extend(group.get('elements', []))
        else:
            final_ingredients = raw_ingredients

        # AFFICHAGE ET CHECKBOX
        for item in final_ingredients:
            # On calcule le nom "propre" pour la liste de courses
            clean_name = clean_ingredient_name(item)
            
            # Est-ce que cet ingrédient (version propre) est déjà dans la liste ?
            is_in_list = clean_name in st.session_state.shopping_list
            
            # On affiche la phrase complète (ex: "2 oeufs") mais on stocke "Oeufs"
            if st.checkbox(item, value=is_in_list, key=f"shop_{r.get('id', 'new')}_{item}"):
                if clean_name not in st.session_state.shopping_list:
                    st.session_state.shopping_list.append(clean_name)
            else:
                if clean_name in st.session_state.shopping_list:
                    st.session_state.shopping_list.remove(clean_name)

        st.subheader("Instructions")
        for i, s in enumerate(r.get('etapes', []), 1): st.write(f"**{i}.** {s}")

# --- CONTENU COMPLET COMPARATEUR (REMIS A NEUF) ---
def show_comparator_examples():
    examples = {
        "Coca-Cola": {
            "verdict": "Mauvais",
            "desc": """
            **Composition :** Eau gazeuse, Sucre (35g par canette = 7 sucres !), Acide phosphorique, Caféine.
            **Pourquoi c'est mauvais :**
            * **Sucre liquide :** Pic d'insuline immédiat, stockage gras, risque diabète.
            * **Acide phosphorique :** Attaque l'émail des dents.
            * **Addiction :** Le mélange sucre/caféine crée une dépendance.
            """,
            "alt_titre": "Eau Infusée Fraîcheur Citron-Menthe",
            "alt_recette": "Dans 1L d'eau pétillante: 1/2 citron vert, 1/4 concombre, menthe, glaçons."
        },
        "Nutella": {
            "verdict": "Mauvais",
            "desc": """
            **Composition :** Sucre (55%), Huile de Palme (23%), Noisettes (13%), Cacao maigre.
            **Pourquoi c'est mauvais :** C'est un glaçage au sucre. Huile de palme riche en gras saturés.
            """,
            "alt_titre": "Pâte à tartiner Maison Express",
            "alt_recette": "2 c.à.s purée noisette + 1 c.à.c cacao + 1 c.à.c sirop d'agave."
        },
        "Chips Industrielles": {
            "verdict": "Mauvais",
            "desc": """
            **Composition :** Pommes de terre, Huile, Sel, Exhausteurs.
            **Pourquoi c'est mauvais :** Friture (Acrylamide cancérigène), Densité calorique extrême.
            """,
            "alt_titre": "Pois Chiches Croustillants",
            "alt_recette": "Pois chiches + Huile olive + Paprika au four 200°C 25min."
        },
        "Pizza Surgelée": {
            "verdict": "Moyen / Mauvais",
            "desc": """
            **Composition :** Pâte raffinée, Faux fromage, Jambon reconstitué, Sucre caché.
            **Pourquoi c'est mauvais :** Ingrédients bas de gamme, Trop de sel.
            """,
            "alt_titre": "Pizza Tortilla Express",
            "alt_recette": "Tortilla complète + Purée tomate + Mozza + Jambon + Origan. Poêle 5 min."
        },
         "Céréales Lion / Trésor": {
            "verdict": "Mauvais",
            "desc": """
            **Composition :** Blé, Sucre, Huile, Glucose.
            **Pourquoi c'est mauvais :** C'est un dessert. Hypoglycémie à 10h.
            """,
            "alt_titre": "Porridge 'Lion' Healthy",
            "alt_recette": "Flocons avoine + Carré chocolat noir fondu + Beurre cacahuète."
        }
    }

    for nom, data in examples.items():
        with st.expander(f"❌ {nom} -> 🟢 {data['alt_titre']}"):
            st.error(f"VERDICT : {data['verdict']}")
            st.markdown(data['desc'])
            st.divider()
            st.success(f"✅ MIEUX : {data['alt_titre']}")
            st.info(data['alt_recette'])

# --- SIDEBAR (CONFIG COOKIES) ---
with st.sidebar:
    st.header("⚙️ Configuration")
    if "INSTAGRAM_COOKIES" in st.secrets:
        st.success("🍪 Cookies chargés depuis les Secrets (Cloud).")
    else:
        st.info("Mode Manuel : Si Instagram bloque, upload cookies.txt ici.")
        uploaded_cookies = st.file_uploader("Fichier cookies.txt", type=["txt"])
        if uploaded_cookies:
            cookie_path = os.path.join(TEMP_FOLDER, "cookies.txt")
            with open(cookie_path, "wb") as f: f.write(uploaded_cookies.getbuffer())
            st.session_state.cookies_path = cookie_path
            st.success("Cookies chargés ! ✅")
        else:
            st.session_state.cookies_path = None

# --- MAIN ---

st.title("🥘 Goumin")
tabs = st.tabs(["🔥 Import", "👨‍🍳 Super Chef", "🛒 Courses", "🔄 Comparateur", "🏋️ Coach", "📚 Bibliothèque"])

# 1. IMPORT
with tabs[0]:
    st.header("Import TikTok / Insta")
    url = st.text_input("Lien vidéo")
    
    if st.button("Analyser"):
        if url:
            with st.status("Analyse...", expanded=True) as status:
                # Utilisation des cookies (Session ou Secret)
                video_path, title, thumb = download_video(url)
                
                if video_path:
                    status.write("Vidéo récupérée. IA en cours...")
                    recipe = process_ai_full(video_path, title)
                    status.update(label="Fini", state="complete")
                    if "error" in recipe: st.error(recipe['error'])
                    else:
                        st.session_state.current_recipe = recipe
                        st.session_state.current_url = url
                        st.session_state.current_thumb = thumb
                        st.rerun()
                else:
                    status.update(label="Bloqué par Insta", state="error")
                    st.warning("⚠️ Instagram a bloqué le téléchargement. Pas grave ! Utilise l'option manuelle ci-dessous.")
                    st.session_state.show_manual_input = True

    if st.session_state.get('show_manual_input'):
        st.divider()
        st.info("💡 Colle la description de la vidéo ou écris juste le nom du plat (ex: 'Pâtes Carbonara').")
        manual_text = st.text_area("📋 Description / Nom du plat :")
        if st.button("Lancer avec le texte"):
            with st.spinner("Génération..."):
                recipe = generate_recipe_from_text(manual_text)
                if "error" in recipe: st.error("Erreur")
                else:
                    st.session_state.current_recipe = recipe
                    st.session_state.current_url = "Import Manuel"
                    st.session_state.current_thumb = generate_image_url(recipe.get('nom', 'Plat'))
                    st.session_state.show_manual_input = False
                    st.rerun()

    if st.session_state.current_recipe:
        display_recipe_card_full(st.session_state.current_recipe, st.session_state.current_url, st.session_state.current_thumb, show_save=True)

# 2. SUPER CHEF (FUSION)
with tabs[1]:
    st.header("👨‍🍳 Super Chef IA")
    
    c1, c2 = st.columns([3, 1])
    with c1: 
        req = st.text_input("J'ai envie de quoi ?", placeholder="Ex: Pâtes, Asiatique, Réconfortant...")
        frigo = st.text_input("J'ai quoi dans le frigo ? (Optionnel)", placeholder="Ex: 2 courgettes, des oeufs")
    with c2: 
        nb_p_c = st.number_input("Pers.", 1, 10, 2, key="nb_c")
    
    # Options à cocher
    st.write("Filtres :")
    opts = st.columns(4)
    options_selected = []
    if opts[0].checkbox("🥗 Healthy"): options_selected.append("Healthy")
    if opts[1].checkbox("💰 Eco"): options_selected.append("Economique")
    if opts[2].checkbox("⚡ Rapide"): options_selected.append("Rapide")
    if opts[3].checkbox("📉 Peu d'ing."): options_selected.append("Peu d'ingrédients")

    if st.button("Inventer mes recettes"):
        with st.spinner("Le chef réfléchit..."):
            # On appelle la nouvelle fonction avec tous les paramètres
            res = generate_chef_proposals(req, frigo, options_selected, nb_p_c)
            if "error" in res: st.error("Erreur IA")
            elif isinstance(res, list): st.session_state.generated_recipes = res
            
    if st.session_state.generated_recipes:
        st.divider()
        cols = st.columns(3)
        for i, r in enumerate(st.session_state.generated_recipes):
            with cols[i]:
                st.subheader(r.get('type', 'Recette'))
                st.image(generate_image_url(r.get('nom')), use_container_width=True)
                st.write(f"**{r.get('nom')}**")
                display_score(r.get('score'))
                if st.button("Voir", key=f"view_{i}"):
                    st.session_state.current_recipe = r
                    st.session_state.current_url = "Chef IA"
                    st.session_state.current_thumb = "AI_GENERATED"
                    st.rerun()

# 3. NOUVEL ONGLET LISTE DE COURSES
with tabs[2]:
    st.header("🛒 Ma Liste de Courses")
    
    if not st.session_state.shopping_list:
        st.info("Ta liste est vide. Coche des ingrédients dans les recettes !")
    else:
        # Bouton pour tout effacer
        if st.button("🗑️ Vider la liste"):
            st.session_state.shopping_list = []
            st.rerun()
            
        st.divider()
        for item in st.session_state.shopping_list:
            # On affiche juste l'item, ou une checkbox pour le "rayer" (retirer)
            if st.checkbox(item, value=True, key=f"list_view_{item}"):
                pass # Si on décoche, ça le retire au prochain rerun
            else:
                st.session_state.shopping_list.remove(item)
                st.rerun()
        
        # Export simple (texte à copier)
        st.divider()
        st.text_area("Copier pour envoyer par SMS :", "\n".join(["- " + i for i in st.session_state.shopping_list]))
        
# 4. COMPARATEUR
with tabs[3]:
    st.subheader("🔍 Analyser un autre produit")
    prod = st.text_input("Nom du produit (Ex: Kinder Bueno)")
    if st.button("Comparer ce produit"):
        st.session_state.alternative_result = analyze_alternative(prod)

    if st.session_state.alternative_result:
        res = st.session_state.alternative_result
        if "error" not in res:
            st.success(res.get('verdict'))
            st.write(res.get('analyse'))
            st.info(f"Mieux : {res.get('alternative')}")
    st.divider()
    st.header("Comparateur Expert")
    show_comparator_examples() # Affiche les 5 exemples complets

# 5. COACH & SPORT (CONTENU COMPLET RESTITUÉ)
with tabs[4]:
    st.header("🏋️ Coach Goumin")
    
    with st.expander("🏃 Générateur de Séance Sport", expanded=True):
        c1, c2, c3 = st.columns(3)
        duree = c1.slider("Durée (min)", 10, 90, 30)
        intensite = c2.selectbox("Intensité", ["Douce", "Moyenne", "Elevée", "Hardcore"])
        lieu = c3.selectbox("Lieu", ["Maison (Poids corps)", "Maison (Equipé)", "Salle", "Extérieur"])
        
        matos = ""
        if "Equipé" in lieu:
            matos = st.multiselect("Matériel dispo :", ["Haltères", "Vélo Appart", "Elastique", "Tapis"])
            
        if st.button("Créer ma séance"):
            with st.spinner("Coaching..."):
                plan = generate_workout(duree, intensite, lieu, str(matos))
                st.session_state.workout_plan = plan
        
        if st.session_state.workout_plan:
            p = st.session_state.workout_plan
            st.subheader(f"🔥 {p.get('titre')}")
            st.write(p.get('resume'))
            
            st.markdown("### 1. Echauffement")
            for e in p.get('echauffement', []): st.write(f"- {e}")
            
            st.markdown("### 2. Circuit")
            for ex in p.get('circuit', []):
                st.write(f"💪 **{ex.get('exo')}** | {ex.get('rep')} | Repos: {ex.get('repos')}")
                
            st.markdown("### 3. Retour au calme")
            for c in p.get('cooldown', []): st.write(f"- {c}")
            
    # CALCULATEURS
    c1, c2 = st.columns(2)
    with c1:
        with st.expander("⚖️ IMC (Corpulence)"):
            poids = st.number_input("Poids (kg)", 40, 150, 70)
            taille = st.number_input("Taille (cm)", 100, 220, 175)
            if st.button("Calcul IMC"): 
                i = poids/((taille/100)**2)
                st.metric("IMC", f"{i:.1f}")
                if i<18.5: st.warning("Maigreur")
                elif i<25: st.success("Normal")
                else: st.error("Surpoids")
    with c2:
        with st.expander("🔥 TDEE (Besoins Kcal)"):
            age = st.number_input("Age", 10, 100, 25)
            sex = st.radio("Sexe", ["H", "F"], horizontal=True)
            act = st.selectbox("Activité", ["Sédentaire", "Léger", "Modéré", "Intense"])
            if st.button("Calcul"):
                b = (10*poids)+(6.25*taille)-(5*age)
                b = (b+5) if sex=="H" else (b-161)
                f = {"Sédentaire":1.2, "Léger":1.375, "Modéré":1.55, "Intense":1.725}
                res = int(b*f[act])
                st.metric("Maintenance", f"{res} kcal")
                st.caption(f"Sèche: {res-400} | Masse: {res+300}")

    st.divider()

    # WIKI COMPLET (TEXTES RESTITUÉS)
    with st.expander("🥩 LES PROTÉINES (Le Constructeur)"):
        st.markdown("""
        **Rôle :** Construire le muscle, réparer les tissus, couper la faim (satiété).
        **Combien ?** 1.6g à 2g par kg de poids (Sportif).
        **Sources :** Poulet, Boeuf 5%, Poisson, Oeufs, Skyr, Lentilles, Tofu.
        **❌ A éviter :** Saucisses, nuggets, charcuterie.
        """)

    with st.expander("🍞 LES GLUCIDES (Le Carburant)"):
        st.markdown("""
        **Rôle :** Énergie pour l'entraînement et le cerveau.
        **✅ Les Bons (IG Bas) :** Avoine, Riz Basmati, Patate Douce, Pâtes Complètes, Fruits.
        **⚠️ Les Rapides :** Riz blanc, Banane mûre, Miel (autour du sport).
        **❌ A bannir :** Sucre blanc, Sodas, Gâteaux industriels.
        """)

    with st.expander("🥑 LES LIPIDES (Le Protecteur)"):
        st.markdown("""
        **Rôle :** Hormones, cerveau. Ne jamais descendre sous 1g/kg.
        **✅ Bons Gras :** Huile d'Olive (cru), Avocat, Noix/Amandes, Saumon, Jaune d'oeuf.
        **❌ Mauvais Gras :** Friture, Huile tournesol chauffée, Gras trans.
        """)
        
    with st.expander("💧 L'HYDRATATION"):
        st.markdown("**3 Litres / jour minimum.** Une urine claire = bonne hydratation.")

    st.subheader("🛑 DO & DON'T")
    c_do, c_dont = st.columns(2)
    with c_do:
        st.success("""
        **✅ DO**
        1. Légumes à chaque repas (Volume).
        2. Sommeil 7-8h (Récupération).
        3. Peser aliments crus.
        4. Marcher (10k pas).
        """)
    with c_dont:
        st.error("""
        **❌ DON'T**
        1. Boire ses calories (Sodas).
        2. Régimes famine (1000kcal).
        3. Culpabiliser après un écart.
        """)

# 6. BIBLIOTHEQUE (SYSTEME VUE DETAILLEE)
with tabs[5]:
    if st.button("🔄 Actualiser"): st.rerun()
    db = load_db()
    
    # --- LOGIQUE D'AFFICHAGE VUE DETAILLEE ---
    if st.session_state.selected_recipe_id:
        r = next((item for item in db if item["id"] == st.session_state.selected_recipe_id), None)
        if r:
            if st.button("⬅️ Retour à la bibliothèque"):
                st.session_state.selected_recipe_id = None
                st.rerun()
            
            display_recipe_card_full(r, r['url'], r['image_path'], show_save=False)
            
            st.divider()
            st.subheader("🖼️ Modifier la photo du plat")
            c1, c2 = st.columns(2)
            with c1: new_url_input = st.text_input("Option 1 : Lien URL d'une image")
            with c2: uploaded_file = st.file_uploader("Option 2 : Uploader une photo", type=['png', 'jpg', 'jpeg'])
            
            if st.button("💾 Enregistrer la nouvelle image"):
                new_path = None
                if uploaded_file: new_path = save_uploaded_file(uploaded_file, r['id'])
                elif new_url_input: new_path = new_url_input
                if new_path: update_recipe_image(r['id'], new_path); st.success("Mise à jour !"); time.sleep(1); st.rerun()

    # --- LOGIQUE D'AFFICHAGE GRILLE ---
    else:
        if not db: st.info("Vide.")
        else:
            cols = st.columns(6) 
            for i, item in enumerate(reversed(db)):
                with cols[i % 6]:
                    with st.container(border=True):
                        img_path = item.get('image_path')
                        if img_path and (os.path.exists(img_path) or "http" in img_path):
                             st.image(img_path, use_container_width=True)
                        else:
                             st.image(generate_image_url(item['nom']), use_container_width=True)
                        
                        st.markdown(f"<div class='small-text'><b>{item['nom'][:30]}..</b></div>", unsafe_allow_html=True)
                        display_score(item.get('score'))
                        
                        c_voir, c_del = st.columns([3, 1])
                        with c_voir:
                            if st.button("Voir", key=f"see_{item['id']}"): st.session_state.selected_recipe_id = item['id']; st.rerun()
                        with c_del:
                            if st.button("🗑️", key=f"del_{item['id']}"): delete_recipe(item['id']); st.rerun()
