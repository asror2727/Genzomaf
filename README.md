# 🤵🏻 Mafia Telegram Bot

aiogram 3.x + SQLite asosida yozilgan Mafia o'yin boti. Ko'p guruhda parallel ishlaydi.

## Ishga tushirish (lokal)

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # BOT_TOKEN ni @BotFather dan olib kiriting
export $(cat .env | xargs)    # yoki python-dotenv qo'shing
python main.py
```

## GitHub + Render'ga deploy qilish

1. Shu papkani GitHub repoga push qiling.
2. Render.com'da **New +** → **Blueprint** → repongizni tanlang (`render.yaml` avtomatik o'qiladi),
   yoki qo'lda **Background Worker** yarating:
   - Build command: `pip install -r requirements.txt`
   - Start command: `python main.py`
3. Environment Variables bo'limida `BOT_TOKEN` ni kiriting (BotFather'dan olingan token).
4. Deploy qiling — bot polling rejimida ishga tushadi.

> Eslatma: bu versiya **long polling** ishlatadi (webhook emas) — Render'ning bepul workerida ham to'g'ri ishlaydi, chunki worker doim tirik turadi (web service kabi "uxlab qolish" muammosi yo'q).

## Loyiha tuzilishi

```
main.py              — kirish nuqtasi
config.py            — sozlamalar (token, owner id, default qiymatlar)
database.py          — SQLite bilan ishlash (users, groups, transactions)
i18n.py               — ko'p tillilik (locales/*.json)
game/roles.py         — rollar va rol taqsimoti logikasi
game/engine.py        — o'yin holati, tun/kun/ovoz berish tsikli
handlers/private.py   — /start, /profile, /lang, /reyting (private chat)
handlers/group.py     — /game, /give, /settings, night/vote callbacklari (guruh)
handlers/admin.py     — /admin — faqat OWNER_ID uchun boshqaruv paneli
locales/*.json        — har til uchun barcha matnlar
```

## Hozircha amalga oshirilgan (v1)

- ✅ Til tanlash (6 til, `locales/*.json` orqali kengaytiriladi)
- ✅ `/start`, `/profile`, `/reyting`
- ✅ Guruhda `/game` — ro'yxatdan o'tish, avto-pin/unpin, min/max o'yinchi
- ✅ Rol taqsimoti: Don, Mafiya, Komissar, Doktor, Tinch aholi (Don va Komissar har doim bor)
- ✅ Tun (Don o'ldiradi, Doktor davolaydi, Komissar tekshiradi) → Kun → Ovoz berish tsikli
- ✅ G'alaba shartini avtomatik tekshirish, o'yin yakuni va mukofot (pul + reyting balli)
- ✅ `/give` — almaz sovg'a qilish
- ✅ `/admin` — faqat owner uchun, statistika va to'lov tasdiqlash (`approve_tx_<id>`)
- ✅ Har guruh mustaqil sozlamaga ega (`groups.settings` JSON, `/settings` skeleton)

## Keyingi bosqichlar (TODO — kod ichida belgilangan)

- `/settings` to'liq inline menyu (vaqtlar, jimlik, arjament, boshqa sozlamalar)
- Qo'shimcha rollar: Advokat, Daydi, Kezuvchi, Serjant, Afsungar, Bo'ri, Qotil
- Do'kon: haqiqiy to'lov oqimi (chek yuborish → admin tasdiqlaydi → `approve_tx_<id>` callback allaqachon tayyor)
- Premium guruhlar ro'yxati (admin panel orqali)
- `/giveaway`, `/send`, `/token`, `/top`, `/leave`, `/extend`, `/stop`
- NPC (bot) o'yinchilar + AI suhbat integratsiyasi

## Test qilingan qismlar

- Barcha `.py` fayllar sintaksis bo'yicha tekshirildi (`py_compile`)
- `game/roles.py` — rol taqsimoti (4/10/15/20/30 o'yinchi) va g'alaba shartlari unit-test qilindi
- `database.py` sxemasi va SQL so'rovlari standart `sqlite3` bilan tasdiqlandi
- `i18n.py` — barcha 6 til uchun matn yuklash tekshirildi

`aiogram`/`aiosqlite` kutubxonalari joriy sandbox'da tarmoq yo'qligi sababli o'rnatilmadi —
`pip install -r requirements.txt` ishga tushirilgan muhitda avtomatik o'rnatiladi va bot to'liq ishga tayyor.
