# خطة Hot Reload Studio — FlutterWay

> **الحالة:** خطة فقط — لم يُنفَّذ أي كود جديد بعد.
> **آخر كوميت قبل الخطة:** `e2178de` — الفرع متقدم 11 كوميت عن `origin/main`.

---

## 1. الهدف

إضافة تبويب داخل التطبيق يسمح للطالب بتجربة **Hot Reload الحقيقي**:

- يفتح مشروعاً موجوداً.
- يعدّل `lib/main.dart` داخل محرر مدمج.
- يتحدّث التطبيق على الهاتف تلقائياً بعد توقف الكتابة (~900ms) **بدون زر وبدون Enter**.
- أزرار احتياطية: Hot Reload الآن، Hot Restart، إيقاف.
- سجل حي يعرض `Reloaded … in Xms`، ومعاينة شاشة الهاتف.

---

## 2. ما تم إثباته فعلياً (أساس الخطة)

- `flutter attach` لم يستجب على هذا الجهاز.
- `flutter run --use-application-binary app-debug.signed.apk` نجح:
  - تثبيت APK بحجم **71MB** في **3.5 ثانية**.
  - بعد تعديل `lib/main.dart` وإرسال `r`:
    `Reloaded 1 of 754 libraries in 1,222ms`
  - شاشة الهاتف أظهرت النص الجديد فوراً (`tmp/hot_reload_test.png`).
  - إعادة النص الأصلي و`r` ثانياً: **900ms**.
- إذن المسار المعتمد هو `flutter run --use-application-binary` وليس `flutter attach`.

---

## 3. المعمارية المقترحة

### 3.1 `gui/hot_reload.py` (جديد)

كلاس `HotReloadSession`:

- `start(project_path, serial)`:
  - يتحقق من `lib/main.dart` ووجود الهاتف.
  - يفضّل `build/app/outputs/flutter-apk/app-debug.signed.apk`.
  - إن وُجد: `flutter run -d <serial> --debug --use-application-binary <apk>`.
  - إن لم يوجد: رسالة واضحة "ابنِ التطبيق أولاً من تبويب المشاريع" (وليس بناء 636MB صامتاً).
  - `Popen(stdin=PIPE, stdout=PIPE, stderr=STDOUT)` + خيط قراءة.
  - ينتظر `r Hot reload.` أو `A Dart VM Service` حتى 120 ثانية.
- `save(content, reload=True)`:
  - يكتب `lib/main.dart` بعد التحقق من المسار.
  - إن كان الجلسة جاهزة: يرسل `r\n`.
- `action("reload" | "restart" | "stop")`:
  - `r` / `R` / `q` أو terminate.
- `read_main()`.
- `status()`:
  - `running`, `ready`, `project_path`, `last_reload_ms`, `logs` (آخر 200 سطر), `vm_service`.
- تحليل السجل:
  - `Reloaded … in ([\d,]+)ms` → `last_reload_ms`.
  - `Flutter run key commands` → `ready=True`.
- Singleton داخل `OnboardingApi` + `atexit` لإغلاق العملية.

### 3.2 API في `OnboardingApi`

- `hot_reload_start(project_path=None)`.
- `hot_reload_read()`.
- `hot_reload_save(content)`.
- `hot_reload_action(action)`.
- `hot_reload_status()`.
- `hot_reload_screenshot()` → يستخدم `capture_device_screenshot_b64`.

### 3.3 الواجهة (تبويب جديد)

- زر في `companion-subnav`: `btn-tab-hotreload` → "التحديث الفوري".
- بانل `tab-hotreload` يحتوي:
  - اسم المشروع النشط ومساره.
  - حالة الاتصال + آخر زمن Reload.
  - `<textarea id="hr-editor">` بخط monospace، LTR، بدون syntax highlighting.
  - `checkbox` "تحديث تلقائي عند الكتابة" (مفعّل افتراضياً).
  - أزرار: بدء الجلسة، Hot Reload الآن، Hot Restart، إيقاف.
  - `<pre id="hr-log">` للسجل.
  - `<img id="hr-preview">` لشاشة الهاتف (تحديث كل 2 ثانية أثناء الجلسة).

### 3.4 التحديث التلقائي

```
oninput في textarea
  → debounce 900ms
  → لو المحتوى تغيّر
  → hot_reload_save(content)
  → Python يكتب الملف ويرسل "r"
```

- لا يوجد Enter ولا زر مطلوب.
- أثناء الكتابة السريعة لا يُرسل أكثر من Reload واحد.
- لو الجلسة غير جاهزة: يتم الحفظ فقط، ويظهر تنبيه.
- أخطاء Dart تظهر في السجل؛ التطبيق يبقى على آخر نسخة ناجحة.

