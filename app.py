import streamlit as st
import yt_dlp
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import json
import os
import time
import requests
import urllib.parse
from datetime import datetime
from pathlib import Path

# --- CONFIGURATION ---
favicon = "🥘"
if os.path.exists("favicon.png"): favicon = "favicon.png"
elif os.path.exists("favicon.ico"): favicon = "favicon.ico"

st.set_page_config(page_title="Goumin", page_icon=favicon, layout="wide")

# --- API KEY ---
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = "AIzaSyDOUJX8GSxh_-yP8MXYGbGdaN8ASPNW2EA".strip()

os.environ["GOOGLE_API_KEY"] = API_KEY
genai.configure(api_key=API_KEY)

# --- DOSSIERS ---
DB_FILE = "database.json"
MEDIA_FOLDER = "media"
TEMP_FOLDER = "temp"
Path(MEDIA_FOLDER).mkdir(exist_ok=True)
Path(TEMP_FOLDER).mkdir(exist_ok=True)

# --- CSS PREMIUM ---
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

# --- DATABASE & UTILS ---
def load_db():
    if not os.path.exists(DB_FILE): return []
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except: return []

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=4, ensure_ascii=False)

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
        with open(chemin, "wb") as f: f.write(uploaded_file.getbuffer())
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

def clean_ai_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        if text.startswith("["): return json.loads(text[:text.rfind(']')+1])
        start, end = text.find('{'), text.rfind('}') + 1
        return json.loads(text[start:end]) if start != -1 else json.loads(text)
    except: return {"error": "Erreur format JSON", "raw": text}

def generate_image_url(food_name):
    clean_name = urllib.parse.quote(food_name)
    return f"https://image.pollinations.ai/prompt/delicious_{clean_name}_food_photography_high_quality?width=400&height=300&nologo=true"

# --- DOWNLOADER AVEC COOKIES SECRETS OU UPLOAD ---
def download_video(url):
    # 1. Priorité aux cookies uploadés manuellement
    cookies_to_use = st.session_state.cookies_path
    
    # 2. Sinon, on cherche dans les SECRETS Streamlit
    if not cookies_to_use and "INSTAGRAM_COOKIES" in st.secrets:
        secret_cookies_path = os.path.join(TEMP_FOLDER, "secret_cookies.txt")
        # On crée le fichier temporairement depuis les secrets
        with open(secret_cookies_path, "w", encoding="utf-8") as f:
            f.write(st.secrets["INSTAGRAM_COOKIES"])
        cookies_to_use = secret_cookies_path

    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{TEMP_FOLDER}/video_%(id)s.%(ext)s',
        'quiet': True, 'no_warnings': True, 'ignoreerrors': True, 'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1',
    }
    
    if cookies_to_use:
        ydl_opts['cookiefile'] = cookies_to_use

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info: return None, None, None
            return ydl.prepare_filename(info), info.get('title', 'Recette'), info.get('thumbnail')
    except Exception as e: return None, str(e), None

# --- IA ---
def process_ai_full(video_path, title):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        video_file = genai.upload_file(path=video_path)
        while video_file.state.name == "PROCESSING": time.sleep(1); video_file = genai.get_file(video_file.name)
        prompt = f"""Analyse: "{title}". Recette + Nutrition. INSTRUCTION: 1. Recette complète. 2. Nutri 1 PART. 3. Score Santé Sévère /100. JSON STRICT: {{ "nom": "...", "temps": "...", "tags": [], "score": 85, "portion_text": "Selon vidéo", "nutrition": {{ "cal": "...", "prot": "...", "carb": "...", "fat": "..." }}, "ingredients": [], "etapes": [] }}"""
        response = model.generate_content([video_file, prompt], safety_settings={HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE})
        genai.delete_file(video_file.name)
        return clean_ai_json(response.text)
    except Exception as e: return {"error": str(e)}

