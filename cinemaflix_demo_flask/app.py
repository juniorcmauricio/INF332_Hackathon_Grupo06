from flask import Flask, render_template, request
import requests
import google.generativeai as genai
import json

# --- Configuração do Flask ---
app = Flask(__name__)

# -----------------------------------------------------------------
# CHAVES DE API
# -----------------------------------------------------------------
TMDB_API_KEY = "2f53cd1e3d755ee11953a10b90a5a1e8"
GEMINI_API_KEY = "AIzaSyALFiuY3opOo4vhNyOwWAuBI3vmb-pXH3I"
# -----------------------------------------------------------------

TMDB_BASE_URL = "https://api.themoviedb.org/3"
MODEL_NAME = "gemini-2.5-flash" # O modelo que funcionou para você

try:
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"Erro ao configurar o Gemini. Verifique a chave: {e}")

# --- DICIONÁRIO DE TRADUÇÃO DE GÊNEROS ---
GENRE_MAP = {
    "28": "Ação", "12": "Aventura", "16": "Animação", "35": "Comédia",
    "80": "Crime", "99": "Documentário", "18": "Drama", "10751": "Família",
    "14": "Fantasia", "36": "História", "27": "Terror", "10402": "Música",
    "9648": "Mistério", "10749": "Romance", "878": "Ficção Científica",
    "53": "Thriller", "10752": "Guerra"
}

# --- Rota Principal (Renderiza a página) ---
@app.route('/')
def index():
    return render_template('index.html')


# --- Rota para a Demo 1 (TMDb - Busca Direta) ---
@app.route('/demo_tmdb', methods=['POST'])
def run_demo_tmdb():
    try:
        nome_do_filme = request.form.get('movie_name')
        # ... (Lógica da Demo 1 - O código desta função não muda) ...
        endpoint_busca = f"{TMDB_BASE_URL}/search/movie"
        params_busca = {'api_key': TMDB_API_KEY, 'query': nome_do_filme, 'language': 'pt-BR'}
        response_busca = requests.get(endpoint_busca, params=params_busca)
        response_busca.raise_for_status()
        dados_busca = response_busca.json()
        if not dados_busca['results']:
            return render_template('index.html', tmdb_error=f"Filme '{nome_do_filme}' não encontrado.")
        filme = dados_busca['results'][0]
        filme_id = filme['id']
        endpoint_providers = f"{TMDB_BASE_URL}/movie/{filme_id}/watch/providers"
        params_providers = {'api_key': TMDB_API_KEY}
        response_providers = requests.get(endpoint_providers, params=params_providers)
        response_providers.raise_for_status()
        dados_providers = response_providers.json()
        results_data = {
            "query": nome_do_filme, "title": filme['title'], "id": filme_id,
            "overview": filme['overview'], "poster_path": filme['poster_path'],
            "streaming": [], "rent": []
        }
        if 'BR' in dados_providers.get('results', {}):
            providers_br = dados_providers['results']['BR']
            if 'flatrate' in providers_br: results_data["streaming"] = [p['provider_name'] for p in providers_br['flatrate']]
            if 'rent' in providers_br: results_data["rent"] = [p['provider_name'] for p in providers_br['rent']]
        return render_template('index.html', tmdb_results=results_data)
    except Exception as e:
        return render_template('index.html', tmdb_error=f"Erro na API do TMDb: {e}")


# --- Rota para a Demo 2 (IA "Pura") ---
@app.route('/demo_ia', methods=['POST'])
def run_demo_ia():
    try:
        user_mood = request.form.get('user_mood_simple')
        # ... (Lógica da Demo 2 - O código desta função não muda) ...
        model = genai.GenerativeModel(MODEL_NAME)
        prompt = f"""
            Você é um assistente de recomendação de filmes (o CinemaFlix).
            O usuário está se sentindo: "{user_mood}".
            Sua tarefa é sugerir os *melhores* gêneros e temas de filmes para esse humor.
            Responda APENAS com um objeto JSON válido, contendo "generos", "temas" e "explicacao".
        """
        response = model.generate_content(prompt)
        json_text = response.text.strip().replace("```json", "").replace("```", "")
        recomendacao = json.loads(json_text)
        recomendacao['query'] = user_mood
        return render_template('index.html', ia_results=recomendacao)
    except Exception as e:
        return render_template('index.html', ia_error=f"Erro na API de IA: {e}")


