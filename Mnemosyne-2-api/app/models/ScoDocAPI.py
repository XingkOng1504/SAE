import requests
from typing import Dict, List, Optional, Tuple
from flask import current_app

class ScoDocAPI:
    """Classe pour interagir avec l'API ScoDoc"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        #récupération du token
        self.api_token = self._recupToken()  
        self.headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _getConfig(self)-> Tuple[str, str]:
        id = ''
        mdp = ''
        return id, mdp

    def _recupToken(self) -> str:
        identifiant, mdp = self._getConfig()
        auth_url = f"{self.base_url}/tokens"

        try:
            response = requests.post(auth_url, auth=(identifiant, mdp), timeout=10)
            response.raise_for_status()
            data = response.json()
            
            token = data.get('token')
            
            if not token:
                raise Exception("Pas de token dans la réponse")
                
            return token

        except Exception as e:
            err_msg = f"ERREUR AUTHENTIFICATION SCODOC ({auth_url}) : {e}"
            print(err_msg)
            return ""
        
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Effectue une requête GET générique"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=60)
            response.raise_for_status()

        except Exception as e:
            err_msg = f"Erreur requête API {url}: {e}"
            print(err_msg)
            return None

    # --- DONNÉES STRUCTURELLES ---

    def get_departements(self) -> List[Dict]:
        res = self._make_request("/departements")
        return res.get('departements', []) if res else []

    def get_formations(self) -> List[Dict]:
        """Récupère toutes les formations"""
        res = self._make_request("/formations")
        return res.get('formations', []) if res else []

    def get_referentiel_competences(self, formation_id: int) -> Optional[Dict]:
        """
        Récupère le référentiel (Parcours, Compétences, UE) d'une formation.
        Vital pour remplir les tables 'parcours' et 'competence'.
        """
        return self._make_request(f"/formation/{formation_id}/referentiel_competences")

    # --- DONNÉES ÉTUDIANTS / RÉSULTATS ---

    def get_formsemestres_query(self, annee_scolaire: int) -> List[Dict]:
        """
        Récupère tous les semestres (FormSemestres) d'une année donnée.
        """
        return self._make_request("/formsemestres/query", params={'annee_scolaire': annee_scolaire})

    def get_decisions_jury(self, formsemestre_id: int) -> List[Dict]:
        """
        Récupère TOUS les résultats (étudiants, décisions, moyennes) pour un semestre.
        C'est ici qu'on trouve les notes et les validations de compétences.
        """
        return self._make_request(f"/formsemestre/{formsemestre_id}/decisions_jury")