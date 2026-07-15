# "Loop Engineering"i Test Etmek İstedim. Loop Hiç Dönmedi — ve Asıl Ders Buydu.

*Claude Code (Opus 4.8) ile kontrollü, tekrarlanabilir bir deney. Gerçek
rakamlar ve dürüst bir negatif sonuç.*

---

Haziran 2026'da internetin yazılım-AI köşesini yeni bir terim ele geçirdi:
**loop engineering**. Peter Steinberger açıkça söyledi — *"Artık kodlama
ajanlarına prompt yazmamalısınız. Ajanlarınıza prompt yazan loop'ları
tasarlamalısınız."* Anthropic'te Claude Code'un başındaki Boris Cherny de kendi
işi için aynısını söyledi: *"Ben artık Claude'a prompt yazmıyorum. Claude'a
prompt yazıp ne yapacağına karar veren loop'larım çalışıyor. Benim işim loop
yazmak."* Addy Osmani
[disiplini isimlendirdi](https://addyosmani.com/blog/loop-engineering/), ve ay
bitmeden Anthropic kendi
[loop taksonomisini](https://claude.com/blog/getting-started-with-loops)
yayınladı.

Bulabildiğim her yazı loop engineering'in *ne olduğunu* anlatıyordu. Hiçbiri
*ne zaman gerçekten işe yaradığını* kontrollü bir deneyle ölçmemişti. Ben
ölçtüm — ve sonuç beni neredeyse yayınlamayacak kadar şaşırttı. Sonra fark
ettim: asıl bulgu, o şaşkınlığın **kendisiydi**.

**Özet:** Aynı, iyi tanımlanmış görevi Claude Code'a dört farklı yöntemle
verdim, her birini ajanın hiç görmediği gizli bir test paketiyle puanladım;
maliyet, süre ve kaliteyi ölçtüm. Düz tek-atış prompt **%100** aldı.
Hedef-tabanlı bir loop (`/goal`) da **%100** aldı — ve dış loop'u **sıfır**
ekstra iterasyon çevirdi. Bu kadar temiz bir görevde loop gereksizdi. Asıl soru
"loop çalışıyor mu" değil — "doğrulama döngüsü gerçekte nerede yaşıyor" ve iyi
bir spec için cevap: *tek bir turun içinde*.

---

## Kimsenin ayırmadığı katmanlar

Deneyden önce, çoğu yazının bulanıklaştırdığı bir ayrım:

- **İç loop:** Yetenekli her kodlama ajanının *tek bir* turun içinde yaptığı
  şey: akıl yürüt → eyleme geç (dosya düzenle, test çalıştır, endpoint'e istek
  at) → gözlemle → tekrarla. Bunu sen tasarlamıyorsun; model böyle çalışıyor.
- **Dış loop:** *Senin* tasarladığın şey: `/goal`, `/loop`, zamanlanmış
  rutinler — ajanı bir durma koşuluna kadar birçok tur veya session boyunca
  yeniden dürten harness. **"Loop engineering" tam olarak budur.**

Bu ikisini ayrı tut, çünkü bu deneyin tüm sonucu aralarındaki boşlukta yaşıyor.

Anthropic'in kendi taksonomisi dış loop'ları dörde ayırıyor:

| Loop tipi | Tetikleyici | Duruş | Primitive |
|---|---|---|---|
| Turn-based | Promptun | Model "bitti" der | düz prompt |
| Goal-based | Promptun | Bir evaluator koşulu onaylar | `/goal` |
| Time-based | Zamanlama | Sen iptal edersin / iş biter | `/loop`, `/schedule` |
| Proactive | Bir olay, insan yok | Her görev hedefine ulaşınca | routines + workflows |

## Deney

**Tek görev, dört farklı yöntem.** Görev: tek bir spec dosyasından (`SPEC.md`)
bir **Görev Yöneticisi REST API'si** inşa etmek — 15 endpoint, API-key kimlik
doğrulama, key-başına çok kiracılılık (multi-tenancy), header'lı rate limiting,
sayfalama, toplu işlemler, durum geçişleri, etiket normalleştirme ve bir yığın
isimli edge-case. Hacimli, ama tam tanımlı.

Planlanan dört koşu:

- **A — Tek-atış:** tek prompt, hiç takip yok.
- **B — Turn-based:** insan her turda sadece mekanik hata çıktısını iletir.
- **C — Goal-based:** doğrulanabilir durma koşuluyla `/goal`, sonra çekil.
- **D — Otonom:** `/loop` + öz-doğrulama skill'i, gözetimsiz çalışır.

**Dürüstlük mekanizması.** Kaliteyi, API'yi HTTP üzerinden süren **71 testlik
kara-kutu kabul paketi** puanlıyor. Ajan bu paketi **asla görmüyor** — bu, bir
modelin okuyabildiği testlere ezberleyerek "geçmesi" gibi bariz hileyi imkânsız
kılıyor. Her koşu temiz bir klasörde ve temiz bir session'da yapılıyor. Önce bir
referans implementasyon yazıp paketin ona 71/71 verdiğini doğruladım; böylece
düşük bir puan bozuk testi değil, gerçek bir kusuru gösterir.

Her şey — spec, gizli paket, promptlar, ham metrikler —
[repo'da](https://github.com/zexy2/loop-engineering-experiment). Mesele bu
zaten: tekrar çalıştırıp beni denetleyebilirsin.

**Baştan bir bütçe itirafı:** Bunu standart bir planla yaptım, kurumsal bir
token musluğuyla değil. Bu kısıt bulguları şekillendirdi, o yüzden onu
saklamak yerine veri olarak raporluyorum.

## Gerçekte ne oldu

### Koşu A — Tek-atış: %100

Tam olarak tek prompt gönderdim: *"SPEC.md'yi oku ve tarif ettiği API'nin
tamamını uygula. Uygulamanın bittiğine inanana kadar çalış, sonra dur."*

Ajan dört dosyada 805 satır yazdı — ve sonra, **istenmediği halde**, bir
virtualenv kurdu, bağımlılıkları yükledi, anahtarları seed'ledi, gerçek
sunucuyu başlattı ve her endpoint'i ve edge-case'i curl ile deneyip yol
boyunca düzeltti. Durup "uçtan uca tamamlandı ve doğrulandı" dediğinde, iyimser
bir abartı bekledim.

Gizli paket: **71/71. %100.** İddia doğruydu.

Ama *ne olduğuna* bak: bu "tek-atış" üret-ve-dur değildi. Model tam bir
doğrulama döngüsünü **tek turunun içinde** çalıştırdı. Bu tam olarak Cherny'nin
kuralı — *"Claude'a işini doğrulayacak bir yol ver, kaliteyi 2-3× artırır"* —
ama kimse ona bir şey vermedi. Doğrulamayı kendi sağladı.

### Koşu C — Goal-based loop: yine %100, sıfır ekstra tur

Aynı görev, ama şimdi dış bir loop'a sardım. Aynı açılış promptundan sonra bir
hedef koydum:

> `/goal SPEC.md'de tarif edilen API tamamen uygulanmış; sunucu temiz başlıyor;
> kendi yazdığın bir smoke script her endpoint'i deniyor … ve her kontrol,
> sunucu çıktısı kanıt gösterilerek geçiyor. En fazla 5 turda dur.`

Sonra ayrıldım. `/goal` primitive'i her turdan sonra ayrı bir evaluator model
çalıştırıp koşulu kontrol ediyor ve koşul sağlanana ya da tur tavanına ulaşana
kadar ajanı çalıştırıyor.

Sonuç: **`Goal achieved (8m · 1 turn · 39.4k tokens)`.** Evaluator **ilk**
turdan sonra "bitti" dedi. Loop engineering'in tüm amacı olan dış loop,
**sıfır** ek iterasyon çevirdi. Gizli paket puanı: **yine 71/71.**

Neden? Koşu A ile aynı sebep. Model tek turunun içinde 70-iddialı bir smoke
test yazdı, onu canlı bir sunucuya karşı çalıştırdı, seed çıktısını `od -c` ile
bayt bayt kontrol etti, sonra temiz teslim etmek için çalışma dosyalarını sildi.
Doğrulama döngüsü *turun içinde* yaşadı; dış harness'a yapacak bir şey kalmadı.

### İki koşu yan yana

| Metrik | Koşu A (tek-atış) | Koşu C (`/goal`) |
|---|---|---|
| **Kabul puanı** | **71/71 (%100)** | **71/71 (%100)** |
| Dış-loop iterasyonu | 0 (tek prompt) | **1** (tavan 5'ti; 0 ekstra) |
| İnsan müdahalesi | 0 | 0 |
| Uygulama kodu satırı | 805 (4 dosya) | 1046 (7 dosya) |
| Rate-limit tasarımı | sabit pencere | kayan pencere |
| Spec dışı kapsam taşması | yok | yok (+`.gitignore`) |

![Her iki koşu da %100 aldı; goal-based loop sıfır ekstra iterasyon çevirdi](charts/chart1_score_turns.png)

İki bağımsız, tamamen doğru implementasyon — hatta *farklı* ama savunulabilir
tasarım kararları bile verdiler (sabit vs kayan pencere) — çünkü iyi bir spec
yargıya alan bırakır ve pencere-agnostik testler ikisini de kabul eder.

## Bir efsaneyi yıkan maliyet bulgusu

Loop'lar hakkında en çok tekrarlanan uyarı: "dikkat, pahalıya patlarlar."
`/usage` dökümü, bu uyarının genelde neden **yanlış yere** atfedildiğini
gösterdi.

Koşu C'nin maliyet raporunda **iki** model vardı:

```
claude-opus-4-8:  3.9k in, 39.4k out, 845k cache read, 51k cache write   $1.94
claude-haiku-4-5:   547 in,   277 out,      0 cache read, 27k cache write $0.036
```

O ikinci satır `/goal` **evaluator'ı** — her turda durma koşulunu kontrol eden
"hakem". Ucuz Haiku üzerinde çalışıyor ve maliyeti **3.6 sent: koşunun ~%1.8'i.**

Yani loop, evaluator yüzünden pahalı **değil**. Bir loop yalnızca **ekstra
tur** tetiklediğinde pahalanır — her tur context'i yeniden okur, araçları
yeniden çalıştırır, çıktıyı yeniden üretir. Burada sıfır ekstra tur tetikledi,
o yüzden tüm goal-based koşu **her şey dahil $1.97'ye**, 1046 satırlık,
%100-doğru bir API için geldi. Ucuz.

![/goal evaluator'ı maliyetin %1.8'iydi; loop'lar sadece ekstra tur zorladıklarında pahalı](charts/chart2_cost_breakdown.png)

Ders genelleşiyor: *bir loop'un maliyeti kabaca bir turun maliyeti × zorladığı
tur sayısıdır.* Görevin bir turda kapanıyorsa dış loop neredeyse bedava.
Yirmi tur boyunca debeleniyorsa — işte fatura ve "kontrolden çıkmış commit"
korku hikâyeleri oradan geliyor.

## Token-fakir gerçeği (çoğu yazının atladığı kısım)

Temiz metrik tablosuna girmeyen şu var. Koşu A bir duvara çarptı — kelimenin
tam anlamıyla:

```
API Error: 402 {"error":"5 saatlik dahil-kullanım limitine ulaşıldı.
Bu pencere için 5.00$ tahsisatını kullandın."}
```

…12. dakikada, doğrulamanın ortasında. Koşu, kullanım pencereleri sıfırlandıkça
iki gün boyunca **üç** session'a bölünerek duraklatılıp devam ettirilmek zorunda
kaldı. Koşu A'nın maliyetinin bile temiz toplanamamasının sebebi bu: session'lara
bölünmüş durumda, ve son session'ın `/usage`'ı harfiyen *"0 satır değişti"*
diyor çünkü kod daha önceki bir session'da yazılmıştı.

Dört koşu planlamıştım. **İkisini koştum.** B ve D koşuları repo'da tasarlanmış
ve tekrarlanabilir, ama onları çalıştırmadım — bir blog yazısına harcamaya razı
olduğum bütçeyi tükettim.

Bu bir dipnot değil; bir bulgu. Osmani orijinal yazısında loop ekonomisinin
"token zengini ya da fakiriysen çılgınca değişebileceği" uyarısını yapmıştı.
Loop engineering — özellikle sen uyurken çalışan otonom türü — sessizce cömert
bir token bütçesi varsayar. Normal bir plandaysan, dürüst manşet şu: *sana
kurman söylenen dış loop, otomatikleştirdiği şeyden daha pahalıya patlayabilir
ve bunu 12. dakikada hissedersin.*

## Peki — deney "yanlış" mıydı?

Adil bir okur (ve kendi vicdanım) sordu: *loop'ları test etmeye çıktın ama loop
aslında hiç dönmedi. Bu bozuk bir deney değil mi?*

Kısmen, evet — ve bunu açıkça söylemeye değer. Bir loop çok iterasyon çevirdiğinde
nasıl performans gösterdiğini ölçmedim. Daha dar ve bence daha yararlı bir şey
ölçtüm: **iyi tanımlı, kendine yeterli, tek turda doğrulanabilir bir görevde dış
loop gereksizdir.** Modelin iç loop'u boşluğu zaten kapatıyor.

Bu "loop'lar işe yaramaz" değil. Bu "loop'lar, bu görevin sahip olmadığı bir
problemi çözer" demek. Ve bu, asıl soruyu yeniden çerçeveliyor.

## Dış loop maliyetini ne zaman gerçekten hak eder?

Anthropic'in taksonomisini gözlemlerimle çaprazlayınca, dış loop tam olarak
**iç** loop kendi başına kapanamadığında değer üretiyor — şunlardan en az biri
doğruysa:

- **Spec belirsiz veya evriliyor.** Her iterasyon rotayı düzeltme fırsatı. Net
  bir spec (benimki gibi) bu ihtiyacı tamamen ortadan kaldırıyor.
- **"Bitti" dış duruma bağlı.** Flaky bir bağımlılık, drift olan gerçek bir
  veritabanı, kırmızıya dönen CI, review yorumu gelen bir PR — modelin tek
  turda çözemeyeceği, çünkü gerçeklik turlar arasında değişen şeyler. (`/loop`,
  proactive.)
- **İş tek context penceresine sığmıyor.** Modelin bir durum dosyasını hafıza
  olarak kullanıp turlar/session'lar boyunca yontması gereken büyük bir migrasyon.
- **İş tekrarlayan.** Aynı görev, yeni girdiler, bir zamanlamada — sabah triyajı,
  bağımlılık taramaları. Burada loop opsiyonel değil; tasarımın kendisi.

Benim görevimde bunların **hiçbiri** yoktu. Loop'un boşta oturmasının sebebi de
tam olarak buydu.

**Pratik bir kural:** bir loop tasarlamadan önce, iyi bir spec artı modelin
kendi çalıştırabileceği bir doğrulamanın görevi tek turda kapatıp
kapatmayacağını sor. Cevap evetse, loop'u değil, spec'i ve kontrolü yaz. Loop
engineering güçlüdür ama o, *"iç loop bunu tek başına bitiremez"* sorusunun
cevabıdır, varsayılan bir duruş değil. Osmani'nin kapanış cümlesi tam oturuyor:
kaldıraç noktası kaydı, iş kolaylaşmadı. Bir spec yeterken loop'a uzanmak, aynı
%100'ü almanın sadece daha pahalı bir yolu.

## Dürüst sınırlılıklar

- **Yöntem başına n = 1.** Bu bir vaka çalışması, benchmark değil. Eğilimler,
  kanıtlar değil.
- **Dört koşunun sadece ikisi çalıştırıldı** (bütçe). B ve D repo'da,
  çalıştırılmadı.
- **Tek görev tipi** (bir CRUD API). Sonuçlar UI işine, algoritmik problemlere
  veya gerçekten açık uçlu görevlere transfer olmayabilir.
- **İç/dış loop ayrımı "tek-atış" temelini bulanıklaştırıyor** — Koşu A saf bir
  tek atış değildi, çünkü model içeride döngü kuruyor. Bu bulanıklık zaten ana
  bulgunun kendisi.

## Tekrarla

Tüm harness — spec, gizli 71-testlik paket, puanlayıcı, iki koşunun çıktısı, her
ham metrik ve çalıştırılmamış iki koşu tasarımı — burada:

**→ https://github.com/zexy2/loop-engineering-experiment**

Klonla, kendi ajanına yönelt ve bir loop kurmadan önce görevinin loop'a ihtiyacı
olup olmadığını kontrol et.

*Claude Code (Opus 4.8) ile inşa edildi ve ölçüldü. Buradan tek bir şey
alacaksan: iç loop'u dış loop'tan ayır ve ilki işi çoktan bitirdiyse ikincisine
para ödeme.*