# --- Rota para a Demo 3 (IA + TMDb Discover) ---
@app.route('/discover_by_mood', methods=['POST'])
def discover_by_mood():
    try:
        user_mood = request.form.get('user_mood_discover')
        if not user_mood:
            return render_template('index.html', mood_error="Você não digitou um humor.")
        # ... (Lógica da Demo 3 - O código desta função não muda) ...
        prompt_template = f"""
            Você é um assistente de recomendação de filmes (o CinemaFlix) que usa a API do TMDb.
            O usuário está se sentindo: "{user_mood}".
            Sua tarefa é traduzir esse humor em IDs de Gênero do TMDb.
            IDs de Gênero do TMDb (Use APENAS estes): {json.dumps(GENRE_MAP)}
            Selecione de 1 a 3 IDs que melhor se encaixam no humor.
            Responda APENAS com um objeto JSON válido, com uma única chave "genre_ids" [lista de strings].
            Exemplo: {{"genre_ids": ["35", "10751"]}}
        """
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt_template)
        json_text = response.text.strip().replace("```json", "").replace("```", "")
        ia_data = json.loads(json_text)
        genre_id_list = ia_data['genre_ids']
        genre_id_string_for_api = "|".join(genre_id_list) 
        suggestion_texts = []
        for genre_id in genre_id_list:
            genre_name = GENRE_MAP.get(genre_id, "?") 
            suggestion_texts.append(f"{genre_id} ({genre_name})")
        ia_suggestion_string_for_html = ", ".join(suggestion_texts)
        discover_endpoint = f"{TMDB_BASE_URL}/discover/movie"
        discover_params = {
            'api_key': TMDB_API_KEY, 'language': 'pt-BR', 'with_genres': genre_id_string_for_api,
            'sort_by': 'popularity.desc', 'include_adult': 'false'
        }
        response_discover = requests.get(discover_endpoint, params=discover_params)
        response_discover.raise_for_status()
        movie_results = response_discover.json().get('results', [])
        return render_template('index.html', 
                               mood_movies=movie_results, 
                               user_mood_query=user_mood,
                               ia_suggestion_ids=ia_suggestion_string_for_html
                              )
    except Exception as e:
        return render_template('index.html', mood_error=f"Erro no fluxo de Descoberta: {e}")


# --- Rota para a Demo 4 (Monetização - SIMULAÇÃO) ---
@app.route('/demo_monetization', methods=['POST'])
def run_demo_monetization():
    try:
        movie_name = request.form.get('movie_name_cinema')
        cep = request.form.get('user_cep')
        # ... (Lógica da Demo 4 - O código desta função não muda) ...
        fake_cinema_results = {
            "query_movie": movie_name, "query_cep": cep,
            "cinemas": [
                { "name": f"Kinoplex D. Pedro (próximo ao CEP {cep[:5]}-xxx)", "showtimes": ["18:00 (Dublado)", "20:30 (Legendado)"]},
                { "name": "Cinepolis Galleria Shopping", "showtimes": ["19:15 (Legendado)", "21:45 (Legendado)"]},
                { "name": "Cinemark Iguatemi Campinas", "showtimes": ["17:00 (Dublado)", "19:30 (Legendado)", "22:00 (Legendado)"]}
            ]
        }
        return render_template('index.html', cinema_results=fake_cinema_results)
    except Exception as e:
        return render_template('index.html', cinema_error=f"Erro na simulação: {e}")


# --- Rota para a Demo 5 (IA de Visão - SIMULAÇÃO) ---
@app.route('/demo_vision_ai', methods=['POST'])
def run_demo_vision_ai():
    try:
        # ... (Lógica da Demo 5 - O código desta função não muda) ...
        fake_vision_results = {
            "faceAnnotations": [
                {
                    "joyLikelihood": "VERY_LIKELY", "sorrowLikelihood": "VERY_UNLIKELY",
                    "angerLikelihood": "UNLIKELY", "surpriseLikelihood": "POSSIBLE"
                }
            ]
        }
        return render_template('index.html', vision_results=fake_vision_results)
    except Exception as e:
        return render_template('index.html', vision_error=f"Erro na simulação: {e}")


# --- Rota para a Demo 6 (Firebase - SIMULAÇÃO) ---
@app.route('/demo_firebase', methods=['POST'])
def run_demo_firebase():
    try:
        user_email = request.form.get('user_email')
        liked_movie_id = request.form.get('liked_movie_id')
        
        # A estrutura de dados agora inclui um "match" (filme 872585)
        # e o "like" que o usuário acabou de dar (liked_movie_id).
        fake_db_record = {
            "users": {
                "user_ABC123": { # ID do usuário (gerado pelo Firebase Auth)
                    "email": user_email,
                    "subscriptions": ["netflix", "prime_video", "max"]
                },
                "user_XYZ789": {
                    "email": "amigo@email.com",
                    "subscriptions": ["netflix", "disney_plus"]
                }
            },
            "groups": {
                "group_1234": {
                    "members": ["user_ABC123", "user_XYZ789"],
                    "likes": {
                        f"{liked_movie_id}": ["user_ABC123"], # O "like" que você acabou de dar
                        "872585": ["user_ABC123", "user_XYZ789"] # <-- ESTE É O MATCH!
                    },
                    # O script backend moveria o 872585 para cá:
                    "matches": ["872585"] 
                }
            }
        }
        
        pretty_json = json.dumps(fake_db_record, indent=4, ensure_ascii=False)
        
        return render_template('index.html', firebase_results=pretty_json)
    
    except Exception as e:
        return render_template('index.html', firebase_error=f"Erro na simulação: {e}")


# --- Rota para rodar o servidor ---
if __name__ == '__main__':
    app.run(debug=True)