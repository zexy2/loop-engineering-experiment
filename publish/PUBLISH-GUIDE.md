# Medium'a Yayınlama Rehberi (3 dakika)

Medium'un resmî yayın API'si 2023'te kapandı, o yüzden akış manuel — ama hızlı.

## Adımlar

1. **[medium.com/new-story](https://medium.com/new-story)** aç.
2. Dil seç: Türkçe için `MEDIUM-TR.md`, İngilizce için `MEDIUM-EN.md`.
3. Dosyanın en üstündeki yorumdan **Başlık** ve **Alt başlık**'ı al, Medium'un
   başlık alanlarına yaz.
4. **"GÖVDE BAŞLANGICI"** (EN: "BODY START") satırından **"GÖVDE SONU"**'na kadar
   olan kısmı kopyala, Medium editörüne yapıştır. Medium; başlıkları, kalınları,
   listeleri, alıntıları (`>`) ve kod bloklarını (` ``` `) otomatik biçimlendirir.
5. **Görseller:** metinde `[GÖRSEL: ...]` / `[IMAGE: ...]` yazan her yere ilgili
   PNG'yi **sürükle-bırak**, sonra o satırı sil. Sıra:
   - `article/charts/chart1_score_turns@2x.png`
   - `article/charts/chart2_cost_breakdown@2x.png`
   - senin **`402 Usage limit reached`** ekran görüntün
6. **Kapak görseli:** `chart1_score_turns@2x.png` iyi bir kapak olur.
7. **Etiketler** (max 5): `Loop Engineering, AI, Claude, Software Engineering, Developer Tools`
8. Önizle → Yayınla.

## Neden tablo yok?

Medium markdown tablolarını render etmiyor (yapıştırınca dağılır). Bu yüzden
iki ana karşılaştırma tablosunu **grafik** yaptım, kalan tabloları da liste/metin
biçimine çevirdim. `article/` klasöründeki orijinal `.md` dosyaları tabloları
korur (GitHub için); bu `publish/` sürümleri Medium için optimize edilmiştir.

## İpuçları

- İlk 2-3 cümle Medium önizlemesinde görünür — güçlü açılış zaten var.
- Yayın sonrası kanonik URL'yi (Medium sana verir) istersen repo README'sine
  ekleyebilirsin.
- İki dili ayrı yazı olarak yayınla; her birinin sonundaki repo linki aynı.
