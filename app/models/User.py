
class User:

    def __init__(self, dico):
        self.id = dico["id"]
        self.swmdp = dico["switchmdp"]
        # nous omettons volontairement le mot de passe, ainsi nous n'avons pas de circulation du mot de passe en dehors du DAO, même en version chiffrée



