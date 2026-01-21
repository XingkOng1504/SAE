from app.models.RegleDAO import RegleDAO

class RegleService():
    
    def __init__(self):
        self.rdao = RegleDAO()



    def ajouter_regle(self, nom, description, condition):
        return self.rdao.ajouter_regle(nom,description,condition)

    def modifier_statut(self, index, statut):
        return self.rdao.modifier_statut(index,statut)
            

    def get_regles(self):
        return self.rdao.get_regles()

    def supprimer_regle(self, index):
        return self.rdao.supprimer_regle(index)
    
    def finSQL(self):
        return self.rdao.finSQL()