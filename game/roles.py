import random
from enum import Enum


class Role(str, Enum):
    DON = "don"
    MAFIA = "mafia"
    CIVILIAN = "civilian"
    COMMISSIONER = "commissioner"
    DOCTOR = "doctor"


ROLE_SIDE = {
    Role.DON: "mafia",
    Role.MAFIA: "mafia",
    Role.CIVILIAN: "city",
    Role.COMMISSIONER: "city",
    Role.DOCTOR: "city",
}

ROLE_LOCALE_KEY = {
    Role.DON: "role_don",
    Role.MAFIA: "role_mafia",
    Role.CIVILIAN: "role_civilian",
    Role.COMMISSIONER: "role_commissioner",
    Role.DOCTOR: "role_doctor",
}

ROLE_DESC_KEY = {
    Role.DON: "desc_don",
    Role.MAFIA: "desc_mafia",
    Role.CIVILIAN: "desc_civilian",
    Role.COMMISSIONER: "desc_commissioner",
    Role.DOCTOR: "desc_doctor",
}


def distribute_roles(player_count: int) -> list[Role]:
    """
    Odamlar soniga qarab rol ro'yxatini qaytaradi.
    Qat'iy qoida: Don va Komissar HAR DOIM (2+ o'yinchida) bo'ladi.
    Bu jadval kelajakda admin panel/JSON konfiguratsiyaga chiqariladi.
    """
    if player_count < 2:
        raise ValueError("Kamida 2 o'yinchi kerak")

    roles: list[Role] = [Role.DON, Role.COMMISSIONER]
    remaining = player_count - 2

    # taxminiy mafiya soni: har 4 tinch aholiga 1 mafiya
    mafia_extra = max(0, (player_count // 5) - 1)
    mafia_extra = min(mafia_extra, remaining)
    roles.extend([Role.MAFIA] * mafia_extra)
    remaining -= mafia_extra

    # 1 doktor qo'shish imkoni bo'lsa (50% ehtimol kichik o'yinlarda, katta o'yinlarda har doim)
    if remaining > 0 and (player_count >= 7 or random.random() < 0.5):
        roles.append(Role.DOCTOR)
        remaining -= 1

    # qolganlarning hammasi tinch aholi
    roles.extend([Role.CIVILIAN] * remaining)

    random.shuffle(roles)
    return roles


def mafia_team(roles_map: dict[int, Role]) -> list[int]:
    return [uid for uid, r in roles_map.items() if ROLE_SIDE[r] == "mafia"]


def city_team(roles_map: dict[int, Role]) -> list[int]:
    return [uid for uid, r in roles_map.items() if ROLE_SIDE[r] == "city"]


def check_winner(alive_roles: dict[int, Role]) -> str | None:
    """G'olib tomonni qaytaradi: 'mafia', 'city' yoki None (davom etadi)."""
    mafia_count = sum(1 for r in alive_roles.values() if ROLE_SIDE[r] == "mafia")
    city_count = sum(1 for r in alive_roles.values() if ROLE_SIDE[r] == "city")
    if mafia_count == 0:
        return "city"
    if mafia_count >= city_count:
        return "mafia"
    return None
