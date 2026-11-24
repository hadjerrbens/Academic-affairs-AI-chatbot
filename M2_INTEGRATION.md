# M2 integration hand-off (do not modify other owners' files automatically)

هذه معلومات تسليم للزملاء. الواجهات الموضحة تعتمد على الملفات الموجودة في فروع الفريق، لذلك لا تعمل وحدها قبل دمج M1/M3/M4/M5.

## M3 — Application startup & Prolog

- تثبيت `SWI-Prolog` واختيار/تجهيز `ask(goal, **params)` داخل `app.core.prolog_engine` كما في `02_PROLOG_LOOKUP_PLAN.md`.
- دمج أقسام `kb/m2_schema.toml` في `kb/schema.toml` **بعد مراجعة M3**، دون استبدال أقسام الآخرين.
- توليد Facts من CSV وتحميل `kb/rules/standing.pl`, `kb/rules/requirements.pl` عند startup، مع اختبار `ask('standing_classify({gpa}, Status)', gpa=2.5)`.
- لا يوجد عمود `priority` في بيانات `requirement_groups.csv` المعتمدة. تستخدم M2 ترتيب الصفوف الحالي مؤقتاً؛ يجب تأكيد ترتيب التخصيص مع الفريق قبل تغيير البيانات.

**Example wiring sketch — M3 يكيّفه مع طريقة إنشاء DB الفعلية:**

```python
from app.api.routes.auth import router as auth_router, AuthService
from app.data.progress_repo import ProgressRepo
from app.services.progress_service import ProgressService, configure_progress_service
from app.data.records_repo import get_grade_points_map, passing_points
from app.core.prolog_engine import ask

# db must expose synchronous users, students, refresh_sessions collections.
# Motor's async collections require an adapter or async service implementation.
progress = ProgressService(
    ProgressRepo(db),
    kb_query=ask,
    grade_points_provider=get_grade_points_map,
    passing_points_provider=passing_points,
)
progress.register(registry)  # M4's ToolRegistry instance
configure_progress_service(progress)

app.state.auth_service = AuthService(
    db, jwt_secret=settings.jwt_secret,
    standing_loader=progress.get_standing_status,
)
app.state.auth_service.ensure_indexes()
app.include_router(auth_router)
```

لا تضع هذا المقطع مباشرة في `main.py` قبل توافقه مع startup الخاص بـ M3. تأكد من استخدام PyMongo synchronous `db` أو Adapter إن كان M3 يعمل بـ Motor asynchronous. Auth endpoints نفسها `def` وتعمل في Threadpool الخاصة بـ FastAPI.

## M1 / M4 — Cross-member contracts

- M1 `get_student_record(student_id)`:
  ```python
  from app.data.progress_repo import get_student_record
  ```
  بعد إنجاز M3 يمكن ضبط الـ default repo بـ DB مناسب. `get_standing_for_registration(student_id) -> (blocked, reason)` جاهز للتوصيل بمصدر M1.
- M4 `get_grade_points_map()` و`passing_points()` هما المصدر الرسمي. M2 لا تُعيد تعريف جدول الدرجات.
- M4 يمكنه استدعاء `get_standing_status(student_id)` ثم استخدام `status` و`blocks_transcripts` وتوافق `AuthUser.id == student_id` مع سجلات الطالب.
- M4 يسجل الأدوات عبر `progress.register(registry)`. الأدوات الثلاث: `get_major_requirements`, `audit_degree_progress`, `get_academic_standing`.

## M2 ChatShell — browser wiring

```tsx
// Inside the app entry once frontend is available:
import ChatShell from './features/chat/ChatShell';
export default function App() { return <ChatShell />; }
```

هذه واجهة MVP أساسية؛ عند وصول M5، مرّر `renderCitations`, `renderTool`, `renderConfirmation` باستخدام مكونات M5، و`connectionStatus` من `useRealtime()` الخاص بـ M1. M4 هو المسؤول عن Degraded Banner وM5 عن Starter Chips حسب خطة Prolog الأخيرة.

`frontend/vite.config.js` الموجود بفرع M4 يمرر `/api` إلى FastAPI ويزيل prefix. تأكد أن مسارات `/auth/...` و`/chat/stream` عند M3 تستخدم نفس القاعدة.

## Dataset (original)

هذه الملفات من dataset المعتمد دون تغيير: `programs.csv`, `requirement_groups.csv`, `requirement_group_courses.csv`, `students.csv`, `student_courses.csv`, `standing_policies.csv`, `users.csv`. لا ترفع `demo_accounts.txt` (كلمات المرور الصريحة).

## Real integration checks (after team merge)

1. Login الصحيح -> `/auth/me` يعمل؛ الخطأ في email/password يعطي نفس 401؛ استخدام Refresh القديم للمرة الثانية يفشل.
2. `S0000003` يجب أن يعود `PROBATION` وفق الجدول؛ `S0000004` = `WARNING`؛ `S0000010` = `DISMISSAL`.
3. Demo `S0000001`: Audit يكتمل؛ `S0000002`: `CS404` غير مكتملة (In progress).
4. Browser: رسالة SSE `delta` تتجمع؛ Logout يمسح المحادثة الشخصية المعروضة؛ `401` يجرّب Refresh مرة واحدة فقط.
5. `kb/rules` parity tests تُنفَّذ عبر SWI-Prolog، ثم اختبار `ask()` الحقيقي بعد توليد facts.