def generate_recipe_from_text(text_description):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""Crée une recette: "{text_description}". JSON STRICT: {{ "nom": "...", "temps": "...", "tags": [], "score": 85, "portion_text": "1 personne", "nutrition": {{ "cal": "...", "prot": "...", "carb": "...", "fat": "..." }}, "ingredients": [], "etapes": [] }}"""
        response = model.generate_content(prompt, safety_settings={HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE})
        return clean_ai_json(response.text)
    except Exception as e: return {"error": str(e)}

def suggest_frigo_recipes(ingredient, nb_pers):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""J'ai SEULEMENT: "{ingredient}". 3 recettes simples. {nb_pers} PERS. JSON LIST: [ {{ "nom": "...", "temps": "...", "score": 75, "portion_text": "Pour {nb_pers} p.", "nutrition": {{...}}, "ingredients": [...], "etapes_courtes": "..." }} ]"""
        response = model.generate_content(prompt)
        return clean_ai_json(response.text)
    except: return {"error": "IA"}

def generate_chef_proposals(req, nb_pers):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""3 recettes pour "{req}". 1. Rapide 2. Gourmande 3. Originale. {nb_pers} Pers. JSON LIST: [ {{ "nom": "...", "type": "Rapide", "score": 80, "portion_text": "Pour {nb_pers} p.", "nutrition": {{...}}, "ingredients": [...], "etapes": [...] }} ]"""
        response = model.generate_content(prompt)
        return clean_ai_json(response.text)
    except: return {"error": "IA"}

def generate_workout(time_min, intensity, place, tools):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""Sport {time_min}min {intensity} {place} {tools}. JSON STRICT: {{ "titre": "...", "resume": "...", "echauffement": [], "circuit": [ {{"exo": "...", "rep": "...", "repos": "..."}} ], "cooldown": [] }}"""
        response = model.generate_content(prompt)
        return clean_ai_json(response.text)
    except: return {"error": "IA"}

