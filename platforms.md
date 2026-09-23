# P2P / Merchant API: مقارنة المنصات

> **مهم:** البحث ده معمول من **التوثيق العام بس**. ماقدرتش أفتح Chrome ولا أدخل على حساباتك، لأن الجلسة دي شغالة في سيرفر سحابي معزول ومفيش أداة تتحكم في المتصفح. عشان كده:
> - الجزء التاني من سؤال 5 ("هل حسابي عنده الصلاحية حاليًا؟") **مقدرتش أتأكد منه** لأي منصة. لازم تشوفه بنفسك في صفحة إدارة الـ API.
> - ماتعملش أي API key ولا اتغير أي إعداد.
> - التاريخ: 2026-09-23. التوثيق بيتغير، فراجع اللينكات قبل ما تبني عليها.

## الجدول

| السؤال | Binance | OKX | Bybit | Bitget |
|---|---|---|---|---|
| **1. قراءة الأوردرات** | ✅ `listOrders`، `getUserOrderDetail`، `listUserOrderHistory` (تحت `/sapi/v1/c2c/...`) | ⚠️ على الأغلب أيوه، بس التوثيق التقني مش منشور للعامة (بيتبعت بعد الموافقة) | ✅ `/v5/p2p/order/simplifyList`، `/order/info`، `/order/pending/simplifyList` | ✅ Get Merchant P2P Orders (`/api/v2/p2p/orderList`) |
| **2. تعديل سعر الإعلان** | ✅ `/sapi/v1/c2c/agent/ads/update` (محتاج صلاحية كتابة + ميرشانت) | ⚠️ غير موثّق للعامة | ✅ `/v5/p2p/item/update` | ✅ Create/Update ads (Read-Write). عليه حد لعدد مرات تغيير السعر غير الـ rate limit العادي |
| **3. تحرير العملة (release)** | ⚠️ **مش موجود في التوثيق العام** (الـ Skills Hub بيقول صراحة إن release مش مدعوم). في endpoints للميرشانت زي `checkIfCanReleaseCoin` في الـ SAPI الخاص، ومحتاجة 2FA (Google Authenticator). محتاج تأكيد من الـ docs اللي بتيجي بعد الموافقة | ⚠️ غير موثّق للعامة | ✅ `/v5/p2p/order/finish`. الصلاحية: **FiatP2P** | ❌ **مش مذكور.** المتاح "mark as paid" بس (ده للشاري). الـ release مش موجود في المزايا المعلنة |
| **Withdraw مطلوب للـ release؟** | مش موثّق | مش موثّق | **لأ.** المطلوب FiatP2P بس | لا ينطبق |
| **4. رسايل شات الأوردر** | ❌ في التوثيق العام (الـ Skills Hub بيقول صراحة إنه مش مدعوم). ⚠️ ممكن يكون موجود في الـ SAPI الخاص بالميرشانت، مش مؤكد | ⚠️ غير موثّق للعامة | ✅ `/v5/p2p/order/message/send`، وكمان رفع ملفات وقراءة الرسايل | ❌ مش مذكور |
| **5. شرط الموافقة / المستوى** | لازم تكون **Verified Merchant**. غير كده بيرجع `Permission denied` | **Super أو Diamond Merchant** + **طلب** من صفحة P2P API، وفريق Merchant Management بيراجعه ويرد بالإيميل. لازم حسابك يتعمله whitelist صريح | **General Advertiser أو أعلى** (مقالات أقدم بتقول VA). مفيش طلب منفصل مذكور | **Verified P2P Merchant**. الصلاحية بتتفعل من API Key Management |
| **هل حسابي عنده الصلاحية؟** | ❓ مقدرتش أتأكد | ❓ مقدرتش أتأكد | ❓ مقدرتش أتأكد | ❓ مقدرتش أتأكد |
| **6. ربط بـ IP ثابت (78.141.212.182)** | ✅ Binance بيدعم IP restriction للمفاتيح بشكل عام | ✅ لحد 20 IP لكل مفتاح (IPv4/IPv6/نطاقات) | ✅ مدعوم بشكل عام في إدارة مفاتيح Bybit (مش مذكور في صفحة P2P نفسها) | ⚠️ مدعوم بشكل عام في مفاتيح Bitget، بس مش مذكور في توثيق P2P |