---

## 4. VS Code — كيف لا يتأثر مستقبلاً

المشكلة: VS Code F5 سيبني APK debug جديداً. على هذا الجهاز (بدون NDK) سيكون ~636MB ويستغرق وقتاً.

الحلول بالترتيب:

1. **`.vscode/launch.json` في المشروع**:
   ```json
   {
     "name": "FlutterWay (prebuilt 71MB)",
     "request": "launch",
     "type": "dart",
     "args": [
       "--use-application-binary",
       "build/app/outputs/flutter-apk/app-debug.signed.apk"
     ]
   }
   ```
   - يحتاج اختباراً داخل VS Code للتأكد أن إضافة Dart تمرر الوسيط.
   - إن نجح: F5 يستخدم APK الجاهز، تثبيت سريع، وHot Reload يعمل.

2. **خطوة Gradle لتجريد مكتبات `.so` بعد البناء** (نفس `gui/elf_strip.py`):
   - تحتاج أداة strip متاحة على جهاز الطالب، أو سكربت Python مرفق.
   - تُؤجل لحين التأكد من الخيار 1.

3. **NDK** — مرفوض لأنه فخ 6.7GB.

**ملاحظة:** حجم 71MB لا يقيّد الكود ولا الميزات؛ يؤثر فقط على زمن أول تثبيت/مساحة الجهاز.

---

## 5. خطة الاختبار

### Static
- وجود `gui/hot_reload.py` و`gui.hot_reload` في `FlutterWayNative.spec`.
- وجود API والتبويب والأزرار.
- عدم وجود `flutter attach` في المسار.

### Real device (`tests/hot_reload_journey.py`)
1. فتح التطبيق عبر CDP.
2. `Companion → Hot Reload`.
3. اختيار مشروع `student_custom_142510` (يملك `app-debug.signed.apk`).
4. بدء الجلسة والانتظار حتى `ready`.
5. قراءة `lib/main.dart`.
6. استبدال أول `const Text(...)` بنص ASCII فريد.
7. إرسال `input` للـ textarea (بدون زر/Enter).
8. انتظار `Reloaded … in Xms` في السجل.
9. قراءة شاشة الهاتف عبر `uiautomator dump` والتأكد من ظهور النص الجديد.
10. لقطة شاشة + استعادة النص الأصلي + Reload.
11. إيقاف الجلسة والتأكد من عدم بقاء عملية `flutter run`.

### حالات حدّية
- مشروع بدون APK signed → رسالة "ابنِ التطبيق أولاً".
- فصل الهاتف أثناء الجلسة.
- خطأ Syntax في المحرر.
- إغلاق التطبيق أثناء الجلسة (`atexit`).
- تعديل سريع متتابع (debounce).
- مشروع release (بدون VM service) → منع Hot Reload ورسالة واضحة.

---

## 6. معايير القبول

- [ ] تثبيت أول مرة ≤ 10 ثوانٍ باستخدام APK 71MB.
- [ ] Hot Reload ≤ 3 ثوانٍ، ويظهر `Reloaded ...` في السجل.
- [ ] النص يتغير على شاشة الهاتف بدون زر/Enter.
- [ ] لا إعادة بناء/تثبيت عند كل تعديل.
- [ ] لا أخطاء JavaScript في الكونسول.
- [ ] إيقاف الجلسة لا يترك `flutter run` أو `dart` يتيماً.
- [ ] `tests/hot_reload_journey.py` ينجح على التابلت.

---

## 7. ترتيب التنفيذ

1. `gui/hot_reload.py` + API + اختبار وحدة بسيط.
2. تبويب الواجهة + المحرر + السجل + معاينة الهاتف.
3. التحديث التلقائي (debounce) + أزرار Reload/Restart/Stop.
4. `tests/hot_reload_journey.py` + اختبار على التابلت.
5. `.vscode/launch.json` واختباره، أو توثيق البديل.
6. تحديث README + rebuild + commit.

---

## 8. مهام متبقية خارج Hot Reload

- `@media` / DPI 125–150% (الملاحظة الوحيدة من رحلة الطالب).
- Accessibility أوسع (تباين/قارئ شاشة).
- Installer (Inno Setup) + توقيع الكود + SmartScreen.
- تحديث README/الأرقام واللقطات.
- push للكوميتات (11 حالياً) عند توفر الشحن/الإنترنت.
- تنظيف مشروع الاختبار `student_custom_142510` من سطح المكتب والتابلت عند الانتهاء.