def analyze_alternative(prod):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""Analyse "{prod}". JSON STRICT: {{ "verdict": "Bon/Mauvais/Moyen", "analyse": "...", "alternative": "...", "recette_rapide": "..." }}"""
        response = model.generate_content(prompt)
        return clean_ai_json(response.text)
    except: return {"error": "IA"}

# --- UI COMPONENTS ---
def display_score(score):
    try: s = int(score)
    except: s = 50
    color = "#2ed573" if s >= 80 else "#ffa502" if s >= 50 else "#ff4757"
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
        if r.get('type'): st.caption(f"Style : {r.get('type')}")
    with c_badge: st.markdown(f"<div style='text-align:right;'><span class='portion-badge'>👥 {r.get('portion_text', 'Standard')}</span></div>", unsafe_allow_html=True)
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
                if not thumb or thumb == "AI_GENERATED": final_thumb = generate_image_url(r.get('nom'))
                add_recipe(r, url, final_thumb)
                st.balloons(); st.toast("Ajouté !", icon="✅"); time.sleep(1); st.rerun()
    with col2:
        st.subheader("Ingrédients")
        for i in r.get('ingredients', []): st.write(f"- {i}")
        st.subheader("Instructions")
        for i, s in enumerate(r.get('etapes', []), 1): st.write(f"**{i}.** {s}")

def show_comparator_examples():
    examples = {
        "Coca-Cola": { "verdict": "Mauvais", "alt_titre": "Eau Infusée Citron-Menthe", "desc": "Sucre liquide (35g), acide, addiction.", "alt_recette": "Eau pétillante, citron vert, concombre, menthe." },
        "Nutella": { "verdict": "Mauvais", "alt_titre": "Pâte Maison Express", "desc": "55% Sucre, Huile de Palme.", "alt_recette": "Purée de noisette + Cacao + Miel." },
        "Chips": { "verdict": "Mauvais", "alt_titre": "Pois Chiches Croustillants", "desc": "Friture, Calories vides, Sel.", "alt_recette": "Pois chiches + Épices au four." },
    }
    for nom, data in examples.items():
        with st.expander(f"❌ {nom} -> 🟢 {data['alt_titre']}"):
            st.error(f"VERDICT : {data['verdict']}"); st.write(data['desc']); st.success(f"✅ MIEUX : {data['alt_titre']}"); st.info(data['alt_recette'])

# --- SIDEBAR (Fallback Cookie) ---
with st.sidebar:
    st.header("⚙️ Configuration")
    if "INSTAGRAM_COOKIES" in st.secrets:
        st.success("🍪 Cookies chargés depuis les Secrets (Mode Sécurisé).")
    else:
        st.info("Mode Manuel : Upload cookies.txt ici si Insta bloque.")
        uploaded_cookies = st.file_uploader("Fichier cookies.txt", type=["txt"])
        if uploaded_cookies:
            cookie_path = os.path.join(TEMP_FOLDER, "cookies.txt")
            with open(cookie_path, "wb") as f: f.write(uploaded_cookies.getbuffer())
            st.session_state.cookies_path = cookie_path
            st.success("Cookies chargés ! ✅")

# --- MAIN ---
st.title("🥘 Goumin")
tabs = st.tabs(["🔥 Import", "🥕 Frigo Magic", "💡 Chef IA", "🔄 Comparateur", "🏋️ Coach", "📚 Bibliothèque"])

# 1. IMPORT
with tabs[0]:
    st.header("Import TikTok / Insta")
    url = st.text_input("Lien vidéo")
    
    if st.button("Analyser"):
        if url:
            with st.status("Analyse...", expanded=True) as status:
                # Le script gère auto les cookies (secrets ou upload)
                video_path, title, thumb = download_video(url)
                
                if video_path:
                    status.write("Vidéo OK. IA en cours...")
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
                    st.warning("⚠️ Instagram a bloqué le téléchargement malgré tout.")
                    st.session_state.show_manual_input = True

    if st.session_state.get('show_manual_input'):
        st.divider()
        manual_text = st.text_area("📋 Colle la description / nom du plat :")
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

# 2. FRIGO
with tabs[1]:
    st.header("🥕 Frigo Anti-Gaspi")
    c1, c2 = st.columns([3, 1])
    with c1: ing = st.text_input("J'ai quoi ?", placeholder="Ex: 3 oeufs, 1 courgette")
    with c2: nb_p = st.number_input("Pers.", 1, 10, 1, key="nb_f")
    if st.button("Trouver recette"):
        with st.spinner("Recherche..."):
            res = suggest_frigo_recipes(ing, nb_p)
            if "error" in res: st.error("Erreur IA")
            elif isinstance(res, list): st.session_state.frigo_suggestions = res
    if st.session_state.frigo_suggestions:
        st.divider()
        for i, s in enumerate(st.session_state.frigo_suggestions):
            with st.expander(f"Option {i+1} : {s.get('nom')}", expanded=True):
                c1, c2 = st.columns([1, 3])
                with c1: st.image(generate_image_url(s.get('nom')), use_container_width=True)
                with c2:
                    display_score(s.get('score', 50)); st.caption(f"{s.get('portion_text')}"); display_nutrition_row(s.get('nutrition', {}))
                    st.write("**Ingrédients:** " + ", ".join(s.get('ingredients', [])))
                    if st.button("Choisir", key=f"btn_f_{i}"):
                        add_recipe(s, "Frigo", generate_image_url(s.get('nom')))
                        st.toast("Sauvegardé !")

# 3. CHEF IA
with tabs[2]:
    st.header("Chef IA")
    c1, c2 = st.columns([3, 1])
    with c1: req = st.text_input("Envie de ?")
    with c2: nb_p_c = st.number_input("Pers.", 1, 10, 2, key="nb_c")
    if st.button("Inventer"):
        with st.spinner("Création..."):
            res = generate_chef_proposals(req, nb_p_c)
            if "error" in res: st.error("Erreur IA")
            elif isinstance(res, list): st.session_state.generated_recipes = res
    if st.session_state.generated_recipes:
        st.divider()
        cols = st.columns(3)
        for i, r in enumerate(st.session_state.generated_recipes):
            with cols[i]:
                st.subheader(r.get('type', 'Recette')); st.image(generate_image_url(r.get('nom')), use_container_width=True)
                st.write(f"**{r.get('nom')}**"); display_score(r.get('score'))
                if st.button("Voir", key=f"view_{i}"): st.session_state.current_recipe = r; st.session_state.current_url = "Chef IA"; st.session_state.current_thumb = "AI_GENERATED"; st.rerun()

# 4. COMPARATEUR
with tabs[3]:
    st.header("Comparateur")
    show_comparator_examples(); st.divider(); prod = st.text_input("Comparer un autre produit")
    if st.button("Analyser Produit") and prod: st.session_state.alternative_result = analyze_alternative(prod)
    if st.session_state.alternative_result:
        res = st.session_state.alternative_result
        if "error" not in res: st.success(res.get('verdict')); st.write(res.get('analyse')); st.info(f"Mieux : {res.get('alternative')}")

# 5. COACH
with tabs[4]:
    st.header("🏋️ Coach Goumin")
    with st.expander("🏃 Générateur Séance"):
        c1, c2, c3 = st.columns(3)
        duree = c1.slider("Min", 10, 90, 30)
        ints = c2.selectbox("Intensité", ["Moyenne", "Elevée"])
        lieu = c3.selectbox("Lieu", ["Maison", "Salle"])
        if st.button("Créer"): plan = generate_workout(duree, ints, lieu, ""); st.session_state.workout_plan = plan
    if st.session_state.workout_plan:
        st.write(st.session_state.workout_plan.get('resume'))
        for x in st.session_state.workout_plan.get('circuit', []): st.write(f"💪 {x.get('exo')} | {x.get('rep')}")
    
    c1, c2 = st.columns(2)
    with c1:
        with st.expander("⚖️ IMC (Corpulence)"):
            poids = st.number_input("Poids (kg)", 40, 150, 70); taille = st.number_input("Taille (cm)", 100, 220, 175)
            if st.button("Calcul IMC"): i = poids/((taille/100)**2); st.metric("IMC", f"{i:.1f}")
    with c2:
        with st.expander("🔥 TDEE (Besoins Kcal)"):
            age = st.number_input("Age", 10, 100, 25); sex = st.radio("Sexe", ["H", "F"], horizontal=True); act = st.selectbox("Activité", ["Sédentaire", "Léger", "Modéré", "Intense"])
            if st.button("Calcul"): b = (10*poids)+(6.25*taille)-(5*age); b = (b+5) if sex=="H" else (b-161); f = {"Sédentaire":1.2, "Léger":1.375, "Modéré":1.55, "Intense":1.725}; res = int(b*f[act]); st.metric("Maintenance", f"{res} kcal")
    
    st.divider()
    with st.expander("🥩 LES PROTÉINES"): st.write("1.6g à 2g par kg.")
    with st.expander("🍞 LES GLUCIDES"): st.write("Privilégier IG Bas.")
    with st.expander("🥑 LES LIPIDES"): st.write("Minimum 1g/kg.")
    
# 6. BIBLIOTHEQUE
with tabs[5]:
    if st.button("🔄 Actualiser"): st.rerun()
    db = load_db()
    if st.session_state.selected_recipe_id:
        r = next((item for item in db if item["id"] == st.session_state.selected_recipe_id), None)
        if r:
            if st.button("⬅️ Retour"): st.session_state.selected_recipe_id = None; st.rerun()
            display_recipe_card_full(r, r['url'], r['image_path'], show_save=False)
            st.divider(); st.subheader("🖼️ Modifier la photo"); c1, c2 = st.columns(2)
            with c1: new_url_input = st.text_input("Lien URL")
            with c2: uploaded_file = st.file_uploader("Upload", type=['png', 'jpg', 'jpeg'])
            if st.button("💾 Sauvegarder Image"):
                new_path = None
                if uploaded_file: new_path = save_uploaded_file(uploaded_file, r['id'])
                elif new_url_input: new_path = new_url_input
                if new_path: update_recipe_image(r['id'], new_path); st.rerun()
    else:
        if not db: st.info("Vide.")
        else:
            cols = st.columns(6) 
            for i, item in enumerate(reversed(db)):
                with cols[i % 6]:
                    with st.container(border=True):
                        img_path = item.get('image_path')
                        if img_path and (os.path.exists(img_path) or "http" in img_path): st.image(img_path, use_container_width=True)
                        else: st.image(generate_image_url(item['nom']), use_container_width=True)
                        st.markdown(f"<div class='small-text'><b>{item['nom'][:25]}..</b></div>", unsafe_allow_html=True); display_score(item.get('score'))
                        c_voir, c_del = st.columns([3, 1])
                        with c_voir:
                            if st.button("Voir", key=f"see_{item['id']}"): st.session_state.selected_recipe_id = item['id']; st.rerun()
                        with c_del:
                            if st.button("🗑️", key=f"del_{item['id']}"): delete_recipe(item['id']); st.rerun()