الرموز: ✅ موثّق · ⚠️ مش مؤكد أو مش منشور للعامة · ❌ مش متاح حسب التوثيق · ❓ محتاج تتأكد من حسابك

## الخلاصة: المتاح والناقص

- **Bybit:** الأكمل. قراءة وتعديل إعلان وrelease وشات، كله موثّق للعامة. الـ release محتاج FiatP2P ومش محتاج Withdraw. الناقص الوحيد إنك تتأكد إنك General Advertiser أو أعلى.
- **Binance:** قراءة الأوردرات وإدارة الإعلانات موثّقين. الـ release والشات **مش موثّقين للعامة**، والـ release (لو متاح) محتاج 2FA، وده بيصعّب إنه يبقى أوتوماتيك بالكامل.
- **OKX:** مقفول لحد ما تتقبل. لازم تكون Super/Diamond وتقدّم طلب. التوثيق التقني مش منشور للعامة، فمقدرش أأكد release ولا شات.
- **Bitget:** قراءة أوردرات وإدارة إعلانات. **مفيش release ولا شات** في المزايا المعلنة.

## نصايح للأمان

- **ماتفعّلش Withdraw** على أي مفتاح P2P. مفيش منصة من الأربعة بتطلبه للـ release حسب التوثيق.
- اربط كل مفتاح بـ `78.141.212.182` بس. في Bybit وOKX، المفاتيح اللي فيها صلاحيات كتابة ومش مربوطة بـ IP بتنتهي صلاحيتها بعد مدة.

## اللي تراجعه بنفسك في المتصفح (قراءة بس)

1. **Binance:** صفحة API Management، شوف هل فيه خيار C2C/P2P. وصفحة Merchant، شوف حالة التوثيق.
2. **OKX:** صفحة P2P API، شوف هل فيه طلب مقدّم أو حالة موافقة. ومستوى الميرشانت (Super/Diamond؟).
3. **Bybit:** صفحة P2P Advertiser، شوف مستواك. وفي إنشاء المفتاح، شوف هل خانة **FiatP2P** ظاهرة.
4. **Bitget:** صفحة Advertiser Privileges، شوف هل P2P API ظاهر. وفي API Key Management، شوف صلاحيات P2P.

## المصادر

- Binance: [Binance Skills Hub – p2p](https://www.binance.com/en/skills/detail/binance/p2p) · [SKILL.md](https://github.com/binance/binance-skills-hub/blob/main/skills/binance/p2p/SKILL.md) · [C2C REST API](https://developers.binance.com/docs/c2c/rest-api)
- OKX: [Announcing the P2P API for Super & Diamond Merchants](https://www.okx.com/help/announcing-the-p2p-api-for-super-and-diamond-merchants-trade-smarter) · [P2P API User Agreement](https://www.okx.com/help/p2p-api-user-agreement) · [OKX API FAQ](https://www.okx.com/en-us/help/api-faq)
- Bybit: [P2P API Guide](https://bybit-exchange.github.io/docs/p2p/guide) · [Release Digital Asset](https://bybit-exchange.github.io/docs/p2p/order/release-digital-asset) · [bybit_p2p (GitHub)](https://github.com/bybit-exchange/bybit_p2p)
- Bitget: [How to Use Bitget P2P API?](https://www.bitget.com/support/articles/12560603884311) · [Bitget P2P API Is Now Live](https://www.bitget.com/support/articles/12560603894639) · [Get Merchant P2P Orders](https://www.bitget.com/api-doc/common/p2p/Get-P2P-Order-List)
