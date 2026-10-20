# محرك عثمان · Othman Engine

[العربية](#العربية) · [English](#english)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/vvd7mvv/othman-engine/blob/main/colab.ipynb)

## العربية

محرك مفتوح المصدر يستقبل **ملف تلاوة** (صوت أو فيديو)، ويخرج **السورة والآيات** ووقت بداية ونهاية **كل آية وكل كلمة**،
ووقفات القارئ للنفَس داخل الآية.

- **يتعرف على السورة لحاله:** لا تحتاج تحديد السورة، والمقطع قد يكون جزءاً من سورة أو يعبر سورتين.
- **يتحمل التلاوة الحقيقية:** الاستعاذة والكلام غير القرآني يُتجاهلان، وإعادة الآية، والوقف والابتداء، والحروف المقطعة.
- **يعمل على المعالج:** بلا كرت شاشة ولا PyTorch، بذاكرة نحو 1GB. تلاوة 9 دقائق تُعالج في نحو 15 ثانية على 4 أنوية.
  وكرت الشاشة اختياري: ثبّت `onnxruntime-gpu` بدل `onnxruntime` فيستخدمه المحرك تلقائياً (`--device cpu` لمنعه).

هو المحرك الذي يعمل خلف موقع "عثمان" لرسم الآيات على مقاطع التلاوات.

### المتطلبات
- Python 3.10 أو أحدث، و`ffmpeg` (`sudo apt install ffmpeg`).
- حساب في Hugging Face: النموذج يتطلب **قبول شروطه** من [صفحته](https://huggingface.co/Muno459/fastconformer-quran)،
  ثم [إنشاء token](https://huggingface.co/settings/tokens) (صلاحية Read تكفي).

### التثبيت
```bash
pip install git+https://github.com/vvd7mvv/othman-engine
export HF_TOKEN=hf_...          # الـ token من Hugging Face
othman-engine download          # النموذج (~1GB) ونص Tanzil، مرة واحدة
```
تُحفظ الملفات في `~/.othman-engine`، ويمكن تغيير المكان بمتغير البيئة `OTHMAN_ENGINE_HOME`.

### الاستخدام
**بلا تثبيت:** جرّبه في Google Colab من الزر أعلى الصفحة (`colab.ipynb`).

**مصحف كامل:** `notebooks/othman_engine_batch.ipynb` يوقّت سوراً من روابط صوت (مثل مجلد قارئ في mp3quran)، ويحفظ
ملف JSON لكل سورة في Google Drive أولاً بأول، ويكمل من حيث توقف. ويقبل مجلد ملفات في Drive (السورة من اسم الملف: رقم أو «سورة عبس»). وبنفس المدخلات والصيغة `munajjam_batch.ipynb`
لمحرك [منجّم](https://github.com/Itqan-community/Munajjam)، و`compare_engines.ipynb` يقارن الاثنين بتوقيت mp3quran.
`listen_compare.ipynb` استماع أعمى: تسمع قصّ كل مصدر للآية بأسماء مخفية وتصوّت للأفضل، وفي النهاية نسبة فوز كل مصدر.

```bash
othman-engine align recitation.mp3 -o result.json
othman-engine align clip.mp4 --start 30 --end 95      # جزء من الملف فقط (بالثواني)
```

من بايثون:
```python
from othman_engine import Engine

engine = Engine()                      # يحمّل النموذج مرة واحدة
result = engine.align_file("recitation.mp3")
for segment in result.quran_segments():
    print(segment.surah, segment.ayah, segment.start, segment.end)
```

### الناتج
```json
{
 "duration": 51.96,
 "matched_ratio": 0.83,
 "segments": [
  {
   "surah": 1, "ayah": 1, "start": 7.74, "end": 12.7, "confidence": 1.0,
   "words": [{"index": 0, "start": 7.74, "end": 8.3}, ...],
   "pauses": [],
   "surah_name_ar": "الفاتحة", "surah_name_en": "Al-Faatiha"
  }
 ]
}
```
- `ayah: 0` هي البسملة في أول السور (عدا الفاتحة لأنها آيتها الأولى، والتوبة).
- `words[].index` ترتيب الكلمة في نص Tanzil الإملائي للآية. للعرض بنص آخر (مثل نص مجمع الملك فهد) استخدم رقم السورة والآية.
- `confidence` نسبة كلمات الآية التي طابقها التفريغ (أقل من 0.8 يستحق المراجعة).
- `pauses` وقفات القارئ للنفَس داخل الآية.
- الآيات المكررة تظهر مرة لكل قراءة.

### الدقة
`scripts/evaluate.py` يقيس على تلاوات سور كاملة متصلة من quranicaudio (لا ملفات everyayah، لأن النموذج تدرّب عليها):

| التلاوة | المدة | النتيجة | الوقت (4 أنوية) |
|---|---|---|---|
| الفاتحة، المنشاوي | 52 ث | ✓ | 1.7 ث |
| الفلق والناس، الحصري | 105 ث | ✓ | 3.0 ث |
| الطارق، المعيقلي | 123 ث | ✓ | 3.4 ث |
| النبأ، القطامي (يكرر الآيات) | 303 ث | ✓ | 8.4 ث |
| الملك، السديس | 357 ث | ✓ | 10.5 ث |
| الرحمن، الدوسري | 530 ث | ✓ | 14.5 ث |

```bash
git clone https://github.com/vvd7mvv/othman-engine && cd othman-engine
pip install -e ".[dev]"
python scripts/evaluate.py      # يحمّل التلاوات (~40MB) أول مرة
pytest tests                    # اختبارات سريعة بلا نموذج (تحتاج نص Tanzil)
```

### كيف يعمل
1. **التفريغ** (`asr/`): نموذج FastConformer مدرّب على التلاوات (ONNX). الموديل تدرّب على آيات مفردة فيُسقط أجزاءً من المقاطع الطويلة،
   لذلك يُقطَّع الصوت عند أهدأ النقاط إلى 12 ثانية فأقل، وتُعاد قراءة أي فجوة أطول من 2.5 ثانية بين الكلمات.
2. **المطابقة** (`match.py`): ثلاثيات الكلمات تحدد مواضع محتملة في المصحف كله، وسلسلة المقاطع الأفضل بالبرمجة الديناميكية،
   ثم محاذاة الكلمات داخل الفجوات. قائمة ثابتة للحروف المقطعة لأن النموذج يقطّعها ويكررها.
3. **التوقيت** (`alignment.py`): آية لكل قراءة، ووقت كل كلمة.
4. **وقفات النفَس** (`pauses.py`): من هدوء الصوت نفسه لا من فراغ توقيت الكلمات (النموذج يقطع المد مبكراً).

### الرخص والمصادر
- **كود هذا المستودع:** رخصة MIT (ملف `LICENSE`).
- **النموذج** [Muno459/fastconformer-quran](https://huggingface.co/Muno459/fastconformer-quran) لا يُوزَّع هنا بل يُحمَّل من صفحته،
  وله رخصته **NPL-1.1 التي تمنع أي استخدام ربحي** (لا بيع ولا إعلانات ولا اشتراكات، حتى لميزات أخرى في نفس التطبيق).
  مبني على [NVIDIA FastConformer](https://huggingface.co/nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0) (CC-BY-4.0).
- **نص المصحف وبيانات السور:** [Tanzil](https://tanzil.net)، يُحمَّل كما هو، ورخصته تسمح بالنسخ بلا تعديل مع ذكر المصدر.

---

## English

An open-source engine that takes a **Quran recitation file** (audio or video) and returns the **surah and ayahs**, with start and end
times for **every ayah and every word**, plus the reciter's breathing pauses inside long ayahs.

- **Finds the surah by itself:** no surah number needed; a clip can start mid-surah or cross two surahs.
- **Handles real recitations:** isti'adha and other speech are ignored; repeated ayahs, waqf and ibtida', and the disjoined letters work.
- **Runs on the CPU:** no GPU, no PyTorch, about 1 GB of RAM. A 9-minute recitation takes about 15 seconds on 4 cores.
  A GPU is optional: install `onnxruntime-gpu` instead of `onnxruntime` and the engine uses it (`--device cpu` to opt out).

It is the engine behind the "Othman" site that draws the ayahs on recitation videos.

### Requirements
- Python 3.10+ and `ffmpeg`.
- A Hugging Face account: the model is gated. Accept its terms on [its page](https://huggingface.co/Muno459/fastconformer-quran),
  then [create a token](https://huggingface.co/settings/tokens) (read access is enough).

### Install
```bash
pip install git+https://github.com/vvd7mvv/othman-engine
export HF_TOKEN=hf_...
othman-engine download          # the model (~1 GB) and the Tanzil text, once
```
Files go to `~/.othman-engine`; set `OTHMAN_ENGINE_HOME` to change that.

### Use
**No install:** try it in Google Colab with the button at the top (`colab.ipynb`).

**Whole mushaf:** `notebooks/othman_engine_batch.ipynb` times surahs from audio URLs (e.g. a reciter folder on mp3quran),
saves one JSON per surah to Google Drive as it goes and resumes where it stopped. It also takes a Drive folder of files (surah from each name: a number or «سورة <name>»). `munajjam_batch.ipynb` does the same
with [Munajjam](https://github.com/Itqan-community/Munajjam), and `compare_engines.ipynb` compares both with mp3quran's timings.
`listen_compare.ipynb` is a blind listening test: vote for the best cut of each ayah, then see each source's win rate.

```bash
othman-engine align recitation.mp3 -o result.json
othman-engine align clip.mp4 --start 30 --end 95      # only part of the file (seconds)
```
```python
from othman_engine import Engine

engine = Engine()                      # loads the model once
result = engine.align_file("recitation.mp3")
for segment in result.quran_segments():
    print(segment.surah, segment.ayah, segment.start, segment.end)
```

### Output
See the JSON example above. `ayah: 0` is the basmala at the start of a surah (except Al-Fatiha, where it is ayah 1, and At-Tawba).
`words[].index` is the word's position in the Tanzil simple text of the ayah; use the surah and ayah numbers to show any other text,
such as the King Fahd Complex Uthmani script. `confidence` is the share of the ayah's words the transcription matched (below 0.8 is
worth a look). A repeated ayah appears once per reading.

### Accuracy
`scripts/evaluate.py` runs on full, continuous surah recitations from quranicaudio (not everyayah files, which the model was trained on).
All six cases pass; see the table above for durations and timings.

### Licences and sources
- **This repository's code:** MIT (see `LICENSE`).
- **The model** [Muno459/fastconformer-quran](https://huggingface.co/Muno459/fastconformer-quran) is not redistributed here; it is
  downloaded from its page and carries its own **NPL-1.1 licence, which forbids any profit** (no sales, ads or subscriptions, even for
  unrelated features of the same app). It is built on [NVIDIA FastConformer](https://huggingface.co/nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0) (CC-BY-4.0).
- **Quran text and surah data:** [Tanzil](https://tanzil.net), downloaded unchanged; its terms allow verbatim copies with attribution.
