# تبليغ الأخطاء — FlutterWay

> **الحالة:** تشخيص محلي + مشاركة اختيارية (GitHub أو ZIP). لا يوجد إرسال تلقائي.
> **آخر تحديث:** 2026-10-31 — schema 2، فصل السجل المحلي، تنقية أوسع، أحداث منظّمة.

---

## 1. كيف يصل البلاغ؟

```
خطأ في التطبيق
   ↓
سجل خام محلي فقط: logs\local\flutterway.log  (لا يُشارك أبداً)
   ↓
أحداث منظّمة منقّاة: logs\events\events.jsonl (اختيارية)
   ↓
المستخدم يفتح «أبلغ عن مشكلة»
   ↓
معاينة + وصف اختياري + موافقة
   ↓
GitHub Issue (المستخدم يراجع ويضغط Submit) أو حفظ ZIP وإرساله يدوياً
```

**لا يوجد GitHub Token داخل التطبيق.** الرابط فقط، والمستخدم هو من ينشر البلاغ.

---

## 2. من وين يفتح المستخدم البلاغ؟

- **المزيد → أبلغ عن مشكلة**.
- **شاشة فشل التجهيز** → زر «أبلغ عن المشكلة».
- **شاشة فشل البناء** → زر «أبلغ عن مشكلة البناء».
- أخطاء JavaScript تُسجّل محلياً تلقائياً، لكن **لا تُرسل** حتى يفتح المستخدم البلاغ.

---

## 3. شنو يُشارك؟

- إصدار FlutterWay + commit + تاريخ البناء (إن وُجد).
- نظام التشغيل + إصدار Python/WebView.
- المرحلة (تجهيز/بناء/Hot Reload/يدوي).
- رسالة الخطأ + Stack trace بعد التنقية.
- وصف المستخدم الاختياري.
- أحداث منظّمة **فقط** إذا فعّل المستخدم خيار الأحداث (حد أقصى 500 حدث).

## شنو ما يُشارك؟

- **السجل الخام `flutterway.log` — ممنوع تماماً في ZIP وGitHub والنص المنسوخ.**
- مسارات المنزل: `C:\Users\<name>` و`/home/<name>` و`/Users/<name>` → `<home>`.
- مسارات المشاريع المطلقة → `<path>`، ومسارات FlutterWay → `<project>` / `<appdata>`.
- Tokens: `ghp_`, `github_pat_`, `sk-`, `xoxb-`, `AIza`, `AKIA` → `<token>`.
- `password=`, `token=`, `api_key=`, `Authorization: Bearer` → `<redacted>`.
- البريد الإلكتروني → `<email>`، وروابط قواعد البيانات → `<connection-string>`.
- كود `main.dart` أو ملفات المشروع أو لقطات الشاشة.

> التنقية آلية وقد لا تكتشف كل المعلومات الحساسة. **راجع المحتوى قبل المشاركة.**

---

## 4. وين تُحفظ؟

- السجل الخام: `%LOCALAPPDATA%\FlutterWay\logs\local\flutterway.log` (**محلي فقط**)
- الأحداث: `%LOCALAPPDATA%\FlutterWay\logs\events\events.jsonl`
- أخطاء الويب: `%LOCALAPPDATA%\FlutterWay\logs\client-errors.jsonl` (يُدوّر عند 512 KB)
- تقرير ZIP: `%LOCALAPPDATA%\FlutterWay\logs\reports\flutterway-report-<timestamp>-<id>.zip`
- آخر Crash: `%LOCALAPPDATA%\FlutterWay\logs\reports\last-crash.json`

### محتوى ZIP

```
flutterway-report-YYYYMMDD-HHMMSS-<rand>.zip
├── report.json
├── report.md
├── environment.json   # allowlist فقط
├── manifest.json      # الاسم والحجم وSHA-256 لكل ملف
└── events.jsonl       # فقط عند اختيار الأحداث
```

- الكتابة ذرية: ملف `.part` ثم rename.
- الحد الأقصى 2 MB.
- أسماء ZIP فريدة حتى داخل نفس الثانية.

---

## 5. الملفات

| الملف | الوظيفة |
|---|---|
| `gui/diagnostics.py` | تنقية، أحداث، تقرير schema 2، ZIP آمن، hooks |
| `gui/version.py` | الإصدار + `BUILD_COMMIT` / `BUILD_DATE` وقت الحزمة |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | قالب البلاغ اليدوي |
| `gui/onboarding_app.py` | `get_report_preview`, `open_error_report`, `save_error_report`, `copy_error_report`, `open_reports_folder` |
| `gui/onboarding/index.html` | نافذة البلاغ + أزرار السياق |

---

## 6. الاختبارات

```powershell
python tests/test_diagnostics.py
python tests/test_diagnostics_redaction.py
python tests/test_diagnostics_artifacts.py
python tests/test_diagnostics_hooks.py
python tests/reliability_faults.py
```
