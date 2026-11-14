# حزمة FlutterWay Offline Agent Kit — Windows x64

هذه الحزمة مشروع محلي لمساعدة وكيل البرمجة على إنشاء وتطوير مشروع Flutter دون اتصال بعد التجهيز الأولي. لا تضع ملف ZIP الضخم داخل Git؛ نزّله من رابط MEGA أدناه، وتحقق من بصمته قبل فكّه.

## التنزيل والتحقق

- [تنزيل FlutterWay Agent Kit من MEGA](https://mega.nz/file/gy1TiJbK#kvhHFPNPDMgD06bZf5ozKk0TJOyIEI5xoPS44fZL4Ck)
- بصمة SHA-256 للأرشيف المحلي المنشور: `f9e0fa76800fbc5f764801b2ebe7413ad2fbce375e329ae5a3625ca0632a72b5`

بعد تنزيل الملف، افتح PowerShell في مجلد التنزيلات وتحقق من البصمة (عدّل اسم الملف أو مساره عند الحاجة):

```powershell
Get-FileHash .\FlutterWay-Agent-Kit-v1.0.0-windows-x64-offline.zip -Algorithm SHA256
```

لا تتابع إلا إذا تطابقت قيمة `Hash` مع البصمة أعلاه. أزل علامة الحظر قبل فك الضغط، ثم فك الأرشيف إلى مسار قصير مثل `C:\FlutterWay-Agent-Kit`:

```powershell
Unblock-File .\FlutterWay-Agent-Kit-v1.0.0-windows-x64-offline.zip
Expand-Archive .\FlutterWay-Agent-Kit-v1.0.0-windows-x64-offline.zip -DestinationPath C:\FlutterWay-Agent-Kit
```

## إنشاء مشروع Flutter محلي

افتح PowerShell في مجلد الحزمة:

```powershell
Set-Location C:\FlutterWay-Agent-Kit\FlutterWay-Agent-Kit-v1.0.0-windows-x64-offline
. .\Use-AgentKit.ps1
New-Item -ItemType Directory -Force "$env:USERPROFILE\source" | Out-Null
.\create_project.ps1 -ProjectName campus_tasks -Destination "$env:USERPROFILE\source\campus_tasks" -Organization com.example
```

المجلد الوجهة يجب ألا يكون موجودًا مسبقًا. إنشاء المشروع، تنزيل حزم القالب المخزنة، والتحليل والاختبارات الأولية تعمل محليًا دون إنترنت.

## تجهيز Android لمرة واحدة

الحزمة **لا تحتوي** ملفات Google Android SDK؛ شروط Google لا تسمح بإعادة توزيعها ضمن أرشيف MEGA. على كل حاسبة تريد بناء APK عليها، يلزم اتصال إنترنت لمرة واحدة لتنزيل SDK من Google وقبول الرخصة يدويًا:

```powershell
.\Setup-AndroidSDK.ps1
```

اقرأ مطالبات الرخصة ووافق عليها بنفسك. يثبت السكربت command-line tools وADB وAndroid platform 36 وbuild-tools 36.0.0.

## تهيئة اعتماديات المشروع للبناء دون إنترنت

بعد إنشاء مشروعك، شغّل أول بناء مع توفر الإنترنت لتخزين اعتماديات المشروع محليًا:

```powershell
.\Warm-OfflineBuild.ps1 -Project "$env:USERPROFILE\source\campus_tasks"
```

يتحقق السكربت من بناء APK أولي عبر الإنترنت، ثم من جلب الحزم دون إنترنت، والتحليل والاختبارات، وبناء Gradle دون إنترنت. بعد نجاح التهيئة، تقدر تعمل محليًا على **الحاسبة نفسها**:

```powershell
Set-Location "$env:USERPROFILE\source\campus_tasks"
flutter pub get --offline
flutter analyze
flutter test
.\android\gradlew.bat --offline -p .\android assembleDebug
```

إضافة plugin أو تغيير إصدارات الاعتماديات يحتاج إعادة تشغيل التهيئة مع الإنترنت. كاش Gradle/Maven وSDK تبقى محلية في الحاسبة ولا تنتقل مع رابط MEGA؛ لذلك الحاسبة الجديدة تحتاج تجهيز الإنترنت مرة واحدة أيضًا. لا تتضمن الحزمة Android Studio أو صور المحاكي أو تعريفات USB الخاصة بالمصنّعين.
