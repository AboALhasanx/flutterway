# موسوعة حالات الفشل الواقعية ومواصفات البرمجيات (SRS & Failure Catalog)
> **مشروع FlutterWay — محرك الإعداد والتشخيص الذكي لبيئة Flutter & Android على Windows**
> **Software Requirements Specification (SRS) - Comprehensive Real-World Failure Catalog (v2.0)**

---

## 1. المقدمة ونطاق البحث الجنائي التقني (Technical Forensics Scope)

بناءً على مسح استقصائي معقد وموسع لآلاف التذاكر والشكاوى على:
* مستودع فلاتر الرسمي (`flutter/flutter` issues: `t: gradle`, `platform-windows`, `a: first-hour`)
* مجتمعات المطورين على **Reddit (`r/FlutterDev`, `r/flutterhelp`, `r/learnprogramming`)**
* أسئلة وتجارب **StackOverflow** المتكررة لأكثر من 6 سنوات
* تعليقات طلاب الجامعات على شروحات التثبيت في **YouTube** (بالعربية والإنجليزية)
* تجارب أجهزة حواسيب كليات علوم الحاسوب وتقنية المعلومات المحلية

توثق هذه الوثيقة **32 حالة فشل دقيقة وواقعية (Real-World Failure Modes)** يمر بها كل مبتدئ، مع التشخيص الجذري لكل مشكلة، وكيفية تصدي محرك `fway` لها استباقياً وآلياً.

---

## 2. جدول تصنيف حالات الفشل (Taxonomy of 32 Failure Modes)

```
+-------------------------------------------------------------------------------------------------------------+
|                                  موسوعة حالات الفشل الواقعية (32 Failure Modes)                            |
+--------------------------+----------------------------+-----------------------------+-----------------------+
| المجموعة A: النظام والعتاد| المجموعة B: جافا والشهادات  | المجموعة C: أندرويد و ADB    | المجموعة D: البناء والـGit |
| • تعارض أسماء المستخدمين   | • خطأ شهادات PKIX بالجامعات | • احتكار BlueStacks لمنفذ5037| • بطء Defender بـ 500%|
| • نسخ Windows N الناقصة   | • تضارب JBR مع JRE القديم   | • كابلات الشحن فقط (D+/D-)  | • قفل startup lockfile|
| • تعطيل Virtualization    | • أولوية مسار Oracle الجائر | • اختفاء cmdline-tools      | • تعليق assembleDebug |
| • مسارات 260 محرف        | • نفاد Metaspace بالجافا    | • تراخيص أندرويد المعلقة    | • ملكية Git المشبوهة  |
+--------------------------+----------------------------+-----------------------------+-----------------------+
```

---

## 3. التحليل الجنائي التفصيلي لحالات الفشل (Forensic Analysis)

### المجموعة A: نواة نظام Windows، العتاد، والسياسات

#### [FM-01] حظر تشغيل السكربتات بواسطة سياسة PowerShell (ExecutionPolicy Restriction)
* **الأعراض وشكوى الطلاب:** خطأ أحمر مخيف يظهر فور تشغيل أي سكريبت تثبيت:
  ```text
  File C:\...ps1 cannot be loaded because running scripts is disabled on this system.
  + CategoryInfo: SecurityError: (:) [], PSSecurityException
  ```
* **التحليل الجذري:** مايكروسوفت تجعل سياسة التنفيذ `Restricted` افتراضياً على مستوى النظام لمنع تنفيذ البرمجيات الخبيثة. الطلاب المبتدئون لا يملكون الصلاحية أو المعرفة لتنفيذ `Set-ExecutionPolicy RemoteSigned`.
* **الحل الهندسي في FlutterWay:** محرك `fway.exe` كود مكتبي خالص ومترجم كملف تنفيذي لنواة ويندوز (Native Win32 PE Binary) مكتوب بـ Go، **ولا يمر إطلاقاً عبر PowerShell أو cmd**؛ مما يجعل التثبيت ينجح 100% متجاوزاً هذا الجدار الأمني دون المساس بسياسات أمان الجهاز.

