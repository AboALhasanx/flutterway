# تبليغ الأخطاء — FlutterWay

> **المرحلة:** Phase A — تشخيص محلي + GitHub Issue (opt-in).
> **الحالة:** منفّذ. لا يوجد إرسال تلقائي.

---

## 1. كيف يصل البلاغ؟

```
خطأ في التطبيق
   ↓
سجل محلي في %LOCALAPPDATA%\FlutterWay\logs
   ↓
المستخدم يضغط «أبلغ عن مشكلة»
   ↓
معاينة البيانات + وصف اختياري
   ↓
GitHub Issue مُعبّأ مسبقاً (المستخدم يراجع ويضغط Submit)
   أو حفظ ZIP وإرساله يدوياً
```

**لا يوجد GitHub Token داخل التطبيق.** الرابط فقط، والمستخدم هو من ينشر البلاغ.

---

## 2. من وين يفتح المستخدم البلاغ؟

- **المزيد → أبلغ عن مشكلة**.
- **شاشة فشل التجهيز** → زر «أبلغ عن المشكلة».
- **شاشة فشل البناء** → زر «أبلغ عن مشكلة البناء».
- أخطاء JavaScript تُسجّل محلياً تلقائياً، لكن **لا تُرسل** حتى يفتح المستخدم البلاغ.

---

## 3. شنو يُرسل؟

- إصدار FlutterWay + commit.
- نظام التشغيل + إصدار Python/WebView.
- المرحلة (تجهيز/بناء/Hot Reload).
- رسالة الخطأ + Stack trace.
- آخر 120 سطر من السجل (منقّاة).
- وصف المستخدم الاختياري.

## شنو ما يُرسل؟

- اسم المستخدم أو `C:\Users\...` → `<home>` / `<user>`.
- أسماء مشاريع أو ملفات شخصية.
- كود `main.dart` أو ملفات المشروع.
- Tokens (`ghp_`, `github_pat_`, `sk-`) → `<github-token>` / `<api-key>`.
- Screenshots.

---

## 4. وين تُحفظ؟

- السجل: `%LOCALAPPDATA%\FlutterWay\logs\flutterway.log`
- أخطاء الويب: `%LOCALAPPDATA%\FlutterWay\logs\client-errors.jsonl`
- تقرير ZIP: `%LOCALAPPDATA%\FlutterWay\logs\reports\flutterway-report-*.zip`
- آخر Crash: `%LOCALAPPDATA%\FlutterWay\logs\reports\last-crash.json`

---

## 5. الملفات

| الملف | الوظيفة |
|---|---|
| `gui/diagnostics.py` | تسجيل، تنقية، بناء التقرير، GitHub URL، ZIP |
| `gui/version.py` | إصدار التطبيق |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | قالب البلاغ اليدوي |
| `gui/onboarding_app.py` | `report_client_error`, `get_error_report`, `open_error_report`, `save_error_report`, `copy_error_report` |
| `gui/onboarding/index.html` | نافذة البلاغ + أزرار السياق |

---

## 6. الاختبارات

```powershell
python tests/test_diagnostics.py
python tests/reliability_faults.py
python tests/audit_smoke.py
```

- `test_diagnostics.py`: تنقية، URL، ZIP، JSONL، API.
- `reliability_faults.py`: نافذة البلاغ، الإغلاق، فتح GitHub الوهمي، التقاط JS error.

---

## 7. المرحلة القادمة (اختياري)

- Supabase Edge Function لتجميع البلاغات بدون حساب GitHub.
- Fingerprint/dedupe + لوحة متابعة.
- Offline queue + «إرسال لاحقاً».
- Sentry اختياري مع opt-in.
