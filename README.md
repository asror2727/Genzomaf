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

## Hozircha amalga oshirilgan (v2 — bu yangilanishda tuzatilgan/qo'shilgan)

- ✅ **6 tilning barchasi endi haqiqiy tarjima bilan ishlaydi** (avval faqat uz/en, qolganlari nusxa edi)
- ✅ **`/stop`** — o'yin yoki ro'yxatni istalgan guruh admini/owner to'xtata oladi (avval "stuck" holatdan chiqib bo'lmas edi)
- ✅ **`/leave`** — ro'yxatdan yoki o'yindan chiqish
- ✅ **`/vaqt 100`** — ro'yxatdan o'tish vaqtini soniyaga uzaytirish
- ✅ **`/give`, `/send`, `/token`** — reply orqali sovg'a, pul, token berish (ismlar bosiladigan, profilga o'tadi)
- ✅ **`/giveaway 100`** — ishtirok etish tugmasi bilan, 60 soniyadan keyin tasodifiy g'oliblarga bo'lib beradi
- ✅ **`/mypara`** (reply bilan taklif), **`/parauzish`**, **`/parakorish`** — juftlik tizimi
- ✅ **`/top`**, **`/qoida`** — guruh reytingi va qoidalar
- ✅ **`/settings`** — kategoriyalar bo'yicha ishlaydigan menyu (vaqt/jimlik/arjament/boshqa), yoqish-o'chirish tugmalari haqiqatan DB'ga yoziladi
- ✅ **Profildagi tugmalar ishlaydi**: Do'kon (shield/mask/gun/fake_doc sotib olish), Pul xarid qilish (almazni pulga aylantirish), Almaz xarid qilish (chek yuborish → admin tasdiqlaydi → balансga tushadi)
- ✅ **Admin panel to'liq**: narxlarni ko'rish, kutilayotgan to'lovlarni tasdiqlash, qoidalarni tahrirlash, premium guruh qo'shish, **NPC (bot) o'yinchi qo'shish** (guruh ID + son), statistika, broadcast
- ✅ **Ro'yxatdagi va o'yindagi ismlar endi bosiladigan** (`tg://user?id=...` havola) — bosilsa profilga o'tadi
- ✅ **Muhim mantiqiy tuzatish**: agar Don/Doktor/Komissar vaqtida javob bermasa, endi avtomatik tasodifiy tanlov qo'yiladi — avval hech kim javob bermasa o'yin **hech qachon tugamas edi** (bu test orqali aniqlanib, tuzatildi)
- ✅ **Admin panelning routing xatosi tuzatildi** — avval owner har qanday matn yozganda (guruhda ham) admin handler uni "ushlab qolib", boshqa buyruqlarning ishlashiga to'sqinlik qilardi

## Avvalgi (v1) imkoniyatlar


- ✅ Til tanlash (6 til, `locales/*.json` orqali kengaytiriladi)
- ✅ `/start`, `/profile`, `/reyting`
- ✅ Guruhda `/game` — ro'yxatdan o'tish, avto-pin/unpin, min/max o'yinchi
- ✅ Rol taqsimoti: Don, Mafiya, Komissar, Doktor, Tinch aholi (Don va Komissar har doim bor)
- ✅ Tun (Don o'ldiradi, Doktor davolaydi, Komissar tekshiradi) → Kun → Ovoz berish tsikli
- ✅ G'alaba shartini avtomatik tekshirish, o'yin yakuni va mukofot (pul + reyting balli)
- ✅ `/give` — almaz sovg'a qilish
- ✅ `/admin` — faqat owner uchun, statistika va to'lov tasdiqlash (`approve_tx_<id>`)
- ✅ Har guruh mustaqil sozlamaga ega (`groups.settings` JSON, `/settings` skeleton)

## Keyingi bosqichlar (TODO)

- Qo'shimcha rollar: Advokat, Daydi, Kezuvchi, Serjant, Afsungar, Bo'ri, Qotil
- `/settings` ichidagi vaqt/jimlik/arjament bo'limlariga to'liq +/- tugmalari (hozir vaqt uchun `/vaqt` komandasi ishlatiladi)
- Guruh bo'yicha alohida til va alohida statistika (hozir global)
- NPC o'yinchilarning tungi/kunduzgi "jonli suhbat" AI qismi (Anthropic API orqali)

## Test qilingan qismlar (bu yangilanishda)

- Barcha `.py` fayllar sintaksis bo'yicha tekshirildi (`py_compile`)
- Offline stub (`aiogram`/`aiosqlite` o'rniga soddalashtirilgan versiya) yordamida **to'liq o'yin oqimi** simulyatsiya qilindi: ro'yxatdan o'tish → NPC qo'shish → o'yin boshlash → tun/kun/ovoz → g'alaba — 4, 6, 10, 15 o'yinchi bilan sinaldi, hammasi muvaffaqiyatli tugadi
- Juftlik (`pairs`), premium guruhlar, qoidalar (`kv_store`), tranzaksiyalar (to'lov tasdiqlash) DB funksiyalari alohida sinaldi
- Barcha 6 tilning JSON fayllari kalitlari bir-biriga mos ekanligi va kodda ishlatilgan har bir tarjima kaliti mavjudligi avtomatik tekshirildi
- **Muhim**: haqiqiy `aiogram`/`aiosqlite` kutubxonalari sandboxda internet yo'qligi sabab o'rnatilmadi — lekin ularning ishlash mantig'i soddalashtirilgan stublar orqali tasdiqlandi. Render'da `pip install -r requirements.txt` bilan haqiqiy kutubxonalar o'rnatiladi.
