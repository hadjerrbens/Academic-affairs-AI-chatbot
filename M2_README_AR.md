# M2 — Academic Affairs Chatbot

هذه حزمة عمل M2 فقط، مخصّصة لفرع `m2` في مستودع الفريق. لم تُنشأ لتستبدل ملفات زملائك أو لتُدمج مباشرة في `main`.

## ماذا أنجزنا؟

| Feature | الملفات | الوظيفة |
|---|---|---|
| Authentication | `backend/app/core/security.py`, `backend/app/api/routes/auth.py` | `Argon2id`، التحقق من scrypt القديم وترقيته عند Login صحيح، `JWT`، Refresh rotation، Logout، rate limit وWebSocket ticket يُستخدم مرة واحدة |
| Degree requirements | `backend/app/data/progress_repo.py`, `kb/rules/requirements.pl` | قراءة البرامج والمجموعات والنتائج، فحص `REQUIRED` و`ELECTIVE` و`CREDITS` وعدم استخدام مادة في مجموعتين |
| GPA & Standing | `backend/app/domain/requirement_engine.py`, `backend/app/services/progress_service.py`, `kb/rules/standing.pl` | GPA واحد في Python، أربع حالات Standing في Prolog ومدة Appeal من CSV |
| Chat interface | `frontend/src/features/chat/` | شاشة محادثة، Login، SSE، Cancel، Retry، رسالة Login للبيانات الشخصية، عرض الإجابة ومراجع ومكونات قابلة للربط |
| Data & tests | `data/seed/`, `backend/tests/`, `frontend/tests/`, `data/golden/` | نسخة مطابقة من بيانات M2 المعتمدة واختبارات Backend/Frontend وأسئلة Demo |

**قواعد ثابتة:** لا تحمل أدوات M2 معاملات `student_id` أو `user_id`؛ هوية الطالب تأتي من `ctx.user`. لا نحسب GPA في Prolog أو LLM. لا نغير سياسات الدرجات أو أيام Appeal الموجودة في CSV. لا نعيد كتابة ملفات M1/M3/M4/M5.

## 1. الإضافة إلى فرع m2

نفّذ على جهازك بعد فك ضغط ZIP، من داخل نسخة Git المحلية الصحيحة:

```bash
git fetch origin
git switch m2
# Copy the ZIP to this machine, then extract new files without replacing existing files.
# Example: update the ZIP path to the location where you saved it.
unzip -n ~/Downloads/AcademicAffairs_M2_ready_manual_push.zip -d .
git status --short
```

راجع `git status` جيداً؛ الحزمة لا تتطلب حذف أي ملفات. لا ترفع `__pycache__`, `.pytest_cache`, `.env`, `demo_accounts.txt` أو credentials. ضع ملفات M2 فقط في staging:

```bash
git add backend/app/core/security.py backend/app/api/routes/auth.py \
  backend/app/data/progress_repo.py backend/app/domain/requirement_engine.py \
  backend/app/services/progress_service.py backend/tests/test_m2_*.py \
  backend/tests/kb/test_m2_prolog.py backend/tests/conftest.py \
  frontend/src/features/chat/ frontend/tests/ kb/rules/requirements.pl \
  kb/rules/standing.pl kb/m2_schema.toml data/seed/ data/policy_docs/ \
  data/golden/m2.jsonl M2_README_AR.md M2_INTEGRATION.md

git diff --cached --stat
git commit -m "M2: authentication GPA degree audit standing and chat shell"
git push origin m2
```

الخيار `unzip -n` لا يستبدل الملفات الموجودة مسبقاً. إذا رأيت ملفات M2 بنفس الأسماء في `git status`، راجعها وادمج التعديلات يدوياً بدلاً من الكتابة فوقها. الملفات هنا مطابقة للبيانات التي استُخدمت في إعداد M2.

## 2. الاختبار محلياً

من جذر المستودع:

```bash
cd backend
python -m pip install -r requirements.txt
python -m pytest -q tests/test_m2_security.py tests/test_m2_gpa.py \
  tests/test_m2_progress_service.py tests/kb/test_m2_prolog.py
cd ../frontend
node --test tests/*.test.mjs
```

الاختبارات المستقلة تستخدم `FakeCollection` أو Prolog Bridge وهمياً؛ لا تحتاج MongoDB أو Groq. اختبارات Prolog الفعلية تحتاج `SWI-Prolog` مثبتاً (`swipl`) ثم تشغيل pytest مجدداً. **لا تعتبر اختبارات Mock إثباتاً للتكامل الحقيقي.**

## 3. ما يحتاج تنسيقاً مع الفريق

اقرأ `M2_INTEGRATION.md` قبل تقديم العرض. ملفات M2 مستقلة حالياً لأن فرع `main` ما زال بلا M1 `shared_models.py`، ولا M3 `main.py`/Prolog bridge، ولا M4 ToolRegistry/M5 cards.

## 4. شرح قصير للعرض

1. `security.py`: يتحقق من كلمة المرور ويصدر Access/Refresh JWT؛ رمز Refresh القديم يصبح غير صالح بعد الاستخدام.
2. `progress_repo.py`: يجلب بيانات الطالب من `students` و`student_courses` والبرنامج والمجموعات.
3. `calculate_gpa`: تختار BEST attempt ثم تحسب المتوسط المرجح بالساعات؛ `F` تدخل في attempted و`I/W` مستثناة.
4. `requirements.pl`: يختبر كل مجموعة، ينقل `Used` إلى المجموعة التالية كي لا تُحسب المادة مرتين.
5. `standing.pl`: يقارن GPA بعتبات `standing_policies.csv`؛ Python تحسب تاريخ Appeal باستخدام `ctx.today`.
6. `ChatShell`: يرسل السؤال عبر SSE ويضيف أجزاء `delta` إلى رسالة واحدة، مع دعم Cancel وRetry.

## 5. حدود التحقق

- الاختبارات المحلية تشمل Auth، GPA، خدمة تقدم مع Fake Prolog، وSSE transport.
- الاختبار الفعلي لProlog يتطلب `SWI-Prolog` وجسر M3 لتوليد/تحميل Facts من CSV.
- تشغيل ChatShell في متصفح مع Groq/Database يتطلب Backend M3 وM4 وبقية مكونات الواجهة؛ لم يتم تأكيد هذا المسار كاملاً في هذه الحزمة.
- لا يوجد أي Password أو API key في هذه الحزمة بصيغته الصريحة؛ `users.csv` يحتوي Password hashes معتمدة فقط.