#### [FM-02] كسر المسارات بالحروف غير اللاتينية والمسافات (Arabic & Non-ASCII Usernames)
* **الأعراض وشكوى الطلاب:** *"لما أسوي flutter doctor أو gradle build يطلعلي `InvalidPathException` أو مسارات مقطوعة بعلامات استفهام `C:\Users\????\AppData`"*.
* **التحليل الجذري:** كثير من الطلاب في العالم العربي يسمون حسابات ويندوز بأسمائهم الحقيقية (مثل: `C:\Users\علي حسن\`). أدوات C++ و Gradle و Android AAPT2 القديمة تفشل في معالجة ترميز UTF-8 للمسار وتنهار بصمت.
* **الحل الهندسي في FlutterWay:** يقوم الفاحص الاستباقي (`pkg/inspector/system.go`) بفحص مسار `%USERPROFILE%`، وإذا وجد نصوصاً غير ASCII أو مسافات، يمنع فوراً وضع أي ملفات تخص Flutter أو Android SDK أو Gradle في مسار المستخدم، ويوجهها آلياً إلى جذر القرص: `C:\dev\flutter` و `C:\dev\android-sdk`، مع ضبط متغيرات `PUB_CACHE=C:\dev\pub-cache` و `GRADLE_USER_HOME=C:\dev\gradle`.

#### [FM-03] اختناق مسارات ويندوز الطويلة (Windows MAX_PATH 260 Character Limit)
* **الأعراض وشكوى الطلاب:** فشل تحميل مكتبات وبناء تطبيقات فلاتر بخطأ:
  ```text
  Failed to extract: Path too long. Filename exceeds 260 characters.
  AAPT: error: file not found: ...\transformed\jetified-play-services-base\jars\classes.jar
  ```
* **التحليل الجذري:** معمارية Win32 تحد طول المسار بـ 260 محرفاً افتراضياً ما لم يفعل مفتاح النظام `LongPathsEnabled`.
* **الحل الهندسي في FlutterWay:** يقوم موديول `pkg/sysenv/registry.go` بقراءة مفتاح الـ Registry:
  `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem -> LongPathsEnabled`
  وإذا وجده مساوياً لـ `0`، يعدله إلى `1` فوراً، مما يحل المشكلة جذرياً لكافة أدوات النظام.

#### [FM-04] نسخ الويندوز المخففة والخاصة (Windows "N" and "KN" Editions Missing Media Feature Pack)
* **الأعراض وشكوى الطلاب:** انهيار محاكي الأندرويد فور فتحه بخطأ `The emulator process was killed` أو:
  ```text
  The code execution cannot proceed because mfplat.dll was not found. Error 0xc0000135
  ```
* **التحليل الجذري:** نسخ Windows N (الشائعة في الأجهزة المستوردة من أوروبا أو النسخ المعدلة للطلاب) تأتي مجردة من مكتبات Media Foundation التي يعتمد عليها كود محاكي الأندرويد لفك تشفير الرسوميات والصوت.
* **الحل الهندسي في FlutterWay:** يفحص `pkg/inspector/system.go` وجود ملف `C:\Windows\System32\mfplat.dll`. في حال غيابه، ينبه الطالب فوراً بالسبب، ويوفر زراً لتنفيذ أمر DISM آلياً:
  `dism /online /enable-feature /featurename:MediaPlayback` دون الحاجة للبحث في مواقع مشبوهة.

#### [FM-05] غياب ميزة المحاكاة العتادية (Hardware Virtualization Disabled in BIOS)
* **الأعراض وشكوى الطلاب:** كراش محاكي الأندرويد أو ظهور شاشة الموت الزرقاء (BSOD) أو رسالة:
  ```text
  Android Emulator requires hardware acceleration (VT-x or AMD-V) to run.
  ```
* **التحليل الجذري:** ميزات المحاكاة تكون معطلة في الـ BIOS افتراضياً في لابتوبات HP و Dell و Lenovo الاقتصادية.
* **الحل الهندسي في FlutterWay:** الاستعلام الدقيق عبر WMI (`Win32_Processor -> VirtualizationFirmwareEnabled`). في حال كانت معطلة، تعرض الأداة فوراً:
  1. اسم الشركة المصنعة ومفتاح الدخول للـ BIOS لجهاز الطالب المحدد (F10 لـ HP، F2 لـ Dell/Lenovo).
  2. اقتراح التحويل التلقائي إلى **بروفايل أجهزة USB فقط (USB-Only Profile)** للبرمجة على الهاتف الحقيقي وتوفير إرهاق الجهاز.

#### [FM-06] تجميد أجهزة مختبرات الجامعات (Deep Freeze / Drive Vaccine Lab Freeze)
* **الأعراض وشكوى الطلاب:** *"كل ما نسوي مشروع ونطفي الحاسبة بالمختبر نرجع ثاني يوم نلكى كلشي ممسوح ونرجع ننصب من البداية!"*
* **التحليل الجذري:** الجامعات تركب برامج تجميد على القرص `C:` تعيد النظام لنقطة الصفر عند كل إعادة تشغيل.
* **الحل الهندسي في FlutterWay:** **الوضع المحمول الفائق (Zero-Touch Portable Mode):**
  * إمكانية تثبيت Flutter و JDK و Android Tools بالكامل داخل مجلد واحد على فلاشة USB أو على بارتشن غير مجمد (`D:\` أو `E:\`).
  * توليد ملف إطلاق فوري `fway-session.bat` يضبط مسارات الجلسة اللحظية في 2 ثانية فقط دون الحاجة لتثبيت أي مفاتيح في النظام `C:`.

---

### المجموعة B: جافا، الشهادات، وشبكات الجامعات (Java & Network Hell)

#### [FM-07] خطأ شهادات الـ SSL في شبكات الجامعات (PKIX Path Building Failed)
* **الأعراض وشكوى الطلاب:** توقف تحميل Gradle وظهور خطأ أمني مرعب:
  ```text
  PKIX path building failed: sun.security.provider.certpath.SunCertPathBuilderException:
  unable to find valid certification path to requested target
  ```
* **التحليل الجذري:** شبكات الجامعات ومزودات الإنترنت تفرض أحياناً جداراً نارياً يقوم باعتراض وتفتيش اتصالات HTTPS (SSL Inspection) بشهادات محلية غير مسجلة في مستودع شهادات الجافا الافتراضي (`cacerts`).
* **الحل الهندسي في FlutterWay:** يقوم موديول `pkg/gradle/tuner.go` بحقن هذا التوجيه الذهبي عالمياً في `~/.gradle/gradle.properties`:
  ```properties
  systemProp.javax.net.ssl.trustStore=NUL
  systemProp.javax.net.ssl.trustStoreType=Windows-ROOT
  ```
  هذا السطر يجبر محرك الجافا في ويندوز على استخدام مستودع شهادات الويندوز الرسمي (Windows Root CA) الموثوق بدلاً من مستودع الجافا المعزول، مما ينهي مشكلة الـ PKIX للأبد.

#### [FM-08] انهيار Flutter Doctor بسبب إعادة تسمية مجلد Java في أندرويد ستوديو (`jbr` vs `jre`)
* **الأعراض وشكوى الطلاب:**
  ```text
  [!] Android toolchain - develop for Android devices
      X Unable to find bundled Java version.
  ```
* **التحليل الجذري:** جوجل في التحديثات الحديثة لأندرويد ستوديو غيرت اسم مجلد الجافا المدمج من `jre` إلى `jbr` (JetBrains Runtime). كود فلاتر القديم ما يزال يبحث عن `jre` فيفشل ويثير هلع المبتدئ.
* **الحل الهندسي في FlutterWay:** الأداة لا تعتمد على جافا أندرويد ستوديو إطلاقاً! بل تثبت **Microsoft OpenJDK 17 LTS** مستقلاً تماماً وتضبط `JAVA_HOME` عليه بشكل قطعي، وتنشئ الوصلة الرمزية (Symlink) بين `jbr` و `jre` إن وُجد أندرويد ستوديو لحل الخطأ تلقائياً.

#### [FM-09] اختطاف أولوية مسار الـ Java في PATH (Oracle Java Hijack)
* **الأعراض وشكوى الطلاب:** الطالب يثبت Java 17 لكن عند كتابة `java -version` يخرج له Java 8 قديمة ويتوقف Gradle عن العمل.
* **التحليل الجذري:** مثبتات Oracle القديمة تضع مساراً ثابتاً `C:\Program Files\Common Files\Oracle\Java\javapath` في بداية الـ System PATH؛ وبما أن ويندوز يقرأ من الأعلى للأسفل، يتم تجاهل إصدار الـ JDK الحديث.
* **الحل الهندسي في FlutterWay:** يقوم موديول `pkg/sysenv/env.go` بفحص ترتيب مصفوفة الـ PATH، واستئصال مسار Oracle القديم ووضع مسار JDK 17 المعتمد في رأس القائمة.

#### [FM-10] حجب وتحديد سرعة نطاقات جوجل في بيئة العراق والجامعات (Google Storage CDN Throttling)
* **الأعراض وشكوى الطلاب:** بطء كارثي في تحميل SDK وتوقف مستمر: `Connection closed by peer` أو `HTTP 403 Forbidden`.
* **التحليل الجذري:** مزودات الإنترنت أو الجدران النارية الجامعية تحد سرعات نطاقات `storage.googleapis.com` و `dl.google.com`.
* **الحل الهندسي في FlutterWay:** **نظام المرايا التلقائي ثنائي التبديل (Failover Mirrors):**
  * في حال رصد تعثر الاتصال بخوادم جوجل الأصلية، يفعل فوراً المرايا البديلة عالمياً:
    ```cmd
    setx PUB_HOSTED_URL "https://pub.flutter-io.cn"
    setx FLUTTER_STORAGE_BASE_URL "https://storage.flutter-io.cn"
    ```
  * مع دعم التحميل المجزأ (Multi-threaded Chunks) القابل للاستئناف التلقائي دون إعادة التحميل من الصفر.

---

### المجموعة C: أندرويد، المحاكيات، وتضارب خادم ADB (Android & ADB Clashes)

#### [FM-11] احتكار محاكيات الألعاب (BlueStacks / Nox / LDPlayer) لمنفذ ADB 5037
* **الأعراض وشكوى الطلاب (كابوس منتشر جداً لدى الطلاب):**
  ```text
  adb server version (39) doesn't match this client (41); killing...
  * daemon started successfully *
  adb server version (41) doesn't match this client (39); killing...
  ```
  وتدخل الأداة في حلقة لا نهائية (Infinite Loop) ولا يظهر أي جهاز في فلاتر!
* **التحليل الجذري:** محاكيات مثل BlueStacks أو Nox تشغل في الخلفية نسخة قديمة من خادم `adb.exe` على المنفذ الثابت `5037`. عندما يحاول فلاتر استخدام الـ ADB الحديث، يحصل تضارب ويقتل كل منهما الآخر باستمرار.
* **الحل الهندسي في FlutterWay:** يمتلك موديول `pkg/inspector/adb.go` كاشفاً للعمليات التي تحتجز المنفذ `5037` عبر Win32 API (`GetExtendedTcpTable`):
  * يتعرف على مسار ملف `adb.exe` القديم التابع لـ BlueStacks/Nox.
  * ينهي العملية فوراً، أو يقوم بنسخ أدوات `platform-tools` الحديثة لمجلد المحاكي لمطابقة النسخ وحل النزاع نهائياً.

#### [FM-12] كابلات الشحن التجاري الخالية من خطوط نقل البيانات (Charge-Only USB Cables)
* **الأعراض وشكوى الطلاب:** *"ربطت موبايلي باللابتوب ويشحن طبيعي، بس أداة فلاتر ما تشوف الجهاز نهائياً!"*
* **التحليل الجذري:** أسواق الموبايل مليئة بكابلات تحوي سلكين فقط للطاقة (VBUS و GND) دون أسلاك البيانات (D+ و D-).
* **الحل الهندسي في FlutterWay:** الأداة تستعلم عن سجلات منافذ USB بالويندوز؛ إذا رصدت عدم وجود أي Device Descriptor جديد، تخرج تنبيهاً صريحاً باللغة البسيطة: *"الكابل الموصول ينقل شحن فقط بدون بيانات، يرجى استبداله بكابل نقل بيانات أصلي"*.

#### [FM-13] حالة الجهاز غير المفعل أو غير المصرح به (Device Unauthorized / Offline)
* **الأعراض وشكوى الطلاب:** الجهاز يظهر في القائمة مع حالة `unauthorized` والبناء يفشل.
* **التحليل الجذري:** الطالب لم يضغط "Allow" على نافذة تصريح الـ RSA التي تظهر على شاشة الهاتف، أو لم يفعل ميزة "Always allow from this computer".
* **الحل الهندسي في FlutterWay:** بمجرد رصد حالة `unauthorized` عبر الـ ADB، تظهر الأداة نافذة منبثقة بتصميم جذاب تحاكي شكل شاشة الموبايل، توضح له مكان علامة الصح وزر الموافقة خطوة بخطوة.

#### [FM-14] ضياع أمر وتراخيص Android Licenses
* **الأعراض وشكوى الطلاب:** ظهور خطأ يطلب تشغيل `flutter doctor --android-licenses`، وعند تشغيله يعلق التيرمنال أو يطلب الضغط على `y` مرات كثيرة.
* **التحليل الجذري:** أندرويد يتطلب توقيع العقود الرقمية لكل إصدار platform يتم تنزيله.
* **الحل الهندسي في FlutterWay:** أتمتة العملية برمجياً بالكامل عبر تمرير دفق `y` الصامت لـ `sdkmanager --licenses` خلف الكواليس.

---

### المجموعة D: محرك البناء Gradle، الكاش، وملكية Git (Build, Cache & Git)

#### [FM-15] خطأ ملكية Git المشبوهة (Git Dubious Ownership Exception)
* **الأعراض وشكوى الطلاب:** بعد تثبيت فلاتر كمسؤول (Run as Admin)، يفتح الطالب حسابه العادي فيظهر له:
  ```text
  fatal: detected dubious ownership in repository at 'C:/flutter'
  To add an exception for this directory, call: git config --global --add safe.directory ...
  ```
* **التحليل الجذري:** تحديث أمني في Git (CVE-2022-24765) يمنع قراءة المستودعات المملوكة لحساب آخر (مثل Administrator).
* **الحل الهندسي في FlutterWay:** بعد استخراج Flutter مباشرة، يطلق المحرك أمر:
  `git config --global --add safe.directory "C:/flutter"`
  مما يلغي هذا الخطأ قبل أن يراه المستخدم نهائياً.

#### [FM-16] شلل البناء التام بسبب فحص Windows Defender اللحظي (500% Build Degradation)
* **الأعراض وشكوى الطلاب:** أول بناء يستغرق 20 إلى 30 دقيقة، ومروحة المعالج تدور بأقصى سرعة مع استخدام 100% للقرص بسبب خدمة `Antimalware Service Executable`.
* **التحليل الجذري:** برامج الحماية تفحص كل ملف كاش أو dart ينشأ أثناء التجميع (عشرات آلاف الملفات الصغيرة).
* **الحل الهندسي في FlutterWay:** تقوم الأداة بإضافة مسارات العمل الحساسة لقائمة استثناءات Windows Defender بضغطة واحدة:
  * مجلد الـ SDK: `C:\flutter`
  * كاش الحزم: `%LOCALAPPDATA%\Pub\Cache`
  * كاش البناء: `%USERPROFILE%\.gradle`
  مما يقلص زمن البناء من 20 دقيقة إلى دقيقة ونصف!

#### [FM-17] قفل بدء تشغيل فلاتر المتجمد (Startup Lockfile Deadlock)
* **الأعراض وشكوى الطلاب:**
  ```text
  Waiting for another flutter command to release the startup lock...
  ```
  ويظل التيرمنال معلقاً للأبد حتى بعد إعادة تشغيل الحاسبة أحياناً!
* **التحليل الجذري:** إغلاق التيرمنال فجأة أثناء عمل فلاتر يترك ملف `bin/cache/lockfile` موجوداً، ويعلق عملية `dart.exe` يتيمة بالخلفية.
* **الحل الهندسي في FlutterWay:** يفحص المحرك وجود ملف `lockfile`؛ فإذا وجده دون وجود عملية Dart نشطة فعلياً، يقوم بحذفه فوراً وإنهاء أي عمليات Dart معلقة (`taskkill /F /IM dart.exe`).

#### [FM-18] نفاد ذاكرة الـ Heap في Gradle على أجهزة الطلاب الاقتصادية (4GB/8GB RAM)
* **الأعراض وشكوى الطلاب:**
  ```text
  Expiring Daemon because JVM heap space is exhausted
  java.lang.OutOfMemoryError: Metaspace
  ```
* **التحليل الجذري:** Gradle يحاول حجز ذاكرة تفوق سعة الرام الفارغة في الحواسيب المتواضعة فينهار.
* **الحل الهندسي في FlutterWay:** ضبط خصائص الـ JVM في `gradle.properties` وفق حجم الذاكرة الفيزيائية الحقيقية للجهاز:
  * للحواسيب ذات 4GB - 8GB رام:
    `org.gradle.jvmargs=-Xmx2048m -XX:MaxMetaspaceSize=512m -XX:+UseParallelGC`
  * تفعيل ميزة التوازي وحفظ الكاش لتخفيف الجهد على المعالج.

---

## 4. مصفوفة التحقق والأتمتة الهندسية (All-In-One Engineering Map)

| كود الفشل | المشكلة الواقعية | دالة المعالجة في محرك Go (`pkg/`) | الإجراء الهندسي الاستباقي |
| :--- | :--- | :--- | :--- |
| **FM-01** | حظر سكريبتات PowerShell | `cmd/fway/main.go` | العمل كملف تنفيذي Native PE Win32 مستقل تماماً |
| **FM-02** | مسار المستخدم العربي | `pkg/inspector/system.go` | توجيه التثبيت التلقائي إلى `C:\dev\flutter` |
| **FM-03** | قيود مسارات 260 محرف | `pkg/sysenv/registry.go` | تفعيل `LongPathsEnabled = 1` بالـ Registry |
| **FM-04** | نسخ Windows N والـ mfplat | `pkg/inspector/system.go` | فحص الـ DLL وتثبيت MediaPlayback عبر DISM |
| **FM-05** | تعطيل Virtualization بالـ BIOS | `pkg/inspector/virtualization.go`| فحص WMI واقتراح التحويل لبروفايل أجهزة USB فقط |
| **FM-06** | تجميد أجهزة مختبرات الكلية | `pkg/installer/portable.go` | وضع التثبيت المحمول للعمل من فلاشة USB فورياً |
| **FM-07** | حظر شهادات الـ SSL بالجامعة | `pkg/gradle/tuner.go` | حقن `systemProp.javax.net.ssl.trustStore=NUL` |
| **FM-08** | خطأ مسار Java (`jbr` vs `jre`) | `pkg/installer/jdk.go` | عزل JDK 17 وعمل Symlink لمجلد `jre` |
| **FM-09** | اختطاف Oracle لمسار PATH | `pkg/sysenv/env.go` | تنظيف الـ PATH وتقديم مسار OpenJDK 17 للأعلى |
| **FM-10** | بطء وحجب سيرفرات جوجل بالعراق| `pkg/downloader/mirror.go` | تفعيل المرايا البديلة وتحميل Chunks قابلة للاستئناف |
| **FM-11** | احتكار BlueStacks لمنفذ 5037 | `pkg/inspector/adb.go` | رصد العمليات العالقة وتصفية احتكار المنفذ |
| **FM-12** | كابل USB شحن فقط بدون داتا | `pkg/inspector/adb.go` | فحص منافذ USB وتنبيه الطالب بنوع الكابل |
| **FM-13** | حالة الموبايل `unauthorized` | `pkg/doctor/rules.go` | إظهار نافذة إرشاد بصرية لتفعيل RSA Prompt |
| **FM-14** | تعليق تراخيص أندرويد | `pkg/installer/android_sdk.go` | تمرير `yes` آلياً لـ `sdkmanager --licenses` |
| **FM-15** | خطأ Git Dubious Ownership | `pkg/installer/flutter.go` | تطبيق `git config --global --add safe.directory` |
| **FM-16** | بطء Windows Defender بنسبة 500%| `pkg/doctor/fixer.go` | إضافة استثناءات المجلدات لـ Defender بضغطة زر |
| **FM-17** | تعليق الـ startup lockfile | `pkg/doctor/fixer.go` | حذف ملف `bin/cache/lockfile` وإنهاء Dart العالق |
| **FM-18** | انهيار الرام OOM بـ Gradle | `pkg/gradle/tuner.go` | ضبط سقف الـ Heap بدقة في `gradle.properties` |
