import random
from game_logic.roles import ROLES

class GameSession:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = {}
        self.state = "LOBBY"

    def add_player(self, user_id, name):
        if user_id not in self.players:
            self.players[user_id] = {"name": name, "role": None, "is_alive": True}
            return True
        return False

    def remove_player(self, user_id):
        if user_id in self.players:
            del self.players[user_id]
            return True
        return False

    def assign_roles(self):
        role_keys = list(ROLES.keys())
        player_ids = list(self.players.keys())
        random.shuffle(role_keys)
        
        for i, uid in enumerate(player_ids):
            self.players[uid]["role"] = role_keys[i % len(role_keys)]

active_games = {}
