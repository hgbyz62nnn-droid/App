# p2p-bot

بوت بايثون بيظبط سعر إعلانك في **Bybit P2P** إنه يبقى أحسن من أفضل منافس، وبتتحكم فيه من تليجرام.

- مفيش أي تحرير عملات (release). البوت بيغيّر **السعر بس**.
- **dry-run شغال افتراضيًا**: بيبعتلك "كنت هغيّره لكذا" من غير ما يغيّر حاجة، لحد ما تكتب `DRY_RUN=false` في `.env` بنفسك.

## إزاي بيسعّر

كل `interval` ثانية:
1. يجيب إعلانك (`/v5/p2p/item/info`) وإعلانات المنافسين الأونلاين على نفس العملة والجهة (`/v5/p2p/item/online`)، ويستبعد إعلاناتك إنت (بالـ userId).
2. يفلتر المنافسين: أقل نسبة إتمام، أقل عدد أوردرات، وأقل **حد أقصى للإعلان** (`maxAmount` بالعملة المحلية)، عشان مايتبعش الإعلانات الصغيرة أو الوهمية.
3. **إعلان بيع:** السعر = أقل منافس − step. **إعلان شراء:** السعر = أعلى منافس + step. التقريب بيبقى دايمًا في الاتجاه اللي يخليك قدّام.
4. لو السعر طلع برا min/max، يثبت على الحد ويبعتلك تنبيه (مرة واحدة لما يدخل الحالة دي).
5. لو الفرق عن سعرك الحالي أقل من `threshold` مايغيّرش، عشان يوفّر حد التعديلات. الاستثناء: لو سعرك الحالي نفسه برا الحدود، بيعدّله على طول.
6. في الوضع الحقيقي، البوت **مش هيغيّر السعر** غير لو min وmax متحددين الاتنين.

## أوامر تليجرام (بترد على `TELEGRAM_CHAT_ID` بس)

| الأمر | المعنى |
|---|---|
| `/status` | الوضع، والقواعد، وآخر سعر، وأفضل منافس |
| `/pause` `/resume` | إيقاف وتشغيل التسعير |
| `/check` | شغّل دورة دلوقتي |
| `/min 48.5` `/max 52` | الحدود (`off` عشان تلغيها) |
| `/step 0.01` | الفرق عن أفضل منافس |
| `/threshold 0.05` | أقل تغيير يستاهل تعديل |
| `/interval 60` | كل كام ثانية (أقل حاجة 15) |
| `/filters` | يعرض الفلاتر |
| `/filters rate 95` · `/filters orders 50` · `/filters amount 5000` | يغيّر الفلاتر |

أي تغيير من تليجرام بيتحفظ في `data/rules.json` وبيفضل بعد الـ restart. القيم اللي في `.env` بتتاخد في أول تشغيل بس. لو عايز ترجع لقيم `.env`، امسح `data/rules.json`.

## مفتاح Bybit

- صلاحية **P2P (FiatP2P)** بس. **ماتفعّلش Withdraw ولا Transfer.**
- اربطه بـ IP السيرفر: `78.141.212.182`.
- الـ P2P API محتاج تكون General Advertiser أو أعلى.
- `AD_ID`: رقم الإعلان. لازم يبقى **سعر ثابت** (fixed price)، والإعلانات اللي سعرها floating مش مدعومة.

## التسطيب على السيرفر (Ubuntu 24.04)

كل الأوامر دي بتتكتب على السيرفر بـ `root`.

```bash
# 1) المتطلبات
apt update && apt install -y python3-venv python3-pip git

# 2) يوزر مخصص للبوت (من غير login)
useradd --system --home /opt/p2p-bot --shell /usr/sbin/nologin p2pbot

# 3) الكود: انسخ المجلد لـ /opt/p2p-bot (من جهازك: scp -r p2p-bot root@78.141.212.182:/opt/)
cd /opt/p2p-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p data logs

# 4) الإعدادات
cp .env.example .env
nano .env               # املا القيم (سيب DRY_RUN فاضي = dry-run)
chmod 600 .env
chown -R p2pbot:p2pbot /opt/p2p-bot

# 5) التيستات (اختياري)
.venv/bin/pip install pytest && .venv/bin/python -m pytest -q

# 6) systemd
cp deploy/p2p-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now p2p-bot
systemctl status p2p-bot
```

البوت بيتصل هو بتليجرام وBybit (long polling)، فمش **محتاج أي بورت مفتوح** غير SSH:
```bash
ufw allow OpenSSH && ufw enable
```

### ملء `.env` من ويندوز والتأكد إن البوت شغال

من PowerShell على جهازك (بيستخدموا المفتاح `~\.ssh\id_ed25519_p2pbot`):

```powershell
powershell -ExecutionPolicy Bypass -File C:\p2p-bot\fill-env.ps1   # يسألك عن كل قيمة ويرفع .env (DRY_RUN=true)
powershell -ExecutionPolicy Bypass -File C:\p2p-bot\check-bot.ps1  # restart + فحص اللوج + تجربة Bybit وتليجرام
```

الأسرار بتتكتب مخفية، ومش بتتطبع ولا بتتكتب على الديسك. على السيرفر، `python -m p2pbot.selftest` بيعمل نفس فحص الاتصال وبيبعت رسالة تجربة على تليجرام.

### اللوجات
```bash
journalctl -u p2p-bot -f          # لايف
tail -f /opt/p2p-bot/logs/bot.log # ملف اللوج (بيتقسم أوتوماتيك عند 5MB)
```

### التحكم في الخدمة
```bash
systemctl restart p2p-bot   # بعد أي تعديل في .env
systemctl stop p2p-bot
```

### التحويل من dry-run للوضع الحقيقي
بعد ما تتأكد من رسايل الـ dry-run، اعمل الآتي:
1. `nano /opt/p2p-bot/.env` واكتب `DRY_RUN=false`.
2. `systemctl restart p2p-bot`.

رسالة البدء في تليجرام هتقول `🔴 LIVE`.

> **قبل أول تشغيل حقيقي:** راقب أول تعديل في تطبيق Bybit. طلب التعديل بيبعت كل إعدادات الإعلان كما هي، وبيبعت كمية = **الكمية المتبقية** (`lastQuantity`). التوثيق مش واضح هل `quantity` في التعديل هي الإجمالي ولا المتبقي، فاتأكد إن الكمية ماتغيّرتش بشكل مش متوقع.

## الهيكل (وإزاي تضيف منصة)

```
p2pbot/
  models.py          Ad, Side (مستقلين عن المنصة)
  rules.py           القواعد + حفظها في data/rules.json
  pricing.py         منطق التسعير (pure، ومتغطي بالتيستات)
  engine.py          دورة واحدة: جيب ← قرر ← عدّل/dry-run ← تنبيهات
  telegram_bot.py    الأوامر والجدولة
  exchanges/
    base.py          الواجهة اللي أي منصة بتنفّذها
    bybit.py         Bybit P2P
```

- **منصة جديدة** (Binance/OKX/Bitget): اعمل class يورث `Exchange` في `exchanges/`، وسجّله في `exchanges/__init__.py`، وحط `EXCHANGE=<name>` في `.env`.
- **تحرير العملات بعدين:** يتعمل كواجهة منفصلة (`OrderDesk`) بمفتاح API منفصل، عشان مفتاح التسعير مايبقاش عنده صلاحيات أوردرات.

## التطوير المحلي

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```
